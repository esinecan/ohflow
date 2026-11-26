"""The scheduler.

The supervisor loop schedules the phases and launches the steps. Each step
other than a merge step runs in a step thread, which runs its gate, decides
its retry and can set the run's abort.

For each phase in order:
  1. Write `phase_started`.
  2. Compute each step's fingerprint. Mark matching passed steps `cached`.
  3. Launch the remaining steps under `max_parallel` slots, the step with
     the longest estimate first.
  4. On a terminal handle, run the step's gate, write `gate.json`, write
     `attempt_finished`.
  5. When every step in the phase is terminal, apply the failure policy, write
     `phase_settled`, and move to the next phase.

A barrier waits for every step to reach a TERMINAL state, not a successful one.
There is no state that waits forever: `execution_timeout_s` bounds every step.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Callable

from . import attempt_record, console
from . import budget as ohbudget
from . import estimate as ohestimate
from . import exec as ohexec
from . import failure as ohfail
from . import gates as ohgates
from . import attempts as ohattempts
from . import kill as ohkill
from . import preflight as ohpreflight
from . import report as ohreport
from . import retrodraft as ohretro
from . import retry as ohretry
from . import rundir
from . import runnotes as ohrunnotes
from . import harness_executor as ohexecutor
from . import worktree as ohwt
from .coords import coord, phase_coord, render_position
from .fingerprint import fingerprint
from .run_log import SYNTHETIC_ATTEMPT, RunLog, RunState
from .harness_executors import (CAP_REATTACH, harness_executor_for,
                                harness_executor_info, harness_executor_module)
from .paths import win, python_cmd
from .workflow import Workflow, Phase, Step, slug, to_jsonable

__all__ = ["Engine", "new_run_id", "PreflightError"]


class PreflightError(RuntimeError):
    """A named failure before any worktree is created."""


def new_run_id() -> str:
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"r-{stamp}-{secrets.token_hex(4)}"


#: The test-summary formats the baseline reads counts from, tried in order.
BASELINE_FORMATS = ("vitest", "unittest", "pytest")

_FENCED_JSON = re.compile(r"```json\s*(.+?)\s*```", re.DOTALL | re.IGNORECASE)

_ZAI_RESET = re.compile(r"1308.*?will reset at (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", re.DOTALL)
_ZAI_RESET_ZONE = _dt.timezone(_dt.timedelta(hours=8))
_CODEX_RESET = re.compile(r"usage limit.*?try again at (\d{1,2}):(\d{2})\s*([AP]M)",
                          re.DOTALL | re.IGNORECASE)


def _provider_reset_at(error: str | None, now: _dt.datetime | None = None) -> float | None:
    m = _ZAI_RESET.search(error or "")
    if m:
        when = _dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=_ZAI_RESET_ZONE)
        return when.timestamp() + 60.0
    m = _CODEX_RESET.search(error or "")
    if not m:
        return None
    now = now or _dt.datetime.now().astimezone()
    hour = int(m.group(1)) % 12 + (12 if m.group(3).upper() == "PM" else 0)
    when = now.replace(hour=hour, minute=int(m.group(2)), second=0, microsecond=0)
    if when <= now:
        when += _dt.timedelta(days=1)
    return when.timestamp() + 60.0


def _fenced_json(text: str):
    """The last fenced json block in a command step's stdout, parsed. None on
    failure; the `schema_valid` gate turns that into a recorded failure, not a
    crash. Agent harness executors parse their final message with
    `structured.parse_structured` instead."""
    blocks = _FENCED_JSON.findall(text or "")
    if not blocks:
        return None
    try:
        return json.loads(blocks[-1])
    except json.JSONDecodeError:
        return None


class _StartQueue:
    """The slots of one phase, granted in the order the queue was built in.

    A `threading.Semaphore` wakes whichever waiter the scheduler picks. This
    grants a free slot only to the step at the head of the queue, so the order
    the engine chose is the order the steps start in.
    """

    def __init__(self, limit: int, order: list[str]):
        self._free = limit
        self._waiting = list(order)
        self._turn = threading.Condition()

    def acquire(self, c: str) -> None:
        with self._turn:
            self._turn.wait_for(
                lambda: self._free > 0 and self._waiting[0] == c)
            self._waiting.pop(0)
            self._free -= 1
            self._turn.notify_all()

    def release(self) -> None:
        with self._turn:
            self._free += 1
            self._turn.notify_all()


class Engine:
    def __init__(self, workflow: Workflow, run_dir: Path, *, run_id: str | None = None,
                 max_parallel: int | None = None,
                 dry_run: bool = False, only_phase: str | None = None,
                 resume: bool = False, verbose: bool = True,
                 workflow_path: str | None = None,
                 workflow_args: dict | None = None,
                 auto_resume: int | None = None,
                 reservation_token: str | None = None,
                 predictions: str | None = None,
                 token_budget: int | None = None,
                 harness_executors: Callable[[str], ohexecutor.HarnessExecutor] | None = None):
        console.use_utf8()
        # Names a harness executor and returns the `HarnessExecutor` object that launches its agents.
        # The registry answers by default; a test passes one that returns a fake.
        self.harness_executors = harness_executors if harness_executors is not None else harness_executor_for
        from .workflow import normalize_handovers
        self.workflow = normalize_handovers(workflow)
        # How the workflow module was named to the CLI, kept so a run directory can
        # say where its own workflow came from. It is deliberately not a field of
        # `Workflow`: `Workflow` feeds the fingerprint, and a machine-specific path in
        # the cache key would invalidate every cache on every move.
        self.workflow_path = workflow_path
        # The `--args` the CLI was given, verbatim. `Workflow.args` is only what the
        # workflow module chose to copy back, and a workflow that copies nothing still
        # needs its arguments to be rebuildable later.
        self.workflow_args = dict(workflow_args or {})
        self.run_dir = Path(run_dir)
        # The run id comes from the caller, and the caller names the directory
        # with it. One mint per run: a directory and the JSON inside it can
        # never name different runs.
        self.run_id = run_id or self.run_dir.name
        # The `--max-parallel` value verbatim, or None when the flag was absent.
        # The two are different instructions: absent means "every phase decides",
        # present means "no phase goes above this". `or` cannot tell them apart,
        # and it also reads 0 as absent.
        #
        # The CLI rejects a bad value with exit 2, and so does this constructor.
        # A caller reaching the engine directly is a workflow author or a test, and
        # silently rounding an override of 0 up to 1 would hide the same fault
        # the CLI refuses.
        if max_parallel is not None:
            if isinstance(max_parallel, bool) or not isinstance(max_parallel, int):
                raise ValueError(
                    f"max_parallel must be an integer or None, got "
                    f"{type(max_parallel).__name__} {max_parallel!r}")
            if max_parallel < 1:
                raise ValueError(
                    f"max_parallel must be at least 1, got {max_parallel}. "
                    f"Pass None to let each phase decide.")
        self.cli_max_parallel = max_parallel
        self.max_parallel = max_parallel or workflow.max_parallel
        # How many times a deferred phase may auto-resume itself. `--auto-resume`
        # overrides the workflow; absent, the workflow decides; the workflow's own default
        # is 0, which is the pause-and-wait-for-a-human behaviour.
        if auto_resume is not None:
            if isinstance(auto_resume, bool) or not isinstance(auto_resume, int) \
                    or auto_resume < 0:
                raise ValueError(
                    f"auto_resume must be an integer of at least 0 or None, "
                    f"got {auto_resume!r}")
        self.auto_resume = (auto_resume if auto_resume is not None
                            else workflow.auto_resume)
        if token_budget is not None and (isinstance(token_budget, bool)
                                         or not isinstance(token_budget, int)
                                         or token_budget < 1):
            raise ValueError(
                f"token_budget must be an integer of at least 1 or None, "
                f"got {token_budget!r}")
        self.cli_token_budget = token_budget
        self.budget: ohbudget.Ledger | None = None
        self._budget_spent = threading.Event()
        self.poll_interval_s = 2.0
        self.dry_run = dry_run
        self.only_phase = only_phase
        self.resume = resume
        # A detached parent reserves the directory before it can open the
        # child's log. Only the child carrying this one-time token may turn
        # that reservation into engine ownership.
        self.reservation_token = reservation_token
        self.predictions = predictions
        self._owns_run_dir = False
        self.verbose = verbose
        self.run_log = RunLog(self.run_dir)
        self.state = RunState()
        self._lock = threading.Lock()
        self._handles: dict[str, Any] = {}
        self._handles_lock = threading.Lock()
        self._killed_by_abort: set[str] = set()
        self._abort = threading.Event()
        # A transient failure pauses the run instead of aborting it. The two are
        # different verdicts: `_abort` says the work was judged and rejected,
        # `_paused` says the work never got its turn.
        self._paused = threading.Event()
        self._backoff_lock = threading.Lock()
        self._cooldown_until = 0.0
        self._transient_hits = 0

    # ------------------------------------------------------------- plumbing

    def say(self, *a):
        """Every console line in the run goes through here.

        `console.say` cannot raise: a character the stream's encoding does not
        carry is replaced, not thrown. A step thread that logs an agent's
        box-drawing output therefore survives the line.
        """
        if self.verbose:
            console.say(*a)

    def _transition(self, event: str, *, coord_: str | None = None,
                    attempt: int | None = None, payload: dict | None = None):
        """Write the transition, then rebuild state from the file it was written
        to. The in-memory board can then never disagree with the run log."""
        with self._lock:
            self.run_log.append(event, coord=coord_, attempt=attempt,
                                payload=payload or {})
            self.state = RunLog.replay(self.run_dir)
            ohreport.write_board_md(self.run_dir, self.workflow, self.state)
            self._write_liveness()

    def _write_liveness(self) -> None:
        """Record which supervisor owns the run."""
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / "supervisor.pid").write_text(str(os.getpid()),
                                                     encoding="utf-8")

    def step_dir(self, c: str) -> Path:
        return rundir.step_dir(self.run_dir, c)

    def phase_limit(self, phase: Phase) -> int:
        """How many steps of this phase may run at once.

        Each knob means one thing. `Workflow.max_parallel` is the limit for a phase
        that declares none. `Phase.max_parallel` is that phase's own limit, and
        it may sit above or below the workflow default. `--max-parallel` sets the
        default and is also a ceiling on every phase, so an operator can throttle
        a whole run from the command line without editing the workflow.

        The engine guarantees the order of phases. Inside one phase the slots
        go to the steps in the order `_start_order` gives, which follows the
        estimate and not the workflow, so no workflow may depend on it.
        """
        run_default = (self.cli_max_parallel if self.cli_max_parallel is not None
                       else self.workflow.max_parallel)
        limit = (phase.max_parallel if phase.max_parallel is not None
                 else run_default)
        if self.cli_max_parallel is not None:
            limit = min(limit, self.cli_max_parallel)
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            # `workflow.validate` refuses this, and an unvalidated workflow reaching the
            # engine is still a fault worth naming. Rounding it up to one would
            # run the phase at a limit nobody asked for.
            raise ValueError(
                f'phase "{phase.name}": max_parallel resolved to {limit!r}, '
                f"which is not a positive integer. Run `ohflow validate` on "
                f"this workflow.")
        return limit

    # ------------------------------------------------------------ preflight

    def preflight(self) -> list[str]:
        return ohpreflight.workflow_problems(self.workflow, self.harness_executors)

    def baseline(self) -> dict:
        """The default workspace's baseline record. A further workspace that
        names a baseline command has its record under `workspaces`."""
        spaces = self.workflow.all_workspaces()
        record = self._baseline_of(spaces[0], "baseline")
        others = {space.name: self._baseline_of(space, f"baseline-{slug(space.name)}")
                  for space in spaces[1:] if space.baseline_cmd}
        if others:
            record["workspaces"] = others
        return record

    def _baseline_of(self, space, log_name: str) -> dict:
        if not space.baseline_cmd:
            return {"command": None, "skipped": "no baseline_cmd in the workflow"}
        c = ohexec.run(space.baseline_cmd, Path(space.path), shell="sh",
                       timeout=1800, log_dir=self.run_dir / "logs",
                       name=log_name)
        output = c.stdout + c.stderr
        record = {"command": space.baseline_cmd, "exit": c.returncode,
                  "tail": output[-1000:], "log": c.stdout_path}
        for name in BASELINE_FORMATS:
            counts = ohgates.PARSERS[name](output)
            if counts["total"]:
                record["format"] = name
                record["counts"] = counts
                break
        return record

    def _ensure_workspaces(self) -> None:
        """Create the repository of each owned workspace that has none yet."""
        for space in self.workflow.all_workspaces():
            try:
                said = ohwt.ensure_workspace(space)
            except RuntimeError as e:
                raise PreflightError(f"preflight failed:\n  - {e}") from None
            if said:
                self.say(f"[workspace] {space.name} {said}")

    def _workspace_facts(self) -> list[dict]:
        return [{"name": space.name, "path": win(space.path),
                 "base_branch": space.base_branch, "owned": space.owned,
                 "base_sha": ohexec.git_out("rev-parse HEAD", Path(space.path))}
                for space in self.workflow.all_workspaces()]

    # -------------------------------------------------------------- setup

    def _reserve_run_dir(self) -> None:
        """Claim one fresh run directory exactly once.

        The exclusive owner file is the actual concurrency boundary. A CLI
        existence check is useful feedback but cannot close the race between
        two launchers, and direct Engine callers do not pass through the CLI.
        """
        if self._owns_run_dir:
            return
        self.run_dir.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.run_dir.mkdir(exist_ok=False)
            created = True
        except FileExistsError:
            created = False
        owner = self.run_dir / ".ohflow-owner.json"
        handoff = self.run_dir / ".ohflow-handoff.json"

        if self.reservation_token:
            if created:
                raise PreflightError(
                    f"detached run reservation does not exist at {win(handoff)}")
            try:
                reserved = json.loads(handoff.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                raise PreflightError(
                    f"detached run reservation is missing or unreadable at "
                    f"{win(handoff)}: {e}") from e
            if not secrets.compare_digest(
                    str(reserved.get("token") or ""), self.reservation_token):
                raise PreflightError(
                    f"detached run reservation token does not match {win(handoff)}")
        else:
            if not created:
                raise PreflightError(
                    f"run directory already exists; use --resume to continue it: "
                    f"{win(self.run_dir)}")

        claimed = {
            "run_id": self.run_id,
            "pid": os.getpid(),
            "claimed": _dt.datetime.now(_dt.timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
            "detached_handoff": bool(self.reservation_token),
        }
        try:
            with owner.open("x", encoding="utf-8") as fh:
                json.dump(claimed, fh, indent=2)
        except FileExistsError as e:
            raise PreflightError(
                f"run directory already has an engine owner: {win(self.run_dir)}") \
                from e
        if self.reservation_token:
            handoff.unlink(missing_ok=True)
        self._owns_run_dir = True

    def inherit_reservation(self) -> None:
        """Take over a claim an earlier engine made on this run directory.

        The hold gate rebuilds the engine after `go`, from the workflow module
        as it reads then. The directory was claimed once, by the engine that
        held, and the owner file names this same process, so the new engine
        is told the claim is its own instead of refusing its own directory.
        """
        self._owns_run_dir = True

    def write_workflow_json(self) -> None:
        """Record the workflow this run executes. Written at the start of
        `run()`, and by a held run before it waits, so the dashboard can show
        the plan while nothing has started."""
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / "workflow.json").write_text(
            json.dumps(to_jsonable(self.workflow), indent=2, sort_keys=True),
            encoding="utf-8")

    def reserve_run_dir(self) -> None:
        """Claim the run directory before `run()`, for a caller that writes
        into it first.

        The CLI writes the exit report into the run directory, and the run
        dashboard writes `dashboard.json` there, so both need to know the
        directory is this run's before the engine starts. A fresh run claims
        it here; `run()` then finds the claim made and does not repeat it. A
        resume claims nothing, exactly as `run()` claims nothing for it.
        """
        if not self.resume:
            self._reserve_run_dir()

    def _ensure_worktrees(self, names: set[str]) -> dict[str, dict]:
        facts: dict[str, dict] = dict(self.state.meta.get("worktrees") or {})
        for w in self.workflow.worktrees:
            if w.name not in names or w.name in facts:
                continue
            spec = w
            if Path(w.path).exists():
                from dataclasses import replace
                spec = replace(w, reuse_existing=True)
            space = self.workflow.workspace(w.workspace)
            h = ohwt.create(Path(space.path), spec, created_by="engine",
                            log_dir=self.run_dir / "logs", workspace=space.name)
            facts[w.name] = h.to_dict()
            self._transition("worktree_ready", payload={
                "name": w.name, "facts": facts[w.name],
            })
            self.say(f"[worktree] {w.name} {win(h.path)} on {h.branch} "
                     f"at {h.base_sha[:8]} ({h.node_modules_mode})")
        return facts

    def _ensure_phase_worktrees(self, phase: Phase) -> None:
        names = {step.worktree for step in phase.steps if step.worktree}
        if not names:
            return
        before = set((self.state.meta.get("worktrees") or {}).keys())
        facts = self._ensure_worktrees(set(names))
        if set(facts) == before:
            return
        run_json = self.run_dir / "run.json"
        if run_json.exists():
            data = json.loads(run_json.read_text(encoding="utf-8"))
            data["worktrees"] = facts
            run_json.write_text(json.dumps(data, indent=2, default=str),
                                encoding="utf-8")
        self._write_anchor(facts, self.state.meta.get("base_sha", ""),
                           self.state.meta.get("baseline") or {})

    def _backfill_workflow_path(self) -> None:
        """Put `workflow_path` into an existing `run.json` that predates the key.

        A resume rewrites no other part of `run.json`, so this only ever adds a
        missing key. A run started before this key existed then becomes
        addressable by `ohflow position --run` after one resume.
        """
        if not self.workflow_path:
            return
        p = self.run_dir / "run.json"
        if not p.exists():
            return
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        if data.get("workflow_path"):
            return
        data["workflow_path"] = self.workflow_path
        data.setdefault("workflow_args", self.workflow_args)
        p.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def _write_anchor(self, facts: dict, base_sha: str, baseline: dict) -> None:
        L = [f"# ANCHOR - run {self.state.run_id}", "",
             f"workflow: {self.workflow.name}",
             f"repo: {win(self.workflow.repo)}",
             f"base branch: {self.workflow.base_branch}",
             f"base sha: {base_sha}", ""]
        spaces = self.workflow.all_workspaces()
        several = len(spaces) > 1
        if several:
            L += ["## Workspaces", ""]
            for space in spaces:
                L.append(f"- `{space.name}` - {win(space.path)} - base branch "
                         f"`{space.base_branch}`"
                         + (" - owned by ohflow" if space.owned else ""))
            L.append("")
        L += ["## Worktrees created", ""]
        for name, f in sorted(facts.items()):
            L.append(f"- `{name}` - {win(f['path'])} - branch `{f['branch']}` "
                     f"from `{f['base']}` at `{f['base_sha'][:8]}` - "
                     f"node_modules `{f['node_modules_mode']}`"
                     + (f" - workspace `{f['workspace']}`"
                        if several and f.get("workspace") else "")
                     + (" - existed before this run" if f.get("existed") else ""))
        L += ["", "## Baseline", "", "```json",
              json.dumps(baseline, indent=2, default=str), "```", "",
              "## Teardown", "",
              f"Run `{python_cmd()} -m ohflow.cli revert --run "
              f"{win(self.run_dir)}`. It removes every node_modules link "
              "before it removes any worktree, and it asserts the shared "
              "node_modules sentinel afterwards."]
        (self.run_dir / "ANCHOR.md").write_text("\n".join(L) + "\n", encoding="utf-8")

    def _scaffold_run_notes(self, base_sha: str) -> None:
        """Put the four run notes at the root of a fresh run directory.

        A dry run prepares artefacts and judges nothing, so it gets no notes.
        A resume never reaches this: it would only find the files already
        there. The notes are a convenience and never a gate, so a failure is
        said and the run carries on.
        """
        if self.dry_run:
            return
        created, problems = ohrunnotes.scaffold(
            self.run_dir, self.workflow, run_id=self.run_id, base_sha=base_sha,
            predictions_text=self.predictions)
        if created:
            self.say(f"[run notes] {', '.join(created)} written at the run "
                     f"root; `ohflow notes check` lists the gaps")
        for problem in problems:
            self.say(f"[run notes] not written, the run goes on: {problem}")

    def _draft_retro(self) -> None:
        """Fill the engine's half of `retro.md` from the summary just written.

        Each end of the run does this, a resume included: the draft is rewritten
        between its two markers and nothing else in the file is touched. A run
        with no `retro.md` (an older run, a dry run, a deleted file) is left as
        it is. The draft is a convenience and never a gate.
        """
        status, message = ohretro.write(self.run_dir)
        if status == ohretro.WRITTEN:
            self.say(f"[retro] {message}; add your verdicts in What I judge")
        elif status == ohretro.PROBLEM:
            self.say(f"[retro] not drafted, the run is unaffected: {message}")

    # ---------------------------------------------------------------- run

    def run(self) -> dict:
        if not self.resume:
            self._reserve_run_dir()
        self.write_workflow_json()

        if self.resume and (self.run_dir / "run-log.jsonl").exists():
            self.state = RunLog.replay(self.run_dir)
            if self.state.run_id and self.state.run_id != self.run_id:
                self.say(f"[resume] the run log records run id "
                         f"{self.state.run_id!r} while the directory is named "
                         f"{self.run_id!r}; the run log wins")
                self.run_id = self.state.run_id
            self.say(f"[resume] {self.state.run_id} - "
                     f"{len(self.state.steps)} step records replayed")
            self._restore_cooldown()
            self._settle_killed_attempts()
            facts = self.state.meta.get("worktrees") or {}
            base_sha = self.state.meta.get("base_sha", "")
            self._backfill_workflow_path()
        else:
            self._ensure_workspaces()
            problems = self.preflight()
            if problems:
                raise PreflightError("preflight failed:\n  - " + "\n  - ".join(problems))
            spaces = self._workspace_facts()
            base_sha = spaces[0]["base_sha"]
            baseline = self.baseline()
            if baseline.get("exit") not in (None, 0):
                raise PreflightError(
                    f"baseline command {baseline.get('command')!r} exited "
                    f"{baseline['exit']} at {base_sha[:8]}; see {baseline.get('log')}")
            for name, other in (baseline.get("workspaces") or {}).items():
                if other.get("exit") not in (None, 0):
                    raise PreflightError(
                        f"baseline command {other.get('command')!r} of "
                        f"workspace {name!r} exited {other['exit']}; see "
                        f"{other.get('log')}")
            facts = {}
            self._transition("run_started", payload={
                "run_id": self.run_id,
                "workflow": self.workflow.name,
                "meta": {
                    "repo": win(self.workflow.repo),
                    "base_branch": self.workflow.base_branch,
                    "base_sha": base_sha,
                    "args": dict(self.workflow.args),
                    "max_parallel": self.max_parallel,
                    # The value the run actually used, which is the CLI
                    # override when there was one. Reporting the workflow's own
                    # number would misdescribe every run started with
                    # `--auto-resume`.
                    "auto_resume": self.auto_resume,
                    "worktrees": facts,
                    "baseline": baseline,
                    "workspaces": spaces,
                },
            })
            (self.run_dir / "run.json").write_text(json.dumps({
                "run_id": self.run_id, "workflow": self.workflow.name,
                "workflow_path": self.workflow_path, "workflow_args": self.workflow_args,
                "repo": win(self.workflow.repo), "base_sha": base_sha,
                "args": dict(self.workflow.args), "max_parallel": self.max_parallel,
                "auto_resume": self.auto_resume,
                "worktrees": facts, "baseline": baseline,
                "workspaces": spaces,
                "started": self.state.started,
            }, indent=2, default=str), encoding="utf-8")
            ohwt.write_revert_plan(self.run_dir, Path(self.workflow.repo),
                                   list(self.workflow.worktrees),
                                   list(self.workflow.all_workspaces()))
            self._write_anchor(facts, base_sha, baseline)
            self._scaffold_run_notes(base_sha)

        if not self.dry_run:
            self._open_budget()

        for pi, phase in enumerate(self.workflow.phases, start=1):
            if self.only_phase and phase.name != self.only_phase \
                    and phase.slug != self.only_phase:
                self.say(f"[phase {pi}] skipped by --only-phase")
                continue
            if self._abort.is_set():
                self.say(f"[phase {pi}] not started: the run aborted earlier")
                break
            if self._paused.is_set():
                self.say(f"[phase {pi}] not started: the run is paused on a "
                         f"transient failure. Resume it with "
                         f"--resume {self.state.run_id}")
                break
            self._run_phase(pi, phase)

        if self._abort.is_set():
            status = "failed"
        elif self._paused.is_set():
            status = "paused"
        else:
            status = "finished"
        finished = {"status": status}
        if self.budget is not None:
            finished["token_budget"] = self.budget.snapshot()
        self._transition("run_finished", payload=finished)
        summary = rundir.open_run(self.run_dir, state=self.state).write_summary()
        self._draft_retro()
        return summary

    # -------------------------------------------------------------- phases

    def _run_phase(self, pi: int, phase: Phase) -> None:
        pc = phase_coord(pi, phase.slug)
        limit = self.phase_limit(phase)
        self._ensure_phase_worktrees(phase)
        (self.run_dir / "phases" / pc).mkdir(parents=True, exist_ok=True)
        self._transition("phase_started", coord_=pc, payload={
            "name": phase.name, "policy": phase.on_step_failure,
            "min_success": phase.min_success,
            "max_parallel": limit,
            "steps": [coord(pi, phase.slug, si, s.id)
                      for si, s in enumerate(phase.steps, start=1)],
        })
        self.say(f'[phase {pi}/{len(self.workflow.phases)}] "{phase.name}" '
                 f'({len(phase.steps)} steps, policy {phase.on_step_failure}, '
                 f'max_parallel {limit})')

        # Step 2 of the loop: fingerprint everything before anything runs.
        fps: dict[str, str] = {}
        live: list[tuple[int, Step]] = []
        for si, step in enumerate(phase.steps, start=1):
            c = coord(pi, phase.slug, si, step.id)
            fp = fingerprint(self.workflow, self.state, step)
            fps[c] = fp
            blocked = self._blocked_dependencies(step)
            if blocked:
                reason = "dependency did not pass: " + ", ".join(blocked)
                self._transition("attempt_finished", coord_=c,
                                 attempt=SYNTHETIC_ATTEMPT, payload={
                    "status": "skipped", "fingerprint": fp,
                    "step_id": step.id, "kind": step.kind,
                    "error": reason, "failure_class": None,
                    "wall_seconds": 0.0, "gate": None,
                    "abort_victim": False,
                })
                self.say(f"  [{c}] skipped - {reason}")
                continue
            prior = self.state.steps.get(c)
            from .handover import intact
            if (prior is not None and prior.ok and prior.fingerprint == fp
                    and (step.handover is None or intact(self.run_dir, prior))):
                # Synthetic: nothing runs for a cached step. Carrying the
                # earlier attempt's number here overwrote that execution's
                # record with `cached` and erased what it actually did.
                self._transition("attempt_finished", coord_=c,
                                 attempt=SYNTHETIC_ATTEMPT,
                                 payload={"status": "cached", "fingerprint": fp,
                                          "step_id": step.id, "kind": step.kind,
                                          "gate": prior.gate,
                                          "result_path": prior.result_path,
                                          "handover_path": prior.handover_path,
                                          "handover_sha256": prior.handover_sha256,
                                          "head_sha": prior.head_sha,
                                          "wall_seconds": 0.0})
                self.say(f"  [{c}] cached")
            else:
                live.append((si, step))

        if self.dry_run:
            for si, step in live:
                c = coord(pi, phase.slug, si, step.id)
                self._prepare_step_dir(pi, phase, si, step, fps[c], attempt=1)
                self.say(f"  [{c}] dry-run: brief and spec written, nothing launched")
            self._settle(pi, phase, dry_run=True)
            return

        # Auto-resume passes already taken for this phase, counted from the run log. A
        # counter starting at zero each invocation would report auto-resume pass 1 again
        # after a resume and read as though the budget had refreshed.
        auto_resume = int(self.state.phases.get(pc, {}).get("auto_resumes") or 0)
        first = True
        while True:
            self._run_steps(pi, phase, live, fps, limit,
                            "initial" if first else "auto_resume")
            first = False
            verdict = self._settle(pi, phase, auto_resume=auto_resume,
                                   pause_on_deferred=False)
            if verdict != "deferred" or self._abort.is_set() \
                    or self._budget_spent.is_set():
                if verdict == "deferred":
                    self._paused.set()
                break

            live = self._auto_resumable(pi, phase, fps)
            if not live:
                # Every deferred step has spent its auto-resume passes, or is excluded. The
                # run pauses and `--resume` is the next move, which is exactly
                # what happens when `auto_resume` is 0.
                self._paused.set()
                self.say(f"[phase {pi}] paused: no deferred step may be auto-resumed "
                         f"again automatically")
                break

            auto_resume += 1
            self._transition("phase_resumed", coord_=pc, payload={
                "pass": auto_resume, "auto_resume": self.auto_resume,
                "steps": [coord(pi, phase.slug, si, s.id) for si, s in live],
            })
            self.say(f"[phase {pi}] auto-resume pass {auto_resume} of "
                     f"{self.auto_resume}: {len(live)} deferred step(s)")
            # The cooldown `_back_off` already computed. An auto-resume pass that started
            # the instant the rate limit fired would meet the same rate limit.
            self._wait_out_cooldown(pc)
            if self._abort.is_set():
                break

    def _blocked_dependencies(self, step: Step) -> list[str]:
        blocked: list[str] = []
        for dep in step.depends_on:
            dpi, dphase, dsi, _ = self.workflow.step_by_id(dep)
            dc = coord(dpi, dphase.slug, dsi, dep)
            rec = self.state.steps.get(dc)
            phase_results = (self.state.phases.get(
                phase_coord(dpi, dphase.slug), {}).get("steps") or {})
            dependency_status = (rec.status if rec is not None
                                 else phase_results.get(dc))
            excluded = bool(
                rec is not None and rec.fingerprint
                and f"{dc}@{rec.fingerprint}" in self.state.exclusions
            )
            if excluded:
                blocked.append(f"{dep} (excluded)")
            elif self.dry_run and dependency_status == "dry-run":
                # Dry runs prepare artifacts without emitting a synthetic
                # attempt_finished record. The settled phase still records each
                # prepared step as dry-run, which is enough to let later
                # dependent briefs materialize in the same workflow preview.
                continue
            elif dependency_status is None:
                blocked.append(f"{dep} (missing)")
            elif rec is None or not rec.ok:
                blocked.append(f"{dep} ({dependency_status})")
            elif dep in step.consumes and not self.dry_run:
                from .handover import recorded
                try:
                    recorded(self.run_dir, rec)
                except ValueError as e:
                    blocked.append(f"{dep} ({e})")
        return blocked

    def _run_steps(self, pi: int, phase: Phase, live, fps, limit: int,
                   start_kind: str) -> None:
        """Run one pass over `live`. Merges are serial and first, in workflow
        order: §7 of the plan, one branch at a time."""
        merges = [(si, s) for si, s in live if s.kind == "merge"]
        others = [(si, s) for si, s in live if s.kind != "merge"]
        for si, step in merges:
            c = coord(pi, phase.slug, si, step.id)
            if self._abort.is_set():
                self._defer_unstarted(
                    c, step, fps.get(c),
                    "the run aborted before this step started")
                continue
            self._execute_step(pi, phase, si, step, fps, start_kind)

        others = self._start_order(pi, phase, others)
        sem = _StartQueue(limit, [coord(pi, phase.slug, si, s.id)
                                  for si, s in others])
        threads = []
        for si, step in others:
            t = threading.Thread(target=self._guarded_step,
                                 args=(pi, phase, si, step, fps, sem,
                                       start_kind),
                                 name=coord(pi, phase.slug, si, step.id))
            t.start()
            threads.append(t)
        for t in threads:
            t.join()

    def _start_order(self, pi: int, phase: Phase, steps: list) -> list:
        """Longest step first: the order the steps of one pass take their slots in.

        The length is the step's p50 wall time in the run's `estimate.json`. A
        step the estimate holds no p50 for keeps its place, and the steps with
        one share out the places left, longest first. Two equal steps keep
        their workflow order. A run without an estimate keeps the workflow order.
        """
        expected = ohestimate.step_expectations(
            ohestimate.read_estimate(self.run_dir))
        known = [(si, s) for si, s in steps
                 if coord(pi, phase.slug, si, s.id) in expected]
        known.sort(key=lambda e: -expected[coord(pi, phase.slug, e[0], e[1].id)])
        longest = iter(known)
        return [next(longest) if coord(pi, phase.slug, si, s.id) in expected
                else (si, s) for si, s in steps]

    def _auto_resumable(self, pi: int, phase: Phase, fps) -> list:
        """The deferred steps of this phase that may be auto-resumed again.

        Exactly the coordinates recorded `deferred`, and no others. Passed
        steps are already `ok` and would be cached, so re-fingerprinting the
        whole phase mid-flight would reach the same answer through a second
        cache decision. One decision per phase is enough.
        """
        out = []
        for si, step in enumerate(phase.steps, start=1):
            c = coord(pi, phase.slug, si, step.id)
            rec = self.state.steps.get(c)
            if rec is None or rec.status != "deferred":
                continue
            if rec.killed is not None:
                self.say(f"  [{c}] not auto-resumed - ohflow kill ended attempt "
                         f"{rec.attempt}; `run --resume` starts it again")
                continue
            allowed, why = ohattempts.may_start(
                self.state, c, fps.get(c), start_kind="auto_resume",
                retry_max=step.retry.max, auto_resume=self.auto_resume)
            if allowed:
                out.append((si, step))
            else:
                self.say(f"  [{c}] not auto-resumed - {why}")
        return out

    def _defer_unstarted(self, c: str, step: Step, fp: str | None,
                         reason: str) -> None:
        """Record a step that never got its turn. `deferred`, never `failed`.

        The step produced no verdict, so nothing about it was judged. It keeps
        its assignment and `--resume` re-runs it, because only `passed` and
        `cached` are `ok` and only `ok` steps are cached.
        """
        self._transition("attempt_finished", coord_=c,
                         attempt=SYNTHETIC_ATTEMPT, payload={
            "status": "deferred", "fingerprint": fp,
            "step_id": step.id, "kind": step.kind, "error": reason,
            "failure_class": None, "wall_seconds": 0.0, "gate": None,
            "abort_victim": True,
        })
        self.say(f"  [{c}] deferred - {reason}")

    def _guarded_step(self, pi, phase, si, step, fps, sem,
                      start_kind: str = "initial"):
        c = coord(pi, phase.slug, si, step.id)
        sem.acquire(c)
        try:
            if self._abort.is_set():
                # The abort already fired. Launching this agent only to kill it
                # a second later costs a provider call and records a verdict
                # nobody reached.
                self._defer_unstarted(
                    c, step, fps.get(c),
                    "the run aborted before this step started")
                return
            self._wait_out_cooldown(c)
            # Checked again after the wait. A cooldown can run for minutes, and
            # the abort that fired during it must not be answered by launching
            # an agent.
            if self._abort.is_set():
                self._defer_unstarted(
                    c, step, fps.get(c),
                    "the run aborted while this step held the provider cooldown")
                return
            self._execute_step(pi, phase, si, step, fps, start_kind)
        except Exception as e:
            # `_execute_step` guards its own body, but not the step directory it
            # prepares first. A fault there used to kill the thread with the
            # step still `pending`, and the phase then settled on a state
            # nothing had written. Record the failure, then let the policy act.
            err = f"{type(e).__name__}: {e}"
            # Whatever attempt the run log is waiting on, not attempt 1.
            # Hardcoding 1 here overwrote the first execution's record and left
            # a later one open, because `replay` matches on (coordinate,
            # attempt).
            open_attempt = self._open_attempt(c)  # SYNTHETIC_ATTEMPT when none
            self._transition("attempt_finished", coord_=c, attempt=open_attempt,
                             payload={
                "status": "failed", "fingerprint": fps.get(c),
                "step_id": step.id, "kind": step.kind, "error": err,
                "failure_class": ohfail.STRUCTURAL, "wall_seconds": 0.0,
                "gate": None, "abort_victim": False,
            })
            self.say(f"  [{c}] failed before it ran - {err}")
            if phase.on_step_failure == "abort":
                self._abort.set()
        finally:
            sem.release()

    def _open_attempt(self, c: str) -> int:
        """The attempt an `attempt_finished` should close at this coordinate.

        The highest attempt that started and has no ending, or the next free
        number when every execution is already closed. A fault before any
        execution started therefore opens and closes a record of its own rather
        than overwriting a finished one.
        """
        open_ones = [e["attempt"] for e in ohattempts.executions(self.state, c)
                     if e.get("status") == "running"
                     and isinstance(e.get("attempt"), int)]
        if open_ones:
            return max(open_ones)
        return SYNTHETIC_ATTEMPT

    def _back_off(self, c: str, error: str | None = None) -> float:
        """Push the cooldown out after a transient failure.

        The wait is held under one of the phase's slots, so at most that phase's
        limit of threads sit in it and the rest queue behind them. Nine steps
        then do not stampede back into the same rate limit one second after it
        fired.
        """
        reset = _provider_reset_at(error)
        if reset is not None and reset > time.time():
            with self._backoff_lock:
                self._cooldown_until = max(self._cooldown_until, reset)
            wait = round(reset - time.time())
            self.say(f"  [{c}] provider usage window - holding until its "
                     f"reset, {wait}s")
            return float(wait)
        base = max(0, int(self.workflow.transient_backoff_s))
        if base == 0:
            return 0.0
        with self._backoff_lock:
            self._transient_hits += 1
            wait = min(base * (2 ** (self._transient_hits - 1)), base * 10)
            self._cooldown_until = max(self._cooldown_until, time.time() + wait)
        self.say(f"  [{c}] transient failure - backing off {wait}s; the steps "
                 f"that have not run keep their assignments")
        return float(wait)

    def _cooldown_record(self) -> dict:
        """The cooldown as the run log should carry it.

        An absolute wake time, not a number of seconds, because the run may be
        resumed in a new process an hour later and a duration would start again
        from then. The hit count rides along so the doubling continues where it
        left off instead of restarting at the base.
        """
        with self._backoff_lock:
            until, hits = self._cooldown_until, self._transient_hits
        if not until:
            return {}
        stamp = _dt.datetime.fromtimestamp(until, _dt.timezone.utc)
        return {"cooldown_until": stamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "transient_hits": hits}

    def _restore_cooldown(self) -> None:
        """Take the cooldown back out of the run log after a resume."""
        stamp = self.state.cooldown_until
        if not stamp:
            return
        try:
            when = _dt.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=_dt.timezone.utc).timestamp()
        except ValueError:
            return
        with self._backoff_lock:
            self._cooldown_until = max(self._cooldown_until, when)
            self._transient_hits = max(self._transient_hits,
                                       self.state.transient_hits)
        remaining = round(when - time.time())
        if remaining > 0:
            self.say(f"[resume] the provider cooldown this run recorded has "
                     f"{remaining}s left, and it is honoured before any step "
                     f"starts")

    def _wait_out_cooldown(self, c: str) -> None:
        announced = False
        while not self._abort.is_set():
            with self._backoff_lock:
                remaining = self._cooldown_until - time.time()
            if remaining <= 0:
                return
            if not announced:
                self.say(f"  [{c}] holding {round(remaining)}s for the provider "
                         f"cooldown before start")
                announced = True
            time.sleep(min(remaining, 5.0))

    def _settle(self, pi: int, phase: Phase, dry_run: bool = False, *,
                auto_resume: int = 0, pause_on_deferred: bool = True) -> str:
        pc = phase_coord(pi, phase.slug)
        results = {}
        for si, step in enumerate(phase.steps, start=1):
            c = coord(pi, phase.slug, si, step.id)
            rec = self.state.steps.get(c)
            results[c] = rec.status if rec else ("pending" if not dry_run else "dry-run")
        good = sum(1 for v in results.values() if v in ("passed", "cached"))
        total = len(results)
        ms = phase.min_success
        if dry_run:
            met = True
        elif ms == "all":
            met = good == total
        elif ms == "any":
            met = good >= 1
        else:
            met = good >= int(ms)
        deferred = sorted(c for c, v in results.items() if v == "deferred")
        hard = [c for c, v in results.items() if v in ("failed", "timeout")]
        if met:
            status = "passed"
        elif deferred and not hard:
            status = "deferred"
        else:
            status = "failed"
        self._transition("phase_settled", coord_=pc, payload={
            "status": status, "steps": results, "good": good, "total": total,
            "min_success": ms, "deferred": deferred, "auto_resumes": auto_resume,
        })
        if dry_run:
            self.say(f"[phase {pi}] dry run: {total} steps prepared, none started")
        else:
            bad = ", ".join(f"{c} {v}" for c, v in results.items()
                            if v not in ("passed", "cached"))
            self.say(f"[phase {pi}] settled {status}: {good} of {total} steps "
                     f"passed" + (f"; {bad}" if bad else ""))
        if met or dry_run:
            return status
        if deferred and not hard and not self._abort.is_set():
            # Nothing in this phase was judged and rejected. Keep every deferred
            # step re-runnable. Whether the run pauses here or auto-resumes them again
            # is the caller's decision, because only the caller knows how many
            # auto-resume passes this phase has already had.
            if pause_on_deferred:
                self._paused.set()
                self.say(f"[phase {pi}] paused: {len(deferred)} step(s) deferred "
                         f"on a transient failure - {deferred}. None is marked "
                         f"failed.")
            return status
        if phase.on_step_failure == "abort":
            self._abort.set()
        return status

    # --------------------------------------------------------------- steps

    def attempt_dir(self, c: str, attempt: int) -> Path:
        """Where one execution writes. Every execution gets its own.

        An agent's `out_dir` is this directory, so every absolute path it
        records - the transcript directory, the completion logs, the command logs -
        points inside it and stays valid for the life of the run. Nothing is
        moved afterwards and no path is ever rewritten.

        A fresh directory per execution is also what stops the next attempt from
        collecting the last one's `result.json` after a crash.
        """
        return rundir.attempt_dir(self.run_dir, c, attempt)

    #: Copied up to the step directory when an execution finishes, so every
    #: reader that looks where it always looked finds the latest attempt. The
    #: large directories - `logs`, `conversations`, `completions` - stay where
    #: they were written, because their absolute paths already resolve.
    PROJECTED = ("handover.md", "position.md", "brief.md", "spec.json", "schema.json",
                 "final.md", "result.json", "gate.json")

    def _clear_projection(self, c: str) -> None:
        """Remove the projected copies, and only those eight names.

        Called when an attempt starts. Between that moment and the moment it
        finishes the step directory holds no projection at all, which is the
        truth: the latest attempt has not produced one yet. Leaving the
        previous attempt's files there would describe attempt 1 as the latest
        for as long as attempt 2 ran, and for ever if attempt 2 crashed.

        Nothing under `attempts/` is touched. That is where the evidence lives.
        """
        d = self.step_dir(c)
        for name in self.PROJECTED:
            f = d / name
            if f.exists():
                f.unlink()

    def _project_attempt(self, c: str, attempt: int) -> None:
        """Copy this attempt's small files up to the step directory.

        A name this attempt did not produce is removed rather than left behind,
        so the projection never mixes two attempts.
        """
        import shutil
        src = self.attempt_dir(c, attempt)
        dst = self.step_dir(c)
        for name in self.PROJECTED:
            f = src / name
            target = dst / name
            if f.exists():
                shutil.copy2(f, target)
            elif target.exists():
                target.unlink()

    def _prepare_step_dir(self, pi, phase, si, step, fp, attempt) -> Path:
        c = coord(pi, phase.slug, si, step.id)
        d = self.attempt_dir(c, attempt)
        if any(d.iterdir()) if d.exists() else False:
            # Attempt numbers come from the run log and never repeat, so a
            # directory with something already in it means two executions were
            # handed one number. Stopping here is better than writing a second
            # agent's output over the first one's evidence.
            raise RuntimeError(
                f"{c}: attempt directory {win(d)} is not empty. An attempt "
                f"number was reused, and the evidence of the earlier execution "
                f"would be overwritten.")
        (d / "logs").mkdir(parents=True, exist_ok=True)
        prev = self.state.steps.get(c)
        prev_failures = None
        if attempt > 1 and prev is not None and prev.gate:
            rep = prev.gate
            prev_failures = [
                f"{ch['name']}: observed {ch.get('observed')!r}, "
                f"expected {ch.get('expected')!r}"
                for ch in rep.get("checks", []) if not ch.get("passed")
            ]
        if attempt > 1 and prev is not None and prev.killed is not None:
            prev_failures = [*(prev_failures or []),
                             ohkill.error_text(prev.killed.get("reason"))]
        # The agent is judged against `step.schema`, so the block that tells it
        # where it stands also tells it what it owes. The file is named too, for
        # an agent that wants the raw JSON Schema.
        from .handover import received
        handovers = received(self.workflow, self.state, step, self.run_dir) if not self.dry_run else {}
        previous_handover = None
        if attempt > 1 and step.handover:
            previous_path = self.attempt_dir(c, attempt - 1) / "handover.md"
            try:
                with previous_path.open(encoding="utf-8", newline="") as stream:
                    previous_handover = stream.read(step.handover.max_chars)
            except (OSError, UnicodeError):
                pass
        position = render_position(self.workflow, self.state, step, attempt=attempt,
                                   handovers=handovers,
                                   handover_path=str(d.resolve() / "handover.md"),
                                   previous_handover=previous_handover,
                                   previous_failures=prev_failures,
                                   schema_path=win(d / "schema.json")
                                   if step.schema else None)
        (d / "position.md").write_text(position, encoding="utf-8")
        if step.kind == "agent" and step.agent is not None:
            brief = position + "\n---\n\n" + step.agent.brief
            (d / "brief.md").write_text(brief, encoding="utf-8")
            if step.schema:
                (d / "schema.json").write_text(json.dumps(dict(step.schema), indent=2),
                                               encoding="utf-8")
            # A step with no worktree works in the repository itself. Every
            # other site that reads `step.worktree` already says so -
            # `_execute_step`, `coords._worktree_facts`, `fingerprint`,
            # `report.render_board_md` - and this one used to raise KeyError
            # instead, inside the step thread, before the step had started.
            workspace = (Path(self.workflow.worktree(step.worktree).path)
                         if step.worktree else Path(self.workflow.repo))
            fork_session = None
            if attempt > 1 and step.retry.carry_context:
                prior_dir = self.attempt_dir(c, attempt - 1)
                try:
                    previous = json.loads(
                        (prior_dir / "result.json").read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    previous = None
                if isinstance(previous, dict):
                    fork_session = harness_executor_module(step.agent.harness_executor).resume_target(
                        previous, prior_dir)
            spec = ohexecutor.spec_json(
                step.agent, coord=c, workspace=workspace,
                out_dir=d, brief_path="brief.md",
                schema=dict(step.schema) if step.schema else None,
                execution_timeout_s=step.execution_timeout_s, attempt=attempt,
                write_scope=step.write_scope,
                stall_timeout_s=getattr(step, "stall_timeout_s", None),
                fork_session=fork_session)
            (d / "spec.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
        return d

    def _reattempt_dir(self, c: str, step: Step, fp: str | None, attempt: int) -> Path:
        """The directory a reattach continues in: the attempt's own.

        Nothing is re-rendered and no new directory is prepared, because the
        host replays its own session and the agent answers the same brief. The
        one change is `reattach: true` in the spec, which tells the adapter to
        wait for the box and the host that a session file is already there.
        """
        d = self.attempt_dir(c, attempt)
        spec_path = d / "spec.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        if spec.get("attempt") != attempt:
            raise RuntimeError(
                f"{c}: {win(spec_path)} names attempt {spec.get('attempt')!r}, "
                f"expected {attempt}; a reattach continues its own attempt")
        spec["reattach"] = True
        spec_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
        return d

    def _execute_step(self, pi, phase, si, step: Step, fps,
                      start_kind: str = "initial") -> None:
        """Run the step until it succeeds, runs out of budget, or is refused.

        One execution per pass. The phase policy is applied once, on the last
        pass, because an intermediate failed attempt is not the step's verdict.
        A `reattach` pass is not an attempt at all: the same attempt number
        continues in the same directory, so it never reaches the gate or the
        policy here.
        """
        c = coord(pi, phase.slug, si, step.id)
        fp = fps[c]
        kind = start_kind
        last = None
        # The attempt number a reattach continues, when a supervisor death
        # left one open in the run log. A resume reaches this; a run in this
        # process reaches the host_lost branch in the loop below instead.
        reuse = self._reattach_pending(c, fp, step)
        self._settle_killed_attempts(c, keep=reuse)
        if reuse is not None:
            reason = "the supervisor stopped while this attempt ran"
            self._close_reattach(c, step, fp, reuse, reason,
                                 self._lost_wall_seconds(c, reuse))
            kind = "reattach"
        while True:
            allowed, why = ohattempts.may_start(
                self.state, c, fp, start_kind=kind,
                retry_max=step.retry.max, auto_resume=self.auto_resume)
            if not allowed:
                if last is None:
                    self._refuse_start(c, step, fp, why, phase)
                else:
                    self._record_retry_decision(c, last, why)
                break

            last = self._attempt_step(pi, phase, si, step, fp, c, kind,
                                      attempt=reuse)
            if last.get("budget_refused"):
                last = None
                break
            if last.get("completion_refused"):
                break
            if last.get("reattach"):
                # The host on the box ended without a verdict: the attempt
                # continues, it does not close, and no gate runs on it.
                self._close_reattach(c, step, fp, last["attempt"],
                                     last["reason"],
                                     float(last.get("wall_seconds") or 0.0))
                kind, reuse = "reattach", last["attempt"]
                continue

            # Asked after the verdict is recorded in the run log, so the attempt history already counts
            # this execution. Asking before it would let a second failure
            # authorise a third attempt.
            retry, why = ohretry.should_retry(
                step, status=last["raw_status"], error=last["error"],
                report=last["report"], abort_victim=last["abort_victim"],
                aborted=self._abort.is_set(), state=self.state, coord=c,
                fingerprint=fp, auto_resume=self.auto_resume,
                killed=bool(last.get("killed")))
            self._record_retry_decision(c, last, why)
            if not retry:
                break
            self.say(f"  [{c}] {why}")
            # A retry answers a verdict with a new execution, so it mints its
            # own attempt number: the one a reattach pass carried belongs to
            # that attempt's directory, which is not empty.
            kind, reuse = "retry", None

        if (last is not None and not last.get("completion_refused")
                and not last.get("reattach")):
            # A reattach marker carries no verdict: its closure already wrote
            # `deferred`, and deferred never reaches a phase policy.
            self._apply_phase_policy(c, phase, last)
        self._maybe_exclude(c, fp)

    def _refuse_start(self, c: str, step: Step, fp: str | None, why: str,
                      phase: Phase) -> None:
        """Record work the attempt history will not start again.

        The step never ran in this invocation, so nothing new was judged. It is
        recorded `failed` and not `deferred`, because a deferred step asks the
        run to come back to it and this one has already been come back to twice.
        """
        status = "quarantined" if phase.on_step_failure == "quarantine" else "failed"
        self._transition("attempt_finished", coord_=c,
                         attempt=SYNTHETIC_ATTEMPT, payload={
            "status": status, "fingerprint": fp, "step_id": step.id,
            "kind": step.kind, "error": why, "failure_class": ohfail.STRUCTURAL,
            "wall_seconds": 0.0, "gate": None, "abort_victim": False,
            "retry_decision": why, "final_attempt": True,
        })
        self.say(f"  [{c}] not started - {why}")

    def _record_retry_decision(self, c: str, outcome: dict | None,
                               why: str) -> None:
        """Write the decision where it can be read back.

        `board.md` and `summary.json` are both rebuilt from the run log, so a
        decision held only in memory is gone by the next transition.

        The decision is known only after the verdict, so it cannot ride on the
        `attempt_finished` that carried the verdict. Its own event updates the
        attempt without re-emitting the terminal transition.
        """
        if outcome is None:
            return
        self._transition("retry_decided", coord_=c,
                         attempt=outcome["attempt"], payload={
            "retry_decision": why, "final_attempt": True,
        })

    def _reattach_pending(self, c: str, fp: str | None, step: Step) -> int | None:
        """The attempt number a dead supervisor left open, when it may reattach.

        Only when the step's harness executor carries `CAP_REATTACH`, the newest
        started execution at this coordinate is still `running` under this
        fingerprint, and the harness executor's `reattach_target` finds the
        attempt's own directory on the box. Anything else is an ordinary
        interrupted step and the usual rules own it.
        """
        if step.kind != "agent" or step.agent is None:
            return None
        if not harness_executor_info(step.agent.harness_executor).has(CAP_REATTACH):
            return None
        started = ohattempts.executions(self.state, c, fp)
        if not started or started[-1].get("status") != "running":
            return None
        attempt = started[-1].get("attempt")
        if not isinstance(attempt, int):
            return None
        module = harness_executor_module(step.agent.harness_executor)
        try:
            target = module.reattach_target(self.attempt_dir(c, attempt))
        except Exception:
            return None
        return attempt if target is not None else None

    def _settle_killed_attempts(self, only: str | None = None,
                                keep: int | None = None) -> None:
        """Close the executions a dead supervisor left `running` in the run log.

        A resume calls this before any step starts, for every coordinate whose
        step cannot reattach. `_execute_step` calls it for its own coordinate
        once the reattach rule has spoken, with `keep` naming the attempt a
        reattach continues, which `_close_reattach` closes instead.

        The verdict is `deferred` with the abort-victim flag, exactly as a
        killed-in-flight victim closes: the execution reached no verdict, so
        no bound counts it toward the exclusion, and its start still spends
        against the total budget. `interrupted` marks it apart from a victim of
        the run's abort, and `wall_seconds` is what `_lost_wall_seconds` reads
        from the attempt's own logs.
        """
        waits_for_reattach = set()
        if only is None:
            for pi, phase in enumerate(self.workflow.phases, start=1):
                for si, step in enumerate(phase.steps, start=1):
                    if (step.kind == "agent" and step.agent is not None
                            and harness_executor_info(
                                step.agent.harness_executor).has(CAP_REATTACH)):
                        waits_for_reattach.add(
                            coord(pi, phase.slug, si, step.id))
        reason = "the supervisor stopped before this attempt finished"
        for ex in list(self.state.executions):
            c, attempt = ex.get("coord"), ex.get("attempt")
            if not ex.get("started") or ex.get("status") != "running" \
                    or not isinstance(attempt, int):
                continue
            if c in waits_for_reattach or attempt == keep \
                    or (only is not None and c != only):
                continue
            rec = self.state.steps.get(c)
            self._transition("attempt_finished", coord_=c, attempt=attempt,
                             payload={
                "status": "deferred", "fingerprint": ex.get("fingerprint"),
                "step_id": rec.step_id if rec else "",
                "kind": rec.kind if rec else "", "error": reason,
                "failure_class": None,
                "wall_seconds": self._lost_wall_seconds(c, attempt),
                "gate": None, "abort_victim": True, "interrupted": True,
            })
            self.say(f"  [{c}] attempt {attempt} closed - {reason}")

    def _lost_wall_seconds(self, c: str, attempt: int) -> float:
        """How long an execution a dead supervisor left open was seen working.

        From that execution's `attempt_started` time to the newest modification
        time of any file in the attempt's `logs/` folder - the last moment the
        attempt was seen working, which is all a supervisor death leaves behind.
        No such file means nothing was ever seen, so 0.0.
        """
        started_at = None
        for ex in reversed(self.state.executions):
            if (ex.get("coord") == c and ex.get("attempt") == attempt
                    and ex.get("started")):
                started_at = ex.get("started_at")
                break
        if not started_at:
            return 0.0
        try:
            began = _dt.datetime.strptime(str(started_at),
                                          "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=_dt.timezone.utc).timestamp()
        except ValueError:
            return 0.0
        try:
            logs = self.attempt_dir(c, attempt) / "logs"
            newest = max((f.stat().st_mtime for f in logs.rglob("*")
                          if f.is_file()), default=None)
        except OSError:
            return 0.0
        if newest is None:
            return 0.0
        return round(max(0.0, newest - began), 1)

    def _close_reattach(self, c: str, step: Step, fp: str | None, attempt: int,
                        reason: str, wall_seconds: float = 0.0) -> None:
        """Close an execution so its attempt may continue where it stopped.

        The verdict is `deferred` with the abort-victim flag, exactly as a
        killed-in-flight victim closes: it reached no verdict, so no bound
        counts it toward the exclusion, and its start still spends against the
        total budget. `reattached` marks the pair on the record, and
        `wall_seconds` carries what the closed execution spent - measured by
        `_attempt_step` for a host loss, read from the attempt's own logs for a
        supervisor death - because an execution may have run for hours before
        its closure was written.
        """
        self._transition("attempt_finished", coord_=c, attempt=attempt, payload={
            "status": "deferred", "fingerprint": fp, "step_id": step.id,
            "kind": step.kind, "error": f"reattach: {reason}",
            "failure_class": None, "wall_seconds": round(float(wall_seconds), 1),
            "gate": None,
            "abort_victim": True, "reattached": True,
        })
        self._transition("retry_decided", coord_=c, attempt=attempt, payload={
            "retry_decision": f"reattach: {reason}", "final_attempt": True,
        })
        self.say(f"  [{c}] attempt {attempt} closed for a reattach - {reason}")

    def _maybe_exclude(self, c: str, fp: str | None) -> None:
        """Write the exclusion once, when the counters have earned it."""
        if not ohattempts.excluded(self.state, c, fp):
            return
        if f"{c}@{fp}" in self.state.exclusions:
            return
        reason = ohattempts.exclusion_reason(self.state, c, fp) or "excluded"
        self._transition("work_excluded", coord_=c, payload={
            "coord": c, "fingerprint": fp, "reason": reason,
            "failures": ohattempts.failed_executions(self.state, c, fp),
            "judged_failures": ohattempts.judged_failures(self.state, c, fp),
            "transient_deferrals": ohattempts.transient_deferrals(self.state, c, fp),
        })
        self.say(f"  [{c}] {reason}")

    def _apply_phase_policy(self, c: str, phase: Phase, outcome: dict) -> None:
        """What the step's final verdict means for the rest of the phase.

        This runs once per step, never once per attempt. An intermediate failed
        attempt that set the abort would have stopped a run that its own retry
        was about to rescue.
        """
        status = outcome["status"]
        if status == "deferred":
            # The cooldown was already pushed out and recorded in the run log with the
            # verdict. An abort victim never gets one: nothing about it says
            # the provider is busy, and the run is stopping anyway.
            return
        if status in ("failed", "timeout", "quarantined") \
                and phase.on_step_failure == "abort":
            self._abort.set()
            with self._handles_lock:
                victims = list(self._handles.items())
                self._killed_by_abort.update(vc for vc, _ in victims)
            for _vc, h in victims:
                try:
                    self.harness_executors(h.harness_executor).kill(h)
                except Exception:
                    pass

    def _attempt_faulted(self, c: str, step: Step, fp: str | None, attempt: int,
                         t0: float, err: str) -> dict:
        """Close the attempt this execution reserved, after a fault outside the
        step's own body.

        Preparing the directory and projecting the result both sit outside the
        guarded body, and a fault in either used to be recorded by
        `_guarded_step` as attempt 1. That overwrote the first execution's
        record and left this one open for ever.
        """
        report = ohgates.GateReport(coord=c, passed=False, checks=[])
        payload = {
            "status": "failed", "fingerprint": fp, "step_id": step.id,
            "kind": step.kind, "result_path": None,
            "attempt_dir": f"attempts/{attempt:02d}",
            "gate": report.to_dict(), "wall_seconds": round(time.time() - t0, 1),
            "head_sha": "", "error": err, "failure_class": ohfail.STRUCTURAL,
            "abort_victim": False, "transient_signature": None,
        }
        self._transition("attempt_finished", coord_=c, attempt=attempt,
                         payload=payload)
        self.say(f"  [{c}] failed in preparation - {err}")
        return {"status": "failed", "raw_status": "failed", "error": err,
                "report": report, "abort_victim": False, "attempt": attempt,
                "failure_class": ohfail.STRUCTURAL, "payload": payload}

    def _attempt_step(self, pi, phase, si, step: Step, fp: str | None, c: str,
                      start_kind: str, attempt: int | None = None) -> dict:
        if self.budget is None or step.kind != "agent":
            return self._attempt_admitted(pi, phase, si, step, fp, c,
                                          start_kind, attempt)
        if not self._admit(c, step, fp):
            return {"budget_refused": True}
        try:
            return self._attempt_admitted(pi, phase, si, step, fp, c,
                                          start_kind, attempt)
        finally:
            self.budget.release(c)

    def _attempt_admitted(self, pi, phase, si, step: Step, fp: str | None,
                          c: str, start_kind: str,
                          attempt: int | None = None) -> dict:
        # `attempt` is the number a reattach reuses; a fresh execution mints
        # its own.
        if attempt is None:
            attempt = ohattempts.next_attempt(self.state, c)
        previous_fp = None
        prior = self.state.steps.get(c)
        if prior is not None and prior.fingerprint and prior.fingerprint != fp:
            previous_fp = prior.fingerprint
        wt_path = Path(self.workflow.worktree(step.worktree).path) if step.worktree \
            else Path(self.workflow.repo)
        wt_facts = (self.state.meta.get("worktrees") or {}).get(step.worktree or "", {})
        base_sha = wt_facts.get("base_sha") or ""

        ohkill.discard(self.step_dir(c))
        # The attempt number is reserved in the run log before a single file is
        # written for it. Preparing the directory first left a kill during
        # preparation with a non-empty `attempts/NN` and no `attempt_started`, so
        # the next resume chose NN again and `_prepare_step_dir` refused it for
        # ever.
        self._transition("attempt_started", coord_=c, attempt=attempt, payload={
            "step_id": step.id, "kind": step.kind, "fingerprint": fp,
            "branch": wt_facts.get("branch"), "note": step.note,
            "start_kind": start_kind, "previous_fingerprint": previous_fp,
        })
        self.say(f"  [{c}] start ({step.kind}, attempt {attempt}, {start_kind})")
        t0 = time.time()

        try:
            if start_kind == "reattach":
                d = self._reattempt_dir(c, step, fp, attempt)
            else:
                self._clear_projection(c)
                d = self._prepare_step_dir(pi, phase, si, step, fp, attempt)
        except Exception as e:
            return self._attempt_faulted(c, step, fp, attempt, t0,
                                         f"{type(e).__name__}: {e}")

        start_sha = ""
        if step.worktree:
            try:
                start_sha = ohexec.git_out("rev-parse HEAD", wt_path)
            except RuntimeError:
                pass    # a check with since=step_start then fails closed
        status = "failed"
        result: dict | None = None
        error: str | None = None
        final_text = ""
        structured = None
        # A step the abort killed, or found already killed, reached no verdict.
        # It is never gated and never marked failed.
        abort_victim = False
        status_hint = None

        try:
            if step.kind == "agent":
                result, status_hint, error = self._run_agent(step, c, d)
                if status_hint == "closed":
                    rec = self.state.steps.get(c)
                    self.say(f"  [{c}] completion refused - {error}")
                    return {
                        "status": rec.status if rec else "failed",
                        "raw_status": rec.status if rec else "failed",
                        "error": error, "report": None,
                        "abort_victim": bool(rec and rec.abort_victim),
                        "attempt": attempt, "failure_class": None,
                        "payload": {}, "completion_refused": True,
                    }
                if (status_hint in ("finished", "error")
                        and step.agent is not None
                        and harness_executor_info(
                            step.agent.harness_executor).has(CAP_REATTACH)
                        and str((result or {}).get("error") or "")
                        .startswith("host_lost")):
                    # The box lost this machine, or its host died mid-run. The
                    # conversation lives on in the host's session file, so the
                    # attempt continues instead of being judged.
                    return {"reattach": True, "attempt": attempt,
                            "reason": str(result.get("error")),
                            "wall_seconds": round(time.time() - t0, 1)}
                final_text = (d / "final.md").read_text(encoding="utf-8") \
                    if (d / "final.md").exists() else ""
                structured = (result or {}).get("structured")
                if status_hint == "timeout":
                    status = "timeout"
                elif status_hint in ("aborted", "killed"):
                    abort_victim = True
                elif status_hint == "invalid":
                    status = "failed"
            elif step.kind == "command" and ohgates.with_base(step.command,
                                                              base_sha) is None:
                error = (f"the command names {ohgates.BASE}, the step's base "
                         "commit, and this step has no worktree")
            elif step.kind == "command":
                command = ohgates.with_base(step.command, base_sha)
                # Command workflows that consume prior engine artifacts need a
                # stable route to this run and their own attempt without
                # duplicating the CLI's --out path as a workflow argument.
                cm = ohexec.run(command, wt_path, shell=step.shell,
                                timeout=step.execution_timeout_s,
                                log_dir=d / "logs", name=f"step-{step.id}",
                                env={"OHFLOW_RUN_DIR": str(self.run_dir),
                                     "OHFLOW_ATTEMPT_DIR": str(d)},
                                stop=lambda: ohkill.pending(
                                    self.step_dir(c), attempt) is not None)
                # A command step's stdout is its final message, so the same
                # message-reading checks apply to it as to an agent.
                final_text = cm.stdout
                structured = _fenced_json(final_text) if step.schema else None
                result = {"coord": c, "exit": cm.returncode,
                          "duration_s": cm.duration_s, "cmd": command,
                          "stdout_path": cm.stdout_path, "tail": cm.tail[-2000:],
                          "final_text_path": "final.md", "structured": structured}
                attempt_record.write(d, result, final_text)
                if cm.stopped:
                    status_hint, abort_victim = "killed", True
                    error = ohkill.take(self.step_dir(c), ohkill.pending(
                        self.step_dir(c), attempt) or {"attempt": attempt}, d)
                elif cm.timed_out:
                    status = "timeout"
                elif cm.returncode != 0:
                    error = f"command exited {cm.returncode}"
            elif step.kind == "merge":
                result, error = self._run_merge(step, c, d, wt_path)
            elif step.kind == "gate":
                result = {"coord": c, "kind": "gate"}
            else:
                error = f"unknown step kind {step.kind!r}"

            if abort_victim:
                # Gating a killed agent would write a verdict on work that was
                # never finished. There is no report and there is no judgement.
                report = ohgates.GateReport(coord=c, passed=False, checks=[])
            else:
                space = self.workflow.workspace_of(step.worktree)
                ctx = ohgates.GateContext(
                    coord=c, repo=Path(space.path), worktree=wt_path,
                    base_sha=base_sha,
                    base_ref=wt_facts.get("base") or space.base_branch,
                    attempt_dir=d, log_dir=d / "logs", write_scope=step.write_scope,
                    final_text=final_text, structured=structured,
                    schema=dict(step.schema) if step.schema else None,
                    agent_error=error, timeout_s=min(step.execution_timeout_s, 3600),
                    attempt=attempt, start_sha=start_sha, run_dir=self.run_dir)
                report = ohgates.run_gate(ctx, step.gate)
                if step.kind == "merge" and error:
                    conflicts = list((result or {}).get("conflicts") or [])
                    name = "merge_conflict" if conflicts else "merge_failed"
                    report.checks.insert(0, ohgates.GateResult(
                        name=name, passed=False,
                        observed=(conflicts if conflicts else
                                  (result or {}).get("exit")),
                        expected=([] if conflicts else 0),
                        evidence_path=(result or {}).get("log"),
                        detail=error,
                    ))
                    report.passed = False
                ohgates.write_report(d, report)
                self._transition("gate_ran", coord_=c, attempt=attempt,
                                 payload={"gate": report.to_dict()})

                if status != "timeout":
                    if status_hint == "invalid":
                        status = "failed"
                    # A gate judges the worktree or the agent's output.  It
                    # cannot turn an agent execution error into success.  Pi
                    # can exit normally while recording a provider error in
                    # result.json; a clean-tree gate may still pass in that
                    # exact case, but the error must reach classification so a
                    # 429 becomes deferred and eligible for an auto-resume pass.
                    elif error:
                        status = "failed"
                    else:
                        status = "passed" if report.passed else "failed"
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            status = "failed"
            abort_victim = False
            report = ohgates.GateReport(coord=c, passed=False, checks=[])

        # Classify before anything is recorded. A transient failure becomes
        # `deferred`, which is neither failed nor quarantined, and which no
        # phase policy turns into an abort.
        failure_class = None
        # The verdict before any phase policy touched it. `retry.should_retry`
        # reads this one, because `quarantined` is what the phase decided to do
        # about a failure and not what this execution was.
        raw_status = status
        if abort_victim:
            status = "deferred"
            raw_status = "deferred"
        elif status_hint == "budget":
            status = "failed"
            failure_class = ohfail.STRUCTURAL
        elif status in ("failed", "timeout"):
            failure_class = ohfail.classify(error=error, report=report,
                                            kind=step.kind, status=status)
            if failure_class == ohfail.TRANSIENT:
                status = "deferred"
                raw_status = "deferred"

        if status == "failed" and phase.on_step_failure == "quarantine":
            status = "quarantined"

        # The cooldown is pushed out before the verdict is written, so the
        # verdict can carry it. A cooldown held only in memory is gone the
        # moment the supervisor is killed, and the resumed run would ask the
        # provider the question it was just rate-limited for.
        if status == "deferred" and not abort_victim:
            self._back_off(c, error)

        try:
            head = ""
            if step.worktree:
                h = ohexec.git("rev-parse HEAD", wt_path)
                head = h.stdout.strip() if h.returncode == 0 else ""

            # The latest attempt's small files are copied up to the step
            # directory, so every reader that looks where it always looked
            # finds them.
            self._project_attempt(c, attempt)

            # A successful agent may have committed the dirty input that
            # caused this execution.  Store the fingerprint of the finished
            # tree for the cache while the execution attempt history keeps the start
            # fingerprint.  A following clean resume then stays cached;
            # moving committed HEAD is not itself dirty state.
            finished_fp = (fingerprint(self.workflow, self.state, step)
                           if status == "passed" else fp)
            handover_path = d / "handover.md"
            handover_bytes = (handover_path.read_bytes()
                              if step.handover and handover_path.is_file()
                              and handover_path.stat().st_size <= step.handover.max_chars * 4
                              else None)
        except Exception as e:
            return self._attempt_faulted(c, step, fp, attempt, t0,
                                         f"{type(e).__name__}: {e}")

        import hashlib
        payload = {
            "status": status, "fingerprint": finished_fp, "step_id": step.id,
            "handover_path": handover_path.relative_to(self.run_dir).as_posix() if handover_bytes is not None else None,
            "handover_sha256": hashlib.sha256(handover_bytes).hexdigest() if handover_bytes is not None else None,
            "kind": step.kind,
            "result_path": "result.json" if (d / "result.json").exists() else None,
            "attempt_dir": str(d.relative_to(self.step_dir(c))).replace("\\", "/"),
            "gate": report.to_dict(), "wall_seconds": round(time.time() - t0, 1),
            "head_sha": head, "error": error, "failure_class": failure_class,
            "abort_victim": abort_victim,
            "transient_signature": (ohfail.explain(error)
                                    if failure_class == ohfail.TRANSIENT else None),
            # The tool call that was open when an agent stopped: the evidence a
            # stall, a cap or a kill leaves behind (tool-output contract).
            "open_tool_call": ((result or {}).get("open_tool_call")
                               if step.kind == "agent" and isinstance(result, dict)
                               else None),
            **(self._cooldown_record() if status == "deferred"
               and not abort_victim else {}),
            **({"killed": ohkill.taken(d)} if status_hint == "killed" else {}),
        }
        self._transition("attempt_finished", coord_=c, attempt=attempt,
                         payload=payload)
        ohkill.discard(self.step_dir(c), attempt)
        self.say(f"  [{c}] {status} in {round(time.time() - t0, 1)}s"
                 + (f" ({failure_class})" if failure_class else "")
                 + (f" - {error}" if error else ""))

        return {"status": status, "raw_status": raw_status, "error": error,
                "report": report, "abort_victim": abort_victim,
                "attempt": attempt, "failure_class": failure_class,
                "payload": payload, "killed": status_hint == "killed"}

    def _open_budget(self) -> None:
        recorded = self.state.meta.get("token_budget") or {}
        limit = (self.cli_token_budget if self.cli_token_budget is not None
                 else recorded.get("limit_tokens") if self.resume and recorded
                 else self.workflow.token_budget)
        if limit is None:
            return
        reserve = (self.workflow.token_reserve
                   or recorded.get("reserve_tokens")
                   or ohbudget.default_reserve(limit, self.max_parallel))
        settled, billing, priced, unpriced = 0, 0.0, 0, 0
        if self.resume:
            run = rundir.open_run(self.run_dir, state=self.state)
            for view in run.steps():
                for a in view.attempts:
                    settled += (rundir.Run.usage(a) or {}).get("total_tokens") or 0
                    if a.get("tokens") is None:
                        continue
                    cost = a.get("cost")
                    if isinstance(cost, (int, float)) and not isinstance(cost, bool) \
                            and a.get("cost_source") not in (None, "unpriced"):
                        billing += float(cost)
                        priced += 1
                    else:
                        unpriced += 1
        self.budget = ohbudget.Ledger(
            limit, reserve, run_dir=self.run_dir, settled=settled,
            billing_usd=billing, priced_attempts=priced,
            unpriced_attempts=unpriced,
            overshoots=list(self.state.meta.get("token_overshoots") or []))
        self._transition("token_budget", payload={
            "kind": "limit", "limit_tokens": self.budget.limit,
            "reserve_tokens": self.budget.reserve,
            "settled_tokens": self.budget.settled})
        self.say(f"[budget] {self.budget.limit} tokens, {self.budget.reserve} "
                 f"reserved per agent attempt, {self.budget.settled} settled")

    def _admit(self, c: str, step: Step, fp: str | None) -> bool:
        grant, why = self.budget.admit(c, cancelled=self._abort.is_set)
        if grant is not None:
            return True
        if self._abort.is_set():
            why = "the run aborted while this step waited for tokens"
        else:
            self._budget_spent.set()
            self._paused.set()
            self._transition("token_budget", coord_=c, payload={
                "kind": "refused", "reason": why})
            self.say(f"  [{c}] TOKEN BUDGET: not admitted - {why}")
        self._defer_unstarted(c, step, fp, why)
        return False

    def _run_agent(self, step: Step, c: str, d: Path):
        if self.budget is None or not self.budget.holds(c):
            return self._drive_agent(step, c, d)
        spec = json.loads((d / "spec.json").read_text(encoding="utf-8"))
        self.budget.attach(c, d)
        usage = harness_executor_module(step.agent.harness_executor).usage
        result: dict = {}
        try:
            result, status, error = self._drive_agent(step, c, d, (c, usage))
        finally:
            self._settle_budget(c, c, d, spec.get("attempt"), result, usage)
        if status in (ohexecutor.FINISHED, ohexecutor.ERROR) \
                and (d / ohbudget.STOP_FILE).exists():
            status = "budget"
            error = (f"token budget: the pi guard started no further model call "
                     f"after this attempt reached its grant\n{error or ''}").strip()
        return result, status, error

    def _settle_budget(self, c: str, key: str, d: Path, attempt, result: dict,
                       usage) -> None:
        tokens = ohbudget.total_tokens((result or {}).get("tokens"))
        if tokens is None:
            try:
                live, _ = usage(d)
            except Exception:
                live = None
            tokens = ohbudget.total_tokens(live)
        record = self.budget.settle(key, tokens, cost=(result or {}).get("cost"),
                                    cost_source=(result or {}).get("cost_source"))
        if record is not None:
            self._budget_spent.set()
            self._transition("token_budget", coord_=c, attempt=attempt,
                             payload={"kind": "overshoot", **record})
            self.say(f"  [{c}] TOKEN BUDGET OVERSHOOT: {record['used_tokens']} "
                     f"tokens used on a grant of {record['grant_tokens']}, "
                     f"{record['overshoot_tokens']} past the run's "
                     f"{record['limit_tokens']}")

    def _observe_budget(self, observer, d: Path) -> bool:
        key, usage = observer
        try:
            live, _ = usage(d)
        except Exception:
            live = None
        return self.budget.observe(key, ohbudget.total_tokens(live))

    def _drive_agent(self, step: Step, c: str, d: Path, observer=None):
        harness_executor = self.harness_executors(step.agent.harness_executor)
        spec = json.loads((d / "spec.json").read_text(encoding="utf-8"))
        if self._abort.is_set():
            # The last check before a provider call. Between its slot and
            # this line the step wrote its brief and its spec, which takes long
            # enough for another step's failure to have aborted the run.
            return ({}, "aborted",
                    "the run aborted before this agent was launched")
        handle = harness_executor.launch(spec, d)
        with self._handles_lock:
            self._handles[c] = handle
        deadline = time.time() + step.execution_timeout_s
        status = ohexecutor.RUNNING
        while True:
            if self._was_killed_by_abort(c):
                with self._handles_lock:
                    self._handles.pop(c, None)
                return (harness_executor.collect(handle), "aborted",
                        "the run aborted while this step was still running")
            status = harness_executor.poll(handle)
            if self._was_killed_by_abort(c):
                with self._handles_lock:
                    self._handles.pop(c, None)
                return (harness_executor.collect(handle), "aborted",
                        "the run aborted while this step was still running")
            if status != ohexecutor.RUNNING:
                break
            request = ohkill.pending(self.step_dir(c), spec.get("attempt"))
            if request is not None:
                harness_executor.kill(handle)
                with self._handles_lock:
                    self._handles.pop(c, None)
                collected = harness_executor.collect(handle)
                return collected, "killed", ohkill.take(self.step_dir(c), request, d)
            if observer is not None and not self._observe_budget(observer, d):
                harness_executor.kill(handle)
                with self._handles_lock:
                    self._handles.pop(c, None)
                collected = harness_executor.collect(handle)
                said = str(collected.get("error") or "").strip()
                snap = self.budget.snapshot()
                msg = (f"token budget: stopped at {snap['observed_tokens']} "
                       f"observed tokens of the run's {snap['limit_tokens']}; "
                       f"no unreserved tokens were left to extend this "
                       f"attempt's grant")
                return collected, "budget", (msg + "\n" + said) if said else msg
            if time.time() > deadline:
                harness_executor.kill(handle)
                with self._handles_lock:
                    self._handles.pop(c, None)
                collected = harness_executor.collect(handle)
                # Keep the agent's own last words. A harness executor's `collect`
                # can return the provider's error text when the killed child wrote
                # no `result.json`, and the classifier reads that text.
                said = str(collected.get("error") or "").strip()
                msg = f"execution timeout {step.execution_timeout_s}s exceeded"
                return collected, "timeout", (msg + "\n" + said) if said else msg
            if self._abort.is_set():
                harness_executor.kill(handle)
                with self._handles_lock:
                    self._handles.pop(c, None)
                return (harness_executor.collect(handle), "aborted",
                        "the run aborted while this step was still running")
            time.sleep(self.poll_interval_s)
        with self._handles_lock:
            self._handles.pop(c, None)
        result = harness_executor.collect(handle)
        if observer is not None:
            self._observe_budget(observer, d)
        attempt = spec.get("attempt")
        refusal = self._completion_refusal(c, attempt, result)
        if refusal:
            kind = "closed" if "already closed" in refusal else "invalid"
            return result, kind, refusal
        return result, status, result.get("error")

    def _was_killed_by_abort(self, c: str) -> bool:
        with self._handles_lock:
            return c in self._killed_by_abort

    def _completion_refusal(self, c: str, attempt: int,
                            result: dict) -> str | None:
        execution = next((ex for ex in reversed(self.state.executions)
                          if ex.get("coord") == c
                          and ex.get("attempt") == attempt), None)
        if execution is None or execution.get("status") != "running":
            return f"completion refused: attempt {attempt} is already closed"
        got = result.get("attempt")
        if got is None:
            return f"completion refused: result has no attempt; expected {attempt}"
        if got != attempt:
            return (f"completion refused: result names attempt {got}; "
                    f"expected {attempt}")
        return None

    def _run_merge(self, step: Step, c: str, d: Path, wt_path: Path):
        """Mechanical. Exit 0 with the gate passing means no agent is needed.
        A failed merge aborts any merge state and proves the branch is back
        where it was. Content conflicts additionally record their paths."""
        before = ohexec.git_out("rev-parse HEAD", wt_path)
        msg = step.merge_message or f"merge {step.merge_branch}"
        m = ohexec.git(f'merge --no-ff --no-edit -m "{msg}" {step.merge_branch}',
                       wt_path, log_dir=d / "logs", name=f"merge-{step.id}")
        result = {"coord": c, "kind": "merge", "branch": step.merge_branch,
                  "before_sha": before, "exit": m.returncode,
                  "log": m.stdout_path}
        error = None
        if m.returncode != 0:
            conflicts = ohexec.git("diff --name-only --diff-filter=U", wt_path,
                                   log_dir=d / "logs", name=f"conflicts-{step.id}")
            result["conflicts"] = [p for p in conflicts.stdout.split("\n") if p.strip()]
            ohexec.git("merge --abort", wt_path, log_dir=d / "logs",
                       name=f"merge-abort-{step.id}")
            after = ohexec.git_out("rev-parse HEAD", wt_path)
            result["after_sha"] = after
            result["restored"] = after == before
            if result["conflicts"]:
                error = (f"merge of {step.merge_branch} conflicted on "
                         f"{result['conflicts']}; branch restored: "
                         f"{result['restored']}")
            else:
                error = (f"merge of {step.merge_branch} failed with exit "
                         f"{m.returncode}; branch restored: "
                         f"{result['restored']}")
        else:
            result["after_sha"] = ohexec.git_out("rev-parse HEAD", wt_path)
        attempt_record.write(d, result)
        return result, error

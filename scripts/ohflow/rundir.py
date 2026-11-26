"""The run directory: its layout, and one reader for everything in it.

A run directory is written by the engine and read by a dozen tools. This module
is the shared reader of where a file lives and what its words mean. It also
writes one file: `Run.write_summary` writes `summary.json` when a run ends and
when `ohflow report` repairs a run after a hard kill. Some readers still parse
run files directly; the module map in CONTRIBUTING.md names them.

    run = rundir.open_run(path)
    run.id, run.status, run.workflow            identity, status, workflow order
    run.steps()                             steps in workflow order, each with attempts
    run.attempts(coord)                     one record per execution of a step
    run.latest_attempt(coord)               the one with the highest attempt number
    run.usage(attempt)                      tokens, in the one vocabulary
    run.summary()                           what `summary.json` holds

The run log is the truth. `RunLog.replay` turns it into a `RunState`, with the
torn-line repair; this module adds the attempt files (`result.json`,
`gate.json`) and `workflow.json`, and never parses the run log itself.

Status words are the engine's (`pending`, `running`, `passed`, `failed`,
`timeout`, `quarantined`, `skipped`, `cached`, `deferred`, and `dry-run` for a
step a dry run listed). A run adds two: `orphaned`, a run the run log calls
`running` whose supervisor process is dead, and `held`, a run with no run log
whose supervisor waits for `go` behind `.ohflow-hold`. Both rules live here,
once.

Token vocabulary: `prompt_tokens` counts every token sent, cache reads and cache
writes included. The total is `prompt_tokens + completion_tokens`. Adding the
cache again counts it twice.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NamedTuple

from . import attempts as ohattempts
from . import summary_audit
from .attempt_record import TOKEN_KEYS
from .coords import step_dir_parts
from .run_log import RunLog, RunState
from .paths import win
from .workflow import slug as _slug
from .proc import pid_alive

__all__ = ["TOKEN_KEYS", "ORPHANED", "STARTING", "HELD", "NOT_STARTED",
           "STOPPED_STATUSES", "HOLD_FILE", "GO_FILE", "step_dir",
           "attempt_dir", "attempt_in", "hold_record", "hold_alive",
           "open_run", "Run", "StepView", "SummaryStep", "walk_summary",
           "step_status"]

ORPHANED = "orphaned"
STARTING = "starting"
HELD = "held"
NOT_STARTED = "not started"
#: The supervisor writes this while a held run waits for `go`: JSON with the
#: supervisor `pid` and the `since` stamp. `ohflow go` reads it to know that a
#: live process will see the go file.
HOLD_FILE = ".ohflow-hold"
#: `ohflow go` writes this; the held supervisor polls for it and leaves it in
#: place afterwards as the record of the release.
GO_FILE = "go"
#: A status after which the run takes no further step by itself.
STOPPED_STATUSES = frozenset({"finished", "failed", "paused", "crashed",
                              "interrupted", "orphaned"})

#: A step status that means the step's work is accepted.
_GOOD = ("passed", "cached")

# ------------------------------------------------------------------ layout


def step_dir(run_dir: Path, coord: str) -> Path:
    """`phases/<phase>/<step>`: where one step keeps its files."""
    phase, step = step_dir_parts(coord)
    return Path(run_dir) / "phases" / phase / step


def attempt_in(step_root: Path, attempt: int) -> Path:
    """The directory of one execution, under a step directory."""
    return Path(step_root) / "attempts" / f"{attempt:02d}"


def attempt_dir(run_dir: Path, coord: str, attempt: int) -> Path:
    """Where one execution writes. Every execution gets its own directory."""
    return attempt_in(step_dir(run_dir, coord), attempt)


class SummaryStep(NamedTuple):
    """One step of a saved `summary.json`, with its executions."""
    phase: str
    coord: str
    step: dict
    executions: list[dict]


def walk_summary(summary: dict) -> list[SummaryStep]:
    """Every step of a `summary.json`, in phase then coordinate order.

    The one walk of a saved summary. A reader that has a run directory opens it
    with `open_run`. A reader that has only a `summary.json` (a copied one, an
    archived one, one written before the run log existed) calls this.

    A summary written before attempt records existed carries `result` and no
    `attempts` key at all, and reading only `attempts` would show those runs
    as zero usage. An `attempts` key that is present and empty is a deliberate
    statement that nothing ever ran, and it stays empty.
    """
    found: list[SummaryStep] = []
    for phase, body in (summary.get("phases") or {}).items():
        for coordinate, step in (body.get("steps") or {}).items():
            if isinstance(step, dict):
                found.append(SummaryStep(str(phase), str(coordinate), step,
                                         _step_executions(step)))
    return sorted(found, key=lambda item: (item.phase, item.coord))


#: What one attempt directory measured. Two executions that share a directory
#: must not both carry these.
_MEASURED = ("tool_calls", "llm_calls", "observation_errors", "wall_seconds",
             "tokens", "cost", "cost_source", "infra_cost")


def _count_continued_once(entries: list[dict]) -> list[dict]:
    """A summary written before `Run.attempts` knew about reattach holds the
    numbers of a continued attempt on both of its executions. The earlier one
    is returned without them, so every reader counts the attempt once."""
    last_of = {(e.get("attempt"), e.get("dir")): i for i, e in enumerate(entries)
               if isinstance(e.get("attempt"), int) and e.get("dir")}
    out = []
    for i, e in enumerate(entries):
        key = (e.get("attempt"), e.get("dir"))
        if key in last_of and last_of[key] != i:
            e = {**e, **{k: None for k in _MEASURED if k in e},
                 "continued": True}
        out.append(e)
    return out


def _step_executions(step: dict) -> list[dict]:
    if "attempts" in step:
        entries = [e for e in (step["attempts"] or []) if isinstance(e, dict)]
        for e in entries:
            e.setdefault("kind", step.get("kind", "agent"))
        return _count_continued_once(entries)
    result = step.get("result")
    if not isinstance(result, dict):
        return []
    return [{**result, "attempt": step.get("attempt", 1),
             "status": step.get("status"),
             "kind": step.get("kind", "agent")}]


def _total_tokens(tokens: Any) -> int | None:
    """`prompt_tokens + completion_tokens`, or None when nothing was recorded."""
    if not isinstance(tokens, dict):
        return None
    return _int(tokens.get("prompt_tokens")) + _int(
        tokens.get("completion_tokens"))


def _int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return int(value)


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"error": f"{path.name} unreadable"}


def exit_record(run_dir: Path) -> dict | None:
    """The `exit.json` of the run's latest stop, or None.

    The file counts only when it is at least as new as the run log."""
    run_dir = Path(run_dir)
    try:
        written = (run_dir / "exit.json").stat().st_mtime
    except OSError:
        return None
    try:
        if (run_dir / "run-log.jsonl").stat().st_mtime > written:
            return None
    except OSError:
        pass
    record = _read_json(run_dir / "exit.json")
    return record if isinstance(record, dict) else None


def hold_record(run_dir: Path) -> dict | None:
    """The `.ohflow-hold` record, or None when the run holds nothing."""
    record = _read_json(Path(run_dir) / HOLD_FILE)
    return record if isinstance(record, dict) else None


def hold_alive(run_dir: Path) -> bool | None:
    """Whether the hold's supervisor is a live process that will read `go`.

    None when no hold record exists or it names no pid. The pid must predate
    the hold file, as `supervisor_alive` asks of `supervisor.pid`: Windows
    reuses PIDs, and a stranger that inherited the number is not waiting.
    """
    path = Path(run_dir) / HOLD_FILE
    record = hold_record(run_dir)
    if record is None:
        return None
    try:
        pid = int(record["pid"])
        written = path.stat().st_mtime
    except (KeyError, TypeError, ValueError, OSError):
        return None
    return pid_alive(pid, started_before=written)


# --------------------------------------------------------------------- run


@dataclass
class StepView:
    """One step, in workflow order."""
    coord: str
    phase: str
    step_id: str
    kind: str
    status: str
    attempt: int
    raw: dict
    attempts: list[dict]


def supervisor_record(run_dir: Path) -> tuple[int, float] | None:
    """The supervisor the run directory records, as (pid, time written).

    `supervisor.pid` is the record, or without it `.ohflow-owner.json`. The
    engine writes the owner file before `workflow.json`, so the owner is
    known during preflight and the baseline command, before the first
    run log line writes `supervisor.pid`.
    """
    pid_path = Path(run_dir) / "supervisor.pid"
    owner_path = Path(run_dir) / ".ohflow-owner.json"
    try:
        return (int(pid_path.read_text(encoding="utf-8").strip()),
                pid_path.stat().st_mtime)
    except (OSError, ValueError):
        pass
    try:
        return (int(json.loads(owner_path.read_text(encoding="utf-8"))["pid"]),
                owner_path.stat().st_mtime)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def live_supervisor(run_dir: Path) -> int | None:
    """The pid of the recorded supervisor when it is a live process that
    could be the supervisor, or None.

    Windows reuses PIDs. The supervisor exists before it writes its PID
    file, so a live process created after the file's mtime is a stranger
    that inherited the number.
    """
    record = supervisor_record(run_dir)
    if record is None or not pid_alive(record[0], started_before=record[1]):
        return None
    return record[0]


def open_run(run_dir: Path, *, state: RunState | None = None,
             records: list[dict] | None = None,
             supervisor_hint: int | None = None) -> "Run":
    """Open a run directory.

    A caller that already holds the replayed `state` and the parsed `records`
    (the dashboard reads the run log incrementally) passes them in, and the
    run log is not read again. `supervisor_hint` is a process that is known to
    be the run's supervisor before it writes `supervisor.pid`.
    """
    run_dir = Path(run_dir)
    if state is None:
        state = RunLog.replay(run_dir)
    return Run(run_dir, state, records, supervisor_hint)


class Run:
    def __init__(self, run_dir: Path, state: RunState,
                 records: list[dict] | None, supervisor_hint: int | None):
        self.run_dir = run_dir
        self.state = state
        self._records = records
        self._hint = supervisor_hint
        self._workflow: dict | None = None
        self._alive: bool | None = None
        self._finishes: dict[tuple[str, int], dict] | None = None

    # ---- identity and status

    @property
    def id(self) -> str:
        return self.state.run_id or self.run_dir.name

    @property
    def supervisor_alive(self) -> bool:
        """The run directory records a live process that could be the
        supervisor: `live_supervisor`, or the hint when nothing is recorded."""
        if self._alive is None:
            if supervisor_record(self.run_dir) is None:
                self._alive = bool(self._hint) and pid_alive(int(self._hint))
            else:
                self._alive = live_supervisor(self.run_dir) is not None
        return self._alive

    def handover(self, coord: str) -> str | None:
        """The recorded attempt's handover, with content integrity checked."""
        from .handover import recorded
        try:
            return recorded(self.run_dir, self.state.steps.get(coord))[1]
        except ValueError:
            return None

    def exit_record(self) -> dict | None:
        """`exit.json`, or None when it is absent, unreadable or older than the
        run log.

        A resume appends to the run log after the earlier stop wrote its exit
        record. That record then describes a stop the run has since left."""
        return exit_record(self.run_dir)

    @property
    def held(self) -> bool:
        """`.ohflow-hold` names a live supervisor waiting for `go`.

        A hold record without a readable pid falls back to the supervisor
        liveness the owner file gives, because the hold is written by the
        same process that claimed the directory.
        """
        alive = hold_alive(self.run_dir)
        if alive is None:
            return hold_record(self.run_dir) is not None and self.supervisor_alive
        return alive

    @property
    def status_without_run_log(self) -> str:
        """The name of a run that has no run log line, from its files.

        `held` while a live supervisor waits behind `.ohflow-hold`. `starting`
        while a supervisor or owner lives. The status that `exit.json` records
        when it records a stopped one (a preflight crash writes `crashed`).
        `not started` otherwise.
        """
        if self.held:
            return HELD
        if self.supervisor_alive:
            return STARTING
        recorded = self.exit_record()
        status = recorded.get("status") if recorded else None
        return status if status in STOPPED_STATUSES else NOT_STARTED

    @property
    def status(self) -> str:
        """The run log's status, with `orphaned` for a dead supervisor, and
        `held` while a live supervisor waits for `go`, as a campaign's REVISE
        round does on its resumed run directory."""
        if self.held:
            return HELD
        if self.state.status == "running" and not self.supervisor_alive:
            return ORPHANED
        return self.state.status

    # ---- workflow order

    @property
    def workflow(self) -> dict:
        """Workflow order, phase names and step definitions.

        `workflow.json` is the source. Before the engine writes it, the run log's
        `phase_started` payloads still name every step of a phase that began.
        """
        if self._workflow is None:
            self._workflow = self._workflow_model()
        return self._workflow

    def _workflow_model(self) -> dict:
        state = self.state
        workflow = _read_json(self.run_dir / "workflow.json")
        phases: list[dict] = []
        if isinstance(workflow, dict) and isinstance(workflow.get("phases"), list):
            for pi, ph in enumerate(workflow["phases"], start=1):
                ph = ph if isinstance(ph, dict) else {}
                name = str(ph.get("name") or f"phase {pi}")
                pc = f"{pi:02d}.{ph.get('slug_override') or _slug(name)}"
                steps = []
                for si, st in enumerate(ph.get("steps") or [], start=1):
                    st = st if isinstance(st, dict) else {}
                    steps.append({"coord": f"{pc}/{si:02d}.{st.get('id')}",
                                  "id": str(st.get("id")), "raw": st})
                phases.append({"coord": pc, "index": pi, "name": name,
                               "raw": ph, "steps": steps})
            return {"name": workflow.get("name") or state.workflow_name,
                    "max_parallel": workflow.get("max_parallel"),
                    "auto_resume": workflow.get("auto_resume"),
                    "repo": workflow.get("repo"),
                    "base_branch": workflow.get("base_branch"),
                    "phases": phases, "from_workflow": True}

        known: dict[str, dict] = {}
        for rec in self._run_log_records():
            if rec.get("event") != "phase_started" or not rec.get("coord"):
                continue
            pc = rec["coord"]
            payload = rec.get("payload") or {}
            if pc not in known:
                known[pc] = {"coord": pc, "index": len(known) + 1,
                             "name": payload.get("name") or pc, "raw": {},
                             "steps": [{"coord": c, "id": _step_id_of(c), "raw": {}}
                                       for c in payload.get("steps") or []]}
        for c, rec in state.steps.items():
            pc = c.split("/", 1)[0]
            entry = known.setdefault(pc, {"coord": pc, "index": len(known) + 1,
                                          "name": pc, "raw": {}, "steps": []})
            if all(s["coord"] != c for s in entry["steps"]):
                entry["steps"].append({"coord": c,
                                   "id": rec.step_id or _step_id_of(c),
                                   "raw": {"kind": rec.kind,
                                           "id": rec.step_id}})
        return {"name": state.workflow_name, "max_parallel": None,
                "auto_resume": None, "repo": None, "base_branch": None,
                "phases": list(known.values()), "from_workflow": False}

    def _run_log_records(self) -> list[dict]:
        if self._records is None:
            self._records = list(RunLog(self.run_dir).read())
        return self._records

    def steps(self, *, kind_default: str = "agent") -> list[StepView]:
        """Every step in workflow order, each with its attempts."""
        out = []
        for ph in self.workflow["phases"]:
            for st in ph["steps"]:
                c = st["coord"]
                rec = self.state.steps.get(c)
                raw = st["raw"]
                kind = raw.get("kind") or (rec.kind if rec else None) \
                    or kind_default
                step_id = st["id"]
                out.append(StepView(
                    coord=c, phase=ph["coord"], step_id=step_id, kind=kind,
                    status=step_status(self.state, c),
                    attempt=rec.attempt if rec and rec.attempt else 0,
                    raw=raw, attempts=self.attempts(c, kind)))
        return out

    # ---- attempts

    def step_dir(self, coord: str) -> Path:
        return step_dir(self.run_dir, coord)

    def attempt_dir(self, coord: str, attempt: int) -> Path:
        return attempt_dir(self.run_dir, coord, attempt)

    def result(self, coord: str) -> dict | None:
        """`result.json` of a step: what its latest execution produced."""
        return _read_json(self.step_dir(coord) / "result.json")

    def gate(self, coord: str) -> dict | None:
        """`gate.json` of a step: the verdict on its latest execution."""
        return _read_json(self.step_dir(coord) / "gate.json")

    @property
    def finishes(self) -> dict[tuple[str, int], dict]:
        """The `attempt_finished` record of each `(coord, attempt)`; the last one wins."""
        if self._finishes is None:
            self._finishes = {}
            for rec in self._run_log_records():
                if rec.get("event") == "attempt_finished":
                    self._finishes[(rec.get("coord"),
                                    rec.get("attempt") or 0)] = rec
        return self._finishes

    def attempts(self, coord: str, kind: str = "agent") -> list[dict]:
        """Every execution of one step, with the numbers each one produced.

        The numbers are embedded, so a summary can be read on a machine that
        never had the run directory, and a failed attempt's cost is counted
        instead of being replaced by the last attempt's.

        A run directory written before attempt directories existed keeps its
        `result.json` at the step root. That layout is detected by the absence
        of an `attempts` directory, and only then, so a new-format attempt that
        crashed before writing its own result stays empty instead of
        inheriting an older one's numbers.
        """
        root = self.step_dir(coord)
        old_layout = not (root / "attempts").is_dir()
        out: list[dict] = []
        executions = ohattempts.executions(self.state, coord)
        # A reattach continues its attempt: two executions then share one
        # number and one directory. The directory's numbers belong to the last
        # of them, so the earlier one carries none and nothing counts twice.
        last_of = {ex.get("attempt"): i for i, ex in enumerate(executions)}
        for i, ex in enumerate(executions):
            attempt = ex.get("attempt")
            if old_layout or not isinstance(attempt, int):
                d = root
            else:
                d = attempt_in(root, attempt)
            continued = (not old_layout and isinstance(attempt, int)
                         and last_of.get(attempt) != i)
            result = {} if continued else _read_json(d / "result.json") or {}
            gate = {} if continued else _read_json(d / "gate.json") or {}
            out.append({
                "attempt": attempt,
                # True for an execution whose attempt a reattach continued:
                # its numbers are on the execution that finished the attempt.
                "continued": continued,
                # A command, a merge and a bare gate produce no agent metrics.
                "kind": kind,
                "start_kind": ex.get("start_kind"),
                "status": ex.get("status"),
                "fingerprint": ex.get("fingerprint"),
                "started": ex.get("started_at"),
                "ended": ex.get("ended"),
                "failure_class": ex.get("failure_class"),
                "abort_victim": ex.get("abort_victim"),
                "retry_decision": ex.get("retry_decision"),
                "gate_passed": gate.get("passed"),
                "tool_calls": result.get("tool_calls"),
                "llm_calls": result.get("llm_calls"),
                "observation_errors": result.get("observation_errors"),
                "wall_seconds": result.get("wall_seconds"),
                "tokens": result.get("tokens"),
                "cost": result.get("cost"),
                "cost_source": result.get("cost_source"),
                "infra_cost": result.get("infra_cost"),
                "error": result.get("error"),
                "dir": str(d),
            })
        return out

    def latest_attempt_dir(self, coord: str) -> Path:
        """The numerically latest attempt directory of a step, found on disk.

        For a caller that runs inside the run and reads what its own step wrote.
        Every entry must be a number, so a stray directory stops the read.
        """
        root = self.step_dir(coord) / "attempts"
        found = [p for p in root.iterdir() if p.is_dir()]
        if not found:
            raise ValueError(f"no attempts found for {coord}")
        invalid = [p.name for p in found if not p.name.isdigit()]
        if invalid:
            raise ValueError(
                f"non-numeric attempt(s) for {coord}: {', '.join(invalid)}")
        return max(found, key=lambda p: int(p.name))

    def latest_attempt(self, coord: str) -> dict | None:
        """The execution with the highest attempt number."""
        numbered = [a for a in self.attempts(coord)
                    if isinstance(a.get("attempt"), int)]
        return max(numbered, key=lambda a: a["attempt"]) if numbered else None

    @staticmethod
    def usage(attempt: dict) -> dict | None:
        """One usage record: every key of `TOKEN_KEYS`, and the total."""
        tokens = attempt.get("tokens")
        if not isinstance(tokens, dict):
            return None
        out = {key: _int(tokens.get(key)) for key in TOKEN_KEYS}
        out["total_tokens"] = _total_tokens(tokens)
        return out

    # ---- the summary

    def summary(self, *, git: bool = True) -> dict[str, Any]:
        """The dictionary `summary.json` holds, computed from the files.

        `git=False` leaves `diff_stat` and `log` empty, for a caller that only
        wants the numbers and has no reason to start git.
        """
        state, workflow = self.state, self.workflow
        phases: dict[str, Any] = {}
        views = self.steps()
        for ph in workflow["phases"]:
            pc = ph["coord"]
            entry = dict(state.phases.get(pc, {}))
            steps: dict[str, Any] = {}
            for view in (v for v in views if v.phase == pc):
                rec = state.steps.get(view.coord)
                d = self.step_dir(view.coord)
                steps[view.coord] = {
                    "step_id": view.step_id,
                    "kind": view.kind,
                    "role": (view.raw.get("agent") or {}).get("role")
                    or view.kind,
                    "status": view.status,
                    "attempt": view.attempt,
                    "wall_seconds": rec.wall_seconds if rec else None,
                    "fingerprint": rec.fingerprint if rec else None,
                    "head_sha": rec.head_sha if rec else None,
                    "handover": rec.handover_path if rec else None,
                    "write_scope": list(view.raw.get("write_scope") or []),
                    "gate": rec.gate if rec else None,
                    "retry_decision": rec.retry_decision if rec else None,
                    # Every execution, failed ones included, with the numbers
                    # each produced.
                    "attempts": view.attempts,
                    "executions": len(view.attempts),
                    "result": _read_json(d / "result.json"),
                    "dir": str(d),
                }
            entry["steps"] = steps
            phases[pc] = entry

        quarantined = [c for c, r in state.steps.items()
                       if r.status in ("quarantined", "failed", "timeout")]
        # Exactly what `--resume` will re-run. A deferred step reached no
        # verdict, so it is listed apart from the ones judged and rejected.
        deferred = [c for c, r in state.steps.items() if r.status == "deferred"]
        worktrees = state.meta.get("worktrees") or {}
        repo = workflow.get("repo")
        summary: dict[str, Any] = {
            "run_id": self.id,
            "workflow": workflow.get("name") or state.workflow_name,
            "status": self.status,
            "started": state.started,
            "finished": state.finished,
            "repo": win(Path(repo)) if repo else "",
            "branch": workflow.get("base_branch") or "",
            "base_sha": state.meta.get("base_sha"),
            "args": state.meta.get("args"),
            "max_parallel": state.meta.get("max_parallel"),
            "baseline": state.meta.get("baseline"),
            "worktrees": state.meta.get("worktrees"),
            "worktree": next(iter(worktrees.values()), {}).get("path"),
            "quarantined": sorted(quarantined),
            "deferred": sorted(deferred),
            "excluded": sorted(state.exclusions.values(),
                               key=lambda e: str(e.get("coord"))),
            # The value the run used, which is the CLI override when there was
            # one. An older run records none, and the workflow value is then right.
            "auto_resume": state.meta.get("auto_resume",
                                          workflow.get("auto_resume")),
            "phases": phases,
        }
        diffs, logs = {}, {}
        if git:
            from . import exec as ohexec
            for name, f in worktrees.items():
                p = Path(f["path"])
                if not p.exists():
                    continue
                base = f.get("base_sha", "")
                diffs[name] = ohexec.git(f"diff --stat {base}..HEAD", p).stdout
                logs[name] = ohexec.git(f"log --oneline {base}..HEAD", p).stdout
        summary["diff_stat"] = diffs
        summary["log"] = logs
        return summary

    def write_summary(self) -> dict[str, Any]:
        """Compute the summary and save it as `summary.json`."""
        summary = self.summary()
        summary_audit.audit_summary(self.run_dir, summary)
        (self.run_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, default=str), encoding="utf-8")
        return summary


def step_status(state: RunState, coord: str) -> str:
    """The status word of one step.

    A dry run starts nothing, so the run log holds no step record. It records
    each step's word once, in the `phase_settled` event, and that word is
    `dry-run`.
    """
    rec = state.steps.get(coord)
    if rec:
        return rec.status
    settled = (state.phases.get(coord.split("/", 1)[0]) or {}).get("steps") or {}
    return settled.get(coord) or "pending"


def _step_id_of(coord: str) -> str:
    """The step id inside a coordinate: `02.build` in `01.p/02.build` gives `build`."""
    tail = coord.split("/", 1)[-1]
    return tail.split(".", 1)[-1] if "." in tail else tail

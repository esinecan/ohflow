"""The roll call matrix: the one end-to-end harness, behind `ohflow rollcall`.

A matrix is a table of test cases. A test case is one scenario of the roll-call workflow
(`ohflow.workflows.rollcall`) on some harness executors at some scale. Each test case runs through
`supervisor.run_workflow` in its own run directory, with its own worktree root and
its own branch prefix. Test cases run one after another.

The output carries one verdict line per test case, verdict first:

    PASS merge pi,claude,codex count=1  3m12s  41.2 k tokens  <run dir>
    FAIL review pi,claude count=1  1m02s  9.0 k tokens  <run dir>  step reviewer: ...
    SKIP single claude count=1  claude harness executor: <why>

and a last line, `ROLLCALL PASS: N of N test cases` or `ROLLCALL FAIL: F of N test cases
failed, S skipped`. `matrix.json` in the output directory holds every test case and
is rewritten after each one, so it is also the heartbeat of a long run.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import secrets
import sys
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable

from . import exec as ohexec
from . import preflight as ohpreflight
from . import rundir
from .console import say
from .harness_executors import harness_executor_for
from .paths import win
from .workflow import WorkflowArgMissing, WorkflowError, load_workflow, validate
from .supervisor import RunOptions, run_workflow

__all__ = ["RollCallCase", "MATRICES", "parse_case", "list_lines", "run_matrix",
           "make_repo", "EXIT_OK", "EXIT_FAIL", "EXIT_WORKFLOW"]

EXIT_OK, EXIT_FAIL, EXIT_WORKFLOW = 0, 1, 2
WORKFLOW = "ohflow.workflows.rollcall"
THREE = ("pi", "claude", "codex")
WHY_MAX = 110

#: Per-test-case options a test case line may carry, as `key=value` after the count.
OPTIONS = ("consolidator", "reviewer", "judge", "agent_profile", "carry_context")


@dataclass(frozen=True)
class RollCallCase:
    """One test case: a scenario, the harness executors it runs on, and its scale and options."""
    scenario: str
    harness_executors: tuple[str, ...]
    count: int = 1
    options: tuple[tuple[str, str], ...] = ()

    @property
    def label(self) -> str:
        extra = "".join(f" {k}" if v == "true" else f" {k}={v}"
                        for k, v in self.options)
        return f"{self.scenario} {','.join(self.harness_executors)} count={self.count}{extra}"

    def workflow_args(self) -> dict:
        args: dict = {"scenario": self.scenario, "harness_executors": ",".join(self.harness_executors),
                      "count": self.count}
        args.update(dict(self.options))
        return args


def _case(scenario: str, harness_executors, count: int = 1, **options) -> RollCallCase:
    opts = tuple((k, "true" if v is True else str(v))
                 for k, v in options.items())
    return RollCallCase(scenario, tuple(harness_executors), count, opts)


#: The matrices, as a table. Every test case is a workflow the roll call can build.
MATRICES: dict[str, tuple[RollCallCase, ...]] = {
    "smoke": tuple(_case("single", (h,)) for h in ("pi", "claude", "codex")),
    "quick": (
        *(_case("single", (harness_executor,)) for harness_executor in THREE),
        _case("fanout", THREE), _case("relay", THREE), _case("merge", THREE),
        _case("retry", ("pi",)),
        _case("review", ("pi", "claude")),
    ),
}
MATRICES["full"] = MATRICES["quick"] + (
    _case("fanout", ("pi",), 3),
    _case("campaign", ("pi",)),
    _case("single", ("claude",), agent_profile="hermetic"),
    _case("single", ("codex",), agent_profile="hermetic"),
    _case("retry", ("claude",), carry_context=True),
)
#: A silent command of twice the stall limit on every harness executor
#: (tool-output contract; `docs/history/silent-command-liveness.md`).
MATRICES["liveness"] = tuple(_case("silent", (h,)) for h in THREE)


def parse_case(text: str) -> RollCallCase:
    """`scenario:harness-executors[:count][:key=value ...]` -> RollCallCase. Raises ValueError."""
    parts = text.split(":")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise ValueError(f"test case {text!r} must read scenario:harness-executors[:count]")
    count, options = 1, []
    for part in parts[2:]:
        if part.isdigit():
            count = int(part)
        elif "=" in part and part.split("=", 1)[0] in OPTIONS:
            k, v = part.split("=", 1)
            options.append((k, v))
        elif part in OPTIONS:
            options.append((part, "true"))
        else:
            raise ValueError(f"test case {text!r}: {part!r} is neither a count nor "
                             f"one of {list(OPTIONS)}")
    return RollCallCase(parts[0], tuple(x for x in parts[1].split(",") if x), count,
                        tuple(options))


def list_lines() -> list[str]:
    """What `ohflow rollcall --list` prints."""
    lines = []
    for name, cases in MATRICES.items():
        lines.append(f"{name}: {len(cases)} test cases")
        lines += [f"  {c.label}" for c in cases]
    return lines


# ------------------------------------------------------------------- results


@dataclass
class RollCallCaseResult:
    index: int
    case: RollCallCase
    verdict: str = "FAIL"            # PASS, FAIL or SKIP
    reason: str = ""                 # why it failed or was skipped
    run_dir: str = ""
    seconds: float = 0.0
    tokens: int = 0
    resume: str = ""                 # "ok", a fault, or "" when not checked
    workflow: str = ""                   # the workflow's name, for a dry run

    def line(self) -> str:
        label = self.case.label
        if self.verdict == "SKIP":
            return f"SKIP {label}  {self.reason}"
        head = f"{self.verdict} {label}  {_duration(self.seconds)}  " \
               f"{_tokens(self.tokens)}" + (f"  {self.run_dir}" if self.run_dir else "")
        return head if self.verdict == "PASS" else f"{head}  {self.reason}"

    def data(self) -> dict:
        return {"index": self.index, "label": self.case.label,
                "scenario": self.case.scenario, "harness_executors": list(self.case.harness_executors),
                "count": self.case.count, "options": dict(self.case.options),
                "verdict": self.verdict, "reason": self.reason,
                "run_dir": self.run_dir, "seconds": round(self.seconds, 1),
                "tokens": self.tokens, "resume": self.resume}


def _duration(seconds: float) -> str:
    whole = int(round(seconds))
    return f"{whole // 60}m{whole % 60:02d}s"


def _tokens(n: int) -> str:
    return f"{n / 1000:.1f} k tokens" if n >= 1000 else f"{n} tokens"


def _short(text: str, limit: int = WHY_MAX) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit - 3] + "..."


def summary_line(results: list[RollCallCaseResult]) -> tuple[str, int]:
    """The last line of the output and the exit code."""
    total = len(results)
    failed = sum(r.verdict == "FAIL" for r in results)
    skipped = sum(r.verdict == "SKIP" for r in results)
    passed = total - failed - skipped
    if failed or passed == 0:
        return (f"ROLLCALL FAIL: {failed} of {total} test cases failed, "
                f"{skipped} skipped", EXIT_FAIL)
    tail = f", {skipped} skipped" if skipped else ""
    return f"ROLLCALL PASS: {passed} of {total} test cases{tail}", EXIT_OK


# ---------------------------------------------------------------- the repo


def make_repo(path: Path, branch: str = "main") -> Path:
    """A throwaway git repository with one commit and no merge commit."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    ohexec.git(f"init -b {branch}", path)
    ohexec.git('config user.name "ohflow rollcall"', path)
    ohexec.git("config user.email rollcall@localhost", path)
    ohexec.git("config commit.gpgsign false", path)
    (path / "README.md").write_text("a throwaway roll-call repository\n",
                                    encoding="utf-8")
    ohexec.git("add README.md", path)
    ohexec.git('commit -m "rollcall: the first commit"', path)
    return path


def _current_branch(repo: Path) -> str:
    out = ohexec.git("rev-parse --abbrev-ref HEAD", repo).stdout.strip()
    return out or "main"


# ----------------------------------------------------------------- the runner


@dataclass
class Context:
    """What every test case shares."""
    repo: Path
    out: Path
    base: str
    config: str
    config_name: str
    models: dict
    tag: str
    verbose: bool
    harness_executors: Callable | None
    say: Callable[[str], None]
    verdicts: dict = field(default_factory=dict)      # harness executor -> reason or None

    def case_dir(self, index: int, case: RollCallCase) -> Path:
        slug = re.sub(r"[^a-z0-9]+", "-", f"{case.scenario}-{'-'.join(case.harness_executors)}"
                      f"-{case.count}".lower()).strip("-")
        return self.out / f"{index:02d}-{slug}"

    def workflow_args(self, index: int, case: RollCallCase, case_dir: Path) -> dict:
        args = {"repo": str(self.repo), "base": self.base,
                "prefix": f"rollcall-{self.tag}-{index:02d}",
                "wt_root": str(case_dir / "wt"), **case.workflow_args()}
        if self.config:
            args["config"] = self.config
        return args


def _workflow_module():
    import importlib
    return importlib.import_module(WORKFLOW)


def _harness_executors_needed(args: dict) -> tuple[str, ...]:
    return _workflow_module().needed_harness_executors(args)


def _harness_executor_fault(ctx: Context, harness_executor: str) -> str | None:
    """Why a harness executor cannot run here, or None. Asked once per harness executor."""
    if harness_executor in ctx.verdicts:
        return ctx.verdicts[harness_executor]
    fault = None
    key = ctx.models[harness_executor].api_key_env if harness_executor in ctx.models else ""
    if key and not os.environ.get(key):
        fault = f"{harness_executor} harness executor: {key} is empty or unset"
    else:
        resolver = ctx.harness_executors or harness_executor_for
        results = ohpreflight.run_checks(
            ohpreflight.harness_executor_checks([harness_executor], resolver))
        bad = [r for r in results if r.status == "FAIL"]
        if bad:
            fault = f"{bad[0].need}: {_short(bad[0].observed)}"
    ctx.verdicts[harness_executor] = fault
    return fault


def _first_failure(run_dir: Path) -> str:
    """The first step that did not pass, and its first failing check."""
    run = rundir.open_run(run_dir)
    summary = run.summary(git=False)
    for item in rundir.walk_summary(summary):
        step = item.step
        if step.get("status") in ("passed", "cached"):
            continue
        name = step.get("step_id") or item.coord
        gate = step.get("gate") or {}
        for check in gate.get("checks") or []:
            if not check.get("passed"):
                return _short(
                    f"step {name}: gate {check.get('name')} failed, observed "
                    f"{check.get('observed')!r}, expected "
                    f"{check.get('expected')!r}")
        error = ((step.get("result") or {}).get("error")
                 or (step.get("attempts") or [{}])[-1].get("error"))
        return _short(f"step {name}: {step.get('status')}"
                      + (f", {error}" if error else ""))
    return f"run ended {summary.get('status')!r} with no step to blame"


def _run_tokens(run_dir: Path) -> int:
    if not (run_dir / "run-log.jsonl").exists():
        return 0
    run = rundir.open_run(run_dir)
    total = 0
    for item in rundir.walk_summary(run.summary(git=False)):
        for attempt in item.executions:
            usage = rundir.Run.usage(attempt)
            total += (usage or {}).get("total_tokens") or 0
    return total


def _started(run_dir: Path) -> int:
    path = run_dir / "run-log.jsonl"
    if not path.exists():
        return 0
    return sum('"event": "attempt_started"' in line or
               '"event":"attempt_started"' in line
               for line in path.read_text(encoding="utf-8").splitlines())


def _check_resume(ctx: Context, workflow, run_dir: Path, workflow_args: dict) -> str:
    """"ok" when a resume of a finished run starts no step, else the fault."""
    before = _started(run_dir)
    try:
        outcome = run_workflow(workflow, run_dir, RunOptions(
            resume="yes", dashboard=False, harness_executors=ctx.harness_executors, workflow_path=WORKFLOW,
            workflow_args=workflow_args))
    except Exception as e:                     # noqa: BLE001 - a finding
        return f"resume raised {type(e).__name__}: {_short(e)}"
    if outcome.problem:
        return f"resume refused: {_short(outcome.problem)}"
    started = _started(run_dir) - before
    return "ok" if started == 0 else f"resume started {started} step(s)"


@contextlib.contextmanager
def _stdout_to(stream):
    with contextlib.redirect_stdout(stream):
        yield


def _run_case(ctx: Context, index: int, case: RollCallCase) -> RollCallCaseResult:
    result = RollCallCaseResult(index, case)
    cdir = ctx.case_dir(index, case)
    args = ctx.workflow_args(index, case, cdir)
    try:
        workflow = validate(load_workflow(WORKFLOW, args))
        needed = _harness_executors_needed(args)
    except (WorkflowError, WorkflowArgMissing, ValueError) as e:
        result.reason = f"workflow does not build: {_short(getattr(e, 'message', e))}"
        return result
    for harness_executor in needed:
        fault = _harness_executor_fault(ctx, harness_executor)
        if fault:
            result.verdict, result.reason = "SKIP", fault
            return result

    cdir.mkdir(parents=True, exist_ok=True)
    run_dir = cdir / "run"
    result.run_dir = str(run_dir)
    started = time.monotonic()
    sink = None if ctx.verbose else io.StringIO()
    try:
        with (contextlib.nullcontext() if sink is None else _stdout_to(sink)):
            if case.scenario == "campaign":
                _run_campaign(ctx, result, args, cdir, run_dir)
            else:
                _run_workflow_case(ctx, result, workflow, args, run_dir)
    except Exception as e:                     # noqa: BLE001 - a test case fault is a FAIL
        result.verdict = "FAIL"
        result.reason = f"{type(e).__name__}: {_short(e)}"
    result.seconds = time.monotonic() - started
    return result


def _run_workflow_case(ctx: Context, result: RollCallCaseResult, workflow, args: dict,
                       run_dir: Path) -> None:
    outcome = run_workflow(workflow, run_dir, RunOptions(
        resume="no", dashboard=False, harness_executors=ctx.harness_executors, workflow_path=WORKFLOW,
        workflow_args=args, say=ctx.say if ctx.verbose else (lambda _m: None),
        warn=ctx.say if ctx.verbose else (lambda _m: None)))
    result.tokens = _run_tokens(run_dir)
    if outcome.problem:
        result.reason = f"the run did not start: {_short(outcome.problem)}"
        return
    summary = outcome.summary or {}
    if summary.get("status") != "finished" or summary.get("quarantined") \
            or summary.get("deferred"):
        result.reason = _first_failure(run_dir)
        return
    if not _all_passed(run_dir):
        result.reason = _first_failure(run_dir)
        return
    result.resume = _check_resume(ctx, workflow, run_dir, args)
    if result.resume != "ok":
        result.reason = f"resume check: {result.resume}"
        return
    result.verdict = "PASS"


def _all_passed(run_dir: Path) -> bool:
    return all(v.status in ("passed", "cached")
               for v in rundir.open_run(run_dir).steps())


# ------------------------------------------------------------------ campaign


def _commit_all(path: Path, message: str) -> None:
    ohexec.git("add -A", path)
    ohexec.git(f'commit -m "{message}"', path)


def _run_campaign(ctx: Context, result: RollCallCaseResult, args: dict, cdir: Path,
                  run_dir: Path) -> None:
    from . import campaign as ohcamp
    mod = _workflow_module()
    root = make_repo(cdir / "campaign")
    for rel, text in mod.campaign_files(args).items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    _commit_all(root, "rollcall: the campaign inputs")
    prefix = args["prefix"]
    milestone_args = {k: str(v) for k, v in args.items()
                      if k not in ("scenario", "count")}
    judge = replace(mod.judge_spec(args), max_iterations=60)
    camp = ohcamp.Campaign(
        name="rollcall-campaign", root=root, repo=ctx.repo,
        charter="charter.md", integration_branch=f"{prefix}-integration-branch", integration_base=ctx.base,
        judge=judge, judge_execution_timeout_s=900, max_revisions=2, auto_resume=0,
        milestones=(ohcamp.Milestone(
            id="m1", title="one agent reports for duty",
            workflow="milestones/m1/workflow.py", spec="milestones/m1/spec.md",
            output_branch=mod.output_branch_name(args), args=milestone_args),))
    problems = ohcamp.validate_campaign(camp)
    if problems:
        result.reason = f"campaign invalid: {_short(problems[0])}"
        return
    quiet_say = ctx.say if ctx.verbose else (lambda _m: None)
    code = ohcamp.CampaignController(camp, no_dashboard=True, say=quiet_say,
                                     harness_executors=ctx.harness_executors).run()
    mdir = root / "milestones" / "m1"
    run_dir_m = mdir / "runs" / "m1"
    result.run_dir = str(root)
    result.tokens = _run_tokens(run_dir_m) + sum(
        _run_tokens(p.parent) for p in (mdir / "judge").glob("r*/run/run-log.jsonl"))
    events = ohcamp.CampaignLog(root).events()
    decisions = [e.get("decision") for e in events if e.get("event") == "judged"]
    if code != ohcamp.EXIT_DELIVERED:
        why = next((e.get("why") for e in events
                    if e.get("event") == "escalated"), None)
        result.reason = _short(f"campaign exit {code}"
                               + (f": {why}" if why else "")
                               + f"; decisions {decisions}")
        return
    if decisions != ["REVISE", "PASS"]:
        result.reason = (f"the judge decisions read {decisions}, expected "
                         f"['REVISE', 'PASS']")
        return
    integration_after = ohexec.git(f"rev-parse {camp.integration_branch}", ctx.repo).stdout.strip()
    base_sha = ohexec.git(f"rev-parse {ctx.base}", ctx.repo).stdout.strip()
    if not integration_after or integration_after == base_sha:
        result.reason = "the integration branch did not move"
        return
    result.verdict = "PASS"


# ----------------------------------------------------------------- the entry


def _write_matrix(ctx: Context, name: str, results: list[RollCallCaseResult],
                  total: int) -> None:
    doc = {"matrix": name, "configuration": ctx.config_name,
           "repo": str(ctx.repo), "out": str(ctx.out), "cases_total": total,
           "cases": [r.data() for r in results]}
    (ctx.out / "matrix.json").write_text(json.dumps(doc, indent=2),
                                         encoding="utf-8")


def dry_run(cases: list[RollCallCase], ctx: Context, say_line) -> int:
    """Build and validate every test case's workflow. Nothing starts."""
    bad = 0
    for index, case in enumerate(cases, start=1):
        args = ctx.workflow_args(index, case, ctx.case_dir(index, case))
        try:
            workflow = validate(load_workflow(WORKFLOW, args))
        except (WorkflowError, WorkflowArgMissing, ValueError) as e:
            bad += 1
            say_line(f"INVALID {case.label}  {_short(getattr(e, 'message', e))}")
            continue
        steps = sum(1 for _ in workflow.steps())
        say_line(f"WORKFLOW {case.label}  {workflow.name}: {len(workflow.phases)} phases, "
                 f"{steps} steps")
    if bad:
        say_line(f"ROLLCALL DRY: {bad} of {len(cases)} test cases invalid")
        return EXIT_WORKFLOW
    say_line(f"ROLLCALL DRY: {len(cases)} test cases valid")
    return EXIT_OK


def run_matrix(*, matrix: str | None = None, cases: list[str] | None = None,
               repo: str | None = None, out: str | None = None,
               config: str | None = None, dry: bool = False,
               verbose: bool = False, harness_executors: Callable | None = None,
               write: Callable[[str], None] = say) -> int:
    """Run a matrix or a list of test cases; print the verdicts through `write`."""
    if cases:
        try:
            chosen = [parse_case(c) for c in cases]
        except ValueError as e:
            write(f"ROLLCALL INVALID: {e}")
            return EXIT_WORKFLOW
        name = "cases"
    else:
        name = matrix or "quick"
        if name not in MATRICES:
            write(f"ROLLCALL INVALID: unknown matrix {name!r}; use one of "
                  f"{list(MATRICES)}")
            return EXIT_WORKFLOW
        chosen = list(MATRICES[name])

    mod = _workflow_module()
    try:
        config_name, models = mod.load_config(config)
    except ValueError as e:
        write(f"ROLLCALL INVALID: {e}")
        return EXIT_WORKFLOW

    out_dir = Path(out).resolve() if out else Path(
        os.environ.get("TEMP", ".")) / f"rollcall-{secrets.token_hex(3)}"
    out_dir.mkdir(parents=True, exist_ok=True)
    if repo:
        repo_path = Path(repo).resolve()
    elif dry:
        repo_path = out_dir / "repo"          # named, never created
    else:
        repo_path = make_repo(out_dir / "repo")
    base = _current_branch(repo_path) if (repo_path / ".git").exists() else "main"
    ctx = Context(repo=repo_path, out=out_dir, base=base,
                  config=str(Path(config).resolve()) if config else "",
                  config_name=config_name, models=models,
                  tag=secrets.token_hex(2), verbose=verbose, harness_executors=harness_executors,
                  say=write)
    if dry:
        return dry_run(chosen, ctx, write)

    results: list[RollCallCaseResult] = []
    for index, case in enumerate(chosen, start=1):
        r = _run_case(ctx, index, case)
        results.append(r)
        _write_matrix(ctx, name, results, len(chosen))
        write(r.line())
    last, code = summary_line(results)
    write(last)
    return code

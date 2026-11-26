"""The one function that runs a workflow: `run_workflow`.

`ohflow run`, the campaign controller and the real-model test all call it. It
reserves the run directory, starts the run's dashboard, runs the engine and writes the exit report on every exit path, so a run has
one dashboard and one exit report whichever entry point started it.

Detaching stays in the CLI: a detached run starts a second process, and that
process calls `run_workflow` too.

The hold gate lives here as well. `RunOptions.hold` makes a fresh run write
its plan, serve its dashboard and pass preflight, then wait behind
`.ohflow-hold` for `<run-dir>/go` before any agent starts. A person reads the
plan on the dashboard, edits the workflow module if the plan is wrong, and
`ohflow go` releases the run; the workflow is loaded again at that moment so
the edit is what runs. `estimate.json` is written before the wait, so the held
page carries a forecast, and again after the reload.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import cloud_spend
from . import estimate as ohestimate
from . import exit_report as ohexit
from . import pilot as ohpilot
from . import rundir
from .console import say as console_say
from .paths import win, python_cmd

__all__ = ["RunOptions", "RunOutcome", "run_workflow", "no_run_log",
           "resume_beside_supervisor", "open_browser", "go_command",
           "HOLD_POLL_S"]

RESUME_CHOICES = ("auto", "yes", "no")
#: How often a held run looks for its go file. Tests shorten it.
HOLD_POLL_S = 0.5
#: The refusal for `hold` on a run that already has a run log.
RESUME_CANNOT_HOLD = "a resume cannot hold: the run already started"


def go_command(run_dir: Path) -> str:
    """The exact command that releases a held run, as every verb prints it."""
    return f"{python_cmd()} -m ohflow.cli go --run {win(Path(run_dir))}"


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stderr(message: str) -> None:
    console_say(message, file=sys.stderr)


@dataclass(frozen=True)
class RunOptions:
    """What a caller may decide about one run.

    `resume`: "yes" continues the run in the directory and refuses when it has
    no run log, "no" starts a fresh run, "auto" continues when a run log is
    there. `harness_executors` names a harness executor and returns the object that launches its
    agents; None takes the registry. `say` writes a line to the operator;
    `warn` writes a line that is a fault, to stderr by default.
    `on_dashboard` receives the URL once the run's dashboard serves.
    `on_release` is called once a held run's go file arrives, before the run
    starts.
    `hold` makes a fresh run wait for `ohflow go` after preflight; a dry run
    ignores it, and a resume refuses it unless `hold_resume` is set, as the
    campaign controller sets it for a round that a judge's REVISE starts; a
    resume never pilots. `history` names the directories of
    finished runs the estimate is read from; None reads `OHFLOW_HISTORY`, and
    with neither the run says so in one line and writes no `estimate.json`.
    `resume_checked` says the launcher of this detached supervisor already
    found no live supervisor in the run directory, where `supervisor.pid` by
    now may name the process the launcher started.
    """
    resume: str = "auto"
    hold: bool = False
    hold_resume: bool = False
    pilot: bool = False
    estimate: bool = True
    dashboard: bool = True
    dashboard_port: int | None = None
    open_dashboard: bool = False
    auto_resume: int | None = None
    max_parallel: int | None = None
    token_budget: int | None = None
    only_phase: str | None = None
    dry_run: bool = False
    harness_executors: Callable | None = None
    workflow_path: str | None = None
    workflow_args: dict = field(default_factory=dict)
    reservation_token: str | None = None
    resume_checked: bool = False
    predictions: str | None = None
    history: tuple[str, ...] | None = None
    on_dashboard: Callable[[str], None] | None = None
    on_release: Callable[[], None] | None = None
    say: Callable[[str], None] = console_say
    warn: Callable[[str], None] = _stderr


@dataclass
class RunOutcome:
    """How a run ended.

    `status` is the engine's final status, or `crashed` when the engine
    refused to start, or `refused` when the run directory was not this run's
    to use. `summary` is the engine's result, None when the engine never
    finished. `problem` is the message a person needs when the run did not
    start or stopped on a preflight fault. `verdict` is the one-sentence line
    of the exit report, None for a dry run. `run` reads the run directory.
    """
    run_dir: Path
    status: str
    summary: dict | None = None
    problem: str | None = None
    verdict: str | None = None

    @property
    def run(self) -> "rundir.Run | None":
        if not (self.run_dir / "run-log.jsonl").exists():
            return None
        return rundir.open_run(self.run_dir)


def no_run_log(run_dir: Path) -> str | None:
    """The refusal for a resume with nothing to resume, or None."""
    if (Path(run_dir) / "run-log.jsonl").exists():
        return None
    return f"no run log to resume at {win(Path(run_dir))}"


def resume_beside_supervisor(run_dir: Path) -> str | None:
    """The refusal for a resume of a run its supervisor still runs, or None.

    A resume closes every attempt the run log calls running, because a dead
    supervisor left them. Beside a live supervisor that closes attempts that
    still work, and the supervisor's own results are then refused. A run the
    run log calls stopped is free, whatever process its record names.
    """
    run_dir = Path(run_dir)
    pid = rundir.live_supervisor(run_dir)
    if pid is None or pid == os.getpid():
        return None
    run = rundir.open_run(run_dir)
    if run.state.status != "running":
        return None
    return (f"run {run.id} is still running under supervisor pid {pid}; "
            f"resume it once that supervisor has stopped: {win(run_dir)}")


def open_browser(url: str, warn: Callable[[str], None] = _stderr) -> None:
    import webbrowser
    try:
        webbrowser.open(url)
    except Exception as e:
        warn(f"dashboard: could not open a browser ({e}); open {url}")


def run_workflow(workflow, run_dir: Path, options: RunOptions | None = None
                 ) -> RunOutcome:
    """Run `workflow` in `run_dir`. Exceptions other than a preflight fault carry
    on to the caller once the exit report is written, and the run stays
    resumable: a crash writes no run log event."""
    from .engine import Engine, PreflightError
    from .workflow import WorkflowError

    options = options or RunOptions()
    if options.resume not in RESUME_CHOICES:
        raise ValueError(f"resume must be one of {RESUME_CHOICES}, got "
                         f"{options.resume!r}")
    run_dir = Path(run_dir)
    if options.resume == "yes":
        missing = no_run_log(run_dir)
        if missing:
            return RunOutcome(run_dir, "refused", problem=missing)
        resume = True
    elif options.resume == "no":
        resume = False
    else:
        resume = (run_dir / "run-log.jsonl").exists()
    if resume and not options.resume_checked:
        beside = resume_beside_supervisor(run_dir)
        if beside:
            return RunOutcome(run_dir, "refused", problem=beside)
    # A rehearsal launches nothing, so there is nothing to hold back.
    pilot = options.pilot and not options.dry_run
    hold = (options.hold or pilot) and not options.dry_run
    started = resume or (run_dir / "run-log.jsonl").exists()
    if hold and started and (pilot or not options.hold_resume):
        return RunOutcome(run_dir, "refused", problem=RESUME_CANNOT_HOLD)
    if pilot and not workflow.units:
        return RunOutcome(run_dir, "refused", problem=ohpilot.NO_UNITS)

    def build_engine(workflow_now) -> Engine:
        return Engine(workflow_now, run_dir, run_id=run_dir.name,
                      max_parallel=options.max_parallel,
                      dry_run=options.dry_run, only_phase=options.only_phase,
                      resume=resume, workflow_path=options.workflow_path,
                      workflow_args=options.workflow_args,
                      auto_resume=options.auto_resume,
                      reservation_token=options.reservation_token,
                      harness_executors=options.harness_executors,
                      token_budget=options.token_budget,
                      predictions=options.predictions)

    engine = build_engine(workflow)

    if options.dry_run:
        # A rehearsal writes no exit report: nothing ran that a person would
        # need to be told about. It prints the estimate and keeps no file.
        _estimate(engine, run_dir, options, resume, write=False)
        try:
            summary = engine.run()
        except PreflightError as e:
            return RunOutcome(run_dir, "crashed", problem=str(e))
        return RunOutcome(run_dir, summary.get("status") or "finished", summary)

    # The exit report is written into the run directory, so the directory must
    # be this run's before anything writes there. A claim that fails belongs to
    # another engine, and its directory is not touched.
    try:
        engine.reserve_run_dir()
    except PreflightError as e:
        return RunOutcome(run_dir, "refused", problem=str(e))

    if hold:
        # The plan and the hold are on disk before the dashboard serves, so
        # the first page a person opens already reads `held` and shows every
        # planned step.
        engine.write_workflow_json()
        (run_dir / rundir.GO_FILE).unlink(missing_ok=True)
        (run_dir / rundir.HOLD_FILE).write_text(
            json.dumps({"pid": os.getpid(), "since": _now()}, indent=2),
            encoding="utf-8")

    handle = _start_dashboard(options, run_dir)
    priors: dict[tuple[str, ...], ohestimate.Prior] = {}
    info = None
    summary = None
    problem = None
    verdict = None
    try:
        if hold:
            problems = engine.preflight()
            if problems:
                raise PreflightError("preflight failed:\n  - "
                                     + "\n  - ".join(problems))
            if options.estimate:
                _estimate(engine, run_dir, options, resume, write=True,
                          say_missing=False, priors=priors)
            if pilot:
                _run_pilot(engine, run_dir, options)
                # The pilot's summary may lie under the history, and the
                # estimate after go counts it: that estimate reads again.
                priors.clear()
            _wait_for_go(run_dir, options)
            (run_dir / rundir.HOLD_FILE).unlink(missing_ok=True)
            if options.on_release:
                options.on_release()
            engine = _reload_engine(engine, options, build_engine)
            if pilot:
                ohpilot.reproject(run_dir, engine.workflow)
        # After the reload: the estimate describes the workflow that runs.
        # The history is read once: a held run estimates twice from one prior,
        # unless a pilot ran in between.
        if options.estimate:
            _estimate(engine, run_dir, options, resume, write=True,
                      priors=priors)
        summary = engine.run()
        info = ohexit.exit_info(summary.get("status") or "finished")
    except WorkflowError as e:
        # The edit made while the run was held does not build. The run stays
        # unstarted, and the go file stays as the record of the ask.
        info = ohexit.exit_info("crashed", e, traceback.format_exc())
        problem = str(e)
    except PreflightError as e:
        info = ohexit.exit_info("crashed", e, traceback.format_exc())
        problem = str(e)
    except KeyboardInterrupt as e:
        info = ohexit.exit_info("interrupted", e, traceback.format_exc())
        raise
    except BaseException as e:
        info = ohexit.exit_info("crashed", e, traceback.format_exc())
        raise
    finally:
        if hold:
            # On every exit path the hold is over: go released it, or the
            # run stopped, and a stopped run holds nothing.
            (run_dir / rundir.HOLD_FILE).unlink(missing_ok=True)
        verdict = _write_exit_report(run_dir, info, options)
        if handle is not None:
            handle.stop(final_status=info["status"] if info else None)
    return RunOutcome(run_dir, info["status"], summary, problem, verdict)


def _estimate(engine, run_dir: Path, options: RunOptions, resume: bool,
              *, write: bool, say_missing: bool = True,
              priors: dict[tuple[str, ...], ohestimate.Prior] | None = None,
              ) -> dict | None:
    """Estimate the run from the history and say the block.

    A resume counts only the steps it will run again: every step the run log
    already calls passed or cached costs nothing more. The estimate is a
    forecast, so a history that cannot be read is named and the run goes on.
    `priors` keeps the prior read from a history, so a second estimate of the
    same run reads no summary again.
    """
    history = ohestimate.history_paths(options.history)
    if history is None:
        if say_missing:
            options.say(ohestimate.NO_HISTORY)
        return None
    try:
        cached: set[str] = set()
        if resume and (run_dir / "run-log.jsonl").exists():
            from .run_log import RunLog
            cached = {c for c, rec in RunLog.replay(run_dir).steps.items()
                      if rec.status in ("passed", "cached")}
        key = tuple(history)
        prior = None if priors is None else priors.get(key)
        if prior is None:
            prior = ohestimate.Prior.from_history(history)
            if priors is not None:
                priors[key] = prior
        estimate = ohestimate.estimate_workflow(
            engine.workflow, prior, cached=cached,
            max_parallel=engine.cli_max_parallel)
        if write:
            ohestimate.write_estimate(run_dir, estimate)
    except Exception as e:  # noqa: BLE001 - a forecast never stops a run
        options.warn(f"estimate: not made ({type(e).__name__}: {e}); the run "
                     f"goes on without it")
        return None
    for line in ohestimate.render_text(estimate).splitlines():
        options.say(line)
    return estimate


def _run_pilot(engine, run_dir: Path, options: RunOptions) -> None:
    from .engine import PreflightError
    from .workflow import validate

    full = engine.workflow
    small = validate(ohpilot.pilot_workflow(full))
    pilot_dir = run_dir / ohpilot.PILOT_DIR
    ohpilot.write_pilot(run_dir, ohpilot.started_record(full, small, pilot_dir))
    options.say(f"pilot: running {', '.join(u.id for u in small.units)} in "
                f"{win(pilot_dir)}")
    try:
        outcome = run_workflow(small, pilot_dir, RunOptions(
            resume="no", dashboard=False, estimate=False,
            max_parallel=options.max_parallel,
            harness_executors=options.harness_executors,
            say=lambda line: options.say(f"[pilot] {line}"), warn=options.warn))
    except Exception as e:
        ohpilot.write_pilot(run_dir, ohpilot.crashed_record(
            full, small, pilot_dir, f"{type(e).__name__}: {e}"))
        raise
    if outcome.summary is None:
        problem = outcome.problem or f"the pilot run ended {outcome.status}"
        ohpilot.write_pilot(run_dir, ohpilot.crashed_record(
            full, small, pilot_dir, problem))
        raise PreflightError(f"the pilot did not run: {problem}")
    record = ohpilot.finished_record(full, small, pilot_dir, outcome.status,
                                     outcome.summary)
    ohpilot.write_pilot(run_dir, record)
    for line in ohpilot.render_text(record).splitlines():
        options.say(line)


def _wait_for_go(run_dir: Path, options: RunOptions) -> None:
    """Block until `<run-dir>/go` exists. Ctrl+C ends the run as interrupted."""
    options.say(f"held: waiting for go ({go_command(run_dir)})")
    go = run_dir / rundir.GO_FILE
    while not go.exists():
        time.sleep(HOLD_POLL_S)


def _reload_engine(engine, options: RunOptions, build_engine):
    """The engine that runs after `go`.

    When the caller named a workflow module, it is loaded and validated again
    so an edit made while the run was held is what runs, and `workflow.json`
    is rewritten to say so. A caller that handed over a built workflow and no
    module keeps the engine it has. A `WorkflowError` carries on to the
    caller; the hold file is already gone and the exit report names it.
    """
    from .workflow import load_workflow, validate

    if not options.workflow_path:
        return engine
    workflow = validate(load_workflow(options.workflow_path,
                                      options.workflow_args))
    fresh = build_engine(workflow)
    fresh.inherit_reservation()
    fresh.write_workflow_json()
    return fresh


def _start_dashboard(options: RunOptions, run_dir: Path):
    """Start the run's own dashboard, or return None.

    A dashboard that cannot start is named and the run goes on: a viewer is
    never a reason to lose a run. The browser opens only on request, because
    agents launch most runs and a window from an agent run is unwanted.
    """
    if not options.dashboard:
        return None
    from . import dashboard as ohdash
    port = options.dashboard_port or 0
    try:
        handle = ohdash.start(run_dir, port=port, supervisor_pid=os.getpid())
    except (OSError, OverflowError, ValueError) as e:
        options.warn(f"dashboard: not started on port {port} ({e}); the run "
                     f"goes on without it")
        return None
    options.say(f"dashboard: {handle.url}")
    if options.on_dashboard:
        options.on_dashboard(handle.url)
    if options.open_dashboard:
        open_browser(handle.url, options.warn)
    return handle


def _write_exit_report(run_dir: Path, info: dict | None,
                       options: RunOptions) -> str | None:
    """Write the three exit files and return the verdict line. A report that
    fails is named, never raised: it must not replace the exception, or the
    verdict, it describes."""
    if info is None:
        return None
    try:
        check = cloud_spend.check_run(run_dir)
        if check is not None:
            options.say("cloudflare: " + cloud_spend.report_lines(check)[0])
            for line in check.get("flags") or []:
                options.warn(f"cloudflare: {line}")
            if check.get("error"):
                options.warn(f"cloudflare: meters not read: {check['error']}")
    except Exception as e:
        options.warn(f"cloudflare check failed: {type(e).__name__}: {e}")
    try:
        paths = ohexit.write_exit_report(run_dir, info)
    except Exception as e:
        options.warn(f"exit report not written: {type(e).__name__}: {e}")
        return None
    options.say(f"exit report: {win(paths['html'])}")
    try:
        return json.loads(paths["json"].read_text(encoding="utf-8")).get(
            "verdict")
    except (OSError, ValueError):
        return None

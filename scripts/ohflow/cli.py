"""The CLI.

    ohflow preflight [--workflow <module|path> --args k=v ...] [--harness-executors a,b]
                    [-v] [--json]
    ohflow validate --workflow <module|path> [--args k=v ...] [-v] [--json]
                    [--history DIR ...]
    ohflow estimate --workflow <module|path> [--args k=v ...] [--history DIR ...]
                    [--max-parallel N] [--pilot RUN_DIR] [--json]
    ohflow board    --workflow <module|path> [--args k=v ...]
    ohflow construct --bundle <bundle> --out <campaign> [--history DIR ...]
    ohflow run      --workflow <module|path> --out <runs root>
                    [--run-id ID] [--max-parallel N] [--dry-run] [--detach]
                    [--hold] [--pilot] [--only-phase NAME] [--resume RUN_ID]
                    [--auto-resume N] [--token-budget N] [--no-dashboard]
                    [--dashboard-port N] [--open-dashboard] [--predictions FILE]
                    [--history DIR ...] [--json]
    ohflow go       --run <run dir> [--predictions FILE]
    ohflow kill     --run <run dir> --step <coord or step id> [--reason TEXT]
                    [--timeout S]
    ohflow status  --run <run dir> [--watch] [--json]
    ohflow watch    --run <run dir> [--timeout S] [--until change|end|attention]
                    [--cursor NAME] [--json]
    ohflow notes log   --run <run dir> "<text>"
    ohflow notes check --run <run dir> [--json]
    ohflow session open|send|wait|status|interrupt|close --dir <record dir>
    ohflow campaign validate|run|status|grant|watch|history|estimate
                    --campaign <module> [--args k=v ...]
                    (run: [--detach] [--no-dashboard] [--hold] [--pilot]
                     [--history DIR ...])
                    (history: --campaign may name the campaign folder;
                     [--milestone ID] [--json])
                    (estimate: [--history DIR ...] [--json])
    ohflow dashboard --run <run dir> [--port N] [--open]
    ohflow report   --run <run dir>
    ohflow position --run <run dir> --step <step id>
                    (or --workflow <module> --step <id> for a run not yet started)
    ohflow transcript --run <run dir> --step <step id> --html [--out FILE]
    ohflow explain  --run <run dir> --step <step id> [--attempt N] [--json]
    ohflow compare  --runs <run A> <run B> [--json]
    ohflow actions  --run <run dir> --step <step id> [--attempt N] [--json]
    ohflow revert   --run <run dir>
    ohflow rollcall [--matrix smoke|quick|full | --cases scenario:harness-executors[:count] ...]
                    [--dry-run] [--config FILE] [--repo DIR] [--out DIR]
                    [--list] [-v]

Every verb that reports prints its verdict on the first line. Exit codes:
0 success, 1 the run finished with a failure, 2 a workflow fault or an unknown run;
`watch` returns 10 when it gave up on the timeout with the run still going (a
held run included), and 3 at once for a run directory that holds a workflow
and no sign of a launch. `run --hold` waits for `go` after preflight; `go`
exits 1 when nothing is waiting. `estimate` exits 0 with one line when no
history is named: a missing history is not a fault of the workflow.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
import time
import traceback
from pathlib import Path
from typing import Callable

from . import actions as ohactions
from . import cloud_spend
from . import dashboard_data as ohdata
from . import detach
from . import estimate as ohestimate
from . import exit_report as ohexit
from . import compare as ohcompare
from . import explain as ohexplain
from . import kill as ohkill
from . import pilot as ohpilot
from . import preflight as ohpreflight
from . import report as ohreport
from . import retrodraft as ohretro
from . import runnotes, runstatus, tiers
from . import sessions as ohsessions
from . import watch as ohwatch
from . import IMPORT_ROOT, live, proc, rundir
from .console import say as print, use_utf8   # `print` here is the safe writer
from .coords import coord, render_gate, render_position
from .run_log import RunState
from .harness_executors import HARNESS_EXECUTOR_INFO, harness_executor_for, harness_executor_module
from .paths import win
from .workflow import WorkflowArgMissing, WorkflowError, load_workflow, objective_warnings, validate
from .supervisor import (RunOptions, go_command, no_run_log, open_browser,
                         resume_beside_supervisor, run_workflow)

EXIT_OK, EXIT_FAIL, EXIT_WORKFLOW = 0, 1, 2
TRACEBACK_TAIL_LINES = 12


_COMMA_PAIR = re.compile(r",\s*[A-Za-z_][A-Za-z0-9_]*=")


def parse_args_kv(items: list[str]) -> dict:
    out = {}
    for item in items or []:
        k, _, v = item.partition("=")
        if "," in k:
            raise WorkflowError(
                f"--args {item!r}: a key holds a comma. Give one --args k=v per key.")
        head = v.split(",", 1)[0]
        if "=" not in head and _COMMA_PAIR.search(v):
            parts = [f"{k}={head}"] + [p.strip() for p in v.split(",")[1:]]
            raise WorkflowError(
                f"--args {item!r} joins several keys with commas and would be read as one "
                f"{k!r} value. Repeat the flag once per key: "
                + " ".join(f"--args {p}" for p in parts))
        if v in ("true", "false"):
            out[k] = v == "true"
        elif v.isdigit():
            out[k] = int(v)
        else:
            out[k] = v
    return out


def _load(ns):
    workflow = load_workflow(ns.workflow, parse_args_kv(ns.args))
    return validate(workflow)


def workflow_ref(arg: str) -> str:
    """The workflow reference as a run directory should record it.

    A workflow module that names an existing file is recorded **absolute**. Three
    candidate anchors were considered and two of them do not work here.

    Relative to `workflow.repo` fails because a workflow module lives in the skills
    repository while `workflow.repo` is the repository the agents edit; the two are
    different trees and the workflow is usually outside the second one entirely.

    Relative to the run directory fails because run directories are archived and
    moved away from both repositories, which is exactly what the preserved
    Cortea runs are.

    An absolute path is correct at the moment it is written, and `--workflow`
    already overrides it when the checkout later moves. A dotted module name is
    stored verbatim: it resolves through `sys.path` and is location-independent
    already.
    """
    p = Path(arg)
    if p.suffix == ".py" and p.exists():
        return str(p.resolve())
    return str(arg)


# ------------------------------------------------------------------ commands


def _count(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _harness_executor_counts(workflow) -> dict:
    counts: dict = {}
    for _pi, _phase, _si, step in workflow.steps():
        if step.agent is not None:
            counts[step.agent.harness_executor] = counts.get(step.agent.harness_executor, 0) + 1
    return counts


def _workflow_detail(workflow) -> list[str]:
    """Today's per-step listing, with the harness executor and the model of each agent."""
    out = [f"repo: {win(workflow.repo)}   base branch: {workflow.base_branch}   "
           f"max_parallel: {workflow.max_parallel}", ""]
    spaces = workflow.all_workspaces()
    if len(spaces) > 1:
        out.append("workspaces:")
        for space in spaces:
            out.append(f"  {space.name}: {win(space.path)}")
            out.append(f"    base branch {space.base_branch}"
                       + (", owned by ohflow" if space.owned else "")
                       + (f", remote {space.remote}" if space.remote else "")
                       + (f", baseline `{space.baseline_cmd}`"
                          if space.baseline_cmd else ""))
        out.append("")
    out.append("worktrees:")
    for w in workflow.worktrees:
        out.append(f"  {w.name}: {win(w.path)}")
        out.append(f"    branch {w.branch} from {w.base}, node_modules "
                   f"{w.node_modules_mode}"
                   + (f", workspace {w.workspace}" if len(spaces) > 1 else ""))
    out.append("")
    for pi, phase in enumerate(workflow.phases, start=1):
        limit = (phase.max_parallel if phase.max_parallel is not None
                 else f"{workflow.max_parallel} (the workflow default)")
        out.append(f"phase {pi:02d}.{phase.slug} - \"{phase.name}\"  "
                   f"(on_step_failure={phase.on_step_failure}, "
                   f"min_success={phase.min_success}, max_parallel={limit})")
        for si, step in enumerate(phase.steps, start=1):
            c = coord(pi, phase.slug, si, step.id)
            role = step.agent.role if step.agent else step.kind
            who = (f" harness_executor={step.agent.harness_executor} model={tiers.label(step.agent)}"
                   if step.agent else "")
            out.append(f"  {c}   kind={step.kind} role={role}{who} "
                       f"worktree={step.worktree} timeout={step.execution_timeout_s}s")
            out.append(f"    write_scope: {', '.join(step.write_scope) if step.write_scope else '(nothing declared)'}")
            if step.depends_on:
                out.append(f"    depends_on: {', '.join(step.depends_on)}")
            out.append("    gate:")
            out.extend(render_gate(step, indent="      "))
        out.append("")
    return out


def _emit(ns, lines: list[str], data: dict) -> None:
    if getattr(ns, "json", False):
        print(json.dumps(data, indent=2, default=str))
    else:
        for line in lines:
            print(line)


def _workflow_name(ref: str) -> str:
    """The file stem of a `.py` path, the last dotted part of a module name."""
    last = Path(ref).name
    return last[:-3] if last.endswith(".py") else last.rsplit(".", 1)[-1]


def _fault(e: Exception) -> str:
    """`<ExceptionType>: <first line of the message>`."""
    text = str(e).strip()
    return f"{type(e).__name__}: {text.splitlines()[0] if text else ''}".rstrip(": ")


def _valid_line(workflow) -> str:
    """The `VALID` line of a workflow that validated."""
    counts = _harness_executor_counts(workflow)
    steps = sum(len(p.steps) for p in workflow.phases)
    executors = ", ".join(f"{k}:{v}" for k, v in counts.items()) or "none"
    unit_text = ""
    if workflow.units:
        unit_text = (f"; {_count(len(workflow.units), 'unit')} on "
                     f"{_count(len(workflow.paths), 'path')}")
    spaces = workflow.all_workspaces()
    space_text = f"; {_count(len(spaces), 'workspace')}" if len(spaces) > 1 else ""
    return (f"VALID {workflow.name}: {_count(len(workflow.phases), 'phase')}, "
            f"{_count(steps, 'step')}; harness executors {executors}"
            f"{unit_text}{space_text}")


def cmd_construct(ns) -> int:
    """`ohflow construct`: write the campaign for a bundle of milestone specs,
    then validate and estimate each milestone and the campaign."""
    from . import campaign as ohcamp
    from . import construct as ohcon
    bundle_dir = Path(ns.bundle).resolve()
    try:
        bundle = ohcon.read_bundle(bundle_dir)
        out = ohcon.write_campaign(bundle, ns.out)
    except ohcon.BundleRefused as refused:
        print(f"REFUSED {win(bundle_dir)}: {_count(len(refused.problems), 'problem')}")
        for problem in refused.problems:
            print(f"- {problem}")
        return EXIT_WORKFLOW
    print(f"CONSTRUCTED {win(out)}: {_count(len(bundle.milestones), 'milestone')}")
    patterns = {m.id: m.pattern for m in bundle.milestones}
    camp = ohcamp.load_campaign(out / "campaign.py")
    problems = ohcamp.validate_campaign(camp)
    history = ohestimate.history_paths(ns.history)
    prior = ohestimate.Prior.from_history(history) if history else None
    for m in camp.milestones:
        try:
            built = validate(load_workflow(out / m.workflow, ohcamp.milestone_args(camp, m)))
        except Exception as e:  # noqa: BLE001 - a milestone that will not build is a verdict
            faults = (list(e.problems) or [str(e)]) \
                if isinstance(e, WorkflowError) else [_fault(e)]
            print(f"{m.id} {patterns[m.id]}: INVALID {m.id}: {_count(len(faults), 'problem')}")
            print("\n".join(f"  - {fault}" for fault in faults))
            problems.append(f"{m.id}: workflow does not validate")
            continue
        problems += ohcamp.milestone_problems(camp, m, built)
        print(f"{m.id} {patterns[m.id]}: {_valid_line(built)}")
        if prior is not None:
            estimate = ohestimate.estimate_workflow(built, prior)
            print(f"{m.id}: {ohestimate.render_text(estimate).splitlines()[0]}")
    if prior is None:
        print(ohestimate.NO_HISTORY)
    for problem in problems:
        print(f"- {problem}")
    print("CAMPAIGN OK" if not problems else "CAMPAIGN INVALID")
    if problems:
        return EXIT_WORKFLOW
    print(f"start: python -m ohflow.cli campaign run --campaign "
          f"{(out / 'campaign.py').as_posix()} --pilot --detach")
    return EXIT_OK


def cmd_validate(ns) -> int:
    name = _workflow_name(ns.workflow)
    try:
        workflow = _load(ns)
    except WorkflowArgMissing:
        raise
    except Exception as e:  # noqa: BLE001 - a workflow that will not build is a verdict
        problems = (list(e.problems) or [str(e)]) \
            if isinstance(e, WorkflowError) else [_fault(e)]
        _emit(ns, [f"INVALID {name}: {_count(len(problems), 'problem')}"]
              + [f"- {p}" for p in problems],
              {"valid": False, "workflow": name, "problems": problems})
        return EXIT_WORKFLOW
    harness_executors = _harness_executor_counts(workflow)
    phases = len(workflow.phases)
    steps = sum(len(p.steps) for p in workflow.phases)
    # A warning, never a refusal: a workflow written before `Step.objective`
    # existed must still run, and the dashboard has a fallback for it.
    warnings = [f"WARNING: {line}" for line in objective_warnings(workflow)]
    spaces = workflow.all_workspaces()
    lines = [_valid_line(workflow)] + warnings
    data = {"valid": True, "workflow": workflow.name, "phases": phases,
            "steps": steps, "harness_executors": harness_executors, "warnings": warnings,
            "workspaces": [space.name for space in spaces]}
    if workflow.units:
        picked = {u.path: u.id for u in ohpilot.pick(workflow)}
        data["paths"] = [{"name": p.name, "units": sum(1 for u in workflow.units
                                                       if u.path == p.name),
                          "pilot_unit": picked.get(p.name)}
                         for p in workflow.paths]
    if getattr(ns, "verbose", False):
        for entry in data.get("paths") or []:
            lines.append(f"path {entry['name']}: {_count(entry['units'], 'unit')}, "
                         f"pilot unit {entry['pilot_unit'] or '-'}")
        lines += [""] + _workflow_detail(workflow)
        # Only when a history is named: `validate` has nothing to forecast
        # from otherwise, and the no-history line belongs to `estimate`.
        history = ohestimate.history_paths(getattr(ns, "history", None))
        if history:
            estimate = _estimate_of(workflow, history, None)
            data["estimate"] = estimate
            lines += [""] + ohestimate.render_text(estimate).splitlines()
    _emit(ns, lines, data)
    return EXIT_OK


def _estimate_of(workflow, history: list[str], max_parallel: int | None) -> dict:
    prior = ohestimate.Prior.from_history(history)
    return ohestimate.estimate_workflow(workflow, prior, max_parallel=max_parallel)


def cmd_estimate(ns) -> int:
    """Forecast a workflow's minutes, tokens and cost from the history of
    finished runs. Without a history there is nothing to forecast from, and
    the one line says what to pass; that is not a fault, so the exit is 0."""
    workflow = _load(ns)
    history = ohestimate.history_paths(ns.history)
    pilot_dir = Path(ns.pilot).resolve() if getattr(ns, "pilot", None) else None
    record = None
    if pilot_dir is not None:
        record = ohpilot.read_pilot(pilot_dir)
        if record is None:
            print(f"--pilot: no {ohpilot.PILOT_FILE} in {win(pilot_dir)}",
                  file=sys.stderr)
            return EXIT_FAIL
        if record.get("measured") is not None:
            record = {**record, "projection": ohpilot.project(
                workflow, record["measured"])}
    estimate = (_estimate_of(workflow, history, ns.max_parallel)
                if history is not None else None)
    lines = (ohestimate.render_text(estimate).splitlines() if estimate
             else [ohestimate.NO_HISTORY])
    if record is not None:
        lines += [""] + ohpilot.render_text(record).splitlines()
    if record is None and estimate is None:
        print(ohestimate.NO_HISTORY)
        return EXIT_OK
    data = dict(estimate or {})
    if record is not None:
        data["pilot"] = record
    _emit(ns, lines, data)
    return EXIT_OK


def cmd_preflight(ns) -> int:
    workflow, workflow_fault = None, None
    if ns.workflow:
        try:
            workflow = _load(ns)
        except Exception as e:  # noqa: BLE001 - an unloadable workflow is one failed check
            workflow_fault = _fault(e)
    resolver = getattr(ns, "harness_executors", None) or harness_executor_for
    if ns.harness_executor_names:
        names = [n.strip() for n in ns.harness_executor_names.split(",") if n.strip()]
    elif workflow is not None:
        names = sorted(_harness_executor_counts(workflow))
    else:
        names = sorted(HARNESS_EXECUTOR_INFO)
    checks = [ohpreflight.bash_check()]
    if workflow_fault is not None:
        checks.append(ohpreflight.workflow_load_check(workflow_fault))
    if workflow is not None:
        checks += ohpreflight.workflow_checks(workflow, resolver)
        known = {c.need for c in checks}
        checks += [c for c in ohpreflight.harness_executor_checks(names, resolver)
                   if c.need not in known]
    else:
        checks += ohpreflight.harness_executor_checks(names, resolver)
    results = ohpreflight.run_checks(checks)
    failed = [r for r in results if r.status == "FAIL"]
    lines = ohpreflight.render(results, verbose=ns.verbose)
    _emit(ns, lines, {"pass": not failed, "results": [
        {"need": r.need, "status": r.status, "observed": r.observed,
         "fix": r.fix} for r in results]})
    return EXIT_FAIL if failed else EXIT_OK


def cmd_board(ns) -> int:
    workflow = _load(ns)
    print(ohreport.render_board_md(workflow, RunState()))
    return EXIT_OK


def cmd_run(ns) -> int:
    from .engine import new_run_id

    if getattr(ns, "json", False) and not ns.detach:
        print("--json works only with --detach: an attached run prints lines.",
              file=sys.stderr)
        return EXIT_WORKFLOW
    if ns.dry_run and ns.resume:
        print("--dry-run with --resume is refused: a dry run writes run log events, "
              "and a resume would write them into the real run's log. Use "
              "`ohflow status --run <run dir>` to see what a resume would start.",
              file=sys.stderr)
        return EXIT_WORKFLOW
    pilot = bool(getattr(ns, "pilot", False))
    if pilot and ns.dry_run:
        print("--pilot with --dry-run is refused: the pilot runs agents, and a "
              "dry run launches none. `ohflow validate -v` lists the pilot units.",
              file=sys.stderr)
        return EXIT_WORKFLOW
    if pilot and ns.resume:
        print("--pilot with --resume is refused: the pilot runs before the hold, "
              "and a resume cannot hold.", file=sys.stderr)
        return EXIT_WORKFLOW
    workflow = _load(ns)
    if pilot and not workflow.units:
        print(ohpilot.NO_UNITS, file=sys.stderr)
        return EXIT_WORKFLOW
    # `--max-parallel 0` used to read as absent, because the engine wrote
    # `max_parallel or workflow.max_parallel`. An operator asking for zero agents
    # got the workflow default instead, silently.
    if ns.max_parallel is not None and ns.max_parallel < 1:
        raise WorkflowError(f"--max-parallel must be at least 1, got "
                            f"{ns.max_parallel}. Leave the flag out to let each "
                            f"phase decide.")
    if ns.auto_resume is not None and ns.auto_resume < 0:
        raise WorkflowError(f"--auto-resume must be zero or more, got "
                            f"{ns.auto_resume}. Zero pauses the run and waits for "
                            f"--resume.")
    token_budget = getattr(ns, "token_budget", None)
    if token_budget is not None and token_budget < 1:
        raise WorkflowError(f"--token-budget must be at least 1, got "
                            f"{token_budget}. Leave the flag out to use the "
                            f"workflow's token_budget.")
    predictions = None
    if getattr(ns, "predictions", None):
        try:
            predictions = Path(ns.predictions).read_text(encoding="utf-8")
        except OSError as e:
            print(f"--predictions: cannot read {ns.predictions}: {e}",
                  file=sys.stderr)
            return EXIT_WORKFLOW
    out_root = Path(ns.out).resolve()
    if ns.resume:
        run_dir = out_root if (out_root / "run-log.jsonl").exists() \
            else out_root / ns.resume
        missing = no_run_log(run_dir)
        if missing:
            print(missing, file=sys.stderr)
            return EXIT_FAIL
        # The launcher asks before it starts anything: once it has, the
        # supervisor record may name the process it started.
        beside = resume_beside_supervisor(run_dir) if ns.detach else None
        if beside:
            print(beside, file=sys.stderr)
            return EXIT_FAIL
    else:
        run_dir = out_root / (ns.run_id or new_run_id())
        if run_dir.exists() and not getattr(ns, "reservation_token", None):
            print(f"run directory already exists; use --resume to continue it: "
                  f"{win(run_dir)}", file=sys.stderr)
            return EXIT_FAIL
    # One mint per run. The directory name IS the run id; every caller below
    # is handed that string instead of making another one.
    run_id = run_dir.name

    if ns.detach:
        handoff_token = None
        if not ns.resume:
            try:
                run_dir.mkdir(parents=True, exist_ok=False)
            except FileExistsError:
                print(f"run directory already exists; use --resume to continue it: "
                      f"{win(run_dir)}", file=sys.stderr)
                return EXIT_FAIL
            handoff_token = secrets.token_urlsafe(24)
            handoff = run_dir / ".ohflow-handoff.json"
            with handoff.open("x", encoding="utf-8") as fh:
                json.dump({"run_id": run_id, "token": handoff_token}, fh,
                          indent=2)
        else:
            run_dir.mkdir(parents=True, exist_ok=True)
        # The child runs with cwd set to the package parent, not this process's
        # cwd, so a workflow named by a relative path would resolve against a
        # different directory. Hand it the resolved reference.
        argv = [sys.executable, "-m", "ohflow.cli", "run",
                "--workflow", workflow_ref(ns.workflow),
                "--out", str(run_dir.parent), "--run-id", run_id]
        if handoff_token:
            argv.append(f"--reservation-token={handoff_token}")
        # Forward the flag only when it was given. `--max-parallel` is both the
        # run default and a ceiling on every phase override, so injecting the
        # workflow default here would cap every phase at that default and a detached
        # run would honour fewer phase overrides than an attached one.
        if ns.max_parallel is not None:
            argv += ["--max-parallel", str(ns.max_parallel)]
        if ns.auto_resume is not None:
            argv += ["--auto-resume", str(ns.auto_resume)]
        if token_budget is not None:
            argv += ["--token-budget", str(token_budget)]
        for a in ns.args or []:
            argv += ["--args", a]
        if ns.only_phase:
            argv += ["--only-phase", ns.only_phase]
        if predictions is not None:
            argv += ["--predictions", str(Path(ns.predictions).resolve())]
        for h in getattr(ns, "history", None) or []:
            argv += ["--history", str(Path(h).resolve())]
        # The dashboard lives in the supervisor, which is the child: this
        # launcher returns in a second. Its URL lands in supervisor.log and in
        # dashboard.json.
        if getattr(ns, "no_dashboard", False):
            argv += ["--no-dashboard"]
        if getattr(ns, "dashboard_port", None) is not None:
            argv += ["--dashboard-port", str(ns.dashboard_port)]
        if getattr(ns, "open_dashboard", False):
            argv += ["--open-dashboard"]
        hold = bool(getattr(ns, "hold", False)) or pilot
        if hold:
            # The child supervisor is the process that holds; this launcher
            # returns, so it tells the person how to release the run.
            argv += ["--hold"]
        if pilot:
            argv += ["--pilot"]
        if ns.resume:
            # The child resolves out_root/run_id, which is the directory this
            # process already chose. Without --run-id the child minted a second
            # id of its own and could land in a different directory.
            argv += ["--resume", run_id, "--resume-checked"]
        env = dict(os.environ)
        env["PYTHONPATH"] = str(IMPORT_ROOT) + os.pathsep + \
            env.get("PYTHONPATH", "")
        # The detached supervisor's stdout is a file, not a console, so Python
        # picks the ANSI code page for it unless it is told otherwise. cp1252
        # cannot carry a box-drawing character, and the write then raises
        # inside the thread that is logging. Name the encoding for the child.
        env["PYTHONIOENCODING"] = "utf-8:replace"
        log_path = run_dir / "supervisor.log"
        pid_path = run_dir / "supervisor.pid"
        stale = _pid_record(pid_path)
        try:
            launched_proc = detach.launch(argv, cwd=IMPORT_ROOT, env=env,
                                          log_path=log_path)
        except detach.DetachFailed as error:
            # The reservation belongs only to this failed launch. Remove it so
            # the operator can run the same id from a safe launcher.
            if handoff_token:
                for path in (run_dir / ".ohflow-handoff.json", log_path):
                    path.unlink(missing_ok=True)
                try:
                    run_dir.rmdir()
                except OSError:
                    pass
            print(error, file=sys.stderr)
            return EXIT_FAIL
        # The launched process is the supervisor only when nothing wraps it.
        # Under the `wmi` launch method it is the `cmd.exe` that runs the
        # supervisor, and a Windows virtual environment puts a redirector in
        # front of the interpreter. The supervisor's pid is the one the
        # supervisor records in the run directory.
        deadline = time.monotonic() + DASHBOARD_WAIT_S
        written = stale
        if _pid_record(pid_path) == stale:
            pid_path.write_text(str(launched_proc.pid), encoding="utf-8")
            written = _pid_record(pid_path)
        supervisor_pid = _wait_for_supervisor(
            run_dir, launched_proc, deadline,
            resumed=bool(ns.resume), written=written)
        if not ns.resume and supervisor_pid != launched_proc.pid:
            pid_path.write_text(str(supervisor_pid), encoding="utf-8")
        launched = {"run_dir": str(run_dir), "pid": supervisor_pid,
                    "launch_method": launched_proc.method, "log": str(log_path)}
        no_dash = getattr(ns, "no_dashboard", False)
        if not no_dash:
            launched["dashboard"] = str(run_dir / "dashboard.json")
        alive = launched_proc.alive \
            if supervisor_pid == launched_proc.pid \
            else lambda: proc.pid_alive(supervisor_pid)
        url = None if no_dash else _wait_for_dashboard(run_dir, alive, deadline)
        if getattr(ns, "json", False):
            launched["url"] = url
            if hold:
                launched["held"] = True
                launched["go"] = go_command(run_dir)
            if pilot:
                launched["pilot"] = str(run_dir / ohpilot.PILOT_DIR)
            print(json.dumps(launched, indent=2))
            return EXIT_OK
        if no_dash:
            print("dashboard: off")
        elif url:
            print(f"dashboard: {url}")
        else:
            print(f"dashboard: pending (see "
                  f"{win(run_dir / 'dashboard.json')})")
        print(f"run dir: {win(run_dir)}")
        print(f"supervisor pid: {supervisor_pid}")
        if pilot:
            print(f"pilot: {win(run_dir / ohpilot.PILOT_DIR)}")
        if hold:
            print(f"go: {go_command(run_dir)}")
        return EXIT_OK

    outcome = run_workflow(workflow, run_dir, RunOptions(
        resume="yes" if ns.resume else "no",
        hold=bool(getattr(ns, "hold", False)), pilot=pilot,
        dashboard=not getattr(ns, "no_dashboard", False),
        dashboard_port=getattr(ns, "dashboard_port", None),
        open_dashboard=getattr(ns, "open_dashboard", False),
        auto_resume=ns.auto_resume, max_parallel=ns.max_parallel,
        token_budget=token_budget,
        only_phase=ns.only_phase, dry_run=ns.dry_run,
        workflow_path=workflow_ref(ns.workflow), workflow_args=parse_args_kv(ns.args),
        reservation_token=getattr(ns, "reservation_token", None),
        resume_checked=bool(getattr(ns, "resume_checked", False)),
        predictions=predictions,
        history=tuple(getattr(ns, "history", None) or ()) or None,
        harness_executors=getattr(ns, "harness_executors", None)))
    if outcome.problem:
        print(outcome.problem, file=sys.stderr)
    if outcome.summary is None:
        return EXIT_FAIL
    return _run_verdict(ns, run_dir, outcome)


DASHBOARD_WAIT_S = 20.0
CAMPAIGN_PID_WAIT_S = 20.0


def _pid_record(path: Path) -> tuple[int, int] | None:
    """`supervisor.pid` as (the time it was written, the pid), or None."""
    try:
        return path.stat().st_mtime_ns, int(
            path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _wait_for_supervisor(run_dir: Path, launched: detach.Launched,
                         deadline: float, *, resumed: bool,
                         written: tuple[int, int] | None) -> int:
    """The detached supervisor's pid, from the record the supervisor writes.

    A fresh run's engine names itself in `.ohflow-owner.json` when it claims
    the run directory. A resume claims nothing, so its record is the
    `supervisor.pid` the engine writes with its next run log line, which is
    any `supervisor.pid` other than `written`, the one the launcher left. The
    answer is the pid of `launched`, the process `detach.launch` started, when
    no record arrives by `deadline` or that process has died. The record is
    read once more after either, since a supervisor may write it and exit.
    """
    if not resumed:
        def read() -> int | None:
            try:
                return int(json.loads((run_dir / ".ohflow-owner.json").read_text(
                    encoding="utf-8"))["pid"])
            except (OSError, ValueError, KeyError, TypeError):
                return None
    else:
        def read() -> int | None:
            return _new_pid(run_dir / "supervisor.pid", written)
    return _wait_for_pid(read, launched, deadline)


def _new_pid(path: Path, written: tuple[int, int] | None) -> int | None:
    record = _pid_record(path)
    return record[1] if record is not None and record != written else None


def _wait_for_pid(read: Callable[[], int | None], launched: detach.Launched,
                  deadline: float) -> int:
    while True:
        over = time.monotonic() >= deadline or not launched.alive()
        pid = read()
        if pid is not None:
            return pid
        if over:
            return launched.pid
        time.sleep(0.05)


def _wait_for_dashboard(run_dir: Path, alive: Callable[[], bool],
                        deadline: float) -> str | None:
    """The detached run's dashboard URL, once it serves. Gives up at
    `deadline`, or at once when `alive` says the supervisor has died."""
    while True:
        url = runstatus.dashboard_url(run_dir)
        if url:
            return url
        if time.monotonic() >= deadline or not alive():
            return None
        time.sleep(0.25)


def _run_verdict(ns, run_dir: Path, outcome) -> int:
    """The end of an attached run: the verdict, and what a person does next.

    The supervisor has already said where the exit report is.
    """
    summary = outcome.summary
    bad = [c for c, s in _flat_statuses(summary).items()
           if s not in ("passed", "cached")]
    if ns.dry_run:
        print(f"dry run {summary['status']}: nothing ran; run dir "
              f"{win(run_dir)}")
        if summary.get("status") == "finished":
            return EXIT_OK
        return EXIT_FAIL if bad else EXIT_OK
    print("")
    print(outcome.verdict or f"run {summary['status']}: {win(run_dir)}")
    resume = live.resume_command(run_dir) \
        if summary["status"] != "finished" or bad else None
    if resume:
        print(f"resume: {resume}")
    return EXIT_FAIL if bad else EXIT_OK


def _flat_statuses(summary: dict) -> dict:
    out = {}
    for _pc, phase in (summary.get("phases") or {}).items():
        for c, s in (phase.get("steps") or {}).items():
            out[c] = s.get("status")
    return out


def _no_run(run_dir: Path) -> int:
    print(f"no run at {win(run_dir)}", file=sys.stderr)
    return EXIT_WORKFLOW


def cmd_status(ns) -> int:
    run_dir = Path(ns.run).resolve()
    if not ohwatch.is_run_dir(run_dir):
        return _no_run(run_dir)
    as_json = getattr(ns, "json", False)
    tty = sys.stdout.isatty()
    while True:
        read_out = live.read_out(run_dir)
        sentence = runstatus.sentence(read_out, run_dir)
        needs = runstatus.need_lines(read_out, run_dir)
        url = runstatus.dashboard_url(run_dir, read_out)
        running = read_out["run"]["status"] in runstatus.LIVE_STATUSES
        held = read_out["run"]["status"] == rundir.HELD
        pilot_lines = ohpilot.status_lines(run_dir) if held else []
        lines = ([sentence] + pilot_lines + needs
                 + ([f"dashboard: {url}"] if url else []))
        if as_json:
            view = ohdata.agent_view(run_dir) or {}
            text = json.dumps({"status": read_out["run"]["status"],
                               "sentence": sentence, "needs": needs,
                               "dashboard": url,
                               "attention": view.get("attention") or [],
                               "pilot": ohpilot.read_pilot(run_dir) if held else None},
                              indent=2)
        else:
            text = "\n".join(lines)
        if not getattr(ns, "watch", False):
            print(text)
            return EXIT_OK
        print(("\033[2J\033[H" if tty else "") + text, flush=True)
        if not running:
            return EXIT_OK
        time.sleep(3)


def cmd_watch(ns) -> int:
    run_dir = Path(ns.run).resolve()
    result = ohwatch.watch_run(run_dir, timeout=ns.timeout, until=ns.until,
                               cursor=ns.cursor, poll=ns.poll)
    if result.code == ohwatch.EXIT_UNKNOWN:
        print(result.lines[0], file=sys.stderr)
    else:
        _emit(ns, result.lines, result.data)
    return result.code


def cmd_go(ns) -> int:
    """Release a held run: write `<run-dir>/go` for the waiting supervisor.

    The verb writes only when a live process will read the file. A directory
    with no hold has nothing waiting, and a hold whose supervisor died would
    never see the go; both are refused with the reason.
    """
    run_dir = Path(ns.run).resolve()
    if not run_dir.is_dir():
        print(f"no run directory at {win(run_dir)}", file=sys.stderr)
        return EXIT_FAIL
    record = rundir.hold_record(run_dir)
    if record is None:
        print(f"no hold at {win(run_dir)}: nothing is waiting for go",
              file=sys.stderr)
        return EXIT_FAIL
    if not rundir.hold_alive(run_dir):
        print(f"the hold at {win(run_dir)} belongs to a dead supervisor "
              f"(pid {record.get('pid')}); start the run again",
              file=sys.stderr)
        return EXIT_FAIL
    pilot_record = ohpilot.read_pilot(run_dir)
    if pilot_record and pilot_record.get("state") == ohpilot.RUNNING:
        print(f"the pilot is still running in {pilot_record.get('run_dir')}; "
              f"go sent nothing. Send go when the projection is on the hold page.",
              file=sys.stderr)
        return EXIT_FAIL
    if getattr(ns, "predictions", None):
        source = Path(ns.predictions).resolve()
        try:
            text = source.read_text(encoding="utf-8")
        except OSError as e:
            print(f"--predictions: cannot read {win(source)}: {e}; go sent nothing",
                  file=sys.stderr)
            return EXIT_FAIL
        if runnotes.predictions_filled(run_dir):
            print(f"predictions.md in {win(run_dir)} already holds predictions; "
                  f"go sent nothing", file=sys.stderr)
            return EXIT_FAIL
        target = run_dir / "predictions.md"
        target.write_text(text, encoding="utf-8")
        if target.read_text(encoding="utf-8") != text:
            print(f"predictions.md in {win(run_dir)} does not match {win(source)} "
                  f"after the write; go sent nothing", file=sys.stderr)
            return EXIT_FAIL
        runnotes.log_line(run_dir, f"predictions.md written by go from {win(source)}")
        print(f"predictions.md written from {win(source)}")
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (run_dir / rundir.GO_FILE).write_text(stamp + "\n", encoding="utf-8")
    print(f"go sent to {win(run_dir)}")
    return EXIT_OK


def cmd_kill(ns) -> int:
    run_dir = Path(ns.run).resolve()
    try:
        coord, attempt, path = ohkill.send(run_dir, ns.step, ns.reason)
    except ohkill.KillRefused as e:
        print(f"NOT KILLED {ns.step}: {e}", file=sys.stderr)
        return EXIT_FAIL
    payload = ohkill.wait(run_dir, coord, attempt, ns.timeout)
    if payload is None:
        print(f"KILL SENT {coord} attempt {attempt}: the supervisor has not closed "
              f"the attempt after {ns.timeout:g} s; the request waits at {win(path)}")
        return EXIT_FAIL
    if payload.get("killed") is None:
        ohkill.discard(path.parent, attempt)
        print(f"NOT KILLED {coord} attempt {attempt}: it ended "
              f"{payload.get('status')} before the supervisor read the kill")
        return EXIT_FAIL
    print(f"KILLED {coord} attempt {attempt}: {payload.get('error')}")
    print(f"recorded deferred; the phase goes on, and `run --resume` starts "
          f"the step again once the run stops")
    return EXIT_OK


def cmd_rollcall(ns) -> int:
    from . import rollcall
    if ns.list:
        for line in rollcall.list_lines():
            print(line)
        return EXIT_OK
    return rollcall.run_matrix(
        matrix=ns.matrix, cases=ns.cases, repo=ns.repo, out=ns.out,
        config=ns.config, dry=ns.dry_run, verbose=ns.verbose, harness_executors=ns.harness_executors,
        write=print)


def cmd_notes(ns) -> int:
    run_dir = Path(ns.run).resolve()
    if not ohwatch.is_run_dir(run_dir):
        return _no_run(run_dir)
    if ns.notes_cmd == "log":
        print(runnotes.log_line(run_dir, ns.text))
        return EXIT_OK
    status = rundir.open_run(run_dir).status
    gaps = runnotes.check(run_dir,
                          run_live=status in runstatus.LIVE_STATUSES)
    head = ("NOTES COMPLETE" if not gaps
            else f"NOTES INCOMPLETE: {_count(len(gaps), 'gap')}")
    _emit(ns, [head] + gaps, {"complete": not gaps, "gaps": gaps})
    return EXIT_FAIL if gaps else EXIT_OK


def cmd_position(ns) -> int:
    if ns.run:
        run_dir = Path(ns.run).resolve()
        state = rundir.open_run(run_dir).state
        recorded = {}
        rj = run_dir / "run.json"
        if rj.exists():
            try:
                recorded = json.loads(rj.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                recorded = {}
        workflow_path = ns.workflow or recorded.get("workflow_path")
        if not workflow_path:
            print("give --workflow as well: run.json carries no workflow path",
                  file=sys.stderr)
            return EXIT_FAIL
        if not ns.workflow and Path(workflow_path).suffix == ".py" \
                and not Path(workflow_path).exists():
            print(f"the workflow this run recorded is gone: {win(Path(workflow_path))}. "
                  "Give --workflow with its new location.", file=sys.stderr)
            return EXIT_FAIL
        # The workflow is a function of its arguments, so a position rendered with
        # different ones describes a different workflow. Use the arguments the run
        # itself recorded unless the caller named others. `workflow_args` is what
        # the CLI was given; `args` is only what the workflow module copied back.
        if ns.args:
            args = parse_args_kv(ns.args)
        else:
            args = dict(recorded.get("workflow_args")
                        or recorded.get("args") or {})
        workflow = validate(load_workflow(workflow_path, args))
    else:
        workflow = _load(ns)
        state = RunState()
    _pi, _ph, _si, step = workflow.step_by_id(ns.step)
    from .coords import coord_of
    rec = None
    if state.steps:
        rec = state.steps.get(coord_of(workflow, ns.step))
    attempt = rec.attempt if rec and rec.attempt else 1
    from .handover import received
    root = Path(ns.run).resolve() if ns.run else None
    try:
        handovers = received(workflow, state, step, root) if root else {}
    except ValueError as e:
        print(f"position: {e}", file=sys.stderr)
        return EXIT_FAIL
    print(render_position(workflow, state, step, attempt=attempt,
                          handovers=handovers,
                          handover_path=str(root / "phases" / coord_of(workflow, ns.step) / "attempts" / f"{attempt:02d}" / "handover.md") if root else None))
    return EXIT_OK


def cmd_table(ns) -> int:
    from . import table as ohtable

    rows, problems = ohtable.load_rows(ns.runs, by=ns.by)
    if ns.reconcile:
        problems.extend(ohtable.reconcile_usage(ns.runs))
    text = (ohtable.render_json(rows) if ns.format == "json"
            else ohtable.render_markdown(rows))
    if ns.out:
        Path(ns.out).write_text(text, encoding="utf-8")
        print(f"{len(rows)} row(s) written to {win(Path(ns.out))}")
    else:
        print(text)
    for problem in problems:
        print(problem, file=sys.stderr)
    # A file that could not be read is reported and the other rows are still
    # rendered. The exit code says something was missed.
    return EXIT_FAIL if problems else EXIT_OK


def _transcript_step(run: "rundir.Run", requested: str):
    """Resolve one step without silently choosing between duplicate ids.

    A full coordinate is authoritative. The short form is the step id.
    """
    steps = run.steps()
    exact = [view for view in steps if view.coord == requested]
    if exact:
        return exact[0]
    matches = [view for view in steps if view.step_id == requested]
    return matches[0] if len(matches) == 1 else None


def _attempt_result(attempt: dict, attempt_dir: Path) -> dict:
    """The full agent result behind a compact attempt record."""
    result = dict(attempt)
    path = attempt_dir / "result.json"
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        loaded = None
    if isinstance(loaded, dict):
        result.update(loaded)
    return result


def _transcript_of(run: "rundir.Run", view, output: Path):
    """Where a human reads the newest attempt of this step that left a transcript.

    Returns `(path, None)` or `(None, why)`. The step's own harness executor decides what
    a transcript is: an HTML export, an event log or a conversation directory.
    """
    harness_executor = (view.raw.get("agent") or {}).get("harness_executor")
    if harness_executor not in HARNESS_EXECUTOR_INFO:
        return None, f"harness executor {harness_executor!r} has no transcript reader"
    why = "no attempt ran"
    numbered = [a for a in view.attempts if isinstance(a.get("attempt"), int)]
    for attempt in sorted(numbered, key=lambda a: a["attempt"], reverse=True):
        attempt_dir = Path(attempt["dir"])
        path, why = harness_executor_module(harness_executor).transcript(
            attempt_dir, _attempt_result(attempt, attempt_dir), output)
        if path is not None:
            return path, None
    return None, why


def _transcript_output_name(view, requested: str) -> str:
    stem = str(view.step_id or requested)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip(".-") or "transcript"
    return f"{stem}.transcript.html"


def cmd_transcript(ns) -> int:
    run_dir = Path(ns.run).resolve()
    if not (run_dir / "run-log.jsonl").is_file():
        print(f"no run-log.jsonl in {win(run_dir)}", file=sys.stderr)
        return EXIT_FAIL
    run = rundir.open_run(run_dir)
    view = _transcript_step(run, ns.step)
    if view is None:
        print(f"step {ns.step!r} is missing or ambiguous", file=sys.stderr)
        return EXIT_FAIL
    output = (Path(ns.out).resolve() if ns.out
              else run_dir / _transcript_output_name(view, ns.step))
    path, why = _transcript_of(run, view, output)
    if path is None:
        print(f"no transcript for step {ns.step!r}: {why}", file=sys.stderr)
        return EXIT_FAIL
    print(win(path))
    return EXIT_OK


def cmd_explain(ns) -> int:
    """One attempt of one step, as the inspector shows it, in bounded text."""
    run_dir = Path(ns.run).resolve()
    try:
        view = ohexplain.explain_data(run_dir, ns.step, ns.attempt)
    except LookupError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_FAIL
    if view is None:
        print(f"no ohflow run at {win(run_dir)}", file=sys.stderr)
        return EXIT_FAIL
    if ns.json:
        print(json.dumps(view, indent=2))
    else:
        print("\n".join(ohexplain.render(view)))
    return EXIT_OK


def cmd_compare(ns) -> int:
    """Two runs, step by step, by fixed rules, in bounded text."""
    run_a, run_b = (Path(r).resolve() for r in ns.runs)
    try:
        view = ohcompare.compare_data(run_a, run_b)
    except LookupError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_FAIL
    if ns.json:
        print(json.dumps(view, indent=2))
    else:
        print("\n".join(ohcompare.render(view)))
    return EXIT_OK


def cmd_actions(ns) -> int:
    """One attempt's model calls, each with the actions it launched."""
    run_dir = Path(ns.run).resolve()
    try:
        view = ohactions.actions_data(run_dir, ns.step, ns.attempt)
    except LookupError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_FAIL
    if view is None:
        print(f"no ohflow run at {win(run_dir)}", file=sys.stderr)
        return EXIT_FAIL
    if ns.json:
        print(json.dumps(view, indent=2))
    else:
        print("\n".join(ohactions.render(view)))
    return EXIT_OK


def _serve_forever(handle) -> None:
    """Block while the dashboard serves. Ctrl+C ends it."""
    while handle.alive:
        time.sleep(0.5)


def cmd_dashboard(ns) -> int:
    """Serve the page for a run directory that has no dashboard of its own:
    a finished run, an orphaned run, or a detached run whose URL is lost.

    A run whose own dashboard still serves gets no second server: the verb
    prints the recorded URL and exits, so one run never has two addresses.
    """
    from . import dashboard as ohdash
    run_dir = Path(ns.run).resolve()
    if not run_dir.is_dir():
        print(f"no run directory at {win(run_dir)}", file=sys.stderr)
        return EXIT_FAIL
    live_record = ohdash.live_record(run_dir)
    if live_record is not None:
        print(f"dashboard: {live_record.get('url')}")
        print("the run's own dashboard is serving; nothing else started")
        if ns.open and live_record.get("url"):
            open_browser(str(live_record["url"]))
        return EXIT_OK
    try:
        handle = ohdash.start(run_dir, port=ns.port or 0)
    except (OSError, OverflowError, ValueError) as e:
        print(f"dashboard: cannot listen on port {ns.port}: {e}",
              file=sys.stderr)
        return EXIT_FAIL
    print(f"dashboard: {handle.url}")
    if ns.open:
        open_browser(handle.url)
    print("serving until Ctrl+C")
    try:
        _serve_forever(handle)
    except KeyboardInterrupt:
        pass
    finally:
        handle.stop()
    return EXIT_OK


def cmd_report(ns) -> int:
    """Write the three exit-report files from a run directory's files alone.

    The one exit path that runs no code of its own - a hard kill, a machine
    restart - leaves a run with no report. This rebuilds it later, and calls
    such a run `orphaned`.
    """
    run_dir = Path(ns.run).resolve()
    if not (run_dir / "run-log.jsonl").exists() \
            and not (run_dir / "workflow.json").exists():
        print(f"no run-log.jsonl and no workflow.json in {win(run_dir)}: it is not "
              f"an ohflow run directory", file=sys.stderr)
        return EXIT_FAIL
    info, paths, verdict = ohexit.rebuild(run_dir)
    retro_status, retro_note = ohretro.write(run_dir)
    print(f"status:  {info['status']}")
    if verdict:
        print(f"verdict: {verdict}")
    print(f"report:  {win(paths['html'])}")
    print(f"         {win(paths['md'])}")
    if retro_status == ohretro.WRITTEN:
        print(f"retro:   {retro_note}")
    return EXIT_OK


def cmd_revert(ns) -> int:
    """Remove a run's worktrees and their branches, through git, on every
    platform. The run directory's `revert.json` says what to remove."""
    from . import worktree as ohwt
    run_dir = Path(ns.run).resolve()
    plan = ohwt.read_revert_plan(run_dir)
    if plan is None:
        old = run_dir / "REVERT.cmd"
        if old.exists() and os.name == "nt":
            # A run from before revert.json: its batch file still works here.
            p = proc.run(["cmd", "/c", str(old)], capture_output=True, text=True)
            print(p.stdout)
            if p.stderr:
                print(p.stderr, file=sys.stderr)
            return EXIT_OK if p.returncode == 0 else EXIT_FAIL
        if old.exists():
            print(f"no {ohwt.REVERT_PLAN} in {win(run_dir)}: this run is from "
                  f"before the revert plan, and its REVERT.cmd is a Windows "
                  f"batch file. Remove each worktree with `git worktree remove "
                  f"--force <path>` and its branch with `git branch -D <branch>`.",
                  file=sys.stderr)
            return EXIT_FAIL
        print(f"no {ohwt.REVERT_PLAN} in {win(run_dir)}", file=sys.stderr)
        return EXIT_FAIL
    ok, lines = ohwt.revert(plan)
    for line in lines:
        print(line)
    return EXIT_OK if ok else EXIT_FAIL


# -------------------------------------------------------------------- parser


def _campaign_history(ns) -> int:
    """`ohflow campaign history`: every round, read from the campaign's files.

    `--campaign` may name the campaign folder: the module of a campaign from
    before a rename may no longer import, and its log still reads."""
    from . import campaign as ohcamp
    from . import campaign_history as ohhistory
    target = Path(ns.campaign)
    if target.is_dir():
        root, name, order = target.resolve(), target.resolve().name, None
    else:
        camp = ohcamp.load_campaign(ns.campaign, parse_args_kv(ns.args))
        root, name = Path(camp.root), camp.name
        order = [m.id for m in camp.milestones]
    log = root / ohcamp.CAMPAIGN_LOG
    if not log.is_file():
        print(f"no campaign log at {win(log)}", file=sys.stderr)
        return EXIT_FAIL
    data = ohhistory.history(root, name=name, milestone_order=order,
                             milestone=ns.milestone)
    if ns.milestone and not data["milestones"]:
        print(f"milestone {ns.milestone!r} has no round or event in {win(log)}",
              file=sys.stderr)
        return EXIT_FAIL
    _emit(ns, ohhistory.render(data), data)
    return EXIT_OK


def _campaign_estimate(ns, camp) -> int:
    """`ohflow campaign estimate`: the forecast of the milestones that are
    left. Without a history there is nothing to forecast from, and the verb
    prints the line `estimate` prints and exits 0."""
    from . import campaign_estimate as ohcampest
    history = ohestimate.history_paths(ns.history)
    if history is None:
        print(ohestimate.NO_HISTORY)
        return EXIT_OK
    data = ohcampest.estimate_campaign(camp, ohestimate.Prior.from_history(history),
                                       history)
    _emit(ns, ohcampest.render_text(data).splitlines(), data)
    return EXIT_OK


def cmd_campaign(ns) -> int:
    """`ohflow campaign validate|run|status|watch|grant|history|estimate`: the
    milestone loop. `history` reads files only and takes a campaign folder too,
    and `estimate` reads files only as well."""
    from . import campaign as ohcamp
    if ns.campaign_cmd == "history":
        return _campaign_history(ns)
    camp = ohcamp.load_campaign(ns.campaign, parse_args_kv(ns.args))
    if ns.campaign_cmd == "validate":
        problems = ohcamp.validate_campaign(camp)
        for m in camp.milestones:
            if (Path(camp.root) / m.workflow).is_file():
                try:
                    built = validate(load_workflow(Path(camp.root) / m.workflow,
                                                   ohcamp.milestone_args(camp, m)))
                except Exception as e:           # a workflow that will not build
                    problems.append(f"{m.id}: workflow does not validate: {e}")
                else:
                    problems += ohcamp.milestone_problems(camp, m, built)
        for p in problems:
            print(f"- {p}")
        print("CAMPAIGN OK" if not problems else "CAMPAIGN INVALID")
        return EXIT_OK if not problems else EXIT_WORKFLOW
    if ns.campaign_cmd == "estimate":
        return _campaign_estimate(ns, camp)
    if ns.campaign_cmd == "status":
        states = ohcamp.replay(camp)
        for m in camp.milestones:
            s = states[m.id]
            print(f"{m.id:<24} {s.status:<10} judged {s.judgements}, "
                  f"revised {s.revisions}")
        status = ohcamp.read_status(Path(camp.root))
        if status is not None:
            print(json.dumps(status, indent=2))
        return EXIT_OK
    if ns.campaign_cmd == "grant":
        ohcamp.grant(camp, ns.milestone, ns.revisions)
        print(f"granted {ns.revisions} revision(s) to {ns.milestone}")
        return EXIT_OK
    if ns.campaign_cmd == "watch":
        result = ohwatch.watch_campaign(camp, timeout=ns.timeout,
                                        cursor=ns.cursor, poll=ns.poll)
        _emit(ns, result.lines, result.data)
        return result.code
    # run
    if ns.detach:
        root = Path(camp.root)
        argv = [sys.executable, "-m", "ohflow.cli", "campaign", "run",
                "--campaign", str(Path(ns.campaign).resolve())]
        for a in ns.args or []:
            argv += ["--args", a]
        if ns.no_dashboard:
            argv += ["--no-dashboard"]
        if getattr(ns, "hold", False):
            argv += ["--hold"]
        if getattr(ns, "pilot", False):
            argv += ["--pilot"]
        for h in getattr(ns, "history", None) or []:
            argv += ["--history", str(Path(h).resolve())]
        env = dict(os.environ)
        env["PYTHONPATH"] = str(IMPORT_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        env["PYTHONIOENCODING"] = "utf-8:replace"
        log = root / "campaign.log"
        pid_path = root / ohcamp.PID_FILE
        stale = _pid_record(pid_path)
        try:
            launched_proc = detach.launch(argv, cwd=IMPORT_ROOT, env=env,
                                          log_path=log, append=True)
        except detach.DetachFailed as error:
            print(error, file=sys.stderr)
            return EXIT_FAIL
        campaign_pid = _wait_for_pid(
            lambda: _new_pid(pid_path, stale), launched_proc,
            time.monotonic() + CAMPAIGN_PID_WAIT_S)
        if _pid_record(pid_path) == stale:
            pid_path.write_text(str(campaign_pid), encoding="utf-8")
        print(json.dumps({"campaign": camp.name, "pid": campaign_pid,
                          "launch_method": launched_proc.method, "log": str(log),
                          "status": str(root / ohcamp.STATUS)}, indent=2))
        return EXIT_OK
    return ohcamp.CampaignController(
        camp, no_dashboard=ns.no_dashboard, hold=bool(getattr(ns, "hold", False)),
        pilot=bool(getattr(ns, "pilot", False)),
        harness_executors=getattr(ns, "harness_executors", None),
        history=tuple(getattr(ns, "history", None) or ()) or None).run()


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="ohflow",
                                 description="fan-out orchestrator for "
                                             "agent harnesses")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def workflow_args(p):
        p.add_argument("--workflow", required=True,
                       help="path to a workflow module, or a dotted module name")
        p.add_argument("--args", action="append", default=[], metavar="k=v")

    def json_flag(p):
        p.add_argument("--json", action="store_true",
                       help="print data instead of lines")

    def history_flag(p):
        p.add_argument("--history", action="append", default=None, metavar="DIR",
                       help="a directory of finished runs the estimate reads "
                            "(summary.json files up to four levels down). "
                            "Repeatable. Default: the OHFLOW_HISTORY variable.")

    def add_watch_flags(p):
        p.add_argument("--timeout", type=float, default=300.0, metavar="S",
                       help="seconds to wait for news; 0 looks once")
        p.add_argument("--cursor", default="agent", metavar="NAME",
                       help="the watcher's name; each name reports only what "
                            "is new to it")
        p.add_argument("--poll", type=float, default=2.0,
                       help=argparse.SUPPRESS)
        json_flag(p)

    p = sub.add_parser("preflight",
                       help="check what a run needs; the verdict is line one")
    p.add_argument("--workflow", default=None,
                   help="also check what this workflow needs")
    p.add_argument("--args", action="append", default=[], metavar="k=v")
    p.add_argument("--harness-executors", dest="harness_executor_names", default=None,
                   metavar="a,b", help="check these harness executors")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="list the passed checks too")
    json_flag(p)
    p.set_defaults(fn=cmd_preflight)

    p = sub.add_parser("validate"); workflow_args(p)
    p.add_argument("-v", "--verbose", action="store_true",
                   help="add the detail of every step")
    history_flag(p)
    json_flag(p)
    p.set_defaults(fn=cmd_validate)

    p = sub.add_parser("estimate",
                       help="forecast a workflow's minutes, tokens and cost "
                            "from the history of finished runs")
    workflow_args(p)
    history_flag(p)
    p.add_argument("--max-parallel", type=int, default=None,
                   help="the run's --max-parallel, when it will be given")
    p.add_argument("--pilot", default=None, metavar="RUN_DIR",
                   help="add the projection from the pilot of this run, with "
                        "the unit counts of the module as it reads now")
    json_flag(p)
    p.set_defaults(fn=cmd_estimate)
    p = sub.add_parser("board"); workflow_args(p); p.set_defaults(fn=cmd_board)

    p = sub.add_parser("construct",
                       help="write a campaign from a bundle of milestone specs, "
                            "then validate and estimate each milestone")
    p.add_argument("--bundle", required=True, metavar="BUNDLE",
                   help="the bundle: bundle.md, milestones/<id>/spec.md and an "
                        "optional contracts.md")
    p.add_argument("--out", required=True, metavar="CAMPAIGN",
                   help="a new folder for the campaign")
    history_flag(p)
    p.set_defaults(fn=cmd_construct)

    p = sub.add_parser("run"); workflow_args(p)
    p.add_argument("--out", required=True, help="runs root; a run id is appended")
    p.add_argument("--run-id", default=None,
                   help="use this run id and this directory name instead of "
                        "minting one")
    p.add_argument("--max-parallel", type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--detach", action="store_true")
    p.add_argument("--hold", action="store_true",
                   help="write the plan, serve the dashboard, pass preflight, "
                        "then wait for `ohflow go --run <run dir>` before any "
                        "agent starts; the workflow is loaded again on go")
    p.add_argument("--pilot", action="store_true",
                   help="run the smallest unit of each path first in "
                        "<run dir>/pilot, project the full run from it, then "
                        "hold for `ohflow go`; implies --hold")
    p.add_argument("--reservation-token", default=None,
                   help=argparse.SUPPRESS)
    p.add_argument("--resume-checked", action="store_true",
                   help=argparse.SUPPRESS)
    p.add_argument("--only-phase", default=None)
    p.add_argument("--resume", default=None, metavar="RUN_ID")
    p.add_argument("--auto-resume", type=int, default=None, metavar="N",
                   help="how many times a phase that settled deferred may "
                        "re-run its deferred steps by itself, after the "
                        "cooldown. Overrides the workflow. 0 pauses the run and "
                        "waits for --resume, which is what a workflow does by "
                        "default.")
    p.add_argument("--token-budget", type=int, default=None, metavar="N",
                   help="the most tokens (prompt plus completion, cached "
                        "input included) the run's agent steps may use. "
                        "Overrides the workflow's token_budget; a resume keeps "
                        "the run's recorded budget unless this flag is given.")
    p.add_argument("--no-dashboard", action="store_true",
                   help="run without the live dashboard; the exit report is "
                        "still written")
    p.add_argument("--dashboard-port", type=int, default=None, metavar="N",
                   help="serve the dashboard on this port instead of one the "
                        "OS picks")
    p.add_argument("--open-dashboard", action="store_true",
                   help="open the dashboard in the default browser")
    p.add_argument("--predictions", default=None, metavar="FILE",
                   help="copy FILE to predictions.md when the run directory "
                        "is made")
    history_flag(p)
    p.add_argument("--json", action="store_true",
                   help="with --detach, print the launch record as JSON")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("go", help="release a run that `run --hold` is holding")
    p.add_argument("--run", required=True, help="the held run directory")
    p.add_argument("--predictions", default=None, metavar="FILE",
                   help="write FILE to predictions.md before the release, when "
                        "predictions.md holds no predictions yet")
    p.set_defaults(fn=cmd_go)

    p = sub.add_parser("kill", help="end one running step's attempt while the "
                                    "other steps run on")
    p.add_argument("--run", required=True, help="the running run directory")
    p.add_argument("--step", required=True,
                   help="the step's coordinate, or its id when the id is unique")
    p.add_argument("--reason", default=None, metavar="TEXT",
                   help="why, recorded in the run log with the kill")
    p.add_argument("--timeout", type=float, default=120.0, metavar="S",
                   help="how long to wait for the supervisor to close the attempt "
                        "(default 120)")
    p.set_defaults(fn=cmd_kill)

    p = sub.add_parser("status",
                       help="one line on what the run is, then what needs you")
    p.add_argument("--run", required=True)
    p.add_argument("--watch", action="store_true")
    json_flag(p)
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("watch",
                       help="wait for news about a run and print only what "
                            "is new")
    p.add_argument("--run", required=True)
    p.add_argument("--until", choices=["change", "end", "attention"],
                   default="change",
                   help="return on the first change, only when the run ends, "
                        "or on a new intervention item or the end")
    add_watch_flags(p)
    p.set_defaults(fn=cmd_watch)

    p = sub.add_parser("notes", help="the run notes: log a line, check gaps")
    nsub = p.add_subparsers(dest="notes_cmd", required=True)
    c = nsub.add_parser("log"); c.add_argument("--run", required=True)
    c.add_argument("text", help="what you did by hand, or what surprised you")
    c.set_defaults(fn=cmd_notes)
    c = nsub.add_parser("check"); c.add_argument("--run", required=True)
    json_flag(c)
    c.set_defaults(fn=cmd_notes)

    p = sub.add_parser("session", help="the orchestrator agent's sessions, one process per turn")
    ohsessions.add_verbs(p)

    p = sub.add_parser("position")
    p.add_argument("--workflow", default=None)
    p.add_argument("--run", default=None)
    p.add_argument("--step", required=True)
    p.add_argument("--args", action="append", default=[], metavar="k=v")
    p.set_defaults(fn=cmd_position)

    p = sub.add_parser("table")
    p.add_argument("--runs", action="append", required=True, metavar="PATH",
                   help="a summary.json, or a directory holding runs. "
                        "Repeatable. A directory is searched for summary.json "
                        "and *.summary.json.")
    p.add_argument("--by", choices=["run", "phase", "step"], default="phase")
    p.add_argument("--format", choices=["md", "json"], default="md")
    p.add_argument("--out", default=None, help="write here instead of stdout")
    p.add_argument("--reconcile", action="store_true",
                   help="compare agent result tokens with harness executor usage records")
    p.set_defaults(fn=cmd_table)

    p = sub.add_parser("transcript")
    p.add_argument("--run", required=True, help="one ohflow run directory")
    p.add_argument("--step", required=True,
                   help="step id or full coordinate from that run")
    p.add_argument("--html", action="store_true", required=True,
                   help="export a pi session as HTML; every other harness executor prints its "
                        "own transcript path")
    p.add_argument("--out", default=None,
                   help="HTML path; defaults to <run>/<step>.transcript.html")
    p.set_defaults(fn=cmd_transcript)

    p = sub.add_parser("explain",
                       help="why one step's attempt ended as it did, with "
                            "its gate, failure class, retry decision and "
                            "next step")
    p.add_argument("--run", required=True, help="one ohflow run directory")
    p.add_argument("--step", required=True,
                   help="step id or full coordinate from that run")
    p.add_argument("--attempt", type=int, default=None,
                   help="the attempt number; defaults to the newest")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_explain)

    p = sub.add_parser("compare",
                       help="two runs step by step: which steps ended "
                            "differently, what changed in their definition, "
                            "and what each run spent")
    p.add_argument("--runs", nargs=2, required=True, metavar=("A", "B"),
                   help="two ohflow run directories")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_compare)

    p = sub.add_parser("actions",
                       help="one attempt's model calls with their tokens and "
                            "latency, and the actions each call launched")
    p.add_argument("--run", required=True, help="one ohflow run directory")
    p.add_argument("--step", required=True,
                   help="step id or full coordinate from that run")
    p.add_argument("--attempt", type=int, default=None,
                   help="the attempt number; defaults to the newest")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_actions)

    p = sub.add_parser("revert")
    p.add_argument("--run", required=True)
    p.set_defaults(fn=cmd_revert)

    p = sub.add_parser("dashboard",
                       help="serve the live page for an existing run directory")
    p.add_argument("--run", required=True, help="one ohflow run directory")
    p.add_argument("--port", type=int, default=0,
                   help="0, the default, lets the OS pick a free port")
    p.add_argument("--open", action="store_true",
                   help="open the page in the default browser")
    p.set_defaults(fn=cmd_dashboard)

    p = sub.add_parser("campaign",
                       help="run milestones in order, each judged by a fresh "
                            "agent that may revise its inputs and rerun")
    csub = p.add_subparsers(dest="campaign_cmd", required=True)
    for name in ("validate", "run", "status", "grant", "watch", "history", "estimate"):
        c = csub.add_parser(name)
        c.add_argument("--campaign", required=True,
                       help="a campaign module exporting build(args)"
                            + ("; or the campaign folder" if name == "history"
                               else ""))
        c.add_argument("--args", action="append", default=[],
                       metavar="KEY=VALUE")
        if name == "watch":
            add_watch_flags(c)
        if name == "run":
            c.add_argument("--detach", action="store_true")
            c.add_argument("--no-dashboard", action="store_true")
            c.add_argument("--hold", action="store_true",
                           help="hold the campaign's first fresh round for "
                                "`ohflow go`, and a later fresh round or a "
                                "round after a judge's REVISE whose estimate "
                                "exceeds the first round's actual minutes by "
                                "half; a resume after an interruption never "
                                "holds")
            c.add_argument("--pilot", action="store_true",
                           help="run each fresh round's pilot first when its "
                                "workflow declares units, then hold for "
                                "`ohflow go`; implies --hold")
            history_flag(c)
        if name == "grant":
            c.add_argument("--milestone", required=True)
            c.add_argument("--revisions", type=int, default=1)
        if name == "history":
            c.add_argument("--milestone", default=None, metavar="ID",
                           help="only this milestone's rounds and events")
            json_flag(c)
        if name == "estimate":
            c.description = ("forecast the campaign: each milestone that has "
                             "not landed, its run estimate times one plus the "
                             "median number of REVISE rounds a milestone takes")
            history_flag(c)
            json_flag(c)
        c.set_defaults(fn=cmd_campaign)

    p = sub.add_parser("rollcall",
                       help="run the roll-call matrix: every scenario on every "
                            "harness executor, one verdict line per test case")
    p.add_argument("--matrix", default=None, metavar="NAME",
                   help="smoke, quick, full or liveness (default quick)")
    p.add_argument("--cases", nargs="+", default=None,
                   metavar="scenario:harness-executors[:count]",
                   help="run these test cases instead of a matrix")
    p.add_argument("--dry-run", action="store_true",
                   help="build and validate every test case's workflow; start nothing")
    p.add_argument("--config", default=None, metavar="FILE",
                   help="a JSON file that sets model and params per harness executor")
    p.add_argument("--repo", default=None,
                   help="a git repository to run in; the default is a "
                        "throwaway one under --out")
    p.add_argument("--out", default=None,
                   help="where the test cases and matrix.json go")
    p.add_argument("--list", action="store_true",
                   help="print each matrix's test cases and exit")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="stream each run's own lines")
    p.set_defaults(fn=cmd_rollcall)

    p = sub.add_parser("report",
                       help="write exit.json, exit-report.md and "
                            "exit-report.html from a run directory")
    p.add_argument("--run", required=True, help="one ohflow run directory")
    p.set_defaults(fn=cmd_report)

    p = sub.add_parser("cloud-spend",
                       help="read Cloudflare's container meters: a run's cloud "
                            "attempts (--run), or the whole account over a window "
                            "(--since)")
    where = p.add_mutually_exclusive_group(required=True)
    where.add_argument("--run", help="one ohflow run directory; writes cloudflare.json")
    where.add_argument("--since", help="window start, ISO UTC, e.g. 2026-11-14T18:00:00Z")
    p.add_argument("--until", help="window end, ISO UTC; default now")
    p.add_argument("--json", action="store_true", help="print the data as JSON")
    p.set_defaults(fn=cloud_spend.main)
    return ap


def main(argv: list[str] | None = None, harness_executors=None) -> int:
    """Run one command. `harness_executors` is the harness executor resolver for the engines the
    command starts; None takes the registry."""
    use_utf8()
    ns = build_parser().parse_args(argv)
    ns.harness_executors = harness_executors
    try:
        return ns.fn(ns)
    except WorkflowArgMissing as e:
        print(e.message, file=sys.stderr)
        return EXIT_WORKFLOW
    except WorkflowError as e:
        print("WORKFLOW INVALID", file=sys.stderr)
        print(str(e), file=sys.stderr)
        return EXIT_WORKFLOW
    except Exception:
        tail = traceback.format_exc().splitlines()[-TRACEBACK_TAIL_LINES:]
        print("\n".join(tail), file=sys.stderr)
        return EXIT_FAIL


if __name__ == "__main__":
    # Off Windows nothing ends a dead supervisor's children for it, so a
    # terminate or a hangup ends them before it ends this process.
    proc.install_exit_signals()
    sys.exit(main())

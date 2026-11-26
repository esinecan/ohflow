"""The run-summary table, generated from `summary.json` files.

The table in `references/implement-review.md` was kept by hand, and it has
already drifted from the artifacts it describes. This module reads the
artifacts.

Two shapes are read. An `ohflow` summary carries `run_id` and a `phases` map of
phase coordinates. A `legacy` summary is what the retired `implement_review.py` driver wrote: no
run id, and `phases` keyed by the phase name. Both are read because the rows
being replaced are legacy runs, and the only preserved artifacts behind them are
two legacy files.

Three rules keep the table honest, and each has its own test.

1. **A missing measurement renders `-`, never `0`.** No legacy summary carries
   `llm_calls`, and printing zero there would claim a measurement nobody took.
2. **An unpriced cost renders `unpriced`, never `0.00`.** A harness executor
   that cannot price an attempt records `cost_source: "unpriced"`, and a zero in
   a cost column reads as free. A `subscription` attempt is the opposite case:
   its zero is known, so it renders as a number.
3. **Every execution is counted, failed ones included.** An ohflow summary
   embeds each attempt's own numbers, and the row sums all of them. Summing the
   latest result alone would lose what the earlier attempts cost.

Two clocks, named apart. **Agent time** is the sum of each execution's own
seconds. **Elapsed** is the wall time from the run's start to its finish. They
differ by however much ran in parallel, and calling either one "wall" invites
the reader to add them up.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import rundir
from .attempt_record import TOKEN_KEYS, checked_tokens
from .harness_executors import HARNESS_EXECUTORS, harness_executor_module

__all__ = ["MISSING", "UNPRICED", "SUBSCRIPTION", "TOKEN_KEYS", "detect_shape", "discover",
           "load_rows", "reconcile_usage", "render_markdown", "render_json",
           "Row"]

#: What a measurement nobody took looks like.
MISSING = "-"
#: What a cost nobody can price looks like.
UNPRICED = "unpriced"
#: The cost source of an attempt on a subscription login: a known zero, never
#: `unpriced`.
SUBSCRIPTION = "subscription"

#: The run log is the truth of a run. A run directory with no `summary.json`
#: (a run that was killed) is read from it.
_RUN_LOG = "run-log.jsonl"

#: The order the columns appear in, and the key each one reads.
COLUMNS = (
    ("Date", "date"),
    ("Workflow", "workflow"),
    ("Run", "run"),
    ("Row", "label"),
    ("Execs", "executions"),
    ("Agent execs", "agent_executions"),
    ("Tool calls", "tool_calls"),
    ("LLM calls", "llm_calls"),
    ("Prompt tokens", "prompt_tokens"),
    ("Completion tokens", "completion_tokens"),
    ("Cache read", "cache_read_tokens"),
    ("Cache write", "cache_write_tokens"),
    ("Reasoning tokens", "reasoning_tokens"),
    ("Agent time", "agent_time"),
    ("Elapsed", "elapsed"),
    ("Cost", "cost"),
    ("Infra cost", "infra_cost"),
    ("Outcome", "outcome"),
)


class Row(dict):
    """One line of the table. A plain dict, so `--format json` is the same data."""


# ------------------------------------------------------------------ reading


def detect_shape(summary: Any) -> str:
    """`ohflow`, `legacy`, or `unknown`."""
    if not isinstance(summary, dict):
        return "unknown"
    if summary.get("run_id"):
        return "ohflow"
    if isinstance(summary.get("phases"), dict) and "repo" in summary:
        return "legacy"
    return "unknown"


def discover(paths: list[str | Path]) -> list[Path]:
    """Every summary file named by these paths, deduplicated, in a stable order.

    A path may name a file or a directory. A directory is searched for
    `summary.json` and for `*.summary.json`, because the preserved artifacts are
    named `run-1.summary.json` and `run-2.summary.json` and a search for
    `summary.json` alone finds neither.

    A run directory that holds a run log and no `summary.json` is named by its
    run log. `_load` computes the summary from it, so a run that was killed
    still has rows.

    The search goes three levels down and no further. A runs root holds run
    directories one level down, and a shim run's `--out` holds
    `ohflow/<run id>/summary.json` two levels down. Deeper than that is a tree
    nobody meant to hand to this command.
    """
    found: dict[Path, None] = {}
    for raw in paths:
        p = Path(raw)
        if p.is_file():
            found[p.resolve()] = None
            continue
        if not p.is_dir():
            continue
        for pattern in ("summary.json", "*.summary.json",
                        "*/summary.json", "*/*.summary.json",
                        "*/*/summary.json", "*/*/*.summary.json"):
            for hit in sorted(p.glob(pattern)):
                found[hit.resolve()] = None
        for pattern in (_RUN_LOG, f"*/{_RUN_LOG}", f"*/*/{_RUN_LOG}"):
            for hit in sorted(p.glob(pattern)):
                if not (hit.parent / "summary.json").exists():
                    found[hit.resolve()] = None
    return list(found)


def _load(path: Path) -> tuple[Any, str | None]:
    if path.name == _RUN_LOG:
        try:
            return rundir.open_run(path.parent).summary(git=False), None
        except (OSError, ValueError) as e:
            return None, f"{path}: {e}"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except json.JSONDecodeError as e:
        return None, f"{path}: {e}"
    except OSError as e:
        return None, f"{path}: {e}"


# ---------------------------------------------------------------- summing


def _add(total: Any, value: Any) -> Any:
    """Sum that keeps a missing measurement missing.

    A row whose parts are `3`, `None`, `4` is not `7`. One of its executions
    never reported the number, so the row cannot claim a total.
    """
    if value is None:
        return None
    if total is None:
        return None
    return total + value


def _tokens(entry: dict, key: str):
    tokens = entry.get("tokens")
    if not isinstance(tokens, dict):
        return None
    return tokens.get(key)


def _cost(entries: list[dict]) -> str:
    """`unpriced` whenever any execution says so, a number only when every one
    of them carried a real price. A `subscription` zero is a real price."""
    if not entries:
        return MISSING
    if any(e.get("cost_source") == UNPRICED for e in entries):
        return UNPRICED
    values = [e.get("cost") for e in entries]
    if any(v is None for v in values):
        return MISSING
    return f"{sum(values):.4f}"


def _fold(entries: list[dict]) -> dict:
    """Sum a list of executions into the numeric half of a row.

    Only agent executions carry agent metrics. A command, a merge and a bare
    gate produce none, and reading their empty numbers as missing measurements
    would make a whole phase's usage unknown although every agent in it was
    measured. They are counted as executions and left out of the sums.

    An agent execution that produced no numbers is a different thing: it
    crashed before writing them, and its row's totals stay unknown.
    """
    agents = [e for e in entries if e.get("kind", "agent") == "agent"]
    counted = len(agents)
    # An execution that a reattach continued measured nothing of its own: the
    # attempt's numbers are on the execution that finished it.
    agents = [e for e in agents if not e.get("continued")]
    out: dict[str, Any] = {
        "executions": len(entries),
        "agent_executions": counted,
        "tool_calls": 0, "llm_calls": 0,
        "prompt_tokens": 0, "completion_tokens": 0,
        "cache_read_tokens": 0, "cache_write_tokens": 0,
        "reasoning_tokens": 0, "agent_time": 0.0,
    }
    for e in agents:
        out["tool_calls"] = _add(out["tool_calls"], e.get("tool_calls"))
        out["llm_calls"] = _add(out["llm_calls"], e.get("llm_calls"))
        out["prompt_tokens"] = _add(out["prompt_tokens"],
                                    _tokens(e, "prompt_tokens"))
        out["completion_tokens"] = _add(out["completion_tokens"],
                                        _tokens(e, "completion_tokens"))
        for key in ("cache_read_tokens", "cache_write_tokens", "reasoning_tokens"):
            out[key] = _add(out[key], _tokens(e, key))
        out["agent_time"] = _add(out["agent_time"], e.get("wall_seconds"))
    out["cost"] = _cost(agents)
    infra = [e.get("infra_cost") for e in agents
             if isinstance(e.get("infra_cost"), (int, float))]
    out["infra_cost"] = f"{sum(infra):.4f}" if infra else MISSING
    return out


def _minutes(seconds: Any) -> str:
    if seconds is None:
        return MISSING
    return f"{seconds / 60:.1f} min"


def _elapsed(summary: dict) -> str:
    import datetime as dt
    started, finished = summary.get("started"), summary.get("finished")
    if not (started and finished):
        return MISSING
    try:
        a = dt.datetime.strptime(started, "%Y-%m-%dT%H:%M:%SZ")
        b = dt.datetime.strptime(finished, "%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        return MISSING
    return _minutes((b - a).total_seconds())


# ------------------------------------------------------------------- rows


def _ohflow_rows(summary: dict, run: str, by: str) -> list[Row]:
    date = (summary.get("started") or "")[:10] or "unknown"
    workflow = summary.get("workflow") or MISSING
    elapsed = _elapsed(summary)
    steps = rundir.walk_summary(summary)

    def row(label: str, group: list[rundir.SummaryStep]) -> Row:
        entries: list[dict] = []
        for item in group:
            entries.extend(item.executions)
        verdicts = sorted({str(item.step.get("status")) for item in group})
        r = Row(date=date, workflow=workflow, run=run, label=label,
                outcome=", ".join(verdicts) or MISSING,
                elapsed=elapsed if by == "run" else MISSING)
        r.update(_fold(entries))
        return r

    if by == "run":
        return [row(summary.get("status") or "run", steps)]
    if by == "phase":
        out = []
        for pc in sorted({item.phase for item in steps}):
            out.append(row(pc, [t for t in steps if t.phase == pc]))
        return out
    return [row(item.coord, [item]) for item in steps]


def _legacy_run_name(path: Path, summary: dict) -> str:
    """What to call a legacy run.

    A legacy summary carries no run id. `run-1.summary.json` and
    `run-2.summary.json` sit in one directory, so the parent directory name
    would give both the same label and the rows would be unreadable. The file
    stem names them apart.
    """
    twin = (summary.get("ohflow_run") or {}).get("run_id")
    if twin:
        return str(twin)
    name = path.name
    if name == "summary.json":
        return path.parent.name
    return name[:-len(".summary.json")] if name.endswith(".summary.json") \
        else path.stem


def _legacy_rows(summary: dict, run: str, by: str) -> list[Row]:
    # A legacy summary records no date. Its file's modification time is when it
    # was last copied, not when the run happened, so it is not used.
    workflow = summary.get("branch") or MISSING
    phases = summary.get("phases") or {}

    def entry_of(name: str, block: dict) -> dict:
        """One legacy phase, read as if it were a single execution."""
        gate = block.get("gate") or {}
        return {
            "attempt": 1,
            "status": ("skipped" if block.get("skipped")
                       else "resumed" if block.get("resumed")
                       else "passed" if gate.get("passed") else "failed"),
            "tool_calls": block.get("tool_calls"),
            # A legacy summary never carried this one.
            "llm_calls": None,
            "wall_seconds": block.get("wall_seconds"),
            "tokens": block.get("tokens"),
            "cost": None, "cost_source": None,
            "kind": "agent",
            "verdict": gate.get("E2a_verdict"),
        }

    def row(label: str, names: list[str]) -> Row:
        entries = [entry_of(n, phases[n]) for n in names]
        verdicts = []
        for n in names:
            e = entry_of(n, phases[n])
            verdicts.append(f"{e['status']}"
                            + (f" {e['verdict']}" if e.get("verdict") else ""))
        r = Row(date="unknown", workflow=workflow, run=run, label=label,
                outcome=", ".join(verdicts) or MISSING, elapsed=MISSING)
        r.update(_fold(entries))
        # A legacy phase block is one record, not one execution: nothing says
        # how many times its agent ran.
        r["executions"] = MISSING
        r["agent_executions"] = MISSING
        return r

    names = list(phases)
    if by == "run":
        return [row("all phases", names)]
    return [row(n, [n]) for n in names]


def load_rows(paths: list[str | Path], *, by: str = "phase"
              ) -> tuple[list[Row], list[str]]:
    """Every row these paths produce, plus one line per file that could not be
    read. A malformed file skips its row and never stops the others."""
    rows: list[Row] = []
    problems: list[str] = []
    native_runs: set[str] = set()
    pending: list[tuple[Path, dict, str]] = []

    for path in discover(paths):
        summary, problem = _load(path)
        if problem:
            problems.append(problem)
            continue
        shape = detect_shape(summary)
        if shape == "unknown":
            problems.append(f"{path}: not an ohflow or a legacy summary.json")
            continue
        if shape == "ohflow":
            native_runs.add(str(summary.get("run_id")))
        pending.append((path, summary, shape))

    for path, summary, shape in pending:
        if shape == "legacy":
            # A shim run writes both shapes. The legacy one names the ohflow
            # run it came from, and the native one carries every attempt, so
            # the native one wins and this projection is dropped.
            twin = (summary.get("ohflow_run") or {}).get("run_id")
            if twin and twin in native_runs:
                continue
            rows.extend(_legacy_rows(summary, _legacy_run_name(path, summary),
                                     by))
        else:
            rows.extend(_ohflow_rows(summary, str(summary.get("run_id")), by))

    rows.sort(key=lambda r: (r["date"], r["run"], r["label"]))
    return rows, problems


# -------------------------------------------------------- usage reconciliation


def _json_file(path: Path) -> tuple[Any, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, f"{path}: file is missing"
    except (OSError, json.JSONDecodeError) as error:
        return None, f"{path}: cannot read JSON ({error})"


def _path(raw: Any, *anchors: Path) -> Path | None:
    if not isinstance(raw, (str, Path)) or not str(raw):
        return None
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate
    for anchor in anchors:
        hit = anchor / candidate
        if hit.exists():
            return hit
    return (anchors[0] / candidate) if anchors else candidate


def _attempt_dir(entry: dict, step: dict, summary_path: Path) -> Path | None:
    run_dir = summary_path.parent
    raw = entry.get("dir") or step.get("dir")
    hit = _path(raw, run_dir, summary_path.parent.parent)
    if hit:
        return hit
    number = entry.get("attempt")
    step_root = _path(step.get("dir"), run_dir)
    if step_root and isinstance(number, int):
        return rundir.attempt_in(step_root, number)
    return None


def _harness_executor(summary: dict, step: dict, entry: dict, result: dict,
                      spec: dict) -> str | None:
    # The attempt's spec/result is authoritative.  A run summary can combine
    # attempts of several harness executors, so its top-level args are only a
    # last-resort compatibility hint.
    for source in (spec, result, entry, step, summary.get("args"), summary):
        if isinstance(source, dict):
            value = source.get("harness_executor")
            if isinstance(value, str) and value.lower() in HARNESS_EXECUTORS:
                return value.lower()
    return None


def _reconcile_summary(path: Path, summary: dict) -> list[str]:
    problems: list[str] = []
    run_id = str(summary.get("run_id") or path.parent.name)
    for item in rundir.walk_summary(summary):
        coordinate, step, entries = item.coord, item.step, item.executions
        # Command, merge, and gate steps have no provider usage by design.
        if step.get("kind", "agent") != "agent":
            continue
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("started") is False:
                continue
            attempt = entry.get("attempt", 1)
            label = f"{run_id}:{coordinate} attempt {attempt}"
            attempt_dir = _attempt_dir(entry, step, path)
            if attempt_dir is None:
                problems.append(f"{label}: attempt directory is missing")
                continue
            result_path = attempt_dir / "result.json"
            result, problem = _json_file(result_path)
            if problem:
                problems.append(f"{label}: {problem}")
                continue
            result_tokens, problem = checked_tokens(
                result.get("tokens") if isinstance(result, dict) else None,
                f"{label} result.json")
            if problem:
                problems.append(problem)
                continue
            spec, _spec_problem = _json_file(attempt_dir / "spec.json")
            harness_executor = _harness_executor(summary, step, entry, result,
                                                 spec if isinstance(spec, dict) else {})
            if harness_executor is None:
                problems.append(f"{label}: cannot determine the harness executor")
                continue
            usage, problem = harness_executor_module(harness_executor).usage(attempt_dir)
            if problem:
                problems.append(f"{label}: {problem}")
                continue
            if usage != result_tokens:
                problems.append(
                    f"TOKEN MISMATCH {label}: result={json.dumps(result_tokens, sort_keys=True)} "
                    f"usage={json.dumps(usage, sort_keys=True)}")
    return problems


def reconcile_usage(paths: list[str | Path]) -> list[str]:
    """Compare every real agent result with its usage records its harness executor owns.

    The returned strings are suitable for CLI diagnostics.  Missing or
    malformed usage records are errors: a reconciliation command must not quietly
    accept an unmeasured agent.
    """
    problems: list[str] = []
    for path in discover(paths):
        summary, problem = _load(path)
        if problem:
            problems.append(problem)
            continue
        if detect_shape(summary) != "ohflow":
            continue
        problems.extend(_reconcile_summary(path, summary))
    return problems


# --------------------------------------------------------------- rendering


def _cell(value: Any, key: str) -> str:
    if value is None:
        return MISSING
    if key == "agent_time":
        return _minutes(value)
    return str(value)


def render_markdown(rows: list[Row]) -> str:
    head = "| " + " | ".join(name for name, _k in COLUMNS) + " |"
    rule = "|" + "|".join("---" for _c in COLUMNS) + "|"
    lines = [head, rule]
    for r in rows:
        lines.append("| " + " | ".join(_cell(r.get(k), k)
                                       for _name, k in COLUMNS) + " |")
    return "\n".join(lines) + "\n"


def render_json(rows: list[Row]) -> str:
    return json.dumps(rows, indent=2, sort_keys=True) + "\n"

"""`ohflow compare`: a rule-based diff of two runs, for the orchestrator.

One call answers the question about two runs: which steps ended differently,
what changed in their definition, and what each run spent. The rules are fixed,
so the same two run directories always give the same output. An LLM comparison
stays an agent step that reads this output.

Rules this module keeps, and why:

* **Steps pair by step id.** A step that moved
  to another phase keeps its pair, and the move is reported as a `coord` change.
* **It reports what each run recorded.** Status, failure class and retry
  decision come from the run log and the summary; nothing is classified again.
* **Sums follow `table`'s rules.** A missing measurement prints `-` and an
  unpriced cost prints `unpriced`, so a gap never reads as zero.
* **Every side carries its evidence**: the `run-log.jsonl` line of its final
  `attempt_finished`, or `summary.json` for a run read from its summary.
* **The output is bounded**, with the caps `explain` uses.

The spec is `docs/history/orchestrator-visibility.md`, "Utility 4".
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from . import dashboard_data as ohdata
from . import live, rundir, table
from .activity import one_line

__all__ = ["SCHEMA", "LINE_CAP", "TEXT_CAP", "CUT_LINE", "RULES",
           "compare_data", "render", "cap_text"]

SCHEMA = "ohflow.compare/1"
LINE_CAP = 300
TEXT_CAP = 6000
CUT_LINE = f"... cut at {TEXT_CAP} characters; --json carries every field"
#: A definition string longer than this reports its length, not its text.
LONG_STRING = 80
#: The rules, in print order.
RULES = ("coord", "status", "attempts", "failure", "gate", "retry",
         "definition", "fingerprint")
_RUN_LOG = "run-log.jsonl"
_SUMMARY = "summary.json"


# ------------------------------------------------------------------ reading


class _Run:
    """One side of the comparison: its summary, run log lines and definitions."""

    def __init__(self, run_dir: Path, summary: dict, source: str,
                 finished_at: dict[tuple[str, int], tuple[int, dict]]):
        self.dir = run_dir
        self.summary = summary
        self.source = source
        #: `(coord, attempt)` -> (run log line, `attempt_finished` payload).
        self.finished_at = finished_at
        self.definitions = _definitions(run_dir / "workflow.json")


def _open(run_dir: Path) -> _Run | None:
    """A run read from its run log, else from its `summary.json`; None for neither."""
    log = run_dir / _RUN_LOG
    if log.is_file():
        try:
            summary = rundir.open_run(run_dir).summary(git=False)
        except (OSError, ValueError):
            return None
        return _Run(run_dir, summary, _RUN_LOG, _finish_lines(log))
    path = run_dir / _SUMMARY
    if path.is_file():
        try:
            summary = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if table.detect_shape(summary) == "ohflow":
            return _Run(run_dir, summary, _SUMMARY, {})
    return None


def _finish_lines(log: Path) -> dict[tuple[str, int], tuple[int, dict]]:
    """The line and payload of each `attempt_finished`; the last one wins.

    A torn final line is skipped, as the run log reader skips it.
    """
    found: dict[tuple[str, int], tuple[int, dict]] = {}
    with log.open(encoding="utf-8", errors="replace") as fh:
        for number, raw in enumerate(fh, start=1):
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict) and rec.get("event") == "attempt_finished":
                found[(str(rec.get("coord")), rec.get("attempt") or 0)] = (
                    number, rec.get("payload") or {})
    return found


def _definitions(path: Path) -> dict[str, dict] | None:
    """Each step's `workflow.json` entry by step id; None without the file."""
    try:
        workflow = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(workflow, dict):
        return None
    out: dict[str, dict] = {}
    for phase in workflow.get("phases") or []:
        if not isinstance(phase, dict):
            continue
        for step in phase.get("steps") or []:
            if isinstance(step, dict) and step.get("id") is not None:
                out.setdefault(str(step["id"]), step)
    return out


def _step_id(item: rundir.SummaryStep) -> str:
    """The step id: the summary's own, else the coordinate's last part."""
    return str(item.step.get("step_id")
               or item.coord.split("/", 1)[-1].split(".", 1)[-1])


# -------------------------------------------------------------------- sides


def _sums(entries: list[dict]) -> dict:
    """`table`'s fold, with prompt and completion tokens added together."""
    folded = table._fold(entries)
    prompt, completion = folded["prompt_tokens"], folded["completion_tokens"]
    return {"executions": folded["executions"],
            "agent_time_s": folded["agent_time"],
            "tokens": (None if prompt is None or completion is None
                       else prompt + completion),
            "tool_calls": folded["tool_calls"],
            "cost": folded["cost"]}


def _gate_checks(gate: Any) -> list[dict]:
    if not isinstance(gate, dict):
        return []
    return [{"name": str(c.get("name")), "passed": bool(c.get("passed")),
             "observed": c.get("observed")}
            for c in gate.get("checks") or [] if isinstance(c, dict)]


def _side(run: _Run, item: rundir.SummaryStep) -> dict:
    entries = item.executions
    final = entries[-1] if entries else {}
    number = final.get("attempt") if isinstance(final.get("attempt"), int) \
        else item.step.get("attempt")
    line, payload = run.finished_at.get((item.coord, number or 0), (None, {}))
    if run.source == _RUN_LOG and line is not None:
        evidence = {"path": _RUN_LOG, "line": line}
    else:
        evidence = {"path": run.source, "line": None}
    gate = payload.get("gate") if isinstance(payload.get("gate"), dict) \
        else item.step.get("gate")
    return {
        "coord": item.coord,
        "status": item.step.get("status"),
        "attempts": [e.get("status") for e in entries],
        "failure_class": final.get("failure_class")
        or payload.get("failure_class"),
        "transient_signature": payload.get("transient_signature"),
        "retry_decision": final.get("retry_decision"),
        "gate": _gate_checks(gate),
        "fingerprint": item.step.get("fingerprint"),
        "sums": _sums(entries),
        "evidence": evidence,
    }


# -------------------------------------------------------------------- rules


def _flat(obj: Any, prefix: str = "") -> dict[str, Any]:
    """Dotted paths to leaves. A list is one leaf, compared whole."""
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key in sorted(obj):
            out.update(_flat(obj[key], f"{prefix}{key}."))
        return out
    return {prefix[:-1]: obj}


def _leaf(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                      sort_keys=True)


def _definition_change(a: dict | None, b: dict | None) -> list[str]:
    """One phrase per differing dotted path, in path order."""
    if a is None or b is None:
        return []
    fa, fb = _flat(a), _flat(b)
    out = []
    for path in sorted(set(fa) | set(fb)):
        va, vb = fa.get(path), fb.get(path)
        if va == vb:
            continue
        if any(isinstance(v, str) and len(v) > LONG_STRING for v in (va, vb)):
            la = len(va) if isinstance(va, str) else 0
            lb = len(vb) if isinstance(vb, str) else 0
            out.append(f"{path} {la} -> {lb} chars")
        else:
            out.append(f"{path} {_leaf(va)} -> {_leaf(vb)}")
    return out


def _gate_change(a: list[dict], b: list[dict]) -> list[str]:
    by_a = {c["name"]: c for c in a}
    by_b = {c["name"]: c for c in b}
    names = [c["name"] for c in a] + [c["name"] for c in b
                                      if c["name"] not in by_a]
    out = []
    for name in names:
        ca, cb = by_a.get(name), by_b.get(name)
        if ca is None or cb is None:
            only = "A" if cb is None else "B"
            there = ca or cb
            out.append(f"{name} only in {only} "
                       f"({'passed' if there['passed'] else 'failed'})")
            continue
        if ca["passed"] == cb["passed"]:
            continue
        failing = cb if not cb["passed"] else ca
        out.append(f"{name} {'passed' if ca['passed'] else 'failed'} -> "
                   f"{'passed' if cb['passed'] else 'failed'} "
                   f"(observed {_leaf(failing.get('observed'))})")
    return out


def _failure(side: dict) -> str | None:
    cls = side.get("failure_class")
    if not cls:
        return None
    sig = side.get("transient_signature")
    return f"{cls}: {sig}" if sig else str(cls)


def _changes(a: dict, b: dict, def_a: dict | None,
             def_b: dict | None) -> list[dict]:
    """Every rule that fires for a pair, in `RULES` order."""
    out: list[dict] = []

    def fire(rule: str, va: Any, vb: Any, text: str | None = None) -> None:
        out.append({"rule": rule, "a": va, "b": vb,
                    "text": text or f"{_leaf(va)} -> {_leaf(vb)}"})

    if a["coord"] != b["coord"]:
        fire("coord", a["coord"], b["coord"])
    if a["status"] != b["status"]:
        fire("status", a["status"], b["status"])
    if a["attempts"] != b["attempts"]:
        fire("attempts", a["attempts"], b["attempts"],
             f"{', '.join(map(_leaf, a['attempts'])) or '-'} -> "
             f"{', '.join(map(_leaf, b['attempts'])) or '-'}")
    if _failure(a) != _failure(b):
        fire("failure", _failure(a), _failure(b))
    gate = _gate_change(a["gate"], b["gate"])
    if gate:
        fire("gate", a["gate"], b["gate"], "; ".join(gate))
    if a["retry_decision"] != b["retry_decision"]:
        fire("retry", a["retry_decision"], b["retry_decision"])
    definition = _definition_change(def_a, def_b)
    if definition:
        fire("definition", None, None, "; ".join(definition))
    elif (a["fingerprint"] and b["fingerprint"]
          and a["fingerprint"] != b["fingerprint"]):
        fire("fingerprint", a["fingerprint"], b["fingerprint"],
             f"{str(a['fingerprint'])[:12]} -> {str(b['fingerprint'])[:12]} "
             "(same definition: the base commit or a dependency changed)")
    return out


# --------------------------------------------------------------------- view


def _elapsed(summary: dict) -> float | None:
    started, finished = summary.get("started"), summary.get("finished")
    try:
        a = dt.datetime.strptime(str(started), "%Y-%m-%dT%H:%M:%SZ")
        b = dt.datetime.strptime(str(finished), "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None
    return (b - a).total_seconds()


def _run_view(run: _Run) -> dict:
    s = run.summary
    return {"dir": str(run.dir), "run_id": s.get("run_id"),
            "workflow": s.get("workflow"), "status": s.get("status"),
            "started": s.get("started"), "finished": s.get("finished"),
            "elapsed_s": _elapsed(s), "base_sha": s.get("base_sha"),
            "source": run.source}


def _totals(steps: list[rundir.SummaryStep]) -> dict:
    by_status: dict[str, int] = {}
    entries: list[dict] = []
    for item in steps:
        status = str(item.step.get("status"))
        by_status[status] = by_status.get(status, 0) + 1
        entries.extend(item.executions)
    return {"steps": dict(sorted(by_status.items())), **_sums(entries)}


def _definition(run: _Run, sid: str) -> dict | None:
    return None if run.definitions is None else run.definitions.get(sid)


def compare_data(run_a: Path, run_b: Path) -> dict:
    """The comparison of two runs.

    Raises `LookupError` with a one-line message naming a directory that is
    not a run.
    """
    runs = []
    for raw in (run_a, run_b):
        run_dir = Path(raw)
        run = _open(run_dir)
        if run is None:
            raise LookupError(f"no ohflow run at {run_dir}")
        runs.append(run)
    a, b = runs
    walk_a = rundir.walk_summary(a.summary)
    walk_b = rundir.walk_summary(b.summary)
    ids_a = {_step_id(i): i for i in walk_a}
    ids_b = {_step_id(i): i for i in walk_b}

    steps: list[dict] = []
    for sid, item in ids_a.items():
        side_a = _side(a, item)
        other = ids_b.get(sid)
        side_b = _side(b, other) if other is not None else None
        changes = [] if side_b is None else _changes(
            side_a, side_b, _definition(a, sid), _definition(b, sid))
        steps.append({"id": sid, "a": side_a, "b": side_b, "changes": changes})
    for sid, item in ids_b.items():
        if sid not in ids_a:
            steps.append({"id": sid, "a": None, "b": _side(b, item),
                          "changes": []})

    view = {
        "schema": SCHEMA,
        "runs": {"a": _run_view(a), "b": _run_view(b)},
        "totals": {"a": _totals(walk_a), "b": _totals(walk_b)},
        "steps": steps,
    }
    return live._redact_tree(ohdata._cap_tree(view, ohdata.STRING_CAP))


# ------------------------------------------------------------------ text


def _fit(text: str, suffix: str = "", indent: str = "") -> str:
    """One line of at most LINE_CAP characters; the suffix is never cut."""
    tail = f" · {suffix}" if suffix else ""
    room = max(20, LINE_CAP - len(indent) - len(tail))
    return indent + one_line(str(text), room) + tail


def _seconds(value: Any) -> str:
    if value is None:
        return table.MISSING
    value = float(value)
    return f"{value:.1f} s" if value < 120 else f"{value / 60:.1f} min"


def _num(value: Any) -> str:
    return table.MISSING if value is None else str(value)


def _pair(name: str, a: Any, b: Any, fmt=_num) -> str:
    return f"{name} {fmt(a)} -> {fmt(b)}"


def _ev(side: dict | None, label: str) -> str:
    if not side:
        return ""
    ev = side["evidence"]
    return f"{label} {ev['path']}:{ev['line']}" if ev.get("line") \
        else f"{label} {ev['path']}"


def _statuses(steps: dict) -> str:
    return ", ".join(f"{k} {v}" for k, v in steps.items()) or "none"


def render(view: dict) -> list[str]:
    """The text lines of one comparison, capped by `cap_text`."""
    ra, rb = view["runs"]["a"], view["runs"]["b"]
    steps = view["steps"]
    paired = [s for s in steps if s["a"] and s["b"]]
    differ = sum(1 for s in paired if s["changes"])
    only_a = sum(1 for s in steps if s["b"] is None)
    only_b = sum(1 for s in steps if s["a"] is None)
    lines = [_fit(f"COMPARE {ra['run_id']} -> {rb['run_id']}: "
                  f"{len(paired)} paired, {differ} differ, {only_a} only in A, "
                  f"{only_b} only in B")]
    for label, r in (("A", ra), ("B", rb)):
        base = f" · base {str(r['base_sha'])[:10]}" if r.get("base_sha") else ""
        lines.append(_fit(f"{label}: {r['workflow']} {r['status']} · elapsed "
                          f"{_seconds(r['elapsed_s'])}{base}", r["dir"]))
    ta, tb = view["totals"]["a"], view["totals"]["b"]
    lines.append(_fit(" · ".join([
        f"totals: steps {_statuses(ta['steps'])} -> {_statuses(tb['steps'])}",
        _pair("executions", ta["executions"], tb["executions"]),
        _pair("agent time", ta["agent_time_s"], tb["agent_time_s"], _seconds),
        _pair("tokens", ta["tokens"], tb["tokens"]),
        _pair("tool calls", ta["tool_calls"], tb["tool_calls"]),
        _pair("cost", ta["cost"], tb["cost"])])))
    for step in steps:
        lines += _step_lines(step)
    return cap_text(lines)


def _step_lines(step: dict) -> list[str]:
    a, b = step["a"], step["b"]
    if a and b:
        sa, sb = a["sums"], b["sums"]
        text = " · ".join([
            f"step {step['id']}: {a['status']} -> {b['status']}",
            _pair("attempts", len(a["attempts"]), len(b["attempts"])),
            _pair("agent time", sa["agent_time_s"], sb["agent_time_s"],
                  _seconds),
            _pair("tokens", sa["tokens"], sb["tokens"]),
            _pair("tool calls", sa["tool_calls"], sb["tool_calls"])])
        lines = [_fit(text, f"{_ev(a, 'A')} · {_ev(b, 'B')}")]
        lines += [_fit(f"{c['rule']}: {c['text']}", indent="  ")
                  for c in step["changes"]]
        return lines
    side, label = (a, "A") if a else (b, "B")
    s = side["sums"]
    text = " · ".join([
        f"step {step['id']}: only in {label} ({side['coord']})",
        str(side["status"]), f"attempts {len(side['attempts'])}",
        f"agent time {_seconds(s['agent_time_s'])}",
        f"tokens {_num(s['tokens'])}", f"tool calls {_num(s['tool_calls'])}"])
    return [_fit(text, _ev(side, label))]


def cap_text(lines: list[str]) -> list[str]:
    """At most TEXT_CAP characters joined; a cut text ends with CUT_LINE."""
    total = len("\n".join(lines))
    if total <= TEXT_CAP:
        return lines
    out: list[str] = []
    size = len(CUT_LINE)
    for line in lines:
        if size + len(line) + 1 > TEXT_CAP:
            break
        out.append(line)
        size += len(line) + 1
    return out + [CUT_LINE]

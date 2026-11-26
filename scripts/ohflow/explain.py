"""`ohflow explain`: the step inspector as bounded text, for the orchestrator.

One call answers the triage question about one attempt of one step: why it
failed, whether the engine called the fault transient or structural, what the
engine decided about a retry, and what waits on a person. The dashboard's
inspector shows the same facts to a human; this module reads them from the run
directory, so it works whether or not a dashboard serves.

Rules this module keeps, and why:

* **It reports what the engine recorded.** The failure class and the retry
  decision come from the run log. `explain` never classifies again, because a
  second opinion would not be what the engine acted on.
* **The execution error comes first.** When a stall, a kill or the execution
  timeout ended the attempt, the gates fail because the attempt stopped, so
  the `cause:` line names the error and the failed checks follow it.
* **A message is final only when the agent completed its answer.** A stopped
  attempt leaves its last intermediate message in `final.md`, and `explain`
  prints it as an interrupted last message.
* **Every claim carries its evidence**: a `run-log.jsonl` line, or a path
  relative to the run directory.
* **The output is bounded.** Each text line is at most `LINE_CAP` characters
  and the whole text at most `TEXT_CAP`; `--json` strings pass the dashboard's
  `_cap_tree` and redaction.

The spec is `docs/history/orchestrator-visibility.md`, "Utility 2".
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from . import dashboard_data as ohdata
from . import live, rundir, tool_output
from .activity import one_line

__all__ = ["SCHEMA", "LINE_CAP", "TEXT_CAP", "explain_data", "resolve_step",
           "render", "cap_text"]

SCHEMA = "ohflow.explain/1"
LINE_CAP = 300
TEXT_CAP = 6000
#: Attempt rows shown, newest kept.
MAX_ATTEMPTS = 10
#: Lines of the newest tool call's output.
TAIL_LINES = 10
#: Recent tool calls from the harness executor's activity block.
RECENT_TOOLS = 5
CUT_LINE = f"... cut at {TEXT_CAP} characters; --json carries every field"
NOTHING_NEXT = "next: nothing waits on a person for this step"


def explain_data(run_dir: Path, step: str, attempt: int | None = None,
                 now: float | None = None) -> dict | None:
    """The explain view of one attempt. None for a directory that is not a run.

    Raises `LookupError` with a one-line message when the step is missing or
    ambiguous, or has no recorded attempt with that number.
    """
    now = time.time() if now is None else float(now)
    run_dir = Path(run_dir)
    source = ohdata.open_source(run_dir)
    if source is None or source.kind != "run":
        return None
    coord = resolve_step(source, step)
    invocations = source.invocations(now)
    mine = [inv for inv in invocations if inv["coord"] == coord]
    if attempt is None:
        inv = max(mine, key=lambda i: i["attempt"]) if mine else None
    else:
        inv = next((i for i in mine if i["attempt"] == int(attempt)), None)
    if inv is None:
        tail = f" {int(attempt)}" if attempt is not None else ""
        raise LookupError(f"step {coord} has no recorded attempt{tail}")
    n = inv["attempt"]
    steps = source.steps(now)
    step_row = next(s for s in steps if s["coord"] == coord)
    payload = (source.run.finishes.get((coord, n)) or {}).get("payload") or {}
    view = {
        "schema": SCHEMA,
        "run": {"dir": str(run_dir), "status": source.run.status},
        "step": {k: step_row.get(k) for k in
                 ("coord", "id", "role", "harness_executor", "phase", "kind",
                  "status", "reason")},
        "attempt": _attempt(source, inv, payload),
        "attempts": [_attempt_row(source, i) for i in
                     sorted(mine, key=lambda i: i["attempt"])][-MAX_ATTEMPTS:],
        "gate": _gate(source, coord, n),
        "handover": _handover(source, coord, n, payload),
        "final": _final(source, inv, payload),
        "tool_output": _tool_output(run_dir, coord, n, now, inv),
        "activity": _activity(run_dir, coord, n, now),
        "next": _next(source.attention(now, steps, invocations), coord),
    }
    return live._redact_tree(ohdata._cap_tree(view, ohdata.STRING_CAP))


def resolve_step(source, requested: str) -> str:
    """A full coordinate first, then a unique step id, as `transcript` does."""
    raw_steps = source.model()["raw_steps"]
    if any(s["coord"] == requested for s in raw_steps):
        return requested
    matches = [s["coord"] for s in raw_steps if s["id"] == requested]
    if len(matches) != 1:
        raise LookupError(f"step {requested!r} is missing or ambiguous")
    return matches[0]


def _line_of(source, event: str, coord: str, attempt: int) -> dict | None:
    for entry in reversed(source.entries):
        rec = entry["rec"]
        if (rec.get("event") == event and rec.get("coord") == coord
                and rec.get("attempt") == attempt):
            return {"path": "run-log.jsonl", "line": entry["line"]}
    return None


def _decision(source, inv: dict) -> tuple[str | None, dict | None]:
    """The retry decision the engine recorded on this attempt, with its line."""
    where = _line_of(source, "retry_decided", inv["coord"], inv["attempt"])
    decision = inv.get("retry_decision")
    if decision is None and where is not None:
        rec = source.entries[where["line"] - 1]["rec"]
        decision = (rec.get("payload") or {}).get("retry_decision")
    return decision, where


def _attempt(source, inv: dict, payload: dict) -> dict:
    coord, n = inv["coord"], inv["attempt"]
    decision, decision_at = _decision(source, inv)
    evidence = (_line_of(source, "attempt_finished", coord, n)
                or _line_of(source, "attempt_started", coord, n))
    return {
        "attempt": n, "status": inv["status"], "launch": inv.get("launch"),
        "started": inv.get("started"), "finished": inv.get("finished"),
        "wall_s": inv.get("wall_s"),
        "cause": inv.get("cause"), "short_cause": inv.get("short_cause"),
        "error": inv.get("error"),
        "failure_class": payload.get("failure_class"),
        "transient_signature": payload.get("transient_signature"),
        "retry_decision": decision,
        "evidence": evidence, "decision_evidence": decision_at,
    }


def _attempt_row(source, inv: dict) -> dict:
    decision, _where = _decision(source, inv)
    coord, n = inv["coord"], inv["attempt"]
    payload = (source.run.finishes.get((coord, n)) or {}).get("payload") or {}
    return {"attempt": n, "status": inv["status"],
            "short_cause": inv.get("short_cause"),
            "error": inv.get("error"),
            "transient_signature": payload.get("transient_signature"),
            "retry_decision": decision,
            "evidence": (_line_of(source, "attempt_finished", coord, n)
                         or _line_of(source, "attempt_started", coord, n))}


def _gate(source, coord: str, n: int) -> dict | None:
    found = source.gate_evidence(coord, n)
    gate = found.get("gate")
    if not isinstance(gate, dict):
        return None
    checks = [{"name": str(c.get("name")), "passed": bool(c.get("passed")),
               "observed": c.get("observed"), "expected": c.get("expected"),
               "detail": c.get("detail")}
              for c in gate.get("checks") or [] if isinstance(c, dict)]
    return {"passed": bool(gate.get("passed")), "source": found.get("source"),
            "checks": checks}


def _handover(source, coord: str, n: int, payload: dict) -> dict | None:
    first = source._handover_line(coord, n, payload)
    if first is None:
        return None
    return {"first_line": first, "path": payload.get("handover_path")}


def _final(source, inv: dict, payload: dict) -> dict | None:
    coord, n = inv["coord"], inv["attempt"]
    first = source._final_line(coord, n)
    if first is None:
        return None
    adir = rundir.attempt_dir(source.run_dir, coord, n)
    return {"first_line": first,
            "path": ohdata._rel(source.run_dir, adir / "final.md"),
            "completed": _completed(adir, inv, payload)}


def _completed(adir: Path, inv: dict, payload: dict) -> bool:
    """Whether the agent completed its answer, so `final.md` is its final one.

    A runner that recovers a stopped attempt writes the last intermediate
    message to `final.md` and records `execution_status: error`. A command
    step's record has no execution status: its output is complete when the
    command exited.
    """
    if (inv["status"] in ("timeout", "interrupted", "running")
            or payload.get("abort_victim")):
        return False
    try:
        record = json.loads((adir / "result.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        record = None
    if not isinstance(record, dict):
        record = {}
    if "execution_status" in record:
        return (record["execution_status"] == "finished"
                and not record.get("error"))
    return "exit" in record or not payload.get("error")


def _tool_output(run_dir: Path, coord: str, n: int, now: float,
                 inv: dict) -> dict | None:
    adir = rundir.attempt_dir(run_dir, coord, n)
    every = tool_output.calls(adir) if adir.is_dir() else []
    if not every:
        return None
    call = tool_output.current(adir, lines=TAIL_LINES, now=now,
                               ended_at=ohdata.epoch(inv.get("finished")))
    chosen = next((c for c in every if c["id"] == call["id"]), every[-1])
    path = tool_output.output_path(adir, chosen)
    call["file"] = ohdata._rel(Path(run_dir), path) if path else None
    return {"total": len(every), "call": call}


def _activity(run_dir: Path, coord: str, n: int, now: float) -> dict | None:
    if n < 1:
        return None
    block = live.activity(run_dir, coord, n, limit=RECENT_TOOLS, now=now)
    act = (block or {}).get("activity") or {}
    if "mechanical" in act:
        mech = act["mechanical"]
        return {"kind": "mechanical", "command": mech.get("command"),
                "log": mech.get("log"),
                "log_tail": (mech.get("log_tail") or [])[-TAIL_LINES:]}
    if not act:
        return None
    reasoning = act.get("latest_reasoning") or {}
    return {
        "kind": "agent",
        "tool_calls_total": act.get("tool_calls_total"),
        "running_tool": act.get("running_tool"),
        "tool_calls": [{"name": c.get("name"), "summary": c.get("summary"),
                        "ok": c.get("ok"), "pending": c.get("pending"),
                        "first_line": c.get("first_line")}
                       for c in (act.get("tool_calls") or [])[:RECENT_TOOLS]],
        "reasoning": reasoning.get("text"),
        "last_error": act.get("last_error"),
    }


def _next(items: list[dict], coord: str) -> list[dict]:
    """The attention items of this step, and those of the run as a whole."""
    return [{"group": i["group"], "kind": i["kind"], "coord": i["coord"],
             "observed": (i.get("observed") or {}).get("text"),
             "command": (i.get("next") or {}).get("command"),
             "text": (i.get("next") or {}).get("text"),
             "evidence": _run_log_line(i.get("evidence"))}
            for i in items if i.get("coord") in (coord, None)]


def _run_log_line(evidence: dict | None) -> dict | None:
    """An attention item's evidence, in this module's pointer shape."""
    if not isinstance(evidence, dict) or not evidence.get("line"):
        return None
    return {"path": "run-log.jsonl", "line": evidence["line"]}


# ------------------------------------------------------------------ text


def _ev(evidence: dict | None) -> str:
    if not isinstance(evidence, dict) or not evidence.get("path"):
        return ""
    line = evidence.get("line")
    return f"{evidence['path']}:{line}" if line else str(evidence["path"])


def _fit(text: str, suffix: str = "") -> str:
    """One line of at most LINE_CAP characters; the suffix is never cut."""
    tail = f" · {suffix}" if suffix else ""
    return one_line(str(text), max(20, LINE_CAP - len(tail))) + tail


def _value(value) -> str:
    """A gate's observed or expected value: JSON for a list or a mapping."""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _quoted(prefix: str, text: str) -> str:
    """A line of recorded output, indentation kept, cut to LINE_CAP."""
    body = str(text).replace("\t", "    ").rstrip()
    room = LINE_CAP - len(prefix)
    return prefix + (body if len(body) <= room else body[:room - 1] + "…")


def _attempt_head(view: dict) -> str:
    a = view["attempt"]
    cls = ""
    if a.get("failure_class") and a["status"] not in ("passed", "cached"):
        cls = f", {a['failure_class']}"
        if a.get("transient_signature"):
            cls += f": {a['transient_signature']}"
    decision = a.get("retry_decision") or "no retry decision is recorded"
    return _fit(f"EXPLAIN {view['step']['coord']} attempt {a['attempt']}: "
                f"{a['status']}{cls}; {decision}")


def render(view: dict) -> list[str]:
    """The text lines of one explain view, capped by `cap_text`."""
    s, a = view["step"], view["attempt"]
    lines = [_attempt_head(view)]
    where = (f" ({s['reason']})"
             if s.get("reason") and s["reason"] != s["status"] else "")
    lines.append(_fit(" · ".join(str(x) for x in (
        f"step: {s['id']}", s.get("role"), s.get("harness_executor"),
        f"phase {s['phase']}", f"{s['status']}{where}") if x)))
    error = _execution_error(a)
    if error or a.get("cause"):
        cause = f"execution error: {error}" if error else a["cause"]
        lines.append(_fit(f"cause: {cause}", _ev(a.get("evidence"))))
    failed = ("gate failed after the execution error: " if error
              else "gate failed: ")
    gate = view.get("gate")
    if gate:
        for c in gate["checks"]:
            if c["passed"]:
                continue
            detail = f": {c['detail']}" if c.get("detail") else ""
            lines.append(_fit(f"{failed}{c['name']} (observed "
                              f"{_value(c.get('observed'))}, expected "
                              f"{_value(c.get('expected'))}{detail})",
                              gate.get("source") or ""))
        passed = [c["name"] for c in gate["checks"] if c["passed"]]
        if passed:
            lines.append(_fit("gate passed: " + ", ".join(passed)))
    for row in view["attempts"]:
        cause = row.get("short_cause")
        if row.get("error"):
            cause = row.get("transient_signature") or one_line(row["error"], 80)
        short = f" ({cause})" if cause else ""
        decision = f" · {row['retry_decision']}" if row.get("retry_decision") \
            else ""
        lines.append(_fit(f"attempt {row['attempt']}: {row['status']}{short}"
                          f"{decision}", _ev(row.get("evidence"))))
    if view.get("handover"):
        lines.append(_fit(f"handover: {view['handover']['first_line']}",
                          view["handover"].get("path") or ""))
    if view.get("final"):
        label = ("final" if view["final"].get("completed")
                 else "last message, interrupted")
        lines.append(_fit(f"{label}: {view['final']['first_line']}",
                          view["final"]["path"]))
    lines += _tool_lines(view.get("tool_output"))
    final = (view.get("final") or {}).get("first_line")
    lines += _activity_lines(view.get("activity"), final)
    nexts = [_next_line(item) for item in view["next"]] or [NOTHING_NEXT]
    # The next lines are what a person acts on: a cut takes earlier lines.
    return cap_text(lines, reserve=len("\n".join(nexts)) + 1) + nexts


def _execution_error(a: dict) -> str | None:
    """The error that ended the attempt, as the engine recorded it.

    The execution timeout may stop an attempt with no error text, and its
    `timeout` status is then the record.
    """
    if a.get("error"):
        return str(a["error"])
    if a.get("status") == "timeout":
        return "the execution timeout stopped the attempt"
    return None


def _next_line(item: dict) -> str:
    """One attention item. Its command is never cut, as in `watch`.

    A cut command cannot be run, so the text before it gives way. When the
    command alone fills LINE_CAP, the line runs past the cap.
    """
    command = " ".join(str(item.get("command") or "").split())
    if not command:
        return _fit(f"next: {item['group']} {item['kind']}: "
                    f"{item.get('text') or ''}", _ev(item.get("evidence")))
    head = f"next: {item['group']} {item['kind']}: "
    ev = _ev(item.get("evidence"))
    tail = f" `{command}`" + (f" · {ev}" if ev else "")
    text = one_line(item.get("text") or "", 10_000)
    room = LINE_CAP - len(head) - len(tail)
    if len(text) > room:
        text = text[:room - 1].rstrip() + "…" if room > 1 else ""
    return (head + text + tail) if text else (head + tail.lstrip())


def _tool_lines(out: dict | None) -> list[str]:
    if not out:
        return []
    call = out["call"]
    if call.get("open"):
        state = f"open for {int(call.get('since_s') or 0)} s"
    elif call.get("exit") is not None:
        state = f"exit {call['exit']}"
    else:
        state = "ok" if call.get("ok") else "ended"
    calls = f"{out['total']} call" + ("" if out["total"] == 1 else "s")
    lines = [_fit(f"tool output: `{call.get('command') or call.get('tool')}` "
                  f"{state} ({calls})", call.get("file") or "")]
    lines += [_quoted("  | ", text) for text in call.get("lines") or []]
    return lines


def _activity_lines(act: dict | None, final: str | None) -> list[str]:
    if not act:
        return []
    if act["kind"] == "mechanical":
        lines = [_fit(f"command: {act.get('command')}", act.get("log") or "")]
        return lines + [_quoted("  ~ ", text) for text in act.get("log_tail")
                        or []]
    lines = []
    for c in act.get("tool_calls") or []:
        state = ("pending" if c.get("pending") else
                 "ok" if c.get("ok") else "failed" if c.get("ok") is False
                 else "ended")
        first = f": {c['first_line']}" if c.get("first_line") else ""
        lines.append(_fit(f"tool: {c.get('name')} {c.get('summary') or ''} "
                          f"-> {state}{first}"))
    # The last reasoning is often the final message itself; print it once.
    if act.get("reasoning") and one_line(act["reasoning"], 200) != final:
        lines.append(_fit(f"reasoning: {act['reasoning']}"))
    if act.get("last_error"):
        lines.append(_fit(f"last error: {act['last_error']}"))
    return lines


def cap_text(lines: list[str], reserve: int = 0) -> list[str]:
    """At most TEXT_CAP - reserve characters joined; a cut ends with CUT_LINE.

    `reserve` is the room kept for lines the caller appends after the cut.
    """
    total = len("\n".join(lines))
    if total + reserve <= TEXT_CAP:
        return lines
    out: list[str] = []
    size = len(CUT_LINE) + reserve
    for line in lines:
        if size + len(line) + 1 > TEXT_CAP:
            break
        out.append(line)
        size += len(line) + 1
    return out + [CUT_LINE]

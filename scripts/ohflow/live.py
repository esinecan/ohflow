"""The run as one JSON document, read from files alone.

`read_out(run_dir, now)` is the single producer of what the live dashboard, the
HTML exit report and the Markdown exit report show. The three can therefore
never disagree about a run.

Rules this module keeps, and why:

* **It only reads.** Nothing here writes into a run directory. A viewer that
  wrote would be one more thing a crash could leave half-done.
* **It reads files, never engine objects.** The dashboard thread lives inside
  the supervisor process. Touching `Engine.state` or the engine lock from it
  would couple a viewer to the scheduler it watches, and a slow page could then
  stall a transition. Reading files makes a live run, a finished run and an
  orphaned run one case, which is also what lets `ohflow report` rebuild the
  exit report after a hard kill.
* **The run log is the truth.** No derived file is an input.
* **Every string that leaves passes `redact`.** Tool arguments and results are
  agent-authored text, and an agent that echoed a key must not publish it on a
  page.

Cost control. Every parsed file is cached on `(mtime, size)`. The two
append-only files, `run-log.jsonl` and a pi session, are read from the last
byte offset. A poll every two seconds therefore re-reads only what changed.
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import re
import statistics
import threading
import time
from pathlib import Path
from typing import Any

from . import attempts as ohattempts
from . import estimate as ohestimate
from . import rundir
from .paths import python_cmd
from .activity import (DEFAULT_TOOL_CALLS, FILES, SUMMARY_MAX, TOKEN_FIELDS, Tail,
                       age, epoch, first_line, first_sentence, hms, int_of, iso,
                       one_line, read_json)
from .run_log import RunLog, RunState
from .harness_executors import HARNESS_EXECUTORS, harness_executor_module

__all__ = ["SCHEMA", "read_out", "activity", "eta", "finished_walls",
           "redact", "resume_command", "agent_attempts",
           "DEFAULT_TOOL_CALLS", "MAX_TOOL_CALLS"]

SCHEMA = "ohflow.read-out/2"

#: The most any request may ask for, so one query cannot render a whole session.
MAX_TOOL_CALLS = 200
#: The events feed is the recent past, newest first.
EVENTS_MAX = 60
#: A mechanical step's card shows the end of its newest log.
MECHANICAL_TAIL = 5

#: Idle thresholds when a step sets no `stall_timeout_s` (spec §9).
IDLE_AMBER_S, IDLE_RED_S = 300, 900
#: Run-activity thresholds (spec §9).
RUN_AMBER_S, RUN_RED_S = 300, 600

_TERMINAL = frozenset({"passed", "failed", "timeout", "quarantined",
                       "skipped", "cached", "deferred"})
_GOOD = frozenset({"passed", "cached"})
_RESTART_KINDS = frozenset({"retry", "auto_resume", "resume"})
#: A run whose supervisor is alive and may still start work: the page polls.
_LIVE_RUN = frozenset({"running", rundir.STARTING, rundir.HELD})
#: The reason every step shows while the run waits for `ohflow go`.
HELD_REASON = "held: waiting for go"


# ----------------------------------------------------------------- redaction

#: A secret value. It stops at a quote, a separator or a closing bracket, and
#: it never re-matches a value already masked, which keeps `redact` idempotent.
_VALUE = r"""(?!\[redacted\])[^\s"'&;,|}\]]+"""
_REDACTIONS: tuple[tuple[re.Pattern, Any], ...] = (
    # First the value of any variable whose name ends in _KEY, _TOKEN,
    # _SECRET or _PASSWORD (plus common bare password names), in the shapes a
    # shell, PowerShell or JSON writes it: NAME=v,
    # NAME = 'v', $env:NAME="v", "NAME": "v". It runs before the token shapes,
    # so `KEY="sk-..."` is masked once, as one whole value.
    (re.compile(r"(?i)\b((?:[A-Za-z0-9_]*(?:_KEY|_TOKEN|_SECRET|_PASSWORD)"
                r"|PASSWORD|PASSWD|PWD))\b"
                r"([\"']?\s*[:=]\s*)([\"']?)" + _VALUE),
     r"\1\2\3[redacted]"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}"), "sk-[redacted]"),
    (re.compile(r"\b(?i:bearer)\s+[A-Za-z0-9._~+/=\-]{6,}"),
     "Bearer [redacted]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{10,}"),
     lambda m: m.group(0)[:4] + "[redacted]"),
    (re.compile(r"\bxox[a-z]-[A-Za-z0-9\-]{6,}"),
     lambda m: m.group(0)[:5] + "[redacted]"),
)

# Structured payloads do not necessarily render their key beside their value,
# so the string patterns above cannot protect e.g. ``{"PASSWORD": "..."}``
# after a producer has already separated the two.  Keep this deliberately
# narrower than "contains token": usage fields such as ``input_tokens`` and
# ``max_tokens`` are measurements, not credentials.
_SECRET_FIELD = re.compile(
    r"(?i)^(?:"
    r"password|passwd|pwd|secret|token|key|credential|credentials|"
    r"authorization|proxy_authorization|cookie|set_cookie|"
    r"(?:[a-z0-9]+_)*(?:password|passwd|pwd|secret|token|key)|"
    r"(?:access|refresh|id|auth|bearer)_token"
    r")$")


def redact(text: str) -> str:
    """Mask the secret shapes spec §7.4 names. Idempotent."""
    if not text:
        return text
    for pattern, repl in _REDACTIONS:
        text = pattern.sub(repl, text)
    return text


def _redact_tree(obj: Any) -> Any:
    """Recursively redact strings and values of structured secret fields.

    Keys remain visible so diagnostics retain their shape.  A secret field's
    value is replaced as a unit, including non-string/list values, which also
    makes the operation idempotent.  Token counters such as ``input_tokens``
    deliberately remain meaningful.
    """
    if isinstance(obj, str):
        return redact(obj)
    if isinstance(obj, dict):
        return {
            k: ("[redacted]" if _SECRET_FIELD.fullmatch(str(k))
                else _redact_tree(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact_tree(v) for v in obj]
    return obj




class _RunLogView:
    """The run log's records and their replay, refreshed by offset."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.tail = Tail()
        self.records: list[dict] = []
        self.state = RunState()
        self.unreadable = 0

    def refresh(self, run_dir: Path) -> tuple[list[dict], RunState, int]:
        with self.lock:
            lines, reset = self.tail.read(run_dir / "run-log.jsonl")
            if reset:
                self.records, self.unreadable = [], 0
            if lines or reset:
                for raw in lines:
                    try:
                        rec = json.loads(raw.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        # `RunLog.replay` refuses a corrupt middle line. A
                        # viewer counts it and keeps showing the rest.
                        self.unreadable += 1
                        continue
                    if isinstance(rec, dict):
                        self.records.append(rec)
                self.state = RunLog.replay_records(self.records)
            return list(self.records), self.state, self.unreadable


_VIEWS_LOCK = threading.Lock()
_RUN_LOGS: dict[str, _RunLogView] = {}
_ACTIVITY: dict[str, "Activity"] = {}


def _run_log_view(run_dir: Path) -> _RunLogView:
    key = str(run_dir)
    with _VIEWS_LOCK:
        view = _RUN_LOGS.get(key)
        if view is None:
            if len(_RUN_LOGS) > 256:
                _RUN_LOGS.clear()
            view = _RUN_LOGS[key] = _RunLogView()
        return view



_LIST_ITEM = re.compile(r"^([-*+]|\d+[.)])\s")


def brief_objective(brief: str | None) -> str | None:
    """The first plain sentence of a brief, per spec §8 source 3.

    Skips empty lines, Markdown headings, list items and indented lines, and
    the inside of a code fence, which is not prose either. The paragraph that
    starts at the first surviving line is joined, so a sentence wrapped onto a
    second line is read whole.
    """
    lines = str(brief or "").splitlines()
    fenced = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```"):
            fenced = not fenced
            continue
        if fenced or not stripped or line[:1] in (" ", "\t"):
            continue
        if stripped.startswith("#") or _LIST_ITEM.match(stripped):
            continue
        para = [stripped]
        for nxt in lines[i + 1:]:
            ns = nxt.strip()
            if not ns or ns.startswith(("#", "```")) or _LIST_ITEM.match(ns):
                break
            para.append(ns)
        return first_sentence(" ".join(para), SUMMARY_MAX)
    return None


# ------------------------------------------------------------ harness executor adapters





def _log_tail(path: Path) -> list[str]:
    def parse(p: Path) -> list[str]:
        with p.open("rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - 8192))
            data = fh.read()
        lines = data.decode("utf-8", "replace").splitlines()
        while lines and not lines[-1].strip():
            lines.pop()
        return [one_line(line, 240) for line in lines[-MECHANICAL_TAIL:]]
    return FILES.load(path, parse) or []


def activity_mechanical(attempt_dir: Path, raw_step: dict,
                        run_dir: Path) -> dict:
    """Spec §7.3: the command string and the end of the newest `.out.log`."""
    kind = raw_step.get("kind")
    if kind == "merge":
        command = f"git merge --no-ff {raw_step.get('merge_branch') or '?'}"
    elif kind == "gate":
        command = "(gate checks only)"
    else:
        command = raw_step.get("command") or ""
    logs = []
    try:
        logs = sorted((attempt_dir / "logs").glob("*.out.log"),
                      key=lambda p: (p.stat().st_mtime_ns, p.name))
    except OSError:
        logs = []
    newest = logs[-1] if logs else None
    return {"command": one_line(command, 400),
            "log": _relpath(newest, run_dir) if newest else None,
            "log_tail": _log_tail(newest) if newest else []}


def _relpath(p: Path | None, run_dir: Path) -> str | None:
    if p is None:
        return None
    try:
        return Path(p).relative_to(run_dir).as_posix()
    except ValueError:
        return Path(p).as_posix()


def _harness_executor_activity(harness_executor: str | None, attempt_dir: Path, *, now: float,
                               running: bool, limit: int) -> dict | None:
    if harness_executor not in HARNESS_EXECUTORS:
        return None
    return harness_executor_module(harness_executor).activity(attempt_dir, now=now, running=running,
                                                              limit=limit)


# ---------------------------------------------------------- liveness


def _quote(arg: str) -> str:
    if arg and re.fullmatch(r"[A-Za-z0-9_@%+=:,./\\-]+", arg):
        return arg
    return '"' + str(arg).replace('"', '\\"') + '"'


def revert_command(run_dir: Path) -> str | None:
    """The exact teardown command, when the run directory has a revert plan."""
    run_dir = Path(run_dir)
    if not (run_dir / "revert.json").exists():
        return None
    return " ".join([python_cmd(), "-m", "ohflow.cli", "revert",
                     "--run", _quote(str(run_dir))])


def resume_command(run_dir: Path) -> str | None:
    """The exact `--resume` command, from what `run.json` recorded."""
    run_dir = Path(run_dir)
    run = read_json(run_dir / "run.json")
    if not isinstance(run, dict) or not run.get("workflow_path"):
        return None
    parts = [python_cmd(), "-m", "ohflow.cli", "run",
             "--workflow", _quote(str(run["workflow_path"])),
             "--out", _quote(str(run_dir.parent)),
             "--resume", _quote(str(run.get("run_id") or run_dir.name))]
    args = run.get("workflow_args")
    if not isinstance(args, dict):
        args = run.get("args") if isinstance(run.get("args"), dict) else {}
    for k, v in args.items():
        value = ("true" if v is True else "false" if v is False else str(v))
        parts += ["--args", _quote(f"{k}={value}")]
    return " ".join(parts)


# ------------------------------------------------------------- attempts


def _failed_checks(gate: Any) -> list[str]:
    if not isinstance(gate, dict):
        return []
    return [str(ch.get("name")) for ch in gate.get("checks") or []
            if isinstance(ch, dict) and not ch.get("passed")]


def _cause(payload: dict) -> tuple[str | None, str | None]:
    """(cause, short cause) of one attempt, per spec §6."""
    failed = _failed_checks(payload.get("gate"))
    if failed:
        text = "gate " + ", ".join(failed) + " failed"
        return text, "gate " + ", ".join(failed)
    fc = payload.get("failure_class")
    err = first_line(payload.get("error"), 160)
    if payload.get("killed") is not None:
        return (err or "killed by ohflow kill"), "killed"
    if payload.get("abort_victim"):
        return (err or "stopped by the run's abort"), "abort"
    if fc or err:
        text = f"{fc}: {err}" if fc and err else (fc or err)
        short = payload.get("transient_signature") or fc or "error"
        return text, str(short)
    return None, None


def _attempt_rows(state: RunState, records_fin: dict, coord: str,
                  step_dir: Path, run_dir: Path, now: float,
                  live: bool) -> list[dict]:
    rows = []
    for ex in ohattempts.executions(state, coord):
        n = ex.get("attempt")
        if not isinstance(n, int):
            continue
        fin = records_fin.get((coord, n))
        payload = (fin or {}).get("payload") or {}
        status = ex.get("status") or "running"
        started = epoch(ex.get("started_at"))
        ended = epoch(ex.get("ended"))
        if status == "running" and not live:
            status = "interrupted"
        wall = payload.get("wall_seconds")
        if not isinstance(wall, (int, float)):
            if status == "running" and started is not None:
                wall = now - started
            elif started is not None and ended is not None:
                wall = ended - started
            else:
                wall = None
        cause = short = None
        if status not in _GOOD and status not in ("running",):
            cause, short = _cause(payload)
            if status == "interrupted":
                cause, short = ("the supervisor stopped before this attempt "
                                "finished", "interrupted")
        rows.append({
            "n": n,
            "start_kind": ex.get("start_kind") or "initial",
            "status": status,
            "started": iso(started),
            "ended": iso(ended),
            "wall_s": round(wall, 1) if isinstance(wall, (int, float)) else None,
            "cause": cause,
            "short_cause": short,
            "retry_decision": ex.get("retry_decision"),
            "failure_class": ex.get("failure_class"),
            "abort_victim": bool(ex.get("abort_victim")),
            "dir": _relpath(rundir.attempt_in(step_dir, n), run_dir),
        })
    rows.sort(key=lambda r: r["n"])
    return rows


def _lineage(rows: list[dict]) -> str | None:
    """"01 deferred (429) -> 02 auto_resume -> passed", one chain per agent."""
    if not rows:
        return None
    parts = []
    for i, r in enumerate(rows):
        label = f"{r['n']:02d}"
        if r["start_kind"] != "initial":
            label += f" {r['start_kind']}"
        if r["status"] == "running":
            label += " running"
        elif (i < len(rows) - 1 or r["status"] not in _GOOD
              or len(rows) == 1):
            label += f" {r['status']}"
            if r.get("short_cause"):
                label += f" ({r['short_cause']})"
        parts.append(label)
    last = rows[-1]
    if last["status"] in _GOOD and len(rows) > 1:
        parts.append(last["status"])
    return " \u2192 ".join(parts)


def _attempt_tokens(tokens: Any) -> dict | None:
    """The live page's four token fields, from the one usage record."""
    usage = rundir.Run.usage({"tokens": tokens})
    if usage is None:
        return None
    return {"input": usage["prompt_tokens"],
            "output": usage["completion_tokens"],
            "cache_read": usage["cache_read_tokens"],
            "reasoning": usage["reasoning_tokens"]}


def _add_tokens(into: dict, more: dict | None) -> None:
    for k in TOKEN_FIELDS:
        into[k] = into.get(k, 0) + int_of((more or {}).get(k))


def _signal(value: float | None, amber: float | None,
            red: float | None) -> str:
    if value is None or amber is None or red is None:
        return "ok"
    if value > red:
        return "red"
    if value > amber:
        return "amber"
    return "ok"


# ------------------------------------------------------------ the events


def _event_text(rec: dict, names: dict[str, str],
                phase_names: dict[str, str]) -> tuple[str, str]:
    """One human sentence per run log event, and its tone."""
    ev = rec.get("event")
    p = rec.get("payload") or {}
    c = rec.get("coord") or ""
    who = names.get(c) or c
    n = rec.get("attempt")
    phase = f"phase {c.split('.', 1)[0]} {phase_names.get(c, c)}"
    if ev == "run_started":
        return f"run started (workflow {p.get('workflow') or '?'})", "info"
    if ev == "worktree_ready":
        facts = p.get("facts") or {}
        return (f"worktree {p.get('name')} ready on branch "
                f"{facts.get('branch') or '?'}"), "info"
    if ev == "phase_started":
        steps = len(p.get("steps") or [])
        return (f"{phase} started: {steps} step(s), at most "
                f"{p.get('max_parallel') or '?'} at once"), "info"
    if ev == "attempt_started":
        kind = p.get("start_kind") or "initial"
        return f"{who} attempt {n} started ({kind})", "info"
    if ev == "gate_ran":
        gate = p.get("gate") or {}
        if gate.get("passed"):
            return f"{who} attempt {n}: gate passed", "ok"
        failed = _failed_checks(gate)
        return (f"{who} attempt {n}: gate failed"
                + (f" ({', '.join(failed)})" if failed else "")), "bad"
    if ev == "attempt_finished":
        status = p.get("status") or "?"
        wall = p.get("wall_seconds")
        if not n:
            reason = first_line(p.get("error"), 140)
            return (f"{who} {status}" + (f": {reason}" if reason else "")), (
                "ok" if status in _GOOD else "warn")
        cause, _short = _cause(p)
        text = f"{who} attempt {n} {status}"
        if isinstance(wall, (int, float)) and wall:
            text += f" ({round(wall)} s)"
        if status not in _GOOD and cause:
            text += f": {cause}"
        tone = ("ok" if status in _GOOD else
                "warn" if status == "deferred" else "bad")
        return text, tone
    if ev == "retry_decided":
        return f"{who} attempt {n}: {p.get('retry_decision') or '?'}", "info"
    if ev == "phase_settled":
        status = p.get("status") or "?"
        return (f"{phase} settled {status}: {p.get('good', '?')} of "
                f"{p.get('total', '?')} good"), (
            "ok" if status == "passed" else
            "warn" if status == "deferred" else "bad")
    if ev == "phase_resumed":
        steps = ", ".join(names.get(s) or s
                          for s in p.get("steps") or [])
        return (f"{phase} auto-resume pass {p.get('pass')} of "
                f"{p.get('auto_resume', '?')} reruns {steps or 'nothing'}"), "warn"
    if ev == "work_excluded":
        return f"{who} excluded: {p.get('reason') or 'excluded'}", "bad"
    if ev == "run_log_recovered":
        return (f"run log repaired a torn final line (line "
                f"{p.get('line', '?')})"), "warn"
    if ev == "run_finished":
        status = p.get("status") or "?"
        return f"run {status}", ("ok" if status == "finished" else
                                 "warn" if status == "paused" else "bad")
    return f"{ev}", "info"


def _is_noise(rec: dict) -> bool:
    """A decision not to retry a passed step says nothing to a watcher."""
    if rec.get("event") != "retry_decided":
        return False
    decision = str((rec.get("payload") or {}).get("retry_decision") or "")
    return "is not a failure" in decision


def _events(records: list[dict], names: dict[str, str],
            phase_names: dict[str, str]) -> list[dict]:
    out = []
    for rec in reversed(records):
        if _is_noise(rec):
            continue
        text, tone = _event_text(rec, names, phase_names)
        at = epoch(rec.get("ts"))
        out.append({"at": hms(at), "ts": rec.get("ts"),
                    "coord": rec.get("coord"), "event": rec.get("event"),
                    "text": one_line(text, 240), "tone": tone})
        if len(out) >= EVENTS_MAX:
            break
    return out


# --------------------------------------------------------------- the ETA


def finished_walls(state: RunState, records_fin: dict) -> list[float]:
    """The wall seconds of every finished agent attempt of this run, as the
    run log's `attempt_finished` payloads recorded them."""
    walls = []
    for ex in state.executions:
        if not ex.get("started") or ex.get("status") not in (
                "passed", "failed", "timeout", "quarantined"):
            continue
        fin = records_fin.get((ex.get("coord"), ex.get("attempt")))
        payload = (fin or {}).get("payload") or {}
        if payload.get("kind") not in (None, "agent"):
            continue
        wall = payload.get("wall_seconds")
        if isinstance(wall, (int, float)) and wall > 0:
            walls.append(float(wall))
    return walls


def eta(phases: list[dict], steps: list[dict], walls: list[float],
        expected: dict[str, float] | None = None) -> tuple[int | None, str]:
    """Spec §9, shared by `/api/read-out` and `/api/workflow`.

    `phases` carry `coord`, `state` and `max_parallel`; `steps` carry `coord`,
    `phase`, `kind`, `state` (`waiting`, `running` or `done`) and, while
    running, `elapsed_s`. Phases are barriers, so their estimates add in
    order: the running phase adds `ceil(waiting / max_parallel)` waves plus
    the longest remainder of its running steps, and each later phase adds
    `ceil(agents / max_parallel)` waves.

    A wave lasts the median of the run's own finished agent steps once one
    has finished. Before that, `expected` (the p50 of each step from
    `estimate.json`) stands in: a wave lasts the median of the waiting steps'
    expectations, and a running step's remainder is its own expectation
    less its elapsed time. The basis says which source answered.
    """
    expected = expected or {}
    median = statistics.median(walls) if walls else None

    def expect(step: dict) -> float | None:
        if median is not None:
            return median
        return expected.get(step["coord"])

    if median is None and not expected:
        return None, "unknown until one agent step finishes"
    total = 0.0
    unknown = False
    for ph in phases:
        agents = [s for s in steps
                  if s["phase"] == ph["coord"] and s["kind"] == "agent"]
        mp = max(1, int(ph.get("max_parallel") or 1))
        if ph["state"] == "running":
            waiting = [s for s in agents if s["state"] == "waiting"]
            waves = [expect(s) for s in waiting]
            if any(w is None for w in waves):
                unknown = True
            elif waves:
                total += math.ceil(len(waiting) / mp) * statistics.median(waves)
            longest = 0.0
            for s in agents:
                if s["state"] != "running":
                    continue
                own = expect(s)
                if own is None:
                    unknown = True
                    continue
                longest = max(longest, own - float(s.get("elapsed_s") or 0))
            total += max(0.0, longest)
        elif ph["state"] == "waiting":
            waves = [expect(s) for s in agents]
            if any(w is None for w in waves):
                unknown = True
            elif waves:
                total += math.ceil(len(agents) / mp) * statistics.median(waves)
    if median is not None:
        basis = (f"median {round(median)} s over {len(walls)} finished agent "
                 f"step(s)")
    else:
        basis = ("predicted from history (estimate.json); no agent step of "
                 "this run has finished yet")
    if unknown:
        basis += "; a step with no estimate is left out"
    return int(round(total)), basis


def _eta(phases: list[dict], agents_by_phase: dict[str, list[dict]],
         state: RunState, records_fin: dict, now: float,
         status: str, expected: dict[str, float] | None = None
         ) -> tuple[int | None, str]:
    """The read-out's rows, handed to `eta`."""
    if status not in _LIVE_RUN:
        return None, "the run is not running"
    steps = []
    for ph in phases:
        for a in agents_by_phase.get(ph["coord"], []):
            steps.append({"coord": a["coord"], "phase": ph["coord"],
                          "kind": a["kind"], "state": a["display"]["state"],
                          "elapsed_s": (a.get("limits") or {}).get("elapsed_s")})
    return eta(phases, steps, finished_walls(state, records_fin), expected)


#: Why agents wait, in the order a watcher acts on it, as words for the NOW row.
_WAITING_WORDS = (
    ("hold", "for go", "for go"),
    ("slot", "for a free slot", "for a free slot"),
    ("cooldown", "for the provider cooldown", "for the provider cooldown"),
    ("auto_resume", "for an auto-resume pass", "for an auto-resume pass"),
    ("resume", "for a resume", "for a resume"),
    ("phase", "for its phase", "for their phase"),
    # Only `/api/workflow` names this wait: the read-out's cards never do,
    # because the engine closes a step whose dependency failed as `skipped`
    # and starts one whose dependency passed, so a card sees it as a slot wait.
    ("dependency", "for a dependency", "for their dependencies"),
    ("stopped", "never started", "never started"),
)


def waiting_phrases(waiting_by: dict[str, int]) -> list[tuple[str, str]]:
    """`{"slot": 1, "phase": 4}` as `[("slot", "1 for a free slot"),
    ("phase", "4 for their phase")]`, in the order a watcher acts on them.

    The key rides along so a caller can add a fact to one phrase, as the
    phase lane line adds "(2 of 2 busy)" to the slot wait.
    """
    out = []
    for key, one, many in _WAITING_WORDS:
        n = int(waiting_by.get(key) or 0)
        if n:
            out.append((key, f"{n} {one if n == 1 else many}"))
    return out


def waiting_words(waiting_by: dict[str, int]) -> str:
    """`{"slot": 1, "phase": 4}` as "1 for a free slot, 4 for their phase"."""
    return ", ".join(phrase for _key, phrase in waiting_phrases(waiting_by))


# ------------------------------------------------------------- read-out


def read_out(run_dir: Path, now: float | None = None, *,
             supervisor_pid: int | None = None,
             final_status: str | None = None,
             detail: bool = False,
             tool_calls: int = DEFAULT_TOOL_CALLS) -> dict:
    """The whole run at one instant (spec §5).

    `now` is epoch seconds; tests pass a fixed one. `supervisor_pid` is the
    serving process when it is the supervisor. `final_status` is the exit
    path's verdict for a run whose run log never reached `run_finished` - a
    crash or an interrupt - and it marks the read-out final. `detail` adds the
    activity of every failed attempt, which the exit report shows and the live
    page does not need.
    """
    run_dir = Path(run_dir).resolve()
    now = time.time() if now is None else _now(now)
    records, state, unreadable = _run_log_view(run_dir).refresh(run_dir)
    run = rundir.open_run(run_dir, state=state, records=records,
                          supervisor_hint=supervisor_pid)
    alive = run.supervisor_alive
    workflow = run.workflow
    records_fin = run.finishes

    # ---- run status
    if not records:
        status = run.status_without_run_log
    else:
        status = run.status
    if final_status and status in ("running", "starting", "held",
                                   "not started", "orphaned"):
        status = final_status
    live = status in _LIVE_RUN and not final_status
    paused_like = status in ("paused", "orphaned", "crashed", "interrupted")

    run_json = read_json(run_dir / "run.json")
    run_json = run_json if isinstance(run_json, dict) else {}
    owner = read_json(run_dir / ".ohflow-owner.json")
    started = epoch(state.started) or epoch(
        (owner or {}).get("claimed") if isinstance(owner, dict) else None)
    finished = epoch(state.finished)
    auto_resume = state.meta.get("auto_resume", workflow.get("auto_resume")) or 0
    cooldown = epoch(state.cooldown_until)
    cooldown_active = cooldown is not None and cooldown > now and live
    resume_cmd = resume_command(run_dir) if paused_like and records else None

    names = {}
    phase_names = {}
    for ph in workflow["phases"]:
        phase_names[ph["coord"]] = ph["name"]
        for st in ph["steps"]:
            names[st["coord"]] = st["id"]

    # ---- phases, first pass (agents need the phase state)
    phases_out: list[dict] = []
    for ph in workflow["phases"]:
        entry = state.phases.get(ph["coord"]) or {}
        begun = "started" in entry
        pstate = "waiting" if not begun else (entry.get("status") or "running")
        mp = (entry.get("max_parallel") or ph["raw"].get("max_parallel")
              or state.meta.get("max_parallel") or workflow.get("max_parallel"))
        phases_out.append({
            "coord": ph["coord"], "index": ph["index"], "name": ph["name"],
            "state": pstate, "total": len(ph["steps"]),
            "max_parallel": mp,
            "policy": entry.get("policy") or ph["raw"].get("on_step_failure"),
            "min_success": entry.get("min_success",
                                     ph["raw"].get("min_success")),
            "auto_resumes": int(entry.get("auto_resumes") or 0),
        })

    # ---- agents
    agents: list[dict] = []
    by_phase: dict[str, list[dict]] = {}
    for ph, pout in zip(workflow["phases"], phases_out):
        for st in ph["steps"]:
            agent = _agent(run_dir, st, ph, pout, state, records_fin, now,
                           live=live, status=status, alive=alive,
                           cooldown=cooldown if cooldown_active else None,
                           auto_resume=auto_resume, resume_cmd=resume_cmd,
                           detail=detail, tool_calls=tool_calls)
            agents.append(agent)
            by_phase.setdefault(ph["coord"], []).append(agent)

    # Slot reasons need every running agent of the phase first.
    for pout in phases_out:
        members = by_phase.get(pout["coord"], [])
        busy = sum(1 for a in members if a["display"]["state"] == "running")
        for a in members:
            if a["display"].get("why") == "slot":
                a["display"]["reason"] = (
                    f"waits for a free slot ({busy} of "
                    f"{pout['max_parallel'] or '?'} busy)")
        if pout["state"] != "waiting" and "good" not in pout:
            pout["good"] = sum(1 for a in members
                               if a["engine_status"] in _GOOD)
        entry = state.phases.get(pout["coord"]) or {}
        if isinstance(entry.get("good"), int) and pout["state"] not in (
                "running", "waiting"):
            pout["good"] = entry["good"]

    # ---- counts and tokens
    counts = {"running": 0, "waiting": 0, "restarted": 0, "done": 0}
    waiting_by: dict[str, int] = {}
    tokens = {k: 0 for k in TOKEN_FIELDS}
    for a in agents:
        d = a["display"]
        counts[d["state"]] = counts.get(d["state"], 0) + 1
        if d["restarted"]:
            counts["restarted"] += 1
        if d["state"] == "waiting" and d.get("why"):
            waiting_by[d["why"]] = waiting_by.get(d["why"], 0) + 1
        _add_tokens(tokens, a.get("tokens"))
    counts["waiting_by"] = waiting_by
    counts["waiting_text"] = waiting_words(waiting_by)

    # ---- clocks and signals
    last_event = epoch(records[-1].get("ts")) if records else None
    idles = [a["limits"]["idle_s"] for a in agents
             if a["display"]["state"] == "running"
             and a.get("limits", {}).get("idle_s") is not None]
    last_event_age = age(now, last_event)
    candidates = [x for x in [last_event_age] + idles if x is not None]
    last_activity_age = min(candidates) if candidates else None
    activity_signal = "ok"
    if status in _LIVE_RUN:
        if not alive:
            activity_signal = "red"
        else:
            activity_signal = _signal(last_activity_age, RUN_AMBER_S,
                                      RUN_RED_S)
    estimate = ohestimate.read_estimate(run_dir)
    eta_s, eta_basis = _eta(phases_out, by_phase, state, records_fin, now,
                            status if live else "stopped",
                            ohestimate.step_expectations(estimate))

    current = next((p for p in phases_out if p["state"] == "running"), None)
    if current is None:
        begun = [p for p in phases_out if p["state"] != "waiting"]
        current = begun[-1] if begun else None

    recovery = state.meta.get("run_log_recovery")
    recovered = [rec.get("payload") or {} for rec in records
                 if rec.get("event") == "run_log_recovered"]

    document = {
        "schema": SCHEMA,
        "generated": iso(now),
        "mode": "final" if (final_status or not live) else "live",
        "run": {
            "id": state.run_id or run_json.get("run_id") or run_dir.name,
            "workflow": workflow.get("name") or run_json.get("workflow"),
            "status": status,
            "started": iso(started),
            "finished": iso(finished),
            "elapsed_s": age(finished or now, started),
            "supervisor_alive": alive,
            "last_event_age_s": last_event_age,
            "last_activity_age_s": last_activity_age,
            "activity_signal": activity_signal,
            "cooldown_until": iso(cooldown) if cooldown_active else None,
            "eta_s": eta_s,
            "eta_basis": eta_basis,
            # The estimate the run started with, and what it has recorded so
            # far, so the exit report's embedded page shows predicted against
            # actual the way the live page does.
            "estimate": (dict(estimate["run"], generated=estimate.get("generated"))
                         if estimate else None),
            "actual": ({"wall_s": age(finished or now, started),
                        "tokens": int(tokens.get("input") or 0)
                        + int(tokens.get("output") or 0)}
                       if estimate else None),
            "phase_index": current["index"] if current else None,
            "phase_total": len(phases_out),
            "counts": counts,
            "tokens": tokens,
            "resume_command": resume_cmd,
            "revert_command": revert_command(run_dir),
            "dir": str(run_dir),
            "auto_resume": auto_resume,
        },
        "phases": phases_out,
        "agents": agents,
        "events": _events(records, names, phase_names),
        "run_log": {
            "records": len(records),
            "unreadable_lines": unreadable,
            "recovered": recovered or ([recovery] if recovery else []),
        },
    }
    return _redact_tree(document)


def _now(value: Any) -> float:
    if isinstance(value, _dt.datetime):
        return value.timestamp()
    return float(value)


def _agent(run_dir: Path, st: dict, ph: dict, pout: dict, state: RunState,
           records_fin: dict, now: float, *, live: bool, status: str,
           alive: bool, cooldown: float | None, auto_resume: int,
           resume_cmd: str | None, detail: bool, tool_calls: int) -> dict:
    c = st["coord"]
    raw = st["raw"] or {}
    agent_spec = raw.get("agent") if isinstance(raw.get("agent"), dict) else None
    rec = state.steps.get(c)
    kind = raw.get("kind") or (rec.kind if rec else None) or "agent"
    harness_executor = agent_spec.get("harness_executor") if agent_spec else None
    model = ((agent_spec.get("model") or {}).get("model") if agent_spec else None)
    step_dir = rundir.step_dir(run_dir, c)
    rows = _attempt_rows(state, records_fin, c, step_dir, run_dir, now, live)
    newest = rows[-1] if rows else None
    engine_status = rec.status if rec else "pending"

    # ---- display state, spec §6, in its order
    restarted = bool(newest and (newest["n"] >= 2
                                 or newest["start_kind"] in _RESTART_KINDS))
    why = None
    label = engine_status.upper()
    # Excluded work is never started again, by an auto-resume pass or by `--resume`, so a
    # deferred step that earned an exclusion waits for nothing.
    excluded = bool(rec and rec.fingerprint
                    and f"{c}@{rec.fingerprint}" in state.exclusions)
    if status == rundir.HELD:
        # Nothing has started and nothing will until `go`: the phase barrier
        # and the slot count are not what the step waits for.
        d_state, why, reason, label = "waiting", "hold", HELD_REASON, "WAITING"
    elif pout["state"] == "waiting":
        d_state, why = "waiting", "phase"
        reason = (f"waits for phase {ph['index']}" if live
                  else f"not started: the run stopped before phase "
                       f"{ph['index']}")
        label = "WAITING"
    elif rec is None or engine_status == "pending":
        d_state, label = "waiting", "WAITING"
        if not live:
            why, reason = "stopped", "not started: the run stopped"
        elif cooldown is not None:
            why = "cooldown"
            reason = (f"waits for provider cooldown until "
                      f"{hms(cooldown)}")
        else:
            why, reason = "slot", "waits for a free slot"
    elif engine_status == "running":
        if live:
            d_state, label = "running", "RUNNING"
            reason = f"attempt {rec.attempt}, {newest['start_kind'] if newest else 'initial'}"
        else:
            d_state, label = "done", "INTERRUPTED"
            reason = (f"attempt {rec.attempt} never finished: the "
                      f"supervisor stopped")
    elif engine_status == "deferred" and not excluded and status in (
            "paused", "orphaned", "crashed", "interrupted"):
        d_state, why, label = "waiting", "resume", "DEFERRED"
        verb = "paused" if status == "paused" else "stopped"
        reason = (f"{verb}: run `{resume_cmd}`" if resume_cmd
                  else f"{verb}: resume the run with --resume")
    elif engine_status == "deferred" and live and _auto_resumable(
            state, c, rec, raw, auto_resume):
        d_state, why, label = "waiting", "auto_resume", "DEFERRED"
        reason = (f"deferred: {first_line(rec.error, 100) or 'transient'}; "
                  f"an auto-resume pass reruns it")
    else:
        d_state = "done"
        if engine_status == "cached":
            label, reason = "PASSED", "cached: passed in an earlier run"
        else:
            reason = engine_status
            if engine_status not in _GOOD and rec and rec.error:
                reason += f": {first_line(rec.error, 120)}"
        if excluded:
            reason += " (excluded)"
            label += " \u00b7 EXCLUDED"
    display = {"state": d_state, "reason": reason, "restarted": restarted,
               "label": label, "why": why}

    # ---- objective, spec §8
    objective, source = None, None
    for candidate, src in ((raw.get("objective"), "objective"),
                           (raw.get("note"), "note")):
        if isinstance(candidate, str) and candidate.strip():
            objective, source = one_line(candidate), src
            break
    if objective is None and agent_spec:
        objective = brief_objective(agent_spec.get("brief"))
        source = "brief" if objective else None

    agent: dict[str, Any] = {
        "coord": c,
        "phase": pout["coord"],
        "step_id": st["id"],
        "kind": kind,
        "role": (agent_spec.get("role") if agent_spec else None) or kind,
        "harness_executor": harness_executor,
        "model": model,
        "display": display,
        "engine_status": engine_status,
        "attempt": newest["n"] if newest else 0,
        "start_kind": newest["start_kind"] if newest else None,
        "objective": objective,
        "objective_source": source,
        "branch": rec.branch if rec else None,
        "excluded": excluded,
        "attempts": rows,
        "lineage": _lineage(rows),
        "wall_s": (round(sum(r["wall_s"] or 0 for r in rows), 1)
                   if rows else None),
        "gate": _gate_view(rec.gate if rec else None),
        "error": first_line(rec.error, 240) if rec and rec.error else None,
    }

    # ---- activity of the newest attempt
    act = None
    if newest:
        adir = rundir.attempt_in(step_dir, newest["n"])
        running = newest["status"] == "running"
        if kind == "agent":
            act = _harness_executor_activity(harness_executor, adir, now=now, running=running,
                                             limit=tool_calls)
        else:
            agent["mechanical"] = activity_mechanical(adir, raw, run_dir)
        agent["evidence"] = {"attempt_dir": newest["dir"],
                             "step_dir": _relpath(step_dir, run_dir)}
    elif kind != "agent":
        agent["mechanical"] = activity_mechanical(step_dir, raw, run_dir)
    if act is not None:
        agent["latest_reasoning"] = act["latest_reasoning"]
        agent["running_tool"] = act["running_tool"]
        agent["tool_calls"] = act["tool_calls"]
        agent["tool_calls_total"] = act["tool_calls_total"]
        agent["note"] = act["note"] if d_state == "running" else None
        agent["last_error"] = act["last_error"]
    else:
        agent.update({"latest_reasoning": None, "running_tool": None,
                      "tool_calls": [], "tool_calls_total": 0, "note": None,
                      "last_error": None})

    # ---- limits and signals
    execution_timeout = raw.get("execution_timeout_s")
    stall = raw.get("stall_timeout_s")
    max_iter = agent_spec.get("max_iterations") if agent_spec else None
    effective = {}
    elapsed = None
    if newest:
        elapsed = newest["wall_s"]
        newest_result = read_json(rundir.attempt_in(step_dir, newest["n"]) / "result.json")
        settings = newest_result.get("settings") if isinstance(newest_result, dict) else None
        if isinstance(settings, dict) and isinstance(settings.get("effective"), dict):
            effective = settings["effective"]
    idle = act["idle_s"] if act else None
    if d_state == "running" and act is None and newest:
        idle = age(now, epoch(newest["started"]))
    agent["limits"] = {
        "elapsed_s": int(elapsed) if isinstance(elapsed, (int, float)) else None,
        "execution_timeout_s": execution_timeout,
        "llm_calls": act["llm_calls"] if act else None,
        "max_iterations": max_iter,
        "max_iterations_effective": effective.get("max_iterations"),
        "max_iterations_enforced_by": effective.get("max_iterations_enforced_by"),
        "idle_s": idle if d_state == "running" else None,
        "stall_timeout_s": stall,
    }
    signals = {"idle": "ok", "wall": "ok", "calls": "ok"}
    if d_state == "running":
        if isinstance(stall, (int, float)) and stall > 0:
            signals["idle"] = _signal(idle, stall / 2, stall)
        else:
            signals["idle"] = _signal(idle, IDLE_AMBER_S, IDLE_RED_S)
        if isinstance(execution_timeout, (int, float)) and execution_timeout > 0:
            signals["wall"] = _signal(elapsed, 0.75 * execution_timeout,
                                      0.90 * execution_timeout)
        if isinstance(max_iter, (int, float)) and max_iter > 0 and act:
            signals["calls"] = _signal(act["llm_calls"], 0.75 * max_iter,
                                       0.90 * max_iter)
    agent["signals"] = signals

    # ---- tokens: final numbers per attempt, live numbers where none exist
    # A reattach continues its attempt, so two rows can share one number and
    # one directory. That directory's usage counts once.
    tokens = {k: 0 for k in TOKEN_FIELDS}
    counted: set = set()
    for r in rows:
        if r["n"] in counted:
            continue
        counted.add(r["n"])
        adir = rundir.attempt_in(step_dir, r["n"])
        result = read_json(adir / "result.json")
        final = _attempt_tokens(result.get("tokens")) if isinstance(
            result, dict) else None
        if final is None and kind == "agent":
            if newest is not None and r["n"] == newest["n"] and act:
                final = act["tokens"]
            else:
                other = _harness_executor_activity(harness_executor, adir, now=now, running=False,
                                                   limit=0)
                final = other["tokens"] if other else None
        _add_tokens(tokens, final)
    agent["tokens"] = tokens

    # ---- the exit report reads what each failed attempt did
    if detail and kind == "agent":
        for r in rows:
            if r["status"] in _GOOD or r["status"] == "running":
                continue
            adir = rundir.attempt_in(step_dir, r["n"])
            other = _harness_executor_activity(harness_executor, adir, now=now, running=False,
                                               limit=DEFAULT_TOOL_CALLS)
            if other:
                r["activity"] = {"latest_reasoning": other["latest_reasoning"],
                                 "tool_calls": other["tool_calls"],
                                 "last_error": other["last_error"]}
    return agent


def agent_attempts(agent: dict) -> list[dict]:
    """The attempt rows of one agent in a read-out, oldest first."""
    return agent["attempts"]


def _gate_view(gate: Any) -> dict | None:
    if not isinstance(gate, dict):
        return None
    return {"passed": bool(gate.get("passed")),
            "failed": _failed_checks(gate)}


def _auto_resumable(state: RunState, c: str, rec, raw: dict,
                    auto_resume: int) -> bool:
    """Whether an auto-resume pass may still rerun this deferred step."""
    if getattr(rec, "killed", None) is not None:
        return False
    retry = raw.get("retry") if isinstance(raw.get("retry"), dict) else {}
    allowed, _why = ohattempts.may_start(
        state, c, rec.fingerprint, start_kind="auto_resume",
        retry_max=int(retry.get("max") or 0), auto_resume=int(auto_resume or 0))
    return allowed


# ---------------------------------------------------------- one attempt


def activity(run_dir: Path, coord: str, attempt: int, *,
             limit: int = 20, now: float | None = None) -> dict | None:
    """The activity block of one attempt, for `/api/agent`.

    The coordinate must name a step of this run, and the attempt must be a
    number. Nothing from the request is ever joined into a path unchecked.
    """
    run_dir = Path(run_dir).resolve()
    now = time.time() if now is None else _now(now)
    limit = max(1, min(int(limit), MAX_TOOL_CALLS))
    records, state, _bad = _run_log_view(run_dir).refresh(run_dir)
    run = rundir.open_run(run_dir, state=state, records=records)
    workflow = run.workflow
    raw = None
    for ph in workflow["phases"]:
        for st in ph["steps"]:
            if st["coord"] == coord:
                raw = st["raw"] or {}
    if raw is None or not isinstance(attempt, int) or not 1 <= attempt <= 999:
        return None
    execs = {e.get("attempt"): e for e in ohattempts.executions(state, coord)}
    if attempt not in execs:
        return None
    adir = rundir.attempt_dir(run_dir, coord, attempt)
    alive = run.supervisor_alive
    running = execs[attempt].get("status") == "running" and alive
    agent = raw.get("agent") if isinstance(raw.get("agent"), dict) else None
    if (raw.get("kind") or "agent") != "agent":
        block = {"mechanical": activity_mechanical(adir, raw, run_dir)}
    else:
        block = _harness_executor_activity(agent.get("harness_executor") if agent else None, adir,
                                           now=now, running=running, limit=limit) or {}
    return _redact_tree({"coord": coord, "attempt": attempt,
                         "limit": limit, "activity": block})

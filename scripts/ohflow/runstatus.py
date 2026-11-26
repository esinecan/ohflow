"""One status sentence per run, and the facts a watcher compares.

`status`, `watch`, the end of `run` and the exit verdict all describe a run.
They read one `live.read_out` and use the functions here, so the four cannot
disagree about how many steps passed.

A watcher stores `facts(read_out)` as its cursor. The next call compares the new
facts with the stored ones and reports only the difference. The comparison is
on facts (step status, attempt number, signal colour, run status), never on
text, so a reworded line cannot read as a change.
"""

from __future__ import annotations

from pathlib import Path

from . import live, rundir
from .exit_report import human_duration, needs

__all__ = ["tally", "step_status", "step_statuses", "sentence", "need_lines", "dashboard_url",
           "facts", "changes", "LIVE_STATUSES", "STOPPED_STATUSES", "NOT_STARTED"]

GOOD = frozenset({"passed", "cached"})
FAILED = frozenset({"failed", "timeout", "quarantined"})
#: What `live.read_out` names a run with no run log and no live supervisor.
NOT_STARTED = rundir.NOT_STARTED
LIVE_STATUSES = frozenset({"running", rundir.STARTING, rundir.HELD})
STOPPED_STATUSES = rundir.STOPPED_STATUSES
#: Facts a first call reports at most this many step lines for.
FIRST_CALL_LINES = 10
_RANK = {"ok": 0, "amber": 1, "red": 2}


def step_status(agent: dict) -> str:
    """The step's word. The dashboard's INTERRUPTED label is a status here."""
    if agent["display"]["label"] == "INTERRUPTED":
        return "interrupted"
    return str(agent["engine_status"] or "pending")


def tally(statuses: list[str]) -> dict:
    """Counts by group. `pending` also holds `skipped`, which never started."""
    n = {"total": len(statuses), "passed": 0, "running": 0, "failed": 0,
         "pending": 0, "deferred": 0, "interrupted": 0, "dry-run": 0}
    for s in statuses:
        if s in GOOD:
            n["passed"] += 1
        elif s == "running":
            n["running"] += 1
        elif s in FAILED:
            n["failed"] += 1
        elif s in ("deferred", "interrupted", "dry-run"):
            n[s] += 1
        else:
            n["pending"] += 1
    return n


def step_statuses(read_out: dict, run_dir: Path | None = None) -> list[str]:
    """One word per step. The run log holds no record of a step a dry run
    listed, so the run reader names it `dry-run` instead of `pending`."""
    words = [step_status(a) for a in read_out["agents"]]
    if run_dir is None or "pending" not in words:
        return words
    read = {v.coord: v.status for v in rundir.open_run(run_dir).steps()}
    return ["dry-run" if w == "pending" and read.get(a["coord"]) == "dry-run"
            else w for a, w in zip(read_out["agents"], words)]


def sentence(read_out: dict, run_dir: Path | None = None) -> str:
    """`<status>: P of T steps passed, R running, F failed, Q pending · <time>`.

    A deferred or interrupted step is waiting for a resume, and a dry-run step
    never ran. Each is named after the four counts, and only when there is one.
    Give `run_dir` to let the run reader name the dry-run steps.
    """
    n = tally(step_statuses(read_out, run_dir))
    parts = [f"{n['passed']} of {n['total']} steps passed",
             f"{n['running']} running", f"{n['failed']} failed",
             f"{n['pending']} pending"]
    for word in ("deferred", "interrupted", "dry-run"):
        if n[word]:
            parts.append(f"{n[word]} {word}")
    run = read_out["run"]
    return (f"{run['status']}: " + ", ".join(parts) + " · "
            + human_duration(run.get("elapsed_s")))


def dashboard_url(run_dir: Path, read_out: dict | None = None) -> str | None:
    """The URL of the run's dashboard while the run is live, else None.

    A campaign controller serves the dashboard of every run it starts and outlives
    them, so a live pid in `dashboard.json` does not say the dashboard still
    serves. Only a run in `LIVE_STATUSES` does. Give `read_out` to reuse the
    one the caller already took.
    """
    import json

    from . import dashboard as ohdash
    if not ohdash.record_is_live(run_dir):
        return None
    try:
        record = json.loads((Path(run_dir) / ohdash.RECORD).read_text(
            encoding="utf-8"))
    except (OSError, ValueError):
        return None
    url = record.get("url") if isinstance(record, dict) else None
    if not isinstance(url, str) or not url:
        return None
    read_out = read_out or live.read_out(Path(run_dir))
    return url if read_out["run"]["status"] in LIVE_STATUSES else None


def need_lines(read_out: dict, run_dir: Path, limit: int = 4) -> list[str]:
    """One line per thing that needs a person, at most `limit` of them."""
    run_live = read_out["run"]["status"] in LIVE_STATUSES
    lines = []
    for item in needs(read_out, Path(run_dir)):
        if run_live and item["text"].startswith("Tear down"):
            continue
        text = " ".join(item["text"].split())
        lines.append(f"{text} {item['command']}" if item.get("command")
                     else text)
    if len(lines) > limit:
        rest = len(lines) - (limit - 1)
        lines = lines[:limit - 1] + [f"... and {rest} more in the exit report"]
    return lines


# ------------------------------------------------------------------ facts


def _worst_signal(agent: dict) -> tuple[str, str | None]:
    worst, name = "ok", None
    for key, colour in (agent.get("signals") or {}).items():
        if _RANK.get(colour, 0) > _RANK[worst]:
            worst, name = colour, key
    return worst, name


def facts(read_out: dict) -> dict:
    """What a watcher stores: run status and signal, and one entry per step."""
    steps = {}
    for a in read_out["agents"]:
        colour, _name = _worst_signal(a)
        steps[a["coord"]] = {"status": step_status(a),
                             "attempt": int(a.get("attempt") or 0),
                             "signal": colour}
    return {"run": {"status": read_out["run"]["status"],
                    "signal": read_out["run"].get("activity_signal") or "ok"},
            "steps": steps}


def _why(agent: dict) -> str:
    text = (agent.get("error") or agent["display"].get("reason") or "").strip()
    first = text.splitlines()[0] if text else ""
    return first if len(first) <= 100 else first[:97] + "..."


def _step_lines(coord: str, old: dict, new: dict, agent: dict) -> list[str]:
    status, attempt = new["status"], new["attempt"]
    lines = []
    if status == "running" and old.get("attempt", 0) >= 1 \
            and attempt > old.get("attempt", 0):
        lines.append(f"{coord} restarted (attempt {attempt})")
    elif status != old.get("status"):
        if status == "running":
            lines.append(f"{coord} started (attempt {attempt})")
        elif status in GOOD:
            lines.append(f"{coord} passed")
        elif status in FAILED or status == "deferred":
            why = _why(agent)
            lines.append(f"{coord} {status}" + (f": {why}" if why else ""))
        elif status in ("interrupted", "skipped"):
            lines.append(f"{coord} {status}")
    if new["signal"] == "red" and old.get("signal") != "red":
        _colour, name = _worst_signal(agent)
        lines.append(f"{coord} signal red: {name}")
    return lines


def changes(old: dict | None, new: dict, read_out: dict) -> list[str]:
    """The lines that say what is new since `old`, in workflow order.

    With no `old` the first call reports every step that already moved, up to
    `FIRST_CALL_LINES`, and says how many it left out.
    """
    first = not old
    old = old or {"run": {}, "steps": {}}
    lines: list[str] = []
    by_coord = {a["coord"]: a for a in read_out["agents"]}
    for coord, now in new["steps"].items():
        lines += _step_lines(coord, old["steps"].get(coord) or {}, now,
                             by_coord[coord])
    if first and len(lines) > FIRST_CALL_LINES:
        lines = lines[:FIRST_CALL_LINES] + [
            f"... and {len(lines) - FIRST_CALL_LINES} more"]
    run_old, run_new = old["run"], new["run"]
    if run_new["status"] != run_old.get("status") \
            and (run_old.get("status") or run_new["status"]
                 in STOPPED_STATUSES):
        lines.append(f"run {run_new['status']}")
    if run_new["signal"] == "red" and run_old.get("signal") != "red":
        lines.append("run signal red: no activity")
    return lines

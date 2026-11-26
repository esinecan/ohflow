from __future__ import annotations

import datetime as _dt
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from . import estimate as ohestimate
from . import rundir
from . import table as ohtable
from .paths import win
from .workflow import Workflow

__all__ = ["SCHEMA", "PILOT_FILE", "PILOT_DIR", "SUFFIX", "RUNNING", "CRASHED",
           "NO_UNITS", "pick", "pilot_workflow", "measure", "project",
           "started_record", "finished_record", "crashed_record", "reproject",
           "write_pilot", "read_pilot", "render_text", "status_lines",
           "hold_line", "page_view"]

SCHEMA = "ohflow.pilot/1"
PILOT_FILE = "pilot.json"
PILOT_DIR = "pilot"
SUFFIX = "-pilot"
RUNNING = "running"
CRASHED = "crashed"
NO_UNITS = ("--pilot needs units: the workflow declares no Workflow.units, so "
            "it has no path to pilot")
_GOOD = ("passed", "cached")


def _stamp() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def pick(workflow: Workflow) -> list:
    order = {unit.id: i for i, unit in enumerate(workflow.units)}
    chosen = []
    for path in workflow.paths:
        on_path = [u for u in workflow.units if u.path == path.name]
        if on_path:
            chosen.append(min(on_path, key=lambda u: (u.size, order[u.id])))
    return chosen


def pilot_workflow(workflow: Workflow) -> Workflow:
    chosen = pick(workflow)
    keep = {unit.id for unit in chosen}
    kept = {step.id for _pi, _phase, _si, step in workflow.steps()
            if step.unit is None or step.unit in keep}
    branches = {(workflow.workspace_of(w.name).name, w.branch)
                for w in workflow.worktrees}

    def branch(name, worktree):
        home = workflow.workspace_of(worktree).name
        return f"{name}{SUFFIX}" if (home, name) in branches else name

    phases = []
    for phase in workflow.phases:
        steps = tuple(
            replace(step,
                    depends_on=tuple(d for d in step.depends_on if d in kept),
                    consumes=tuple(c for c in step.consumes if c in kept),
                    merge_branch=branch(step.merge_branch, step.worktree))
            for step in phase.steps if step.id in kept)
        if not steps:
            continue
        floor = phase.min_success
        if isinstance(floor, int) and not isinstance(floor, bool):
            floor = min(floor, len(steps))
        phases.append(replace(phase, steps=steps, min_success=floor))
    worktrees = tuple(
        replace(w, path=Path(f"{w.path}{SUFFIX}"), branch=f"{w.branch}{SUFFIX}",
                base=branch(w.base, w.name))
        for w in workflow.worktrees)
    return replace(workflow, phases=tuple(phases), worktrees=worktrees,
                   units=tuple(chosen))


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _bucket() -> dict:
    return {"steps": 0, "attempts": 0, "statuses": [], "wall_s": 0.0,
            "tokens": 0, "cost_usd": 0.0, "unpriced": False, "timed": False}


def _settle(bucket: dict) -> dict:
    bad = [s or "unknown" for s in bucket["statuses"] if s not in _GOOD]
    if not bucket["statuses"]:
        status = "not run"
    else:
        status = bad[0] if bad else "passed"
    return {
        "steps": bucket["steps"], "attempts": bucket["attempts"],
        "status": status,
        "wall_s": round(bucket["wall_s"], 1) if bucket["timed"] else None,
        "tokens": bucket["tokens"] if bucket["timed"] or bucket["tokens"] else None,
        "cost_usd": None if bucket["unpriced"] else round(bucket["cost_usd"], 4),
    }


def measure(small: Workflow, summary: dict | None) -> dict:
    unit_of = {step.id: step.unit for _pi, _phase, _si, step in small.steps()}
    buckets: dict[str | None, dict] = {}
    for item in rundir.walk_summary(summary or {}):
        step_id = item.step.get("step_id")
        if step_id not in unit_of:
            continue
        bucket = buckets.setdefault(unit_of[step_id], _bucket())
        bucket["steps"] += 1
        bucket["statuses"].append(item.step.get("status"))
        started = [e for e in item.executions
                   if isinstance(e, dict) and e.get("started") is not False]
        for entry in started:
            bucket["attempts"] += 1
            wall = _num(entry.get("wall_seconds"))
            if wall is None and len(started) == 1:
                wall = _num(item.step.get("wall_seconds"))
            if wall is None:
                wall = _span(entry)
            if wall is not None and wall >= 0:
                bucket["wall_s"] += wall
                bucket["timed"] = True
            usage = rundir.Run.usage(entry)
            tokens = (usage or {}).get("total_tokens") or 0
            bucket["tokens"] += tokens
            cost = _num(entry.get("cost"))
            if cost is not None and entry.get("cost_source") not in (None, ohtable.UNPRICED):
                bucket["cost_usd"] += cost
            elif tokens:
                bucket["unpriced"] = True
    units = {}
    for unit in small.units:
        found = buckets.get(unit.id)
        entry = _settle(found) if found else _settle(_bucket())
        units[unit.id] = {"path": unit.path, "size": unit.size, **entry}
    shared = _settle(buckets[None]) if None in buckets else None
    return {"units": units, "shared": shared}


def _times(part: dict | None, n: int) -> dict | None:
    if part is None or part.get("wall_s") is None:
        return None

    def scale(value):
        return None if value is None else round(value * n, 4 if isinstance(value, float) else 0)

    return {"wall_s": scale(part["wall_s"]),
            "tokens": None if part.get("tokens") is None else int(part["tokens"]) * n,
            "cost_usd": scale(part.get("cost_usd"))}


def _add(total: dict, part: dict | None) -> None:
    if part is None:
        return
    for key in ("wall_s", "tokens", "cost_usd"):
        if total[key] is None or part.get(key) is None:
            total[key] = None
        else:
            total[key] += part[key]


def project(workflow: Workflow, measured: dict | None) -> dict:
    measured = measured or {"units": {}, "shared": None}
    counts: dict[str, int] = {}
    for unit in workflow.units:
        counts[unit.path] = counts.get(unit.path, 0) + 1
    by_path = {m["path"]: (uid, m) for uid, m in measured["units"].items()}
    paths, missing = [], []
    total = {"wall_s": 0.0, "tokens": 0, "cost_usd": 0.0}
    for path in workflow.paths:
        n = counts.get(path.name, 0)
        uid, unit = by_path.get(path.name, (None, None))
        per_unit = None
        if unit is not None and unit.get("wall_s") is not None:
            per_unit = {k: unit.get(k) for k in ("wall_s", "tokens", "cost_usd")}
        projected = _times(per_unit, n) if n else {"wall_s": 0.0, "tokens": 0,
                                                   "cost_usd": 0.0}
        if n and projected is None:
            missing.append(path.name)
        _add(total, projected)
        paths.append({"name": path.name, "description": path.description,
                      "units": n, "pilot_unit": uid,
                      "status": unit["status"] if unit else "not measured",
                      "unit": per_unit, "projected": projected})
    shared = measured.get("shared")
    shared_out = None
    if shared is not None:
        shared_out = {"steps": shared["steps"], "status": shared["status"],
                      "projected": _times(shared, 1)}
        _add(total, shared_out["projected"])
    if total["wall_s"] is not None:
        total["wall_s"] = round(total["wall_s"], 1)
    if total["cost_usd"] is not None:
        total["cost_usd"] = round(total["cost_usd"], 4)
    return {"paths": paths, "shared": shared_out,
            "total": {**total, "units": len(workflow.units),
                      "complete": not missing, "missing": missing}}


def _base(full: Workflow, small: Workflow, pilot_dir: Path) -> dict:
    return {"schema": SCHEMA, "generated": _stamp(), "workflow": full.name,
            "run_dir": win(pilot_dir), "units": [u.id for u in small.units]}


def started_record(full: Workflow, small: Workflow, pilot_dir: Path) -> dict:
    return {**_base(full, small, pilot_dir), "state": RUNNING, "elapsed_s": None,
            "measured": None, "projection": None, "problem": None}


def finished_record(full: Workflow, small: Workflow, pilot_dir: Path,
                    status: str, summary: dict | None) -> dict:
    measured = measure(small, summary)
    started = _epoch((summary or {}).get("started"))
    finished = _epoch((summary or {}).get("finished"))
    elapsed = round(finished - started, 1) if started and finished else None
    return {**_base(full, small, pilot_dir), "state": status, "elapsed_s": elapsed,
            "measured": measured, "projection": project(full, measured),
            "problem": None}


def crashed_record(full: Workflow, small: Workflow, pilot_dir: Path,
                   problem: str) -> dict:
    return {**_base(full, small, pilot_dir), "state": CRASHED, "elapsed_s": None,
            "measured": None, "projection": None, "problem": problem}


def reproject(run_dir: Path, workflow: Workflow) -> dict | None:
    record = read_pilot(run_dir)
    if record is None or record.get("measured") is None:
        return record
    record = {**record, "generated": _stamp(),
              "projection": project(workflow, record["measured"])}
    write_pilot(run_dir, record)
    return record


def _span(entry: dict) -> float | None:
    start, end = _epoch(entry.get("started")), _epoch(entry.get("ended"))
    if start is None or end is None or end < start:
        return None
    return end - start


def _epoch(stamp: Any) -> float | None:
    if not isinstance(stamp, str) or not stamp:
        return None
    try:
        return _dt.datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def write_pilot(run_dir: Path, record: dict) -> Path:
    path = Path(run_dir) / PILOT_FILE
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def read_pilot(run_dir: Path) -> dict | None:
    try:
        data = json.loads((Path(run_dir) / PILOT_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return None
    return data


def _time(value: Any) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value < 60:
        return f"{value:.1f} s"
    return ohestimate._minutes(value)


def _tok(value: Any) -> str:
    return ohestimate._tokens(value)


def _usd(value: Any) -> str:
    return ohestimate._cost(value)


def _triple(part: dict | None) -> str:
    if not part:
        return ohtable.MISSING
    return f"{_time(part.get('wall_s'))}, {_tok(part.get('tokens'))} tokens, {_usd(part.get('cost_usd'))}"


def _head(record: dict) -> str:
    state = record.get("state")
    units = ", ".join(record.get("units") or [])
    if state == RUNNING:
        return (f"running the smallest unit of each path ({units}) in "
                f"{record.get('run_dir')}")
    projection = record.get("projection")
    if not projection:
        return f"{state}; nothing measured ({record.get('problem') or 'no summary'})"
    total = projection["total"]
    paths = sum(1 for p in projection["paths"] if p["units"])
    head = (f"projected {_triple(total)} for {total['units']} units on {paths} "
            f"path{'s' if paths != 1 else ''}; measured on "
            f"{len(record.get('units') or [])} pilot units in "
            f"{_time(record.get('elapsed_s'))}, pilot run {state}")
    if not total["complete"]:
        head += f"; not measured: {', '.join(total['missing'])}"
    return head


def render_text(record: dict) -> str:
    lines = [f"PILOT {record.get('workflow')}: {_head(record)}"]
    projection = record.get("projection")
    if not projection:
        return "\n".join(lines)
    lines += ["", ohestimate._row(["path", "units", "pilot unit", "status",
                                   "time per unit", "tokens per unit",
                                   "cost per unit", "projected time",
                                   "projected tokens", "projected cost"]),
              "|" + "---|" * 10]
    for p in projection["paths"]:
        unit, out = p["unit"] or {}, p["projected"] or {}
        lines.append(ohestimate._row([
            p["name"], p["units"], p["pilot_unit"] or ohtable.MISSING, p["status"],
            _time(unit.get("wall_s")), _tok(unit.get("tokens")),
            _usd(unit.get("cost_usd")) if unit else ohtable.MISSING,
            _time(out.get("wall_s")), _tok(out.get("tokens")),
            _usd(out.get("cost_usd")) if out else ohtable.MISSING]))
    shared = projection.get("shared")
    if shared:
        out = shared["projected"] or {}
        lines.append(ohestimate._row([
            "shared steps", ohtable.MISSING, ohtable.MISSING, shared["status"],
            ohtable.MISSING, ohtable.MISSING, ohtable.MISSING,
            _time(out.get("wall_s")), _tok(out.get("tokens")),
            _usd(out.get("cost_usd")) if out else ohtable.MISSING]))
    lines.append(f"time is the summed wall time of a unit's attempts; the pilot "
                 f"run is {record.get('run_dir')}")
    return "\n".join(lines)


def status_lines(run_dir: Path) -> list[str]:
    record = read_pilot(run_dir)
    if record is None:
        return []
    lines = [f"pilot: {_head(record)}"]
    for p in (record.get("projection") or {}).get("paths") or []:
        lines.append(f"pilot {p['name']}: {p['units']} units x {_triple(p['unit'])} "
                     f"= {_triple(p['projected'])} ({p['status']} on "
                     f"{p['pilot_unit'] or 'no unit'})")
    shared = (record.get("projection") or {}).get("shared")
    if shared:
        noun = "step" if shared["steps"] == 1 else "steps"
        lines.append(f"pilot shared steps: {shared['steps']} {noun}, "
                     f"{_triple(shared['projected'])} once ({shared['status']})")
    found = ohestimate.read_estimate(run_dir)
    if found:
        lines.append(ohestimate.render_text(found).splitlines()[0])
    return lines


def hold_line(run_dir: Path) -> str | None:
    record = read_pilot(run_dir)
    if record is None or record.get("state") != RUNNING:
        return None
    return (f"held: the pilot runs first · ohflow watch --run "
            f"{record.get('run_dir')}")


def page_view(run_dir: Path) -> dict | None:
    record = read_pilot(run_dir)
    if record is None:
        return None
    return {"state": record.get("state"), "run_dir": record.get("run_dir"),
            "units": record.get("units") or [],
            "elapsed_s": record.get("elapsed_s"),
            "problem": record.get("problem"),
            "projection": record.get("projection"),
            "head": _head(record)}

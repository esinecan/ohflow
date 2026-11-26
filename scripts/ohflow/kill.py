from __future__ import annotations

import json
import os
import time
from pathlib import Path

from . import attempts as ohattempts
from . import rundir
from .paths import win
from .run_log import RunLog

__all__ = ["REQUEST", "KILLABLE_KINDS", "KillRefused", "error_text", "pending",
           "take", "taken", "discard", "send", "wait"]

REQUEST = "kill-request.json"
KILLABLE_KINDS = ("agent", "command")


class KillRefused(RuntimeError):
    pass


def error_text(reason: str | None) -> str:
    return f"killed by ohflow kill: {reason}" if reason else "killed by ohflow kill"


def _read(path: Path) -> dict | None:
    try:
        request = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return request if isinstance(request, dict) else None


def pending(step_dir: Path, attempt: int | None) -> dict | None:
    request = _read(Path(step_dir) / REQUEST)
    if request is None or request.get("attempt") != attempt:
        return None
    return request


def take(step_dir: Path, request: dict, attempt_dir: Path) -> str:
    target = Path(attempt_dir) / REQUEST
    try:
        os.replace(Path(step_dir) / REQUEST, target)
    except OSError:
        target.write_text(json.dumps(request, indent=2), encoding="utf-8")
    return error_text(request.get("reason"))


def taken(attempt_dir: Path) -> dict:
    request = _read(Path(attempt_dir) / REQUEST) or {}
    return {"reason": request.get("reason"),
            "requested_at": request.get("requested_at")}


def discard(step_dir: Path, attempt: int | None = None) -> None:
    path = Path(step_dir) / REQUEST
    if attempt is not None and pending(step_dir, attempt) is None:
        return
    try:
        path.unlink()
    except OSError:
        pass


def _resolve(state, requested: str) -> str:
    if requested in state.steps:
        return requested
    matches = [c for c, rec in state.steps.items() if rec.step_id == requested]
    if len(matches) != 1:
        raise KillRefused(
            f"step {requested!r} is missing or ambiguous in the run log; name "
            f"its full coordinate. Steps with a record: "
            f"{', '.join(sorted(state.steps)) or 'none'}")
    return matches[0]


def send(run_dir: Path, step: str, reason: str | None) -> tuple[str, int, Path]:
    run_dir = Path(run_dir)
    if not (run_dir / "run-log.jsonl").is_file():
        raise KillRefused(f"no ohflow run log at {win(run_dir)}")
    pid = rundir.live_supervisor(run_dir)
    if pid is None:
        raise KillRefused(
            f"no live supervisor runs {win(run_dir)}, so nothing would read the "
            f"kill; a resume closes the attempts a dead supervisor left open")
    state = RunLog.replay(run_dir)
    coord = _resolve(state, step)
    rec = state.steps[coord]
    if rec.kind and rec.kind not in KILLABLE_KINDS:
        raise KillRefused(
            f"{coord} is a {rec.kind} step, which ends on its own; ohflow kill "
            f"ends an agent or a command step")
    started = ohattempts.executions(state, coord)
    newest = started[-1] if started else None
    if newest is None or newest.get("status") != "running" \
            or not isinstance(newest.get("attempt"), int):
        said = (f"its latest attempt {newest.get('attempt')} ended "
                f"{newest.get('status')}" if newest else "it never started")
        raise KillRefused(f"{coord} has no running attempt: {said}")
    attempt = newest["attempt"]
    step_dir = rundir.step_dir(run_dir, coord)
    step_dir.mkdir(parents=True, exist_ok=True)
    request = {"attempt": attempt, "reason": reason or None,
               "requested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "supervisor_pid": pid}
    scratch = step_dir / (REQUEST + ".tmp")
    scratch.write_text(json.dumps(request, indent=2), encoding="utf-8")
    os.replace(scratch, step_dir / REQUEST)
    return coord, attempt, step_dir / REQUEST


def _finish(run_dir: Path, coord: str, attempt: int) -> dict | None:
    found = None
    for rec in RunLog(run_dir).read():
        if (rec.get("event") == "attempt_finished" and rec.get("coord") == coord
                and rec.get("attempt") == attempt):
            found = rec.get("payload") or {}
    return found


def wait(run_dir: Path, coord: str, attempt: int, timeout_s: float,
         poll_s: float = 0.5) -> dict | None:
    deadline = time.monotonic() + max(0.0, timeout_s)
    while True:
        payload = _finish(Path(run_dir), coord, attempt)
        if payload is not None:
            return payload
        if time.monotonic() >= deadline:
            return None
        time.sleep(poll_s)

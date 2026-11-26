"""Durable state. `run-log.jsonl` is append-only and it is the truth.

Every transition is written before it is acted on. That is what makes the
supervisor killable at any instant and resumable afterwards. `board.md` is
derived from the run log and rewritten after every transition. `rundir.py` reads
a run directory.
"""

from __future__ import annotations

import datetime as _dt
import json
import threading
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterator

__all__ = ["RunLog", "RunState", "StepRecord", "utcnow", "TERMINAL",
           "STATUSES", "SYNTHETIC_ATTEMPT"]

#: The attempt number an `attempt_finished` carries when nothing was ever started
#: for it: a cached step, a step the abort reached before it launched, work the
#: attempt history refused to start again, a fault with no execution open.
#:
#: Real attempts are numbered from 1, so this can never name one. That is the
#: whole point. `replay` matches a finish to an execution on the pair
#: (coordinate, attempt), and a synthetic finish carrying a real number used to
#: overwrite the record of an execution that genuinely ran.
SYNTHETIC_ATTEMPT = 0

#: Events that say nothing about the run going again after a `run_finished`.
_NOT_WORK_EVENTS = frozenset({"run_started", "run_finished",
                              "run_log_recovered"})

STATUSES = (
    "pending", "running", "passed", "failed",
    "timeout", "quarantined", "skipped", "cached", "deferred",
)
# `deferred` is terminal for this attempt and it is not ok. A resume therefore
# re-runs exactly the deferred steps, because the cache only keeps `ok` ones.
TERMINAL = frozenset({"passed", "failed", "timeout", "quarantined", "skipped",
                      "cached", "deferred"})
EVENTS = (
    "run_started", "phase_started", "attempt_started", "attempt_finished",
    "gate_ran", "phase_settled", "run_finished",
    # A verdict is closed once. Decisions learned after that verdict have
    # their own event, so run log readers never count one attempt twice.
    "retry_decided",
    # Worktrees are created at the first phase that uses them, not at run
    # start. Their facts enter durable state as each one becomes available.
    "worktree_ready",
    # Appending after a torn tail first truncates the bad bytes, then records
    # that repair durably before it writes the caller's event.
    "run_log_recovered",
    # A phase that settled `deferred` is being auto-resumed again, automatically.
    "phase_resumed",
    # This work failed twice unchanged and will not be started again in this
    # run directory, by an auto-resume pass or by a manual `--resume`.
    "work_excluded",
    "token_budget",
)


def utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class StepRecord:
    coord: str
    step_id: str = ""
    kind: str = ""
    status: str = "pending"
    attempt: int = 0
    started: str | None = None
    ended: str | None = None
    fingerprint: str | None = None
    result_path: str | None = None
    handover_path: str | None = None
    handover_sha256: str | None = None
    gate: dict[str, Any] | None = None
    wall_seconds: float | None = None
    branch: str | None = None
    head_sha: str | None = None
    error: str | None = None
    failure_class: str | None = None       # transient | structural | None
    note: str | None = None
    # True when the run's abort killed this execution. It may already have
    # called the provider; it reached no verdict, and that is why no bound
    # counts it. `ohflow.attempts` keeps abort victims apart from genuine
    # provider deferrals for exactly this reason.
    abort_victim: bool = False
    # Why the engine did or did not start another attempt, in one line.
    retry_decision: str | None = None
    killed: dict[str, Any] | None = None

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL

    @property
    def ok(self) -> bool:
        return self.status in ("passed", "cached")

    @property
    def rerunnable(self) -> bool:
        """The step holds its assignment: it reached no verdict of its own."""
        return self.status == "deferred"


@dataclass
class RunState:
    run_id: str = ""
    workflow_name: str = ""
    started: str | None = None
    finished: str | None = None
    status: str = "running"
    steps: dict[str, StepRecord] = field(default_factory=dict)
    phases: dict[str, dict[str, Any]] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    #: Every execution the run log recorded, in order, for the attempt history to count.
    #: `steps` keeps only the latest record per coordinate, which cannot answer
    #: "how many times has this work been tried".
    executions: list[dict[str, Any]] = field(default_factory=list)
    #: "<coord>@<fingerprint>" -> the payload of the `work_excluded` event.
    exclusions: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: When the provider cooldown ends, as `YYYY-MM-DDTHH:MM:SSZ`, and how many
    #: transient hits set it. Both are in the run log so a run resumed in a new
    #: process does not start by asking the provider the question it was just
    #: rate-limited for.
    cooldown_until: str | None = None
    transient_hits: int = 0

    def record(self, coord: str) -> StepRecord:
        rec = self.steps.get(coord)
        if rec is None:
            rec = StepRecord(coord=coord)
            self.steps[coord] = rec
        return rec

    def passed_fingerprints(self) -> dict[str, str]:
        """coord -> fingerprint, for every step that finished in a good state."""
        return {c: r.fingerprint for c, r in self.steps.items()
                if r.ok and r.fingerprint}

    def to_board(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "workflow": self.workflow_name,
            "status": self.status,
            "started": self.started,
            "finished": self.finished,
            "phases": self.phases,
            "steps": {c: asdict(r) for c, r in sorted(self.steps.items())},
            "executions": self.executions,
            "exclusions": self.exclusions,
            "cooldown_until": self.cooldown_until,
            "transient_hits": self.transient_hits,
            "meta": self.meta,
        }


class RunLog:
    """Append-only writer plus a pure replay. One instance per run directory."""

    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)
        self.path = self.run_dir / "run-log.jsonl"
        self._lock = threading.Lock()
        self.recovery: dict[str, Any] | None = None

    # ------------------------------------------------------------- writing

    def append(self, event: str, *, coord: str | None = None,
               attempt: int | None = None, payload: dict[str, Any] | None = None) -> dict:
        if event not in EVENTS:
            raise ValueError(f"unknown run log event {event!r}")
        rec = {"ts": utcnow(), "event": event}
        if coord is not None:
            rec["coord"] = coord
        if attempt is not None:
            rec["attempt"] = attempt
        rec["payload"] = payload or {}
        line = json.dumps(rec, sort_keys=True)
        with self._lock:
            self.run_dir.mkdir(parents=True, exist_ok=True)
            recovery = self._repair_torn_tail()
            with self.path.open("a", encoding="utf-8") as fh:
                if recovery:
                    repaired = {
                        "ts": utcnow(), "event": "run_log_recovered",
                        "payload": recovery,
                    }
                    fh.write(json.dumps(repaired, sort_keys=True) + "\n")
                fh.write(line + "\n")
                fh.flush()
        return rec

    # ------------------------------------------------------------- reading

    def read(self) -> Iterator[dict]:
        if not self.path.exists():
            return iter(())
        return self._iter()

    def _iter(self) -> Iterator[dict]:
        lines = self.path.read_bytes().splitlines(keepends=True)
        nonempty = [i for i, line in enumerate(lines) if line.strip()]
        last = nonempty[-1] if nonempty else -1
        for i, raw in enumerate(lines):
            raw = raw.strip()
            if not raw:
                continue
            try:
                line = raw.decode("utf-8")
                yield json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError):
                if i != last:
                    raise
                self.recovery = {
                    "torn_final_line": True,
                    "line": i + 1,
                    "bytes": len(raw),
                }

    def _repair_torn_tail(self) -> dict[str, Any] | None:
        """Make a following append safe after a supervisor-torn final record.

        A valid final record without its newline only needs the delimiter. An
        invalid final record is truncated at its byte offset. Corruption before
        the final non-empty line is deliberately left for replay to reject.
        """
        if not self.path.exists():
            return None
        data = self.path.read_bytes()
        if not data:
            return None
        lines = data.splitlines(keepends=True)
        indexes = [i for i, raw in enumerate(lines) if raw.strip()]
        if not indexes:
            return None
        i = indexes[-1]
        raw = lines[i]
        start = sum(len(part) for part in lines[:i])
        try:
            json.loads(raw.strip().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            with self.path.open("r+b") as fh:
                fh.truncate(start)
            recovery = {"torn_final_line": True, "line": i + 1,
                        "bytes": len(raw.strip()), "action": "truncated"}
            self.recovery = recovery
            return recovery
        if not raw.endswith((b"\n", b"\r")):
            with self.path.open("ab") as fh:
                fh.write(b"\n")
        return None

    @classmethod
    def replay(cls, run_dir: Path) -> RunState:
        """Rebuild the board from the run log file alone."""
        j = cls(run_dir)
        state = cls.replay_records(j.read())
        if j.recovery:
            state.meta["run_log_recovery"] = dict(j.recovery)
        return state

    @staticmethod
    def replay_records(records) -> RunState:
        """Rebuild the board from records already parsed.

        `replay` reads the file and calls this. The run dashboard calls it
        directly, because it reads the run log from its last byte offset and
        already holds every record; reading the whole file again on each poll
        would cost a full parse per refresh for no new information.
        """
        state = RunState()
        for rec in records:
            ev = rec.get("event")
            payload = rec.get("payload") or {}
            coord = rec.get("coord")
            if state.finished and ev not in _NOT_WORK_EVENTS:
                # A resume appends no run-level event. Work after a
                # `run_finished` is the run going again.
                state.status = "running"
                state.finished = None
            if ev == "run_started":
                state.run_id = payload.get("run_id", state.run_id)
                state.workflow_name = payload.get("workflow", state.workflow_name)
                state.started = rec.get("ts")
                state.meta.update(payload.get("meta") or {})
                state.status = "running"
            elif ev == "phase_started":
                state.phases[coord or payload.get("phase", "")] = {
                    "name": payload.get("name"),
                    "status": "running",
                    "started": rec.get("ts"),
                    "policy": payload.get("policy"),
                    "min_success": payload.get("min_success"),
                    # The limit the engine actually applied, not the one the
                    # workflow asked for. A run log from before this key replays
                    # with None, which the board renders as a dash.
                    "max_parallel": payload.get("max_parallel"),
                }
            elif ev == "attempt_started":
                r = state.record(coord)
                r.status = "running"
                r.attempt = rec.get("attempt", r.attempt or 1)
                r.started = rec.get("ts")
                r.ended = None
                r.handover_path = None
                r.handover_sha256 = None
                r.step_id = payload.get("step_id", r.step_id)
                r.kind = payload.get("kind", r.kind)
                r.fingerprint = payload.get("fingerprint", r.fingerprint)
                r.branch = payload.get("branch", r.branch)
                r.note = payload.get("note", r.note)
                r.abort_victim = False
                r.retry_decision = None
                state.executions.append({
                    "coord": coord,
                    "attempt": rec.get("attempt", r.attempt),
                    "fingerprint": payload.get("fingerprint"),
                    # `initial`, `reattach`, `retry` or `auto_resume`. A
                    # second `attempt_started` with the same attempt number is
                    # the reattach continuing that attempt. An older run log
                    # carries no kind, and the attempt history reads that as
                    # `initial`.
                    "start_kind": payload.get("start_kind") or "initial",
                    "previous_fingerprint": payload.get("previous_fingerprint"),
                    # True only for an execution an `attempt_started` opened. A
                    # cached step, an abort victim that never got its turn and
                    # a policy relabel all write `attempt_finished` alone, and
                    # none of them spent an agent.
                    "started": True,
                    "started_at": rec.get("ts"),
                    "status": "running",
                    "failure_class": None,
                    "abort_victim": False,
                })
            elif ev == "gate_ran":
                r = state.record(coord)
                r.gate = payload.get("gate")
            elif ev == "attempt_finished":
                r = state.record(coord)
                attempt = rec.get("attempt", SYNTHETIC_ATTEMPT)
                if SYNTHETIC_ATTEMPT < attempt < r.attempt:
                    # A finish for an attempt older than the one the step is
                    # on closes that execution and says nothing about the
                    # step. A resume writes one for an attempt a supervisor
                    # death left open, and the step may have passed since.
                    for ex in reversed(state.executions):
                        if ex["coord"] == coord \
                                and ex.get("attempt") == attempt:
                            ex.update({
                                "status": payload.get("status", "failed"),
                                "ended": rec.get("ts"),
                                "failure_class": payload.get("failure_class"),
                                "abort_victim": bool(
                                    payload.get("abort_victim")),
                                "retry_decision": payload.get(
                                    "retry_decision"),
                            })
                            break
                    continue
                r.status = payload.get("status", "failed")
                # A synthetic finish leaves the attempt count alone. It says
                # what became of the step, not which execution said so, and
                # writing 0 here would report the step as never attempted.
                if rec.get("attempt"):
                    r.attempt = rec["attempt"]
                r.ended = rec.get("ts")
                r.fingerprint = payload.get("fingerprint", r.fingerprint)
                r.result_path = payload.get("result_path", r.result_path)
                r.handover_path = payload.get("handover_path", r.handover_path)
                r.handover_sha256 = payload.get("handover_sha256", r.handover_sha256)
                r.gate = payload.get("gate", r.gate)
                r.wall_seconds = payload.get("wall_seconds", r.wall_seconds)
                r.head_sha = payload.get("head_sha", r.head_sha)
                r.error = payload.get("error")
                r.failure_class = payload.get("failure_class")
                r.step_id = payload.get("step_id", r.step_id)
                r.kind = payload.get("kind", r.kind)
                r.abort_victim = bool(payload.get("abort_victim"))
                r.retry_decision = payload.get("retry_decision")
                r.killed = payload.get("killed")
                # The cooldown a transient deferral set. The latest wake time
                # wins, and the hit count only ever rises, so a replay of the
                # whole run log reaches the same state the engine held.
                wake = payload.get("cooldown_until")
                if wake and (state.cooldown_until is None
                             or wake > state.cooldown_until):
                    state.cooldown_until = wake
                hits = payload.get("transient_hits")
                if isinstance(hits, int) and hits > state.transient_hits:
                    state.transient_hits = hits
                # Close the execution this event belongs to, matched on the
                # pair (coordinate, attempt). Matching on the coordinate alone
                # let a cached or policy-relabelled finish close an older
                # interrupted attempt that was still open, and a second finish
                # for one attempt appended a second execution and doubled its
                # failure.
                match = None
                for ex in reversed(state.executions):
                    if ex["coord"] == coord and ex.get("attempt") == attempt:
                        match = ex
                        break
                if match is not None:
                    match.update({
                        "status": r.status,
                        "ended": rec.get("ts"),
                        "failure_class": r.failure_class,
                        "abort_victim": r.abort_victim,
                        "retry_decision": r.retry_decision,
                    })
                else:
                    # No `attempt_started` ever opened this attempt. A cached step,
                    # an abort victim recorded before it got its turn, a step
                    # the phase policy settled without running it. None of them
                    # spent an agent, so `started` is False and the attempt history
                    # passes over it.
                    state.executions.append({
                        "coord": coord, "attempt": attempt,
                        "fingerprint": r.fingerprint, "start_kind": "none",
                        "previous_fingerprint": None,
                        "started": False, "started_at": None,
                        "ended": rec.get("ts"),
                        "status": r.status, "failure_class": r.failure_class,
                        "abort_victim": r.abort_victim,
                        "retry_decision": r.retry_decision,
                    })
            elif ev == "work_excluded":
                key = f"{coord}@{payload.get('fingerprint')}"
                state.exclusions[key] = dict(payload)
            elif ev == "retry_decided":
                r = state.record(coord)
                r.retry_decision = payload.get("retry_decision")
                attempt = rec.get("attempt", SYNTHETIC_ATTEMPT)
                for ex in reversed(state.executions):
                    if ex.get("coord") == coord \
                            and ex.get("attempt") == attempt:
                        ex["retry_decision"] = r.retry_decision
                        break
            elif ev == "worktree_ready":
                name = payload.get("name")
                if name:
                    state.meta.setdefault("worktrees", {})[name] = dict(
                        payload.get("facts") or {})
            elif ev == "run_log_recovered":
                state.meta["run_log_recovery"] = dict(payload)
            elif ev == "token_budget":
                kind = payload.get("kind")
                if kind == "limit":
                    state.meta["token_budget"] = {
                        "limit_tokens": payload.get("limit_tokens"),
                        "reserve_tokens": payload.get("reserve_tokens")}
                elif kind == "overshoot":
                    state.meta.setdefault("token_overshoots", []).append(
                        {k: v for k, v in payload.items() if k != "kind"})
                elif kind == "refused":
                    state.meta.setdefault("token_refusals", []).append(
                        {"coord": coord, "attempt": rec.get("attempt"),
                         "reason": payload.get("reason")})
            elif ev == "phase_resumed":
                entry = state.phases.setdefault(
                    coord or payload.get("phase", ""), {})
                entry["status"] = "running"
                entry["auto_resumes"] = payload.get("pass", entry.get("auto_resumes", 0))
            elif ev == "phase_settled":
                key = coord or payload.get("phase", "")
                entry = state.phases.setdefault(key, {})
                entry.update({
                    "status": payload.get("status", "settled"),
                    "settled_at": rec.get("ts"),
                    "steps": payload.get("steps"),
                    "good": payload.get("good"),
                    "total": payload.get("total"),
                    "min_success": payload.get("min_success",
                                               entry.get("min_success")),
                })
            elif ev == "run_finished":
                state.finished = rec.get("ts")
                state.status = payload.get("status", "finished")
        return state

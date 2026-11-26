"""The dashboard's graph data layer: one run, read as graph truth.

Four fixed GET endpoints answer from this module:

* `/api/workflow`   the whole run as the UI's graph truth: planned phases and
                    steps, every execution attempt, the edges that say why one
                    thing followed another, run segments, cached evaluations,
                    the campaign rounds where they exist, and diagnostics that
                    name what this server does not know.
* `/api/plan`       the declared plan, whole: every phase and step of
                    `workflow.json` with the full brief, the position block,
                    the gate checks in words, the handover contract, the
                    schema, the command and the limits, plus the totals and
                    the estimate. Fetched once, never polled.
* `/api/transcript` one attempt's full transcript, paged from the top, safe to
                    poll while the file appends, redacted before it leaves.
* `/api/evidence`   one attempt's recorded evidence: its gate, the events that
                    name it, its final message, and the files it left behind,
                    from a whitelist only.

Two source formats are supported, and nothing else:

* the current run directory (`workflow.json`, `run-log.jsonl`, attempt
  directories under `phases/<phase>/<step>/attempts/NN/`), and
* the `ohflow.dashboard-case/1` evidence packet (`docs/dashboard-basis`), a
  historical export of the real `m7-smoke-fixes` run whose journal names
  differ: `step_started` where the run log writes `attempt_started`, `lane`
  where a workflow writes `harness_executor`, `worker` where a workflow writes
  `kind: agent`. The packet's own normalized fields are read as recorded; the
  original names stay attached to every event.

Rules this module keeps, and why:

* **It only reads.** A viewer that wrote would be one more thing a crash could
  leave half-done, and the packet is evidence: a byte changed there is a
  source quietly rewritten. `dashboard.start` skips `dashboard.json` for a
  packet for the same reason.
* **Nothing from the request joins a path.** A coordinate must name a step of
  this run, an attempt must name a recorded execution, an artifact id must map
  to a whitelist entry, and every file is checked to resolve inside the source
  root, so a symlink cannot walk out either.
* **Relationships are recorded, never inferred.** A retry edge exists because
  the run log or the packet records `start_kind: retry` (the packet: its
  retry proof), not because attempt numbers are adjacent. A phase barrier is
  the declared phase order; `depends_on` is the declared step dependency, and
  the two are separate edges with separate sources. Run segments are context:
  an attempt in a later segment is not caused by one in an earlier one.
* **Unknown stays unknown.** A record without a timestamp carries `ts: null`.
  An idle threshold is labelled a threshold, never a proven stall.
* **Every string that leaves passes `redact`.** The live read-out's secret
  shapes and structured secret fields are applied recursively.

Payload control: graph/evidence strings are capped, transcript page sizes and
response content are bounded, and unusually large transcript records use a
lossless continuation contract.  The workflow payload carries no transcript
records - an invocation carries its gate verdict, its recorded claim (a
bounded final-message line) and, while it runs, its latest observed activity.
"""

from __future__ import annotations

import json
import math
import time
from collections import Counter
from pathlib import Path
from typing import Any

from . import attempts as ohattempts
from . import budget as ohbudget
from . import attention as ohattention
from . import coords
from . import dashboard_transcript as transcript_io
from . import estimate as ohestimate
from . import pilot as ohpilot
from . import live, rundir, tool_output
from .activity import FILES, epoch, first_line, hms, iso, one_line, read_json
from .run_log import RunLog, RunState, StepRecord

__all__ = ["WORKFLOW_SCHEMA", "TRANSCRIPT_SCHEMA", "EVIDENCE_SCHEMA",
           "PACKET_SCHEMA", "PLAN_SCHEMA", "is_packet", "open_source",
           "workflow_data", "agent_view", "plan_data", "plan_stamp",
           "transcript_data", "evidence_data"]

WORKFLOW_SCHEMA = "ohflow.dashboard/1"
PLAN_SCHEMA = "ohflow.plan/1"
TRANSCRIPT_SCHEMA = "ohflow.transcript/1"
EVIDENCE_SCHEMA = "ohflow.evidence/1"
#: The evidence packet's own schema (`docs/dashboard-basis/case.json`).
PACKET_SCHEMA = "ohflow.dashboard-case/1"

#: Transcript paging. One query cannot render a whole session.
DEFAULT_LIMIT = 150
MAX_LIMIT = 400
#: Any single graph/evidence string. Transcript content is lossless and uses
#: continuation chunks instead of this cap.
STRING_CAP = 2000
#: Event payloads are context, not documents. A payload bigger than this is
#: replaced by a note naming its size, so one event cannot dominate the graph.
PAYLOAD_CAP = 400
PAYLOAD_JSON_MAX = 1200
#: The workflow event list keeps the recent past, oldest first.
EVENT_MAX = 600
#: Evidence events for one attempt.
ATTEMPT_EVENT_MAX = 40
#: A final message is a claim a reader reads whole; this is generous.
FINAL_MESSAGE_CAP = 8000
#: One artifact's text content.
ARTIFACT_TEXT_CAP = 32000
#: Log artifacts show their tail, like the live page's card.
LOG_TAIL_LINES = 60
MAX_ARTIFACTS = 40
#: Attempt numbers are directories; nothing real reaches four digits.
MAX_ATTEMPT = 999

#: A run whose supervisor is alive and may still start work: the page polls.
_LIVE_RUN = frozenset({"running", rundir.STARTING, rundir.HELD})
_TERMINAL_OK = frozenset({"passed", "cached"})
_RESTART_KINDS = frozenset({"retry", "auto_resume"})
#: The run-log events the digest turns into sentences: every verdict, every
#: decision after a verdict, every settlement, and the end of the run.
_DIGEST_EVENTS = frozenset({"attempt_finished", "retry_decided",
                            "work_excluded", "phase_settled", "run_finished"})


# ------------------------------------------------------------------ shaping


def _cut(value: Any, limit: int = STRING_CAP) -> Any:
    """One string, capped. The cap is named, so a reader knows it saw all."""
    if not isinstance(value, str):
        return value
    if len(value) <= limit:
        return value
    return value[:limit] + f"…[capped at {limit} of {len(value)} chars]"


def _cap_tree(obj: Any, limit: int = STRING_CAP, lists: int | None = None) -> Any:
    """Every string in a JSON-shaped value, capped; keys are left alone."""
    if isinstance(obj, str):
        return _cut(obj, limit)
    if isinstance(obj, dict):
        return {k: _cap_tree(v, limit, lists) for k, v in obj.items()}
    if isinstance(obj, list):
        out = [_cap_tree(v, limit, lists) for v in obj]
        if lists is not None and len(out) > lists:
            out = out[:lists] + [f"…[{len(out) - lists} more entries]"]
        return out
    return obj


def _signal(value: float | None, amber: float | None, red: float | None) -> str:
    if value is None or amber is None or red is None:
        return "ok"
    if value > red:
        return "red"
    if value > amber:
        return "amber"
    return "ok"


# ------------------------------------------------------------- safe files


def _inside(root: Path, path: Path) -> bool:
    """Whether `path` resolves inside `root`. A symlink cannot walk out."""
    try:
        return path.resolve().is_relative_to(root.resolve())
    except (OSError, ValueError):
        return False


def _text_of(path: Path, cap: int = ARTIFACT_TEXT_CAP) -> str | None:
    try:
        data = path.read_bytes()[: cap * 4]
    except OSError:
        return None
    return _cut(data.decode("utf-8", "replace"), cap)


# ---------------------------------------------------------------- dispatch


def is_packet(run_dir: Path) -> bool:
    """Whether this directory is an `ohflow.dashboard-case/1` evidence packet.

    A packet is recorded evidence, so the dashboard never writes into one:
    `dashboard.start` skips its `dashboard.json` here.
    """
    try:
        case = json.loads((Path(run_dir) / "case.json").read_text(
            encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(case, dict) and case.get("schema") == PACKET_SCHEMA


def open_source(run_dir: Path):
    """The reader for this directory: a run, a packet, or None for neither."""
    run_dir = Path(run_dir)
    if is_packet(run_dir):
        source = _PacketSource(run_dir)
    elif (run_dir / "run-log.jsonl").exists() \
            or (run_dir / "workflow.json").exists():
        source = _RunSource(run_dir)
    else:
        return None
    source.load()
    return source


# ============================================================== run source


class _RunSource:
    """The current format: `workflow.json` + `run-log.jsonl` + attempt dirs."""

    kind = "run"

    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)
        self.entries: list[dict] = []
        self.unreadable = 0
        self.state = RunState()
        self.run: rundir.Run | None = None
        self._model: dict | None = None
        self._inv_memo: tuple[float, list] | None = None

    # ---- loading

    def load(self) -> None:
        if self.run is not None:
            return
        records = []
        try:
            raw_lines = (self.run_dir / "run-log.jsonl").read_bytes().splitlines()
        except OSError:
            raw_lines = []
        last = max((i for i, l in enumerate(raw_lines) if l.strip()),
                   default=-1)
        for i, raw in enumerate(raw_lines):
            if not raw.strip():
                continue
            try:
                rec = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                if i != last:            # a torn final line is normal
                    self.unreadable += 1
                continue
            if isinstance(rec, dict):
                self.entries.append({"rec": rec, "line": i + 1})
                records.append(rec)
        self.state = RunLog.replay_records(records)
        self.run = rundir.open_run(self.run_dir, state=self.state,
                                   records=records)

    # ---- the planned shape

    def model(self) -> dict:
        if self._model is not None:
            return self._model
        wf = self.run.workflow
        by_id: dict[str, str] = {}
        phases: list[dict] = []
        raw_steps: list[dict] = []
        for ph in wf["phases"]:
            entry = self.state.phases.get(ph["coord"]) or {}
            begun = "started" in entry
            phases.append({
                "coord": ph["coord"], "index": ph["index"],
                "name": ph["name"],
                "state": "waiting" if not begun
                else (entry.get("status") or "running"),
                "max_parallel": entry.get("max_parallel")
                or ph["raw"].get("max_parallel"),
                "policy": entry.get("policy") or ph["raw"].get("on_step_failure"),
                "min_success": entry.get("min_success",
                                         ph["raw"].get("min_success")),
                "auto_resumes": int(entry.get("auto_resumes") or 0),
                "steps": [st["coord"] for st in ph["steps"]],
                # The declared policy, as `workflow.json` states it, for the
                # reviewer of a run that has not started. `policy` above is
                # the one the run log recorded once the phase began.
                "plan": {
                    "on_step_failure": ph["raw"].get("on_step_failure"),
                    "min_success": ph["raw"].get("min_success"),
                    "max_parallel": ph["raw"].get("max_parallel"),
                },
            })
            for st in ph["steps"]:
                by_id[st["id"]] = st["coord"]
                raw_steps.append({"coord": st["coord"], "phase": ph["coord"],
                                  "phase_index": ph["index"], "id": st["id"],
                                  "raw": st["raw"] or {}})
        self._model = {"workflow": wf, "phases": phases,
                       "raw_steps": raw_steps, "by_id": by_id,
                       "by_coord": {s["coord"]: s for s in raw_steps}}
        return self._model

    # ---- helpers

    def _names(self) -> tuple[dict, dict]:
        model = self.model()
        names = {s["coord"]: s["id"] for s in model["raw_steps"]}
        phase_names = {p["coord"]: p["name"] for p in model["phases"]}
        return names, phase_names

    def status(self) -> str:
        """The run's status word.

        The run log names it once a line exists. Before that, the files do:
        `held`, `starting`, the stop `exit.json` records, or `not started`.
        `RunState` defaults to `running`, so asking the replayed state about
        an empty run log would call a held run running.
        """
        if not self.entries:
            return self.run.status_without_run_log
        return self.run.status

    def _live_run(self) -> bool:
        return self.status() in _LIVE_RUN

    def _held(self) -> bool:
        return self.status() == rundir.HELD

    def _auto_resume(self) -> int:
        """The auto-resume budget the run used: the CLI override the run log
        recorded, else the workflow's own."""
        wf = self.run.workflow
        return int(self.state.meta.get("auto_resume", wf.get("auto_resume"))
                   or 0)

    def _cooldown(self, now: float) -> float | None:
        """When the provider cooldown ends, while one is active in a live run."""
        wake = epoch(self.state.cooldown_until)
        if wake is None or wake <= now or not self._live_run():
            return None
        return wake

    def _deferred_wait(self, coord: str, raw: dict, live_run: bool
                       ) -> tuple[str, str | None, str]:
        """What a deferred step waits for, in the read-out's order.

        Live and within budget: an auto-resume pass. Stopped and not excluded:
        a resume. Otherwise nothing: the step is done as `deferred`, and the
        reason names the budget the engine ran out of, which is what the
        attention strip and the lane counts read.
        """
        rec = self.state.steps.get(coord)
        fingerprint = rec.fingerprint if rec else None
        excluded = bool(fingerprint
                        and f"{coord}@{fingerprint}" in self.state.exclusions)
        if live_run:
            retry = raw.get("retry") if isinstance(raw.get("retry"), dict) else {}
            allowed, why = ohattempts.may_start(
                self.state, coord, fingerprint, start_kind="auto_resume",
                retry_max=int(retry.get("max") or 0),
                auto_resume=self._auto_resume())
            if allowed:
                return ("waiting", "auto_resume",
                        "deferred; an auto-resume pass may rerun it")
            return "done", None, f"deferred: {why}"
        if excluded:
            return "done", None, "deferred (excluded)"
        return ("waiting", "resume",
                "deferred: the run stopped before a verdict")

    def _step_agent(self, raw: dict) -> dict:
        agent = raw.get("agent")
        return agent if isinstance(agent, dict) else {}

    @staticmethod
    def _step_plan(raw: dict, agent: dict) -> dict:
        """What a reviewer reads before the step runs, from `workflow.json`.

        Every field is the declared one, not an observed one: the brief the
        agent will receive, the tool policy and model, the write scope and
        worktree, the retry policy, the handovers it consumes, its
        dependencies, the gate check names, its limits and its own handover
        spec. `_cap_tree` caps the brief with every other graph string.
        """
        model = agent.get("model")
        gate = raw.get("gate") if isinstance(raw.get("gate"), dict) else {}
        return {
            "brief": agent.get("brief"),
            "tool_policy": agent.get("tools"),
            "harness_executor": agent.get("harness_executor"),
            "model": model.get("model") if isinstance(model, dict) else None,
            "write_scope": list(raw.get("write_scope") or []),
            "worktree": raw.get("worktree"),
            "retry": raw.get("retry"),
            "consumes": list(raw.get("consumes") or []),
            "depends_on": list(raw.get("depends_on") or []),
            "gate": [str(c.get("name") if isinstance(c, dict) else c)
                     for c in gate.get("checks") or []],
            "limits": {
                "execution_timeout_s": raw.get("execution_timeout_s"),
                "stall_timeout_s": raw.get("stall_timeout_s"),
                "max_iterations": agent.get("max_iterations"),
            },
            "handover": raw.get("handover"),
        }

    def _step_kind(self, raw: dict, coord: str) -> str:
        rec = self.state.steps.get(coord)
        return raw.get("kind") or (rec.kind if rec else None) or "agent"

    def _gate_view(self, payload: dict) -> dict | None:
        gate = payload.get("gate")
        if not isinstance(gate, dict):
            return None
        failed = [str(c.get("name")) for c in gate.get("checks") or []
                  if isinstance(c, dict) and not c.get("passed")]
        return {"passed": bool(gate.get("passed")), "failed": failed}

    # ---- invocations

    def invocations(self, now: float) -> list[dict]:
        """Every recorded execution, ordered by start (finish for cached),
        tie-broken by coordinate then attempt."""
        memo = self._inv_memo
        if memo is not None and memo[0] == now:
            return list(memo[1])
        invocations = self._build_invocations(now)
        self._inv_memo = (now, invocations)
        return list(invocations)

    def _build_invocations(self, now: float) -> list[dict]:
        model = self.model()
        finishes = self.run.finishes
        live_run = self._live_run()
        out: list[dict] = []
        for ordinal, ex in enumerate(self.state.executions):
            coord, attempt = ex.get("coord"), ex.get("attempt")
            step = model["by_coord"].get(coord)
            if step is None or not isinstance(attempt, int):
                continue
            fin = finishes.get((coord, attempt))
            payload = (fin or {}).get("payload") or {}
            started = epoch(ex.get("started_at"))
            ended = epoch(ex.get("ended"))
            status = ex.get("status") or "running"
            if status == "running" and not live_run:
                status = "interrupted"
            if status == "cached":
                launch = "cached"
            elif ex.get("started"):
                launch = "agent" \
                    if self._step_kind(step["raw"], coord) == "agent" \
                    else "process"
            else:
                # A finish with no start: a cached evaluation, an abort victim
                # recorded before its turn, a policy relabel. Nothing ran.
                launch = "prepared"
            wall = payload.get("wall_seconds")
            if not isinstance(wall, (int, float)):
                if status == "running" and started is not None:
                    wall = now - started
                elif started is not None and ended is not None:
                    wall = ended - started
                else:
                    wall = None
            cause, short = (None, None)
            if status not in _TERMINAL_OK and status not in ("running",):
                cause, short = live._cause(payload)
                if status == "interrupted":
                    cause = ("the supervisor stopped before this attempt "
                             "finished")
                    short = "interrupted"
            inv: dict[str, Any] = {
                "id": f"{coord}@{attempt}",
                "coord": coord, "attempt": attempt,
                "step_id": step["id"], "phase": step["phase"],
                "kind": self._step_kind(step["raw"], coord),
                "role": self._step_agent(step["raw"]).get("role") or None,
                "harness_executor":
                    self._step_agent(step["raw"]).get("harness_executor"),
                "launch": launch, "status": status,
                "started": iso(started), "finished": iso(ended),
                "wall_s": round(wall, 1) if isinstance(wall, (int, float))
                else None,
                "start_kind": ex.get("start_kind") or "initial",
                "fingerprint": ex.get("fingerprint"),
                "previous_fingerprint": ex.get("previous_fingerprint"),
                "gate": self._gate_view(payload),
                "final_message": self._final_line(coord, attempt),
                "retry_decision": ex.get("retry_decision"),
                "cause": cause, "short_cause": short,
                "error": first_line(payload.get("error"), 240) or None,
                "ordinal": ordinal,
                "order_ts": started if started is not None else ended,
                "elapsed_s": None, "activity": None, "health": None,
            }
            if status == "running" and live_run and ex.get("started"):
                self._add_live_fields(inv, step, now)
            out.append((inv.pop("order_ts"), inv))
        out.sort(key=lambda pair: (pair[0] is None, pair[0] or 0.0,
                                   pair[1]["coord"], pair[1]["attempt"]))
        ordered = [pair[1] for pair in out]
        self._link_cached(ordered)
        return ordered

    @staticmethod
    def _link_cached(invocations: list[dict]) -> None:
        """A cached evaluation points at the earlier attempt its gate reuses."""
        for i, inv in enumerate(invocations):
            if inv["status"] != "cached":
                continue
            linked = None
            for other in reversed(invocations[:i]):
                if other["coord"] != inv["coord"] or other["status"] != "passed":
                    continue
                fp = inv.get("fingerprint")
                if fp and other.get("fingerprint") and other["fingerprint"] != fp:
                    continue
                linked = other
                break
            inv["evidence_for"] = linked["id"] if linked else None

    def _add_live_fields(self, inv: dict, step: dict, now: float) -> None:
        """Elapsed, latest observed activity, and honest idle health."""
        coord, attempt = inv["coord"], inv["attempt"]
        inv["elapsed_s"] = (round(now - epoch(inv["started"]), 1)
                            if inv["started"] else None)
        block = live.activity(self.run_dir, coord, attempt, limit=0,
                              now=now)
        act = (block or {}).get("activity") or {}
        running_tool = act.get("running_tool")
        inv["activity"] = {
            "latest_tool": ({"name": running_tool.get("name"),
                             "summary": running_tool.get("summary"),
                             "since_s": running_tool.get("since_s")}
                            if running_tool else None),
            "latest_reasoning": act.get("latest_reasoning"),
            "idle_s": act.get("idle_s"),
            "llm_calls": act.get("llm_calls"),
            "note": act.get("note"),
        }
        if act.get("log_tail") is not None:
            inv["activity"]["log_tail"] = act["log_tail"]
        # The command the agent is waiting on, with its output so far.
        # An open call is the agent working, not idle: the runtime's stall
        # clock waits for it (tool-output contract).
        command = tool_output.current(
            rundir.attempt_dir(self.run_dir, coord, attempt), lines=20, now=now)
        if command is not None:
            inv["activity"]["command_output"] = command
        raw = step["raw"]
        stall = raw.get("stall_timeout_s")
        idle = act.get("idle_s")
        amber = (stall / 2) if isinstance(stall, (int, float)) and stall > 0 \
            else live.IDLE_AMBER_S
        red = stall if isinstance(stall, (int, float)) and stall > 0 \
            else live.IDLE_RED_S
        signal = _signal(idle, amber, red)
        inv["health"] = {
            "idle_s": idle, "idle_signal": signal,
            "idle_amber_s": amber, "idle_red_s": red,
            "stall_timeout_s": stall if isinstance(stall, (int, float)) else None,
            "note": None,
        }
        if signal != "ok" and idle is not None:
            inv["health"]["note"] = (
                f"no recorded activity for {int(idle)} s "
                f"({signal} threshold {int(amber)} s): a threshold, "
                f"not a proven stall")
        if command is not None and command["open"]:
            inv["health"]["note"] = (
                f"a {command.get('tool') or 'tool'} call has been open for "
                f"{int(command['since_s'] or 0)} s: the agent is waiting on "
                f"its command, and the stall clock waits with it")

    def _final_line(self, coord: str, attempt: int) -> str | None:
        """The attempt's recorded claim, one bounded line."""
        adir = rundir.attempt_dir(self.run_dir, coord, attempt)
        path = adir / "final.md"
        if not path.is_file():
            return None
        return first_line(_text_of(path, 400), 200)

    # ---- steps, with honest waiting reasons

    def steps(self, now: float) -> list[dict]:
        model = self.model()
        live_run = self._live_run()
        held = self._held()
        out = []
        for step in model["raw_steps"]:
            coord = step["coord"]
            raw = step["raw"]
            agent = self._step_agent(raw)
            rec = self.state.steps.get(coord)
            status = rec.status if rec else "pending"
            if status == "running" and not live_run:
                status = "interrupted"
            running = status == "running" and live_run
            latest = None
            for inv in self.invocations(now):
                if inv["coord"] == coord:
                    latest = inv["id"]
            deps = [model["by_id"].get(d) for d in raw.get("depends_on") or []]
            bad_dep = None
            for d in deps:
                dep_rec = self.state.steps.get(d) if d else None
                if dep_rec is None or dep_rec.status not in _TERMINAL_OK:
                    bad_dep = d
                    break
            display, why, reason = "done", None, None
            if held:
                # Nothing has started and nothing will until `go`. The phase
                # barrier and the slot count are not what the step waits for.
                display, why, reason = "waiting", "hold", live.HELD_REASON
            elif status in ("pending", "deferred") or running:
                if running:
                    display = "running"
                elif status == "deferred":
                    display, why, reason = self._deferred_wait(coord, raw,
                                                               live_run)
                elif bad_dep is not None:
                    display, why = "waiting", "dependency"
                    dep_rec = self.state.steps.get(bad_dep)
                    reason = (f"waits for {bad_dep} "
                              f"({dep_rec.status if dep_rec else 'pending'})")
                else:
                    phase_state = next((p["state"] for p in model["phases"]
                                        if p["coord"] == step["phase"]),
                                       "waiting")
                    if phase_state == "waiting":
                        display, why = "waiting", "phase"
                        reason = ("waits for its phase barrier"
                                  if live_run else
                                  "not started: the run stopped before "
                                  "its phase")
                    elif not live_run:
                        display, why = "waiting", "stopped"
                        reason = "not started: the run stopped"
                    elif self._cooldown(now) is not None:
                        # The read-out's order: a cooldown holds every start
                        # of the phase, so the slot count is not the wait.
                        display, why = "waiting", "cooldown"
                        reason = ("waits for the provider cooldown until "
                                  f"{hms(self._cooldown(now))}")
                    else:
                        display, why = "waiting", "slot"
                        reason = "waits for a free slot"
            elif status not in _TERMINAL_OK:
                display, reason = "done", status
            out.append({
                "coord": coord, "phase": step["phase"],
                "phase_index": step["phase_index"], "id": step["id"],
                "kind": self._step_kind(raw, coord),
                "role": agent.get("role") or None,
                "harness_executor": agent.get("harness_executor"),
                "model": (agent.get("model") or {}).get("model")
                if isinstance(agent.get("model"), dict) else None,
                "depends_on": [d for d in deps if d],
                "unresolved_depends_on": [d for d in
                                          (raw.get("depends_on") or [])
                                          if model["by_id"].get(d) is None],
                # A command step without a gate records `"gate": null`, so
                # the key is present and the default never applies.
                "gate_checks": [str(c.get("name") if isinstance(c, dict)
                                    else c)
                                for c in (raw.get("gate") or {}).get("checks")
                                or []],
                "status": status,
                "display": display, "waiting_on": why, "reason": reason,
                "latest_invocation": latest,
                "execution_count": len([e for e in self.state.executions
                                        if e.get("coord") == coord
                                        and e.get("started")]),
                "objective": one_line(raw.get("objective")
                                      or raw.get("note") or "", 200) or None,
                "plan": self._step_plan(raw, agent),
            })
        return out

    # ---- events, segments, edges, campaign

    def events(self) -> list[dict]:
        names, phase_names = self._names()
        out = []
        for entry in self.entries[-EVENT_MAX:]:
            rec = entry["rec"]
            text, tone = live._event_text(rec, names, phase_names)
            out.append({
                "ts": rec.get("ts"), "event": rec.get("event"),
                "coord": rec.get("coord"), "attempt": rec.get("attempt"),
                "text": one_line(text, 240), "tone": tone,
                "payload": _event_payload(rec),
                "source": {"path": "run-log.jsonl", "line": entry["line"]},
            })
        return out

    def segments(self) -> list[dict]:
        """One segment per `run_finished`: a resumption is context, not cause."""
        model = self.model()
        names = {s["coord"]: s["id"] for s in model["raw_steps"]}
        segments: list[dict] = []
        current: dict | None = None
        for entry in self.entries:
            rec = entry["rec"]
            ev = rec.get("event")
            if current is None:
                current = {"index": len(segments) + 1,
                           "started": rec.get("ts"),
                           "finished": None, "status": None,
                           "invocations": [], "events": 0}
            current["events"] += 1
            coord, attempt = rec.get("coord"), rec.get("attempt")
            if ev == "attempt_started" and coord and isinstance(attempt, int):
                current["invocations"].append(f"{coord}@{attempt}")
            if ev == "run_finished":
                current["finished"] = rec.get("ts")
                current["status"] = (rec.get("payload") or {}).get("status")
                current["closed_by"] = {"path": "run-log.jsonl",
                                        "line": entry["line"]}
                segments.append(current)
                current = None
        if current is not None:
            current["status"] = self.run.status
            segments.append(current)
        return segments

    def edges(self) -> list[dict]:
        model = self.model()
        source = ("workflow.json" if model["workflow"].get("from_workflow")
                  else "run-log.jsonl (workflow.json absent; rebuilt)")
        edges = []
        for step in model["raw_steps"]:
            for dep in step["raw"].get("depends_on") or []:
                target = model["by_id"].get(dep)
                if target:
                    edges.append({"from": target, "to": step["coord"],
                                  "kind": "depends_on",
                                  "label": "depends_on", "source": source})
        for i in range(len(model["phases"]) - 1):
            for a in model["phases"][i]["steps"]:
                for b in model["phases"][i + 1]["steps"]:
                    edges.append({"from": a, "to": b, "kind": "phase",
                                  "label": "phase barrier",
                                  "source": "declared phase order"})
        for ex in self.state.executions:
            kind = ex.get("start_kind")
            if kind not in _RESTART_KINDS:
                continue
            coord, attempt = ex.get("coord"), ex.get("attempt")
            prior_ex = None
            for other in self.state.executions:
                if other.get("coord") != coord or not isinstance(attempt, int) \
                        or not isinstance(other.get("attempt"), int):
                    continue
                if 0 <= other["attempt"] < attempt and (
                        prior_ex is None
                        or other["attempt"] > prior_ex["attempt"]):
                    prior_ex = other
            if prior_ex is None:
                continue
            # The decision that caused the restart is the one the engine
            # recorded on the attempt that failed, not the restart's own.
            decision = prior_ex.get("retry_decision") or ex.get("retry_decision")
            edges.append({
                "from": f"{coord}@{prior_ex['attempt']}",
                "to": f"{coord}@{attempt}",
                "kind": kind,
                "label": decision or f"automatic {kind}",
                "source": ("run-log.jsonl retry_decided" if decision
                           else "run-log.jsonl attempt_started start_kind"),
            })
        return edges

    def campaign(self) -> dict | None:
        return None

    # ---- attention and digest

    def attention(self, now: float, steps: list[dict],
                  invocations: list[dict]) -> list[dict]:
        return ohattention.derive(self, now, steps, invocations)

    def digest(self, invocations: list[dict]) -> list[dict]:
        """One sentence per verdict, decision, settlement and run end.

        An `attempt_finished` gets the full sentence: status, wall, tokens
        from its `result.json`, the gate checks by name, and the first prose
        line of its handover when the recorded bytes still match. Every other
        event keeps the sentence `live._event_text` gives it. A decision not to
        retry a passed attempt is noise and is left out.
        """
        names, phase_names = self._names()
        by_id = {inv["id"]: inv for inv in invocations}
        out = []
        for entry in self.entries:
            rec = entry["rec"]
            ev = rec.get("event")
            if ev not in _DIGEST_EVENTS or live._is_noise(rec):
                continue
            coord, attempt = rec.get("coord"), rec.get("attempt")
            if ev == "work_excluded" and coord:
                # The exclusion names no attempt; the last execution of the
                # excluded work is the one it is about.
                mine = [i for i in invocations if i["coord"] == coord]
                attempt = mine[-1]["attempt"] if mine else None
            inv_id = (f"{coord}@{attempt}" if coord and isinstance(attempt, int)
                      else None)
            inv = by_id.get(inv_id) if inv_id else None
            text, tone = live._event_text(rec, names, phase_names)
            tokens = wall = handover_line = None
            if ev == "attempt_finished" and coord and isinstance(attempt, int):
                payload = rec.get("payload") or {}
                tokens = self._attempt_tokens(coord, attempt)
                wall = payload.get("wall_seconds")
                wall = float(wall) if isinstance(wall, (int, float)) else None
                handover_line = self._handover_line(coord, attempt, payload)
                text = _finish_sentence(
                    who=(inv or {}).get("role") or names.get(coord) or coord,
                    attempt=attempt, payload=payload, tokens=tokens,
                    wall=wall, handover_line=handover_line)
            out.append({
                "ts": rec.get("ts"), "kind": ev, "coord": coord,
                "attempt": attempt if isinstance(attempt, int) else None,
                "id": inv_id if inv is not None else None,
                "text": one_line(text, 400), "tone": tone,
                "tokens": tokens, "wall_s": wall,
                "handover_first_line": handover_line,
                "evidence": {"path": "run-log.jsonl", "line": entry["line"]},
            })
        return out

    def _attempt_tokens(self, coord: str, attempt: int) -> int | None:
        """`prompt + completion` from the attempt's `result.json`, or None."""
        adir = self._attempt_dir(coord, attempt)
        if adir is None:
            return None
        result = read_json(adir / "result.json")
        usage = rundir.Run.usage(result) if isinstance(result, dict) else None
        return usage["total_tokens"] if usage else None

    def _handover_line(self, coord: str, attempt: int, payload: dict
                       ) -> str | None:
        """The first prose line of the handover the finish recorded.

        Read through `handover.recorded`, so a file whose bytes no longer
        match the recorded digest is not quoted: the digest shows what the
        engine accepted, not what sits on disk now. Headings are skipped
        because every handover opens with `## State`.
        """
        if not payload.get("handover_path") or not payload.get("handover_sha256"):
            return None
        from .handover import recorded
        probe = StepRecord(coord=coord, attempt=attempt,
                           handover_path=payload["handover_path"],
                           handover_sha256=payload["handover_sha256"])
        try:
            _path, text = recorded(self.run_dir, probe)
        except ValueError:
            return None
        for line in text.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                return one_line(stripped, 200)
        return None

    def diagnostics(self) -> list[str]:
        out = []
        if not self.model()["workflow"].get("from_workflow"):
            out.append("workflow.json is absent: phases and steps are rebuilt "
                       "from the run log, so agent briefs and gate checks are "
                       "unknown")
        if self.unreadable:
            out.append(f"run-log.jsonl: {self.unreadable} unreadable line(s) "
                       f"before the final one; they are skipped, not repaired")
        recovery = self.state.meta.get("run_log_recovery")
        if recovery:
            out.append(f"run-log.jsonl: torn final line at line "
                       f"{recovery.get('line', '?')} was never repaired; the "
                       f"record is missing")
        out.append("campaign rounds live outside the run directory; this "
                   "server reads one run and reports campaign: null")
        return out

    # ---- per-attempt evidence

    def _attempt_dir(self, coord: str, attempt: int) -> Path | None:
        step = self.model()["by_coord"].get(coord)
        if step is None:
            return None
        return rundir.attempt_dir(self.run_dir, coord, attempt)

    def gate_evidence(self, coord: str, attempt: int) -> dict:
        finishes = self.run.finishes
        payload = (finishes.get((coord, attempt)) or {}).get("payload") or {}
        gate = payload.get("gate")
        out: dict[str, Any] = {"gate": gate if isinstance(gate, dict) else None,
                               "source": None}
        adir = self._attempt_dir(coord, attempt)
        if adir is not None and (adir / "gate.json").is_file() \
                and _inside(self.run_dir, adir / "gate.json"):
            out["gate"] = read_json(adir / "gate.json")
            out["source"] = _rel(self.run_dir, adir / "gate.json")
        elif isinstance(gate, dict):
            out["source"] = "run-log.jsonl attempt_finished payload"
        return out

    def final_message(self, coord: str, attempt: int) -> str | None:
        adir = self._attempt_dir(coord, attempt)
        if adir is None:
            return None
        path = adir / "final.md"
        if not path.is_file() or not _inside(self.run_dir, path):
            return None
        return _text_of(path, FINAL_MESSAGE_CAP)

    def evidence_artifacts(self, coord: str, attempt: int) -> list[dict]:
        """The attempt's files, from a whitelist. Credentials are not on it."""
        adir = self._attempt_dir(coord, attempt)
        if adir is None or not adir.is_dir():
            return []
        named = {"gate.json": ("gate", "json"),
                 "result.json": ("result", "json"),
                 "final.md": ("final", "text"),
                 "position.md": ("position", "text"),
                 "brief.md": ("brief", "text")}
        out = []
        for name, (art_id, kind) in named.items():
            path = adir / name
            if path.is_file() and _inside(self.run_dir, path):
                out.append(_artifact_entry(self.run_dir, path, art_id, name,
                                           kind))
        logs = sorted((adir / "logs").glob("*.log")) \
            if (adir / "logs").is_dir() else []
        for path in logs[:MAX_ARTIFACTS]:
            if path.name.endswith((".out.log", ".err.log")) \
                    and _inside(self.run_dir, path):
                out.append(_artifact_entry(self.run_dir, path,
                                           f"log:{path.name}", path.name,
                                           "log"))
        return out[:MAX_ARTIFACTS]

    def artifact(self, coord: str, attempt: int, art_id: str) -> dict | None:
        for entry in self.evidence_artifacts(coord, attempt):
            if entry["id"] == art_id:
                return _artifact_content(self.run_dir, entry)
        return None

    def evidence_events(self, coord: str, attempt: int) -> list[dict]:
        names, phase_names = self._names()
        out = []
        for entry in self.entries:
            rec = entry["rec"]
            if rec.get("coord") != coord or rec.get("attempt") != attempt:
                continue
            text, tone = live._event_text(rec, names, phase_names)
            out.append({"ts": rec.get("ts"), "event": rec.get("event"),
                        "text": one_line(text, 240), "tone": tone,
                        "source": {"path": "run-log.jsonl",
                                   "line": entry["line"]}})
            if len(out) >= ATTEMPT_EVENT_MAX:
                break
        return out

    # ---- transcripts

    def transcript_source(self, coord: str, attempt: int) -> dict:
        """Where this attempt's transcript lives, or why it does not.

        The current harness executors: pi writes a session JSONL; claude,
        codex, pi-cloud, codex-cloud and claude-cloud write event JSONL logs.
        A command, gate or
        merge attempt has no agent transcript; its newest `.out.log` serves.
        """
        step = self.model()["by_coord"].get(coord)
        if step is None:
            return {"error": "unknown coordinate"}
        adir = self._attempt_dir(coord, attempt)
        if adir is None:
            return {"error": "unknown coordinate"}
        kind = self._step_kind(step["raw"], coord)
        result = read_json(adir / "result.json")
        result = result if isinstance(result, dict) else {}
        harness = self._step_agent(step["raw"]).get("harness_executor")
        if kind != "agent":
            logs = sorted((adir / "logs").glob("*.out.log"),
                          key=lambda p: (p.stat().st_mtime_ns, p.name)) \
                if (adir / "logs").is_dir() else []
            if logs:
                return {"path": logs[-1], "rel": _rel(self.run_dir, logs[-1]),
                        "fmt": "log"}
            return {"error": f"no .out.log under {_rel(self.run_dir, adir)}"
                             f"/logs for this {kind} attempt"}
        from .harness_executors import harness_executor_module
        if harness == "pi":
            from . import pi_runner
            session = pi_runner._session_in(result, adir)
            if session is not None:
                return {"path": session, "rel": _rel(self.run_dir, session),
                        "fmt": "pi"}
            return {"error": "no pi session file for this attempt"}
        if harness in ("claude", "codex"):
            mod = harness_executor_module(harness)
            path = adir / "logs" / mod.EVENT_LOG
            if path.is_file():
                return {"path": path, "rel": _rel(self.run_dir, path),
                        "fmt": harness}
            return {"error": f"no {mod.EVENT_LOG} for this {harness} attempt"}
        if harness == "pi-cloud":
            from . import pi_cloud_runner
            path = adir / "logs" / pi_cloud_runner.EVENT_LOG
            if path.is_file():
                return {"path": path, "rel": _rel(self.run_dir, path),
                        "fmt": "pi-cloud"}
            return {"error": f"no {pi_cloud_runner.EVENT_LOG} for this "
                             "pi-cloud attempt"}
        if harness in ("codex-cloud", "claude-cloud"):
            mod = harness_executor_module(harness)
            path = adir / "logs" / mod.EVENT_LOG
            if path.is_file():
                return {"path": path, "rel": _rel(self.run_dir, path),
                        "fmt": harness}
            return {"error": f"no {mod.EVENT_LOG} for this {harness} attempt"}
        return {"error": f"harness executor {harness!r} has no transcript "
                         f"reader here" if harness else
                         "no harness executor recorded for this attempt"}


# =========================================================== packet source


class _PacketSource:
    """The `ohflow.dashboard-case/1` packet: a historical export, read as is."""

    kind = "packet"

    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)
        self.case: dict = {}
        self.entries: list[dict] = []
        self._model: dict | None = None
        self._inv_memo: tuple[float, list] | None = None

    def load(self) -> None:
        if self.case:
            return
        self.case = json.loads((self.run_dir / "case.json").read_text(
            encoding="utf-8"))
        try:
            raw_lines = (self.run_dir / "events.jsonl").read_bytes().splitlines()
        except OSError:
            raw_lines = []
        for i, raw in enumerate(raw_lines):
            if not raw.strip():
                continue
            try:
                rec = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(rec, dict):
                self.entries.append({"rec": rec, "line": i + 1})

    # ---- the planned shape

    def model(self) -> dict:
        if self._model is not None:
            return self._model
        phases = []
        by_id: dict[str, str] = {}
        raw_steps = []
        for index, ph in enumerate(self.case.get("phases") or [], start=1):
            coord = str(ph.get("id"))
            phases.append({
                "coord": coord, "index": index,
                "name": str(ph.get("name") or coord),
                "state": str(ph.get("final_status") or "unknown"),
                "max_parallel": ph.get("max_parallel"),
                "policy": ph.get("policy"),
                "min_success": ph.get("min_success"),
                "depends_on": [str(d) for d in ph.get("depends_on") or []],
                "steps": [str(c) for c in ph.get("steps") or []],
            })
        for st in self.case.get("steps") or []:
            coord = str(st.get("coord"))
            by_id[str(st.get("id"))] = coord
            raw_steps.append({"coord": coord,
                              "phase": str(st.get("phase")),
                              "id": str(st.get("id")),
                              "kind": "agent" if st.get("kind") == "worker"
                              else str(st.get("kind")),
                              "recorded_kind": st.get("kind"),
                              "role": st.get("role"),
                              "lane": st.get("lane"),
                              "model": st.get("model"),
                              "depends_on": [str(d)
                                             for d in st.get("depends_on")
                                             or []],
                              "gate_checks": [str(c) for c in
                                              st.get("gate_checks") or []],
                              "retry_policy": st.get("retry_policy"),
                              "wall_timeout_s": st.get("wall_timeout_s"),
                              "stall_timeout_s": st.get("stall_timeout_s")})
        self._model = {"phases": phases, "raw_steps": raw_steps,
                       "by_id": by_id,
                       "by_coord": {s["coord"]: s for s in raw_steps}}
        return self._model

    def _attempt_records(self) -> list[dict]:
        return [a for a in self.case.get("attempts") or []
                if isinstance(a, dict)]

    def _invocation_for(self, coord: str, attempt: int) -> dict | None:
        for a in self._attempt_records():
            if a.get("coord") == coord and a.get("attempt") == attempt:
                return a
        return None

    # ---- invocations

    def invocations(self, now: float) -> list[dict]:
        memo = self._inv_memo
        if memo is not None and memo[0] == now:
            return list(memo[1])
        invocations = self._build_invocations(now)
        self._inv_memo = (now, invocations)
        return list(invocations)

    def _build_invocations(self, now: float) -> list[dict]:
        out = []
        for ordinal, a in enumerate(self._attempt_records()):
            coord, attempt = str(a.get("coord")), a.get("attempt")
            step = self.model()["by_coord"].get(coord)
            if step is None or not isinstance(attempt, int):
                continue
            started = epoch((a.get("started") or {}).get("ts"))
            ended = epoch((a.get("finished") or {}).get("ts"))
            status = str(a.get("status") or "unknown")
            cached = bool(a.get("cached")) or status == "cached"
            usage = a.get("usage") if isinstance(a.get("usage"), dict) else {}
            wall = a.get("wall_seconds")
            inv: dict[str, Any] = {
                "id": f"{coord}@{attempt}",
                "coord": coord, "attempt": attempt,
                "step_id": step["id"], "phase": step["phase"],
                "kind": step["kind"],
                "role": step.get("role"),
                "harness_executor": step.get("lane"),
                "launch": "cached" if cached else
                ("agent" if step["kind"] == "agent" else "process"),
                "status": status,
                "started": iso(started), "finished": iso(ended),
                "wall_s": round(wall, 1) if isinstance(wall, (int, float))
                else None,
                "wall_s_basis": a.get("wall_seconds_basis"),
                "start_kind": a.get("start_kind") or "initial",
                "fingerprint": a.get("fingerprint"),
                "previous_fingerprint": a.get("previous_fingerprint"),
                "gate": {"passed": a.get("gate_passed"),
                         "failed": [str(c) for c in
                                    a.get("failed_checks") or []]},
                "final_message": self._final_line(coord, attempt),
                "retry_decision": a.get("retry_decision"),
                "cause": (f"gate {', '.join(str(c) for c in a.get('failed_checks') or [])}"
                          f" failed") if a.get("failed_checks") else None,
                "short_cause": (str(a["failed_checks"][0])
                                if a.get("failed_checks") else None),
                "error": a.get("error"),
                "tokens": {"input": usage.get("prompt_tokens"),
                           "output": usage.get("completion_tokens")},
                "cost": usage.get("cost"), "cost_source": usage.get("cost_source"),
                "llm_calls": usage.get("llm_calls"),
                "actions": usage.get("actions"),
                "source_refs": self._refs(a),
                "ordinal": ordinal,
                "order_ts": started if started is not None else ended,
                "elapsed_s": None, "activity": None, "health": None,
            }
            out.append((inv.pop("order_ts"), inv))
        out.sort(key=lambda pair: (pair[0] is None, pair[0] or 0.0,
                                   pair[1]["coord"], pair[1]["attempt"]))
        ordered = [pair[1] for pair in out]
        self._link_cached(ordered)
        return ordered

    @staticmethod
    def _link_cached(invocations: list[dict]) -> None:
        for i, inv in enumerate(invocations):
            if inv["status"] != "cached":
                continue
            linked = None
            for other in reversed(invocations[:i]):
                if other["coord"] == inv["coord"] \
                        and other["status"] == "passed":
                    linked = other
                    break
            inv["evidence_for"] = linked["id"] if linked else None

    @staticmethod
    def _refs(a: dict) -> dict:
        refs = {}
        for key in ("started", "finished", "retry_decision_ref"):
            ref = a.get(key)
            if isinstance(ref, dict):
                refs[key] = {"journal_line": ref.get("line"),
                             "original_type": ref.get("type"),
                             "ts": ref.get("ts")}
        return refs

    def _transcript_dir(self, coord: str, attempt: int) -> Path | None:
        a = self._invocation_for(coord, attempt)
        ref = (a or {}).get("transcript") or {}
        ref = ref.get("jsonl") if isinstance(ref, dict) else None
        if not isinstance(ref, str):
            return None
        return self._packet_path(ref)

    def _final_line(self, coord: str, attempt: int) -> str | None:
        path = self._transcript_dir(coord, attempt)
        if path is None:
            return None
        final = path.parent / "final.md"
        if final.is_file() and _inside(self.run_dir, final):
            return first_line(_text_of(final, 400), 200)
        return None

    # ---- steps, events, segments, edges, campaign

    def steps(self, now: float) -> list[dict]:
        model = self.model()
        invocations = self.invocations(now)
        out = []
        for step in model["raw_steps"]:
            coord = step["coord"]
            mine = [i for i in invocations if i["coord"] == coord]
            latest = mine[-1]["id"] if mine else None
            status = mine[-1]["status"] if mine else "pending"
            out.append({
                "coord": coord, "phase": step["phase"],
                "phase_index": next((p["index"] for p in model["phases"]
                                     if p["coord"] == step["phase"]), None),
                "id": step["id"], "kind": step["kind"],
                "recorded_kind": step.get("recorded_kind"),
                "role": step.get("role"),
                "harness_executor": step.get("lane"),
                "model": step.get("model"),
                "depends_on": [model["by_id"].get(d) for d in
                               step["depends_on"] if model["by_id"].get(d)],
                "unresolved_depends_on": [d for d in step["depends_on"]
                                          if model["by_id"].get(d) is None],
                "gate_checks": step["gate_checks"],
                "retry_policy": step.get("retry_policy"),
                "status": status, "display": "done", "waiting_on": None,
                "reason": None, "latest_invocation": latest,
                "execution_count": len([i for i in mine
                                        if i["status"] != "cached"]),
                "objective": None,
            })
        return out

    def events(self) -> list[dict]:
        """The packet's normalized names, with the original type beside them."""
        model = self.model()
        names = {s["coord"]: s["id"] for s in model["raw_steps"]}
        phase_names = {p["coord"]: p["name"] for p in model["phases"]}
        reverse = {"run.started": "run_started",
                   "run.worktree_ready": "worktree_ready",
                   "phase.started": "phase_started",
                   "phase.settled": "phase_settled",
                   "attempt.started": "attempt_started",
                   "attempt.finished": "attempt_finished",
                   "attempt.gate_ran": "gate_ran",
                   "attempt.retry_decided": "retry_decided"}
        out = []
        for entry in self.entries[-EVENT_MAX:]:
            rec = entry["rec"]
            original = rec.get("original") or {}
            engine = {"event": reverse.get(rec.get("type"),
                                           rec.get("type") or "unknown"),
                      "coord": rec.get("coord"), "attempt": rec.get("attempt"),
                      "payload": rec.get("payload") or {}}
            text, tone = live._event_text(engine, names, phase_names)
            out.append({
                "ts": rec.get("ts"), "event": rec.get("type"),
                "original_type": original.get("type"),
                "coord": rec.get("coord"), "attempt": rec.get("attempt"),
                "text": one_line(text, 240), "tone": tone,
                "payload": _event_payload(rec),
                "source": {"path": "journal.jsonl (original)",
                           "line": original.get("line")},
            })
        return out

    def segments(self) -> list[dict]:
        segments: list[dict] = []
        current: dict | None = None
        for entry in self.entries:
            rec = entry["rec"]
            if current is None:
                current = {"index": len(segments) + 1,
                           "started": rec.get("ts"), "finished": None,
                           "status": None, "invocations": [], "events": 0}
            current["events"] += 1
            coord, attempt = rec.get("coord"), rec.get("attempt")
            if rec.get("type") == "attempt.started" and coord \
                    and isinstance(attempt, int):
                current["invocations"].append(f"{coord}@{attempt}")
            if rec.get("type") == "run.finished":
                current["finished"] = rec.get("ts")
                current["status"] = (rec.get("payload") or {}).get("status")
                original = rec.get("original") or {}
                current["closed_by"] = {"path": "journal.jsonl (original)",
                                        "line": original.get("line")}
                segments.append(current)
                current = None
        if current is not None:
            segments.append(current)
        return segments

    def edges(self) -> list[dict]:
        model = self.model()
        edges = []
        for step in model["raw_steps"]:
            for dep in step["depends_on"]:
                target = model["by_id"].get(dep)
                if target:
                    edges.append({"from": target, "to": step["coord"],
                                  "kind": "depends_on", "label": "depends_on",
                                  "source": "case.json steps (plan.json)"})
        for i in range(len(model["phases"]) - 1):
            for a in model["phases"][i]["steps"]:
                for b in model["phases"][i + 1]["steps"]:
                    edges.append({"from": a, "to": b, "kind": "phase",
                                  "label": "phase barrier",
                                  "source": "declared phase order (case.json)"})
        proof = self.case.get("retry_proof") or {}
        failed, start = proof.get("failed_attempt") or {}, \
            proof.get("retry_start") or {}
        if failed.get("attempt") is not None and start.get("attempt") is not None:
            decision = (proof.get("decision") or {}).get("decision")
            edges.append({
                "from": f"{proof.get('coord')}@{failed['attempt']}",
                "to": f"{proof.get('coord')}@{start['attempt']}",
                "kind": start.get("start_kind") or "retry",
                "label": decision or "automatic retry",
                "source": "case.json retry_proof (journal.jsonl retry_decided)",
            })
        return edges

    def campaign(self) -> dict | None:
        campaign = self.case.get("campaign")
        if not isinstance(campaign, dict):
            return None
        rounds = []
        for r in campaign.get("rounds") or []:
            if not isinstance(r, dict):
                continue
            rounds.append({k: (_cut(str(v), 300) if v is not None else None)
                           for k, v in r.items()})
        return {"name": campaign.get("name"),
                "milestone": campaign.get("milestone"),
                "milestone_index": campaign.get("milestone_index"),
                "rounds": rounds}

    # ---- attention and digest

    def attention(self, now: float, steps: list[dict],
                  invocations: list[dict]) -> list[dict]:
        """A packet is recorded evidence; nothing in it still needs a person."""
        return []

    def digest(self, invocations: list[dict]) -> list[dict]:
        """The packet's verdicts as sentences, from its normalized events.

        The packet carries each attempt's usage and wall in `case.json`, not
        in a `result.json`, so the numbers come from the invocation rows. It
        records no handover.
        """
        by_id = {inv["id"]: inv for inv in invocations}
        out = []
        for event in self.events():
            ev = event["event"]
            kind = {"attempt.finished": "attempt_finished",
                    "attempt.retry_decided": "retry_decided",
                    "phase.settled": "phase_settled",
                    "run.finished": "run_finished",
                    "work.excluded": "work_excluded"}.get(ev)
            if kind is None or "is not a failure" in (event.get("text") or ""):
                continue
            coord, attempt = event.get("coord"), event.get("attempt")
            inv_id = (f"{coord}@{attempt}" if coord and isinstance(attempt, int)
                      else None)
            inv = by_id.get(inv_id) if inv_id else None
            text, tokens, wall = event["text"], None, None
            if kind == "attempt_finished" and inv is not None:
                tokens_block = inv.get("tokens") or {}
                counted = [v for v in (tokens_block.get("input"),
                                       tokens_block.get("output"))
                           if isinstance(v, (int, float))]
                tokens = int(sum(counted)) if counted else None
                wall = inv.get("wall_s")
                payload = {"status": inv["status"],
                           "gate": {"passed": (inv.get("gate") or {}).get("passed"),
                                    "checks": [{"name": n, "passed": False}
                                               for n in (inv.get("gate") or {})
                                               .get("failed") or []]}}
                text = _finish_sentence(who=inv.get("role") or inv["step_id"],
                                        attempt=attempt, payload=payload,
                                        tokens=tokens, wall=wall,
                                        handover_line=None)
            out.append({
                "ts": event.get("ts"), "kind": kind, "coord": coord,
                "attempt": attempt if isinstance(attempt, int) else None,
                "id": inv_id if inv is not None else None,
                "text": one_line(text, 400), "tone": event.get("tone"),
                "tokens": tokens, "wall_s": wall,
                "handover_first_line": None,
                "evidence": event.get("source"),
            })
        return out

    def diagnostics(self) -> list[str]:
        out = [
            f"packet schema {PACKET_SCHEMA}: a historical export; the "
            f"journal's original names (step_started, lane, worker) are kept "
            f"beside every normalized one",
            "cached evaluations launched no agent; their wall_seconds is an "
            "engine default, not a measurement",
        ]
        for hole in self.case.get("known_holes") or []:
            out.append(_cut(str(hole), 300))
        return out

    # ---- per-attempt evidence

    def _packet_path(self, ref: str) -> Path | None:
        """A `packet:` reference resolved inside the packet, or None."""
        text = str(ref)
        if text.startswith("packet:"):
            text = text[len("packet:"):]
        path = self.run_dir / text
        if not _inside(self.run_dir, path):
            return None
        return path

    def gate_evidence(self, coord: str, attempt: int) -> dict:
        a = self._invocation_for(coord, attempt)
        if a is None:
            return {"gate": None, "source": None}
        if a.get("status") == "cached" or a.get("cached"):
            finished = a.get("finished") or {}
            return {"gate": {"passed": a.get("gate_passed"), "checks": []},
                    "source": "no gate ran: a cached evaluation reuses the "
                              "earlier attempt's gate",
                    "journal_line": finished.get("line")}
        gate = None
        line = None
        for entry in self.entries:
            rec = entry["rec"]
            if rec.get("type") == "attempt.gate_ran" \
                    and rec.get("coord") == coord \
                    and rec.get("attempt") == attempt:
                gate = (rec.get("payload") or {}).get("gate")
                line = entry["line"]
        if gate is None:
            gate = {"passed": a.get("gate_passed"),
                    "failed_checks": a.get("failed_checks")}
        return {"gate": gate,
                "source": (f"events.jsonl line {line}"
                           f" (journal.jsonl gate_ran)") if line else None}

    def final_message(self, coord: str, attempt: int) -> str | None:
        path = self._transcript_dir(coord, attempt)
        if path is None:
            return None
        final = path.parent / "final.md"
        if final.is_file() and _inside(self.run_dir, final):
            return _text_of(final, FINAL_MESSAGE_CAP)
        return None

    #: The packet's attempt directory is a transcripts/<name> folder; only
    #: these names are ever served from it.
    _ARTIFACT_NAMES = {"gate.json": ("gate", "json"),
                       "final.md": ("final", "text"),
                       "position.md": ("position", "text"),
                       "gate-command-exit.out.log":
                           ("log:gate-command-exit.out.log", "log"),
                       "gate-command-exit.err.log":
                           ("log:gate-command-exit.err.log", "log"),
                       "transcript.md": ("transcript", "text")}

    def evidence_artifacts(self, coord: str, attempt: int) -> list[dict]:
        a = self._invocation_for(coord, attempt)
        if a is None:
            return []
        linked = None
        if a.get("status") == "cached" or a.get("cached"):
            invocations = self.invocations(0.0)
            linked = next((i.get("evidence_for") for i in invocations
                           if i["id"] == f"{coord}@{attempt}"), None)
            if linked:
                ref = linked.split("@")
                return self.evidence_artifacts(ref[0], int(ref[1]))
        path = self._transcript_dir(coord, attempt)
        if path is None:
            return []
        out = []
        for name, (art_id, kind) in self._ARTIFACT_NAMES.items():
            candidate = path.parent / name
            if candidate.is_file() and _inside(self.run_dir, candidate):
                out.append(_artifact_entry(self.run_dir, candidate, art_id,
                                           name, kind))
        return out

    def artifact(self, coord: str, attempt: int, art_id: str) -> dict | None:
        for entry in self.evidence_artifacts(coord, attempt):
            if entry["id"] == art_id:
                return _artifact_content(self.run_dir, entry)
        return None

    def evidence_events(self, coord: str, attempt: int) -> list[dict]:
        out = []
        for entry in self.events():
            if entry.get("coord") == coord and entry.get("attempt") == attempt:
                out.append(entry)
            if len(out) >= ATTEMPT_EVENT_MAX:
                break
        return out

    def transcript_source(self, coord: str, attempt: int) -> dict:
        a = self._invocation_for(coord, attempt)
        if a is None:
            return {"error": "no such attempt in this packet"}
        if a.get("status") == "cached" or a.get("cached"):
            return {"error": "cached evaluation launched no agent; there is "
                             "no transcript"}
        path = self._transcript_dir(coord, attempt)
        if path is None or not path.is_file():
            return {"error": "the packet records no transcript.jsonl for "
                             "this attempt"}
        return {"path": path, "rel": _rel(self.run_dir, path), "fmt": "packet"}


# ============================================================== shaping


def _duration_words(seconds: float | None) -> str:
    """`252` as "4 m 12 s": the digest reads aloud, not in a column."""
    if not isinstance(seconds, (int, float)):
        return "unknown time"
    s = int(round(seconds))
    if s < 60:
        return f"{s} s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m} m {s} s" if s else f"{m} m"
    h, m = divmod(m, 60)
    return f"{h} h {m} m"


def _tokens_words(n: int | None) -> str | None:
    if not isinstance(n, int):
        return None
    if n < 1000:
        return f"{n} tokens"
    if n < 1_000_000:
        return f"{n / 1000:.0f} k tokens"
    return f"{n / 1_000_000:.1f} M tokens"


def _finish_sentence(*, who: str, attempt: int, payload: dict,
                     tokens: int | None, wall: float | None,
                     handover_line: str | None) -> str:
    """The digest's one sentence for an `attempt_finished`.

    "Implement attempt 2 passed in 4 m 12 s, 31 k tokens; gate command_exit
    ok; handover: <first line>". A synthetic finish (attempt 0: a cached
    evaluation, a refused start) has no attempt number to name and no clock.
    """
    status = payload.get("status") or "?"
    if not attempt:
        text = f"{who} {status}"
        error = first_line(payload.get("error"), 140)
        if error and status not in _TERMINAL_OK:
            text += f": {error}"
        return text
    text = f"{who} attempt {attempt} {status}"
    if wall is not None and wall > 0:
        text += f" in {_duration_words(wall)}"
    tokens_text = _tokens_words(tokens)
    if tokens_text:
        text += f", {tokens_text}"
    gate = payload.get("gate")
    if isinstance(gate, dict) and gate.get("checks"):
        verdicts = []
        for check in gate["checks"]:
            if not isinstance(check, dict):
                continue
            verdicts.append(f"{check.get('name')} "
                            f"{'ok' if check.get('passed') else 'failed'}")
        if verdicts:
            text += "; gate " + ", ".join(verdicts)
    elif status not in _TERMINAL_OK:
        cause, _short = live._cause(payload)
        if cause:
            text += f"; {cause}"
    if handover_line:
        text += f"; handover: {handover_line}"
    return text


def _lanes(phase: dict, steps: list[dict], default_parallel: Any) -> dict:
    """Who in this phase runs and who waits for what, as counts and as the one
    line the page shows: "2 running · 1 for a free slot (2 of 2 busy) · 3 for
    their phase"."""
    mine = [s for s in steps if s["phase"] == phase["coord"]]
    running = sum(1 for s in mine if s["display"] == "running")
    waiting_by: dict[str, int] = {}
    for s in mine:
        if s["display"] == "waiting" and s.get("waiting_on"):
            waiting_by[s["waiting_on"]] = waiting_by.get(s["waiting_on"], 0) + 1
    max_parallel = phase.get("max_parallel") or default_parallel
    parts = [f"{running} running"]
    for key, phrase in live.waiting_phrases(waiting_by):
        if key == "slot":
            phrase += f" ({running} of {max_parallel or '?'} busy)"
        parts.append(phrase)
    return {"running": running, "waiting_by": waiting_by,
            "waiting_words": live.waiting_words(waiting_by),
            "max_parallel": max_parallel, "text": " · ".join(parts)}


def _event_payload(rec: dict) -> dict:
    """A bounded payload. A huge one is named, not shipped."""
    payload = rec.get("payload") or {}
    capped = _cap_tree(payload, PAYLOAD_CAP, lists=40)
    if len(json.dumps(capped, default=str)) <= PAYLOAD_JSON_MAX:
        return capped
    return {"payload_omitted": f"{len(json.dumps(payload, default=str))} "
                               f"chars; the run log holds the record whole"}


def _rel(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _artifact_entry(root: Path, path: Path, art_id: str, name: str,
                    kind: str) -> dict:
    try:
        size = path.stat().st_size
    except OSError:
        size = None
    return {"id": art_id, "name": name, "kind": kind, "bytes": size,
            "source": {"path": _rel(root, path)}}


def _artifact_content(root: Path, entry: dict) -> dict:
    path = root / entry["source"]["path"]
    out = dict(entry)
    if entry["kind"] == "json":
        out["content"] = _cap_tree(read_json(path), STRING_CAP, lists=200)
    else:
        out["content"] = _text_of(path, ARTIFACT_TEXT_CAP)
    return out


# ======================================================= transcript records


def _record_base(rel: str, line: int, ts: Any, rtype: str, role: str) -> dict:
    return {"id": f"L{line}",
            "source": {"path": rel, "line": line},
            "ts": iso(epoch(ts)) if ts is not None else None,
            "type": rtype, "role": role, "blocks": []}


def _text_block(text: Any) -> dict | None:
    if isinstance(text, str) and text.strip():
        return {"type": "text", "text": text}
    return None


def _packet_blocks(blocks: Any) -> list[dict]:
    """Packet blocks in one vocabulary with the raw formats: a tool call is
    `tool_call` with `call_id`, its answer `tool_result` with the same id."""
    out = []
    for b in blocks or []:
        if not isinstance(b, dict):
            continue
        btype = b.get("type")
        if btype in ("tool_use", "toolCall"):
            out.append({"type": "tool_call", "call_id": b.get("id"),
                        "name": b.get("name"),
                        "input": (b.get("input") if btype == "tool_use"
                                  else b.get("arguments"))})
        elif btype == "tool_result":
            out.append({"type": "tool_result", "call_id": b.get("tool_use_id"),
                        "is_error": bool(b.get("is_error")),
                        "content": b.get("content")})
        else:
            out.append(b)
    return out


def _norm_packet(rec: dict, rel: str, line: int) -> dict | None:
    """A packet transcript record: already in the packet's own shape."""
    rtype = str(rec.get("type") or "unknown")
    if rtype == "message":
        role = str(rec.get("role") or "unknown")
        out = _record_base(rel, line, rec.get("ts"), "message", role)
        out["blocks"] = _packet_blocks(rec.get("blocks"))
        if role == "toolResult" and rec.get("tool_call_id"):
            out["tool_call_id"] = rec["tool_call_id"]
            out["type"] = "tool_result"
        return out
    out = _record_base(rel, line, rec.get("ts"),
                       {"tool-progress": "tool_progress",
                        "rate-limit": "rate_limit"}.get(rtype, rtype),
                       "system")
    for key in ("tool_use_id", "tool_name", "elapsed_time_seconds",
                "heartbeat", "status", "rate_limit_type", "subtype",
                "stop_reason", "result"):
        if rec.get(key) is not None:
            out[key] = rec[key]
    if rec.get("tool_use_id"):
        out["tool_call_id"] = rec["tool_use_id"]
    return out


def _norm_claude(rec: dict, rel: str, line: int) -> dict | None:
    """A raw claude event (the runner's copy of claude's stream)."""
    rtype = rec.get("type")
    ts = rec.get("timestamp")
    msg = rec.get("message") if isinstance(rec.get("message"), dict) else {}
    if rtype in ("assistant", "user"):
        role = str(rtype)
        out = _record_base(rel, line, ts, "message", role)
        blocks = []
        content = msg.get("content")
        items = content if isinstance(content, list) else []
        if isinstance(content, str):
            block = _text_block(content)
            if block:
                blocks.append(block)
        for c in items:
            if not isinstance(c, dict):
                continue
            ct = c.get("type")
            if ct == "text":
                block = _text_block(c.get("text"))
                if block:
                    blocks.append(block)
            elif ct == "thinking":
                if str(c.get("thinking") or "").strip():
                    blocks.append({"type": "thinking",
                                   "thinking": str(c["thinking"])})
            elif ct == "tool_use":
                blocks.append({"type": "tool_call", "call_id": c.get("id"),
                               "name": c.get("name"),
                               "input": c.get("input") or {}})
            elif ct == "tool_result":
                blocks.append({"type": "tool_result",
                               "call_id": c.get("tool_use_id"),
                               "is_error": bool(c.get("is_error")),
                               "content": c.get("content")})
        out["blocks"] = blocks
        if msg.get("model"):
            out["model"] = str(msg["model"])
        return out
    if rtype == "system":
        out = _record_base(rel, line, ts, "system", "system")
        out["subtype"] = rec.get("subtype")
        return out
    if rtype == "tool_progress":
        out = _record_base(rel, line, ts, "tool_progress", "system")
        out["tool_call_id"] = rec.get("tool_use_id")
        out["tool_name"] = rec.get("tool_name")
        out["elapsed_s"] = rec.get("elapsed_time_seconds")
        return out
    if rtype == "rate_limit_event":
        info = rec.get("rate_limit_info") or {}
        out = _record_base(rel, line, ts, "rate_limit", "system")
        out["status"] = info.get("status")
        out["rate_limit_type"] = info.get("rateLimitType")
        return out
    if rtype == "result":
        out = _record_base(rel, line, ts, "result", "system")
        out["stop_reason"] = rec.get("stop_reason")
        out["is_error"] = bool(rec.get("is_error"))
        out["result"] = rec.get("result") or ""
        return out
    out = _record_base(rel, line, ts, str(rtype or "unknown"), "system")
    return out


def _norm_pi(rec: dict, rel: str, line: int) -> dict | None:
    """A raw pi session entry."""
    rtype = rec.get("type")
    ts = rec.get("timestamp")
    msg = rec.get("message") if isinstance(rec.get("message"), dict) else {}
    if rtype == "message":
        role = str(msg.get("role") or "unknown")
        if role == "toolResult":
            out = _record_base(rel, line, ts, "tool_result", "toolResult")
            out["tool_call_id"] = msg.get("toolCallId")
            out["tool_name"] = msg.get("toolName")
            out["is_error"] = bool(msg.get("isError"))
            blocks = []
            for c in msg.get("content") or []:
                if not isinstance(c, dict):
                    continue
                if c.get("type") == "text":
                    block = _text_block(c.get("text"))
                    if block:
                        blocks.append(block)
                else:
                    blocks.append(c)
            out["blocks"] = blocks
            return out
        out = _record_base(rel, line, ts, "message", role)
        blocks = []
        for c in msg.get("content") or []:
            if not isinstance(c, dict):
                continue
            ct = c.get("type")
            if ct == "text":
                block = _text_block(c.get("text"))
                if block:
                    blocks.append(block)
            elif ct == "thinking":
                if str(c.get("thinking") or "").strip():
                    blocks.append({"type": "thinking",
                                   "thinking": str(c["thinking"])})
            elif ct == "toolCall":
                blocks.append({"type": "tool_call", "call_id": c.get("id"),
                               "name": c.get("name"),
                               "input": c.get("arguments") or {}})
        out["blocks"] = blocks
        if msg.get("errorMessage"):
            out["error"] = str(msg["errorMessage"])
        return out
    out = _record_base(rel, line, ts,
                       {"model_change": "model_change",
                        "thinking_level_change": "thinking_level_change",
                        "session": "session"}.get(str(rtype),
                                                  str(rtype or "unknown")),
                       "system")
    for key in ("provider", "modelId", "thinking_level", "version"):
        camel = {"thinking_level": "thinkingLevel", "model_id": "modelId"}.get(
            key, key)
        if rec.get(camel) is not None:
            out[key] = str(rec[camel])
    return out


def _norm_codex(rec: dict, rel: str, line: int) -> dict | None:
    """A raw codex event (the runner's copy of `codex exec --json`)."""
    rtype = str(rec.get("type") or "unknown")
    ts = rec.get("timestamp")
    item = rec.get("item") if isinstance(rec.get("item"), dict) else {}
    itype = item.get("type")
    if rtype == "item.started" and itype is not None \
            and itype not in ("agent_message", "reasoning", "error"):
        out = _record_base(rel, line, ts, "tool_call", "assistant")
        out["tool_call_id"] = item.get("id")
        out["name"] = {"command_execution": "shell",
                       "file_change": "apply_patch",
                       "web_search": "web_search"}.get(
            itype, str(item.get("server") or itype))
        out["input"] = (item.get("command") or item.get("arguments")
                        or item.get("changes") or {})
        return out
    if rtype == "item.completed":
        if itype == "agent_message":
            out = _record_base(rel, line, ts, "message", "assistant")
            block = _text_block(item.get("text"))
            out["blocks"] = [block] if block else []
            return out
        if itype == "reasoning":
            out = _record_base(rel, line, ts, "message", "assistant")
            text = item.get("text")
            out["blocks"] = [{"type": "thinking", "thinking": str(text)}
                             ] if str(text or "").strip() else []
            return out
        if itype == "error":
            out = _record_base(rel, line, ts, "system", "system")
            out["note"] = str(item.get("message") or "")
            return out
        if itype is not None:
            out = _record_base(rel, line, ts, "tool_result", "assistant")
            out["tool_call_id"] = item.get("id")
            out["is_error"] = (item.get("exit_code") not in (0, None)
                               if itype == "command_execution"
                               else item.get("status") == "failed")
            out["content"] = (item.get("aggregated_output")
                              or item.get("status") or "")
            return out
    if rtype in ("turn.completed",):
        out = _record_base(rel, line, ts, "result", "system")
        out["usage"] = rec.get("usage") or {}
        return out
    if rtype in ("turn.failed", "error"):
        out = _record_base(rel, line, ts, "error", "system")
        err = rec.get("error") if isinstance(rec.get("error"), dict) else {}
        out["error"] = str(err.get("message") if err else
                           rec.get("message") or rtype)
        return out
    out = _record_base(rel, line, ts, rtype, "system")
    return out


def _norm_pi_cloud(rec: dict, rel: str, line: int) -> dict | None:
    """A pi-cloud event (the runner's copy of the Worker's stream), the
    shape the codex-cloud and claude-cloud streams carry too.

    A message reads as pi's own session entry. A tool start is the call
    itself: before the session settles it is the only record that names the
    tool and its arguments. A replayed event's `t` is the replay's clock, so
    a replayed tool event carries no time.
    """
    rtype = str(rec.get("type") or "unknown")
    ts = None if rec.get("replayed") else rec.get("t")
    msg = rec.get("message") if isinstance(rec.get("message"), dict) else None
    if rtype == "message_end" and msg is not None:
        return _norm_pi({"type": "message", "message": msg,
                         "timestamp": msg.get("timestamp") or ts}, rel, line)
    if rtype == "tool_execution_start":
        out = _record_base(rel, line, ts, "tool_started", "system")
        out["tool_call_id"] = rec.get("toolCallId")
        out["tool_name"] = rec.get("toolName")
        out["blocks"] = [{"type": "tool_call",
                          "call_id": rec.get("toolCallId"),
                          "name": rec.get("toolName"),
                          "input": rec.get("args") or {}}]
        return out
    if rtype == "tool_execution_end":
        result = rec.get("result") if isinstance(rec.get("result"),
                                                 dict) else {}
        return _norm_pi({"type": "message", "timestamp": ts, "message": {
            "role": "toolResult", "toolCallId": rec.get("toolCallId"),
            "toolName": rec.get("toolName"),
            "isError": bool(rec.get("isError") or result.get("isError")),
            "content": result.get("content") or []}}, rel, line)
    out = _record_base(rel, line, ts, rtype, "system")
    for key in ("status", "reason", "model", "name", "message", "head",
                "pushed", "push_error"):
        value = rec.get(key)
        if value is not None and not isinstance(value, (dict, list)):
            out[key] = value
    return out


_NORMALIZERS = {"packet": _norm_packet, "claude": _norm_claude,
                "pi": _norm_pi, "codex": _norm_codex,
                "pi-cloud": _norm_pi_cloud, "codex-cloud": _norm_pi_cloud,
                "claude-cloud": _norm_pi_cloud}


def _parse_line(fmt: str, raw: bytes, rel: str, line: int,
                diagnostics: list[str]) -> dict | None:
    """One JSONL line as a normalized record, or a named error record."""
    if fmt == "log":
        # A command step's out log is text, not JSON: every line is a record.
        out = _record_base(rel, line, None, "log", "system")
        text = raw.decode("utf-8", "replace").rstrip("\r\n")
        out["blocks"] = [{"type": "text", "text": _cut(text)}]
        return out
    try:
        rec = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        diagnostics.append(f"{rel} line {line}: malformed JSON "
                           f"({type(e).__name__}); shown as an error record")
        out = _record_base(rel, line, None, "error", "system")
        out["error"] = f"malformed JSON: {type(e).__name__}"
        return out
    if not isinstance(rec, dict):
        diagnostics.append(f"{rel} line {line}: not a JSON object")
        out = _record_base(rel, line, None, "error", "system")
        out["error"] = "record is not a JSON object"
        return out
    normalizer = _NORMALIZERS.get(fmt)
    if normalizer is None:
        return None
    record = normalizer(rec, rel, line)
    if record is None:
        diagnostics.append(f"{rel} line {line}: unrecognized record shape")
    return record


def _initial_page(binding: str, fmt: str, identity: str,
                  signature: str) -> dict:
    return {"b": binding, "s": fmt, "i": identity, "g": signature,
            "o": 0, "l": 0, "f": 0, "q": 0, "n": 0}


def _cursor_matches(page: dict, *, binding: str, fmt: str, identity: str,
                    signature: str, size: int | None = None) -> str | None:
    """Why a cursor cannot continue this exact source, else ``None``."""
    if page["b"] != binding:
        return "cursor belongs to another run, coordinate, attempt, or source"
    if page["s"] != fmt or page["i"] != identity:
        return "transcript source identity changed"
    if page["f"]:
        return "cursor file index does not apply to this transcript source"
    if size is not None and page["o"] > size:
        return "transcript was truncated below the cursor"
    if page["g"] != signature:
        return "transcript prefix changed"
    if page["q"] and not page.get("r"):
        return "cursor continuation is missing its record signature"
    return None


def _bounded_record(record: dict, raw: bytes, continuation_offset: int,
                    records: list[dict], content_chars: int) -> tuple[
                        str, dict | None, int]:
    """Shape a record without loss: full, defer, or one continuation chunk."""
    record = live._redact_tree(record)
    encoded = transcript_io.normalized_json(record)
    if continuation_offset or len(encoded) > transcript_io.INLINE_RECORD_CHARS:
        if records:
            return "defer", None, content_chars
        envelope, next_offset = transcript_io.continuation(
            record, continuation_offset)
        envelope["_next_continuation"] = next_offset
        envelope["_record_hash"] = transcript_io.record_hash(raw)
        return "continuation", envelope, content_chars + len(
            envelope["continuation"]["data"])
    if records and content_chars + len(encoded) > transcript_io.PAGE_CONTENT_CHARS:
        return "defer", None, content_chars
    return "full", record, content_chars + len(encoded)


def _read_stream_page(fh, size: int, page: dict, limit: int, rel: str,
                      fmt: str, diagnostics: list[str], prefix_signature,
                      skip: frozenset[int] = frozenset()
                      ) -> tuple[list[dict], dict, bool, bool, int, int]:
    """Read only the source lines needed for one bounded response page.

    A line numbered in `skip` repeats an earlier record and is passed over.
    """
    records: list[dict] = []
    offset, line_no = page["o"], page["l"]
    logical_done = page["n"]
    continuation_offset = page["q"]
    started = completed = content_chars = 0
    pending_tail = False
    stopped = False
    fh.seek(offset)
    while started < limit or continuation_offset:
        before = fh.tell()
        raw = fh.readline()
        if not raw:
            break
        if not raw.endswith(b"\n"):
            fh.seek(before)
            pending_tail = True
            break
        candidate_line = line_no + 1
        if candidate_line in skip and not continuation_offset:
            offset, line_no = fh.tell(), candidate_line
            continue
        if not raw.strip():
            if continuation_offset:
                stopped = True
                diagnostics.append("continued source record became blank; "
                                   "cursor reset is required")
                break
            offset, line_no = fh.tell(), candidate_line
            continue
        if continuation_offset and transcript_io.record_hash(raw) != page.get("r"):
            stopped = True
            diagnostics.append("continued source record changed; cursor reset "
                               "is required")
            break
        record = _parse_line(fmt, raw, rel, candidate_line, diagnostics)
        if record is None:
            offset, line_no = fh.tell(), candidate_line
            continuation_offset = 0
            continue
        disposition, shaped, content_chars = _bounded_record(
            record, raw, continuation_offset, records, content_chars)
        if disposition == "defer":
            fh.seek(before)
            stopped = True
            break
        if disposition == "continuation":
            assert shaped is not None
            next_offset = shaped.pop("_next_continuation")
            current_hash = shaped.pop("_record_hash")
            records.append(shaped)
            if continuation_offset == 0:
                started += 1
            if next_offset is None:
                offset, line_no = fh.tell(), candidate_line
                logical_done += 1
                completed += 1
                continuation_offset = 0
                page.pop("r", None)
            else:
                fh.seek(before)
                offset = before
                continuation_offset = next_offset
                page["r"] = current_hash
            # One continuation chunk per response.  A final chunk at EOF does
            # not manufacture an extra empty page.
            stopped = bool(next_offset is not None or offset < size)
            break
        assert shaped is not None
        records.append(shaped)
        offset, line_no = fh.tell(), candidate_line
        logical_done += 1
        started += 1
        completed += 1
        continuation_offset = 0
        if started >= limit or content_chars >= transcript_io.PAGE_CONTENT_CHARS:
            stopped = offset < size
            break
    has_more = bool(continuation_offset or stopped or offset < size
                    and not pending_tail)
    next_page = dict(page)
    next_page.update({"o": offset, "l": line_no, "f": 0,
                      "q": continuation_offset, "n": logical_done,
                      "g": prefix_signature(offset)})
    if not continuation_offset:
        next_page.pop("r", None)
    return records, next_page, has_more, pending_tail, started, completed


# ============================================================== public API


def workflow_data(run_dir: Path, now: float | None = None) -> dict:
    """`/api/workflow`: the run as graph truth, redacted."""
    now = time.time() if now is None else float(now)
    run_dir = Path(run_dir)
    source = open_source(run_dir)
    if source is None:
        return {"schema": WORKFLOW_SCHEMA, "generated": iso(now),
                "source": None, "run": None, "phases": [], "steps": [],
                "invocations": [], "edges": [], "segments": [], "cached": [],
                "events": [], "attention": [], "digest": [], "campaign": None,
                "diagnostics": ["this directory is neither an ohflow run "
                                "directory nor a recognized evidence packet"]}
    model = source.model()
    invocations = source.invocations(now)
    steps = source.steps(now)
    if source.kind == "run":
        run = source.run
        status = source.status()
        run_out = {
            "id": run.id, "status": status,
            "workflow": model["workflow"].get("name"),
            "started": run.state.started, "finished": run.state.finished,
            "mode": "live" if status in _LIVE_RUN else "final",
            "supervisor_alive": run.supervisor_alive,
            "elapsed_s": None,
        }
        started, finished = epoch(run.state.started), epoch(run.state.finished)
        if started is not None:
            run_out["elapsed_s"] = round((finished or now) - started, 1)
        run_out["plan_stamp"] = plan_stamp(run_dir)
        _add_estimate(source, run_out, model, steps, invocations)
        run_out["pilot"] = ohpilot.page_view(source.run_dir)
        run_out["token_budget"] = ohbudget.read_snapshot(source.run_dir)
    else:
        canonical = source.case.get("canonical_run") or {}
        run_out = {
            "id": canonical.get("id"), "status": canonical.get("status"),
            "plan": canonical.get("plan"),
            "branch": canonical.get("worktree_branch"),
            "base_sha": canonical.get("base_sha"),
            "started": canonical.get("started"),
            "finished": canonical.get("finished"),
            "mode": "final",
            "elapsed_s": None,
        }
        started, finished = epoch(canonical.get("started")), \
            epoch(canonical.get("finished"))
        if started is not None:
            run_out["elapsed_s"] = round((finished or now) - started, 1)
    default_parallel = (model["workflow"].get("max_parallel")
                        if source.kind == "run" else None)
    for phase in model["phases"]:
        phase["lanes"] = _lanes(phase, steps, default_parallel)
    payload = {
        "schema": WORKFLOW_SCHEMA, "generated": iso(now),
        "source": source.kind,
        "run": run_out,
        "phases": model["phases"],
        "steps": _with_step_estimates(source, steps),
        "invocations": invocations,
        "edges": source.edges(),
        "segments": source.segments(),
        "cached": [{"id": i["id"], "coord": i["coord"], "status": i["status"],
                    "finished": i["finished"],
                    "evidence_for": i.get("evidence_for")}
                   for i in invocations if i["status"] == "cached"],
        "events": source.events(),
        "attention": source.attention(now, steps, invocations),
        "digest": source.digest(invocations),
        "campaign": source.campaign(),
        "diagnostics": source.diagnostics(),
    }
    return live._redact_tree(_cap_tree(payload, STRING_CAP))


def agent_view(run_dir: Path, now: float | None = None) -> dict | None:
    """The attention items and the digest of one run, for `watch` and `status`.

    An orchestrating agent needs these two lists and nothing else of the page
    payload, which is about ten times larger and grows with the step count.
    The route that served the page payload exists only while the dashboard
    serves, so the agent's verbs read the run directory through this function.
    It builds the invocations and steps the two lists are derived from, and no
    other part of `workflow_data`. Strings pass the same cap and redaction.

    Returns None for a directory that is not a run; a packet is recorded
    evidence, not a run an agent watches.
    """
    now = time.time() if now is None else float(now)
    source = open_source(Path(run_dir))
    if source is None or source.kind != "run":
        return None
    invocations = source.invocations(now)
    steps = source.steps(now)
    view = {"attention": source.attention(now, steps, invocations),
            "digest": source.digest(invocations)}
    return live._redact_tree(_cap_tree(view, STRING_CAP))


def plan_stamp(run_dir: Path) -> dict | None:
    """The mtime and size of `workflow.json`, or None without the file.

    The page fetches `/api/plan` once and again when this changes, which is
    how the reload after `go` reaches the Plan view.
    """
    try:
        st = (Path(run_dir) / "workflow.json").stat()
    except OSError:
        return None
    return {"mtime_ns": st.st_mtime_ns, "size": st.st_size}


def _null_estimate() -> dict:
    return {"wall_s": {"p50": None, "p80": None},
            "tokens": {"p50": None, "p80": None},
            "cost_usd": None, "n": None, "basis": None, "confidence": None}


def _plan_estimate(found: dict | None) -> dict:
    """One estimate block of the plan: p50, p80, tokens, cost, n. Every
    field is null when the run has no `estimate.json`."""
    if not isinstance(found, dict):
        return _null_estimate()
    wall = found.get("wall_s") if isinstance(found.get("wall_s"), dict) else {}
    tokens = found.get("tokens") if isinstance(found.get("tokens"), dict) else {}
    return {"wall_s": {"p50": wall.get("p50"), "p80": wall.get("p80")},
            "tokens": {"p50": tokens.get("p50"), "p80": tokens.get("p80")},
            "cost_usd": found.get("cost_usd"), "n": found.get("n"),
            "basis": found.get("basis"), "confidence": found.get("confidence")}


def _gate_words(name: str, args: dict) -> str:
    """The wording of one gate check, as `position.md` prints it."""
    from . import gates
    describe = getattr(gates.REGISTRY.get(name), "describe", None)
    if describe is not None:
        try:
            return str(describe(dict(args)))
        except Exception:
            pass
    rendered = ", ".join(f"{k}={v!r}" for k, v in sorted(args.items()))
    return f"{name}({rendered})"


def _plan_checks(raw: dict) -> list[dict]:
    gate = raw.get("gate") if isinstance(raw.get("gate"), dict) else {}
    out = []
    for check in gate.get("checks") or []:
        if isinstance(check, dict):
            name = str(check.get("name"))
            args = check.get("args") if isinstance(check.get("args"), dict) else {}
        else:
            name, args = str(check), {}
        out.append({"name": name, "args": args, "text": _gate_words(name, args)})
    return out


def _plan_position(workflow_obj, step_id: str) -> str | None:
    if workflow_obj is None:
        return None
    try:
        step = workflow_obj.step_by_id(step_id)[3]
        return coords.render_position(workflow_obj, RunState(), step, attempt=1)
    except Exception:
        return None


def _plan_step(entry: dict, workflow_obj, estimates: dict) -> dict:
    raw = entry["raw"]
    agent = raw.get("agent") if isinstance(raw.get("agent"), dict) else {}
    model = agent.get("model") if isinstance(agent.get("model"), dict) else {}
    params = model.get("params") if isinstance(model.get("params"), dict) else {}
    extra = model.get("extra_body") if isinstance(model.get("extra_body"), dict) else {}
    thinking = extra.get("thinking") if isinstance(extra.get("thinking"), dict) else {}
    effort = params.get("effort")
    if effort is None:
        effort = thinking.get("reasoning_effort")
    kind = raw.get("kind") or "agent"
    return {
        "coord": entry["coord"], "id": entry["id"], "kind": kind,
        "role": agent.get("role") or kind,
        "objective": raw.get("objective"), "note": raw.get("note"),
        "harness_executor": agent.get("harness_executor") if agent else None,
        "model": model.get("model"),
        "effort": effort if isinstance(effort, (str, int)) else None,
        "profile": agent.get("agent_profile"),
        "box": agent.get("box"),
        "tools": agent.get("tools") if isinstance(agent.get("tools"), dict) else None,
        "max_iterations": agent.get("max_iterations"),
        "command_time_cap_s": agent.get("command_time_cap_s"),
        "worktree": raw.get("worktree"), "unit": raw.get("unit"),
        "write_scope": list(raw.get("write_scope") or []),
        "depends_on": list(raw.get("depends_on") or []),
        "consumes": list(raw.get("consumes") or []),
        "execution_timeout_s": raw.get("execution_timeout_s"),
        "stall_timeout_s": raw.get("stall_timeout_s"),
        "retry": raw.get("retry") if isinstance(raw.get("retry"), dict) else None,
        "gate": _plan_checks(raw),
        "handover": raw.get("handover") if isinstance(raw.get("handover"), dict) else None,
        "schema": raw.get("schema") if isinstance(raw.get("schema"), dict) else None,
        "command": raw.get("command"), "shell": raw.get("shell"),
        "merge_branch": raw.get("merge_branch"),
        "merge_message": raw.get("merge_message"),
        "brief": agent.get("brief"),
        "position": _plan_position(workflow_obj, entry["id"]),
        "estimate": _plan_estimate(estimates.get(entry["coord"])),
    }


def _plan_phase(phase: dict, steps: list[dict], default_parallel: Any,
                estimates: dict) -> dict:
    declared = (phase.get("plan") or {}).get("max_parallel")
    try:
        limit = max(1, int(declared if declared is not None
                           else (default_parallel or 1)))
    except (TypeError, ValueError):
        limit = 1
    waves = math.ceil(len(steps) / limit) if steps else 0
    worst = max((int(s["execution_timeout_s"] or 0) for s in steps), default=0)
    policy = phase.get("plan") or {}
    return {
        "index": phase["index"], "coord": phase["coord"],
        "name": phase["name"],
        "max_parallel": limit, "declared_max_parallel": declared,
        "min_success": policy.get("min_success"),
        "on_step_failure": policy.get("on_step_failure"),
        "waves": waves, "worst_timeout_s": worst,
        "timeout_bound_s": waves * worst,
        "estimate": _plan_estimate(estimates.get(phase["coord"])),
        "steps": steps,
    }


def _plan_totals(phases: list[dict], worktrees: list[dict]) -> dict:
    steps = [s for p in phases for s in p["steps"]]
    kinds = {"agent": 0, "command": 0, "merge": 0, "gate": 0}
    by_model: Counter = Counter()
    for s in steps:
        kinds[s["kind"]] = kinds.get(s["kind"], 0) + 1
        if s["kind"] == "agent":
            by_model[(s["harness_executor"], s["model"], s["effort"])] += 1
    return {
        "phases": len(phases), "steps": len(steps), "kinds": kinds,
        "by_model": [{"harness_executor": k[0], "model": k[1], "effort": k[2],
                      "n": n}
                     for k, n in sorted(by_model.items(),
                                        key=lambda kv: tuple(str(x or "")
                                                             for x in kv[0]))],
        "gate_checks": sum(len(s["gate"]) for s in steps),
        "gated_steps": sum(1 for s in steps if s["gate"]),
        "retry_steps": sum(1 for s in steps
                           if int((s["retry"] or {}).get("max") or 0) > 0),
        "handovers": sum(1 for s in steps if s["handover"]),
        "schemas": sum(1 for s in steps if s["schema"]),
        "worktrees": len(worktrees),
        "timeout_bound_s": sum(p["timeout_bound_s"] for p in phases),
    }


def plan_data(run_dir: Path, now: float | None = None) -> dict | None:
    """`/api/plan`: the declared plan of one run, whole and redacted.

    Phases, steps, totals and worktrees come from `workflow.json` alone, and
    the estimate from `estimate.json`, so a run-log line changes none of them.
    The `run` block follows the run: `status` is the status the run log
    replays to, `held_since` and `hold_pid` are null once `go` removes
    `.ohflow-hold`, and `plan_stamp` changes when `workflow.json` is written
    again. Each step carries its full brief under the artifact cap, its
    position block rendered with an empty run state, its gate checks with
    their wording, its handover contract, schema, command and limits. None
    for a packet or a directory that is not a run, which the route answers
    with 404.
    """
    from .supervisor import go_command
    from .workflow import from_jsonable

    now = time.time() if now is None else float(now)
    run_dir = Path(run_dir)
    source = open_source(run_dir)
    if source is None or source.kind != "run":
        return None
    raw = read_json(run_dir / "workflow.json")
    raw = raw if isinstance(raw, dict) else {}
    diagnostics: list[str] = []
    if not raw:
        diagnostics.append("workflow.json is missing: the run recorded no plan")
    workflow_obj = None
    if raw:
        try:
            workflow_obj = from_jsonable(raw)
        except Exception as e:
            diagnostics.append(f"position blocks are not available: "
                               f"{type(e).__name__}: {e}")
    estimate = ohestimate.read_estimate(run_dir)
    step_estimates = {s["coord"]: s for s in (estimate or {}).get("steps") or []
                      if isinstance(s, dict) and s.get("coord")}
    phase_estimates = {p["coord"]: p for p in (estimate or {}).get("phases") or []
                       if isinstance(p, dict) and p.get("coord")}
    model = source.model()
    by_phase: dict[str, list[dict]] = {}
    for entry in model["raw_steps"]:
        by_phase.setdefault(entry["phase"], []).append(
            _plan_step(entry, workflow_obj, step_estimates))
    phases = [_plan_phase(ph, by_phase.get(ph["coord"], []),
                          raw.get("max_parallel"), phase_estimates)
              for ph in model["phases"]]
    worktrees = [{"name": w.get("name"), "path": w.get("path"),
                  "branch": w.get("branch"), "base": w.get("base")}
                 for w in raw.get("worktrees") or [] if isinstance(w, dict)]
    hold = rundir.hold_record(run_dir) or {}
    record = read_json(run_dir / "dashboard.json")
    record = record if isinstance(record, dict) else {}
    run_estimate = _plan_estimate((estimate or {}).get("run"))
    run_estimate["n"] = ((estimate or {}).get("history") or {}).get("samples")
    run_estimate["generated"] = (estimate or {}).get("generated")
    run_estimate["history"] = (estimate or {}).get("history")
    payload = {
        "schema": PLAN_SCHEMA, "generated": iso(now),
        "run": {
            "id": source.run.id, "workflow": model["workflow"].get("name"),
            "status": source.status(),
            "repo": raw.get("repo"), "base_branch": raw.get("base_branch"),
            "max_parallel": raw.get("max_parallel"),
            "auto_resume": raw.get("auto_resume"),
            "transient_backoff_s": raw.get("transient_backoff_s"),
            "baseline_cmd": raw.get("baseline_cmd"),
            "held_since": hold.get("since"), "hold_pid": hold.get("pid"),
            "go_command": go_command(run_dir),
            "dashboard_url": record.get("url"),
            "plan_stamp": plan_stamp(run_dir),
        },
        "totals": _plan_totals(phases, worktrees),
        "estimate": run_estimate,
        "worktrees": worktrees,
        "phases": phases,
        "diagnostics": diagnostics,
    }
    return live._redact_tree(_cap_tree(payload, ARTIFACT_TEXT_CAP))


def _add_estimate(source, run_out: dict, model: dict, steps: list[dict],
                  invocations: list[dict]) -> None:
    """The ETA and the estimate on the run block, the estimate on each phase.

    The ETA is `live.eta`, fed the graph's own rows: phase states from the
    model, step states from `steps()`, elapsed time from the running
    invocations, finished walls from the run log. The estimate is
    `estimate.json`, written when the run started; without the file every
    estimate field is null and the ETA is unknown until a step finishes.
    `actual` is what the run has recorded so far, beside the prediction.
    """
    estimate = ohestimate.read_estimate(source.run_dir)
    status = source.status()
    elapsed = {inv["coord"]: inv.get("elapsed_s") for inv in invocations
               if inv["status"] == "running"}
    rows = [{"coord": s["coord"], "phase": s["phase"], "kind": s["kind"],
             "state": s["display"], "elapsed_s": elapsed.get(s["coord"])}
            for s in steps]
    if status in _LIVE_RUN:
        eta_s, basis = live.eta(model["phases"], rows,
                                live.finished_walls(source.state, source.run.finishes),
                                ohestimate.step_expectations(estimate))
    else:
        eta_s, basis = None, "the run is not running"
    run_out["eta_s"], run_out["eta_basis"] = eta_s, basis
    run_out["estimate"] = (dict(estimate["run"], generated=estimate.get("generated"))
                           if estimate else None)
    by_phase = {p["coord"]: p for p in (estimate or {}).get("phases") or []}
    for phase in model["phases"]:
        phase["estimate"] = _estimate_view(by_phase.get(phase["coord"]))
    if estimate is None:
        run_out["actual"] = None
        return
    tokens = 0
    for coord in source.state.steps:
        for attempt in source.run.attempts(coord):
            usage = rundir.Run.usage(attempt)
            tokens += (usage or {}).get("total_tokens") or 0
    run_out["actual"] = {"wall_s": run_out.get("elapsed_s"), "tokens": tokens}


def _estimate_view(found: dict | None) -> dict | None:
    if not found:
        return None
    return {"wall_s": found["wall_s"], "tokens": found["tokens"],
            "cost_usd": found.get("cost_usd"), "n": found["n"],
            "basis": found["basis"], "confidence": found["confidence"]}


def _with_step_estimates(source, steps: list[dict]) -> list[dict]:
    """Each step's own estimate from `estimate.json`, or null."""
    estimate = (ohestimate.read_estimate(source.run_dir)
                if getattr(source, "kind", None) == "run" else None)
    by_coord = {s["coord"]: s for s in (estimate or {}).get("steps") or []}
    for step in steps:
        step["estimate"] = _estimate_view(by_coord.get(step["coord"]))
    return steps


def _tail_start(fh, size: int, count: int) -> tuple[int, int, int]:
    """Where the last `count` records of a stream begin: the byte offset, and
    the physical and non-blank line counts before it.

    One forward pass in chunks, constant memory: the pager needs the physical
    line count because a record's id is its line number, and the non-blank
    count because blank lines are not records. A final line without its
    newline is not complete; the pager reports it as pending, as it does from
    the top. The prefix hash the cursor carries is linear in the offset
    anyway, so the pass costs nothing new.
    """
    from collections import deque
    starts: deque[tuple[int, int, int]] = deque(maxlen=max(1, count))
    fh.seek(0)
    physical = logical = 0
    consumed = 0
    line_start = 0
    carry = b""
    while consumed < size:
        chunk = fh.read(min(transcript_io.HASH_CHUNK_BYTES, size - consumed))
        if not chunk:
            break
        consumed += len(chunk)
        parts = (carry + chunk).split(b"\n")
        carry = parts.pop()
        for part in parts:
            if part.strip():
                starts.append((line_start, physical, logical))
                logical += 1
            physical += 1
            line_start += len(part) + 1
    if len(starts) < count or not starts:
        return 0, 0, 0
    return starts[0]


def transcript_data(run_dir: Path, coord: str, attempt: int, *,
                    cursor: str | None = None, limit: int | None = None,
                    tail: int | None = None,
                    now: float | None = None) -> dict | None:
    """`/api/transcript`: one attempt's transcript, paged. None → 404.

    `tail=N` starts the page N complete records before the end and sizes it
    N, so the first page is the end of the transcript and `next_cursor`
    continues from there. It overrides `limit` and replaces `cursor`.
    """
    now = time.time() if now is None else float(now)
    run_dir = Path(run_dir)
    source = open_source(run_dir)
    if source is None:
        return None
    if _resolve_attempt(source, coord, attempt) is None:
        return None
    if tail is not None:
        try:
            tail = int(tail)
        except (TypeError, ValueError):
            return None
        if not 1 <= tail <= MAX_LIMIT:
            return None
        limit, cursor = tail, None
    try:
        limit = DEFAULT_LIMIT if limit is None else int(limit)
    except (TypeError, ValueError):
        return None
    if not 1 <= limit <= MAX_LIMIT:
        return None
    supplied_page, cursor_error = transcript_io.decode_cursor(cursor)
    diagnostics: list[str] = []
    reset = bool(cursor and cursor_error)
    if cursor_error:
        diagnostics.append(cursor_error)
    src = source.transcript_source(coord, attempt)
    records: list[dict] = []
    next_cursor = None
    has_more = False
    total = None
    logical_started = logical_completed = 0
    if src.get("error"):
        diagnostics.append(src["error"])
        complete = False
    else:
        path: Path = src["path"]
        rel = src.get("rel") or _rel(run_dir, path)
        fmt = src["fmt"]
        if not _inside(run_dir, path):
            diagnostics.append(f"{rel}: resolves outside the run directory")
            complete = False
        else:
            try:
                identity = transcript_io.file_identity(path)
                size = path.stat().st_size
            except OSError:
                diagnostics.append(f"{rel}: cannot stat the transcript file")
                complete = False
            else:
                binding = transcript_io.source_binding(
                    run_dir, coord, attempt, fmt, rel)
                prefix = (lambda offset: transcript_io.file_prefix_signature(
                    path, offset, binding))
                page = _initial_page(binding, fmt, identity, prefix(0))
                if tail is not None:
                    try:
                        with path.open("rb") as probe:
                            offset, lines, logical = _tail_start(
                                probe, size, tail)
                    except OSError:
                        offset, lines, logical = 0, 0, 0
                    # Records before the tail were skipped, not read, so
                    # the logical count starts at the lines passed over.
                    page.update({"o": offset, "l": lines, "n": logical,
                                 "g": prefix(offset)})
                if supplied_page is not None:
                    signature = prefix(min(supplied_page["o"], size))
                    reason = _cursor_matches(
                        supplied_page, binding=binding, fmt=fmt,
                        identity=identity, signature=signature, size=size)
                    if reason is None and supplied_page["q"]:
                        try:
                            with path.open("rb") as probe:
                                probe.seek(supplied_page["o"])
                                raw = probe.readline()
                        except OSError:
                            raw = b""
                        if transcript_io.record_hash(raw) != supplied_page.get("r"):
                            reason = "continued transcript record was replaced"
                    if reason:
                        reset = True
                        diagnostics.append(reason
                                           + "; restarted at the beginning")
                    else:
                        page = supplied_page
                        diagnostics.append(
                            "cursor accepted: source identity and prefix "
                            "match; append polling adds no duplicates")
                skip: frozenset[int] = frozenset()
                if fmt in ("pi-cloud", "codex-cloud", "claude-cloud"):
                    from . import pi_cloud_runner
                    skip = pi_cloud_runner.replayed_lines(path)
                try:
                    with path.open("rb") as fh:
                        records, next_page, has_more, pending, \
                            logical_started, logical_completed = \
                            _read_stream_page(
                                fh, size, page, limit, rel, fmt,
                                diagnostics, prefix, skip)
                except OSError:
                    diagnostics.append(f"{rel}: cannot read from byte "
                                       f"{page['o']}")
                    records, next_page, has_more, pending = [], page, \
                        False, False
                next_cursor = transcript_io.encode_cursor(next_page)
                complete = (not has_more and not pending
                            and not _attempt_running(source, coord,
                                                     attempt, now))
                if pending:
                    diagnostics.append(
                        "a partial final JSONL line is pending and was "
                        "not emitted")
                elif not has_more and not complete:
                    diagnostics.append(
                        "the attempt is still running: this page reaches "
                        "the current end, more may follow")
                if has_more and next_page["q"]:
                    diagnostics.append(
                        "record continues losslessly in next_cursor; "
                        "concatenate continuation.data by record_id")
                if not has_more and not pending:
                    total = next_page["n"]
    payload = {
        "schema": TRANSCRIPT_SCHEMA,
        "coord": coord, "attempt": attempt, "limit": limit, "tail": tail,
        "cursor_version": transcript_io.CURSOR_VERSION,
        # Invalid cursor text can be arbitrarily large.  Diagnostics describe
        # the reset; only a successfully decoded, bounded cursor is reflected.
        "cursor": cursor if supplied_page is not None else None,
        "next_cursor": next_cursor,
        "has_more": has_more, "complete": complete, "reset": reset,
        "logical_records_started": logical_started,
        "logical_records_completed": logical_completed,
        "continuation_schema": "ohflow.record-json/1",
        "records": records,
        "diagnostics": diagnostics[:40],
    }
    if total is not None:
        payload["total"] = total
    return live._redact_tree(payload)


def _attempt_running(source, coord: str, attempt: int, now: float) -> bool:
    for inv in source.invocations(now):
        if inv["coord"] == coord and inv["attempt"] == attempt:
            return inv["status"] == "running"
    return False


def evidence_data(run_dir: Path, coord: str, attempt: int, *,
                  artifact_id: str | None = None) -> dict | None:
    """`/api/evidence`: one attempt's recorded evidence. None → 404."""
    run_dir = Path(run_dir)
    source = open_source(run_dir)
    if source is None:
        return None
    if _resolve_attempt(source, coord, attempt) is None:
        return None
    diagnostics: list[str] = []
    gate = source.gate_evidence(coord, attempt)
    artifacts = source.evidence_artifacts(coord, attempt)
    final_message = source.final_message(coord, attempt)
    events = source.evidence_events(coord, attempt)
    if artifact_id is not None:
        found = source.artifact(coord, attempt, artifact_id)
        if found is None:
            return None
        artifacts = [found]
        diagnostics.append(f"artifact {artifact_id!r} served from the "
                           f"whitelist only")
    for inv in source.invocations(0.0):
        if inv["id"] == f"{coord}@{attempt}" and inv.get("evidence_for"):
            diagnostics.append(
                f"a cached evaluation launched no agent: this evidence is "
                f"the earlier attempt {inv['evidence_for']}")
    payload = {
        "schema": EVIDENCE_SCHEMA,
        "coord": coord, "attempt": attempt,
        "gate": _cap_tree(gate.get("gate"), STRING_CAP, lists=60)
        if isinstance(gate.get("gate"), dict) else None,
        "gate_source": gate.get("source"),
        "final_message": final_message,
        "artifacts": artifacts[:MAX_ARTIFACTS],
        "events": events,
        "diagnostics": diagnostics,
        "tool_output": None,
        "open_tool_call": None,
    }
    adir = rundir.attempt_dir(run_dir, coord, int(attempt))
    if adir.is_dir():
        payload["tool_output"] = tool_output.summary(adir)
        result = read_json(adir / "result.json")
        if isinstance(result, dict) and isinstance(result.get("open_tool_call"), dict):
            payload["open_tool_call"] = result["open_tool_call"]
    return live._redact_tree(payload)


def _resolve_attempt(source, coord: str, attempt: int) -> dict | None:
    """The (coord, attempt) the request names, validated. None → 404.

    The coordinate must name a step of this run and the attempt a recorded
    execution of it. Nothing from the request ever joins a path unchecked.
    """
    if not isinstance(coord, str) or not coord:
        return None
    try:
        attempt = int(attempt)
    except (TypeError, ValueError):
        return None
    if not 0 <= attempt <= MAX_ATTEMPT:
        return None
    model = source.model()
    if coord not in model["by_coord"]:
        return None
    for inv in source.invocations(0.0):
        if inv["coord"] == coord and inv["attempt"] == attempt:
            return inv
    # A launched attempt the run log opened but this reader has not matched
    # (a running execution is in the same list), so falling through here
    # means the pair is genuinely unrecorded.
    return None

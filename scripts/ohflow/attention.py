"""The attention strip: what needs a person, what recovers by itself, and what
is only a signal.

`derive(source, now, steps, invocations)` turns the graph a `_RunSource` already
holds into a short list of items, one per condition, grouped by consequence:

* `intervention`  the engine permits no further start by itself: a failed or
                  quarantined step whose retry budget is spent, excluded work,
                  a deferred step with no auto-resume pass left, a run that is
                  paused, orphaned, crashed or interrupted.
* `recovering`    the engine will act without a person: a deferred step under
                  the provider cooldown or waiting for an auto-resume pass, a
                  retry that is running right now.
* `signal`        a measured threshold worth a look, never a verdict: a red or
                  amber idle signal, an attempt near its execution timeout, a
                  step whose checks ran longer than its agent.

Every item answers five questions the design record asks: what was observed
and when, what was expected, what it affects (the phase and the declared
dependants), what the engine permits next (the exact CLI command, or why there
is none), and which run-log line is the evidence. The evidence names the
invocation, so the page can select it.

Rules this module keeps, and why:

* **It reads the model, never the files.** Everything comes from the run log
  replay and the invocation rows `dashboard_data` built. The one file it
  touches is `run.json`, through `live.resume_command`, because that is where
  the exact `--resume` command is recorded.
* **One item per condition.** A paused run is one item that owns the resume
  command; its deferred steps are its impact, not a second alarm each.
* **A packet has none.** `docs/dashboard-basis` is a historical export, and
  nothing in it can still need a person.
"""

from __future__ import annotations

from typing import Any

from . import attempts as ohattempts
from . import gates as ohgates
from . import live
from .activity import epoch, first_line, hms, iso

__all__ = ["GROUPS", "derive"]

#: Consequence order: what a watcher must act on comes first.
GROUPS = ("intervention", "recovering", "signal")

_FAILED = frozenset({"failed", "timeout", "quarantined"})
_STOPPED = ("paused", "orphaned", "crashed", "interrupted")
_RESTART_KINDS = frozenset({"retry", "auto_resume"})
#: An attempt this far into its execution timeout is near its deadline, which
#: is the amber wall signal of spec §9.
DEADLINE_FRACTION = 0.75


def derive(source, now: float, steps: list[dict],
           invocations: list[dict]) -> list[dict]:
    """The attention items of one run, in consequence order."""
    ctx = _Context(source, now, steps, invocations)
    items: list[dict] = []
    run_item = ctx.run_item()
    if run_item is not None:
        items.append(run_item)
    items.extend(ctx.excluded_items())
    items.extend(ctx.token_items())
    for step in steps:
        items.extend(ctx.step_items(step))
        items.extend(ctx.price_items(step))
    for inv in invocations:
        if inv["status"] == "running":
            items.extend(ctx.signal_items(inv))
    items.sort(key=lambda item: GROUPS.index(item["group"]))
    return items


def _dur(seconds: Any) -> str:
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


class _Context:
    """The run as the items read it: steps by coordinate, invocations by id,
    run-log entries by event."""

    def __init__(self, source, now: float, steps: list[dict],
                 invocations: list[dict]):
        self.source = source
        self.now = now
        self.state = source.state
        self.steps = steps
        self.by_coord = {s["coord"]: s for s in steps}
        self.invocations = invocations
        self.status = source.status()
        self.live = self.status in live._LIVE_RUN
        wf = source.model()["workflow"]
        self.auto_resume = int(self.state.meta.get(
            "auto_resume", wf.get("auto_resume")) or 0)
        self.phases = {p["coord"]: p for p in source.model()["phases"]}
        cooldown = epoch(self.state.cooldown_until)
        self.cooldown = cooldown if (cooldown is not None and cooldown > now
                                     and self.live) else None

    # ---- lookups

    def entry(self, event: str, coord: str | None = None,
              attempt: int | None = None) -> dict | None:
        """The last run-log entry of this event for this coordinate."""
        found = None
        for entry in self.source.entries:
            rec = entry["rec"]
            if rec.get("event") != event:
                continue
            if coord is not None and rec.get("coord") != coord:
                continue
            if attempt is not None and rec.get("attempt") != attempt:
                continue
            found = entry
        return found

    def evidence(self, event: str | None, coord: str | None = None,
                 attempt: int | None = None) -> dict | None:
        # An exclusion names the work, not an attempt; the entry is matched
        # on the coordinate alone while the link still selects the attempt.
        entry = (self.entry(event, coord,
                            None if event == "work_excluded" else attempt)
                 if event else None)
        if entry is None and coord is None:
            return None
        rec = (entry or {}).get("rec") or {}
        return {
            "id": f"{coord}@{attempt}" if coord is not None
            and isinstance(attempt, int) else None,
            "coord": coord, "attempt": attempt,
            "event": rec.get("event") if entry else None,
            "line": entry["line"] if entry else None,
            "ts": rec.get("ts") if entry else None,
        }

    def invocations_of(self, coord: str) -> list[dict]:
        return [i for i in self.invocations if i["coord"] == coord]

    def latest(self, coord: str) -> dict | None:
        mine = self.invocations_of(coord)
        return mine[-1] if mine else None

    def dependants(self, coord: str) -> list[str]:
        return [s["coord"] for s in self.steps if coord in (s.get("depends_on") or [])]

    def impact(self, step: dict) -> dict:
        phase = self.phases.get(step["phase"]) or {}
        dependants = self.dependants(step["coord"])
        text = f"phase {phase.get('index', '?')} {phase.get('name') or step['phase']}"
        if dependants:
            names = ", ".join(self.by_coord[c]["id"] if c in self.by_coord else c
                              for c in dependants)
            text += f"; dependants: {names}"
        else:
            text += "; no declared dependants"
        return {"phase": step["phase"], "phase_name": phase.get("name"),
                "dependants": dependants, "text": text}

    def item(self, group: str, kind: str, step: dict | None, *,
             attempt: int | None, observed: str, observed_ts: str | None,
             expected: str, impact: dict, command: str | None,
             next_text: str, evidence: dict | None) -> dict:
        return {
            "group": group, "kind": kind,
            "coord": step["coord"] if step else None,
            "attempt": attempt,
            "step_id": step["id"] if step else None,
            "role": step.get("role") if step else None,
            "phase": step["phase"] if step else None,
            "observed": {"text": observed, "ts": observed_ts},
            "expected": expected,
            "impact": impact,
            "next": {"command": command, "text": next_text},
            "evidence": evidence,
        }

    # ---- the run as a whole

    def run_item(self) -> dict | None:
        status = self.status
        if status not in _STOPPED:
            return None
        deferred = [s for s in self.steps if s["status"] == "deferred"]
        interrupted = [i for i in self.invocations
                       if i["status"] == "interrupted"]
        unstarted = [s for s in self.steps
                     if s["status"] == "pending" and s["display"] == "waiting"]
        parts = []
        if deferred:
            parts.append("deferred and never judged: "
                         + ", ".join(s["id"] for s in deferred))
        if interrupted:
            parts.append("interrupted while running: "
                         + ", ".join(i["id"] for i in interrupted))
        if unstarted:
            parts.append(f"{len(unstarted)} step(s) never started")
        impact = {"phase": None, "phase_name": None,
                  "dependants": [s["coord"] for s in deferred]
                  + [i["coord"] for i in interrupted],
                  "text": "; ".join(parts) or "every step reached a verdict"}
        last = self.source.entries[-1] if self.source.entries else None
        last_ts = (last or {}).get("rec", {}).get("ts")
        if status == "paused":
            entry = self.entry("run_finished")
            killed = [s["id"] for s in deferred
                      if getattr(self.state.steps.get(s["coord"]), "killed",
                                 None) is not None]
            if self.state.meta.get("token_refusals"):
                observed = ("the run paused: the token budget admits no "
                            "further agent step")
            elif killed:
                observed = ("the run paused: ohflow kill ended "
                            + ", ".join(killed)
                            + ("; a transient fault deferred the rest"
                               if len(killed) < len(deferred) else ""))
            else:
                observed = "the run paused on a transient fault"
            evidence = self.evidence("run_finished")
            ts = (entry or {}).get("rec", {}).get("ts") or last_ts
        elif status == "orphaned":
            observed = ("the run log says running, and the supervisor process "
                        "is dead: a hard kill or a machine restart")
            evidence = {"id": None, "coord": None, "attempt": None,
                        "event": (last or {}).get("rec", {}).get("event"),
                        "line": (last or {}).get("line"), "ts": last_ts}
            ts = last_ts
        else:
            record = self.source.run.exit_record() or {}
            error = first_line(record.get("error"), 160)
            observed = f"the run {status}" + (f": {error}" if error else "")
            evidence = {"id": None, "coord": None, "attempt": None,
                        "event": None, "line": None, "ts": record.get("at")}
            ts = record.get("at") or last_ts
        command = live.resume_command(self.source.run_dir)
        if command:
            next_text = ("resume reruns the deferred steps and starts the "
                         "ones that never began; passed steps stay cached")
        else:
            next_text = ("resume the run with --resume; run.json does not "
                         "record the exact command")
        return self.item("intervention", f"{status}_run", None, attempt=None,
                         observed=observed, observed_ts=ts,
                         expected="a live supervisor carrying the run to "
                                  "run_finished",
                         impact=impact, command=command, next_text=next_text,
                         evidence=evidence)

    def token_items(self) -> list[dict]:
        out = []
        for entry in self.source.entries:
            rec = entry["rec"]
            payload = rec.get("payload") or {}
            if rec.get("event") != "token_budget" or payload.get("kind") != "overshoot":
                continue
            coord = rec.get("coord")
            step = self.by_coord.get(coord)
            attempt = rec.get("attempt")
            out.append(self.item(
                "intervention", "token_overshoot", step, attempt=attempt,
                observed=(f"{payload.get('used_tokens')} tokens used on a grant "
                          f"of {payload.get('grant_tokens')}: "
                          f"{payload.get('overshoot_tokens')} past the run's "
                          f"token budget of {payload.get('limit_tokens')}"),
                observed_ts=rec.get("ts"),
                expected="settled tokens within the run's token budget",
                impact=(self.impact(step) if step else
                        {"phase": None, "phase_name": None, "dependants": [],
                         "text": "the run's token budget"}),
                command=None,
                next_text=("the tokens are spent; a later agent step starts "
                           "only while the ledger has room for its grant"),
                evidence=self.evidence("token_budget", coord, attempt)))
        return out

    # ---- excluded work

    def excluded_items(self) -> list[dict]:
        out = []
        for key, payload in self.state.exclusions.items():
            coord = payload.get("coord") or key.rsplit("@", 1)[0]
            step = self.by_coord.get(coord)
            if step is None:
                continue
            fingerprint = payload.get("fingerprint")
            mine = [i for i in self.invocations_of(coord)
                    if fingerprint is None or i.get("fingerprint") == fingerprint]
            latest = (mine or self.invocations_of(coord) or [None])[-1]
            attempt = latest["attempt"] if latest else None
            entry = self.entry("work_excluded", coord)
            reason = str(payload.get("reason") or "excluded")
            evidence = self.evidence("work_excluded", coord, attempt)
            out.append(self.item(
                "intervention", "excluded", step, attempt=attempt,
                observed=reason,
                observed_ts=(entry or {}).get("rec", {}).get("ts"),
                expected="a passed verdict within the execution budget",
                impact=self.impact(step), command=None,
                next_text=("no start permitted: the work is excluded from this "
                           "run directory; a changed brief or input is new "
                           "work with a fresh budget"),
                evidence=evidence))
        return out

    # ---- one step

    def step_items(self, step: dict) -> list[dict]:
        coord = step["coord"]
        rec = self.state.steps.get(coord)
        status = step["status"]
        latest = self.latest(coord)
        if status in _FAILED and latest is not None:
            return [self.failed_item(step, latest)]
        if status == "deferred" and self.live and rec is not None:
            if rec.fingerprint and f"{coord}@{rec.fingerprint}" in self.state.exclusions:
                return []                       # the exclusion item owns it
            return [self.deferred_item(step, rec, latest)]
        if latest is not None and latest["status"] == "running" \
                and latest.get("start_kind") in _RESTART_KINDS:
            return [self.retry_item(step, latest)]
        return []

    def failed_item(self, step: dict, inv: dict) -> dict:
        rec = self.state.steps.get(step["coord"])
        cause = inv.get("cause") or inv.get("error") or inv["status"]
        gate = inv.get("gate") or {}
        decision = (rec.retry_decision if rec else None) or inv.get("retry_decision")
        return self.item(
            "intervention", "failed_step", step, attempt=inv["attempt"],
            observed=f"attempt {inv['attempt']} {inv['status']}: {cause}",
            observed_ts=inv.get("finished"),
            expected=("every gate check passed" if gate.get("passed") is False
                      else "a passed verdict"),
            impact=self.impact(step), command=None,
            next_text=("no further start by the engine: " + decision
                       if decision else
                       "no further start by the engine: no retry decision "
                       "is recorded"),
            evidence=self.evidence("attempt_finished", step["coord"],
                                   inv["attempt"]))

    def deferred_item(self, step: dict, rec, latest: dict | None) -> dict:
        raw = self.source.model()["by_coord"][step["coord"]]["raw"]
        retry = raw.get("retry") if isinstance(raw.get("retry"), dict) else {}
        allowed, why = ohattempts.may_start(
            self.state, step["coord"], rec.fingerprint,
            start_kind="auto_resume", retry_max=int(retry.get("max") or 0),
            auto_resume=self.auto_resume)
        attempt = latest["attempt"] if latest else None
        observed = "deferred: " + (first_line(rec.error, 140) or "transient fault")
        evidence = self.evidence("attempt_finished", step["coord"], attempt)
        if rec.killed is not None:
            return self.item(
                "intervention", "killed_step", step, attempt=attempt,
                observed=observed, observed_ts=rec.ended,
                expected="a verdict, which ohflow kill withheld",
                impact=self.impact(step), command=None,
                next_text=("no start by the engine: `run --resume` starts it "
                           "again once the run stops; edit its brief first to "
                           "give it a new direction"),
                evidence=evidence)
        if not allowed:
            return self.item(
                "intervention", "budget_spent", step, attempt=attempt,
                observed=observed, observed_ts=rec.ended,
                expected="a verdict from the provider",
                impact=self.impact(step), command=None,
                next_text="no auto-resume pass left: " + why,
                evidence=evidence)
        if self.cooldown is not None:
            kind = "deferred_cooldown"
            next_text = ("automatic: an auto-resume pass reruns it after the "
                         f"provider cooldown ends at {hms(self.cooldown)}")
        else:
            kind = "deferred_auto_resume"
            next_text = ("automatic: an auto-resume pass reruns it once the "
                         "phase's other steps settle")
        return self.item("recovering", kind, step, attempt=attempt,
                         observed=observed, observed_ts=rec.ended,
                         expected="a verdict from the provider",
                         impact=self.impact(step), command=None,
                         next_text=next_text, evidence=evidence)

    def retry_item(self, step: dict, running: dict) -> dict:
        prior = None
        for other in self.invocations_of(step["coord"]):
            if isinstance(other["attempt"], int) \
                    and other["attempt"] < running["attempt"]:
                prior = other
        cause = (prior or {}).get("cause") or (prior or {}).get("status") \
            or "an earlier attempt failed"
        decision = (prior or {}).get("retry_decision") \
            or f"automatic {running.get('start_kind')}"
        evidence = None
        if prior is not None:
            evidence = self.evidence("retry_decided", step["coord"],
                                     prior["attempt"])
            if evidence and evidence["line"] is None:
                evidence = self.evidence("attempt_started", step["coord"],
                                         running["attempt"])
        return self.item(
            "recovering", "retry_running", step, attempt=running["attempt"],
            observed=(f"attempt {prior['attempt']} {prior['status']}: {cause}"
                      if prior else cause),
            observed_ts=(prior or {}).get("finished"),
            expected=f"attempt {running['attempt']} passes its gate",
            impact=self.impact(step), command=None,
            next_text=f"automatic: {decision}; attempt {running['attempt']} "
                      f"is running", evidence=evidence)

    def price_items(self, step: dict) -> list[dict]:
        entry = self.entry("attempt_finished", step["coord"])
        rec = (entry or {}).get("rec") or {}
        payload = rec.get("payload") or {}
        if payload.get("status") == "cached" or payload.get("kind", "agent") != "agent":
            return []
        checks = ohgates.check_seconds(payload.get("gate"))
        wall = payload.get("wall_seconds")
        if checks is None or not isinstance(wall, (int, float)):
            return []
        agent = round(max(0.0, wall - checks), 1)
        if checks <= agent:
            return []
        return [self.item(
            "signal", "checks_over_agent", step, attempt=rec.get("attempt"),
            observed=f"its checks ran {_dur(checks)}, its agent {_dur(agent)}",
            observed_ts=rec.get("ts"),
            expected="checks that take less time than the work they check",
            impact=self.impact(step), command=None,
            next_text=("none: a price, not a fault; a check that costs more "
                       "than it catches is a candidate to cut"),
            evidence=self.evidence("attempt_finished", step["coord"],
                                   rec.get("attempt")))]

    # ---- signals on running attempts

    def signal_items(self, inv: dict) -> list[dict]:
        step = self.by_coord.get(inv["coord"])
        if step is None:
            return []
        out = []
        health = inv.get("health") or {}
        signal = health.get("idle_signal")
        idle = health.get("idle_s")
        if signal in ("amber", "red") and idle is not None:
            out.append(self.item(
                "signal", f"idle_{signal}", step, attempt=inv["attempt"],
                observed=health.get("note")
                or f"no recorded activity for {int(idle)} s",
                observed_ts=iso(self.now - float(idle)),
                expected=f"recorded activity within {int(health.get('idle_amber_s') or 0)} s",
                impact=self.impact(step), command=None,
                next_text=("none: a threshold, not a proven stall; read the "
                           "output tail, the engine kills the attempt at its "
                           "stall timeout" if health.get("stall_timeout_s")
                           else "none: a threshold, not a proven stall; read "
                                "the output tail"),
                evidence=self.evidence("attempt_started", inv["coord"],
                                       inv["attempt"])))
        raw = self.source.model()["by_coord"][inv["coord"]]["raw"]
        timeout = raw.get("execution_timeout_s")
        elapsed = inv.get("elapsed_s")
        if isinstance(timeout, (int, float)) and timeout > 0 \
                and isinstance(elapsed, (int, float)) \
                and elapsed >= DEADLINE_FRACTION * timeout:
            out.append(self.item(
                "signal", "deadline", step, attempt=inv["attempt"],
                observed=f"running for {_dur(elapsed)} of the "
                         f"{_dur(timeout)} execution timeout",
                observed_ts=inv.get("started"),
                expected="a verdict before the execution timeout",
                impact=self.impact(step), command=None,
                next_text=("none: at the timeout the engine kills the attempt "
                           "and records timeout"),
                evidence=self.evidence("attempt_started", inv["coord"],
                                       inv["attempt"])))
        return out

"""`/api/workflow`: the run as graph truth.

The real `m7-smoke-fixes` packet (tests/fixtures/dashboard-basis) is the truth for
counts and relationships: nine launched attempts, two cached evaluations that
launched no agent, one failed check, one automatic retry, five run segments
and five campaign rounds. The current-format fixture proves the same fields
from a run directory. A live fixture - a current-format run whose worker is
still running - proves the in-progress fields the component review asked for:
stable ids, elapsed time, latest observed activity, and idle thresholds that
never claim a proven stall. No fake running agent is ever added to the
finished m7 history.
"""

from __future__ import annotations

import json
import shutil
import urllib.error
import urllib.request
from pathlib import Path

from dashboard_support import T0, RunLog, agent, command, mark_alive
from support import TempCase

from ohflow import dashboard, dashboard_data

HERE = Path(__file__).resolve().parent
PACKET = HERE / "fixtures" / "dashboard-basis"
IMPL = "01.implement/01.implement"
REVIEW = "02.review/01.review"

#: Loopback requests must never route through a configured proxy.
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def get(url: str, **kwargs):
    req = urllib.request.Request(url, **kwargs)
    try:
        with OPENER.open(req, timeout=10) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def workflow(run_dir=PACKET):
    return dashboard_data.workflow_data(run_dir, now=T0 + 10_000)


def by_id(payload, inv_id):
    return next(i for i in payload["invocations"] if i["id"] == inv_id)


def live_run(run_dir: Path) -> Path:
    """The current-format live fixture: one worker, launched and running."""
    worker = agent("worker")
    run_dir.mkdir(parents=True)
    (run_dir / "workflow.json").write_text(json.dumps({
        "name": "live-fixture", "max_parallel": 1, "auto_resume": 0,
        "phases": [{"name": "Build", "slug_override": None, "max_parallel": 1,
                    "on_step_failure": "quarantine", "min_success": "all",
                    "steps": [worker]}],
    }), encoding="utf-8")
    log = RunLog(run_dir)
    log.phase(1, "01.build", "Build", ["01.build/01.worker"], 1)
    log.start(2, "01.build/01.worker", 1, "initial", fingerprint="fp-live")
    mark_alive(run_dir)
    attempt = (run_dir / "phases" / "01.build" / "01.worker" / "attempts"
               / "01")
    session = attempt / "session"
    session.mkdir(parents=True)
    lines = [
        {"type": "session", "version": 3, "id": "live",
         "timestamp": "2026-09-30T12:00:02.000Z", "cwd": str(run_dir)},
        {"type": "message", "id": "m1",
         "timestamp": "2026-09-30T12:00:03.000Z",
         "message": {"role": "assistant", "content": [
             {"type": "thinking", "thinking": "I should look around first"},
             {"type": "toolCall", "id": "call-1", "name": "read",
              "arguments": {"path": "README.md"}},
         ]}},
    ]
    (session / "2026-09-30T12-00-02-000Z_live.jsonl").write_text(
        "\n".join(json.dumps(line) for line in lines) + "\n",
        encoding="utf-8")
    (attempt / "result.json").write_text("{}", encoding="utf-8")
    return run_dir


class ThePacket(TempCase):

    def test_the_recorded_counts_come_through(self):
        payload = workflow()
        self.assertEqual(payload["schema"], "ohflow.dashboard/1")
        self.assertEqual(payload["source"], "packet")
        self.assertEqual(payload["run"]["id"], "m7-smoke-fixes")
        self.assertEqual(payload["run"]["status"], "finished")
        self.assertEqual(payload["run"]["mode"], "final")
        self.assertEqual(len(payload["phases"]), 2)
        self.assertEqual(len(payload["steps"]), 2)
        self.assertEqual(len(payload["invocations"]), 11)

    def test_launches_cached_and_preparations_are_distinct(self):
        payload = workflow()
        launched = [i for i in payload["invocations"]
                    if i["launch"] == "agent"]
        cached = [i for i in payload["invocations"]
                  if i["launch"] == "cached"]
        self.assertEqual(len(launched), 9)
        self.assertEqual(len(cached), 2)
        for inv in cached:
            self.assertEqual(inv["attempt"], 0)
            self.assertEqual(inv["status"], "cached")
            self.assertEqual(inv["wall_s_basis"],
                             "Engine-reported default; no new invocation "
                             "duration was measured.")
        # Nine invocations really spent an agent; the packet names the lane.
        lanes = {i["harness_executor"] for i in launched}
        self.assertEqual(lanes, {"claude", "pi"})

    def test_the_retry_edge_is_recorded_not_inferred(self):
        payload = workflow()
        retries = [e for e in payload["edges"] if e["kind"] == "retry"]
        self.assertEqual(len(retries), 1)
        edge = retries[0]
        self.assertEqual(edge["from"], f"{IMPL}@4")
        self.assertEqual(edge["to"], f"{IMPL}@5")
        # The decision text the engine recorded, verbatim.
        self.assertEqual(edge["label"],
                         "retry start, execution 2 of 5, attempt 5")
        # Campaign revisions are context, not engine retries: attempts 2-4
        # start fresh revisions (new fingerprints) and get no retry edge.
        kinds = {by_id(payload, f"{IMPL}@{n}")["start_kind"]
                 for n in (2, 3, 4)}
        self.assertEqual(kinds, {"initial"})
        self.assertEqual(len([e for e in payload["edges"]
                              if e["kind"] in ("retry", "auto_resume")]), 1)

    def test_cached_evaluations_link_the_earlier_attempt(self):
        payload = workflow()
        cached = {c["id"]: c for c in payload["cached"]}
        self.assertEqual(cached[f"{IMPL}@0"]["evidence_for"], f"{IMPL}@5")
        self.assertEqual(cached[f"{REVIEW}@0"]["evidence_for"], f"{REVIEW}@4")

    def test_dependency_and_barrier_edges_are_distinct_and_sourced(self):
        payload = workflow()
        depends = [e for e in payload["edges"] if e["kind"] == "depends_on"]
        barriers = [e for e in payload["edges"] if e["kind"] == "phase"]
        self.assertEqual(len(depends), 1)
        self.assertEqual(len(barriers), 1)
        self.assertEqual(depends[0]["from"], IMPL)
        self.assertEqual(depends[0]["to"], REVIEW)
        self.assertIn("case.json", depends[0]["source"])
        self.assertNotEqual(depends[0]["source"], barriers[0]["source"])
        self.assertEqual(barriers[0]["label"], "phase barrier")

    def test_five_run_segments_with_the_recorded_boundaries(self):
        payload = workflow()
        segments = payload["segments"]
        self.assertEqual(len(segments), 5)
        self.assertEqual([len(s["invocations"]) for s in segments],
                         [2, 2, 2, 3, 0])
        # Segment 5 is the cached round: nothing launched, both steps cached.
        self.assertEqual(segments[-1]["status"], "finished")
        self.assertTrue(all(s["finished"] for s in segments))
        self.assertTrue(all("line" in s["closed_by"] for s in segments))

    def test_campaign_rounds_come_from_the_packet(self):
        payload = workflow()
        campaign = payload["campaign"]
        self.assertIsNotNone(campaign)
        self.assertEqual(campaign["milestone"], "m7-smoke-fixes")
        verdicts = [r["verdict"] for r in campaign["rounds"]
                    if r.get("verdict")]
        self.assertEqual(verdicts, ["REVISE", "REVISE", "REVISE", "PASS",
                                    "PASS"])
        # The refused PASS is there, with the driver's escalation beside it.
        escalations = [r["why"] for r in campaign["rounds"]
                       if r.get("event") == "escalated"]
        self.assertEqual(len(escalations), 2)

    def test_invocations_are_ordered_by_start(self):
        payload = workflow()
        stamps = [i["started"] or i["finished"]
                  for i in payload["invocations"]]
        self.assertEqual(stamps, sorted(stamps))
        # A cached evaluation has no start: it stays null, not zero.
        cached = by_id(payload, f"{IMPL}@0")
        self.assertIsNone(cached["started"])
        self.assertIsNotNone(cached["finished"])

    def test_events_keep_the_original_names_beside_the_normalized_ones(self):
        payload = workflow()
        started = next(e for e in payload["events"]
                       if e["event"] == "attempt.started")
        self.assertEqual(started["original_type"], "step_started")
        self.assertEqual(started["source"]["line"], 4)
        self.assertEqual(started["ts"], "2026-10-01T21:48:37Z")

    def test_claims_and_checks_are_separate_fields(self):
        payload = workflow()
        failed = by_id(payload, f"{IMPL}@4")
        # The check result...
        self.assertEqual(failed["gate"]["failed"], ["command_exit"])
        self.assertEqual(failed["short_cause"], "command_exit")
        # ...and the agent's claim, recorded apart from it.
        self.assertIsNotNone(failed["final_message"])
        self.assertNotIn("command_exit", failed["final_message"])

    def test_diagnostics_name_the_packet_and_its_holes(self):
        payload = workflow()
        joined = "\n".join(payload["diagnostics"])
        self.assertIn("ohflow.dashboard-case/1", joined)
        self.assertIn("cached", joined)

    def test_the_payload_carries_no_transcript(self):
        payload = workflow()
        text = json.dumps(payload)
        self.assertNotIn('"blocks"', text)
        self.assertNotIn("tool_call", text)


class CurrentFormat(TempCase):

    def setUp(self):
        super().setUp()
        from dashboard_support import RunLog, workflow_json
        self.run = self.tmp / "synthetic"
        first = agent("first")
        second = agent("second")
        second["depends_on"] = ["first"]
        fourth = agent("fourth")
        fourth["depends_on"] = ["second"]
        third = command("third")
        workflow_json(self.run, [("Alpha", [first, second, fourth], 2),
                                 ("Beta", [third], 1)], name="synthetic")
        log = RunLog(self.run)
        log.phase(1, "01.alpha", "Alpha",
                  ["01.alpha/01.first", "01.alpha/02.second",
                   "01.alpha/03.fourth"], 2)
        log.start(2, "01.alpha/01.first", 1, "initial", fingerprint="fp-a")
        # first fails and a retry with the same inputs is decided and started
        log.finish(3, "01.alpha/01.first", 1, "failed", fingerprint="fp-a",
                   error="boom")
        log.add(4, "retry_decided", "01.alpha/01.first", 1,
                payload={"retry_decision": "retry start, execution 2 of 3, "
                                           "attempt 2"})
        log.start(5, "01.alpha/01.first", 2, "retry", fingerprint="fp-a")
        log.finish(6, "01.alpha/01.first", 2, "passed", fingerprint="fp-a")
        log.phase(7, "02.beta", "Beta", ["02.beta/01.third"], 1)
        # a synthetic finish with no start: a cached evaluation
        log.add(8, "attempt_finished", "02.beta/01.third", 0, payload={
            "status": "cached", "step_id": "third", "kind": "command",
            "fingerprint": "fp-t", "wall_seconds": 0.0,
            "gate": {"passed": True, "checks": []}})
        self.payload = dashboard_data.workflow_data(self.run, now=T0 + 1000)

    def test_dependency_and_phase_edges_are_separate_and_sourced(self):
        edges = self.payload["edges"]
        depends = [e for e in edges if e["kind"] == "depends_on"]
        self.assertEqual(len(depends), 2)
        self.assertEqual({(e["from"], e["to"]) for e in depends},
                         {("01.alpha/01.first", "01.alpha/02.second"),
                          ("01.alpha/02.second", "01.alpha/03.fourth")})
        self.assertEqual([e["source"] for e in depends],
                         ["workflow.json", "workflow.json"])
        barriers = [e for e in edges if e["kind"] == "phase"]
        # every Alpha step -> the Beta step
        self.assertEqual(len(barriers), 3)
        self.assertEqual({e["from"] for e in barriers},
                         {"01.alpha/01.first", "01.alpha/02.second",
                          "01.alpha/03.fourth"})
        self.assertEqual({e["to"] for e in barriers},
                         {"02.beta/01.third"})

    def test_the_retry_edge_carries_the_decision_that_caused_it(self):
        retry = next(e for e in self.payload["edges"]
                     if e["kind"] == "retry")
        self.assertEqual(retry["from"], "01.alpha/01.first@1")
        self.assertEqual(retry["to"], "01.alpha/01.first@2")
        self.assertEqual(retry["label"],
                         "retry start, execution 2 of 3, attempt 2")
        self.assertIn("retry_decided", retry["source"])

    def test_a_cached_finish_is_not_a_launch(self):
        cached = by_id(self.payload, "02.beta/01.third@0")
        self.assertEqual(cached["launch"], "cached")
        self.assertEqual(cached["status"], "cached")
        self.assertIsNone(cached["started"])

    def test_segments_close_at_run_finished(self):
        segments = self.payload["segments"]
        self.assertEqual(len(segments), 1)
        self.assertIsNone(segments[0]["finished"])
        # No supervisor: the open segment is named orphaned, not running.
        self.assertEqual(segments[0]["status"], "orphaned")
        self.assertIn("01.alpha/01.first@2", segments[0]["invocations"])

    def test_campaign_is_null_for_one_run_and_named_so(self):
        self.assertIsNone(self.payload["campaign"])
        self.assertTrue(any("campaign" in d for d in
                            self.payload["diagnostics"]))

    def test_events_cite_their_run_log_line(self):
        events = self.payload["events"]
        self.assertTrue(all(e["source"]["path"] == "run-log.jsonl"
                            for e in events))
        lines = [e["source"]["line"] for e in events]
        self.assertEqual(lines, sorted(lines))
        self.assertEqual(lines[0], 1)

    def test_unstarted_work_names_why_it_waits(self):
        steps = {s["coord"]: s for s in self.payload["steps"]}
        third = steps["02.beta/01.third"]
        self.assertEqual(third["display"], "done")     # cached: no waiting
        # fourth depends on second, which never ran: the dependency is named.
        fourth = steps["01.alpha/03.fourth"]
        self.assertEqual(fourth["display"], "waiting")
        self.assertEqual(fourth["waiting_on"], "dependency")
        self.assertIn("01.alpha/02.second", fourth["reason"])
        # The run stopped (no supervisor): never-started work with nothing in
        # front of it says the run stopped, not that anything failed.
        second = steps["01.alpha/02.second"]
        self.assertEqual(second["display"], "waiting")
        self.assertEqual(second["waiting_on"], "stopped")


class StoppedRunWaiting(TempCase):

    def test_a_phase_that_never_started_waits_for_its_barrier(self):
        from dashboard_support import RunLog, workflow_json
        run = self.tmp / "stopped"
        workflow_json(run, [("Alpha", [agent("only")], 1),
                            ("Beta", [command("later")], 1)])
        log = RunLog(run)
        log.phase(1, "01.alpha", "Alpha", ["01.alpha/01.only"], 1)
        log.start(2, "01.alpha/01.only", 1)
        payload = dashboard_data.workflow_data(run, now=T0 + 100)
        steps = {s["coord"]: s for s in payload["steps"]}
        later = steps["02.beta/01.later"]
        self.assertEqual(later["display"], "waiting")
        self.assertEqual(later["waiting_on"], "phase")
        self.assertEqual(payload["run"]["mode"], "final")


class TheLiveFixture(TempCase):
    """A current-format run whose worker is running right now."""

    def setUp(self):
        super().setUp()
        self.run = live_run(self.tmp / "live-run")
        # Late enough that the worker's last record (T0+3) is past the red
        # idle threshold (900 s), which is what makes the health note show.
        self.now = T0 + 2000.0

    def test_the_running_invocation_keeps_its_identity_while_polling(self):
        first = dashboard_data.workflow_data(self.run, now=self.now)
        second = dashboard_data.workflow_data(self.run, now=self.now + 5)
        a, b = first["invocations"][0], second["invocations"][0]
        self.assertEqual(a["id"], "01.build/01.worker@1")
        self.assertEqual(a["id"], b["id"])
        self.assertEqual(a["started"], b["started"])
        self.assertEqual(b["elapsed_s"], a["elapsed_s"] + 5)

    def test_the_running_invocation_carries_its_latest_activity(self):
        payload = dashboard_data.workflow_data(self.run, now=self.now)
        inv = payload["invocations"][0]
        self.assertEqual(inv["status"], "running")
        self.assertEqual(inv["elapsed_s"], 1998.0)
        self.assertEqual(inv["activity"]["latest_tool"]["name"], "read")
        self.assertEqual(inv["activity"]["latest_reasoning"]["text"],
                         "I should look around first")
        self.assertEqual(payload["steps"][0]["display"], "running")

    def test_an_idle_threshold_never_claims_a_proven_stall(self):
        payload = dashboard_data.workflow_data(self.run, now=self.now)
        health = payload["invocations"][0]["health"]
        self.assertEqual(health["idle_signal"], "red")
        self.assertIn("not a proven stall", health["note"])
        self.assertIn("threshold", health["note"])

    def test_the_end_transition_keeps_the_id_and_closes_the_health(self):
        from dashboard_support import RunLog
        before = dashboard_data.workflow_data(self.run, now=self.now)
        log = RunLog(self.run)
        log.finish(60, "01.build/01.worker", 1, "passed", wall=58.0,
                   fingerprint="fp-live")
        after = dashboard_data.workflow_data(self.run, now=self.now)
        a, b = before["invocations"][0], after["invocations"][0]
        self.assertEqual(a["id"], b["id"])
        self.assertEqual(b["status"], "passed")
        self.assertIsNone(b["health"])
        self.assertIsNone(b["activity"])
        self.assertEqual(b["wall_s"], 58.0)

    def test_the_fixture_serves_over_http(self):
        handle = dashboard.start(self.run)
        self.addCleanup(handle.stop)
        status, body = get(handle.url.rstrip("/") + "/api/workflow")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(payload["schema"], "ohflow.dashboard/1")
        self.assertEqual(payload["run"]["mode"], "live")
        self.assertEqual(payload["invocations"][0]["status"], "running")
        status, body = get(handle.url.rstrip("/")
                           + "/api/transcript?coord=01.build/01.worker"
                             "&attempt=1")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["schema"], "ohflow.transcript/1")


class UnreadableLog(TempCase):

    def test_a_corrupt_middle_line_is_counted_not_repaired(self):
        from dashboard_support import RunLog, workflow_json
        run = self.tmp / "torn"
        workflow_json(run, [("Alpha", [agent("only")], 1)])
        log = RunLog(run)
        log.phase(1, "01.alpha", "Alpha", ["01.alpha/01.only"], 1)
        with (run / "run-log.jsonl").open("a", encoding="utf-8") as fh:
            fh.write('{"ts": "x", "event": "attempt_started", CORRUPT\n')
        log.start(2, "01.alpha/01.only", 1)
        payload = dashboard_data.workflow_data(run, now=T0 + 100)
        joined = "\n".join(payload["diagnostics"])
        self.assertIn("unreadable line", joined)
        self.assertEqual(len(payload["invocations"]), 1)


if __name__ == "__main__":
    import unittest
    unittest.main()

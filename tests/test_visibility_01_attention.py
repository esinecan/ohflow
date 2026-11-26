"""`/api/workflow` carries an attention strip: one item per condition that
needs a person, is recovering by itself, or is a signal worth a look.

Each item is derived from the run log and the attempt files alone, grouped by
its consequence (`intervention`, `recovering`, `signal`), and names what was
observed, what was expected, what it affects, the next command the engine
permits, and the run-log line that is its evidence. A healthy finished run
has none; a packet, which is historical evidence, has none either.
"""

from __future__ import annotations

import json
from pathlib import Path

from dashboard_support import (T0, RunLog, agent, command, mark_alive, stamp,
                               workflow_json)
from support import TempCase
from test_dashboard_07_data import live_run

from ohflow import dashboard_data, live

HERE = Path(__file__).resolve().parent
PACKET = HERE / "fixtures" / "dashboard-basis"
A, B, C = "01.alpha/01.a", "01.alpha/02.b", "01.alpha/03.c"
LATER = "02.beta/01.later"


def two_phases(run: Path, *, auto_resume: int = 0) -> None:
    a, b, c = agent("a", retry_max=1), agent("b"), agent("c")
    c["depends_on"] = ["a"]
    workflow_json(run, [("Alpha", [a, b, c], 2), ("Beta", [command("later")], 1)],
                  auto_resume=auto_resume)


def attention(run: Path, now: float = T0 + 100) -> list[dict]:
    return dashboard_data.workflow_data(run, now=now)["attention"]


def groups(items: list[dict]) -> list[str]:
    return [item["group"] for item in items]


class NothingToSay(TempCase):

    def test_a_healthy_finished_run_has_no_attention_item(self):
        run = self.run_dir("r-quiet")
        two_phases(run)
        (RunLog(run).phase(1, "01.alpha", "Alpha", [A, B, C])
         .start(2, A).finish(12, A, 1, "passed")
         .start(2, B).finish(13, B, 1, "passed")
         .start(13, C).finish(20, C, 1, "passed")
         .settle(21, "01.alpha", "passed", 3, 3)
         .phase(22, "02.beta", "Beta", [LATER], 1)
         .start(22, LATER).finish(23, LATER, 1, "passed")
         .settle(24, "02.beta", "passed", 1, 1)
         .run_finished(25, "finished"))
        self.assertEqual(attention(run), [])

    def test_a_packet_is_evidence_and_has_no_attention(self):
        payload = dashboard_data.workflow_data(PACKET, now=T0)
        self.assertEqual(payload["attention"], [])

    def test_a_directory_that_is_no_run_still_answers_the_field(self):
        payload = dashboard_data.workflow_data(self.tmp / "nothing", now=T0)
        self.assertEqual(payload["attention"], [])
        self.assertEqual(payload["digest"], [])


class Intervention(TempCase):

    def test_a_failed_step_with_no_eligible_retry_names_cause_impact_and_evidence(self):
        run = self.run_dir("r-failed")
        two_phases(run)
        (RunLog(run).phase(1, "01.alpha", "Alpha", [A, B, C])
         .start(2, A)
         .finish(12, A, 1, "quarantined", error="tests red",
                 gate={"passed": False, "checks": [
                     {"name": "command_exit", "passed": False}]})
         .add(12, "retry_decided", A, 1,
              retry_decision="retry budget spent: 1 of 1 retries used for this work")
         .start(2, B))
        mark_alive(run)
        items = attention(run)
        self.assertEqual(groups(items), ["intervention"])
        item = items[0]
        self.assertEqual(item["kind"], "failed_step")
        self.assertEqual(item["coord"], A)
        self.assertEqual(item["attempt"], 1)
        self.assertIn("quarantined", item["observed"]["text"])
        self.assertIn("command_exit", item["observed"]["text"])
        self.assertEqual(item["observed"]["ts"], stamp(12))
        self.assertIn("gate", item["expected"])
        # The declared dependant is named, and the phase it sits in.
        self.assertEqual(item["impact"]["phase"], "01.alpha")
        self.assertEqual(item["impact"]["dependants"], [C])
        self.assertEqual(item["impact"]["text"], "phase 1 Alpha; dependants: c")
        # The engine permits no further start: the decision it recorded says why.
        self.assertIsNone(item["next"]["command"])
        self.assertIn("retry budget spent", item["next"]["text"])
        # The evidence is the run-log line of the verdict, linked to the attempt.
        self.assertEqual(item["evidence"]["id"], f"{A}@1")
        self.assertEqual(item["evidence"]["event"], "attempt_finished")
        self.assertEqual(item["evidence"]["line"], 4)

    def test_a_paused_run_names_the_resume_command(self):
        run = self.run_dir("r-paused")
        two_phases(run)
        (RunLog(run).phase(1, "01.alpha", "Alpha", [A, B, C])
         .start(2, A)
         .finish(5, A, 1, "deferred", error="429: rate limit",
                 failure_class="transient")
         .settle(6, "01.alpha", "deferred", 0, 3)
         .run_finished(7, "paused"))
        (run / "run.json").write_text(json.dumps({
            "run_id": "r-paused", "workflow_path": "C:/workflows/p.py",
            "workflow_args": {"repo": "C:/work/repo"}}), encoding="utf-8")
        items = attention(run)
        paused = next(i for i in items if i["kind"] == "paused_run")
        self.assertEqual(paused["group"], "intervention")
        self.assertEqual(paused["next"]["command"], live.resume_command(run))
        self.assertIn("--resume r-paused", paused["next"]["command"])
        self.assertIn("deferred", paused["impact"]["text"])
        self.assertEqual(paused["evidence"]["event"], "run_finished")
        # The deferred step waits for that resume and is not a second alarm:
        # one item per condition, and the run-level item owns the command.
        self.assertEqual(groups(items), ["intervention"])

    def test_a_killed_step_waits_for_a_person_and_no_auto_resume(self):
        run = self.run_dir("r-killed")
        two_phases(run, auto_resume=1)
        killed = {"reason": "it reruns the full suite",
                  "requested_at": "2026-11-24T10:00:00Z"}
        (RunLog(run, auto_resume=1).phase(1, "01.alpha", "Alpha", [A, B, C])
         .start(2, A)
         .finish(5, A, 1, "deferred", abort_victim=True, killed=killed,
                 error="killed by ohflow kill: it reruns the full suite"))
        mark_alive(run)
        items = attention(run)
        self.assertEqual([i["kind"] for i in items], ["killed_step"])
        self.assertEqual(items[0]["group"], "intervention")
        self.assertIn("run --resume", items[0]["next"]["text"])
        a = next(s for s in live.read_out(run, T0 + 100)["agents"]
                 if s["coord"] == A)
        self.assertEqual(a["display"]["state"], "done")

    def test_a_run_paused_on_a_kill_names_the_kill(self):
        run = self.run_dir("r-killed-paused")
        two_phases(run)
        (RunLog(run).phase(1, "01.alpha", "Alpha", [A, B, C])
         .start(2, A)
         .finish(5, A, 1, "deferred", abort_victim=True,
                 killed={"reason": None, "requested_at": None},
                 error="killed by ohflow kill")
         .settle(6, "01.alpha", "deferred", 0, 3)
         .run_finished(7, "paused"))
        paused = next(i for i in attention(run) if i["kind"] == "paused_run")
        self.assertEqual(paused["observed"]["text"],
                         "the run paused: ohflow kill ended a")

    def test_an_orphaned_run_names_the_interrupted_attempt(self):
        run = self.run_dir("r-orphan")
        two_phases(run)
        (RunLog(run).phase(1, "01.alpha", "Alpha", [A, B, C]).start(2, A))
        (run / "supervisor.pid").write_text("2147483646", encoding="utf-8")
        (run / "run.json").write_text(json.dumps({
            "run_id": "r-orphan", "workflow_path": "C:/workflows/p.py"}),
            encoding="utf-8")
        items = attention(run)
        self.assertEqual(groups(items), ["intervention"])
        item = items[0]
        self.assertEqual(item["kind"], "orphaned_run")
        self.assertIn("supervisor", item["observed"]["text"])
        self.assertIn(f"{A}@1", item["impact"]["text"])
        self.assertIn("--resume r-orphan", item["next"]["command"])

    def test_excluded_work_is_an_intervention_with_no_next_start(self):
        run = self.run_dir("r-excluded")
        two_phases(run)
        (RunLog(run).phase(1, "01.alpha", "Alpha", [A, B, C])
         .start(2, A).finish(5, A, 1, "failed", error="boom")
         .add(5, "retry_decided", A, 1,
              retry_decision="retry start, execution 2 of 3, attempt 2")
         .start(6, A, 2, "retry").finish(9, A, 2, "quarantined", error="boom")
         .add(9, "work_excluded", A, payload={
             "coord": A, "fingerprint": "fp",
             "reason": "excluded: 2 failed executions of unchanged work "
                       "(2 judged, 0 transient, work fp)"})
         .start(2, B))
        mark_alive(run)
        items = attention(run)
        kinds = [i["kind"] for i in items]
        self.assertIn("excluded", kinds)
        self.assertIn("failed_step", kinds)
        excluded = next(i for i in items if i["kind"] == "excluded")
        self.assertEqual(excluded["group"], "intervention")
        self.assertIsNone(excluded["next"]["command"])
        self.assertIn("excluded", excluded["next"]["text"])
        self.assertEqual(excluded["evidence"]["event"], "work_excluded")
        self.assertEqual(excluded["evidence"]["id"], f"{A}@2")


class Recovering(TempCase):

    def test_a_deferred_step_under_cooldown_recovers_by_itself(self):
        run = self.run_dir("r-cooldown")
        two_phases(run, auto_resume=1)
        (RunLog(run, auto_resume=1).phase(1, "01.alpha", "Alpha", [A, B, C])
         .start(2, A)
         .finish(5, A, 1, "deferred", error="429: rate limit",
                 failure_class="transient", cooldown_until=stamp(160),
                 transient_signature="429"))
        mark_alive(run)
        items = attention(run)
        self.assertEqual(groups(items), ["recovering"])
        item = items[0]
        self.assertEqual(item["kind"], "deferred_cooldown")
        self.assertIn("429", item["observed"]["text"])
        self.assertIsNone(item["next"]["command"])
        self.assertIn("auto-resume", item["next"]["text"])
        self.assertIn("cooldown", item["next"]["text"])

    def test_a_deferred_step_with_an_auto_resume_pass_left_recovers(self):
        run = self.run_dir("r-auto")
        two_phases(run, auto_resume=1)
        (RunLog(run, auto_resume=1).phase(1, "01.alpha", "Alpha", [A, B, C])
         .start(2, A)
         .finish(5, A, 1, "deferred", error="429: rate limit",
                 failure_class="transient"))
        mark_alive(run)
        items = attention(run)
        self.assertEqual([i["kind"] for i in items], ["deferred_auto_resume"])
        self.assertEqual(items[0]["group"], "recovering")

    def test_a_deferred_step_with_the_budget_spent_needs_a_person(self):
        run = self.run_dir("r-spent")
        two_phases(run, auto_resume=0)
        (RunLog(run, auto_resume=0).phase(1, "01.alpha", "Alpha", [A, B, C])
         .start(2, A)
         .finish(5, A, 1, "deferred", error="429: rate limit",
                 failure_class="transient"))
        mark_alive(run)
        items = attention(run)
        self.assertEqual([i["kind"] for i in items], ["budget_spent"])
        self.assertEqual(items[0]["group"], "intervention")
        self.assertIn("auto-resume budget spent", items[0]["next"]["text"])

    def test_a_retry_under_way_is_recovering_not_an_alarm(self):
        run = self.run_dir("r-retrying")
        two_phases(run)
        (RunLog(run).phase(1, "01.alpha", "Alpha", [A, B, C])
         .start(2, A)
         .finish(12, A, 1, "failed", gate={"passed": False, "checks": [
             {"name": "command_exit", "passed": False}]})
         .add(12, "retry_decided", A, 1,
              retry_decision="retry start, execution 2 of 3, attempt 2")
         .start(13, A, 2, "retry"))
        mark_alive(run)
        items = attention(run, now=T0 + 20)
        self.assertEqual(groups(items), ["recovering"])
        item = items[0]
        self.assertEqual(item["kind"], "retry_running")
        self.assertEqual(item["attempt"], 2)
        self.assertIn("command_exit", item["observed"]["text"])
        self.assertIn("retry start", item["next"]["text"])
        self.assertEqual(item["evidence"]["event"], "retry_decided")


class Signal(TempCase):

    def test_a_red_idle_signal_is_a_threshold_not_a_verdict(self):
        run = live_run(self.tmp / "live-run")
        # 1997 s past the worker's last record: red idle, and past three
        # quarters of its 900 s execution timeout as well.
        items = attention(run, now=T0 + 2000)
        self.assertEqual(groups(items), ["signal", "signal"])
        self.assertEqual([i["kind"] for i in items], ["idle_red", "deadline"])
        item = items[0]
        self.assertEqual(item["coord"], "01.build/01.worker")
        self.assertIn("threshold", item["observed"]["text"])
        self.assertIn("not a proven stall", item["observed"]["text"])
        self.assertIsNone(item["next"]["command"])
        self.assertEqual(item["evidence"]["id"], "01.build/01.worker@1")

    def test_an_amber_idle_signal_is_named_amber(self):
        run = live_run(self.tmp / "live-run")
        # 400 s after the worker's last record: past amber (300), short of red.
        items = attention(run, now=T0 + 403)
        self.assertEqual([i["kind"] for i in items], ["idle_amber"])

    def test_a_running_attempt_near_its_execution_deadline_is_flagged(self):
        run = self.run_dir("r-deadline")
        workflow_json(run, [("Alpha", [agent("a", execution_timeout_s=100,
                                             stall_timeout_s=100_000)], 1)])
        RunLog(run).phase(1, "01.alpha", "Alpha", [A]).start(2, A)
        mark_alive(run)
        items = attention(run, now=T0 + 90)
        self.assertEqual([i["kind"] for i in items], ["deadline"])
        self.assertIn("execution timeout", items[0]["observed"]["text"])
        self.assertEqual(attention(run, now=T0 + 30), [])


class ChecksOverAgent(TempCase):

    def items(self, check_s: float, agent_s: float, *,
              cached: bool = False) -> list[dict]:
        run = self.run_dir("r-price")
        workflow_json(run, [("Alpha", [agent("a")], 1)])
        gate = {"passed": True, "checks": [
            {"name": "command_exit", "passed": True, "duration_s": check_s}]}
        log = (RunLog(run).phase(1, "01.alpha", "Alpha", [A]).start(2, A)
               .finish(12, A, 1, "passed", wall=agent_s + check_s, gate=gate))
        if cached:
            log.finish(13, A, 0, "cached", wall=0.0, gate=gate)
        log.settle(14, "01.alpha", "passed", 1, 1).run_finished(15, "finished")
        return [i for i in attention(run) if i["kind"] == "checks_over_agent"]

    def test_checks_longer_than_the_agent_raise_one_signal(self):
        (item,) = self.items(600.0, 300.0)
        self.assertEqual((item["group"], item["coord"]), ("signal", A))
        self.assertEqual(item["observed"]["text"],
                         "its checks ran 10 m, its agent 5 m")

    def test_checks_shorter_than_the_agent_raise_none(self):
        self.assertEqual(self.items(100.0, 300.0), [])

    def test_a_cached_step_raises_none(self):
        self.assertEqual(self.items(100.0, 300.0, cached=True), [])


class Ordering(TempCase):

    def test_groups_come_in_consequence_order(self):
        run = self.run_dir("r-mixed")
        a, b = agent("a", retry_max=1), agent("b")
        c = agent("c", execution_timeout_s=100, stall_timeout_s=100_000)
        workflow_json(run, [("Alpha", [a, b, c], 3)], auto_resume=1)
        (RunLog(run, auto_resume=1).phase(1, "01.alpha", "Alpha", [A, B, C], 3)
         .start(2, B).finish(5, B, 1, "deferred", error="429",
                             failure_class="transient")
         .start(2, A).finish(12, A, 1, "quarantined", error="tests red")
         .add(12, "retry_decided", A, 1,
              retry_decision="retry budget spent: 1 of 1 retries used")
         .start(13, C))
        mark_alive(run)
        items = attention(run, now=T0 + 100)
        self.assertEqual(groups(items), ["intervention", "recovering", "signal"])
        self.assertEqual([i["kind"] for i in items],
                         ["failed_step", "deferred_auto_resume", "deadline"])


if __name__ == "__main__":
    import unittest
    unittest.main()

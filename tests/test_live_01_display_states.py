"""Dashboard S1, test 1: one test per display state of spec §6.

Each test writes the run log a moment of a real run leaves behind, then asks
`live.read_out` what a watcher sees at a fixed `now`. The rules apply in the
order the spec lists them, so each test also pins that its state wins over the
ones after it.
"""

from __future__ import annotations

import json
import subprocess
import sys

from dashboard_support import (T0, RunLog, command, mark_alive, workflow_json,
                               stamp, agent)
from ohflow import activity as activity_mod, live
from ohflow.paths import python_cmd
from support import TempCase

NOW = T0 + 100


def _agent(read_out: dict, coord: str) -> dict:
    return next(a for a in read_out["agents"] if a["coord"] == coord)


class DisplayStates(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.run = self.run_dir("r-display")

    def two_phases(self, max_parallel: int = 2, auto_resume: int = 0) -> None:
        workflow_json(self.run, [
            ("Map", [agent("a"), agent("b")], max_parallel),
            ("Merge", [command("c")], 1),
        ], auto_resume=auto_resume)

    def test_waiting_for_its_phase(self):
        self.two_phases()
        RunLog(self.run).phase(1, "01.map", "Map",
                               ["01.map/01.a", "01.map/02.b"])
        mark_alive(self.run)
        read_out = live.read_out(self.run, NOW)
        c = _agent(read_out, "02.merge/01.c")
        self.assertEqual(c["display"]["state"], "waiting")
        self.assertEqual(c["display"]["reason"], "waits for phase 2")
        self.assertEqual(read_out["phases"][1]["state"], "waiting")
        self.assertEqual(read_out["run"]["status"], "running")

    def test_waiting_for_the_provider_cooldown(self):
        self.two_phases()
        wake = stamp(160)
        (RunLog(self.run)
         .phase(1, "01.map", "Map", ["01.map/01.a", "01.map/02.b"])
         .start(2, "01.map/01.a")
         .finish(5, "01.map/01.a", 1, "deferred", error="429: rate limit",
                 failure_class="transient", cooldown_until=wake,
                 transient_signature="429"))
        mark_alive(self.run)
        read_out = live.read_out(self.run, NOW)
        b = _agent(read_out, "01.map/02.b")
        self.assertEqual(b["display"]["state"], "waiting")
        self.assertEqual(b["display"]["why"], "cooldown")
        self.assertEqual(b["display"]["reason"],
                         "waits for provider cooldown until "
                         + activity_mod.hms(T0 + 160))
        self.assertEqual(read_out["run"]["cooldown_until"], wake)

    def test_a_cooldown_in_the_past_is_a_slot_wait(self):
        self.two_phases()
        (RunLog(self.run)
         .phase(1, "01.map", "Map", ["01.map/01.a", "01.map/02.b"])
         .start(2, "01.map/01.a")
         .finish(5, "01.map/01.a", 1, "deferred", error="429",
                 failure_class="transient", cooldown_until=stamp(50)))
        mark_alive(self.run)
        b = _agent(live.read_out(self.run, NOW), "01.map/02.b")
        self.assertEqual(b["display"]["why"], "slot")

    def test_waiting_for_a_free_slot(self):
        self.two_phases(max_parallel=1)
        (RunLog(self.run)
         .phase(1, "01.map", "Map", ["01.map/01.a", "01.map/02.b"],
                max_parallel=1)
         .start(2, "01.map/01.a"))
        mark_alive(self.run)
        read_out = live.read_out(self.run, NOW)
        b = _agent(read_out, "01.map/02.b")
        self.assertEqual(b["display"]["state"], "waiting")
        self.assertEqual(b["display"]["reason"],
                         "waits for a free slot (1 of 1 busy)")
        self.assertEqual(read_out["run"]["counts"]["waiting_by"],
                         {"slot": 1, "phase": 1})
        self.assertEqual(read_out["run"]["counts"]["waiting_text"],
                         "1 for a free slot, 1 for its phase")

    def test_the_waiting_breakdown_is_worded(self):
        self.assertEqual(live.waiting_words({"phase": 10}),
                         "10 for their phase")
        self.assertEqual(live.waiting_words({"phase": 4, "slot": 1}),
                         "1 for a free slot, 4 for their phase")
        self.assertEqual(
            live.waiting_words({"cooldown": 2, "auto_resume": 1, "resume": 3}),
            "2 for the provider cooldown, 1 for an auto-resume pass, "
            "3 for a resume")
        self.assertEqual(live.waiting_words({}), "")

    def test_running_a_restarted_attempt(self):
        self.two_phases()
        (RunLog(self.run)
         .phase(1, "01.map", "Map", ["01.map/01.a", "01.map/02.b"])
         .start(2, "01.map/01.a")
         .finish(20, "01.map/01.a", 1, "failed",
                 gate={"passed": False, "checks": [
                     {"name": "command_exit", "passed": False}]})
         .add(20, "retry_decided", "01.map/01.a", 1,
              retry_decision="retry 1 of 1 on gate:command_exit")
         .start(21, "01.map/01.a", attempt=2, kind="retry"))
        mark_alive(self.run)
        read_out = live.read_out(self.run, NOW)
        a = _agent(read_out, "01.map/01.a")
        self.assertEqual(a["display"]["state"], "running")
        self.assertEqual(a["display"]["reason"], "attempt 2, retry")
        self.assertTrue(a["display"]["restarted"])
        self.assertEqual(a["attempt"], 2)
        self.assertEqual(a["start_kind"], "retry")
        first = a["attempts"][0]
        self.assertEqual(first["cause"], "gate command_exit failed")
        self.assertEqual(first["retry_decision"],
                         "retry 1 of 1 on gate:command_exit")
        self.assertEqual(a["lineage"],
                         "01 failed (gate command_exit) \u2192 02 retry running")
        self.assertEqual(read_out["run"]["counts"]["restarted"], 1)
        self.assertEqual(read_out["run"]["counts"]["running"], 1)

    def test_deferred_and_waiting_for_an_auto_resume_pass(self):
        self.two_phases(auto_resume=1)
        (RunLog(self.run, auto_resume=1)
         .phase(1, "01.map", "Map", ["01.map/01.a", "01.map/02.b"])
         .start(2, "01.map/01.a")
         .finish(5, "01.map/01.a", 1, "deferred",
                 error="429: Rate limit reached\nsecond line",
                 failure_class="transient"))
        mark_alive(self.run)
        a = _agent(live.read_out(self.run, NOW), "01.map/01.a")
        self.assertEqual(a["display"]["state"], "waiting")
        self.assertEqual(a["display"]["why"], "auto_resume")
        self.assertEqual(a["display"]["reason"],
                         "deferred: 429: Rate limit reached; an "
                         "auto-resume pass reruns it")

    def test_deferred_with_the_auto_resume_budget_spent_is_done(self):
        self.two_phases(auto_resume=0)
        (RunLog(self.run, auto_resume=0)
         .phase(1, "01.map", "Map", ["01.map/01.a", "01.map/02.b"])
         .start(2, "01.map/01.a")
         .finish(5, "01.map/01.a", 1, "deferred", error="429",
                 failure_class="transient"))
        mark_alive(self.run)
        a = _agent(live.read_out(self.run, NOW), "01.map/01.a")
        self.assertEqual(a["display"]["state"], "done")
        self.assertEqual(a["display"]["label"], "DEFERRED")

    def test_deferred_in_a_paused_run_names_the_resume_command(self):
        self.two_phases()
        (RunLog(self.run)
         .phase(1, "01.map", "Map", ["01.map/01.a", "01.map/02.b"])
         .start(2, "01.map/01.a")
         .finish(5, "01.map/01.a", 1, "deferred", error="429",
                 failure_class="transient")
         .run_finished(6, "paused"))
        (self.run / "run.json").write_text(json.dumps({
            "run_id": "r-display", "workflow_path": "C:/workflows/p.py",
            "workflow_args": {"repo": "C:/work/repo"}}), encoding="utf-8")
        read_out = live.read_out(self.run, NOW)
        a = _agent(read_out, "01.map/01.a")
        self.assertEqual(a["display"]["state"], "waiting")
        self.assertEqual(a["display"]["why"], "resume")
        out = live._quote(str(self.run.resolve().parent))
        expected = (f"{python_cmd()} -m ohflow.cli run --workflow C:/workflows/p.py --out "
                    f"{out} --resume r-display --args repo=C:/work/repo")
        self.assertEqual(read_out["run"]["resume_command"], expected)
        self.assertEqual(a["display"]["reason"], f"paused: run `{expected}`")
        self.assertEqual(read_out["run"]["status"], "paused")

    def test_done_states_cached_counts_as_passed_and_excluded_is_named(self):
        workflow_json(self.run, [("Map", [agent("a"), agent("b")], 2)])
        (RunLog(self.run)
         .phase(1, "01.map", "Map", ["01.map/01.a", "01.map/02.b"])
         .finish(1, "01.map/01.a", 0, "cached")
         .start(2, "01.map/02.b")
         .finish(9, "01.map/02.b", 1, "quarantined", error="gate failed")
         .add(9, "work_excluded", "01.map/02.b", payload={
             "coord": "01.map/02.b", "fingerprint": "fp",
             "reason": "excluded: 2 failed executions"})
         .settle(10, "01.map", "failed", 1, 2)
         .run_finished(11, "finished"))
        read_out = live.read_out(self.run, NOW)
        a, b = _agent(read_out, "01.map/01.a"), _agent(read_out, "01.map/02.b")
        self.assertEqual(a["display"]["state"], "done")
        self.assertEqual(a["display"]["label"], "PASSED")
        self.assertEqual(b["display"]["state"], "done")
        self.assertIn("excluded", b["display"]["reason"])
        self.assertIn("EXCLUDED", b["display"]["label"])
        self.assertEqual(read_out["phases"][0]["state"], "failed")
        self.assertEqual(read_out["phases"][0]["good"], 1)
        self.assertEqual(read_out["run"]["counts"]["done"], 2)


class RunLevelStates(TempCase):

    def test_a_running_run_log_with_no_live_supervisor_is_orphaned(self):
        run = self.run_dir("r-orphan")
        workflow_json(run, [("Map", [agent("a")], 1)])
        (RunLog(run).phase(1, "01.map", "Map", ["01.map/01.a"])
         .start(2, "01.map/01.a"))
        (run / "supervisor.pid").write_text("2147483646", encoding="utf-8")
        read_out = live.read_out(run, NOW)
        self.assertEqual(read_out["run"]["status"], "orphaned")
        self.assertFalse(read_out["run"]["supervisor_alive"])
        a = read_out["agents"][0]
        self.assertEqual(a["display"]["label"], "INTERRUPTED")
        self.assertEqual(a["attempts"][0]["status"], "interrupted")

    def test_no_run_log_yet_is_starting_while_the_supervisor_lives(self):
        run = self.run_dir("r-new")
        workflow_json(run, [("Map", [agent("a")], 1)])
        mark_alive(run)
        read_out = live.read_out(run, NOW)
        self.assertEqual(read_out["run"]["status"], "starting")
        self.assertEqual(read_out["agents"][0]["display"]["reason"],
                         "waits for phase 1")

    def test_no_run_log_is_named_from_its_owner_file_and_its_exit_file(self):
        """An attached run writes `.ohflow-owner.json` before `workflow.json` and
        `supervisor.pid` only with its first run log line. The reader names
        the run from the owner in between, and from `exit.json` once the
        engine has crashed."""
        run = self.run_dir("r-owner")
        workflow_json(run, [("Map", [agent("a")], 1)])
        owner = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.addCleanup(owner.wait)
        self.addCleanup(owner.kill)
        (run / ".ohflow-owner.json").write_text(
            json.dumps({"run_id": "r-owner", "pid": owner.pid}),
            encoding="utf-8")
        read_out = live.read_out(run, NOW)
        self.assertEqual(read_out["run"]["status"], "starting")
        self.assertTrue(read_out["run"]["supervisor_alive"])

        owner.kill()
        owner.wait()
        read_out = live.read_out(run, NOW)
        self.assertEqual(read_out["run"]["status"], "not started")

        (run / "run.json").write_text(
            json.dumps({"run_id": "r-owner", "workflow_path": "p.py"}),
            encoding="utf-8")
        (run / "exit.json").write_text(
            json.dumps({"status": "crashed", "error": "PreflightError: x"}),
            encoding="utf-8")
        read_out = live.read_out(run, NOW)
        self.assertEqual(read_out["run"]["status"], "crashed")
        self.assertIsNone(read_out["run"]["resume_command"],
                          "--resume refuses a run with no run log")

    def test_the_eta_is_unknown_until_an_agent_finishes_then_adds_phases(self):
        run = self.run_dir("r-eta")
        workflow_json(run, [("Map", [agent("a"), agent("b"), agent("c")], 1),
                            ("Fix", [agent("d"), agent("e")], 2)])
        j = (RunLog(run).phase(1, "01.map", "Map",
                               ["01.map/01.a", "01.map/02.b", "01.map/03.c"],
                               max_parallel=1)
             .start(2, "01.map/01.a"))
        mark_alive(run)
        read_out = live.read_out(run, NOW)
        self.assertIsNone(read_out["run"]["eta_s"])
        self.assertIn("unknown", read_out["run"]["eta_basis"])
        j.finish(62, "01.map/01.a", 1, "passed", wall=60.0)
        j.start(63, "01.map/02.b")
        read_out = live.read_out(run, T0 + 83)
        # Current phase: 1 waiting at max 1 is 60 s, plus 60 - 20 left on b.
        # Later phase: 2 steps at max 2 is one wave of 60 s.
        self.assertEqual(read_out["run"]["eta_s"], 60 + 40 + 60)
        self.assertEqual(read_out["run"]["eta_basis"],
                         "median 60 s over 1 finished agent step(s)")

"""m7: a resumed run is running, not finished.

A resume appends no run-level event. The run log reads `run_started`,
`run_finished`, then `phase_started` and `attempt_started`. The replay set the
status only on `run_finished`, so `status`, `watch` and the dashboard read-out
kept the old verdict while an agent ran. `watch` also read the `exit.json` of
the earlier finish as the end of the current run, and printed the old verdict
with exit code 1.

The run log now says what a run is: any work event after a `run_finished`
reopens the run, and an `exit.json` older than the run log is not a verdict.
"""

from __future__ import annotations

import os
import json
import time

from dashboard_support import RunLog, mark_alive, workflow_json, agent
from ohflow import live, watch
from support import TempCase
from verb_support import call

STEPS = ["01.map/01.a"]
DEAD_PID = "2147483646"
OLD_VERDICT = "Run r-resumed finished: 1 of 1 agents passed"


class AResumedRun(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.dir = self.run_dir("r-resumed")
        workflow_json(self.dir, [("Map", [agent("a")], 1)])
        self.run_log = (RunLog(self.dir)
                        .phase(1, "01.map", "Map", STEPS)
                        .start(2, STEPS[0])
                        .finish(30, STEPS[0], 1, "failed")
                        .settle(31, "01.map", "failed", 0, 1)
                        .run_finished(32, "failed"))
        self.exit_json = self.dir / "exit.json"
        self.exit_json.write_text(json.dumps({
            "status": "failed", "verdict": OLD_VERDICT, "error": None,
            "traceback_tail": []}), encoding="utf-8")
        self.resume()

    def resume(self) -> None:
        """The engine's resume: a second phase_started and a new attempt."""
        (self.run_log.phase(100, "01.map", "Map", STEPS)
         .start(101, STEPS[0], attempt=2, kind="retry"))
        past = time.time() - 100
        os.utime(self.exit_json, (past, past))

    def test_status_names_a_resumed_run_running(self):
        mark_alive(self.dir)
        code, lines = call("status", "--run", self.dir)
        self.assertRegex(lines[0], r"^running: ", lines)

    def test_read_out_names_a_resumed_run_running(self):
        mark_alive(self.dir)
        read_out = live.read_out(self.dir)
        self.assertEqual(read_out["run"]["status"], "running")
        self.assertIsNone(read_out["run"].get("finished"),
                          "a running run has no finish time")

    def test_watch_keeps_a_resumed_run_going_and_prints_no_old_verdict(self):
        mark_alive(self.dir)
        code, lines = call("watch", "--run", self.dir, "--timeout", 0)
        self.assertEqual(code, watch.EXIT_GOING, lines)
        self.assertRegex(lines[0], r"^running: ")
        self.assertNotIn(OLD_VERDICT, "\n".join(lines))

    def test_watch_does_not_read_an_older_exit_json_as_the_verdict(self):
        (self.dir / "supervisor.pid").write_text(DEAD_PID, encoding="utf-8")
        code, lines = call("watch", "--run", self.dir, "--timeout", 0)
        self.assertEqual(code, watch.EXIT_ENDED_BAD, lines)
        self.assertRegex(lines[0], r"^orphaned: ")
        self.assertNotIn(OLD_VERDICT, "\n".join(lines))

    def test_a_resumed_run_that_finishes_again_is_finished(self):
        mark_alive(self.dir)
        (self.run_log.finish(130, STEPS[0], 2, "passed")
         .settle(131, "01.map", "passed", 1, 1)
         .run_finished(132, "finished"))
        code, lines = call("status", "--run", self.dir)
        self.assertRegex(lines[0], r"^finished: ", lines)

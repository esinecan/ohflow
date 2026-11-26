"""A held run reads `held` everywhere a run is described.

A run directory with `workflow.json`, `.ohflow-hold` naming a live supervisor
and no run log is a held run. The run reader names it `held`, the dashboard
serves it in live mode with every step waiting on the hold, the read-out
agrees, and `watch` returns 10 with one line naming the go command.
"""

from __future__ import annotations

import json
import os

from dashboard_support import workflow_json, agent, T0
from ohflow import dashboard_data, live, rundir, runstatus, watch
from support import TempCase
from verb_support import call

STEPS = ["01.map/01.a", "01.map/02.b", "02.merge/01.c"]
HELD_REASON = "held: waiting for go"


class StatusHeld(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.dir = self.run_dir("r-held")
        workflow_json(self.dir, [("Map", [agent("a"), agent("b")], 2),
                                 ("Merge", [agent("c")], 1)])
        (self.dir / rundir.HOLD_FILE).write_text(
            json.dumps({"pid": os.getpid(), "since": "2026-10-09T12:00:00Z"}),
            encoding="utf-8")

    def test_the_run_reader_names_it_held(self):
        run = rundir.open_run(self.dir)
        self.assertEqual(run.status_without_run_log, rundir.HELD)
        self.assertTrue(run.held)
        self.assertIn(rundir.HELD, runstatus.LIVE_STATUSES)

    def test_a_dead_hold_is_not_held(self):
        (self.dir / rundir.HOLD_FILE).write_text(
            json.dumps({"pid": 2147483646, "since": "2026-10-09T12:00:00Z"}),
            encoding="utf-8")
        run = rundir.open_run(self.dir)
        self.assertFalse(run.held)
        self.assertEqual(run.status_without_run_log, rundir.NOT_STARTED)

    def test_the_workflow_api_serves_it_live_with_every_step_held(self):
        payload = dashboard_data.workflow_data(self.dir, now=T0 + 5)
        self.assertEqual(payload["run"]["status"], rundir.HELD)
        self.assertEqual(payload["run"]["mode"], "live")
        self.assertEqual([s["coord"] for s in payload["steps"]], STEPS)
        for step in payload["steps"]:
            self.assertEqual(step["display"], "waiting", step)
            self.assertEqual(step["waiting_on"], "hold", step)
            self.assertEqual(step["reason"], HELD_REASON, step)
        self.assertEqual(payload["invocations"], [])

    def test_the_read_out_agrees(self):
        read_out = live.read_out(self.dir, now=T0 + 5)
        self.assertEqual(read_out["run"]["status"], rundir.HELD)
        for card in read_out["agents"]:
            self.assertEqual(card["display"]["state"], "waiting")
            self.assertEqual(card["display"]["why"], "hold")
            self.assertEqual(card["display"]["reason"], HELD_REASON)

    def test_watch_returns_10_and_names_the_go_command(self):
        code, lines = call("watch", "--run", self.dir, "--timeout", 0)
        self.assertEqual(code, watch.EXIT_GOING)
        self.assertRegex(lines[0], r"^held: 0 of 3 steps passed")
        held = [line for line in lines if line.startswith("held:")
                and "-m ohflow.cli go --run" in line]
        self.assertEqual(len(held), 1, lines)

    def test_status_says_held(self):
        code, lines = call("status", "--run", self.dir)
        self.assertEqual(code, 0)
        self.assertRegex(lines[0], r"^held: 0 of 3 steps passed")


if __name__ == "__main__":
    import unittest
    unittest.main()

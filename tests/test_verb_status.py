"""m4: `ohflow status` prints one status sentence, then what needs a person.

Before: `status` printed a JSON dict, and an agent parsed it to learn whether a
run was done. Now line one is `<status>: P of T steps passed, R running, F
failed, Q pending · <elapsed>`. An unknown run directory exits 2.
"""

from __future__ import annotations

import json
import re

from dashboard_support import (G1_RUN, RunLog, copy_tree, mark_alive,
                               workflow_json, agent)
from ohflow import dashboard
from support import TempCase
from verb_support import NO_ANSI, call, live_child

SENTENCE = (r"^{status}: \d+ of \d+ steps passed, \d+ running, \d+ failed, "
            r"\d+ pending")


class StatusOfAFinishedRun(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.dir = copy_tree(G1_RUN, self.tmp / "runs" / "g1")

    def test_status_first_line_is_the_sentence_and_the_run_is_short(self):
        code, lines = call("status", "--run", self.dir)
        self.assertEqual(code, 0)
        self.assertRegex(lines[0], SENTENCE.format(status="finished"))
        self.assertIn("2 of 2 steps passed", lines[0])
        self.assertLessEqual(len(lines), 6)

    def test_status_watch_sends_no_ansi_code_when_stdout_is_not_a_tty(self):
        code, lines = call("status", "--run", self.dir, "--watch")
        self.assertEqual(code, 0)
        self.assertRegex(lines[0], SENTENCE.format(status="finished"))
        self.assertNotIn(NO_ANSI, "\n".join(lines))

    def test_status_json_carries_the_same_sentence(self):
        import json
        code, lines = call("status", "--run", self.dir, "--json")
        self.assertEqual(code, 0)
        data = json.loads("\n".join(lines))
        self.assertRegex(data["sentence"], SENTENCE.format(status="finished"))


class StatusOfARunThatIsGoing(TempCase):

    def test_status_counts_the_running_step(self):
        run = self.run_dir("r-going")
        workflow_json(run, [("Map", [agent("a"), agent("b")], 2)])
        (RunLog(run).phase(1, "01.map", "Map", ["01.map/01.a", "01.map/02.b"])
         .start(2, "01.map/01.a").start(3, "01.map/02.b")
         .finish(40, "01.map/02.b", 1, "passed"))
        mark_alive(run)
        code, lines = call("status", "--run", run)
        self.assertEqual(code, 0)
        self.assertRegex(lines[0], SENTENCE.format(status="running"))
        self.assertIn("1 of 2 steps passed, 1 running", lines[0])
        self.assertLessEqual(len(lines), 6)


class StatusOfAFinishedRunWithALiveController(TempCase):

    def test_status_prints_no_dashboard_url_for_a_finished_run(self):
        """A campaign controller serves the dashboard of every run it starts and
        outlives them. Its pid stays alive after the run's dashboard stopped,
        so the record alone cannot say the URL answers."""
        run = copy_tree(G1_RUN, self.tmp / "runs" / "g1")
        controller = live_child(self)
        (run / "dashboard.json").write_text(json.dumps(
            {"url": "http://127.0.0.1:60396/", "pid": controller.pid,
             "supervisor": True}), encoding="utf-8")
        self.assertTrue(dashboard.record_is_live(run), "the record looks live")
        code, lines = call("status", "--run", run)
        self.assertEqual(code, 0)
        self.assertRegex(lines[0], SENTENCE.format(status="finished"))
        self.assertFalse(any(line.startswith("dashboard:") for line in lines),
                         lines)


class StatusOfAnUnknownRun(TempCase):

    def test_status_of_a_directory_with_no_run_exits_2(self):
        code, lines = call("status", "--run", self.tmp / "no-such-run")
        self.assertEqual(code, 2)
        self.assertTrue(re.search(r"no run", lines[0]), lines)
        self.assertLessEqual(len(lines), 2)


if __name__ == "__main__":
    import unittest
    unittest.main()

"""`ohflow go --run DIR` releases a held run, and refuses when nothing waits.

The verb writes `<run-dir>/go`; the held supervisor polls for that file. A
directory with no `.ohflow-hold` has nothing waiting, and a hold whose
supervisor died would never read the file, so both are refused with exit 1
and a sentence that says so.
"""

from __future__ import annotations

import json
import os

from ohflow import cli, rundir
from support import TempCase
from verb_support import call

DEAD_PID = 2147483646


class GoVerb(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.dir = self.run_dir("r-go")
        self.dir.mkdir(parents=True)
        (self.dir / "workflow.json").write_text("{}", encoding="utf-8")

    def hold(self, pid: int) -> None:
        (self.dir / rundir.HOLD_FILE).write_text(
            json.dumps({"pid": pid, "since": "2026-10-09T12:00:00Z"}),
            encoding="utf-8")

    def test_go_refuses_a_directory_with_no_hold(self):
        code, lines = call("go", "--run", self.dir)
        self.assertEqual(code, cli.EXIT_FAIL)
        self.assertIn("no hold", lines[0])
        self.assertFalse((self.dir / rundir.GO_FILE).exists())

    def test_go_refuses_a_hold_whose_supervisor_is_dead(self):
        self.hold(DEAD_PID)
        code, lines = call("go", "--run", self.dir)
        self.assertEqual(code, cli.EXIT_FAIL)
        self.assertIn("dead", lines[0])
        self.assertIn(str(DEAD_PID), lines[0])
        self.assertFalse((self.dir / rundir.GO_FILE).exists())

    def test_go_writes_the_go_file_for_a_live_hold(self):
        self.hold(os.getpid())
        code, lines = call("go", "--run", self.dir)
        self.assertEqual(code, cli.EXIT_OK)
        self.assertTrue(lines[0].startswith("go sent to "), lines)
        stamp = (self.dir / rundir.GO_FILE).read_text(encoding="utf-8").strip()
        self.assertRegex(stamp, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_go_refuses_a_missing_directory(self):
        code, lines = call("go", "--run", self.tmp / "nowhere")
        self.assertEqual(code, cli.EXIT_FAIL)
        self.assertIn("no run directory", lines[0])


if __name__ == "__main__":
    import unittest
    unittest.main()

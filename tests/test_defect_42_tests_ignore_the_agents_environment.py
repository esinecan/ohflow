"""Defect 42: a guard test wrote into the evidence of the run that ran it.

An agent that runs the suite carries the `OHFLOW_*` variables of its own
attempt, among them `OHFLOW_COMMAND_TIME_CAP_LOG`. The guard tests start the pi
guard as a child, the child inherited the variable, and every clamp the test
provoked (`requested 999`, `applied 23`, `applied 0.05`) landed in the
agent's own `logs/command_time_caps.jsonl`. The suite now clears the coordinates
of a running attempt before any child starts.
"""

import os
import subprocess
import sys
from pathlib import Path

import support
from support import TempCase

TESTS = Path(__file__).resolve().parent


class TheSuiteDropsTheAgentsCoordinates(TempCase):

    def _run_guard_test(self, env_extra):
        env = {**os.environ, **env_extra}
        return subprocess.run(
            [sys.executable, str(TESTS / "run_tests.py"),
             "-k", "guard_enforces_write_scope_timeout"],
            capture_output=True, text=True, env=env, timeout=120,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def test_a_guard_test_leaves_the_inherited_cap_log_untouched(self):
        log = self.tmp / "evidence" / "command_time_caps.jsonl"
        done = self._run_guard_test({
            "OHFLOW_COMMAND_TIME_CAP_LOG": str(log),
            "OHFLOW_COMMAND_TIME_CAP_CONTEXT": '{"coord": "01.p/01.s", "attempt": 1}',
        })
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("ran 1 tests", done.stdout)
        self.assertFalse(log.exists(), log.read_text(encoding="utf-8")
                         if log.exists() else "")
        self.assertFalse(log.parent.exists())

    def test_the_scrub_keeps_the_settings_an_operator_chose(self):
        env = {"OHFLOW_COMMAND_TIME_CAP_LOG": "x", "OHFLOW_ATTEMPT": "3",
               "OHFLOW_WRITE_SCOPE": "[]", "OHFLOW_E2E": "1",
               "OHFLOW_BASH": "C:/bash.exe", "OHFLOW_TEST_FAKE_KEY": "k",
               "PATH": "p"}
        support.scrub_attempt_environment(env)
        self.assertEqual(env, {"OHFLOW_E2E": "1", "OHFLOW_BASH": "C:/bash.exe",
                               "OHFLOW_TEST_FAKE_KEY": "k", "PATH": "p"})


if __name__ == "__main__":
    import unittest
    unittest.main()

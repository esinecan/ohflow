"""A test that never ends in time, for the per-test time limit of `run_tests.py`.

The file name matches no `test_*.py`, so the suite never discovers it.
`test_suite_01_test_timeout.py` runs it in a child process.
"""

from __future__ import annotations

import subprocess
import sys
import time
import unittest

#: The file, in the working directory, where the waited-on child writes its pid.
CHILD_PID_FILE = "waited-on-child.pid"

WAITED_ON_CHILD = f"""
import os, time
with open({CHILD_PID_FILE!r}, "w") as out:
    out.write(str(os.getpid()))
time.sleep(120)
"""


class SlowCase(unittest.TestCase):

    def test_1_ends_at_once(self):
        self.assertTrue(True)

    def test_2_sleeps_past_any_limit(self):
        time.sleep(600)

    def test_3_never_starts(self):
        self.assertTrue(True)


class WaitsOnAChild(unittest.TestCase):

    def test_waits_on_a_plain_child_that_holds_stdout(self):
        subprocess.run([sys.executable, "-c", WAITED_ON_CHILD],
                       stdin=subprocess.DEVNULL)

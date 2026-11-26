"""Defect 80: a supervisor that wrote its pid file at once counted as dead.

What went wrong. `pid_alive` treats a process created after its pid file's
mtime as a stranger that inherited the number. On a GitHub Actions Windows
runner the file's mtime ticked coarser than the process's creation time, so a
test owner written a few milliseconds after its start read as created after
the file. `live`, `watch` and `resume` then called a live run dead.

What is asserted here. A process created up to `PID_FILE_SLACK_S` after the
file's mtime is the recorded process. One created an hour after it is still a
stranger.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import unittest

from ohflow import proc
from support import TempCase


@unittest.skipUnless(sys.platform == "win32", "the creation time check is Windows")
class APidFileWrittenAtOnceNamesItsProcess(TempCase):

    def setUp(self):
        super().setUp()
        self.started = time.time()
        self.child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            creationflags=subprocess.CREATE_NO_WINDOW)
        self.addCleanup(self.child.wait, timeout=5)
        self.addCleanup(self.child.kill)
        self.pid_file = self.tmp / "supervisor.pid"
        self.pid_file.write_text(str(self.child.pid), encoding="utf-8")

    def _alive_with_mtime(self, seconds_before_start: float) -> bool:
        written = self.started - seconds_before_start
        os.utime(self.pid_file, (written, written))
        return proc.pid_alive(self.child.pid,
                              started_before=self.pid_file.stat().st_mtime)

    def test_a_creation_half_a_second_after_the_mtime_is_the_recorded_process(self):
        self.assertTrue(self._alive_with_mtime(0.5))

    def test_a_creation_an_hour_after_the_mtime_is_a_stranger(self):
        self.assertFalse(self._alive_with_mtime(3600))


if __name__ == "__main__":
    unittest.main()

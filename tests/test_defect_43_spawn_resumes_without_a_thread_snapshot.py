"""Defect 43: every managed child paid for a snapshot of all threads on the box.

`spawn_managed` starts a child suspended, puts it in a job and resumes it.
Resuming walked `CreateToolhelp32Snapshot(SNAPTHREAD)`, which lists every
thread of every process. It cost 0.36 s per child on this box, and a roll-call
test case starts dozens of git children. `NtResumeProcess` resumes the child from
its handle. The snapshot walk stays as the fallback when that call fails.
"""

import subprocess
import sys
import unittest
from unittest import mock

from ohflow import proc
from support import TempCase


@unittest.skipUnless(sys.platform == "win32", "suspended start is Windows only")
class SpawnResumesTheChildDirectly(TempCase):

    def _spawn(self):
        out = self.tmp / "out.txt"
        with out.open("w") as handle:
            managed = proc.spawn_managed(
                [sys.executable, "-c", "print('ran')"], cwd=self.tmp, env={},
                stdin=subprocess.DEVNULL, stdout=handle, stderr=handle)
            managed.wait(timeout=30)
            managed.close()
        return out.read_text(encoding="utf-8").strip()

    def test_the_child_runs_with_the_thread_snapshot_forbidden(self):
        with mock.patch.object(proc, "_resume_threads_by_snapshot",
                               side_effect=AssertionError("snapshot walked")):
            self.assertEqual(self._spawn(), "ran")

    def test_the_snapshot_walk_still_serves_when_the_direct_call_fails(self):
        with mock.patch.object(proc, "_nt_resume_process",
                               return_value=False), \
                mock.patch.object(proc, "_resume_threads_by_snapshot",
                                  wraps=proc._resume_threads_by_snapshot) as walk:
            self.assertEqual(self._spawn(), "ran")
        walk.assert_called_once()


if __name__ == "__main__":
    unittest.main()

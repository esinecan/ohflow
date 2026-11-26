"""Defect 61: off Windows `kill_tree` ended the direct child and nothing else.

On Windows a managed child sits in a kill-on-close Job Object, so ending it
ends its descendants, also after the child itself exited. Off Windows
`ManagedProcess.kill_tree` called `terminate()` on the one process. On macOS
on 2026-11-15 a descendant survived in three cases: under a live parent, under
a parent that had already exited, and under a parent that ignores SIGTERM,
where `kill_tree` also returned without reaping the parent.

Off Windows a managed child now leads its own process group. `kill_tree`
signals the group with SIGTERM, waits, then sends SIGKILL, and `close` ends
what is left of the group, as closing the job does on Windows. A child of a
guarded runner stays in the runner's group; its tree is found through the
process table.

Every process here is a `/bin/sh` or a `sleep` that the test started, and the
cleanup kills by the recorded pid only.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
import unittest
from unittest import mock

from ohflow import proc
from support import TempCase

POSIX = os.name != "nt"


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _gone(pid: int, within_s: float = 5.0) -> bool:
    deadline = time.monotonic() + within_s
    while time.monotonic() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.05)
    return not _alive(pid)


@unittest.skipUnless(POSIX, "process groups are the POSIX tree")
class KillTreeTakesDescendants(TempCase):

    def _start(self, script: str) -> tuple[proc.ManagedProcess, int]:
        pid_file = self.tmp / "descendant.pid"
        managed = proc.spawn_managed(
            ["/bin/sh", "-c", script.format(pid_file=pid_file)],
            cwd=self.tmp, env=proc.agent_env(), stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self._reap, managed)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not (
                pid_file.exists() and pid_file.read_text().strip()):
            time.sleep(0.02)
        descendant = int(pid_file.read_text())
        self.addCleanup(self._kill_pid, descendant)
        self.assertTrue(_alive(descendant))
        return managed, descendant

    @staticmethod
    def _kill_pid(pid: int) -> None:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass

    @staticmethod
    def _reap(managed: proc.ManagedProcess) -> None:
        if managed.process.poll() is None:
            managed.process.kill()
        try:
            managed.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass

    def test_a_descendant_of_a_live_parent_ends(self):
        managed, descendant = self._start(
            "sleep 300 & echo $! > {pid_file}; wait")
        managed.kill_tree(timeout_s=5)
        self.assertTrue(_gone(descendant), "the descendant survived")
        self.assertIsNotNone(managed.returncode, "the parent was not reaped")

    def test_a_descendant_ends_after_its_parent_exited_first(self):
        managed, descendant = self._start("sleep 300 & echo $! > {pid_file}")
        managed.wait(timeout=10)
        managed.kill_tree(timeout_s=5)
        self.assertTrue(_gone(descendant),
                        "the descendant outlived a parent that exited first")

    def test_the_forced_path_ends_a_parent_that_ignores_sigterm(self):
        managed, descendant = self._start(
            "trap '' TERM; sleep 300 & echo $! > {pid_file}; wait")
        started = time.monotonic()
        managed.kill_tree(timeout_s=1)
        self.assertLess(time.monotonic() - started, 8)
        self.assertTrue(_gone(descendant), "the descendant survived SIGKILL")
        self.assertIsNotNone(managed.returncode, "the parent was not reaped")

    def test_the_graceful_path_lets_a_parent_exit_on_sigterm(self):
        marker = self.tmp / "graceful"
        managed, descendant = self._start(
            f"trap 'echo done > {marker}; exit 0' TERM; "
            "sleep 300 & echo $! > {pid_file}; wait")
        managed.kill_tree(timeout_s=5)
        self.assertTrue(marker.exists(), "SIGKILL arrived before SIGTERM")
        self.assertTrue(_gone(descendant))

    def test_close_ends_what_a_finished_child_left_behind(self):
        managed, descendant = self._start("sleep 300 & echo $! > {pid_file}")
        managed.wait(timeout=10)
        managed.close()
        self.assertTrue(_gone(descendant),
                        "close left a descendant of a finished child")

    def test_a_child_of_a_guarded_runner_loses_its_tree_too(self):
        # A guarded runner's children stay in the runner's own group, so the
        # tree is read from the process table.
        with mock.patch.object(proc, "_CURRENT_JOB", "process-group"):
            managed, descendant = self._start(
                "sleep 300 & echo $! > {pid_file}; wait")
        self.assertIsNone(managed.pgid)
        self.assertEqual(os.getpgid(managed.pid), os.getpgrp())
        managed.kill_tree(timeout_s=5)
        self.assertTrue(_gone(descendant), "the descendant survived")
        self.assertTrue(_alive(os.getpid()))

    def test_a_managed_child_leads_its_own_group(self):
        managed, _descendant = self._start(
            "sleep 300 & echo $! > {pid_file}; wait")
        self.assertEqual(managed.pgid, managed.pid)
        self.assertEqual(os.getpgid(managed.pid), managed.pid)
        self.assertNotEqual(os.getpgid(managed.pid), os.getpgrp())
        managed.kill_tree(timeout_s=5)


if __name__ == "__main__":
    unittest.main()

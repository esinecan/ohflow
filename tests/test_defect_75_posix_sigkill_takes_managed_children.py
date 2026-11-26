"""Defect 75: off Windows a SIGKILL of the supervisor left its children running.

On Windows the kernel closes the job of a dead owner, so a killed supervisor
takes its managed children with it. Off Windows the owner ended its process
groups itself, at exit and on SIGTERM and SIGHUP (defect 64), and a SIGKILL
gave it no chance to. On macOS on 2026-11-15 the `sleep` of a command step
outlived its killed supervisor.

Off Windows `proc` now starts one group watcher per owner, in its own session,
on the read end of a pipe that only the owner can write. The owner names each
group it starts and each group it has ended. When the pipe ends, the owner is
gone, and the watcher ends the groups still named. A process started through
`detach.launch` is no managed child, so it stays.

Every process here is one this test started, and the cleanup kills by the
recorded pid only.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import unittest
from pathlib import Path

from ohflow import group_watcher, proc
from support import TempCase

POSIX = os.name != "nt"
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

OWNER = """
import os, signal, subprocess, sys, time
from pathlib import Path
from ohflow import detach, proc
tmp = Path(sys.argv[1])
mode = sys.argv[2]

def managed(name):
    return proc.spawn_managed(
        ["/bin/sh", "-c", f"sleep 300 & echo $! > {tmp / name}; wait"],
        cwd=tmp, env=proc.agent_env(), stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def written(name):
    while not ((tmp / name).exists() and (tmp / name).read_text().strip()):
        time.sleep(0.02)

child = managed("descendant.pid")
written("descendant.pid")
watcher = getattr(proc, "_WATCHER", None)
if watcher is not None:
    (tmp / "watcher.pid").write_text(str(watcher.pid))
if mode == "detached":
    launched = detach.launch(["/bin/sh", "-c", "sleep 300"], cwd=tmp,
                             env=proc.agent_env(), log_path=tmp / "detached.log")
    (tmp / "detached.pid").write_text(str(launched.pid))
if mode == "ended":
    child.kill_tree(timeout_s=5)
    managed("second.pid")
    written("second.pid")
if mode == "watcherless":
    os.kill(proc._WATCHER.pid, signal.SIGKILL)
    proc._WATCHER.wait(timeout=10)
    second = managed("second.pid")
    written("second.pid")
    second.kill_tree(timeout_s=5)
    child.kill_tree(timeout_s=5)
    print("ready", flush=True)
    sys.exit(0)
print("ready", flush=True)
if mode == "exit":
    sys.exit(0)
time.sleep(300)
"""


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


@unittest.skipUnless(POSIX, "process groups are the POSIX tree")
class AKilledOwnerLosesItsManagedChildren(TempCase):

    def _owner(self, mode: str = "wait") -> subprocess.Popen:
        script = self.tmp / "owner.py"
        script.write_text(OWNER, encoding="utf-8")
        env = proc.agent_env()
        env["PYTHONPATH"] = str(SCRIPTS) + os.pathsep + env.get("PYTHONPATH", "")
        owner = subprocess.Popen(
            [sys.executable, str(script), str(self.tmp), mode],
            cwd=str(self.tmp), env=env, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, text=True,
            start_new_session=True)
        self.addCleanup(owner.stdout.close)
        self.addCleanup(self._reap, owner)
        self.addCleanup(self._kill_recorded)
        self.assertEqual(owner.stdout.readline().strip(), "ready")
        return owner

    def _pid(self, name: str) -> int:
        return int((self.tmp / name).read_text())

    def _kill_recorded(self) -> None:
        for pid_file in self.tmp.glob("*.pid"):
            try:
                os.kill(int(pid_file.read_text()), signal.SIGKILL)
            except (OSError, ValueError):
                pass

    @staticmethod
    def _reap(owner: subprocess.Popen) -> None:
        if owner.poll() is None:
            owner.kill()
        owner.wait(timeout=10)

    def _gone(self, pid: int) -> bool:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and _alive(pid):
            time.sleep(0.05)
        return not _alive(pid)

    def _kill(self, owner: subprocess.Popen) -> None:
        os.kill(owner.pid, signal.SIGKILL)
        self.assertEqual(owner.wait(timeout=15), -signal.SIGKILL)

    def test_a_kill_ends_the_tree(self):
        owner = self._owner()
        descendant = self._pid("descendant.pid")
        self.assertTrue(_alive(descendant))
        self._kill(owner)
        self.assertTrue(self._gone(descendant),
                        "SIGKILL to the owner left its descendant alive")
        self.assertTrue(self._gone(self._pid("watcher.pid")),
                        "the group watcher outlived its work")

    def test_a_kill_leaves_a_detached_process(self):
        owner = self._owner("detached")
        descendant, detached = self._pid("descendant.pid"), self._pid("detached.pid")
        self._kill(owner)
        self.assertTrue(self._gone(descendant))
        self.assertTrue(self._gone(self._pid("watcher.pid")))
        self.assertTrue(_alive(detached),
                        "the group watcher ended a detached process")

    def test_a_kill_ends_only_the_groups_still_owned(self):
        owner = self._owner("ended")
        self.assertTrue(self._gone(self._pid("descendant.pid")))
        second = self._pid("second.pid")
        self.assertTrue(_alive(second))
        self._kill(owner)
        self.assertTrue(self._gone(second))

    def test_a_plain_exit_ends_the_watcher(self):
        owner = self._owner("exit")
        self.assertEqual(owner.wait(timeout=15), 0)
        self.assertTrue(self._gone(self._pid("descendant.pid")))
        self.assertTrue(self._gone(self._pid("watcher.pid")),
                        "the group watcher outlived an owner that exited")

    def test_an_owner_outlives_its_watcher(self):
        owner = self._owner("watcherless")
        self.assertEqual(owner.wait(timeout=15), 0)
        self.assertTrue(self._gone(self._pid("descendant.pid")))
        self.assertTrue(self._gone(self._pid("second.pid")))


class TheWatcherKeepsTheGroupsStillOwned(unittest.TestCase):

    def test_an_ended_group_is_forgotten(self):
        self.assertEqual(
            group_watcher.owned_groups([b"+41\n", b"+42\n", b"-41\n"]), {42})

    def test_a_line_that_names_no_group_is_skipped(self):
        self.assertEqual(
            group_watcher.owned_groups(
                [b"\n", b"+\n", b"+0\n", b"+1\n", b"42\n", b"+x\n", b"+43\n"]),
            {43})


if __name__ == "__main__":
    unittest.main()

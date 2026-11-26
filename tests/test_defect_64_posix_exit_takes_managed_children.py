"""Defect 64: off Windows an interrupted supervisor left its children running.

On Windows a managed child sits in a kill-on-close job, so when the process
that started it ends - by Ctrl-C, by a kill, by a crash - the kernel ends the
child's tree. Off Windows a managed child leads its own session, so a terminal
interrupt reaches the supervisor only. On macOS on 2026-11-15 a `run` that got
SIGINT wrote its exit report and exited, and the `sleep` of its command step
kept running; SIGTERM did the same.

Off Windows `proc` now keeps the groups this process started. It ends them
when the interpreter exits, and `install_exit_signals` (called by the CLI)
makes SIGTERM and SIGHUP end them too. A SIGKILL of the supervisor is
defect 75.

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

from ohflow import proc
from support import TempCase

POSIX = os.name != "nt"
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

OWNER = """
import subprocess, sys, time
from pathlib import Path
from ohflow import proc
proc.install_exit_signals()
tmp = Path(sys.argv[1])
proc.spawn_managed(
    ["/bin/sh", "-c", f"sleep 300 & echo $! > {tmp / 'descendant.pid'}; wait"],
    cwd=tmp, env=proc.agent_env(), stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print("ready", flush=True)
if sys.argv[2] == "exit":
    while not (tmp / "descendant.pid").exists():
        time.sleep(0.02)
    time.sleep(0.2)
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
class TheOwnersExitEndsItsManagedChildren(TempCase):

    def _owner(self, mode: str = "wait") -> tuple[subprocess.Popen, int]:
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
        self.assertEqual(owner.stdout.readline().strip(), "ready")
        pid_file = self.tmp / "descendant.pid"
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not (
                pid_file.exists() and pid_file.read_text().strip()):
            time.sleep(0.02)
        descendant = int(pid_file.read_text())
        self.addCleanup(self._kill, descendant)
        return owner, descendant

    @staticmethod
    def _kill(pid: int) -> None:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
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

    def _signal_ends_the_tree(self, sig: int) -> None:
        owner, descendant = self._owner()
        self.assertTrue(_alive(descendant))
        os.kill(owner.pid, sig)
        owner.wait(timeout=15)
        self.assertTrue(self._gone(descendant),
                        f"signal {sig} to the owner left its descendant alive")

    def test_an_interrupt_ends_the_tree(self):
        self._signal_ends_the_tree(signal.SIGINT)

    def test_a_terminate_ends_the_tree(self):
        self._signal_ends_the_tree(signal.SIGTERM)

    def test_a_hangup_ends_the_tree(self):
        self._signal_ends_the_tree(signal.SIGHUP)

    def test_a_terminate_still_ends_the_owner_by_the_signal(self):
        owner, _descendant = self._owner()
        os.kill(owner.pid, signal.SIGTERM)
        self.assertEqual(owner.wait(timeout=15), -signal.SIGTERM)

    def test_a_plain_exit_ends_the_tree(self):
        owner, descendant = self._owner("exit")
        owner.wait(timeout=15)
        self.assertTrue(self._gone(descendant),
                        "the owner's exit left its descendant alive")


if __name__ == "__main__":
    unittest.main()

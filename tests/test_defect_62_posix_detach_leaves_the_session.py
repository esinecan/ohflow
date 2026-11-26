"""Defect 62: off Windows a detached run stayed in its launcher's session.

`detach.launch` started the background process with a plain `Popen`. Off
Windows that child keeps the launcher's session and process group, so the
signal that ends the launcher's group also ends the promised background run:
SIGHUP when the terminal closes, SIGINT on Ctrl-C.

Off Windows `launch` now starts the child in a new session. The launch method
is still reported as `direct`.

Every process here is one this test started, and the cleanup kills by the
recorded pid only.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import unittest
from pathlib import Path

from ohflow import detach, proc
from support import TempCase

POSIX = os.name != "nt"
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

LAUNCHER = """
import json, os, sys, time
from ohflow import detach
launched = detach.launch([sys.executable, "-c", "import time; time.sleep(300)"],
                         cwd=sys.argv[1], env=os.environ, log_path=sys.argv[2])
print(json.dumps({"pid": launched.pid, "method": launched.method}), flush=True)
time.sleep(300)
"""


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


@unittest.skipUnless(POSIX, "sessions are the POSIX detach")
class ADetachedProcessLeavesItsLaunchersSession(TempCase):

    def _kill(self, pid: int) -> None:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass

    def test_the_child_leads_a_session_of_its_own(self):
        launched = detach.launch(
            [sys.executable, "-c", "import time; time.sleep(300)"],
            cwd=self.tmp, env=proc.agent_env(), log_path=self.tmp / "d.log")
        self.addCleanup(self._kill, launched.pid)
        self.assertEqual(launched.method, "direct")
        self.assertEqual(os.getsid(launched.pid), launched.pid)
        self.assertNotEqual(os.getsid(launched.pid), os.getsid(0))
        self.assertNotEqual(os.getpgid(launched.pid), os.getpgrp())

    def _launcher(self) -> tuple[subprocess.Popen, int]:
        script = self.tmp / "launcher.py"
        script.write_text(LAUNCHER, encoding="utf-8")
        env = proc.agent_env()
        env["PYTHONPATH"] = str(SCRIPTS) + os.pathsep + env.get("PYTHONPATH", "")
        launcher = subprocess.Popen(
            [sys.executable, str(script), str(self.tmp),
             str(self.tmp / "detached.log")],
            cwd=str(self.tmp), env=env, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, text=True,
            start_new_session=True)
        self.addCleanup(launcher.stdout.close)
        self.addCleanup(self._reap, launcher)
        line = launcher.stdout.readline()
        self.assertTrue(line, "the launcher printed no pid")
        detached = int(json.loads(line)["pid"])
        self.addCleanup(self._kill, detached)
        self.assertTrue(_alive(detached))
        return launcher, detached

    def _reap(self, launcher: subprocess.Popen) -> None:
        if launcher.poll() is None:
            launcher.kill()
        launcher.wait(timeout=10)

    def _survives(self, sig: int) -> None:
        launcher, detached = self._launcher()
        os.killpg(launcher.pid, sig)
        launcher.wait(timeout=10)
        time.sleep(0.5)
        self.assertTrue(_alive(detached),
                        f"signal {sig} to the launcher's group ended the "
                        "detached process")

    def test_it_survives_the_hangup_of_its_launchers_terminal(self):
        self._survives(signal.SIGHUP)

    def test_it_survives_an_interrupt_of_its_launchers_group(self):
        self._survives(signal.SIGINT)


if __name__ == "__main__":
    unittest.main()

"""D-36: a command step that times out ends with its whole process tree.

Before: `exec.run` ran the command through `subprocess.run(timeout=...)`. The
timeout killed the shell only. A grandchild that held the stdout pipe kept
`communicate()` waiting until the grandchild exited, so the step ran far past
its timeout and the grandchild lived on.
Now: `exec.run` starts the command through `proc.spawn_managed`, and a timeout
kills the job object, so the step ends at the timeout and nothing is left.
"""

from __future__ import annotations

import json
import os
import sys
import time
import unittest
from pathlib import Path

from ohflow import exec as ohexec
from support import TempCase
from tree_kill_support import (
    _process_identity, _same_process_alive)

TIMEOUT_S = 5
GRACE_S = 30
GRANDCHILD_LIFE_S = 90

GRANDCHILD = """import ctypes, json, os, pathlib, time
from ctypes import wintypes
k = ctypes.WinDLL('kernel32', use_last_error=True)
k.GetCurrentProcess.restype = wintypes.HANDLE
k.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
k.GetProcessTimes(k.GetCurrentProcess(), ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel), ctypes.byref(user))
identity = (created.dwHighDateTime << 32) | created.dwLowDateTime
pathlib.Path(os.environ['OHFLOW_D36_MARKER']).write_text(json.dumps({'pid': os.getpid(), 'created': identity}), encoding='ascii')
time.sleep(%d)
""" % GRANDCHILD_LIFE_S

CHILD = """import os, subprocess, sys, time
subprocess.Popen([sys.executable, os.environ['OHFLOW_D36_GRANDCHILD']])
time.sleep(%d)
""" % GRANDCHILD_LIFE_S


@unittest.skipUnless(sys.platform == "win32", "Windows Job Object contract")
class TreeKillCommandStep(TempCase):

    def _read_identity(self, marker: Path):
        try:
            record = json.loads(marker.read_text(encoding="ascii"))
            return int(record["pid"]), int(record["created"])
        except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError):
            return None

    def test_tree_kill_a_timed_out_command_takes_a_grandchild_that_holds_stdout(self):
        marker = self.tmp / "grandchild.json"
        grandchild = self.tmp / "grandchild.py"
        child = self.tmp / "child.py"
        grandchild.write_text(GRANDCHILD, encoding="utf-8")
        child.write_text(CHILD, encoding="utf-8")
        self.addCleanup(self._restore_env, "OHFLOW_D36_MARKER",
                        os.environ.get("OHFLOW_D36_MARKER"))
        self.addCleanup(self._restore_env, "OHFLOW_D36_GRANDCHILD",
                        os.environ.get("OHFLOW_D36_GRANDCHILD"))
        os.environ["OHFLOW_D36_MARKER"] = str(marker)
        os.environ["OHFLOW_D36_GRANDCHILD"] = str(grandchild)

        started = time.monotonic()
        try:
            done = ohexec.run(f'"{sys.executable}" "{child}"', cwd=self.tmp,
                              shell="cmd", timeout=TIMEOUT_S,
                              log_dir=self.tmp / "logs", name="holds-stdout")
        finally:
            identity = self._read_identity(marker)
            if identity:
                self.addCleanup(self._force_kill, *identity)
        elapsed = time.monotonic() - started

        self.assertTrue(done.timed_out)
        self.assertEqual(done.returncode, 124)
        self.assertIn("timed out after", done.stderr)
        self.assertLess(elapsed, TIMEOUT_S + GRACE_S,
                        "the step ran far past its timeout")
        self.assertIsNotNone(identity, "the grandchild never started")
        deadline = time.monotonic() + 10
        while (time.monotonic() < deadline
               and _same_process_alive(*identity)):
            time.sleep(0.05)
        self.assertFalse(_same_process_alive(*identity),
                         "the grandchild survived the timeout")

    @staticmethod
    def _restore_env(name: str, value: str | None) -> None:
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value

    @staticmethod
    def _force_kill(pid: int, created: int) -> None:
        if _process_identity(pid) == created:
            import subprocess
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL,
                           creationflags=0x08000000, check=False)


if __name__ == "__main__":
    unittest.main()

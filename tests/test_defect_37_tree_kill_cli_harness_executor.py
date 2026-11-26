"""D-37: killing a CLI harness executor agent takes descendants after the agent exits.

Before: `CliHarnessExecutor.launch` used a plain `subprocess.Popen` and `CliHarnessExecutor.kill`
ran `taskkill /T`. When the runner had exited, `kill` returned at once, and
`taskkill /T` could not find a grandchild the runner had left behind.
Now: `launch` starts the runner through `proc.spawn_managed`, and `kill` ends
the job object, so a reparented grandchild goes with it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

from ohflow.cli_harness_executor import CliHarnessExecutor
from support import TempCase
from tree_kill_support import (
    _process_identity, _same_process_alive)


@unittest.skipUnless(sys.platform == "win32", "Windows Job Object contract")
class TreeKillCliHarnessExecutor(TempCase):

    def _wait(self, predicate, message: str, timeout: float = 10.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            time.sleep(0.05)
        self.fail(message)

    def test_tree_kill_cli_harness_executor_kill_takes_a_reparented_grandchild(self):
        marker = self.tmp / "grandchild.json"
        grandchild = self.tmp / "grandchild.py"
        grandchild.write_text(
            """import ctypes, json, os, pathlib, time
from ctypes import wintypes
k = ctypes.WinDLL('kernel32', use_last_error=True)
k.GetCurrentProcess.restype = wintypes.HANDLE
k.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
k.GetProcessTimes(k.GetCurrentProcess(), ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel), ctypes.byref(user))
identity = (created.dwHighDateTime << 32) | created.dwLowDateTime
pathlib.Path(os.environ['OHFLOW_D37_MARKER']).write_text(json.dumps({'pid': os.getpid(), 'created': identity}), encoding='ascii')
time.sleep(60)
""",
            encoding="utf-8",
        )
        (self.tmp / "sitecustomize.py").write_text(
            """import os, subprocess, sys
env = dict(os.environ)
env.pop('PYTHONPATH', None)
subprocess.Popen(
    [sys.executable, '-S', os.environ['OHFLOW_D37_GRANDCHILD']],
    env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
os._exit(0)
""",
            encoding="utf-8",
        )
        for name, value in (("PYTHONPATH", str(self.tmp)),
                            ("OHFLOW_D37_MARKER", str(marker)),
                            ("OHFLOW_D37_GRANDCHILD", str(grandchild))):
            self.addCleanup(self._restore_env, name, os.environ.get(name))
            os.environ[name] = value

        harness_executor = CliHarnessExecutor(name="d37", runner_module="d37_runner",
                                              python=Path(sys.executable))
        handle = harness_executor.launch({"coord": "01.only/01.cli", "attempt": 1},
                                         self.tmp / "attempt")
        identity = self._wait(lambda: self._read_identity(marker),
                              "grandchild did not record its process identity")
        pid, created = identity
        self.addCleanup(self._force_kill, pid, created)
        self._wait(lambda: handle.process.poll() is not None,
                   "fake runner did not exit")
        self.assertTrue(_same_process_alive(pid, created))

        harness_executor.kill(handle)

        self._wait(lambda: not _same_process_alive(pid, created),
                   "cli harness executor grandchild survived harness_executor.kill")

    @staticmethod
    def _read_identity(path: Path):
        try:
            record = json.loads(path.read_text(encoding="ascii"))
            return int(record["pid"]), int(record["created"])
        except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError):
            return None

    @staticmethod
    def _restore_env(name: str, value: str | None) -> None:
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value

    @staticmethod
    def _force_kill(pid: int, created: int) -> None:
        if _process_identity(pid) == created:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL,
                           creationflags=0x08000000, check=False)


if __name__ == "__main__":
    unittest.main()

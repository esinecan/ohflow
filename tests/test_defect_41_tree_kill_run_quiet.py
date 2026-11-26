"""D-41: a quiet probe that times out ends with its whole process tree.

Before: `signed_in.run_quiet` ran `claude auth status` and `claude --version`
through `subprocess.run(timeout=...)`. `claude` on Windows is a `.cmd` shim that
starts `node`. The timeout killed the shim only, and a `node` grandchild that
held the stdout pipe kept `communicate()` waiting until it exited.
Now: `run_quiet` starts the probe through `proc.run_managed`, and a timeout
kills the job object, so the call ends at the timeout and nothing is left.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import unittest

import test_defect_36_tree_kill_command_step as d36
from ohflow.signed_in import run_quiet
from support import TempCase
from tree_kill_support import _same_process_alive


@unittest.skipUnless(sys.platform == "win32", "Windows Job Object contract")
class TreeKillRunQuiet(TempCase):

    def test_tree_kill_a_timed_out_probe_takes_a_grandchild_that_holds_stdout(self):
        marker = self.tmp / "grandchild.json"
        grandchild = self.tmp / "grandchild.py"
        child = self.tmp / "child.py"
        grandchild.write_text(d36.GRANDCHILD, encoding="utf-8")
        child.write_text(d36.CHILD, encoding="utf-8")
        env = dict(os.environ, OHFLOW_D36_MARKER=str(marker),
                   OHFLOW_D36_GRANDCHILD=str(grandchild))

        started = time.monotonic()
        try:
            with self.assertRaises(subprocess.TimeoutExpired):
                run_quiet([sys.executable, str(child)],
                          timeout=d36.TIMEOUT_S, env=env)
        finally:
            identity = d36.TreeKillCommandStep._read_identity(None, marker)
            if identity:
                self.addCleanup(d36.TreeKillCommandStep._force_kill, *identity)
        elapsed = time.monotonic() - started

        self.assertLess(elapsed, d36.TIMEOUT_S + d36.GRACE_S,
                        "the probe ran far past its timeout")
        self.assertIsNotNone(identity, "the grandchild never started")
        deadline = time.monotonic() + 10
        while (time.monotonic() < deadline
               and _same_process_alive(*identity)):
            time.sleep(0.05)
        self.assertFalse(_same_process_alive(*identity),
                         "the grandchild survived the timeout")

    def test_a_probe_that_finishes_returns_its_output(self):
        done = run_quiet([sys.executable, "-c",
                          "import sys; print('out'); print('err', file=sys.stderr);"
                          " sys.exit(3)"], timeout=30)
        self.assertEqual(done.returncode, 3)
        self.assertEqual(done.stdout.strip(), "out")
        self.assertEqual(done.stderr.strip(), "err")


if __name__ == "__main__":
    unittest.main()

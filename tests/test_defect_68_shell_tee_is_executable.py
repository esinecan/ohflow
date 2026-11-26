"""Defect 68: off Windows every Bash command of a claude agent exited 126.

The claude harness executor routes each Bash command through `shell_tee.sh`
with `CLAUDE_CODE_SHELL_PREFIX`. Claude runs the prefix as a program. The file
was tracked with mode 100644, which Git Bash on Windows ignores, so on macOS
each command ended in `permission denied: .../shell_tee.sh` and the agent could
run nothing: no git commit, so `commits_past_base` failed.

The file is tracked executable now, and `shell_capture_env` restores the bit
for an install that lost it (a zip, a copy), or routes nothing when it cannot.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import unittest
from pathlib import Path

from ohflow import claude_runner
from ohflow.claude_runner import SHELL_TEE, shell_capture_env
from support import TempCase

POSIX = os.name != "nt"


@unittest.skipUnless(POSIX, "Git Bash on Windows ignores the executable bit")
class TheShellPrefixRunsAsAProgram(TempCase):

    def test_the_shipped_wrapper_is_executable(self):
        env = shell_capture_env(self.tmp / "out")
        self.assertEqual(env["CLAUDE_CODE_SHELL_PREFIX"], str(SHELL_TEE))
        self.assertTrue(os.access(SHELL_TEE, os.X_OK))

    def test_the_wrapper_is_tracked_executable(self):
        root = SHELL_TEE.parent
        p = subprocess.run(["git", "-C", str(root), "ls-files", "-s", SHELL_TEE.name],
                           capture_output=True, text=True)
        if p.returncode != 0 or not p.stdout.strip():
            self.skipTest("not a git checkout")
        self.assertTrue(p.stdout.startswith("100755 "), p.stdout)

    def test_a_copy_without_the_bit_gets_it_back_and_runs(self):
        copy = self.tmp / "shell_tee.sh"
        shutil.copyfile(SHELL_TEE, copy)
        copy.chmod(0o644)
        self.assertFalse(os.access(copy, os.X_OK))
        self.assertTrue(claude_runner.ensure_executable(copy))
        self.assertTrue(copy.stat().st_mode & stat.S_IXUSR)
        # The way Claude runs it: `bash -c "<prefix> '<line>'"`.
        p = subprocess.run(["bash", "-c", f"{copy} 'echo ran-through-the-prefix'"],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.strip(), "ran-through-the-prefix")

    def test_a_wrapper_that_cannot_run_routes_nothing(self):
        missing = self.tmp / "gone" / "shell_tee.sh"
        self.assertFalse(claude_runner.ensure_executable(missing))
        original = claude_runner.SHELL_TEE
        claude_runner.SHELL_TEE = missing
        try:
            self.assertEqual(shell_capture_env(self.tmp / "out"), {})
        finally:
            claude_runner.SHELL_TEE = original


if __name__ == "__main__":
    unittest.main()

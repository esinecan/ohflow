"""`bash_exe` never returns a WSL launcher, whatever its letter case.

Windows has two WSL launchers named `bash.exe`. One is under %SystemRoot%, and
a PATH entry spelled `c:\\windows\\system32\\bash.exe` once passed a guard that
looked for "System32". The other is the app execution alias in
`%LOCALAPPDATA%\\Microsoft\\WindowsApps`, which points at `wsl.exe`. A
PowerShell PATH can hold Git's `cmd` and `mingw64\\bin` and no Git `bash.exe`,
so the alias was the first `bash` found there. The engine then ran
`git rev-parse` in WSL, read the branch as '' and failed preflight.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

from ohflow import paths

GIT_BASH = r"C:\Program Files\Git\bin\bash.exe"


class BashExeSkipsTheSystemRoot(unittest.TestCase):
    def setUp(self):
        if not Path(GIT_BASH).exists():
            self.skipTest(f"Git Bash is not installed at {GIT_BASH}")

    def bash_exe_with_path_hit(self, hit: str) -> str:
        env = {"SystemRoot": r"C:\Windows"}
        with mock.patch.dict(os.environ, env), \
                mock.patch.dict(os.environ, {"OHFLOW_BASH": ""}), \
                mock.patch.object(paths.shutil, "which", return_value=hit):
            return paths.bash_exe()

    def test_bash_exe_lower_cased_system32_still_yields_git_bash(self):
        found = self.bash_exe_with_path_hit(r"c:\windows\system32\bash.exe")
        self.assertEqual(found, GIT_BASH)

    def test_bash_exe_upper_cased_system32_still_yields_git_bash(self):
        found = self.bash_exe_with_path_hit(r"C:\WINDOWS\SYSTEM32\BASH.EXE")
        self.assertEqual(found, GIT_BASH)

    def test_bash_exe_skips_the_windows_apps_alias(self):
        found = self.bash_exe_with_path_hit(
            r"C:\Users\<user>\AppData\Local\Microsoft\WindowsApps\bash.EXE")
        self.assertEqual(found, GIT_BASH)

    def test_bash_exe_keeps_a_bash_outside_the_system_root(self):
        found = self.bash_exe_with_path_hit(r"D:\tools\git\bin\bash.exe")
        self.assertEqual(found, r"D:\tools\git\bin\bash.exe")


if __name__ == "__main__":
    unittest.main()

"""Defect 65: off Windows the durable executor looked for ssh in System32.

`durable_runner` named `C:\\Windows\\System32\\OpenSSH\\ssh.exe` and
`scp.exe` as its defaults on every platform. On macOS on 2026-11-15 the
`preflight` verb said `ssh executable not found at
C:\\Windows\\System32\\OpenSSH\\ssh.exe`. The Git Bash check's fix hint said
`install Git for Windows` on a Mac.

Off Windows the defaults are the `ssh` and `scp` on PATH, and the bash hint
names bash. On Windows both stay as they were. No ssh is started here: the
tests read the argv only.
"""

from __future__ import annotations

import os
import stat
import unittest
from unittest import mock

from ohflow import durable_runner, preflight
from support import TempCase

POSIX = os.name != "nt"


@unittest.skipUnless(POSIX, "the POSIX lookup")
class SshAndScpComeFromPath(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        patch = mock.patch.dict(os.environ, {
            "PATH": str(self.bin), "OHFLOW_DURABLE_SSH": "",
            "OHFLOW_DURABLE_SCP": ""})
        patch.start()
        self.addCleanup(patch.stop)

    def _on_path(self, name: str):
        exe = self.bin / name
        exe.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
        return exe

    def test_ssh_on_path_is_the_program(self):
        exe = self._on_path("ssh")
        self.assertEqual(durable_runner.ssh_argv()[0], str(exe))

    def test_scp_on_path_is_the_program(self):
        exe = self._on_path("scp")
        self.assertEqual(durable_runner.scp_argv()[0], str(exe))

    def test_a_missing_ssh_names_no_windows_path(self):
        with self.assertRaises(FileNotFoundError) as caught:
            durable_runner.ssh_argv()
        self.assertIn("OHFLOW_DURABLE_SSH", str(caught.exception))
        self.assertNotIn("System32", str(caught.exception))

    def test_an_override_wins_over_path(self):
        self._on_path("ssh")
        other = self._on_path("other-ssh")
        with mock.patch.dict(os.environ, {"OHFLOW_DURABLE_SSH": str(other)}):
            self.assertEqual(durable_runner.ssh_argv()[0], str(other))


class TheBashHintNamesThisPlatform(unittest.TestCase):

    @unittest.skipUnless(POSIX, "the POSIX hint")
    def test_the_hint_does_not_send_a_mac_to_git_for_windows(self):
        hint = preflight.bash_check().fix
        self.assertNotIn("Git for Windows", hint)
        self.assertIn("bash", hint)
        self.assertIn("OHFLOW_BASH", hint)

    @unittest.skipIf(POSIX, "the Windows hint")
    def test_the_hint_still_names_git_for_windows_on_windows(self):
        self.assertIn("Git for Windows", preflight.bash_check().fix)


if __name__ == "__main__":
    unittest.main()

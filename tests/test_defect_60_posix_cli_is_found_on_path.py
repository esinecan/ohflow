"""Defect 60: off Windows no signed-in CLI was found without an override.

`signed_in.executable_argv` resolved the npm `.cmd` shim under `%APPDATA%`
and nothing else for `claude` and `codex`. A Mac has no `.cmd` shim:
npm, a native installer or Homebrew puts an executable named `claude` on
PATH. On macOS on 2026-11-15, with `claude` on PATH, the lookup raised
`claude executable not found; set OHFLOW_CLAUDE_EXE`.

Off Windows the lookup takes the first PATH hit of the plain name. On Windows
the rule stays: the npm shim is resolved to its target and PATH is never
searched first.
"""

from __future__ import annotations

import os
import stat
import unittest
from unittest import mock

from ohflow import signed_in
from support import TempCase

POSIX = os.name != "nt"


@unittest.skipUnless(POSIX, "the POSIX lookup")
class ASignedInCliIsFoundOnPath(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        for var in ("OHFLOW_CLAUDE_EXE", "OHFLOW_CODEX_EXE"):
            patch = mock.patch.dict(os.environ, {var: ""})
            patch.start()
            self.addCleanup(patch.stop)

    def _on_path(self, name: str):
        exe = self.bin / name
        exe.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
        patch = mock.patch.dict(os.environ, {"PATH": str(self.bin)})
        patch.start()
        self.addCleanup(patch.stop)
        return exe

    def test_claude_on_path_is_the_executable(self):
        exe = self._on_path("claude")
        self.assertEqual(
            signed_in.executable_argv("OHFLOW_CLAUDE_EXE", "claude"),
            [str(exe)])

    def test_codex_on_path_is_the_executable(self):
        exe = self._on_path("codex")
        self.assertEqual(
            signed_in.executable_argv("OHFLOW_CODEX_EXE", "codex"),
            [str(exe)])

    def test_an_override_wins_over_path(self):
        self._on_path("claude")
        other = self.tmp / "other-claude"
        with mock.patch.dict(os.environ, {"OHFLOW_CLAUDE_EXE": str(other)}):
            self.assertEqual(
                signed_in.executable_argv("OHFLOW_CLAUDE_EXE", "claude"),
                [str(other)])

    def test_a_missing_cli_names_the_override_variable(self):
        with mock.patch.dict(os.environ, {"PATH": str(self.bin)}):
            with self.assertRaises(FileNotFoundError) as caught:
                signed_in.executable_argv("OHFLOW_CLAUDE_EXE", "claude")
        self.assertIn("OHFLOW_CLAUDE_EXE", str(caught.exception))


if __name__ == "__main__":
    unittest.main()

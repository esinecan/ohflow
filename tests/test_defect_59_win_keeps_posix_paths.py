"""Defect 59: `paths.win` turned a POSIX path into one name with backslashes.

`win` renders a path for cmd.exe, PowerShell and any text an agent reads. Off
Windows it still replaced every `/` with a backslash, so `/tmp/run/wt/pi-1`
became `\\tmp\\run\\wt\\pi-1`: one relative file name. An agent that read its
worktree from the position block then worked in the current directory. On
macOS on 2026-11-15 the suite's fake agents made 11 commits in the source
checkout and left 12 such directories in it.

Off Windows `win` returns the path as the platform writes it. On Windows it
still returns backslashes.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from ohflow import paths
from support import TempCase

POSIX = os.name != "nt"


class WinKeepsThePlatformsPath(unittest.TestCase):

    @unittest.skipUnless(POSIX, "the POSIX rendering")
    def test_win_leaves_a_posix_path_absolute(self):
        rendered = paths.win(Path("/tmp/run/wt/pi-1"))
        self.assertEqual(rendered, "/tmp/run/wt/pi-1")
        self.assertTrue(os.path.isabs(rendered))

    @unittest.skipIf(POSIX, "the Windows rendering")
    def test_win_still_writes_backslashes_on_windows(self):
        self.assertEqual(paths.win("C:/Users/<user>/run"),
                         "C:\\Users\\<user>\\run")


class ThePositionBlockNamesARealWorktree(TempCase):

    @unittest.skipUnless(POSIX, "the POSIX rendering")
    def test_the_worktree_line_is_a_path_that_exists(self):
        worktree = (self.tmp / "wt" / "a").resolve()
        worktree.mkdir(parents=True)
        self.assertTrue(Path(paths.win(worktree)).is_dir(),
                        f"{paths.win(worktree)!r} names no directory")


if __name__ == "__main__":
    unittest.main()

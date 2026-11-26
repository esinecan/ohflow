"""Defect 66: `ohflow revert` ran `cmd /c REVERT.cmd`, a Windows batch file.

The engine wrote `REVERT.cmd` on every platform and the verb ran it through
`cmd`. Off Windows the verb ended in `FileNotFoundError: 'cmd'`, and status and
the exit report named a script no Mac operator could run.

The verb now removes the worktrees and their branches in Python, through git,
on every platform. The engine writes `revert.json`, the list of what to remove,
and the teardown every surface prints is the `revert --run <dir>` command.

Off Windows the shared `node_modules` is a symbolic link, made without
`cmd /c mklink`. The link comes out before the worktree, and the target stays.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import subprocess
import unittest
from pathlib import Path

from ohflow import cli, live, worktree as ohwt
from ohflow.paths import python_cmd
from ohflow.workflow import WorktreeSpec
from support import TempCase, git_repo

POSIX = os.name != "nt"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          text=True).stdout


def _revert(run_dir: Path) -> tuple[int, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.cmd_revert(argparse.Namespace(run=str(run_dir)))
    return code, out.getvalue() + err.getvalue()


class TheRevertVerbRemovesARealWorktree(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.repo = git_repo(self.tmp / "repo")
        self.run = self.tmp / "run"
        self.run.mkdir()

    def _spec(self, name: str, **kw) -> WorktreeSpec:
        return WorktreeSpec(name=name, path=self.tmp / "wt" / name,
                            branch=f"ohflow/{name}", base="main", **kw)

    def test_the_worktree_and_its_branch_are_gone(self):
        spec = self._spec("a", node_modules_mode="none")
        ohwt.create(self.repo, spec, created_by="test")
        ohwt.write_revert_plan(self.run, self.repo, [spec])
        self.assertTrue(Path(spec.path).exists())
        self.assertIn("ohflow/a", _git(self.repo, "branch", "--list"))

        code, text = _revert(self.run)

        self.assertEqual(code, 0, text)
        self.assertFalse(Path(spec.path).exists())
        self.assertNotIn("ohflow/a", _git(self.repo, "branch", "--list"))
        self.assertNotIn(str(spec.path), _git(self.repo, "worktree", "list"))

    def test_a_worktree_that_was_never_created_is_no_failure(self):
        made = self._spec("made", node_modules_mode="none")
        never = self._spec("never", node_modules_mode="none")
        ohwt.create(self.repo, made, created_by="test")
        ohwt.write_revert_plan(self.run, self.repo, [made, never])

        code, text = _revert(self.run)

        self.assertEqual(code, 0, text)
        self.assertFalse(Path(made.path).exists())

    @unittest.skipUnless(POSIX, "off Windows the shared node_modules is a symlink")
    def test_the_node_modules_link_comes_out_and_its_target_stays(self):
        shared = self.repo / "node_modules"
        shared.mkdir()
        (shared / ".package-lock.json").write_text("{}", encoding="utf-8")
        (shared / "kept.txt").write_text("kept", encoding="utf-8")
        spec = self._spec("j")
        ohwt.create(self.repo, spec, created_by="test")
        link = Path(spec.path) / "node_modules"
        self.assertTrue(link.is_symlink())
        self.assertTrue((link / "kept.txt").exists())
        ohwt.write_revert_plan(self.run, self.repo, [spec])

        code, text = _revert(self.run)

        self.assertEqual(code, 0, text)
        self.assertFalse(Path(spec.path).exists())
        self.assertTrue((shared / "kept.txt").exists())
        self.assertIn("sentinel present", text)

    @unittest.skipUnless(POSIX, "off Windows the shared node_modules is a symlink")
    def test_a_missing_sentinel_fails_the_verb(self):
        shared = self.repo / "node_modules"
        shared.mkdir()
        (shared / ".package-lock.json").write_text("{}", encoding="utf-8")
        spec = self._spec("s")
        ohwt.create(self.repo, spec, created_by="test")
        ohwt.write_revert_plan(self.run, self.repo, [spec])
        (shared / ".package-lock.json").unlink()

        code, text = _revert(self.run)

        self.assertNotEqual(code, 0)
        self.assertIn("SENTINEL MISSING", text)

    def test_a_run_without_a_revert_plan_fails_without_a_traceback(self):
        code, text = _revert(self.run)
        self.assertNotEqual(code, 0)
        self.assertIn("revert.json", text)

    @unittest.skipUnless(POSIX, "an old run's REVERT.cmd is a Windows batch file")
    def test_an_old_run_with_only_a_batch_file_is_refused_in_words(self):
        (self.run / "REVERT.cmd").write_text("@echo off\r\n", encoding="utf-8")
        code, text = _revert(self.run)
        self.assertNotEqual(code, 0)
        self.assertIn("REVERT.cmd", text)
        self.assertIn("git worktree remove", text)


class EverySurfaceNamesTheRevertCommand(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.run = self.tmp / "run"
        self.run.mkdir()

    def test_the_command_is_the_verb_with_this_interpreter(self):
        command = live.revert_command(self.run)
        self.assertIsNone(command)
        ohwt.write_revert_plan(self.run, self.tmp / "repo", [])
        command = live.revert_command(self.run)
        self.assertTrue(command.startswith(
            f"{python_cmd()} -m ohflow.cli revert --run "), command)
        self.assertIn(self.run.name, command)

    def test_the_plan_lists_what_the_verb_needs(self):
        spec = WorktreeSpec(name="w", path=self.tmp / "wt", branch="b",
                            base="main", node_modules_mode="none")
        ohwt.write_revert_plan(self.run, self.tmp / "repo", [spec])
        plan = json.loads((self.run / "revert.json").read_text(encoding="utf-8"))
        self.assertEqual(plan["repo"], str(self.tmp / "repo"))
        self.assertEqual(plan["worktrees"][0]["branch"], "b")
        self.assertEqual(plan["worktrees"][0]["node_modules_mode"], "none")


if __name__ == "__main__":
    unittest.main()

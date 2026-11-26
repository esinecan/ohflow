"""Defect 63: a suite run could change the source checkout and still pass.

On macOS on 2026-11-15 the suite's fake agents made 11 commits in the source
checkout and left 12 directories in it (defect 59). The run reported only the
gate failures that followed; nothing said that the checkout itself had moved.

`run_tests.py` now reads the checkout's HEAD and its `git status` before and
after a run. A commit, or a path that is new in the status, fails the run and
is named. A checkout that was already dirty is no fault: only what the run
added counts.
"""

from __future__ import annotations

import unittest

import run_tests
from support import TempCase, git_repo


class TheRunnerNoticesAChangedCheckout(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.repo = git_repo(self.tmp / "checkout")

    def test_an_untouched_checkout_reports_nothing(self):
        before = run_tests.checkout_state(self.repo)
        self.assertEqual(
            run_tests.checkout_changes(before,
                                       run_tests.checkout_state(self.repo)),
            [])

    def test_a_new_file_is_named(self):
        before = run_tests.checkout_state(self.repo)
        (self.repo / "stray.md").write_text("x\n", encoding="utf-8")
        changes = run_tests.checkout_changes(
            before, run_tests.checkout_state(self.repo))
        self.assertEqual(len(changes), 1, changes)
        self.assertIn("stray.md", changes[0])

    def test_a_commit_is_named(self):
        import subprocess
        before = run_tests.checkout_state(self.repo)
        (self.repo / "stray.md").write_text("x\n", encoding="utf-8")
        for argv in (["git", "add", "stray.md"],
                     ["git", "-c", "user.name=t", "-c", "user.email=t@localhost",
                      "commit", "-qm", "stray"]):
            subprocess.run(argv, cwd=str(self.repo), check=True,
                           capture_output=True)
        changes = run_tests.checkout_changes(
            before, run_tests.checkout_state(self.repo))
        self.assertTrue(any("HEAD moved" in line for line in changes), changes)

    def test_dirt_from_before_the_run_is_no_fault(self):
        (self.repo / "mine.md").write_text("x\n", encoding="utf-8")
        before = run_tests.checkout_state(self.repo)
        self.assertEqual(
            run_tests.checkout_changes(before,
                                       run_tests.checkout_state(self.repo)),
            [])

    def test_a_folder_that_is_no_checkout_has_no_state(self):
        self.assertIsNone(run_tests.checkout_state(self.tmp / "no-repo"))
        self.assertEqual(run_tests.checkout_changes(None, None), [])


if __name__ == "__main__":
    unittest.main()

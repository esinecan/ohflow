"""remote_git: the branch that carries a step between this machine and the box.

`push_start` refuses a dirty tree naming the paths and a branch outside the
`ohflow/` prefix, `fetch_result` moves only what descends from the start
commit - with one message for a branch that moved sideways and another for a
worktree that moved on its own - and `delete_branch` removes the branch once
its commit is fetched. All against a real repository with a real bare origin,
because the module under test is git plumbing.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from ohflow import remote_git
from support import TempCase, git_repo

WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class RemoteGit(TempCase):

    def setUp(self):
        super().setUp()
        self.origin = self.tmp / "origin.git"
        subprocess.run(["git", "init", "--bare", "-b", "main", str(self.origin)],
                       check=True, capture_output=True, creationflags=WINDOW)
        self.repo = git_repo(self.tmp / "repo")
        self.g(self.repo, "remote", "add", "origin", self.origin.as_posix())
        self.g(self.repo, "push", "origin", "main")
        self.other = self._clone("other")
        self.branch = "ohflow/durable/test-1"

    def g(self, cwd: Path, *args: str) -> str:
        done = subprocess.run(
            ["git", "-c", "user.name=ohflow tests",
             "-c", "user.email=tests@localhost", *args],
            cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
            errors="replace", creationflags=WINDOW)
        assert done.returncode == 0, (args, done.stderr, done.stdout)
        return done.stdout.strip()

    def _clone(self, name: str) -> Path:
        path = self.tmp / name
        self.g(self.tmp, "clone", self.origin.as_posix(), name)
        return path

    def _commit(self, repo: Path, name: str) -> str:
        (repo / name).write_text(f"{name}\n", encoding="utf-8")
        self.g(repo, "add", name)
        self.g(repo, "commit", "-m", f"commit {name}")
        return self.g(repo, "rev-parse", "HEAD")

    def test_remote_url_names_the_worktree_that_has_no_origin(self):
        bare = git_repo(self.tmp / "no-origin")
        with self.assertRaises(ValueError) as caught:
            remote_git.remote_url(bare)
        self.assertIn("works from the project's own remote", str(caught.exception))
        self.assertIn("has no origin", str(caught.exception))
        self.assertIn(str(bare), str(caught.exception))
        self.assertEqual(remote_git.remote_url(self.repo), self.origin.as_posix())

    def test_push_start_refuses_a_dirty_tree_and_names_the_paths(self):
        (self.repo / "uncommitted.txt").write_text("work\n", encoding="utf-8")
        (self.repo / "tracked.txt").write_text("edited\n", encoding="utf-8")
        self.g(self.repo, "add", "tracked.txt")
        with self.assertRaises(ValueError) as caught:
            remote_git.push_start(self.repo, self.branch)
        self.assertIn("uncommitted.txt", str(caught.exception))
        self.assertIn("tracked.txt", str(caught.exception))
        self.assertIn("would not reach the other machine", str(caught.exception))
        # Nothing was pushed by the refused call.
        self.g(self.repo, "fetch", "origin")
        self.assertEqual(self.g(self.repo, "rev-parse", "origin/main"),
                         self.g(self.repo, "rev-parse", "HEAD"))

    def test_push_start_refuses_a_branch_outside_the_ohflow_prefix(self):
        with self.assertRaises(ValueError) as caught:
            remote_git.push_start(self.repo, "feature/durable-test-1")
        self.assertIn("must sit under ohflow/", str(caught.exception))
        self.assertIn("feature/durable-test-1", str(caught.exception))
        # Nothing was pushed by the refused call.
        self.g(self.repo, "fetch", "origin")
        self.assertEqual(self.g(self.repo, "rev-parse", "origin/main"),
                         self.g(self.repo, "rev-parse", "HEAD"))

    def test_push_start_pushes_the_head_and_returns_its_sha(self):
        sha = remote_git.push_start(self.repo, self.branch)
        self.assertEqual(sha, self.g(self.repo, "rev-parse", "HEAD"))
        listed = self.g(self.tmp, "ls-remote", self.origin.as_posix(),
                        f"refs/heads/{self.branch}")
        self.assertEqual(listed.split()[0], sha)

    def test_fetch_result_fast_forwards_to_the_fetched_commit(self):
        start = remote_git.push_start(self.repo, self.branch)
        theirs = self._commit(self.other, "theirs")
        self.g(self.other, "push", "--force", "origin",
               f"HEAD:refs/heads/{self.branch}")
        moved = remote_git.fetch_result(self.repo, self.branch, start)
        self.assertEqual(moved, theirs)
        self.assertEqual(self.g(self.repo, "rev-parse", "HEAD"), theirs)

    def test_fetch_result_accepts_a_worktree_that_already_holds_the_commit(self):
        start = remote_git.push_start(self.repo, self.branch)
        theirs = self._commit(self.other, "theirs")
        self.g(self.other, "push", "--force", "origin",
               f"HEAD:refs/heads/{self.branch}")
        self.g(self.repo, "fetch", "origin", f"refs/heads/{self.branch}")
        self.g(self.repo, "merge", "--ff-only", "FETCH_HEAD")
        again = remote_git.fetch_result(self.repo, self.branch, start)
        self.assertEqual(again, theirs)

    def test_fetch_result_refuses_a_commit_that_does_not_descend(self):
        start = remote_git.push_start(self.repo, self.branch)
        # An amended start: same tree, different history, so nothing descends.
        self.g(self.other, "commit", "--amend", "--no-edit", "-m", "sideways")
        sideways = self.g(self.other, "rev-parse", "HEAD")
        self.g(self.other, "push", "--force", "origin",
               f"HEAD:refs/heads/{self.branch}")
        with self.assertRaises(ValueError) as caught:
            remote_git.fetch_result(self.repo, self.branch, start)
        self.assertIn("does not descend", str(caught.exception))
        self.assertIn(sideways, str(caught.exception))
        self.assertIn(start, str(caught.exception))
        self.assertNotIn("moved on its own", str(caught.exception))
        self.assertEqual(self.g(self.repo, "rev-parse", "HEAD"), start)

    def test_fetch_result_refuses_a_worktree_that_moved_on_its_own(self):
        start = remote_git.push_start(self.repo, self.branch)
        ours = self._commit(self.repo, "ours")
        theirs = self._commit(self.other, "theirs")
        self.g(self.other, "push", "--force", "origin",
               f"HEAD:refs/heads/{self.branch}")
        with self.assertRaises(ValueError) as caught:
            remote_git.fetch_result(self.repo, self.branch, start)
        # The worktree moved; the fetched commit itself may descend just fine,
        # so the message names the worktree and never claims non-descent.
        self.assertIn("moved on its own", str(caught.exception))
        self.assertNotIn("does not descend", str(caught.exception))
        for sha in (ours, theirs, start):
            self.assertIn(sha, str(caught.exception))

    def test_delete_branch_removes_it_from_origin(self):
        remote_git.push_start(self.repo, self.branch)
        self.assertTrue(remote_git.delete_branch(self.repo, self.branch))
        listed = self.g(self.tmp, "ls-remote", self.origin.as_posix(),
                        f"refs/heads/{self.branch}")
        self.assertEqual(listed, "")

    def test_delete_branch_returns_false_when_origin_refuses(self):
        # A branch that is not there: the delete fails, the caller records it.
        self.assertFalse(remote_git.delete_branch(self.repo, self.branch))

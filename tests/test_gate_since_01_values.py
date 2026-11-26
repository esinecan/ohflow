"""m5: the checks that read git history take `since`.

Before: every one measured from the worktree's creation commit. A step that
started later, or a consolidator that works after the merges, could not say
"my own commits" and had to hand-roll a shell check that named a merge commit.
That shell check failed on a repository with no merge commit.

Now `since` is `base` (the default, today's behaviour), `step_start` (HEAD when
the attempt began), `last_merge` (the newest merge past the base) or a ref name.

The scratch repository, drawn oldest first:

    A  base                       (base_sha)
    B  early   a.txt              (start_sha; its message carries a trailer)
    S  side    side.txt           (tag v1; on a branch made from A)
    M  merge of side into main
    C  late    after.txt
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ohflow.gates import (REGISTRY, GateContext, commits_past_base,
                          no_ai_attribution, ownership, paths_untouched)
from support import TempCase, git_repo

TRAILER = "Co-Authored-By: Claude <noreply@anthropic.com>"


def git(repo: Path, *args: str) -> str:
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@localhost",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@localhost")
    done = subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True, env=env,
                          creationflags=getattr(subprocess,
                                                "CREATE_NO_WINDOW", 0))
    return done.stdout.strip()


def commit(repo: Path, name: str, message: str) -> str:
    (repo / name).write_text(name, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "commit", "-m", message)
    return git(repo, "rev-parse", "HEAD")


class SinceOnARepoWithAMerge(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.repo = git_repo(self.tmp / "repo")
        self.base = git(self.repo, "rev-parse", "HEAD")
        git(self.repo, "checkout", "-q", "-b", "side")
        commit(self.repo, "side.txt", "side")
        git(self.repo, "tag", "v1")
        git(self.repo, "checkout", "-q", "main")
        self.early = commit(self.repo, "a.txt", f"early\n\n{TRAILER}")
        git(self.repo, "merge", "--no-ff", "-q", "side", "-m", "merge side")
        self.merge = git(self.repo, "rev-parse", "HEAD")
        commit(self.repo, "after.txt", "late")

    def ctx(self, **kw) -> GateContext:
        return GateContext(
            coord="01.p/01.s", repo=self.repo, worktree=self.repo,
            base_sha=self.base, base_ref="main", attempt_dir=self.tmp / "step",
            log_dir=self.tmp / "step" / "logs", start_sha=self.early, **kw)

    def test_the_default_measures_from_the_base(self):
        r = commits_past_base(self.ctx(), min=1)
        self.assertEqual(r.observed, 4)
        r = ownership(self.ctx(), allowed=["after.txt"])
        self.assertFalse(r.passed)
        self.assertEqual(sorted(r.observed), ["a.txt", "side.txt"])

    def test_step_start_counts_only_what_this_attempt_added(self):
        r = commits_past_base(self.ctx(), min=1, since="step_start")
        self.assertEqual(r.observed, 3)
        r = ownership(self.ctx(), allowed=["side.txt", "after.txt"],
                      since="step_start")
        self.assertTrue(r.passed, r)
        self.assertFalse(no_ai_attribution(self.ctx(), since="base").passed)
        self.assertTrue(no_ai_attribution(self.ctx(),
                                          since="step_start").passed)

    def test_last_merge_measures_from_the_newest_merge_commit(self):
        r = commits_past_base(self.ctx(), min=1, since="last_merge")
        self.assertEqual(r.observed, 1)
        self.assertTrue(ownership(self.ctx(), allowed=["after.txt"],
                                  since="last_merge").passed)
        self.assertTrue(paths_untouched(self.ctx(), globs=["a.txt"],
                                        since="last_merge").passed)
        self.assertFalse(paths_untouched(self.ctx(), globs=["a.txt"]).passed)

    def test_a_ref_name_measures_from_that_ref(self):
        r = commits_past_base(self.ctx(), min=1, since="v1")
        self.assertEqual(r.observed, 3)
        r = ownership(self.ctx(), allowed=["a.txt", "after.txt"], since="v1")
        self.assertTrue(r.passed, r)

    def test_a_ref_that_does_not_resolve_fails_closed(self):
        r = commits_past_base(self.ctx(), min=0, since="no-such-ref")
        self.assertFalse(r.passed)
        self.assertEqual(r.observed["git_exit"], 128)

    def test_a_since_that_is_not_a_ref_name_is_refused(self):
        r = ownership(self.ctx(), allowed=[], since="v1; rm -rf x")
        self.assertFalse(r.passed)
        self.assertIn("since is", r.detail)

    def test_the_position_block_names_the_starting_point(self):
        text = REGISTRY["ownership"].describe(
            {"allowed": ["x"], "since": "last_merge"})
        self.assertIn("the last merge..HEAD", text)
        self.assertIn("base..HEAD", REGISTRY["ownership"].describe({}))
        self.assertIn("past the step's start", REGISTRY[
            "no_ai_attribution"].describe({"since": "step_start"}))


class SinceOnARepoWithNoMerge(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.repo = git_repo(self.tmp / "repo")
        self.base = git(self.repo, "rev-parse", "HEAD")
        commit(self.repo, "one.txt", "one")

    def ctx(self, start_sha: str = "") -> GateContext:
        return GateContext(
            coord="01.p/01.s", repo=self.repo, worktree=self.repo,
            base_sha=self.base, base_ref="main", attempt_dir=self.tmp / "step",
            log_dir=self.tmp / "step" / "logs", start_sha=start_sha)

    def test_last_merge_with_no_merge_falls_back_to_the_base(self):
        r = commits_past_base(self.ctx(), min=1, since="last_merge")
        self.assertTrue(r.passed, r)
        self.assertEqual(r.observed, 1)
        self.assertTrue(ownership(self.ctx(), allowed=["one.txt"],
                                  since="last_merge").passed)

    def test_step_start_with_no_recorded_start_fails_closed(self):
        r = commits_past_base(self.ctx(), min=0, since="step_start")
        self.assertFalse(r.passed)
        self.assertIn("no worktree", r.detail)

    def test_a_merge_older_than_the_base_is_not_the_last_merge(self):
        git(self.repo, "checkout", "-q", "-b", "old")
        commit(self.repo, "old.txt", "old")
        git(self.repo, "checkout", "-q", "main")
        git(self.repo, "merge", "--no-ff", "-q", "old", "-m", "older merge")
        base = git(self.repo, "rev-parse", "HEAD")
        commit(self.repo, "new.txt", "new")
        ctx = self.ctx()
        ctx.base_sha = base
        r = commits_past_base(ctx, min=1, since="last_merge")
        self.assertEqual(r.observed, 1)
        self.assertTrue(ownership(ctx, allowed=["new.txt"],
                                  since="last_merge").passed)


if __name__ == "__main__":
    import unittest
    unittest.main()

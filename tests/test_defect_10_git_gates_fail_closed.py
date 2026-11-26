"""Defect 10: a gate check that cannot read the tree used to approve it.

What went wrong. Five checks in `ohflow.gates` ran a git command and read only
its stdout. When git failed it wrote nothing to stdout and exited 128, and the
checks read that silence as good news:

    ownership          no strays       -> passed
    tree_clean         clean           -> passed
    paths_untouched    no hits         -> passed
    no_ai_attribution  no attribution  -> passed
    commits_past_base  zero commits    -> passed, but only when min == 0

`no_ai_attribution` is one of the two checks `workflow.FORBIDDEN_RETRY_ON` protects,
so a bad base commit let an attributed commit through the check that exists to
stop it.

The evidence is `thread1/oracle-before.json`, recorded on 2026-09-18 by
`thread2/oracle.py` against this package before the fix: `ownership` with the
base `invalid-sha` returned `passed: true, observed: "none"` while
`git diff --name-only invalid-sha..HEAD` exited 128, and `tree_clean` outside a
repository returned `passed: true, observed: "clean"` while
`git status --porcelain` exited 128.

What is asserted here. Every one of the five checks fails when its git command
fails, and says the exit code. Two positive controls hold the line in the
other direction: the same five checks still pass on a healthy repository, and a
step that declares no worktree still passes, because git reads an empty side of
a range as HEAD and exits 0.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from ohflow.gates import (GateContext, commits_past_base, no_ai_attribution,
                          ownership, paths_untouched, tree_clean)
from support import TempCase, git_repo

#: The base the oracle used. It resolves to nothing, which is the point.
INVALID_BASE = "invalid-sha"


class GitRefusesAndTheCheckMustRefuseToo(TempCase):
    """The five checks, each given a tree its git command cannot read."""

    def setUp(self) -> None:
        super().setUp()
        self.repo = git_repo(self.tmp / "repo")
        self.not_repo = self.tmp / "not-a-repo"
        self.not_repo.mkdir(parents=True, exist_ok=True)

    def ctx(self, *, worktree: Path, base_sha: str) -> GateContext:
        return GateContext(coord="01.p/01.probe", repo=self.repo,
                           worktree=worktree, base_sha=base_sha,
                           base_ref="main", attempt_dir=self.tmp / "step",
                           log_dir=self.tmp / "step" / "logs")

    def assert_refused(self, result, *, name: str) -> None:
        self.assertFalse(
            result.passed,
            f"{name} approved a tree its git command could not read")
        self.assertIsInstance(result.observed, dict)
        self.assertEqual(result.observed.get("git_exit"), 128,
                         "the check must record the exit code it saw")
        self.assertTrue(result.detail and "exited 128" in result.detail,
                        "the detail must name the failure, not stay silent")

    # ---- the two the oracle observed directly

    def test_ownership_refuses_an_invalid_base(self):
        ctx = self.ctx(worktree=self.repo, base_sha=INVALID_BASE)
        self.assert_refused(ownership(ctx, allowed=[]), name="ownership")

    def test_tree_clean_refuses_a_directory_that_is_not_a_repository(self):
        ctx = self.ctx(worktree=self.not_repo, base_sha="HEAD")
        self.assert_refused(tree_clean(ctx), name="tree_clean")

    # ---- the three with the same shape

    def test_no_ai_attribution_refuses_an_invalid_base(self):
        """The clan rule rests on this check, so its silence was the worst."""
        ctx = self.ctx(worktree=self.repo, base_sha=INVALID_BASE)
        self.assert_refused(no_ai_attribution(ctx), name="no_ai_attribution")

    def test_paths_untouched_refuses_an_invalid_base(self):
        ctx = self.ctx(worktree=self.repo, base_sha=INVALID_BASE)
        self.assert_refused(paths_untouched(ctx, globs=["package.json"]),
                            name="paths_untouched")

    def test_commits_past_base_refuses_an_invalid_base_even_with_min_zero(self):
        """`min=1` hid this one: a failed git call reads as zero commits and
        fails closed by accident. `min=0` is where it showed."""
        ctx = self.ctx(worktree=self.repo, base_sha=INVALID_BASE)
        self.assert_refused(commits_past_base(ctx, min=0),
                            name="commits_past_base")

    def test_the_evidence_path_points_at_the_log_that_proves_it(self):
        ctx = self.ctx(worktree=self.repo, base_sha=INVALID_BASE)
        result = ownership(ctx, allowed=[])
        self.assertTrue(result.evidence_path,
                        "a refusal must point at the log that proves it")
        self.assertTrue(Path(result.evidence_path).exists())


class AHealthyTreeStillPasses(TempCase):
    """The fix must not have turned every check into a refusal."""

    def setUp(self) -> None:
        super().setUp()
        self.repo = git_repo(self.tmp / "repo")
        self.base = subprocess.run(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True).stdout.strip()

    def ctx(self, base_sha: str) -> GateContext:
        return GateContext(coord="01.p/01.probe", repo=self.repo,
                           worktree=self.repo, base_sha=base_sha,
                           base_ref="main", attempt_dir=self.tmp / "step",
                           log_dir=self.tmp / "step" / "logs")

    def test_every_check_passes_against_a_real_base(self):
        ctx = self.ctx(self.base)
        for result in (tree_clean(ctx),
                       ownership(ctx, allowed=[]),
                       paths_untouched(ctx, globs=["package.json"]),
                       no_ai_attribution(ctx),
                       commits_past_base(ctx, min=0)):
            self.assertTrue(result.passed,
                            f"{result.name} refused a healthy tree: "
                            f"{result.observed!r} {result.detail!r}")

    def test_a_step_with_no_worktree_still_passes(self):
        """A step that declares no worktree has `base_sha == ""`, so the range
        is `..HEAD`, which git reads as `HEAD..HEAD`. Measured 2026-09-18:
        both commands exit 0. The fix therefore adds no failure here, and this
        test says so rather than leaving it assumed."""
        ctx = self.ctx("")
        for result in (ownership(ctx, allowed=[]), no_ai_attribution(ctx)):
            self.assertTrue(result.passed,
                            f"{result.name} refused an empty base range: "
                            f"{result.observed!r}")

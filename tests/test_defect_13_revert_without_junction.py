"""D-13: the revert checks a sentinel only for junction worktrees."""

from ohflow.workflow import WorktreeSpec
from ohflow import worktree as ohwt
from support import TempCase


class RevertWithoutAJunctionNeedsNoSentinel(TempCase):

    def test_none_mode_has_no_node_modules_sentinel_check(self):
        spec = WorktreeSpec(name="w", path=self.tmp / "wt", branch="b",
                            base="main", node_modules_mode="none")
        run = self.tmp / "run"
        run.mkdir()
        ohwt.write_revert_plan(run, self.tmp / "repo", [spec])
        plan = ohwt.read_revert_plan(run)
        self.assertIsNone(plan["worktrees"][0]["sentinel"])
        ok, lines = ohwt.revert(plan)
        self.assertTrue(ok, lines)
        self.assertNotIn("SENTINEL", "\n".join(lines).upper())

    def test_junction_mode_names_its_sentinel(self):
        spec = WorktreeSpec(name="w", path=self.tmp / "wt", branch="b",
                            base="main")
        run = self.tmp / "run"
        run.mkdir()
        ohwt.write_revert_plan(run, self.tmp / "repo", [spec])
        sentinel = ohwt.read_revert_plan(run)["worktrees"][0]["sentinel"]
        self.assertEqual(sentinel, str(self.tmp / "repo" / "node_modules"
                                       / ".package-lock.json"))

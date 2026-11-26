"""D-25: a worktree is created when its first phase starts, after its base."""

from __future__ import annotations

from ohflow.engine import Engine
from ohflow.run_log import RunLog
from ohflow.workflow import (CheckSpec, GateSpec, Phase, Workflow, Step, WorktreeSpec)
from support import TempCase, git_repo


EXIT_ZERO = GateSpec(checks=(CheckSpec(
    "command_exit", {"cmd": "git status --porcelain", "expect": 0}),))


class LazyWorktreeCreation(TempCase):

    def test_later_phase_can_use_a_branch_created_by_an_earlier_phase(self):
        repo = git_repo(self.tmp / "repo")
        wt = self.tmp / "late-worktree"
        workflow = Workflow(
            name="lazy-worktree",
            repo=repo,
            base_branch="main",
            baseline_cmd=None,
            max_parallel=1,
            transient_backoff_s=0,
            worktrees=(WorktreeSpec(
                name="late", path=wt, branch="late-work",
                base="built-base", node_modules_mode="none"),),
            phases=(
                Phase(name="Build base", on_step_failure="abort",
                      steps=(Step(id="build-base", kind="command",
                                  command="git branch built-base",
                                  gate=EXIT_ZERO),)),
                Phase(name="Use base", on_step_failure="abort",
                      steps=(Step(id="use-base", kind="command",
                                  worktree="late",
                                  command="git rev-parse --verify built-base",
                                  gate=EXIT_ZERO),)),
            ),
        )
        run_dir = self.run_dir()
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False).run()

        state = RunLog.replay(run_dir)
        first = state.steps["01.build-base/01.build-base"]
        self.assertEqual(first.status, "passed", first.error)
        self.assertEqual(state.steps["02.use-base/01.use-base"].status,
                         "passed")
        self.assertTrue(wt.exists())
        self.assertIn("late", state.meta["worktrees"])

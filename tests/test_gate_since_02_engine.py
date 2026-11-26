"""m5: the engine records the commit each attempt starts from.

Two steps share one worktree. The first commits. The second commits nothing.
Measured from the base, both pass `commits_past_base`. Measured from the step's
start, only the first one passes.
"""

from __future__ import annotations

from ohflow.engine import Engine
from ohflow.run_log import RunLog
from ohflow.workflow import CheckSpec, GateSpec, Phase, Workflow, Step, WorktreeSpec
from support import TempCase, git_repo

COMMIT = ("git -c user.name=t -c user.email=t@localhost "
          "commit --allow-empty -m work")


def gate(since: str) -> GateSpec:
    return GateSpec(checks=(CheckSpec(
        "commits_past_base", {"min": 1, "since": since}),))


class TheEngineRecordsEachAttemptsStart(TempCase):

    def run_workflow(self, since: str) -> dict[str, str]:
        repo = git_repo(self.tmp / "repo")
        workflow = Workflow(
            name="since-step-start", repo=repo, base_branch="main",
            baseline_cmd=None, max_parallel=1, transient_backoff_s=0,
            worktrees=(WorktreeSpec(name="w", path=self.tmp / "wt",
                                    branch="since-work", base="main",
                                    node_modules_mode="none"),),
            phases=(
                Phase(name="Commit", on_step_failure="quarantine", steps=(
                    Step(id="commits", kind="command", worktree="w",
                         command=COMMIT, gate=gate(since)),)),
                Phase(name="Idle", on_step_failure="quarantine", steps=(
                    Step(id="idles", kind="command", worktree="w",
                         command="git status --porcelain",
                         gate=gate(since)),)),
            ),
        )
        run_dir = self.run_dir()
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False).run()
        state = RunLog.replay(run_dir)
        return {c: r.status for c, r in state.steps.items()}

    def test_since_base_counts_the_earlier_step_commit(self):
        got = self.run_workflow("base")
        self.assertEqual(got["01.commit/01.commits"], "passed")
        self.assertEqual(got["02.idle/01.idles"], "passed")

    def test_since_step_start_counts_only_this_steps_own_commits(self):
        got = self.run_workflow("step_start")
        self.assertEqual(got["01.commit/01.commits"], "passed")
        self.assertNotEqual(got["02.idle/01.idles"], "passed")


if __name__ == "__main__":
    import unittest
    unittest.main()

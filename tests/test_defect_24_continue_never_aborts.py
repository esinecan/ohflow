"""D-24: continue settles a failed phase and still starts later phases."""

from __future__ import annotations

from ohflow.engine import Engine
from ohflow.run_log import RunLog
from ohflow.workflow import Phase
from support import (FakeHarnessExecutor, TempCase, AgentScript, git_repo,
                     install_fake_harness_executor, simple_workflow, stub_preflight,
                     agent_step)


class ContinueNeverAborts(TempCase):

    def test_min_success_all_failure_does_not_stop_the_next_phase(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        harness_executor = install_fake_harness_executor(self, FakeHarnessExecutor(scripts={
            "01.bad": AgentScript(final_text="not done\n"),
            "01.after": AgentScript(final_text="DONE\n"),
        }))
        workflow = simple_workflow(repo, phases=(
            Phase(name="May fail", steps=(agent_step("bad"),),
                  on_step_failure="continue", min_success="all"),
            Phase(name="After", steps=(agent_step("after"),),
                  on_step_failure="continue", min_success="all"),
        ))
        run_dir = self.run_dir()
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors).run()

        state = RunLog.replay(run_dir)
        self.assertEqual(state.phases["01.may-fail"]["status"], "failed")
        self.assertEqual(state.steps["02.after/01.after"].status, "passed")
        self.assertTrue(any(c.endswith("after") for c in harness_executor.launched))

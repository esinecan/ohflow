"""D-32: each attempt emits one finish; replay still accepts old duplicates."""

from __future__ import annotations

from dataclasses import replace

from ohflow.engine import Engine
from ohflow.run_log import RunLog
from ohflow.workflow import Phase, RetryPolicy
from support import (FakeHarnessExecutor, TempCase, AgentScript, git_repo,
                     install_fake_harness_executor, read_run_log, simple_workflow,
                     stub_preflight, agent_step)


class OneFinishPerAttempt(TempCase):

    def test_retry_decisions_do_not_duplicate_attempt_finished(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript(sequence=[
            {"final_text": "not done\n"}, {"final_text": "DONE\n"},
        ])))
        step = replace(agent_step("flaky"),
                       retry=RetryPolicy(max=1,
                                         on=("gate:final_message_matches",)))
        workflow = simple_workflow(repo, phases=(Phase(
            name="Only", steps=(step,), on_step_failure="continue",
            min_success="all"),))
        run_dir = self.run_dir()
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors).run()

        finishes = [r for r in read_run_log(run_dir)
                    if r["event"] == "attempt_finished"
                    and r.get("coord") == "01.only/01.flaky"]
        self.assertEqual([r["attempt"] for r in finishes], [1, 2])

    def test_old_duplicate_finishes_replay_as_one_execution(self):
        run_dir = self.run_dir()
        run_log = RunLog(run_dir)
        run_log.append("run_started", payload={"run_id": run_dir.name,
                                                "workflow": "old"})
        run_log.append("attempt_started", coord="01.p/01.s", attempt=1,
                       payload={"step_id": "s", "fingerprint": "abc"})
        payload = {"status": "failed", "step_id": "s",
                   "fingerprint": "abc", "error": "old failure"}
        run_log.append("attempt_finished", coord="01.p/01.s", attempt=1,
                       payload=payload)
        run_log.append("attempt_finished", coord="01.p/01.s", attempt=1,
                       payload={**payload, "retry_decision": "old duplicate"})

        state = RunLog.replay(run_dir)
        executions = [e for e in state.executions if e.get("started")]
        self.assertEqual(len(executions), 1)
        self.assertEqual(executions[0]["retry_decision"], "old duplicate")

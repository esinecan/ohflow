"""D-22: an abort mark wins the race with a killed child's exit status."""

from __future__ import annotations

import threading

from ohflow import harness_executor as ohexecutor
from ohflow.engine import Engine
from ohflow.run_log import RunLog
from support import (FakeHarnessExecutor, TempCase, AgentScript, git_repo,
                     install_fake_harness_executor, simple_workflow, stub_preflight,
                     agent_step)


class AbortKillRace(TempCase):

    def test_killed_child_is_deferred_even_when_poll_reports_error(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        killed = threading.Event()
        victim_polling = threading.Event()

        class SignallingHarnessExecutor(FakeHarnessExecutor):
            def kill(self, handle):
                super().kill(handle)
                killed.set()

        def wait_for_victim_poll():
            self.assertTrue(victim_polling.wait(timeout=15),
                            "victim never reached its registered poll boundary")
            return None

        def wait_for_abort_kill():
            # Reaching on_poll means _run_agent has registered this handle,
            # so the abort policy's victim snapshot must include it.
            victim_polling.set()
            # Returning ERROR before the kill signal fabricates the very race
            # this test is meant to classify: under suite load the old two
            # second wait could expire first and make an ordinary agent error
            # look like an abort victim.  Block for the deterministic signal;
            # a missing signal is a test failure, not a synthetic child exit.
            self.assertTrue(killed.wait(timeout=15),
                            "abort kill signal did not arrive")
            return ohexecutor.ERROR

        harness_executor = install_fake_harness_executor(self, SignallingHarnessExecutor(
            scripts={
                "01.trigger": AgentScript(error="structural failure", final_text="",
                                             on_poll=wait_for_victim_poll),
                "02.victim": AgentScript(on_poll=wait_for_abort_kill,
                                           final_text=""),
            },
            gate_at=2, gate_timeout=15,
        ))
        workflow = simple_workflow(
            repo,
            steps=[agent_step("trigger"), agent_step("victim")],
            on_step_failure="abort", max_parallel=2,
        )
        run_dir = self.run_dir()
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors).run()

        victim = RunLog.replay(run_dir).steps["01.only-phase/02.victim"]
        self.assertEqual(victim.status, "deferred")
        self.assertTrue(victim.abort_victim)
        self.assertIn("01.only-phase/02.victim", harness_executor.killed)

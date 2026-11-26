"""D-23: a step whose earlier dependency did not pass is skipped."""

from __future__ import annotations

from ohflow.engine import Engine
from ohflow.fingerprint import fingerprint
from ohflow.run_log import RunLog
from ohflow.workflow import Phase
from support import (FakeHarnessExecutor, TempCase, AgentScript, git_repo,
                     install_fake_harness_executor, simple_workflow, stub_preflight,
                     agent_step)


class FailedDependenciesDoNotRun(TempCase):

    def test_quarantined_dependency_skips_its_consumer(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        harness_executor = install_fake_harness_executor(self, FakeHarnessExecutor(scripts={
            "01.owner": AgentScript(final_text="not done\n"),
            "01.consumer": AgentScript(final_text="DONE\n"),
        }))
        consumer = agent_step("consumer")
        from dataclasses import replace
        consumer = replace(consumer, depends_on=("owner",))
        workflow = simple_workflow(repo, phases=(
            Phase(name="Build", steps=(agent_step("owner"),),
                  on_step_failure="quarantine", min_success="all"),
            Phase(name="Consolidate", steps=(consumer,),
                  on_step_failure="continue", min_success="all"),
        ))
        run_dir = self.run_dir()
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors).run()

        state = RunLog.replay(run_dir)
        rec = state.steps["02.consolidate/01.consumer"]
        self.assertEqual(rec.status, "skipped")
        self.assertIn("owner", rec.error or "")
        self.assertFalse(any(c.endswith("consumer") for c in harness_executor.launched))

    def test_old_exclusion_does_not_block_newly_passed_dependency(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        harness_executor = install_fake_harness_executor(self, FakeHarnessExecutor(scripts={
            "01.consumer": AgentScript(final_text="DONE\n"),
        }))
        owner = agent_step("owner")
        consumer = agent_step("consumer")
        from dataclasses import replace
        consumer = replace(consumer, depends_on=("owner",))
        workflow = simple_workflow(repo, phases=(
            Phase(name="Build", steps=(owner,), min_success="all"),
            Phase(name="Consolidate", steps=(consumer,), min_success="all"),
        ))
        run_dir = self.run_dir()
        run_log = RunLog(run_dir)
        run_log.append("run_started", payload={
            "run_id": run_dir.name,
            "workflow": workflow.name,
            "meta": {"repo": str(repo), "base_branch": "main",
                     "base_sha": "current", "worktrees": {}},
        })
        current = fingerprint(workflow, RunLog.replay(run_dir), owner)
        owner_coord = "01.build/01.owner"
        run_log.append("work_excluded", coord=owner_coord, payload={
            "fingerprint": "OLD", "reason": "two earlier failures",
        })
        run_log.append("attempt_finished", coord=owner_coord, attempt=1, payload={
            "status": "passed", "fingerprint": current,
            "step_id": "owner", "kind": "agent", "wall_seconds": 0.0,
        })

        Engine(workflow, run_dir, run_id=run_dir.name, resume=True,
               verbose=False,
               harness_executors=self.harness_executors).run()

        state = RunLog.replay(run_dir)
        self.assertEqual(state.steps["02.consolidate/01.consumer"].status,
                         "passed")
        self.assertTrue(any(c.endswith("consumer") for c in harness_executor.launched))

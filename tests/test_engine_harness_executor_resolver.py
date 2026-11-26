"""The engine asks its own harness executor resolver for a harness executor, and the default is the registry.

Before: the engine called `worker.lane_for`, so a test had to replace a module
function to run a step without a process.
Now: `Engine(..., harness_executors=resolver)` takes the resolver as an argument. The
default is `harness_executors.harness_executor_for`.
"""

from __future__ import annotations

import unittest

from ohflow import harness_executors as ohexecutors
from ohflow.engine import Engine
from support import (FakeHarnessExecutor, TempCase, AgentScript, git_repo,
                     simple_workflow, stub_preflight, agent_step)


class EngineHarnessExecutorResolver(TempCase):
    def test_a_passed_resolver_supplies_the_harness_executor_for_each_step(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        harness_executor = FakeHarnessExecutor(default=AgentScript(final_text="DONE\n"))
        asked: list[str] = []

        def resolver(name: str):
            asked.append(name)
            return harness_executor

        run_dir = self.run_dir()
        summary = Engine(simple_workflow(repo), run_dir, run_id=run_dir.name,
                         verbose=False, harness_executors=resolver).run()
        self.assertEqual(summary["status"], "finished")
        self.assertEqual(asked, ["pi"])
        self.assertEqual(len(harness_executor.launched), 1)

    def test_without_a_resolver_the_engine_uses_the_registry(self):
        repo = git_repo(self.tmp / "repo")
        run_dir = self.run_dir()
        engine = Engine(simple_workflow(repo), run_dir, run_id=run_dir.name)
        self.assertIs(engine.harness_executors, ohexecutors.harness_executor_for)


if __name__ == "__main__":
    unittest.main()

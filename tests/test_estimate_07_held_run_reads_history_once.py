"""A held run reads the history once and estimates twice.

A held run estimates its plan while it waits, so the plan a person reads has
numbers, and again after `go`, because the reload may have changed the plan.
Reading a history over a large folder takes minutes, so the second estimate
uses the prior the first one read: `Prior.from_history` runs once per run.
The estimate itself is still made again, so an edit made while the run was
held is what `estimate.json` describes.

A pilot is the exception. It finishes a run between the two estimates, and
with `--history <runs root>` that run lies under the history, so the estimate
after `go` reads the history again and counts it.
"""

from __future__ import annotations

import json
import textwrap
import threading

from ohflow import estimate, rundir, supervisor
from ohflow.supervisor import RunOptions, run_workflow
from ohflow.workflow import load_workflow, validate
from pilot_support import start_in_thread, two_paths
from support import (AgentScript, FakeHarnessExecutor, TempCase, git_repo,
                     install_fake_harness_executor, quiet, stub_preflight)
from test_estimate_01_prior_from_history import attempt, summary
from test_hold_02_go_reloads_the_workflow import HOLD_WAIT_S, wait_for

WORKFLOW = '''
from pathlib import Path
from ohflow.workflow import (CheckSpec, GateSpec, ModelConfig, Phase, Workflow,
                             Step, AgentSpec)

MODEL = ModelConfig(model="fake/deterministic",
                    base_url="http://127.0.0.1:0/never-called",
                    api_key_env="OHFLOW_TEST_FAKE_KEY")
STEPS = %s


def step(name):
    return Step(id=name, kind="agent",
                gate=GateSpec(checks=(CheckSpec("final_message_matches",
                                                {"regex": "DONE"}),)),
                agent=AgentSpec(harness_executor="pi", role="role-a",
                                brief="do it", model=MODEL, max_iterations=3))


def build(args):
    return Workflow(name="held-estimate", repo=Path(args["repo"]),
                    base_branch="main", max_parallel=1, transient_backoff_s=0,
                    phases=(Phase(name="Only",
                                  steps=tuple(step(n) for n in STEPS)),))
'''


class AHeldRunReadsTheHistoryOnce(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript()))
        original = supervisor.HOLD_POLL_S
        supervisor.HOLD_POLL_S = 0.02
        self.addCleanup(setattr, supervisor, "HOLD_POLL_S", original)
        self.history = self.tmp / "history"
        for n, wall in enumerate((60, 120, 180)):
            summary(self.history / f"r{n}", f"r{n}", [
                {"role": "role-a", "executor": "pi", "model": "fake/deterministic",
                 "attempts": [attempt(wall, 500, 0.0, "unpriced")]}])
        self.module = self.tmp / "workflow.py"
        self.write_module(("a",))
        self.args = {"repo": str(self.repo)}
        self.reads: list[list[str]] = []
        read = estimate.Prior.from_history

        def counted(paths):
            paths = [str(p) for p in paths]
            self.reads.append(paths)
            return read(paths)

        estimate.Prior.from_history = counted
        self.addCleanup(setattr, estimate.Prior, "from_history", read)

    def write_module(self, steps: tuple[str, ...]) -> None:
        self.module.write_text(textwrap.dedent(WORKFLOW) % repr(steps),
                               encoding="utf-8")

    def start(self, run_dir, **options):
        workflow = validate(load_workflow(self.module, self.args))
        result: dict = {}

        def target():
            with quiet():
                result["outcome"] = run_workflow(workflow, run_dir, RunOptions(
                    dashboard=False, harness_executors=self.harness_executors,
                    workflow_path=str(self.module), workflow_args=self.args,
                    history=(str(self.history),), say=lambda _line: None,
                    **options))

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        return thread, result

    def steps_estimated(self, run_dir) -> list[str]:
        data = json.loads((run_dir / estimate.ESTIMATE_FILE)
                          .read_text(encoding="utf-8"))
        return [s["coord"] for s in data["steps"]]

    def test_the_estimate_after_go_uses_the_prior_the_hold_read(self):
        run_dir = self.tmp / "runs" / "r-held"
        thread, result = self.start(run_dir, hold=True)
        self.assertTrue(wait_for(run_dir / rundir.HOLD_FILE))
        self.assertTrue(wait_for(run_dir / estimate.ESTIMATE_FILE))
        self.assertEqual(self.steps_estimated(run_dir), ["01.only/01.a"])
        self.write_module(("a", "b"))
        (run_dir / rundir.GO_FILE).write_text("now", encoding="utf-8")
        thread.join(HOLD_WAIT_S)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result["outcome"].status, "finished")
        self.assertEqual(self.steps_estimated(run_dir),
                         ["01.only/01.a", "01.only/02.b"],
                         "the estimate is made again for the reloaded plan")
        self.assertEqual(self.reads, [[str(self.history)]],
                         "the history is read once, not once per estimate")

    def test_the_estimate_after_a_pilot_counts_the_pilot_run(self):
        runs = self.tmp / "runs"
        run_dir = runs / "r-pilot"
        thread, result = start_in_thread(lambda: run_workflow(
            two_paths(self.repo), run_dir, RunOptions(
                dashboard=False, harness_executors=self.harness_executors,
                history=(str(runs),), say=lambda _line: None, pilot=True)))
        self.assertTrue(wait_for(run_dir / rundir.HOLD_FILE))
        (run_dir / rundir.GO_FILE).write_text("now", encoding="utf-8")
        thread.join(HOLD_WAIT_S)
        self.assertFalse(thread.is_alive())
        self.assertNotIn("error", result, result.get("error"))
        self.assertEqual(result["outcome"].status, "finished")
        self.assertEqual(self.reads, [[str(runs)], [str(runs)]],
                         "the pilot finished a run under the history")
        data = json.loads((run_dir / estimate.ESTIMATE_FILE)
                          .read_text(encoding="utf-8"))
        self.assertEqual(data["history"]["sources"], 1)
        self.assertEqual(data["history"]["samples"], 3)


if __name__ == "__main__":
    import unittest
    unittest.main()

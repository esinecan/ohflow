"""`run_workflow` is the one function that runs a workflow, below the CLI.

Before: `cli.supervise` held the run order (claim the directory, start the
dashboard, run the engine, write the exit report), and the campaign controller and
the shim built a fake argparse namespace to reach it.
Now: `run_workflow(workflow, run_dir, RunOptions)` holds it, and returns a `RunOutcome`
with the final status, the exit verdict line and the m1 run reader.
"""

from __future__ import annotations

import json

from ohflow.engine import Engine, PreflightError
from ohflow.workflow import CheckSpec, GateSpec
from ohflow.supervisor import RunOptions, RunOutcome, run_workflow
from support import (FakeHarnessExecutor, TempCase, AgentScript, git_repo,
                     install_fake_harness_executor, quiet, read_run_log, simple_workflow,
                     stub_preflight, agent_step)

FAILING_GATE = GateSpec(checks=(CheckSpec("final_message_matches",
                                          {"regex": r"NEVER-SAID"}),))
EXIT_FILES = ("exit.json", "exit-report.md", "exit-report.html")


class RunWorkflow(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript()))

    def run_it(self, workflow, name: str = "r-one", **options) -> RunOutcome:
        options.setdefault("dashboard", False)
        options.setdefault("harness_executors", self.harness_executors)
        with quiet():
            return run_workflow(workflow, self.tmp / "runs" / name,
                                RunOptions(**options))

    def exit_record(self, outcome: RunOutcome) -> dict:
        return json.loads((outcome.run_dir / "exit.json").read_text(
            encoding="utf-8"))

    def test_a_passing_workflow_writes_the_exit_report_and_returns_its_verdict(self):
        workflow = simple_workflow(self.repo, steps=[agent_step("a"),
                                                     agent_step("b")])
        outcome = self.run_it(workflow)
        self.assertEqual(outcome.status, "finished")
        self.assertEqual(outcome.summary["status"], "finished")
        for name in EXIT_FILES:
            self.assertTrue((outcome.run_dir / name).exists(), name)
        self.assertEqual(outcome.verdict, self.exit_record(outcome)["verdict"])
        self.assertIn("2 of 2 agents passed", outcome.verdict)
        self.assertIsNone(outcome.problem)

    def test_the_outcome_hands_back_the_run_reader(self):
        workflow = simple_workflow(self.repo, steps=[agent_step("a")])
        outcome = self.run_it(workflow)
        statuses = {view.coord: view.status for view in outcome.run.steps()}
        self.assertEqual(list(statuses.values()), ["passed"])

    def test_a_failed_step_still_writes_the_exit_report(self):
        workflow = simple_workflow(self.repo, on_step_failure="abort",
                                   steps=[agent_step("a", gate=FAILING_GATE)])
        outcome = self.run_it(workflow)
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(self.exit_record(outcome)["status"], "failed")
        self.assertIn("1 failed", outcome.verdict)

    def test_an_engine_that_raises_gets_its_exit_report_and_the_exception(self):
        def run(engine):
            engine.run_dir.mkdir(parents=True, exist_ok=True)
            engine.run_log.append("run_started", payload={
                "run_id": engine.run_id, "workflow": engine.workflow.name})
            raise RuntimeError("the engine fell over")
        original = Engine.run
        Engine.run = run
        self.addCleanup(setattr, Engine, "run", original)

        run_dir = self.tmp / "runs" / "r-raise"
        workflow = simple_workflow(self.repo, steps=[agent_step("a")])
        with self.assertRaises(RuntimeError), quiet():
            run_workflow(workflow, run_dir, RunOptions(dashboard=False,
                                                       harness_executors=self.harness_executors))
        record = json.loads((run_dir / "exit.json").read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "crashed")
        self.assertEqual(record["error"], "RuntimeError: the engine fell over")
        self.assertEqual([r["event"] for r in read_run_log(run_dir)],
                         ["run_started"], "a crash writes no run log event")

    def test_a_preflight_fault_is_a_problem_not_an_exception(self):
        def run(engine):
            raise PreflightError("preflight failed:\n  - no repo")
        original = Engine.run
        Engine.run = run
        self.addCleanup(setattr, Engine, "run", original)

        workflow = simple_workflow(self.repo, steps=[agent_step("a")])
        outcome = self.run_it(workflow)
        self.assertEqual(outcome.status, "crashed")
        self.assertIsNone(outcome.summary)
        self.assertIn("preflight failed", outcome.problem)
        self.assertEqual(self.exit_record(outcome)["status"], "crashed")

    def test_a_dry_run_writes_no_exit_report(self):
        workflow = simple_workflow(self.repo, steps=[agent_step("a")])
        outcome = self.run_it(workflow, dry_run=True)
        self.assertEqual(outcome.status, "finished")
        self.assertIsNone(outcome.verdict)
        for name in EXIT_FILES:
            self.assertFalse((outcome.run_dir / name).exists(), name)

    def test_resume_yes_refuses_a_directory_with_no_run_log(self):
        workflow = simple_workflow(self.repo, steps=[agent_step("a")])
        outcome = self.run_it(workflow, resume="yes")
        self.assertEqual(outcome.status, "refused")
        self.assertIn("no run log to resume", outcome.problem)
        self.assertFalse(outcome.run_dir.exists())

    def test_resume_auto_continues_a_run_that_has_a_run_log(self):
        workflow = simple_workflow(self.repo, steps=[agent_step("a")])
        first = self.run_it(workflow)
        second = self.run_it(workflow)
        self.assertEqual(second.run_dir, first.run_dir)
        self.assertEqual(second.status, "finished")
        events = [r["event"] for r in read_run_log(second.run_dir)]
        self.assertEqual(events.count("run_started"), 1,
                         "a resume continues the run; it does not start one")

    def test_resume_no_refuses_a_directory_that_holds_a_run(self):
        workflow = simple_workflow(self.repo, steps=[agent_step("a")])
        self.run_it(workflow)
        outcome = self.run_it(workflow, resume="no")
        self.assertIsNotNone(outcome.problem)
        self.assertEqual(outcome.status, "refused")

    def test_an_unknown_resume_word_is_an_error(self):
        workflow = simple_workflow(self.repo, steps=[agent_step("a")])
        with self.assertRaises(ValueError):
            self.run_it(workflow, resume="maybe")

    def test_say_receives_the_exit_report_line(self):
        workflow = simple_workflow(self.repo, steps=[agent_step("a")])
        heard: list[str] = []
        self.run_it(workflow, say=heard.append)
        self.assertTrue(any(line.startswith("exit report:") for line in heard),
                        heard)

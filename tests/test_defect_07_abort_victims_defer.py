"""Defect 7: an abort's victims are `deferred`, and `--resume` re-runs them.

Fixed in `371694b`, "ohflow: an abort's victims are deferred, not failed".

What went wrong. In the preserved Cortea run the run log records nine steps.
Three produced their own failures. The other six were killed by the abort and
recorded as `failed`, with the error string `run aborted` - a string that says
nothing about their work, because none of them ever called the provider. The
board then said six agents had failed when six agents had never run.

What is asserted here. A step the abort killed, or found already killed, comes
out `deferred`. `deferred` is terminal and is not `ok`, so it is never cached,
and a `--resume` re-runs exactly the deferred steps while every step that passed
comes back `cached`.

Determinism. Nothing here depends on thread scheduling order. The victim that is
killed in flight is made deterministic by a fake agent that sets the abort event
itself from inside its own poll, which is the same ordering the engine sees in
production and is the same every time.
"""

from __future__ import annotations

from fixtures.real_errors import (ABORT_VICTIM_ERROR,
                                  SCOUT1_TERMINAL_FAULT_LOG_TAIL)
from ohflow import harness_executor as ohexecutor
from ohflow.engine import Engine
from ohflow.run_log import TERMINAL, RunLog
from support import (FakeHarnessExecutor, TempCase, AgentScript, git_repo,
                     install_fake_harness_executor, read_run_log, simple_workflow,
                     step_statuses, stub_preflight, agent_step)


class AVictimIsDeferredNotFailed(TempCase):

    def test_a_step_that_never_started_is_deferred(self):
        """`_guarded_step` finds the abort already set and records the step
        without launching an agent. That is the six-scout case exactly."""
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        harness_executor = install_fake_harness_executor(self, FakeHarnessExecutor(
            default=AgentScript(final_text="DONE\n")))
        workflow = simple_workflow(
            repo,
            steps=[agent_step("v1"), agent_step("v2"), agent_step("v3")],
            on_step_failure="abort", max_parallel=3)
        run_dir = self.run_dir()
        engine = Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors)

        # Everything the engine needs before a phase can run, then the abort,
        # then the phase. Every step takes the "already aborted" branch.
        engine.run_dir.mkdir(parents=True, exist_ok=True)
        engine._transition("run_started", payload={
            "run_id": run_dir.name, "workflow": workflow.name, "meta": {}})
        engine._abort.set()
        engine._run_phase(1, workflow.phases[0])

        statuses = step_statuses(run_dir)
        for coord, status in statuses.items():
            self.assertEqual(status, "deferred",
                             f"{coord} was marked {status!r}; a step that never "
                             "called the provider was not judged")
        self.assertEqual(harness_executor.launched, [],
                         "an agent was launched only to be killed")

    def test_the_recorded_reason_says_the_step_never_started(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript()))
        workflow = simple_workflow(repo, steps=[agent_step("v1")],
                                   on_step_failure="abort")
        run_dir = self.run_dir()
        engine = Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors)
        engine._transition("run_started", payload={
            "run_id": run_dir.name, "workflow": workflow.name, "meta": {}})
        engine._abort.set()
        engine._run_phase(1, workflow.phases[0])

        rec = RunLog.replay(run_dir).steps["01.only-phase/01.v1"]
        self.assertEqual(rec.status, "deferred")
        self.assertIn("aborted", (rec.error or "").lower())
        self.assertIsNone(rec.failure_class,
                          "nothing was classified, because nothing failed")
        self.assertNotEqual(rec.error, ABORT_VICTIM_ERROR,
                            "the old text said only 'run aborted'; the new one "
                            "says the step never started")

    def test_a_step_killed_in_flight_is_deferred_and_never_gated(self):
        """The abort fires while this step is running. The engine kills it,
        skips the gate, and records `deferred` rather than a verdict."""
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)

        engine_box: list[Engine] = []

        def abort_from_inside_the_poll():
            # The step is in flight and something else has just aborted the run.
            engine_box[0]._abort.set()
            return ohexecutor.RUNNING

        harness_executor = install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript(
            on_poll=abort_from_inside_the_poll, final_text="DONE\n")))
        workflow = simple_workflow(repo, steps=[agent_step("inflight")],
                                   on_step_failure="abort")
        run_dir = self.run_dir()
        engine = Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors)
        engine_box.append(engine)
        engine.run()

        rec = RunLog.replay(run_dir).steps["01.only-phase/01.inflight"]
        self.assertEqual(rec.status, "deferred")
        self.assertIn("01.only-phase/01.inflight", harness_executor.killed,
                      "the in-flight agent was not killed")
        self.assertEqual(rec.gate, {"coord": "01.only-phase/01.inflight",
                                    "passed": False, "checks": []},
                         "a killed agent must not be gated: there is no work "
                         "to judge and no report to write")


class ResumeReRunsExactlyTheDeferredSteps(TempCase):
    """One run leaves a passed step and deferred steps behind. The second run
    caches the first and re-runs the rest."""

    def _first_run(self, run_dir):
        repo = git_repo(self.tmp / "repo", branch="main")
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(
            scripts={"02.doomed": AgentScript(
                error=SCOUT1_TERMINAL_FAULT_LOG_TAIL, final_text="")},
            default=AgentScript(final_text="DONE\n")))
        workflow = simple_workflow(
            repo,
            steps=[agent_step("good"), agent_step("doomed"),
                   agent_step("victim")],
            on_step_failure="abort", max_parallel=1)
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors).run()
        return repo, workflow

    def test_a_passed_step_caches_and_a_deferred_step_runs_again(self):
        run_dir = self.run_dir()
        repo, workflow = self._first_run(run_dir)
        first = step_statuses(run_dir)

        passed = {c for c, s in first.items() if s == "passed"}
        deferred = {c for c, s in first.items() if s == "deferred"}
        self.assertTrue(passed or deferred,
                        f"the first run produced nothing to resume: {first}")

        # Where the first run's run log ends. A resume writes no second
        # `run_started` - it replays the first one - so the boundary between the
        # two runs is a line count, not an event.
        boundary = len(read_run_log(run_dir))

        # Second run, same directory, everything succeeds this time.
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript(final_text="DONE\n")))
        Engine(workflow, run_dir, run_id=run_dir.name, resume=True,
               verbose=False,
               harness_executors=self.harness_executors).run()

        after = read_run_log(run_dir)[boundary:]
        self.assertTrue(after, "the resume wrote nothing to the run log")
        started_again = {r["coord"] for r in after
                         if r["event"] == "attempt_started"}
        cached_now = {r["coord"] for r in after
                      if r["event"] == "attempt_finished"
                      and r["payload"].get("status") == "cached"}

        for coord in passed:
            self.assertIn(coord, cached_now,
                          f"{coord} passed and was re-run anyway")
            self.assertNotIn(coord, started_again)
        for coord in deferred:
            self.assertIn(coord, started_again,
                          f"{coord} was deferred and was not re-run")
            self.assertNotIn(coord, cached_now,
                             f"{coord} was deferred and was cached instead")

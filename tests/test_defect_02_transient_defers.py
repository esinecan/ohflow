"""Defect 2: a transient failure defers the step, it does not abort the phase.

Fixed in `c97bc45`, "ohflow: a transient failure defers a step, it does not
abort the phase", with `deferred` added to the status set and the
`transient_backoff_s` cooldown.

What went wrong. `on_step_failure="abort"` is the right answer to an agent that
did the wrong thing and the wrong answer to a provider that answered 429. In the
preserved Cortea run three agents hit a rate limit after about 27 minutes each,
the abort fired, and six agents that had not started yet died in roughly a
second each without ever calling the provider.

What is asserted here. A step whose error carries a real rate limit comes out
`deferred`, the run pauses instead of aborting, and the steps beside it still
run and still pass. A step whose error is structural still fails and still
aborts, because the defect was never a reason to weaken abort.

`deferred` is terminal and it is not `ok`, which is what makes `--resume`
re-run exactly those steps. That half is proved in
`test_defect_07_abort_victims_defer.py`.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from fixtures.real_errors import (SCOUT1_TERMINAL_FAULT_LOG_TAIL,
                                  SCOUT2_RATE_LIMIT_RESULT_ERROR)
from ohflow import failure
from ohflow.engine import Engine
from ohflow.run_log import TERMINAL, RunLog
from ohflow.workflow import CheckSpec, GateSpec
from support import (FakeHarnessExecutor, TempCase, AgentScript, git_repo,
                     install_fake_harness_executor, read_run_log, simple_workflow, step_statuses,
                     stub_preflight, agent_step)


F2_PI_RATE_LIMIT_RESULT = (
    Path(__file__).parent / "fixtures" / "f2-pi-429-result.json"
)


class DeferredIsAFirstClassStatus(TempCase):

    def test_deferred_is_terminal_and_is_not_ok(self):
        from ohflow.run_log import STATUSES, StepRecord
        self.assertIn("deferred", STATUSES)
        self.assertIn("deferred", TERMINAL)
        rec = StepRecord(coord="01.p/01.s", status="deferred")
        self.assertTrue(rec.terminal)
        self.assertFalse(rec.ok, "a deferred step must never be cached")
        self.assertTrue(rec.rerunnable)


class ATransientFailureDoesNotAbortThePhase(TempCase):
    """The whole defect, run through the engine with an `abort` policy."""

    def _run(self, first_error: str):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        harness_executor = install_fake_harness_executor(self, FakeHarnessExecutor(
            scripts={
                "01.doomed": AgentScript(error=first_error, final_text=""),
            },
            default=AgentScript(final_text="DONE\n"),
        ))
        workflow = simple_workflow(
            repo,
            steps=[agent_step("doomed"), agent_step("beside-a"),
                   agent_step("beside-b")],
            on_step_failure="abort",
            max_parallel=3,
        )
        run_dir = self.run_dir()
        engine = Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors)
        summary = engine.run()
        return engine, run_dir, summary, harness_executor

    def test_a_real_rate_limit_defers_and_the_others_still_pass(self):
        engine, run_dir, summary, harness_executor = self._run(
            SCOUT2_RATE_LIMIT_RESULT_ERROR)
        statuses = step_statuses(run_dir)

        doomed = "01.only-phase/01.doomed"
        self.assertEqual(statuses[doomed], "deferred",
                         "a rate limit is not a verdict on the work")
        self.assertFalse(engine._abort.is_set(),
                         "a transient failure must never set the abort event")
        for coord in ("01.only-phase/02.beside-a", "01.only-phase/03.beside-b"):
            self.assertEqual(statuses[coord], "passed",
                             "the steps beside a rate-limited one were lost")

        state = RunLog.replay(run_dir)
        self.assertEqual(state.steps[doomed].failure_class, failure.TRANSIENT)
        self.assertEqual(state.status, "paused",
                         "the run must pause, not fail")

    def test_the_phase_settles_deferred_and_the_run_pauses(self):
        _engine, run_dir, summary, _harness_executor = self._run(
            SCOUT2_RATE_LIMIT_RESULT_ERROR)
        state = RunLog.replay(run_dir)
        phase = state.phases["01.only-phase"]
        self.assertEqual(phase["status"], "deferred",
                         "a phase with deferrals and no hard failure is "
                         "deferred, not failed")
        self.assertEqual(summary["deferred"], ["01.only-phase/01.doomed"])
        self.assertEqual(summary["quarantined"], [],
                         "a deferred step was never judged, so it is not "
                         "quarantined")
        self.assertEqual(summary["status"], "paused")

    def test_the_run_log_names_the_signature_that_matched(self):
        _engine, run_dir, _summary, _harness_executor = self._run(
            SCOUT2_RATE_LIMIT_RESULT_ERROR)
        finished = [r for r in _read(run_dir)
                    if r["event"] == "attempt_finished"
                    and r.get("coord", "").endswith("01.doomed")]
        # One execution, and the engine writes its verdict twice: once when the
        # verdict is reached, once again with the retry decision, which is only
        # known afterwards. Both carry the same attempt number, so `replay`
        # updates one execution and the attempt history counts one failure. That is
        # proved in test_defect_16.
        self.assertEqual({r["attempt"] for r in finished}, {1},
                         "a deferred step must have exactly one execution")
        payload = finished[0]["payload"]
        self.assertEqual(payload["status"], "deferred")
        self.assertEqual(payload["transient_signature"], "RateLimitError")
        for extra in finished[1:]:
            self.assertEqual(extra["payload"]["status"], "deferred",
                             "a re-emitted verdict must not change the verdict")

    def test_a_structural_failure_still_aborts(self):
        """The fix must not have weakened abort. Same workflow, same policy, an
        error from the same preserved run that carries no rate limit."""
        engine, run_dir, summary, _harness_executor = self._run(
            SCOUT1_TERMINAL_FAULT_LOG_TAIL)
        statuses = step_statuses(run_dir)
        doomed = "01.only-phase/01.doomed"
        self.assertEqual(statuses[doomed], "failed")
        self.assertTrue(engine._abort.is_set(),
                        "a structural failure under an abort policy must abort")
        self.assertEqual(summary["status"], "failed")
        self.assertIn(doomed, summary["quarantined"])


class AFinishedAgentErrorOutranksAPassingGate(TempCase):
    """Regression for F2's retained live pi result.

    Pi reported a provider error in ``result.json`` while its process exited
    normally, so harness executor polling returned ``FINISHED``.  The worktree was clean,
    which made ``tree_clean`` pass.  The engine used to let that passing gate
    overwrite the agent error and record the execution as passed.
    """

    class PreservedResultHarnessExecutor(FakeHarnessExecutor):
        def collect(self, handle):
            generated = super().collect(handle)
            if handle.launch_index != 1:
                return generated
            recorded = json.loads(
                F2_PI_RATE_LIMIT_RESULT.read_text(encoding="utf-8"))
            # The payload is copied from the live run.  Only its coordinates
            # are rebound to this disposable run so run log and result agree.
            recorded["coord"] = handle.coord
            recorded["attempt"] = handle.attempt
            (handle.out_dir / "result.json").write_text(
                json.dumps(recorded, indent=2), encoding="utf-8")
            return recorded

    def test_the_recorded_429_defers_then_auto_resumes(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        harness_executor = install_fake_harness_executor(self, self.PreservedResultHarnessExecutor(
            scripts={"01.flaky": AgentScript(final_text="DONE\n")}))
        clean_gate = GateSpec(checks=(CheckSpec("tree_clean", {}),))
        workflow = replace(simple_workflow(
            repo,
            steps=[agent_step("flaky", gate=clean_gate)],
            on_step_failure="abort",
            max_parallel=1,
        ), auto_resume=1)
        run_dir = self.run_dir()

        summary = Engine(workflow, run_dir, run_id=run_dir.name,
                         verbose=False,
                         harness_executors=self.harness_executors).run()

        coord = "01.only-phase/01.flaky"
        first_verdict = next(
            row for row in read_run_log(run_dir)
            if row["event"] == "attempt_finished"
            and row.get("coord") == coord
            and row.get("attempt") == 1)
        self.assertEqual(first_verdict["payload"]["status"], "deferred")
        self.assertEqual(first_verdict["payload"]["failure_class"],
                         failure.TRANSIENT)
        self.assertEqual(harness_executor.launched.count(coord), 2)
        self.assertEqual(step_statuses(run_dir)[coord], "passed")
        self.assertEqual(summary["status"], "finished")
        self.assertEqual(len([row for row in read_run_log(run_dir)
                              if row["event"] == "phase_resumed"]), 1)


class TheCooldownHoldsTheRemainingSteps(TempCase):
    """`_back_off` pushes a cooldown out so nine steps do not stampede back
    into the same rate limit one second after it fired."""

    def test_backoff_doubles_and_is_capped_at_ten_times_the_base(self):
        repo = self.tmp / "repo"
        from ohflow.workflow import Workflow
        workflow = simple_workflow(repo)
        workflow = Workflow(**{**{f.name: getattr(workflow, f.name)
                                  for f in workflow.__dataclass_fields__.values()},
                               "transient_backoff_s": 10})
        engine = Engine(workflow, self.run_dir(), run_id="r-test-0001",
                        verbose=False,
                        harness_executors=self.harness_executors)
        waits = [engine._back_off("01.p/01.s") for _ in range(6)]
        self.assertEqual(waits, [10.0, 20.0, 40.0, 80.0, 100.0, 100.0],
                         "doubling, then capped at ten times the base")

    def test_a_zero_base_disables_the_wait_entirely(self):
        workflow = simple_workflow(self.tmp / "repo")     # transient_backoff_s = 0
        engine = Engine(workflow, self.run_dir(), run_id="r-test-0001",
                        verbose=False,
                        harness_executors=self.harness_executors)
        self.assertEqual(engine._back_off("01.p/01.s"), 0.0)
        self.assertEqual(engine._cooldown_until, 0.0)


def _read(run_dir):
    from support import read_run_log
    return read_run_log(run_dir)

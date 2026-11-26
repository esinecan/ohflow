"""Defect 16: a bound held in memory is not a bound.

What would have gone wrong. The first design for retry and auto-resume counted
attempts in the engine process, so a killed supervisor handed every step a fresh
budget on the next `--resume`, and an auto-resume pass handed a step a fresh retry budget so
the worst case was the product of two numbers a workflow author chose separately.

What is asserted here. Every count comes from the run log, keyed by the pair
`(coordinate, fingerprint)`. An abort victim advances no bound, because it
reached no verdict even if it already called the provider. Attempt numbers never
repeat, so no attempt directory is ever written into twice. Two failed executions
of unchanged work exclude it from the rest of the run, whatever mixture of judged
failures and transient deferrals they were, and editing the work gives the new
revision its own budget.

Four counting faults an independent review found before this module reached the
engine, each with its own test below. Exclusion on either counter alone let a
judged failure and a transient deferral authorise a third execution. A manual
start had no bound at all, so a supervisor interrupted over and over never
reached exclusion, because a running execution carries no failure status.
Automatic starts pooled retries and auto-resume passes, so `auto_resume=1` authorised a
retry that `retry.max=0` had refused. An `attempt_finished` matched the latest
running execution by coordinate alone, so a cached or policy-relabelled finish
closed an older interrupted attempt and a second finish for one attempt counted
its failure twice.

Also asserted here: the fingerprint of a first attempt is byte-identical to what
this package produced before the attempt number left the fingerprint, so every
run directory written earlier still caches.
"""

from __future__ import annotations

from ohflow import attempts
from ohflow.fingerprint import fingerprint
from ohflow.run_log import RunLog, RunState
from support import TempCase, git_repo, simple_workflow, agent_step

COORD = "01.only-phase/01.s1"
FP_A = "a" * 64
FP_B = "b" * 64


def _run_log(tmp):
    return RunLog(tmp / "run")


def _start(j, *, attempt, fp, kind="initial", coord=COORD):
    j.append("attempt_started", coord=coord, attempt=attempt,
             payload={"step_id": "s1", "kind": "agent", "fingerprint": fp,
                      "start_kind": kind})


def _finish(j, *, attempt, fp, status, coord=COORD, failure_class=None,
            abort_victim=False):
    j.append("attempt_finished", coord=coord, attempt=attempt,
             payload={"step_id": "s1", "kind": "agent", "fingerprint": fp,
                      "status": status, "failure_class": failure_class,
                      "abort_victim": abort_victim})


def _synthetic(j, *, fp, status, coord=COORD, abort_victim=False, error=None):
    """A finish for something that never started: a cached step, an abort
    victim recorded before it launched, work the attempt history refused to start."""
    from ohflow.run_log import SYNTHETIC_ATTEMPT
    j.append("attempt_finished", coord=coord, attempt=SYNTHETIC_ATTEMPT,
             payload={"step_id": "s1", "kind": "agent", "fingerprint": fp,
                      "status": status, "failure_class": None,
                      "abort_victim": abort_victim, "error": error})


class TheCountsComeFromTheRunLog(TempCase):

    def test_an_execution_that_never_ended_still_counts_as_an_attempt(self):
        """The supervisor was killed while an agent was running. That agent may
        have left side effects, so the next execution is a new attempt."""
        j = _run_log(self.tmp)
        _start(j, attempt=1, fp=FP_A)
        state = RunLog.replay(j.run_dir)
        self.assertEqual(attempts.attempts(state, COORD, FP_A), 1)
        self.assertEqual(attempts.next_attempt(state, COORD), 2,
                         "an interrupted attempt is never reused")

    def test_attempts_are_counted_per_fingerprint(self):
        j = _run_log(self.tmp)
        _start(j, attempt=1, fp=FP_A)
        _finish(j, attempt=1, fp=FP_A, status="failed")
        _start(j, attempt=2, fp=FP_B, kind="initial")
        state = RunLog.replay(j.run_dir)
        self.assertEqual(attempts.attempts(state, COORD, FP_A), 1)
        self.assertEqual(attempts.attempts(state, COORD, FP_B), 1)
        self.assertEqual(attempts.attempts(state, COORD), 2, "both, together")

    def test_attempt_numbers_never_repeat_across_a_fingerprint_change(self):
        j = _run_log(self.tmp)
        _start(j, attempt=1, fp=FP_A)
        _finish(j, attempt=1, fp=FP_A, status="failed")
        state = RunLog.replay(j.run_dir)
        self.assertEqual(attempts.next_attempt(state, COORD), 2,
                         "a new revision of the work still gets a new "
                         "directory, because the old one holds an agent's "
                         "output")


class AVerdictIsWhatCounts(TempCase):

    def test_a_judged_failure_counts(self):
        j = _run_log(self.tmp)
        for attempt in (1, 2):
            _start(j, attempt=attempt, fp=FP_A)
            _finish(j, attempt=attempt, fp=FP_A, status="failed")
        state = RunLog.replay(j.run_dir)
        self.assertEqual(attempts.judged_failures(state, COORD, FP_A), 2)

    def test_a_transient_deferral_counts_separately(self):
        j = _run_log(self.tmp)
        _start(j, attempt=1, fp=FP_A)
        _finish(j, attempt=1, fp=FP_A, status="deferred",
                failure_class="transient")
        state = RunLog.replay(j.run_dir)
        self.assertEqual(attempts.transient_deferrals(state, COORD, FP_A), 1)
        self.assertEqual(attempts.judged_failures(state, COORD, FP_A), 0,
                         "a deferral is not a verdict")

    def test_an_abort_victim_advances_no_bound(self):
        """It may already have called the provider. It reached no verdict, and
        that is why nothing counts it."""
        j = _run_log(self.tmp)
        for attempt in (1, 2, 3):
            _start(j, attempt=attempt, fp=FP_A)
            _finish(j, attempt=attempt, fp=FP_A, status="deferred",
                    abort_victim=True)
        state = RunLog.replay(j.run_dir)
        self.assertEqual(attempts.abort_victims(state, COORD, FP_A), 3)
        self.assertEqual(attempts.judged_failures(state, COORD, FP_A), 0)
        self.assertEqual(attempts.transient_deferrals(state, COORD, FP_A), 0)
        self.assertFalse(attempts.excluded(state, COORD, FP_A),
                         "three abort victims must not exclude the work")


class TwoFailuresExcludeUnchangedWork(TempCase):

    def _twice(self, status: str, failure_class=None):
        j = _run_log(self.tmp)
        for attempt in (1, 2):
            _start(j, attempt=attempt, fp=FP_A)
            _finish(j, attempt=attempt, fp=FP_A, status=status,
                    failure_class=failure_class)
        return RunLog.replay(j.run_dir)

    def test_two_judged_failures_exclude(self):
        state = self._twice("failed")
        self.assertTrue(attempts.excluded(state, COORD, FP_A))
        self.assertIn("2 failed executions",
                      attempts.exclusion_reason(state, COORD, FP_A))

    def test_two_transient_deferrals_exclude(self):
        state = self._twice("deferred", failure_class="transient")
        self.assertTrue(attempts.excluded(state, COORD, FP_A))
        self.assertIn("2 failed executions",
                      attempts.exclusion_reason(state, COORD, FP_A))

    def test_one_of_each_excludes_too(self):
        """Exclusion counts failed executions, not either kind on its own.
        Counting them apart let a judged failure and a transient deferral
        authorise a third execution of unchanged work."""
        j = _run_log(self.tmp)
        _start(j, attempt=1, fp=FP_A)
        _finish(j, attempt=1, fp=FP_A, status="failed")
        _start(j, attempt=2, fp=FP_A, kind="retry")
        _finish(j, attempt=2, fp=FP_A, status="deferred",
                failure_class="transient")
        state = RunLog.replay(j.run_dir)

        self.assertEqual(attempts.judged_failures(state, COORD, FP_A), 1)
        self.assertEqual(attempts.transient_deferrals(state, COORD, FP_A), 1)
        self.assertEqual(attempts.failed_executions(state, COORD, FP_A), 2)
        self.assertTrue(attempts.excluded(state, COORD, FP_A),
                        "one of each is still two failures of the same work")
        reason = attempts.exclusion_reason(state, COORD, FP_A)
        self.assertIn("1 judged", reason)
        self.assertIn("1 transient", reason)

    def test_one_failure_does_not_exclude(self):
        j = _run_log(self.tmp)
        _start(j, attempt=1, fp=FP_A)
        _finish(j, attempt=1, fp=FP_A, status="deferred",
                failure_class="transient")
        state = RunLog.replay(j.run_dir)
        self.assertFalse(attempts.excluded(state, COORD, FP_A))

    def test_a_changed_fingerprint_is_a_new_revision_with_its_own_budget(self):
        state = self._twice("failed")
        self.assertTrue(attempts.excluded(state, COORD, FP_A))
        self.assertFalse(attempts.excluded(state, COORD, FP_B),
                         "editing the work must not inherit its old failures")

    def test_a_recorded_exclusion_event_survives_a_replay(self):
        j = _run_log(self.tmp)
        j.append("work_excluded", coord=COORD,
                 payload={"coord": COORD, "fingerprint": FP_A, "failures": 2,
                          "reason": "excluded: recorded by the engine"})
        state = RunLog.replay(j.run_dir)
        self.assertTrue(attempts.excluded(state, COORD, FP_A))
        self.assertEqual(attempts.exclusion_reason(state, COORD, FP_A),
                         "excluded: recorded by the engine")


class EachKnobBoundsItsOwnKind(TempCase):
    """Pooling retries and auto-resume passes into one automatic budget let a workflow that
    allowed an auto-resume pass also get a retry, and the other way round."""

    def _after_one(self, status: str, failure_class=None):
        j = _run_log(self.tmp)
        _start(j, attempt=1, fp=FP_A, kind="initial")
        _finish(j, attempt=1, fp=FP_A, status=status,
                failure_class=failure_class)
        return RunLog.replay(j.run_dir)

    def test_auto_resume_does_not_authorise_a_retry(self):
        state = self._after_one("failed")
        allowed, why = attempts.may_start(state, COORD, FP_A, start_kind="retry",
                                          retry_max=0, auto_resume=1)
        self.assertFalse(allowed)
        self.assertIn("retry budget spent", why)

    def test_retry_max_does_not_authorise_an_auto_resume(self):
        state = self._after_one("deferred", failure_class="transient")
        allowed, why = attempts.may_start(state, COORD, FP_A, start_kind="auto_resume",
                                          retry_max=1, auto_resume=0)
        self.assertFalse(allowed)
        self.assertIn("auto-resume budget spent", why)

    def test_each_kind_is_granted_when_its_own_knob_allows_it(self):
        state = self._after_one("failed")
        allowed, _why = attempts.may_start(state, COORD, FP_A,
                                           start_kind="retry", retry_max=1,
                                           auto_resume=0)
        self.assertTrue(allowed)

    def test_a_spent_kind_stays_spent_across_a_resume(self):
        """The run log is the attempt history, so a new engine process does not hand the
        step a fresh budget."""
        j = _run_log(self.tmp)
        _start(j, attempt=1, fp=FP_A, kind="initial")
        _finish(j, attempt=1, fp=FP_A, status="deferred",
                failure_class="transient")
        _start(j, attempt=2, fp=FP_A, kind="auto_resume")
        _finish(j, attempt=2, fp=FP_A, status="passed")
        state = RunLog.replay(j.run_dir)
        self.assertEqual(attempts.starts_of_kind(state, COORD, FP_A, "auto_resume"), 1)
        allowed, why = attempts.may_start(state, COORD, FP_A, start_kind="auto_resume",
                                          retry_max=0, auto_resume=1)
        self.assertFalse(allowed, "the one auto-resume pass was already spent")
        self.assertIn("auto-resume budget spent", why)


class ManualRecoveryIsFiniteAndNotZero(TempCase):

    def test_the_total_budget_adds_and_does_not_multiply(self):
        self.assertEqual(attempts.execution_budget(1, 1), 4,
                         "1 initial + 1 retry + 1 auto-resume pass + 1 manual recovery")
        self.assertEqual(attempts.execution_budget(0, 0), 2,
                         "the defaults still allow one manual recovery")
        self.assertEqual(attempts.MANUAL_RECOVERY_ALLOWANCE, 1)

    def test_the_defaults_still_allow_one_manual_resume(self):
        """A single bound of `1 + retry.max + auto_resume` would have been 1 at
        the defaults, so a step deferred on a rate limit could never have been
        recovered by `--resume` and today's behaviour would have broken."""
        j = _run_log(self.tmp)
        _start(j, attempt=1, fp=FP_A, kind="initial")
        _finish(j, attempt=1, fp=FP_A, status="deferred",
                failure_class="transient")
        state = RunLog.replay(j.run_dir)

        allowed, why = attempts.may_start(state, COORD, FP_A,
                                          start_kind="initial", retry_max=0,
                                          auto_resume=0)
        self.assertTrue(allowed, f"a manual resume was refused: {why}")

        refused, why = attempts.may_start(state, COORD, FP_A, start_kind="auto_resume",
                                          retry_max=0, auto_resume=0)
        self.assertFalse(refused, "auto_resume=0 grants no auto-resume pass")
        self.assertIn("auto-resume budget spent", why)

    def test_the_second_manual_recovery_is_refused_by_exclusion(self):
        j = _run_log(self.tmp)
        for attempt in (1, 2):
            _start(j, attempt=attempt, fp=FP_A, kind="initial")
            _finish(j, attempt=attempt, fp=FP_A, status="deferred",
                    failure_class="transient")
        state = RunLog.replay(j.run_dir)
        allowed, why = attempts.may_start(state, COORD, FP_A,
                                          start_kind="initial", retry_max=0,
                                          auto_resume=0)
        self.assertFalse(allowed)
        self.assertIn("2 failed executions", why)

    def test_repeated_supervisor_interruptions_run_out(self):
        """Nothing here ever records a failure, because an interrupted
        execution stays `running`. Exclusion can never fire, so the total
        execution budget is the only thing that stops it."""
        j = _run_log(self.tmp)
        _start(j, attempt=1, fp=FP_A, kind="initial")   # killed mid-flight
        state = RunLog.replay(j.run_dir)
        allowed, why = attempts.may_start(state, COORD, FP_A,
                                          start_kind="initial", retry_max=0,
                                          auto_resume=0)
        self.assertTrue(allowed, f"the one manual recovery was refused: {why}")

        _start(j, attempt=2, fp=FP_A, kind="initial")   # killed again
        state = RunLog.replay(j.run_dir)
        self.assertEqual(attempts.failed_executions(state, COORD, FP_A), 0,
                         "an interrupted execution records no failure")
        allowed, why = attempts.may_start(state, COORD, FP_A,
                                          start_kind="initial", retry_max=0,
                                          auto_resume=0)
        self.assertFalse(allowed, "manual resume must not be unlimited")
        self.assertIn("execution budget spent", why)

    def test_a_longer_workflow_gets_a_larger_total(self):
        j = _run_log(self.tmp)
        for attempt in (1, 2, 3):
            _start(j, attempt=attempt, fp=FP_A, kind="initial")
        state = RunLog.replay(j.run_dir)
        allowed, _why = attempts.may_start(state, COORD, FP_A,
                                           start_kind="initial", retry_max=1,
                                           auto_resume=1)
        self.assertTrue(allowed, "three of four executions used")
        _start(j, attempt=4, fp=FP_A, kind="initial")
        state = RunLog.replay(j.run_dir)
        allowed, why = attempts.may_start(state, COORD, FP_A,
                                          start_kind="initial", retry_max=1,
                                          auto_resume=1)
        self.assertFalse(allowed)
        self.assertIn("execution budget spent", why)


class OnlyARealExecutionCounts(TempCase):
    """`attempt_finished` used to be matched to the latest running execution by
    coordinate alone. A cached or policy-relabelled finish then closed an older
    interrupted attempt, and a second finish for one attempt appended a second
    execution and doubled its failure."""

    def test_a_cached_step_adds_no_execution(self):
        j = _run_log(self.tmp)
        _synthetic(j, fp=FP_A, status="cached")
        state = RunLog.replay(j.run_dir)
        self.assertEqual(attempts.attempts(state, COORD, FP_A), 0,
                         "nothing launched for a cached step")
        self.assertEqual(attempts.next_attempt(state, COORD), 1,
                         "a cached step consumes no attempt number")

    def test_an_unstarted_abort_victim_consumes_no_attempt_number(self):
        j = _run_log(self.tmp)
        _synthetic(j, fp=FP_A, status="deferred", abort_victim=True,
                   error="the run aborted before this step started")
        state = RunLog.replay(j.run_dir)
        self.assertEqual(attempts.attempts(state, COORD, FP_A), 0)
        self.assertEqual(attempts.next_attempt(state, COORD), 1)
        self.assertFalse(attempts.excluded(state, COORD, FP_A))

    def test_a_synthetic_finish_never_rewrites_a_real_execution(self):
        """A cached step, an abort victim that never launched and a refused
        start all carry `SYNTHETIC_ATTEMPT`. Carrying a real number instead let
        them overwrite the record of an execution that genuinely ran, and the
        attempt history then saw fewer failures than there were."""
        from ohflow.run_log import SYNTHETIC_ATTEMPT
        self.assertEqual(SYNTHETIC_ATTEMPT, 0,
                         "real attempts are numbered from 1")
        j = _run_log(self.tmp)
        _start(j, attempt=1, fp=FP_A)
        _finish(j, attempt=1, fp=FP_A, status="failed")
        _synthetic(j, fp=FP_A, status="deferred", abort_victim=True,
                   error="the run aborted before this step started")
        state = RunLog.replay(j.run_dir)

        rows = attempts.executions(state, COORD, FP_A)
        self.assertEqual(len(rows), 1, "one execution ever ran")
        self.assertEqual(rows[0]["status"], "failed",
                         "the synthetic finish rewrote the real execution")
        self.assertEqual(attempts.judged_failures(state, COORD, FP_A), 1)
        self.assertEqual(state.steps[COORD].status, "deferred",
                         "the step's own status still follows the last word")
        self.assertEqual(state.steps[COORD].attempt, 1,
                         "a synthetic finish must not report the step as "
                         "never attempted")

    def test_many_synthetic_finishes_share_one_record(self):
        j = _run_log(self.tmp)
        for _ in range(3):
            _synthetic(j, fp=FP_A, status="cached")
        state = RunLog.replay(j.run_dir)
        self.assertEqual(len(state.executions), 1)
        self.assertEqual(attempts.attempts(state, COORD, FP_A), 0)

    def test_two_finishes_for_one_attempt_count_once(self):
        j = _run_log(self.tmp)
        _start(j, attempt=1, fp=FP_A)
        _finish(j, attempt=1, fp=FP_A, status="failed")
        # The phase policy relabels the same verdict.
        _finish(j, attempt=1, fp=FP_A, status="quarantined")
        state = RunLog.replay(j.run_dir)
        self.assertEqual(attempts.attempts(state, COORD, FP_A), 1)
        self.assertEqual(attempts.judged_failures(state, COORD, FP_A), 1,
                         "one execution failed once, whatever it was relabelled")
        self.assertFalse(attempts.excluded(state, COORD, FP_A))

    def test_an_interrupted_attempt_stays_open_when_a_later_one_finishes(self):
        j = _run_log(self.tmp)
        _start(j, attempt=1, fp=FP_A)                     # never finished
        _start(j, attempt=2, fp=FP_A, kind="initial")
        _finish(j, attempt=2, fp=FP_A, status="passed")
        state = RunLog.replay(j.run_dir)
        rows = attempts.executions(state, COORD, FP_A)
        self.assertEqual([r["attempt"] for r in rows], [1, 2])
        self.assertEqual(rows[0]["status"], "running",
                         "attempt 2 finishing must not close attempt 1")
        self.assertEqual(rows[1]["status"], "passed")
        self.assertEqual(attempts.judged_failures(state, COORD, FP_A), 0)


class TheFingerprintNamesTheWorkAndNotTheTry(TempCase):

    def test_the_hash_is_pinned_without_an_attempt_parameter(self):
        """Each fingerprint version intentionally invalidates older entries
        once; its value stays pinned (now version 7) so removing the attempt
        parameter cannot add try identity back into the cache key."""
        repo = git_repo(self.tmp / "repo")
        workflow = simple_workflow(repo, steps=[agent_step("s1")])
        self.assertEqual(
            fingerprint(workflow, RunState(), workflow.phases[0].steps[0]),
        "f4f48748735d94a9d45ee26a42b72debf0024fc5a0f1485998788480228312d8")


class TheEngineRefusesABadLimitInsteadOfRoundingIt(TempCase):
    """`ohflow validate` refuses these, and a caller reaching the engine
    directly is a workflow author or a test. Rounding an override of 0 up to 1 would
    hide the same fault the CLI refuses."""

    def test_a_direct_override_of_zero_is_refused(self):
        from ohflow.engine import Engine
        workflow = simple_workflow(self.tmp / "repo")
        with self.assertRaises(ValueError) as caught:
            Engine(workflow, self.run_dir(), run_id="r-test-0001", verbose=False,
                   max_parallel=0)
        self.assertIn("must be at least 1", str(caught.exception))

    def test_a_direct_override_that_is_a_boolean_is_refused(self):
        from ohflow.engine import Engine
        workflow = simple_workflow(self.tmp / "repo")
        with self.assertRaises(ValueError):
            Engine(workflow, self.run_dir(), run_id="r-test-0001", verbose=False,
                   max_parallel=True)

    def test_an_unvalidated_phase_limit_of_zero_is_refused(self):
        from ohflow.engine import Engine
        from ohflow.workflow import Phase
        workflow = simple_workflow(self.tmp / "repo", phases=(
            Phase(name="bad", steps=(agent_step("a"),), max_parallel=0),))
        engine = Engine(workflow, self.run_dir(), run_id="r-test-0001",
                        verbose=False)
        with self.assertRaises(ValueError) as caught:
            engine.phase_limit(workflow.phases[0])
        self.assertIn("ohflow validate", str(caught.exception))

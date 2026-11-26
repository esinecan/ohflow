"""Defect 12: `RetryPolicy` was parsed, validated, and never executed.

What went wrong. `workflow.RetryPolicy` has existed since the workflow model was
written, `workflow.validate` refused the two forbidden selectors, and
`_prepare_step_dir` could already render a prior attempt's failed checks into
the next brief. The run path pinned `attempt = 1` and never asked. A run failed
for a reason a retry would have fixed: a reviewer hung on a git pager and its
whole dimension was lost for a round.

What is asserted here. A step with a retry budget runs again when its failure is
covered, and the second brief tells the agent what failed the first time. Both
executions keep their own directory, so neither one's evidence is overwritten.
The phase policy is applied to the step's last verdict and not to an
intermediate attempt, because an abort fired by attempt 1 would have stopped a
run that attempt 2 was about to rescue.

And the refusals, which matter more than the retries:

  * a forbidden gate failure beats every selector
  * every independent failure must be covered, so one matching check does not
    authorise a retry of an unrelated failure beside it
  * a provider that refused structurally is not asked again
  * `auto_resume` does not authorise a retry, and `retry.max` does not
    authorise an auto-resume pass
  * a `command`, `merge` or `gate` step does not retry at all
  * an abort stops a pending retry
  * two failures of unchanged work exclude it, and a resume launches nothing
"""

from __future__ import annotations

import json

from ohflow import attempts, retry
from ohflow.engine import Engine
from ohflow.gates import GateReport, GateResult
from ohflow.run_log import RunLog
from ohflow.workflow import (CheckSpec, GateSpec, Phase, WorkflowError, RetryPolicy,
                             Step, validate)
from support import (FakeHarnessExecutor, TempCase, AgentScript, git_repo,
                     install_fake_harness_executor, read_run_log, simple_workflow,
                     step_statuses, stub_preflight, agent_step)

#: The gate every step in this file carries: the final message must say DONE.
DONE_GATE = GateSpec(checks=(CheckSpec("final_message_matches",
                                       {"regex": r"DONE"}),))
COORD = "01.only-phase/01.flaky"


def flaky_step(*, retry_policy: RetryPolicy, gate: GateSpec = DONE_GATE) -> Step:
    step = agent_step("flaky", gate=gate)
    from dataclasses import replace
    return replace(step, retry=retry_policy)


class OneFailureThenSuccess(TempCase):
    """The plain case: attempt 1 fails its gate, attempt 2 passes it."""

    def _run(self, *, retry_max: int = 1,
             on=("gate:final_message_matches",), auto_resume: int = 0):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        harness_executor = install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript(
            sequence=[{"final_text": "I gave up\n"}, {"final_text": "DONE\n"}])))
        workflow = simple_workflow(repo, phases=(
            Phase(name="Only phase", on_step_failure="continue",
                  min_success="all",
                  steps=(flaky_step(retry_policy=RetryPolicy(max=retry_max,
                                                             on=tuple(on))),)),))
        run_dir = self.run_dir()
        engine = Engine(workflow, run_dir, run_id=run_dir.name, verbose=False,
                        auto_resume=auto_resume,
                        harness_executors=self.harness_executors)
        summary = engine.run()
        return engine, harness_executor, run_dir, summary

    def test_the_second_attempt_runs_and_passes(self):
        _engine, harness_executor, run_dir, _summary = self._run()
        self.assertEqual(len(harness_executor.launched), 2,
                         "a retry budget of one must buy one more execution")
        self.assertEqual(step_statuses(run_dir)[COORD], "passed")

    def test_both_executions_keep_their_own_directory(self):
        _engine, _harness_executor, run_dir, _summary = self._run()
        step = run_dir / "phases" / "01.only-phase" / "01.flaky"
        for attempt in ("01", "02"):
            d = step / "attempts" / attempt
            self.assertTrue((d / "gate.json").exists(), f"{attempt}/gate.json")
            self.assertTrue((d / "brief.md").exists(), f"{attempt}/brief.md")
            self.assertTrue((d / "final.md").exists(), f"{attempt}/final.md")
        self.assertIn("I gave up",
                      (step / "attempts" / "01" / "final.md").read_text(encoding="utf-8"),
                      "the first attempt's evidence was overwritten")
        self.assertIn("DONE",
                      (step / "final.md").read_text(encoding="utf-8"),
                      "the step root must project the latest attempt")

    def test_the_second_brief_says_what_failed_the_first_time(self):
        _engine, _harness_executor, run_dir, _summary = self._run()
        position = (run_dir / "phases" / "01.only-phase" / "01.flaky"
                    / "attempts" / "02" / "position.md").read_text(encoding="utf-8")
        self.assertIn("attempt 2", position)
        self.assertIn("What failed last time (attempt 1)", position)
        self.assertIn("final_message_matches", position)

    def test_the_run_log_names_both_executions_and_how_each_started(self):
        _engine, _harness_executor, run_dir, _summary = self._run()
        starts = [r for r in read_run_log(run_dir)
                  if r["event"] == "attempt_started" and r.get("coord") == COORD]
        self.assertEqual([r["attempt"] for r in starts], [1, 2])
        self.assertEqual([r["payload"]["start_kind"] for r in starts],
                         ["initial", "retry"])

    def test_a_retried_pass_still_caches_on_a_resume(self):
        """The whole reason the fingerprint stopped carrying the attempt. A
        cache key that named the try would miss here and re-run an agent."""
        _engine, harness_executor, run_dir, _summary = self._run()
        launched_first = len(harness_executor.launched)

        repo = self.tmp / "repo"
        workflow = simple_workflow(repo, phases=(
            Phase(name="Only phase", on_step_failure="continue",
                  min_success="all",
                  steps=(flaky_step(retry_policy=RetryPolicy(
                      max=1, on=("gate:final_message_matches",))),)),))
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False,
               resume=True,
               harness_executors=self.harness_executors).run()
        self.assertEqual(len(harness_executor.launched), launched_first,
                         "the resume launched an agent for work that passed")
        self.assertEqual(step_statuses(run_dir)[COORD], "cached")

    def test_a_budget_of_zero_runs_once(self):
        _engine, harness_executor, run_dir, _summary = self._run(retry_max=0, on=())
        self.assertEqual(len(harness_executor.launched), 1)
        self.assertEqual(step_statuses(run_dir)[COORD], "failed")

    def test_auto_resume_does_not_buy_a_retry(self):
        """Each knob bounds its own kind. An auto-resume pass answers a provider that never
        replied; a retry answers a gate that said no."""
        _engine, harness_executor, run_dir, _summary = self._run(retry_max=0, on=(),
                                                                 auto_resume=1)
        self.assertEqual(len(harness_executor.launched), 1)


class TwoFailuresExcludeTheWork(TempCase):

    def _run(self, run_dir=None, resume=False):
        repo = git_repo(self.tmp / "repo") if not resume else self.tmp / "repo"
        if not resume:
            stub_preflight(self)
        workflow = simple_workflow(repo, phases=(
            Phase(name="Only phase", on_step_failure="continue",
                  min_success="all",
                  steps=(flaky_step(retry_policy=RetryPolicy(
                      max=1, on=("gate:final_message_matches",))),)),))
        run_dir = run_dir or self.run_dir()
        engine = Engine(workflow, run_dir, run_id=run_dir.name, verbose=False,
                        resume=resume,
                        harness_executors=self.harness_executors)
        engine.run()
        return run_dir

    def setUp(self) -> None:
        super().setUp()
        self.harness_executor = install_fake_harness_executor(self, FakeHarnessExecutor(
            default=AgentScript(final_text="still not done\n")))

    def test_two_failures_then_an_exclusion_on_the_record(self):
        run_dir = self._run()
        self.assertEqual(len(self.harness_executor.launched), 2,
                         "one initial execution and one retry")
        excluded = [r for r in read_run_log(run_dir)
                    if r["event"] == "work_excluded"]
        self.assertEqual(len(excluded), 1)
        self.assertIn("2 failed executions", excluded[0]["payload"]["reason"])
        self.assertEqual(step_statuses(run_dir)[COORD], "failed")

    def test_a_resume_launches_nothing_for_excluded_work(self):
        run_dir = self._run()
        after_first = len(self.harness_executor.launched)
        self._run(run_dir=run_dir, resume=True)
        self.assertEqual(len(self.harness_executor.launched), after_first,
                         "a resume must not re-run work that failed twice "
                         "unchanged")
        refusals = [r for r in read_run_log(run_dir)
                    if r["event"] == "attempt_finished"
                    and r["payload"].get("status") in ("failed", "quarantined")
                    and "failed executions" in (r["payload"].get("error") or "")]
        self.assertTrue(refusals, "the refusal must say why on the record")


class TheRefusals(TempCase):
    """`retry.should_retry` is pure, so every refusal is checked directly."""

    def setUp(self) -> None:
        super().setUp()
        self.state = RunLog.replay(self.tmp / "empty-run")

    def _report(self, *failed: str) -> GateReport:
        return GateReport(coord=COORD, passed=not failed, checks=[
            GateResult(name, passed=False) for name in failed])

    def _decide(self, *, step=None, status="failed", error=None,
                report=None, abort_victim=False, aborted=False,
                auto_resume=0):
        step = step or flaky_step(retry_policy=RetryPolicy(
            max=1, on=("gate:final_message_matches",)))
        return retry.should_retry(
            step, status=status, error=error,
            report=report if report is not None else self._report(
                "final_message_matches"),
            abort_victim=abort_victim, aborted=aborted, state=self.state,
            coord=COORD, fingerprint="f" * 64, auto_resume=auto_resume)

    def test_the_plain_case_is_allowed(self):
        allowed, why = self._decide()
        self.assertTrue(allowed, why)

    def test_a_forbidden_check_beats_every_selector(self):
        step = flaky_step(retry_policy=RetryPolicy(
            max=1, on=("gate:final_message_matches", "gate:command_exit")))
        allowed, why = self._decide(
            step=step, report=self._report("command_exit", "ownership"))
        self.assertFalse(allowed)
        self.assertIn("gate:ownership", why)
        self.assertIn("did the wrong thing", why)

    def test_every_failure_must_be_covered(self):
        """One matching check must not authorise a retry of the unrelated
        failure standing beside it."""
        allowed, why = self._decide(
            report=self._report("final_message_matches", "tree_clean"))
        self.assertFalse(allowed)
        self.assertIn("gate:tree_clean", why)
        self.assertIn("not in retry.on", why)

    def test_an_agent_error_needs_its_own_token(self):
        allowed, why = self._decide(error="ConnectionResetError: boom")
        self.assertFalse(allowed, "agent_error was not listed in retry.on")
        self.assertIn("agent_error", why)

    def test_a_structural_provider_refusal_is_not_repeated(self):
        step = flaky_step(retry_policy=RetryPolicy(
            max=1, on=("agent_error", "gate:final_message_matches")))
        allowed, why = self._decide(
            step=step,
            error="AuthenticationError: Incorrect API key provided")
        self.assertFalse(allowed)
        self.assertIn("refused structurally", why)

    def test_a_transient_provider_fault_under_agent_error_is_allowed(self):
        from fixtures.real_errors import SCOUT2_RATE_LIMIT_RESULT_ERROR
        step = flaky_step(retry_policy=RetryPolicy(
            max=1, on=("agent_error", "gate:final_message_matches")))
        allowed, why = self._decide(step=step,
                                    error=SCOUT2_RATE_LIMIT_RESULT_ERROR)
        self.assertTrue(allowed, why)

    def test_a_deferred_step_belongs_to_auto_resume(self):
        allowed, why = self._decide(status="deferred")
        self.assertFalse(allowed)
        self.assertIn("auto-resume owns it", why)

    def test_an_abort_victim_is_not_retried(self):
        allowed, why = self._decide(abort_victim=True)
        self.assertFalse(allowed)
        self.assertIn("abort", why)

    def test_an_aborted_run_retries_nothing(self):
        allowed, why = self._decide(aborted=True)
        self.assertFalse(allowed)
        self.assertIn("the run aborted", why)

    def test_a_deterministic_step_is_never_retried(self):
        step = Step(id="merge-it", kind="merge", merge_branch="feature",
                    retry=RetryPolicy(max=1, on=("gate:command_exit",)))
        allowed, why = self._decide(step=step,
                                    report=self._report("command_exit"))
        self.assertFalse(allowed)
        self.assertIn("deterministic", why)

    def test_the_tokens_name_every_independent_failure(self):
        tokens = retry.failure_tokens(
            status="failed", error="something went wrong", report=self._report(
                "tree_clean", "command_exit"), kind="agent")
        self.assertEqual(tokens, {"agent_error",
                                  "gate:tree_clean", "gate:command_exit"})


class TheWorkflowRefusesARetryItCannotSpend(TempCase):

    def _workflow(self, step: Step):
        return simple_workflow(self.tmp / "repo", phases=(
            Phase(name="Only phase", steps=(step,)),))

    def test_a_budget_with_no_selectors_is_a_fault(self):
        step = flaky_step(retry_policy=RetryPolicy(max=1, on=()))
        with self.assertRaises(WorkflowError) as caught:
            validate(self._workflow(step))
        self.assertIn("empty retry.on", str(caught.exception))

    def test_a_retry_on_a_command_step_is_a_fault(self):
        step = Step(id="build", kind="command", command="npm run build",
                    retry=RetryPolicy(max=1, on=("gate:command_exit",)))
        with self.assertRaises(WorkflowError) as caught:
            validate(self._workflow(step))
        self.assertIn("Only an agent step retries", str(caught.exception))

    def test_an_unknown_token_is_a_fault(self):
        step = flaky_step(retry_policy=RetryPolicy(max=1, on=("flaky",)))
        with self.assertRaises(WorkflowError) as caught:
            validate(self._workflow(step))
        self.assertIn("not understood", str(caught.exception))

    def test_an_unknown_gate_name_is_a_fault(self):
        step = flaky_step(retry_policy=RetryPolicy(max=1, on=("gate:nope",)))
        with self.assertRaises(WorkflowError) as caught:
            validate(self._workflow(step))
        self.assertIn("unknown check 'nope'", str(caught.exception))

    def test_a_negative_budget_is_a_fault(self):
        step = flaky_step(retry_policy=RetryPolicy(max=-1, on=("timeout",)))
        with self.assertRaises(WorkflowError) as caught:
            validate(self._workflow(step))
        self.assertIn("retry.max must be at least 0", str(caught.exception))

    def test_a_boolean_budget_is_a_fault(self):
        step = flaky_step(retry_policy=RetryPolicy(max=True, on=("timeout",)))
        with self.assertRaises(WorkflowError) as caught:
            validate(self._workflow(step))
        self.assertIn("must be an integer, got the boolean",
                      str(caught.exception))


class AnAbortStopsAPendingRetry(TempCase):
    """A step's own failure does not abort the phase until its last attempt.
    A sibling's failure aborts immediately, and the step still in flight is
    killed rather than retried."""

    def test_the_policy_waits_for_the_last_attempt_of_the_same_step(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        harness_executor = install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript(
            sequence=[{"final_text": "not done\n"}, {"final_text": "DONE\n"}])))
        workflow = simple_workflow(repo, max_parallel=1, phases=(
            Phase(name="Only phase", on_step_failure="abort", min_success="all",
                  steps=(flaky_step(retry_policy=RetryPolicy(
                      max=1, on=("gate:final_message_matches",))),)),))
        run_dir = self.run_dir()
        engine = Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors)
        engine.run()

        self.assertEqual(len(harness_executor.launched), 2,
                         "attempt 1's failure aborted the run its own retry "
                         "was about to rescue")
        self.assertFalse(engine._abort.is_set())
        self.assertEqual(step_statuses(run_dir)[COORD], "passed")

    def test_a_sibling_abort_kills_the_step_instead_of_retrying_it(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        holder = {"polls": 0}

        def hold_in_flight():
            """Keep this agent in flight so the sibling's failure catches it
            there. The engine's own abort check kills it and records it as a
            victim; returning None here would let it finish normally and reach
            a verdict instead.

            The poll cap is a safety valve. The sibling fails on its first
            poll, so the abort arrives long before it.
            """
            holder["polls"] += 1
            return "running" if holder["polls"] <= 10 else None

        harness_executor = install_fake_harness_executor(self, FakeHarnessExecutor(scripts={
            "01.flaky": AgentScript(final_text="not done\n",
                                    on_poll=hold_in_flight),
            "02.doomed": AgentScript(final_text="also not done\n"),
        }, default=AgentScript()))
        workflow = simple_workflow(repo, max_parallel=2, phases=(
            Phase(name="Only phase", on_step_failure="abort", min_success="any",
                  steps=(flaky_step(retry_policy=RetryPolicy(
                      max=1, on=("gate:final_message_matches",))),
                         agent_step("doomed"))),))
        run_dir = self.run_dir()
        engine = Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors)

        engine.run()

        self.assertTrue(engine._abort.is_set())
        self.assertEqual(step_statuses(run_dir)[COORD], "deferred",
                         "an abort victim reached no verdict")
        decisions = [r["payload"].get("retry_decision")
                     for r in read_run_log(run_dir)
                     if r["event"] in ("attempt_finished", "retry_decided")
                     and r.get("coord") == COORD]
        self.assertTrue(
            any(d and "abort" in d for d in decisions if d),
            f"no refusal named the abort: {decisions}")
        self.assertEqual(harness_executor.script_for(COORD).launches, 1,
                         "the killed step must not be launched again")


class TheRootProjectionNeverMixesTwoAttempts(TempCase):
    """The step directory holds a copy of the latest attempt's small files, so
    every reader that looks where it always looked finds them. A copy left over
    from an earlier attempt would describe that attempt as the latest."""

    def _workflow(self, repo):
        return simple_workflow(repo, phases=(
            Phase(name="Only phase", on_step_failure="continue",
                  min_success="all",
                  steps=(flaky_step(retry_policy=RetryPolicy(
                      max=1, on=("gate:final_message_matches",))),)),))

    def test_a_crashed_second_attempt_leaves_no_stale_root_files(self):
        """Attempt 1 writes a final message and a result. Attempt 2 fails
        before producing either. The root must not still show attempt 1's."""
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)

        from ohflow import harness_executor as ohexecutor
        harness_executor = FakeHarnessExecutor(default=AgentScript(
            final_text="attempt one was here\n"))
        install_fake_harness_executor(self, harness_executor)
        original_launch = harness_executor.launch

        def launch_then_break(spec, out_dir):
            if harness_executor.launched.count(spec["coord"]) >= 1:
                raise ohexecutor.AgentLaunchError("the harness executor died")
            return original_launch(spec, out_dir)

        harness_executor.launch = launch_then_break

        run_dir = self.run_dir()
        Engine(self._workflow(repo), run_dir, run_id=run_dir.name,
               verbose=False,
               harness_executors=self.harness_executors).run()

        step = run_dir / "phases" / "01.only-phase" / "01.flaky"
        self.assertTrue((step / "attempts" / "01" / "final.md").exists(),
                        "attempt 1's evidence must survive in its own directory")
        self.assertIn("attempt one was here",
                      (step / "attempts" / "01" / "final.md").read_text(
                          encoding="utf-8"))
        for name in ("final.md", "result.json"):
            self.assertFalse(
                (step / name).exists(),
                f"the root still shows attempt 1's {name} as the latest, "
                f"although attempt 2 produced none")


class AnAttemptNumberIsReservedBeforeAnyFileIsWritten(TempCase):
    """Preparing the directory first left a kill during preparation with a
    non-empty `attempts/NN` and no `attempt_started`, so the next resume chose NN
    again and refused it for ever."""

    def test_attempt_started_is_logged_before_the_directory_is_written(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript(final_text="DONE\n")))
        workflow = simple_workflow(repo, phases=(
            Phase(name="Only phase", steps=(agent_step("flaky"),)),))
        run_dir = self.run_dir()
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors).run()
        events = [r["event"] for r in read_run_log(run_dir)
                  if r.get("coord") == COORD]
        self.assertEqual(events[0], "attempt_started")

    def test_a_resume_after_an_interrupted_preparation_takes_a_new_number(self):
        """The run log holds a start for attempt 1 and no finish, and
        `attempts/01` holds whatever preparation managed to write. The resume
        must allocate attempt 2 rather than refuse attempt 1 for ever."""
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        harness_executor = install_fake_harness_executor(self, FakeHarnessExecutor(
            default=AgentScript(final_text="DONE\n")))
        workflow = simple_workflow(repo, phases=(
            Phase(name="Only phase", steps=(agent_step("flaky"),)),))
        run_dir = self.run_dir()

        # What a kill during preparation leaves behind.
        engine = Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors)
        engine.run_dir.mkdir(parents=True, exist_ok=True)
        engine.run_log.append("run_started", payload={
            "run_id": run_dir.name, "workflow": workflow.name, "meta": {}})
        engine.run_log.append("attempt_started", coord=COORD, attempt=1, payload={
            "step_id": "flaky", "kind": "agent", "fingerprint": "unknown",
            "start_kind": "initial"})
        half = engine.attempt_dir(COORD, 1)
        half.mkdir(parents=True, exist_ok=True)
        (half / "brief.md").write_text("half a brief", encoding="utf-8")

        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False,
               resume=True,
               harness_executors=self.harness_executors).run()

        self.assertEqual(step_statuses(run_dir)[COORD], "passed")
        step = run_dir / "phases" / "01.only-phase" / "01.flaky"
        self.assertEqual((half / "brief.md").read_text(encoding="utf-8"),
                         "half a brief",
                         "the interrupted attempt's directory was overwritten")
        self.assertTrue((step / "attempts" / "02" / "final.md").exists(),
                        "the resume must write into a new attempt directory")
        self.assertEqual(len(harness_executor.launched), 1)


class AFaultOnASecondAttemptDoesNotRewriteTheFirst(TempCase):
    """`_guarded_step` recorded every fault as attempt 1. `replay` matches a
    finish on the pair (coordinate, attempt), so a fault while preparing
    attempt 2 overwrote execution 1's record and left execution 2 open."""

    def test_a_preparation_fault_on_attempt_two_closes_attempt_two(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript(
            final_text="not done\n")))
        workflow = simple_workflow(repo, phases=(
            Phase(name="Only phase", on_step_failure="continue",
                  min_success="all",
                  steps=(flaky_step(retry_policy=RetryPolicy(
                      max=1, on=("gate:final_message_matches",))),)),))
        run_dir = self.run_dir()
        engine = Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors)

        original = engine._prepare_step_dir
        calls = {"n": 0}

        def fail_on_the_second(*a, **kw):
            calls["n"] += 1
            if calls["n"] == 2:
                raise OSError("the disk went away while preparing attempt 2")
            return original(*a, **kw)

        engine._prepare_step_dir = fail_on_the_second
        engine.run()

        state = RunLog.replay(run_dir)
        fp = state.steps[COORD].fingerprint
        rows = attempts.executions(state, COORD, fp)
        self.assertEqual([r["attempt"] for r in rows], [1, 2])
        self.assertNotEqual(rows[0]["status"], "running",
                            "attempt 1 was reopened by attempt 2's fault")
        self.assertEqual(rows[1]["status"], "failed",
                         "attempt 2 was left open by its own fault")
        self.assertIn("the disk went away", rows[1].get("error") or
                      state.steps[COORD].error or "")
        self.assertEqual(attempts.judged_failures(state, COORD, fp), 2,
                         "two executions failed, and both must be counted")
        self.assertTrue(attempts.excluded(state, COORD, fp))

    def test_attempt_one_keeps_its_evidence(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript(
            final_text="attempt one was here\n")))
        workflow = simple_workflow(repo, phases=(
            Phase(name="Only phase", on_step_failure="continue",
                  min_success="all",
                  steps=(flaky_step(retry_policy=RetryPolicy(
                      max=1, on=("gate:final_message_matches",))),)),))
        run_dir = self.run_dir()
        engine = Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors)
        original = engine._prepare_step_dir
        calls = {"n": 0}

        def fail_on_the_second(*a, **kw):
            calls["n"] += 1
            if calls["n"] == 2:
                raise OSError("the disk went away while preparing attempt 2")
            return original(*a, **kw)

        engine._prepare_step_dir = fail_on_the_second
        engine.run()

        first = (run_dir / "phases" / "01.only-phase" / "01.flaky"
                 / "attempts" / "01" / "final.md")
        self.assertIn("attempt one was here",
                      first.read_text(encoding="utf-8"))


class MixedFailuresStillExclude(TempCase):
    """One structural failure and one transient deferral is two failures of
    unchanged work. The engine must reach the same verdict the attempt history does."""

    def test_a_structural_failure_then_a_transient_one_excludes(self):
        from fixtures.real_errors import SCOUT2_RATE_LIMIT_RESULT_ERROR
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript(sequence=[
            {"final_text": "not done\n"},
            {"final_text": "", "error": SCOUT2_RATE_LIMIT_RESULT_ERROR},
        ])))
        workflow = simple_workflow(repo, phases=(
            Phase(name="Only phase", on_step_failure="continue",
                  min_success="all",
                  steps=(flaky_step(retry_policy=RetryPolicy(
                      max=1, on=("gate:final_message_matches",))),)),))
        run_dir = self.run_dir()
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False,
               auto_resume=1,
               harness_executors=self.harness_executors).run()

        state = RunLog.replay(run_dir)
        fp = state.steps[COORD].fingerprint
        self.assertEqual(attempts.judged_failures(state, COORD, fp), 1)
        self.assertEqual(attempts.transient_deferrals(state, COORD, fp), 1)
        self.assertTrue(attempts.excluded(state, COORD, fp),
                        "two failures of unchanged work, one of each kind")
        excluded = [r for r in read_run_log(run_dir)
                    if r["event"] == "work_excluded"]
        self.assertEqual(len(excluded), 1)
        self.assertIn("1 judged", excluded[0]["payload"]["reason"])
        self.assertIn("1 transient", excluded[0]["payload"]["reason"])


class ATimeoutSelectorStandsOnItsOwn(TempCase):
    """The engine composes the error text for an execution timeout: its own sentence
    plus the agent's last words. A workflow selecting `timeout` must not have to
    select `agent_error` for a string the engine wrote."""

    def test_an_execution_timeout_names_timeout_and_not_agent_error(self):
        tokens = retry.failure_tokens(
            status="timeout",
            error="execution timeout 60s exceeded\nthe agent's last words",
            report=GateReport(coord=COORD, passed=True, checks=[]),
            kind="agent")
        self.assertEqual(tokens, {"timeout"})

    def test_a_gate_that_failed_beside_the_timeout_still_needs_its_selector(self):
        tokens = retry.failure_tokens(
            status="timeout", error="execution timeout 60s exceeded",
            report=GateReport(coord=COORD, passed=False, checks=[
                GateResult("final_message_matches", passed=False)]),
            kind="agent")
        self.assertEqual(tokens, {"timeout", "gate:final_message_matches"})

    def test_a_timeout_whose_text_carries_a_refusal_is_not_repeated(self):
        step = flaky_step(retry_policy=RetryPolicy(max=1, on=("timeout",)))
        allowed, why = retry.should_retry(
            step, status="timeout",
            error="execution timeout 60s exceeded\nAuthenticationError: bad key",
            report=GateReport(coord=COORD, passed=True, checks=[]),
            abort_victim=False, aborted=False,
            state=RunLog.replay(self.tmp / "empty"), coord=COORD,
            fingerprint="f" * 64)
        self.assertFalse(allowed)
        self.assertIn("refused structurally", why)

    def test_a_plain_timeout_is_retried_when_selected(self):
        step = flaky_step(retry_policy=RetryPolicy(max=1, on=("timeout",)))
        allowed, why = retry.should_retry(
            step, status="timeout",
            error="execution timeout 60s exceeded\nthe agent's last words",
            report=GateReport(coord=COORD, passed=True, checks=[]),
            abort_victim=False, aborted=False,
            state=RunLog.replay(self.tmp / "empty"), coord=COORD,
            fingerprint="f" * 64)
        self.assertTrue(allowed, why)


class TheDecisionIsAlwaysOnTheRecord(TempCase):

    def test_a_passing_step_records_why_it_did_not_retry(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript(final_text="DONE\n")))
        workflow = simple_workflow(repo, phases=(
            Phase(name="Only phase", steps=(flaky_step(
                retry_policy=RetryPolicy(max=1,
                                         on=("gate:final_message_matches",))),)),))
        run_dir = self.run_dir()
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors).run()
        decision = RunLog.replay(run_dir).steps[COORD].retry_decision
        self.assertIn("not a failure", decision)

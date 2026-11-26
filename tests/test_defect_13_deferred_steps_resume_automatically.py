"""Defect 13: a rate-limited step waited for a human to type `--resume`.

What went wrong. `ohflow` already tells a transient failure apart from a
rejection: the step is recorded `deferred`, the phase settles `deferred`, and
the run ends `paused` rather than `failed`. Recovering it was still manual, and
in the run that taught this lesson a scout sat 1032 seconds inside the SDK's own
retry chain and died on a rate limit while nine other steps waited.

What is asserted here. With `auto_resume` above zero, a phase that settled
`deferred` waits out the cooldown it already computed and re-runs exactly the
steps that were deferred. A step that passed beside them is not launched again.
Each auto-resume pass is counted in the run log and the count never refreshes, so the loop
is bounded whatever a provider does.

The default is zero, which is today's behaviour exactly: the run pauses and a
human resumes it. `test_defect_02` is the guard for that, and every one of its
behaviour assertions still holds unchanged. One assertion in it was rewritten,
and only that one: it counted `attempt_finished` events, and the engine now writes
the verdict twice for one execution, once when the verdict is reached and once
again carrying the retry decision, which is known only afterwards. Both carry
the same attempt number, so the replay updates one execution.

And the bounds, which matter more than the auto-resume passes:

  * an auto-resume pass never grants a fresh retry budget, and a retry never grants an auto-resume pass
  * one structural failure and one transient deferral is two failures of
    unchanged work, and the work is excluded
  * a manual `--resume` recovers a deferral at the defaults, and the second
    unchanged deferral excludes the work
  * an abort during an auto-resume pass ends the phase
"""

from __future__ import annotations

import datetime as _dt
import time as _time
from dataclasses import replace
from unittest import mock

from fixtures.real_errors import SCOUT2_RATE_LIMIT_RESULT_ERROR
from ohflow import attempts
from ohflow import engine as ohengine
from ohflow.engine import Engine
from ohflow.run_log import RunLog
from ohflow.workflow import Phase, Workflow, RetryPolicy
from support import (FakeHarnessExecutor, TempCase, AgentScript, git_repo,
                     install_fake_harness_executor, read_run_log, simple_workflow,
                     step_statuses, stub_preflight, agent_step)

DOOMED = "01.only-phase/01.doomed"
BESIDE = "01.only-phase/02.beside"

#: The agent answers with a real rate limit first and a real result second.
RECOVERS = [{"final_text": "", "error": SCOUT2_RATE_LIMIT_RESULT_ERROR},
            {"final_text": "DONE\n"}]

#: The agent never gets a turn.
NEVER = [{"final_text": "", "error": SCOUT2_RATE_LIMIT_RESULT_ERROR}]


def _workflow(repo, *, auto_resume: int = 0, steps=None, retry_max: int = 0):
    step = agent_step("doomed")
    if retry_max:
        step = replace(step, retry=RetryPolicy(
            max=retry_max, on=("agent_error", "gate:final_message_matches")))
    steps = steps if steps is not None else (step, agent_step("beside"))
    workflow = simple_workflow(repo, phases=(
        Phase(name="Only phase", steps=tuple(steps),
              on_step_failure="continue", min_success="all"),))
    return replace(workflow, auto_resume=auto_resume)


class EngineClock:
    """The engine's `time`, where a sleep moves the clock instead of waiting."""

    def __init__(self) -> None:
        self.slept = 0.0

    def time(self) -> float:
        return _time.time() + self.slept

    def sleep(self, seconds: float) -> None:
        self.slept += max(seconds, 0.0)

    def __getattr__(self, name):
        return getattr(_time, name)


class AnAutoResumeRecoversADeferredStep(TempCase):

    def _run(self, *, auto_resume: int, sequence=RECOVERS):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        harness_executor = install_fake_harness_executor(self, FakeHarnessExecutor(
            scripts={"01.doomed": AgentScript(sequence=sequence)},
            default=AgentScript(final_text="DONE\n")))
        run_dir = self.run_dir()
        engine = Engine(_workflow(repo, auto_resume=auto_resume), run_dir,
                        run_id=run_dir.name, verbose=False,
                        harness_executors=self.harness_executors)
        summary = engine.run()
        return engine, harness_executor, run_dir, summary

    def test_one_auto_resume_recovers_the_step_and_finishes_the_run(self):
        _engine, harness_executor, run_dir, summary = self._run(auto_resume=1)
        self.assertEqual(step_statuses(run_dir)[DOOMED], "passed")
        self.assertEqual(summary["status"], "finished")
        self.assertEqual(summary["deferred"], [])
        resumed = [r for r in read_run_log(run_dir)
                   if r["event"] == "phase_resumed"]
        self.assertEqual(len(resumed), 1)
        self.assertEqual(resumed[0]["payload"]["pass"], 1)
        self.assertEqual(resumed[0]["payload"]["steps"], [DOOMED])

    def test_the_step_beside_it_is_not_launched_again(self):
        _engine, harness_executor, run_dir, _summary = self._run(auto_resume=1)
        self.assertEqual(harness_executor.launched.count(BESIDE), 1,
                         "an auto-resume pass must re-run only what was deferred")
        self.assertEqual(harness_executor.launched.count(DOOMED), 2)
        self.assertEqual(step_statuses(run_dir)[BESIDE], "passed")

    def test_the_auto_resume_is_recorded_as_its_own_kind_of_start(self):
        _engine, _harness_executor, run_dir, _summary = self._run(auto_resume=1)
        starts = [r["payload"]["start_kind"] for r in read_run_log(run_dir)
                  if r["event"] == "attempt_started" and r.get("coord") == DOOMED]
        self.assertEqual(starts, ["initial", "auto_resume"])

    def test_zero_auto_resumes_pauses_the_run_as_before(self):
        _engine, harness_executor, run_dir, summary = self._run(auto_resume=0)
        self.assertEqual(step_statuses(run_dir)[DOOMED], "deferred")
        self.assertEqual(summary["status"], "paused")
        self.assertEqual(harness_executor.launched.count(DOOMED), 1)
        self.assertEqual([r for r in read_run_log(run_dir)
                          if r["event"] == "phase_resumed"], [])


class TheAutoResumeBudgetIsBoundedAndNeverRefreshes(TempCase):

    def _run(self, *, auto_resume: int):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        harness_executor = install_fake_harness_executor(self, FakeHarnessExecutor(
            scripts={"01.doomed": AgentScript(sequence=NEVER)},
            default=AgentScript(final_text="DONE\n")))
        run_dir = self.run_dir()
        engine = Engine(_workflow(repo, auto_resume=auto_resume), run_dir,
                        run_id=run_dir.name, verbose=False,
                        harness_executors=self.harness_executors)
        summary = engine.run()
        return engine, harness_executor, run_dir, summary

    def test_a_provider_that_never_answers_stops_at_the_exclusion(self):
        """`auto_resume=2` does not buy three launches. Two failed executions
        of unchanged work exclude it, and exclusion is checked first."""
        _engine, harness_executor, run_dir, summary = self._run(auto_resume=2)
        self.assertEqual(harness_executor.launched.count(DOOMED), 2,
                         "the second unchanged deferral excludes the work")
        excluded = [r for r in read_run_log(run_dir)
                    if r["event"] == "work_excluded"]
        self.assertEqual(len(excluded), 1)
        self.assertIn("2 failed executions", excluded[0]["payload"]["reason"])
        self.assertEqual(summary["status"], "paused")

    def test_a_resume_after_the_auto_resumes_are_spent_launches_nothing(self):
        _engine, harness_executor, run_dir, _summary = self._run(auto_resume=2)
        after = harness_executor.launched.count(DOOMED)
        repo = self.tmp / "repo"
        Engine(_workflow(repo, auto_resume=2), run_dir, run_id=run_dir.name,
               verbose=False, resume=True,
               harness_executors=self.harness_executors).run()
        self.assertEqual(harness_executor.launched.count(DOOMED), after,
                         "excluded work must not be started by a resume")


class ManualRecoveryStillWorksAtTheDefaults(TempCase):
    """`auto_resume` defaults to zero, and a human resuming is still allowed
    one recovery. A single bound of `1 + retry.max + auto_resume` would have
    been 1 here and made `--resume` a no-op for a rate-limited step."""

    def setUp(self) -> None:
        super().setUp()
        self.repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        self.run_dir_path = self.run_dir()

    def _go(self, sequence, *, resume=False):
        engine = Engine(_workflow(self.repo, auto_resume=0), self.run_dir_path,
                        run_id=self.run_dir_path.name, verbose=False,
                        resume=resume,
                        harness_executors=self.harness_executors)
        return engine.run()

    def test_a_manual_resume_recovers_one_deferral(self):
        harness_executor = install_fake_harness_executor(self, FakeHarnessExecutor(
            scripts={"01.doomed": AgentScript(sequence=RECOVERS)},
            default=AgentScript(final_text="DONE\n")))
        self.assertEqual(self._go(RECOVERS)["status"], "paused")
        self.assertEqual(step_statuses(self.run_dir_path)[DOOMED], "deferred")

        summary = self._go(RECOVERS, resume=True)
        self.assertEqual(step_statuses(self.run_dir_path)[DOOMED], "passed")
        self.assertEqual(summary["status"], "finished")
        self.assertEqual(harness_executor.launched.count(DOOMED), 2)
        self.assertEqual(harness_executor.launched.count(BESIDE), 1,
                         "the step that passed must stay cached")

    def test_the_second_unchanged_deferral_excludes_the_work(self):
        harness_executor = install_fake_harness_executor(self, FakeHarnessExecutor(
            scripts={"01.doomed": AgentScript(sequence=NEVER)},
            default=AgentScript(final_text="DONE\n")))
        self._go(NEVER)
        self._go(NEVER, resume=True)
        self.assertEqual(harness_executor.launched.count(DOOMED), 2)

        state = RunLog.replay(self.run_dir_path)
        fp = state.steps[DOOMED].fingerprint
        self.assertTrue(attempts.excluded(state, DOOMED, fp))

        self._go(NEVER, resume=True)
        self.assertEqual(harness_executor.launched.count(DOOMED), 2,
                         "a third manual resume must launch nothing")


class TheTwoBudgetsStayApart(TempCase):

    def test_a_retry_and_an_auto_resume_each_answer_their_own_failure(self):
        """The step fails its gate, is retried, then hits a rate limit and is
        auto-resumed. Two kinds of failure, two kinds of recovery, and the totals do
        not multiply."""
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        harness_executor = install_fake_harness_executor(self, FakeHarnessExecutor(
            scripts={"01.doomed": AgentScript(sequence=[
                {"final_text": "not done\n"},
                {"final_text": "", "error": SCOUT2_RATE_LIMIT_RESULT_ERROR},
                {"final_text": "DONE\n"},
            ])},
            default=AgentScript(final_text="DONE\n")))
        run_dir = self.run_dir()
        Engine(_workflow(repo, auto_resume=1, retry_max=1), run_dir,
               run_id=run_dir.name, verbose=False,
               harness_executors=self.harness_executors).run()

        starts = [r["payload"]["start_kind"] for r in read_run_log(run_dir)
                  if r["event"] == "attempt_started" and r.get("coord") == DOOMED]
        self.assertEqual(starts, ["initial", "retry"],
                         "the auto-resume pass must be refused: two failures of unchanged "
                         "work exclude it before a third execution")
        state = RunLog.replay(run_dir)
        fp = state.steps[DOOMED].fingerprint
        self.assertEqual(attempts.judged_failures(state, DOOMED, fp), 1)
        self.assertEqual(attempts.transient_deferrals(state, DOOMED, fp), 1)
        self.assertTrue(attempts.excluded(state, DOOMED, fp))
        self.assertEqual(harness_executor.launched.count(DOOMED), 2)


class AnAbortEndsAnAutoResume(TempCase):

    def test_a_phase_that_aborts_is_not_swept(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        harness_executor = install_fake_harness_executor(self, FakeHarnessExecutor(
            scripts={"01.doomed": AgentScript(sequence=NEVER),
                     "02.beside": AgentScript(final_text="wrong\n")},
            default=AgentScript(final_text="DONE\n")))
        workflow = replace(
            simple_workflow(repo, phases=(
                Phase(name="Only phase",
                      steps=(agent_step("doomed"), agent_step("beside")),
                      on_step_failure="abort", min_success="all"),)),
            auto_resume=2)
        run_dir = self.run_dir()
        engine = Engine(workflow, run_dir, run_id=run_dir.name, verbose=False,
                        max_parallel=1,
                        harness_executors=self.harness_executors)
        engine.run()

        self.assertTrue(engine._abort.is_set())
        self.assertEqual([r for r in read_run_log(run_dir)
                          if r["event"] == "phase_resumed"], [],
                         "a phase with a hard failure must not auto-resume")
        self.assertEqual(harness_executor.launched.count(DOOMED), 1)


class TheCooldownSurvivesARestart(TempCase):
    """`_cooldown_until` and the transient hit count lived in the supervisor's
    memory. A run killed after a rate limit and resumed in a new process would
    have asked the provider the question it was just rate-limited for."""

    def _deferred_run(self, backoff_s: int):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(
            scripts={"01.doomed": AgentScript(sequence=NEVER)},
            default=AgentScript(final_text="DONE\n")))
        workflow = replace(_workflow(repo, auto_resume=0),
                           transient_backoff_s=backoff_s)
        run_dir = self.run_dir()
        engine = Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors)
        engine.run()
        return engine, workflow, run_dir

    def test_the_wake_time_is_written_into_the_run_log(self):
        _engine, _workflow_, run_dir = self._deferred_run(60)
        finished = [r for r in read_run_log(run_dir)
                    if r["event"] == "attempt_finished"
                    and r.get("coord") == DOOMED
                    and r["payload"].get("status") == "deferred"]
        self.assertTrue(finished)
        payload = finished[0]["payload"]
        self.assertIn("cooldown_until", payload)
        self.assertEqual(payload["transient_hits"], 1)
        # An absolute time, not a duration: a duration would start again from
        # the moment of the resume.
        self.assertRegex(payload["cooldown_until"],
                         r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_a_new_process_takes_the_cooldown_back_out_of_the_run_log(self):
        import time as _time
        _engine, workflow, run_dir = self._deferred_run(600)
        state = RunLog.replay(run_dir)
        self.assertIsNotNone(state.cooldown_until)
        self.assertEqual(state.transient_hits, 1)

        resumed = Engine(workflow, run_dir, run_id=run_dir.name, verbose=False,
                         resume=True,
                         harness_executors=self.harness_executors)
        resumed.state = RunLog.replay(run_dir)
        resumed._restore_cooldown()
        self.assertGreater(resumed._cooldown_until, _time.time(),
                           "the resumed run starts with no cooldown at all")
        self.assertEqual(resumed._transient_hits, 1,
                         "the doubling must continue where it stopped, not "
                         "restart at the base")

    def test_a_resume_launches_nothing_before_the_wake_time_the_run_log_recorded(self):
        """The resume itself takes the cooldown back. The engine runs on a clock
        that a sleep moves forward, so the 600 s cooldown costs no wall time."""
        _engine, workflow, run_dir = self._deferred_run(600)
        wake = _dt.datetime.strptime(
            RunLog.replay(run_dir).cooldown_until, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=_dt.timezone.utc).timestamp()

        clock = EngineClock()
        harness_executor = self.harness_executors("pi")
        launch = harness_executor.launch
        launched_at = []

        def launch_on_the_engine_clock(spec, out_dir):
            launched_at.append(clock.time())
            return launch(spec, out_dir)

        harness_executor.launch = launch_on_the_engine_clock
        with mock.patch.object(ohengine, "time", clock):
            Engine(workflow, run_dir, run_id=run_dir.name, verbose=False,
                   resume=True,
                   harness_executors=self.harness_executors).run()

        self.assertEqual(len(launched_at), 1,
                         "the resume must launch the deferred step")
        self.assertGreaterEqual(launched_at[0], wake,
                                "the resume asked the provider again before the "
                                "cooldown it recorded had passed")

    def test_a_zero_backoff_records_no_cooldown(self):
        _engine, _workflow_, run_dir = self._deferred_run(0)
        state = RunLog.replay(run_dir)
        self.assertIsNone(state.cooldown_until)
        self.assertEqual(state.transient_hits, 0)


class TheAutoResumeCountSurvivesARestart(TempCase):

    def test_a_resumed_phase_counts_the_auto_resumes_it_already_took(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(
            scripts={"01.doomed": AgentScript(sequence=NEVER)},
            default=AgentScript(final_text="DONE\n")))
        workflow = _workflow(repo, auto_resume=1)
        run_dir = self.run_dir()
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors).run()

        state = RunLog.replay(run_dir)
        self.assertEqual(state.phases["01.only-phase"]["auto_resumes"], 1,
                         "the phase must record how many auto-resume passes it took")

        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False,
               resume=True,
               harness_executors=self.harness_executors).run()
        resumed = [r["payload"]["pass"] for r in read_run_log(run_dir)
                   if r["event"] == "phase_resumed"]
        self.assertEqual(resumed, [1],
                         "a resumed phase must not announce auto-resume pass 1 again")


class TheSummaryReportsTheLimitTheRunUsed(TempCase):
    """`summary.json` reported `workflow.auto_resume`, so every run started with
    `--auto-resume` described a limit it had not used."""

    def _summary(self, *, workflow_value: int, cli_value: int | None):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript(final_text="DONE\n")))
        run_dir = self.run_dir()
        return Engine(_workflow(repo, auto_resume=workflow_value), run_dir,
                      run_id=run_dir.name, verbose=False,
                      auto_resume=cli_value,
                      harness_executors=self.harness_executors).run()

    def test_the_cli_override_is_what_the_summary_says(self):
        summary = self._summary(workflow_value=0, cli_value=2)
        self.assertEqual(summary["auto_resume"], 2)

    def test_the_workflow_value_is_reported_when_no_override_was_given(self):
        summary = self._summary(workflow_value=1, cli_value=None)
        self.assertEqual(summary["auto_resume"], 1)


class TheCliCarriesTheFlag(TempCase):

    def test_a_negative_value_is_a_fault(self):
        from ohflow.cli import main as cli_main
        from support import quiet
        workflow_path = self.tmp / "tiny_workflow.py"
        workflow_path.write_text(
            "from pathlib import Path\n"
            "from ohflow.workflow import Phase, Workflow, Step\n"
            "def build(args):\n"
            "    step = Step(id='s', kind='command', command='echo hi')\n"
            "    return Workflow(name='tiny', repo=Path(args['repo']),\n"
            "                phases=(Phase(name='Only', steps=(step,)),))\n",
            encoding="utf-8")
        repo = git_repo(self.tmp / "repo")
        with quiet() as out:
            code = cli_main(["run", "--workflow", str(workflow_path),
                             "--args", f"repo={repo}",
                             "--out", str(self.tmp / "runs"),
                             "--auto-resume", "-1"])
        self.assertEqual(code, 2)
        self.assertIn("--auto-resume must be zero or more", out.out)

    def test_the_workflow_value_is_validated(self):
        from ohflow.workflow import WorkflowError, validate
        workflow = replace(simple_workflow(self.tmp / "repo"), auto_resume=True)
        with self.assertRaises(WorkflowError) as caught:
            validate(workflow)
        self.assertIn("auto_resume must be an integer, got the boolean",
                      str(caught.exception))

"""Defect 6: an agent execution timeout is read, not decreed.

Fixed in `5f6af02`, "ohflow: a worker wall timeout is read, not decreed".

What went wrong. When `execution_timeout_s` expired on an agent, the engine killed
the child and replaced the child's collected error with its own sentence,
`wall timeout Ns exceeded`. `failure.classify` then had nothing to read, matched
nothing, and returned `structural` by its safe default. An agent that the
provider had been rate-limiting for the whole of its timeout was therefore
recorded as a verdict on the work. Under an `abort` policy that killed the phase.

The rule the fix states. A kill during a provider stall is not a verdict, so its
text is read like any other agent failure. A `command`, a `merge` or a `gate`
timeout **is** a verdict: those are deterministic and their clock running out is
the answer, so they stay structural without reading anything.

This file also carries the suite's evidence for acceptance criterion 4:
classification is asserted against strings lifted from a preserved run, never
against invented text. See `fixtures/real_errors.py` for where each came from.
"""

from __future__ import annotations

from fixtures.real_errors import (ABORT_VICTIM_ERROR,
                                  SCOUT1_TERMINAL_FAULT_LOG_TAIL,
                                  SCOUT2_RATE_LIMIT_RESULT_ERROR,
                                  SCOUT3_RATE_LIMIT_LOG_TAIL)
from ohflow import failure
from ohflow.gates import GateReport, GateResult
from ohflow.run_log import RunLog
from support import (FakeHarnessExecutor, TempCase, AgentScript, git_repo,
                     install_fake_harness_executor, simple_workflow, step_statuses, stub_preflight,
                     agent_step)


class RealProviderTextIsClassified(TempCase):
    """Acceptance criterion 4. Every string here came out of a real run."""

    def test_a_live_rate_limit_from_result_json_is_transient(self):
        """Scout 2: the child caught the exception and wrote it to result.json."""
        self.assertIn("litellm.RateLimitError", SCOUT2_RATE_LIMIT_RESULT_ERROR)
        self.assertEqual(
            failure.classify(error=SCOUT2_RATE_LIMIT_RESULT_ERROR, kind="agent"),
            failure.TRANSIENT)

    def test_a_live_rate_limit_from_a_log_tail_is_transient(self):
        """Scout 3: the child died, and the text is the tail of its stderr log.

        `rich` wrapped the provider's sentence into a box at console width, so
        `Rate limit reached for requests` is split across two lines with
        box-drawing characters between them. A pattern that needed the whole
        phrase on one line would fail here, which is the point of using the
        recorded text.
        """
        self.assertIn("host_runner exited 1", SCOUT3_RATE_LIMIT_LOG_TAIL)
        self.assertIn("│", SCOUT3_RATE_LIMIT_LOG_TAIL)
        self.assertNotIn("Rate limit reached for requests",
                         SCOUT3_RATE_LIMIT_LOG_TAIL,
                         "the recorded text is wrapped; if this ever holds "
                         "unwrapped, re-lift the fixture")
        self.assertEqual(
            failure.classify(error=SCOUT3_RATE_LIMIT_LOG_TAIL, kind="agent"),
            failure.TRANSIENT)

    def test_a_windows_terminal_fault_from_the_same_run_is_structural(self):
        """Scout 1. Same shape, same minute, no rate limit. Waiting changes
        nothing about a PowerShell process that is not running."""
        self.assertIn("Cannot send", SCOUT1_TERMINAL_FAULT_LOG_TAIL)
        self.assertEqual(
            failure.classify(error=SCOUT1_TERMINAL_FAULT_LOG_TAIL, kind="agent"),
            failure.STRUCTURAL)

    def test_the_run_log_records_which_transient_signature_matched(self):
        self.assertEqual(failure.explain(SCOUT2_RATE_LIMIT_RESULT_ERROR),
                         "RateLimitError")
        self.assertEqual(failure.explain(SCOUT3_RATE_LIMIT_LOG_TAIL),
                         "RateLimitError")
        self.assertIsNone(failure.explain(SCOUT1_TERMINAL_FAULT_LOG_TAIL))

    def test_the_recorded_abort_victim_text_carries_no_transient_signature(self):
        """`run aborted` is what the six killed scouts were recorded with. It
        says nothing about the provider, so it must not read as transient."""
        self.assertEqual(ABORT_VICTIM_ERROR, "run aborted")
        self.assertEqual(
            failure.classify(error=ABORT_VICTIM_ERROR, kind="agent"),
            failure.STRUCTURAL)


class AnExecutionTimeoutIsReadForAnAgent(TempCase):

    def test_the_engine_sentence_alone_is_structural(self):
        """This is the whole defect in one line. Before the fix the engine
        passed exactly this, and nothing else, to the classifier."""
        self.assertEqual(
            failure.classify(error="execution timeout 7200s exceeded", kind="agent"),
            failure.STRUCTURAL)

    def test_the_sentence_plus_the_real_tail_is_transient(self):
        """After the fix the agent's own last words are appended, and the
        classifier reads them."""
        combined = "execution timeout 7200s exceeded\n" + SCOUT3_RATE_LIMIT_LOG_TAIL
        self.assertEqual(failure.classify(error=combined, kind="agent"),
                         failure.TRANSIENT)

    def test_the_sentence_plus_a_structural_tail_stays_structural(self):
        combined = ("execution timeout 7200s exceeded\n"
                    + SCOUT1_TERMINAL_FAULT_LOG_TAIL)
        self.assertEqual(failure.classify(error=combined, kind="agent"),
                         failure.STRUCTURAL)

    def test_a_timeout_sentence_never_matches_a_transient_number_by_accident(self):
        """`_TRANSIENT` matches the HTTP codes 500, 502, 503 and 504 as whole
        words. The engine writes its timeout as `{n}s`, with no space, so a workflow
        with `execution_timeout_s=503` still produces structural text."""
        for seconds in (500, 502, 503, 504, 5400, 7200):
            with self.subTest(seconds=seconds):
                self.assertEqual(
                    failure.classify(error=f"execution timeout {seconds}s exceeded",
                                     kind="agent"),
                    failure.STRUCTURAL)


class ADeterministicTimeoutStaysStructural(TempCase):
    """A command, a merge and a gate are verdicts the orchestrator issued."""

    def test_a_command_timeout_ignores_a_rate_limit_in_its_text(self):
        for kind in ("command", "merge", "gate"):
            with self.subTest(kind=kind):
                self.assertEqual(
                    failure.classify(error=SCOUT2_RATE_LIMIT_RESULT_ERROR,
                                     kind=kind, status="timeout"),
                    failure.STRUCTURAL,
                    f"a {kind} timeout must not be read from the text")

    def test_a_forbidden_gate_failure_beats_any_transient_text(self):
        report = GateReport(coord="01.p/01.s", passed=False, checks=[
            GateResult("no_ai_attribution", False, observed="a trailer",
                       expected="none"),
        ])
        self.assertEqual(
            failure.classify(error=SCOUT2_RATE_LIMIT_RESULT_ERROR,
                             report=report, kind="agent"),
            failure.STRUCTURAL)

    def test_unrecognised_text_is_structural(self):
        """The default must never weaken an abort."""
        self.assertEqual(
            failure.classify(error="the agent wrote nonsense", kind="agent"),
            failure.STRUCTURAL)
        self.assertEqual(failure.classify(error="", kind="agent"),
                         failure.STRUCTURAL)
        self.assertEqual(failure.classify(error=None, kind="agent"),
                         failure.STRUCTURAL)

    def test_an_auth_failure_during_a_rate_limit_is_structural(self):
        """A structural signature beats a transient one in the same text."""
        mixed = ("RateLimitError: retrying ... then "
                 "AuthenticationError: invalid api key")
        self.assertEqual(failure.classify(error=mixed, kind="agent"),
                         failure.STRUCTURAL)


class TheEngineKeepsTheKilledAgentsLastWords(TempCase):
    """The end-to-end shape of the fix, through `Engine._run_agent`.

    A fake agent never finishes, the step's execution timeout is one second, and the
    harness executor's `collect` returns the real rate-limit tail. The recorded error must
    carry both the engine's sentence and the provider's text, and the step must
    come out `deferred` rather than `failed`.
    """

    def test_a_stalled_agent_is_deferred_and_keeps_its_provider_text(self):
        from ohflow.engine import Engine
        from ohflow import harness_executor as ohexecutor

        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)

        class StalledHarnessExecutor(FakeHarnessExecutor):
            def poll(self, handle):
                return ohexecutor.RUNNING          # never finishes

            def collect(self, handle):
                # A killed child with no result.json: collect returns the
                # tail of its stderr log.
                return {"coord": handle.coord, "error": SCOUT3_RATE_LIMIT_LOG_TAIL,
                        "structured": None, "tokens": {}}

        harness_executor = install_fake_harness_executor(self, StalledHarnessExecutor())
        workflow = simple_workflow(repo, steps=[agent_step("stalled", execution_timeout_s=1)],
                                   on_step_failure="abort")
        run_dir = self.run_dir()
        engine = Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors)
        engine.run()

        statuses = step_statuses(run_dir)
        coord = next(iter(statuses))
        self.assertEqual(statuses[coord], "deferred",
                         "a provider stall killed by the execution timeout is not a "
                         "verdict on the work")
        self.assertIn(coord, harness_executor.killed, "the child was not killed")

        state = RunLog.replay(run_dir)
        error = state.steps[coord].error or ""
        self.assertIn("execution timeout 1s exceeded", error)
        self.assertIn("RateLimitError", error,
                      "the agent's own last words were thrown away")
        self.assertEqual(state.steps[coord].failure_class, failure.TRANSIENT)
        self.assertFalse(engine._abort.is_set(),
                         "a transient failure must not abort the phase")

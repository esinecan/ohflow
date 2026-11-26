"""The codex harness executor module answers the harness executor questions over a recorded stream.

The fake `codex` replays the roll-call stream recorded from the real CLI. The
attempt directory it leaves is the fixture. Usage equals the tokens in
`result.json`, activity ends on the last tool call, a retry has no resume
target (codex starts a fresh thread), and transcript is the event log.
"""

from __future__ import annotations

import time

from contract_support import (assert_usage_matches_result, last_tool_call,
                              recorded_result)
from ohflow import harness_executors
from test_signed_in_02_runner_harness_executor import SCHEMA, SignedInHarnessExecutorCase


class CodexContract(SignedInHarnessExecutorCase):
    harness_executor_name = "codex"
    exe_var = "OHFLOW_CODEX_EXE"

    def setUp(self):
        super().setUp()
        home = self.tmp / "real-codex-home"
        home.mkdir()
        (home / "auth.json").write_text('{"fake": true}', encoding="utf-8")
        self._set_env("CODEX_HOME", str(home))
        self.result = self._run("success", schema=SCHEMA, max_iterations=100)
        self.attempt = self.tmp / "success"
        self.module = harness_executors.harness_executor_module("codex")

    def test_harness_executor_contract_usage_equals_the_result_tokens(self):
        tokens = assert_usage_matches_result(self, self.module, self.attempt)
        self.assertEqual(tokens["prompt_tokens"], 1103792)

    def test_harness_executor_contract_activity_returns_the_last_tool_call(self):
        call = last_tool_call(self.module, self.attempt, now=time.time())
        self.assertEqual(call["name"], "shell")

    def test_harness_executor_contract_resume_target_is_none(self):
        self.assertIsNone(self.module.resume_target(
            recorded_result(self.attempt), self.attempt))

    def test_harness_executor_contract_transcript_is_the_event_log(self):
        path, why = self.module.transcript(self.attempt, recorded_result(self.attempt))
        self.assertIsNone(why)
        self.assertEqual(path, self.attempt / "logs" / "codex-events.jsonl")

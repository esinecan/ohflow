"""The claude harness executor module answers the harness executor questions over a recorded stream.

The fake `claude` replays the stream recorded from the real CLI. The attempt
directory it leaves is the fixture. Four questions, each asked of
`ohflow.claude_runner` and never of the engine: usage equals the tokens in
`result.json`, activity ends on the last tool call, the resume target is the
`conversation_id` the record holds (not a file), and transcript is the event log.
"""

from __future__ import annotations

import time

from contract_support import (assert_usage_matches_result, last_tool_call,
                              recorded_result)
from ohflow import harness_executors
from test_signed_in_02_runner_harness_executor import SignedInHarnessExecutorCase


class ClaudeContract(SignedInHarnessExecutorCase):
    harness_executor_name = "claude"
    exe_var = "OHFLOW_CLAUDE_EXE"

    def setUp(self):
        super().setUp()
        self.result = self._run("success")
        self.attempt = self.tmp / "success"
        self.module = harness_executors.harness_executor_module("claude")

    def test_harness_executor_contract_usage_equals_the_result_tokens(self):
        tokens = assert_usage_matches_result(self, self.module, self.attempt)
        self.assertEqual(tokens["prompt_tokens"], 70)

    def test_harness_executor_contract_activity_returns_the_last_tool_call(self):
        call = last_tool_call(self.module, self.attempt, now=time.time())
        self.assertEqual(call["name"], "Bash")

    def test_harness_executor_contract_resume_target_is_the_conversation_id(self):
        record = recorded_result(self.attempt)
        self.assertTrue(record["conversation_id"])
        self.assertEqual(self.module.resume_target(record, self.attempt),
                         record["conversation_id"])

    def test_harness_executor_contract_transcript_is_the_event_log(self):
        path, why = self.module.transcript(self.attempt, recorded_result(self.attempt))
        self.assertIsNone(why)
        self.assertEqual(path, self.attempt / "logs" / "claude-events.jsonl")

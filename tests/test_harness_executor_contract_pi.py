"""The pi harness executor module answers the harness executor questions over a recorded attempt.

`fixtures/usage/pi` is a copy of a preserved pi attempt: `result.json`, the
runner's event log and the session file. Usage equals the tokens in
`result.json`, activity ends on the last tool call, the resume target is the
session file the attempt left, and transcript is that same file when no export is
asked for.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from contract_support import (assert_usage_matches_result, last_tool_call,
                              recorded_result)
from ohflow import harness_executors
from support import TempCase

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "usage" / "pi"


class PiContract(TempCase):

    def setUp(self):
        super().setUp()
        self.attempt = self.tmp / "attempt"
        shutil.copytree(FIXTURE, self.attempt)
        # The preserved record names the session folder of the machine that
        # ran it. A copy points at its own folder.
        record = recorded_result(self.attempt)
        record["transcript_dir"] = "session"
        (self.attempt / "result.json").write_text(json.dumps(record), encoding="utf-8")
        self.module = harness_executors.harness_executor_module("pi")

    def test_harness_executor_contract_usage_equals_the_result_tokens(self):
        tokens = assert_usage_matches_result(self, self.module, self.attempt)
        self.assertEqual(tokens["prompt_tokens"], 2635)

    def test_harness_executor_contract_activity_returns_the_last_tool_call(self):
        call = last_tool_call(self.module, self.attempt, now=time.time())
        self.assertEqual(call["name"], "bash")

    def test_harness_executor_contract_resume_target_is_the_session_file(self):
        session = self.attempt / "session" / "session.jsonl"
        self.assertEqual(self.module.resume_target(
            recorded_result(self.attempt), self.attempt), str(session))

    def test_harness_executor_contract_resume_target_prefers_the_recorded_conversation(self):
        record = recorded_result(self.attempt)
        folder = self.attempt / "session"
        named = folder / f"{record['conversation_id']}.jsonl"
        shutil.copy(folder / "session.jsonl", named)
        shutil.copy(folder / "session.jsonl", folder / "zz-newer.jsonl")
        self.assertEqual(self.module.resume_target(record, self.attempt),
                         str(named))

    def test_harness_executor_contract_transcript_without_export_is_the_session_file(self):
        path, why = self.module.transcript(self.attempt, recorded_result(self.attempt))
        self.assertIsNone(why)
        self.assertEqual(path, self.attempt / "session" / "session.jsonl")

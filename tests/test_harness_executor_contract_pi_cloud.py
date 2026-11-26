"""The pi-cloud harness executor answers the harness executor questions over a real attempt.

The shared assertions of `tests/contract_support.py` on one attempt from the
`success` recording, run through the real executor against the fake Worker
and a real bare `origin`: the module's `usage` equals the five token fields
of its own `result.json`, `activity` ends on the recording's last tool call,
the fetched commit is the worktree HEAD, and the transcript points at the
copied file.
"""

from __future__ import annotations

import json
import time

from contract_support import (assert_usage_matches_result, last_tool_call,
                              recorded_result)
from pi_cloud_support import PiCloudCase, git


class PiCloudContract(PiCloudCase):

    def test_the_recorded_step_fetches_back_its_commit(self):
        key = self.key_of(self.tmp / "contract")
        self.worker.plan(key, 1, ["success"])
        out_dir, result = self.run_attempt("contract")
        self.assertIsNone(result["error"], result["error"])
        self.assertEqual(result["execution_status"], "finished")
        cloud = result["pi_cloud"]
        self.assertEqual(cloud["status"], "done")
        self.assertTrue(cloud["pushed"])
        # The fetched commit is the worktree HEAD.
        self.assertEqual(cloud["head"], git(self.repo, "rev-parse", "HEAD"))
        self.assertEqual(result["conversation_id"], key)
        self.assertEqual(result["tools"], [
            "read", "ls", "find", "grep", "write", "edit", "delete",
            "exec", "git_clone", "git_branch", "git_commit", "git_push"])

    def test_harness_executor_contract_usage_equals_the_result_tokens(self):
        key = self.key_of(self.tmp / "usage")
        self.worker.plan(key, 1, ["success"])
        out_dir, result = self.run_attempt("usage")
        tokens = assert_usage_matches_result(self, self.module,
                                             self.tmp / "usage")
        # The six recorded assistant turns, counted once each.
        self.assertEqual(result["llm_calls"], 6)
        self.assertEqual(tokens["prompt_tokens"], 16717)
        self.assertEqual(tokens["completion_tokens"], 390)

    def test_harness_executor_contract_activity_returns_the_last_tool_call(self):
        key = self.key_of(self.tmp / "activity")
        self.worker.plan(key, 1, ["success"])
        self.run_attempt("activity")
        call = last_tool_call(self.module, self.tmp / "activity",
                              now=time.time())
        # The recording's last started call: the handover write, started in
        # the same instant as the final git push.
        self.assertEqual(call["name"], "write")
        self.assertIn("handover.md", call["summary"])

    def test_harness_executor_contract_the_transcript_is_the_copied_file(self):
        key = self.key_of(self.tmp / "transcript")
        self.worker.plan(key, 1, ["success"])
        out_dir, _result = self.run_attempt("transcript")
        path, why = self.module.transcript(out_dir,
                                           recorded_result(out_dir))
        self.assertIsNone(why)
        self.assertEqual(path, out_dir / "transcript.md")
        (out_dir / "transcript.md").unlink()
        path, why = self.module.transcript(out_dir, recorded_result(out_dir))
        self.assertIsNone(why)
        self.assertEqual(path, out_dir / "logs" / self.module.EVENT_LOG)
        path, why = self.module.transcript(self.tmp / "empty", {})
        self.assertEqual((path, why), (None, "no pi-cloud transcript and no "
                                             "logs/pi-cloud-events.jsonl"))

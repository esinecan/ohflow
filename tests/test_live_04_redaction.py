"""Dashboard S1, test 4: redaction of every masked pattern (spec §7.4).

Tool arguments and results are agent-authored text. An agent that echoes a key
into a command would otherwise publish it on a page and in an exit report, so
redaction runs inside `live.py`, before any text leaves it.
"""

from __future__ import annotations

import json

from dashboard_support import T0, RunLog, mark_alive, workflow_json, stamp, agent
from ohflow import live
from support import TempCase


class EachPatternIsMasked(TempCase):

    def check(self, text: str, secret: str, kept: str) -> None:
        out = live.redact(text)
        self.assertNotIn(secret, out)
        self.assertIn(kept, out)
        self.assertEqual(live.redact(out), out, "redaction is idempotent")

    def test_openai_style_key(self):
        self.check("use sk-proj-AbCdEf0123456789xyz now",
                   "AbCdEf0123456789xyz", "sk-[redacted]")

    def test_bearer_token(self):
        self.check("Authorization: Bearer eyJhbGciOi.payload.sig",
                   "eyJhbGciOi.payload.sig", "Bearer [redacted]")

    def test_github_token(self):
        self.check("git clone https://ghp_0123456789abcdefABCDEF@github.com/x",
                   "ghp_0123456789abcdefABCDEF", "ghp_[redacted]")

    def test_slack_token(self):
        self.check("SLACK=xoxb-1234567890-abcdefghij",
                   "xoxb-1234567890-abcdefghij", "xoxb-[redacted]")

    def test_variables_ending_in_key_token_or_secret(self):
        cases = [
            ("export ZAI_CODING_CN_API_KEY=abc123def", "abc123def",
             "ZAI_CODING_CN_API_KEY=[redacted]"),
            ('$env:GITHUB_TOKEN = "t0k3nvalue"', "t0k3nvalue",
             '$env:GITHUB_TOKEN = "[redacted]"'),
            ('{"CLIENT_SECRET": "s3cr3t-v4lue"}', "s3cr3t-v4lue",
             '{"CLIENT_SECRET": "[redacted]"}'),
            ("OPENAI_API_KEY='sk-live-0123456789'", "0123456789",
             "OPENAI_API_KEY='[redacted]'"),
        ]
        for text, secret, kept in cases:
            with self.subTest(text=text):
                self.check(text, secret, kept)

    def test_names_that_only_look_alike_are_left_alone(self):
        text = ("max_tokens=100 api_key_env=ZAI_CODING_CN_API_KEY task-list "
                "risk-assessment")
        self.assertEqual(live.redact(text), text)


class NothingLeavesUnmasked(TempCase):
    """The read-out itself is redacted: a secret in a tool call never reaches
    the page, whatever field carries it."""

    def test_a_key_in_a_running_command_is_masked_in_the_read_out(self):
        run = self.run_dir("r-secret")
        workflow_json(run, [("Map", [agent("a")], 1)])
        (RunLog(run).phase(1, "01.map", "Map", ["01.map/01.a"])
         .start(2, "01.map/01.a"))
        mark_alive(run)
        session = run / "phases" / "01.map" / "01.a" / "attempts" / "01" / "session"
        session.mkdir(parents=True)
        entry = {"type": "message", "timestamp": stamp(5), "message": {
            "role": "assistant", "usage": {"input": 1, "output": 1},
            "content": [
                {"type": "text", "text": "Calling with OPENAI_API_KEY=sk-abcdefghijklmnop."},
                {"type": "toolCall", "id": "c1", "name": "bash", "arguments": {
                    "command": "curl -H 'Authorization: Bearer abcdef123456' "
                               "https://x && echo ghp_0123456789abcdefXYZ"}}]}}
        (session / "s.jsonl").write_text(json.dumps(entry) + "\n",
                                         encoding="utf-8")
        read_out = live.read_out(run, T0 + 10)
        text = json.dumps(read_out)
        for secret in ("abcdefghijklmnop", "abcdef123456",
                       "0123456789abcdefXYZ"):
            self.assertNotIn(secret, text)
        card = read_out["agents"][0]
        self.assertIn("Bearer [redacted]", card["running_tool"]["summary"])
        self.assertIn("[redacted]", card["latest_reasoning"]["text"])

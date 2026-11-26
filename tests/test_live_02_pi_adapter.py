"""Dashboard S1, test 2: the pi harness executor adapter against a real session.

The fixture is attempt 02 of the G1 run's `flaky` agent, the one the engine
auto-resumed after an injected 429. Its `pi-agent/` directory was never copied: it
holds the attempt's credentials. Paths were rewritten under `C:\\fixture\\g1`.

Four checks, per spec §13 item 2: calls pair with their results, a call with no
result is the running tool, the latest reasoning is the newest statement, and
live tokens are the sum of the assistant `usage` records.
"""

from __future__ import annotations

import json
from pathlib import Path

from dashboard_support import G1_ATTEMPT, copy_tree
from ohflow import activity as activity_mod, pi_runner
from support import TempCase

#: 2026-09-29T00:12:30Z, fifteen seconds after the session's last line.
NOW = 1790640750.0


def _entries(session: Path) -> list[dict]:
    return [json.loads(line) for line in
            session.read_text(encoding="utf-8").splitlines() if line.strip()]


def _session(attempt: Path) -> Path:
    return sorted((attempt / "session").glob("*.jsonl"))[-1]


class PiAdapter(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.attempt = copy_tree(G1_ATTEMPT, self.tmp / "attempt")

    def test_every_call_pairs_with_its_result(self):
        act = pi_runner.activity(self.attempt, now=NOW, running=False)
        calls = act["tool_calls"]
        self.assertEqual(act["tool_calls_total"], 5)
        self.assertEqual(len(calls), 5)
        self.assertTrue(all(c["ok"] is True for c in calls), calls)
        self.assertTrue(all(c["duration_s"] is not None for c in calls))
        self.assertFalse(any(c["pending"] for c in calls))
        self.assertIsNone(act["running_tool"])
        # Newest first, with the rendering rules of spec §7.4.
        self.assertEqual([c["name"] for c in calls],
                         ["bash", "read", "read", "ls", "bash"])
        oldest = calls[-1]
        self.assertEqual(oldest["summary"],
                         "git --no-pager log --oneline -5 && git --no-pager "
                         "status --porcelain && ls -la",
                         "the leading cd into the worktree is dropped")
        self.assertEqual(oldest["first_line"], "7d70f05 g1 fixture")
        self.assertEqual({calls[1]["summary"], calls[2]["summary"]},
                         {"README.md", ".gitignore"},
                         "read paths are relative to the worktree")
        self.assertEqual(calls[3]["summary"], ".")
        self.assertLessEqual(len(calls[0]["summary"]), activity_mod.SUMMARY_MAX)
        self.assertRegex(calls[0]["at"], r"^\d\d:\d\d:\d\d$")

    def test_a_call_without_a_result_is_the_running_tool(self):
        session = _session(self.attempt)
        lines = session.read_text(encoding="utf-8").splitlines(keepends=True)
        # Cut the session right after the assistant message that asked for
        # the third bash call, before its result was appended.
        cut = next(i for i, line in enumerate(lines)
                   if "call_e5db7c58efd5478191f6638f" in line)
        session.write_text("".join(lines[:cut + 1]), encoding="utf-8")
        called_at = activity_mod.epoch(json.loads(lines[cut])["timestamp"])

        act = pi_runner.activity(self.attempt, now=NOW, running=True)
        running = act["running_tool"]
        self.assertIsNotNone(running)
        self.assertEqual(running["name"], "bash")
        self.assertTrue(running["summary"].startswith(
            "git --no-pager status --porcelain > .scratch/status.out"))
        self.assertEqual(running["since_s"], round(NOW - called_at))
        self.assertNotIn(running["id"], [c["id"] for c in act["tool_calls"]],
                         "the running tool is shown once, above the list")
        self.assertEqual(len(act["tool_calls"]), 4)

    def test_the_session_is_read_from_its_last_offset(self):
        session = _session(self.attempt)
        lines = session.read_text(encoding="utf-8").splitlines(keepends=True)
        session.write_text("".join(lines[:5]), encoding="utf-8")
        first = pi_runner.activity(self.attempt, now=NOW, running=True)
        self.assertEqual(first["tool_calls_total"], 2)
        with session.open("a", encoding="utf-8") as fh:
            fh.write("".join(lines[5:]))
        second = pi_runner.activity(self.attempt, now=NOW, running=True)
        self.assertEqual(second["tool_calls_total"], 5)
        self.assertEqual(second["llm_calls"], 4)

    def test_latest_reasoning_is_the_newest_statement(self):
        act = pi_runner.activity(self.attempt, now=NOW, running=False)
        said = act["latest_reasoning"]
        self.assertEqual(said["source"], "text")
        self.assertTrue(said["text"].startswith("Report"), said)
        self.assertLessEqual(len(said["text"]), activity_mod.REASONING_MAX)
        self.assertEqual(said["at"], "2026-09-29T00:12:15Z")
        self.assertEqual(said["age_s"],
                         round(NOW - activity_mod.epoch("2026-09-29T00:12:15.941Z")))

    def test_a_message_with_only_thinking_is_read_from_its_thinking(self):
        session = _session(self.attempt)
        lines = session.read_text(encoding="utf-8").splitlines(keepends=True)
        cut = next(i for i, line in enumerate(lines)
                   if "call_e400a17c45714b3193677d7b" in line)
        session.write_text("".join(lines[:cut + 1]), encoding="utf-8")
        said = pi_runner.activity(self.attempt, now=NOW)["latest_reasoning"]
        self.assertEqual(said["source"], "thinking")
        self.assertEqual(said["text"], "The worktree is nearly empty: "
                                       "README.md, .gitignore, .scratch.")

    def test_live_input_tokens_include_the_cache(self):
        expected = {"input": 0, "output": 0, "cache_read": 0, "reasoning": 0}
        calls = 0
        for entry in _entries(_session(self.attempt)):
            msg = entry.get("message") or {}
            if msg.get("role") != "assistant":
                continue
            calls += 1
            usage = msg["usage"]
            expected["input"] += (usage["input"] + usage["cacheRead"]
                                  + usage.get("cacheWrite", 0))
            expected["output"] += usage["output"]
            expected["cache_read"] += usage["cacheRead"]
            expected["reasoning"] += usage["reasoning"]
        act = pi_runner.activity(self.attempt, now=NOW)
        self.assertEqual(act["tokens"], expected)
        self.assertEqual(act["llm_calls"], calls)
        self.assertEqual(calls, 4)

    def test_an_empty_session_says_starting_and_idles_on_the_heartbeat(self):
        for f in (self.attempt / "session").glob("*.jsonl"):
            f.unlink()
        beat = json.loads((self.attempt / "logs" / "heartbeat.json")
                          .read_text(encoding="utf-8"))
        act = pi_runner.activity(self.attempt, now=NOW, running=True)
        self.assertEqual(act["note"], "starting: no model reply yet")
        self.assertEqual(act["idle_s"], round(NOW - beat["at"]))
        self.assertEqual(act["tool_calls"], [])

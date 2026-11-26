"""`ohflow actions` lists one attempt's model calls and the actions under them.

Before: to find where an agent went wrong, an orchestrating agent exported the
transcript and joined each tool call to its model call and its result by hand,
in five formats. Now one call prints one line per model call with its tokens
and latency, and one indented line per action with its duration and result.
Tokens sit on the call line once: a response that launched three actions is
not counted three times.

The spec is `docs/history/orchestrator-visibility.md`, "Utility 3".
"""

from __future__ import annotations

import json

from dashboard_support import RunLog, agent, command, mark_alive, workflow_json
from ohflow import actions, rundir
from support import TempCase
from verb_support import call

S = "01.work/01.s"
MS = 1790000000000  # a fixed epoch in milliseconds


def a_run(run, harness: str, *, kind: str = "agent"):
    """One step `s` on `harness`; attempt 1 finished. Returns its attempt dir."""
    step = (agent("s", harness_executor=harness) if kind == "agent"
            else command("s"))
    workflow_json(run, [("Work", [step], 1)])
    (RunLog(run).phase(1, "01.work", "Work", [S], 1)
        .start(2, S).finish(30, S, 1, "failed", error="gate failed"))
    mark_alive(run)
    adir = rundir.attempt_dir(run, S, 1)
    adir.mkdir(parents=True, exist_ok=True)
    (adir / "result.json").write_text("{}", encoding="utf-8")
    return adir


def jsonl(path, records) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records),
                    encoding="utf-8")


def iso(ms: int) -> str:
    import datetime as dt
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# ------------------------------------------------------------- pi

def pi_attempt(adir) -> None:
    jsonl(adir / "session" / "s.jsonl", [
        {"type": "session", "timestamp": iso(MS)},
        {"type": "message", "timestamp": iso(MS + 100),
         "message": {"role": "user", "timestamp": MS + 90,
                     "content": [{"type": "text", "text": "go"}]}},
        {"type": "message", "timestamp": iso(MS + 5100),
         "message": {"role": "assistant", "timestamp": MS + 200,
                     "responseId": "P1", "stopReason": "toolUse",
                     "usage": {"input": 3000, "output": 44, "cacheRead": 500,
                               "cacheWrite": 0, "reasoning": 16},
                     "content": [
                         {"type": "text", "text": "Reading the brief first. Then I edit."},
                         {"type": "toolCall", "id": "t1", "name": "read",
                          "arguments": {"path": "brief.md"}},
                         {"type": "toolCall", "id": "t2", "name": "bash",
                          "arguments": {"command": "npm test"}}]}},
        {"type": "message", "timestamp": iso(MS + 5200),
         "message": {"role": "toolResult", "timestamp": MS + 5200,
                     "toolCallId": "t1", "isError": False,
                     "content": [{"type": "text", "text": "# Brief"}]}},
        {"type": "message", "timestamp": iso(MS + 8100),
         "message": {"role": "toolResult", "timestamp": MS + 8100,
                     "toolCallId": "t2", "isError": True,
                     "content": [{"type": "text", "text": "2 tests failed"}]}},
    ])


# ------------------------------------------------------------- claude

def claude_attempt(adir) -> None:
    usage = {"input_tokens": 10, "cache_creation_input_tokens": 400,
             "cache_read_input_tokens": 600, "output_tokens": 4}
    jsonl(adir / "logs" / "claude-events.jsonl", [
        {"type": "system", "subtype": "init"},
        {"type": "assistant", "timestamp": iso(MS + 1000),
         "message": {"id": "msg_A", "usage": usage, "content": [
             {"type": "thinking", "thinking": "Plan the step."}]}},
        {"type": "assistant", "timestamp": iso(MS + 1500),
         "message": {"id": "msg_A", "usage": usage, "content": [
             {"type": "tool_use", "id": "tu1", "name": "Bash",
              "input": {"command": "git status"}}]}},
        {"type": "user", "timestamp": iso(MS + 2500),
         "message": {"content": [{"type": "tool_result", "tool_use_id": "tu1",
                                  "content": "clean"}]}},
        {"type": "assistant", "timestamp": iso(MS + 4000),
         "message": {"id": "msg_B", "usage": dict(usage, input_tokens=20),
                     "content": [{"type": "text", "text": "Done. All clean."}]}},
        {"type": "result", "timestamp": iso(MS + 4100), "is_error": False,
         "result": "Done.", "usage": {"input_tokens": 30,
                                       "cache_creation_input_tokens": 800,
                                       "cache_read_input_tokens": 1200,
                                       "output_tokens": 777}},
    ])


# ------------------------------------------------------------- codex

def codex_attempt(adir) -> None:
    jsonl(adir / "logs" / "codex-events.jsonl", [
        {"type": "thread.started", "thread_id": "x"},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"id": "i0", "type": "agent_message",
                                            "text": "Reading the brief."}},
        {"type": "item.started", "item": {"id": "i1", "type": "command_execution",
                                          "command": "cat brief.md",
                                          "status": "in_progress"}},
        {"type": "item.completed", "item": {"id": "i1", "type": "command_execution",
                                            "command": "cat brief.md", "exit_code": 0,
                                            "aggregated_output": "# Brief",
                                            "status": "completed"}},
        {"type": "item.started", "item": {"id": "i2", "type": "command_execution",
                                          "command": "make test",
                                          "status": "in_progress"}},
        {"type": "turn.completed", "usage": {"input_tokens": 5000,
                                             "cached_input_tokens": 3000,
                                             "output_tokens": 300}},
    ])


class EachHarnessExecutorJoinsActionsToTheirCall(TempCase):

    def run_of(self, harness, build):
        run = self.tmp / "runs" / harness
        build(a_run(run, harness))
        return run

    def test_2_pi_call_tokens_latency_and_a_failed_result(self):
        run = self.run_of("pi", pi_attempt)
        code, lines = call("actions", "--run", run, "--step", "s")
        self.assertEqual(code, 0, lines)
        self.assertEqual(lines[0], f"ACTIONS {S} attempt 1: 1 model call, "
                                   "2 actions, 1 failed; tokens in 3500 out 44 (pi)")
        self.assertRegex(lines[2], r"^call 1 \d\d:\d\d:\d\d · in 3500 out 44 · "
                                   r"4\.9 s · 2 actions · line 3$")
        self.assertEqual(lines[3], "  said: Reading the brief first.")
        self.assertRegex(lines[4], r"^  read brief\.md -> ok \(0\.1 s\): # Brief · "
                                   r"line 4$")
        self.assertRegex(lines[5], r"^  bash npm test -> failed \(3\.0 s\): "
                                   r"2 tests failed · line 5$")

    def test_3_claude_groups_records_by_message_id_and_takes_output_from_result(self):
        run = self.run_of("claude", claude_attempt)
        code, lines = call("actions", "--run", run, "--step", "s")
        self.assertEqual(code, 0, lines)
        self.assertEqual(lines[0], f"ACTIONS {S} attempt 1: 2 model calls, "
                                   "1 action, 0 failed; tokens in 2030 out 777 "
                                   "(claude)")
        self.assertRegex(lines[2], r"^call 1 \d\d:\d\d:\d\d · in 1010 out - · "
                                   r"- s · 1 action · line 2$")
        self.assertRegex(lines[3], r"^  Bash git status -> ok \(1\.0 s\): clean")
        self.assertRegex(lines[4], r"^call 2 .* in 1020 out - · - s · 0 actions")
        self.assertEqual(lines[5], "  said: Done.")

    def test_5_codex_puts_every_action_under_its_turn(self):
        run = self.run_of("codex", codex_attempt)
        code, lines = call("actions", "--run", run, "--step", "s")
        self.assertEqual(code, 0, lines)
        self.assertEqual(lines[0], f"ACTIONS {S} attempt 1: 1 turn, "
                                   "2 actions, 0 failed; tokens in 5000 out 300 "
                                   "(codex)")
        self.assertIn("join: none; codex records tokens once per turn", lines[1])
        self.assertRegex(lines[2], r"^turn 1 - · in 5000 out 300 · - s · 2 actions "
                                   r"· line 7$")
        self.assertEqual(lines[3], "  said: Reading the brief.")
        self.assertRegex(lines[4], r"^  shell cat brief\.md -> ok \(- s\): # Brief")
        # 6: a call with no result is pending.
        self.assertRegex(lines[5], r"^  shell make test -> pending \(- s\)")


class ActionsRefusesWhatItCannotRead(TempCase):

    def test_7_a_command_step_a_missing_step_and_a_non_run_exit_1(self):
        run = self.tmp / "runs" / "cmd"
        a_run(run, "pi", kind="command")
        code, lines = call("actions", "--run", run, "--step", "s")
        self.assertEqual(code, 1)
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("command step", lines[0])
        code, lines = call("actions", "--run", run, "--step", "nope")
        self.assertEqual((code, len(lines)), (1, 1), lines)
        empty = self.tmp / "empty"
        empty.mkdir()
        code, lines = call("actions", "--run", empty, "--step", "s")
        self.assertEqual((code, len(lines)), (1, 1), lines)
        self.assertIn("no ohflow run", lines[0])

    def test_7b_an_attempt_with_no_transcript_exits_1(self):
        run = self.tmp / "runs" / "bare"
        a_run(run, "pi")
        code, lines = call("actions", "--run", run, "--step", "s")
        self.assertEqual((code, len(lines)), (1, 1), lines)
        self.assertIn("no pi session file", lines[0])


class TheTextIsBounded(TempCase):

    def test_8_a_long_transcript_keeps_the_newest_calls(self):
        run = self.tmp / "runs" / "long"
        adir = a_run(run, "pi")
        records = [{"type": "session", "timestamp": iso(MS)}]
        for i in range(200):
            t = MS + i * 1000
            records.append({"type": "message", "timestamp": iso(t + 500),
                            "message": {"role": "assistant", "timestamp": t,
                                        "responseId": f"P{i}",
                                        "usage": {"input": 100, "output": 1},
                                        "content": [{"type": "toolCall",
                                                     "id": f"t{i}", "name": "bash",
                                                     "arguments": {"command": "x" * 400}}]}})
            records.append({"type": "message", "timestamp": iso(t + 600),
                            "message": {"role": "toolResult", "toolCallId": f"t{i}",
                                        "isError": False, "content": []}})
        jsonl(adir / "session" / "s.jsonl", records)
        code, lines = call("actions", "--run", run, "--step", "s")
        self.assertEqual(code, 0)
        self.assertLessEqual(len("\n".join(lines)), actions.TEXT_CAP)
        self.assertTrue(all(len(l) <= actions.LINE_CAP for l in lines))
        cut = next(l for l in lines if l.startswith("... "))
        self.assertRegex(cut, r"^\.\.\. \d+ earlier calls not shown; "
                              r"--json carries every call$")
        self.assertTrue(lines[-2].startswith("call 200 "), lines[-3:])

    def test_9_json_carries_the_schema_and_every_key(self):
        run = self.tmp / "runs" / "j"
        pi_attempt(a_run(run, "pi"))
        code, lines = call("actions", "--run", run, "--step", S, "--json")
        self.assertEqual(code, 0, lines)
        view = json.loads("\n".join(lines))
        self.assertEqual(view["schema"], "ohflow.actions/1")
        for key in ("step", "attempt", "source", "calls", "totals", "unjoined"):
            self.assertIn(key, view)
        c = view["calls"][0]
        for key in ("n", "key", "at", "latency_s", "tokens", "text", "error",
                    "evidence", "actions"):
            self.assertIn(key, c)
        act = c["actions"][0]
        for key in ("tool", "summary", "at", "duration_s", "ok", "first_line",
                    "evidence", "result_evidence"):
            self.assertIn(key, act)


class SummariesReadLikeTheCommand(TempCase):
    """Found on the recorded runs: absolute paths and codex's shell wrapper
    filled the 120-character summary before the command began."""

    def test_10_codex_wrapper_is_dropped_and_worktree_paths_are_short(self):
        run = self.tmp / "runs" / "wrap"
        adir = a_run(run, "codex")
        wt = self.tmp / "wt"
        (adir / "spec.json").write_text(json.dumps({"workspace": str(wt)}),
                                        encoding="utf-8")
        inner = f"Get-Content -Raw -LiteralPath '{wt}\\src\\app.py'"
        wrapped = ('"C:\\Program Files\\PowerShell\\7\\pwsh.exe" -Command "'
                   + inner.replace("\\", "\\\\") + '"')
        jsonl(adir / "logs" / "codex-events.jsonl", [
            {"type": "turn.started"},
            {"type": "item.started", "item": {"id": "i1", "type": "command_execution",
                                              "command": wrapped}},
            {"type": "item.completed", "item": {"id": "i1", "type": "command_execution",
                                                "command": wrapped, "exit_code": 1,
                                                "aggregated_output": "ParserError:"}},
        ])
        code, lines = call("actions", "--run", run, "--step", "s")
        self.assertEqual(code, 0, lines)
        self.assertEqual(lines[3], "  shell Get-Content -Raw -LiteralPath "
                                   "'./src\\app.py' -> failed (- s): "
                                   "ParserError: · line 3")

    def test_11_a_claude_file_tool_shows_its_path_relative_to_the_worktree(self):
        run = self.tmp / "runs" / "rel"
        adir = a_run(run, "claude")
        wt = self.tmp / "wt"
        (adir / "spec.json").write_text(json.dumps({"workspace": str(wt)}),
                                        encoding="utf-8")
        jsonl(adir / "logs" / "claude-events.jsonl", [
            {"type": "assistant", "timestamp": iso(MS),
             "message": {"id": "m", "usage": {}, "content": [
                 {"type": "tool_use", "id": "u", "name": "Read",
                  "input": {"file_path": str(wt / "docs" / "a.md")}}]}},
        ])
        code, lines = call("actions", "--run", run, "--step", "s")
        self.assertEqual(code, 0, lines)
        self.assertEqual(lines[3], "  Read docs/a.md -> pending (- s) · line 1")

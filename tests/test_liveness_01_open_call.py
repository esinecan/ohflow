"""An open tool call suspends the stall clock; the command time cap replaces it.

Measured 2026-10-10 (M0 spikes, `docs/history/silent-command-liveness.md`): pi
and codex print nothing while a silent command runs, so the stall check
killed healthy agents. These tests drive `CliAgentRuntime` with a stub agent
whose events say when a tool call opens and closes.
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

from ohflow import cli_harness_executor as che
from ohflow.cli_harness_executor import CliAgentRuntime, CliEventAction, CliPreparedProcess
from ohflow.tool_output import CallEvent, calls
from support import TempCase


class ScriptAdapter:
    """Prints `spec["script"]`: event dicts, and {"sleep": s} pauses."""

    name = "script"
    event_log_name = "script-events.jsonl"
    stderr_log_name = "script-stderr.log"

    def prepare(self, spec, out_dir):
        program = (
            "import json,sys,time\n"
            f"for step in {spec['script']!r}:\n"
            "    if 'sleep' in step: time.sleep(step['sleep']); continue\n"
            "    print(json.dumps(step), flush=True)\n")
        return CliPreparedProcess(argv=(sys.executable, "-c", program),
                                  cwd=Path(spec["workspace"]), env=dict(os.environ))

    def parse_event(self, line):
        return json.loads(line)

    def on_event(self, spec, event, events):
        kind = event.get("kind")
        if kind == "start":
            return CliEventAction(calls=(CallEvent("start", event["id"], tool="bash",
                                                   command=event.get("command")),))
        if kind == "out":
            return CliEventAction(calls=(CallEvent("output", event["id"],
                                                   text=event["text"]),))
        if kind == "end":
            return CliEventAction(calls=(CallEvent("end", event["id"], ok=True,
                                                   text=event.get("text")),))
        return CliEventAction()

    def build_result(self, outcome):
        return ({"coord": outcome.spec["coord"], "attempt": outcome.spec["attempt"],
                 "execution_status": "finished", "error": outcome.stop_error}, "done\n")


def _spec(tmp: Path, script, **extra):
    return {"coord": "01.s", "attempt": 1, "workspace": str(tmp), "script": script,
            **extra}


class OpenCallTests(TempCase):

    def run_script(self, script, **extra):
        out = self.tmp / "attempt"
        out.mkdir(exist_ok=True)
        return CliAgentRuntime(ScriptAdapter()).run(_spec(self.tmp, script, **extra), out), out

    def test_silent_open_call_twice_the_stall_limit_survives(self):
        result, out = self.run_script(
            [{"kind": "start", "id": "c1", "command": "sleep 3"}, {"sleep": 2.5},
             {"kind": "end", "id": "c1", "text": "slept\n"}, {"kind": "answer"}],
            stall_timeout_s=1)
        self.assertIsNone(result["error"])
        self.assertNotIn("open_tool_call", result)
        [call] = calls(out)
        self.assertEqual(call["command"], "sleep 3")
        self.assertTrue(call["ok"])
        self.assertEqual((out / "logs/tool-output" / call["file"]).read_text(), "slept\n")

    def test_silence_with_no_open_call_is_a_stall(self):
        result, _ = self.run_script(
            [{"kind": "think"}, {"sleep": 4}, {"kind": "answer"}], stall_timeout_s=1)
        self.assertEqual(result["error"], "stall")
        self.assertNotIn("open_tool_call", result)

    def test_open_call_past_the_command_time_cap_stops_with_command_time_cap(self):
        old = che.COMMAND_TIME_CAP_GRACE_S
        che.COMMAND_TIME_CAP_GRACE_S = 0
        self.addCleanup(setattr, che, "COMMAND_TIME_CAP_GRACE_S", old)
        result, out = self.run_script(
            [{"kind": "start", "id": "c1", "command": "hang"},
             {"kind": "out", "id": "c1", "text": "partial line\n"}, {"sleep": 6},
             {"kind": "end", "id": "c1"}],
            stall_timeout_s=30, command_time_cap_s=1, execution_timeout_s=600)
        self.assertTrue(result["error"].startswith("command_time_cap:"), result["error"])
        open_call = result["open_tool_call"]
        self.assertEqual(open_call["command"], "hang")
        self.assertGreaterEqual(open_call["since_s"], 1)
        self.assertTrue((out / open_call["file"]).read_text().startswith("partial line"))
        [call] = calls(out)
        self.assertIsNotNone(call["ended"], "the runtime closes calls the kill left open")

    def test_an_agent_that_answered_is_not_stalled_while_it_shuts_down(self):
        """An agent can finish its answer, then spend more than 45 s closing its MCP
        fleet (live roll call, 2026-10-10). The exit grace governs that time."""
        import time as _time

        class Answered(ScriptAdapter):
            def answered_at(self, prepared, out_dir):
                return self.at

        adapter = Answered()
        adapter.at = _time.time()
        out = self.tmp / "attempt"
        out.mkdir()
        result = CliAgentRuntime(adapter).run(
            _spec(self.tmp, [{"kind": "answer"}, {"sleep": 3}], stall_timeout_s=1), out)
        self.assertIsNone(result["error"])

    def test_poll_calls_feeds_the_open_set(self):
        class Polling(ScriptAdapter):
            polled = False

            def poll_calls(self, prepared, out_dir):
                if self.polled:
                    return []
                self.polled = True
                return [CallEvent("start", "p1", tool="pwsh", command="Start-Sleep 3")]

        out = self.tmp / "attempt"
        out.mkdir()
        result = CliAgentRuntime(Polling()).run(
            _spec(self.tmp, [{"sleep": 3}, {"kind": "answer"}], stall_timeout_s=1), out)
        self.assertIsNone(result["error"])
        self.assertEqual(result["open_tool_call"]["command"], "Start-Sleep 3")


if __name__ == "__main__":
    unittest.main()

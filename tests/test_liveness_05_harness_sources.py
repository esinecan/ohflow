"""Each harness executor's own source feeds the tool-output contract.

claude: tool_use/tool_result events, plus `shell_tee.sh` (the
CLAUDE_CODE_SHELL_PREFIX wrapper) for live Bash output.
Measured sources: `docs/history/silent-command-liveness.md`.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from support import TempCase

from ohflow import tool_output
from ohflow.claude_runner import SHELL_TEE, ClaudeAdapter, shell_capture_env
from ohflow.paths import posix
from ohflow.tool_output import ToolOutputWriter, calls, out_dir_of

BASH = r"C:\Program Files\Git\bin\bash.exe"
WINDOWLESS = ({"creationflags": subprocess.CREATE_NO_WINDOW}
              if sys.platform == "win32" else {})


class ClaudeSources(TempCase):

    def test_tool_use_and_tool_result_open_and_close_a_call(self):
        w = ToolOutputWriter(self.tmp)
        adapter = ClaudeAdapter()
        use = {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "toolu_1", "name": "Bash",
             "input": {"command": "npm test"}}]}}
        result = {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "toolu_1", "is_error": True,
             "content": [{"type": "text", "text": "1 failing"}]}]}}
        for event in (use, result):
            for call in adapter.on_event({}, event, [event]).calls:
                w.apply(call)
        [c] = calls(self.tmp)
        self.assertEqual((c["tool"], c["command"], c["ok"]), ("Bash", "npm test", False))
        self.assertEqual((out_dir_of(self.tmp) / c["file"]).read_text(), "1 failing")

    def test_the_prefix_wrapper_copies_output_and_keeps_the_exit_code(self):
        if not Path(BASH).exists():
            self.skipTest("Git Bash is not installed")
        env = {**os.environ, **shell_capture_env(self.tmp)}
        self.assertEqual(env["CLAUDE_CODE_SHELL_PREFIX"], posix(SHELL_TEE))
        line = ("source /dev/null && eval 'echo one; echo two >&2; exit 4' < /dev/null"
                " && pwd -P >| /dev/null")
        proc = self.prefixed(env, line)
        self.assertEqual(proc.returncode, 4)
        self.assertEqual(proc.stdout, "one\ntwo\n")
        self.assertEqual(proc.stderr, "")
        w = ToolOutputWriter(self.tmp)
        w.start("toolu_9", "Bash", "echo one; echo two >&2; exit 4", at=time.time() - 5)
        [c] = calls(self.tmp)
        self.assertTrue(c["live_file"].startswith("sh-"))
        self.assertEqual(tool_output.tail(tool_output.output_path(self.tmp, c)),
                         ["one", "two"])

    def prefixed(self, env, line):
        quoted = "'" + line.replace("'", "'\\''") + "'"
        return subprocess.run([BASH, "-c", f"{env['CLAUDE_CODE_SHELL_PREFIX']} {quoted}"],
                              env=env, capture_output=True, text=True, timeout=60,
                              **WINDOWLESS)

    def test_mcp_servers_and_hooks_keep_their_own_streams(self):
        """Claude also starts stdio MCP servers and hooks through the prefix.
        Their stderr must stay apart from stdout, and nothing is copied."""
        if not Path(BASH).exists():
            self.skipTest("Git Bash is not installed")
        env = {**os.environ, **shell_capture_env(self.tmp)}
        proc = self.prefixed(env, "echo protocol; echo log >&2; exit 2")
        self.assertEqual((proc.returncode, proc.stdout, proc.stderr),
                         (2, "protocol\n", "log\n"))
        self.assertFalse(out_dir_of(self.tmp).exists())

    def test_the_command_is_read_back_from_claudes_quoting(self):
        wrapped = ("source /x.sh 2>/dev/null || true && { \\builtin unalias -- 'u'; } "
                   ">/dev/null 2>&1 || true && eval 'python -c \"print('\"'\"'A'\"'\"')\"' "
                   "< /dev/null && pwd -P >| /tmp/cwd")
        self.assertEqual(tool_output._shell_command(wrapped), "python -c \"print('A')\"")

    def test_no_capture_when_a_path_has_a_space(self):
        self.assertEqual(shell_capture_env(self.tmp / "with space"), {})

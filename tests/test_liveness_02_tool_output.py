"""The tool-output contract: writer, size cap, shell-wrapper pairing, reader."""

from __future__ import annotations

import json
import os
import time
import unittest

from ohflow import tool_output as to
from ohflow.tool_output import CallEvent, ToolOutputWriter, calls, open_calls, tail
from support import TempCase


class WriterTests(TempCase):

    def test_delta_and_cumulative_output(self):
        w = ToolOutputWriter(self.tmp)
        w.start("a", "bash", "echo")
        w.write("a", "one\n")
        w.write("a", "two\n")
        w.start("b", "bash", "cumulative")
        w.write("b", "x\n", cumulative=True)
        w.write("b", "x\ny\n", cumulative=True)
        w.end("a", ok=True, exit=0)
        w.end("b", ok=False, exit=3)
        got = {c["id"]: c for c in calls(self.tmp)}
        d = to.out_dir_of(self.tmp)
        self.assertEqual((d / got["a"]["file"]).read_text(), "one\ntwo\n")
        self.assertEqual((d / got["b"]["file"]).read_text(), "x\ny\n")
        self.assertEqual(got["b"]["exit"], 3)
        self.assertEqual(open_calls(self.tmp), [])

    def test_cumulative_output_appends_and_rewrites_when_the_prefix_breaks(self):
        w = ToolOutputWriter(self.tmp)
        w.start("a", "bash", "chatty")
        w.write("a", "1\n", cumulative=True)
        w.write("a", "1\n2\n", cumulative=True)
        w.write("a", "1\n2\n3\n", cumulative=True)
        w.write("a", "3\n4\n", cumulative=True)        # the harness trimmed its buffer
        w.end("a")
        [c] = calls(self.tmp)
        self.assertEqual((to.out_dir_of(self.tmp) / c["file"]).read_text(), "3\n4\n")

    def test_end_text_fills_a_call_with_no_live_output(self):
        w = ToolOutputWriter(self.tmp)
        w.start("a", "bash", "x")
        w.end("a", ok=True, text="final\n")
        [c] = calls(self.tmp)
        self.assertEqual((to.out_dir_of(self.tmp) / c["file"]).read_text(), "final\n")

    def test_size_cap_keeps_head_and_tail(self):
        old = (to.CAP_BYTES, to.HEAD_BYTES)
        to.CAP_BYTES, to.HEAD_BYTES = 200, 50
        self.addCleanup(lambda: setattr(to, "CAP_BYTES", old[0]) or
                        setattr(to, "HEAD_BYTES", old[1]))
        w = ToolOutputWriter(self.tmp)
        w.start("a", "bash", "loud")
        w.write("a", "H" * 60)
        for _ in range(10):
            w.write("a", "m" * 30)
        w.write("a", "TAILEND")
        w.end("a")
        [c] = calls(self.tmp)
        data = (to.out_dir_of(self.tmp) / c["file"]).read_text()
        self.assertLessEqual(len(data.encode()), 200)
        self.assertTrue(data.startswith("H" * 50))
        self.assertTrue(data.endswith("TAILEND"))
        self.assertIn("kept the head and the tail", data)
        self.assertTrue(c["truncated"])

    def test_tail_reads_last_lines(self):
        p = self.tmp / "f.log"
        p.write_text("".join(f"line {i}\n" for i in range(100)))
        self.assertEqual(tail(p, 3), ["line 97", "line 98", "line 99"])
        self.assertEqual(tail(None), [])


class ShellPairingTests(TempCase):

    def _shell(self, sid, wrapped, started, ended=None, body="", rc=0):
        d = to.out_dir_of(self.tmp)
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{sid}.cmd").write_text(wrapped)
        (d / f"{sid}.log").write_text(body)
        with (d / to.SHELL_INDEX).open("a") as fh:
            fh.write(json.dumps({"event": "start", "id": sid, "tool": "Bash",
                                 "at": started, "file": f"{sid}.log"}) + "\n")
            if ended is not None:
                fh.write(json.dumps({"event": "end", "id": sid, "at": ended,
                                     "exit": rc}) + "\n")

    def test_wrapper_entry_pairs_with_its_tool_call(self):
        now = time.time()
        w = ToolOutputWriter(self.tmp)
        w.start("toolu_1", "Bash", "echo 'hi' && sleep 2", at=now)
        self._shell("sh-snap", "source x && eval 'snapshot' < /dev/null", now - 5, now - 4)
        wrapped = ("source /tmp/snap && eval 'echo '\\''hi'\\'' && sleep 2' "
                   "< /dev/null && pwd -P >| /tmp/cwd")
        self._shell("sh-1", wrapped, now + 0.2, None, body="hi\n")
        [c] = calls(self.tmp)
        self.assertEqual(c["id"], "toolu_1")
        self.assertEqual(c["live_file"], "sh-1.log")
        self.assertEqual(tail(to.output_path(self.tmp, c)), ["hi"])

    def test_detached_when_output_keeps_growing_after_the_call_ended(self):
        now = time.time()
        w = ToolOutputWriter(self.tmp)
        w.start("toolu_1", "Bash", "long", at=now - 30)
        w.end("toolu_1", ok=True, at=now - 20)
        self._shell("sh-1", "eval 'long' < /dev/null", now - 29.8, None, body="still\n")
        [c] = calls(self.tmp)
        self.assertTrue(c["detached"])

    def test_unpaired_shell_entries_stand_alone_without_events(self):
        now = time.time()
        self._shell("sh-1", "eval 'ls' < /dev/null", now, now + 1, body="a\n")
        [c] = calls(self.tmp)
        self.assertEqual(c["command"], "ls")
        self.assertEqual(c["source"], "shell")


if __name__ == "__main__":
    unittest.main()

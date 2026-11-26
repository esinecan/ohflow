"""The dashboard and the exit report read the tool-output contract.

A live agent shows the command it waits on and its output so far; a finished
attempt shows each call's output; a stopped attempt names the call that was
open when it stopped.
"""

from __future__ import annotations

import json
import time

from dashboard_support import T0, RunLog, agent, workflow_json
from support import TempCase
from test_dashboard_07_data import live_run

from ohflow import dashboard_data, exit_report
from ohflow.tool_output import ToolOutputWriter


ATTEMPT = ("phases", "01.build", "01.worker", "attempts", "01")


def _attempt(run):
    return run.joinpath(*ATTEMPT)


class LiveCommandOutput(TempCase):

    def setUp(self):
        super().setUp()
        self.run = live_run(self.tmp / "live-run")
        w = ToolOutputWriter(_attempt(self.run))
        w.start("call-9", "bash", "python -m pytest", at=T0 + 100)
        w.write("call-9", "collected 40 items\n....\n")
        self.now = T0 + 400

    def test_running_invocation_carries_the_open_command_and_its_tail(self):
        inv = dashboard_data.workflow_data(self.run, now=self.now)["invocations"][0]
        cmd = inv["activity"]["command_output"]
        self.assertTrue(cmd["open"])
        self.assertEqual(cmd["command"], "python -m pytest")
        self.assertEqual(cmd["lines"], ["collected 40 items", "...."])
        self.assertEqual(cmd["since_s"], 300.0)
        self.assertIn("stall clock waits", inv["health"]["note"])


class FinishedAndStopped(TempCase):

    def setUp(self):
        super().setUp()
        self.run = self.tmp / "run"
        workflow_json(self.run, [("Build", [agent("worker", harness_executor="codex")], 1)])
        log = RunLog(self.run)
        log.phase(1, "01.build", "Build", ["01.build/01.worker"], 1)
        log.start(2, "01.build/01.worker", 1)
        log.finish(90, "01.build/01.worker", 1, "failed", wall=88.0,
                   error="command_time_cap: bash call open longer than 61 s")
        log.run_finished(91, "failed")
        adir = _attempt(self.run)
        adir.mkdir(parents=True)
        now = time.time()
        w = ToolOutputWriter(adir)
        w.start("i1", "bash", "ls", at=now - 80)
        w.end("i1", ok=True, exit=0, text="README.md\n", at=now - 79)
        w.start("i2", "bash", "npm test", at=now - 70)
        w.write("i2", "> jest\nPASS a.test.js\n")
        w.end("i2", ok=None, at=now - 1)
        (adir / "result.json").write_text(json.dumps({
            "error": "command_time_cap: bash call open longer than 61 s",
            "open_tool_call": {"id": "i2", "tool": "bash", "command": "npm test",
                               "since_s": 69.0,
                               "file": "logs/tool-output/002-i2.log"}}), encoding="utf-8")

    def test_evidence_lists_each_call_with_its_tail(self):
        ev = dashboard_data.evidence_data(self.run, "01.build/01.worker", 1)
        out = ev["tool_output"]
        self.assertEqual(out["total"], 2)
        self.assertEqual([c["command"] for c in out["calls"]], ["ls", "npm test"])
        self.assertEqual(out["calls"][0]["tail"], ["README.md"])
        self.assertEqual(out["calls"][1]["tail"], ["> jest", "PASS a.test.js"])
        self.assertEqual(ev["open_tool_call"]["id"], "i2")

    def test_exit_report_names_the_call_open_when_it_stopped(self):
        read_out = exit_report.build(self.run, {"status": "failed"})
        md = exit_report.render_md(read_out)
        self.assertIn("open when it stopped: bash `npm test` for 69.0 s", md)
        self.assertIn("PASS a.test.js", md)

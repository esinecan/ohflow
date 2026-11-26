"""Dashboard S2, test 9: `ohflow report` on a run nobody finished.

A hard kill or a machine restart runs no code, so the run is left with a
run log that never reached `run_finished` and no exit report. `ohflow report
--run DIR` rebuilds the three files from what is on disk and calls the run
`orphaned`. It reads the same read-out the live dashboard reads.
"""

from __future__ import annotations

import json

from dashboard_support import (G1_RUN, RunLog, copy_tree, mark_alive,
                               workflow_json, agent)
from ohflow import cli, exit_report
from support import TempCase, quiet


class ReportOnAnOrphanedRun(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.run = self.run_dir("r-orphaned")
        workflow_json(self.run, [("Map", [agent("a"), agent("b")], 2)])
        (RunLog(self.run).phase(1, "01.map", "Map",
                                ["01.map/01.a", "01.map/02.b"])
         .start(2, "01.map/01.a")
         .start(3, "01.map/02.b")
         .finish(40, "01.map/02.b", 1, "passed"))
        (self.run / "supervisor.pid").write_text("2147483646",
                                                 encoding="utf-8")
        (self.run / "run.json").write_text(json.dumps({
            "run_id": "r-orphaned", "workflow_path": "C:/workflows/p.py",
            "workflow_args": {}}), encoding="utf-8")

    def report(self) -> tuple[int, str]:
        with quiet() as output:
            code = cli.main(["report", "--run", str(self.run)])
        return code, output.out

    def test_the_report_calls_it_orphaned(self):
        code, out = self.report()
        self.assertEqual(code, cli.EXIT_OK)
        self.assertIn("status:  orphaned", out)
        record = json.loads((self.run / "exit.json").read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "orphaned")
        self.assertIn("hard kill", record["error"])
        self.assertTrue((self.run / "exit-report.md").exists())
        self.assertTrue((self.run / "exit-report.html").exists())
        self.assertTrue(record["verdict"].startswith(
            "Run r-orphaned orphaned: 1 of 2 agents passed, 1 interrupted"),
            record["verdict"])
        md = (self.run / "exit-report.md").read_text(encoding="utf-8")
        self.assertIn("`01.map/01.a` was running when the supervisor stopped",
                      md)
        self.assertIn("--resume r-orphaned", md)

    def test_the_report_writes_no_run_log_event(self):
        before = (self.run / "run-log.jsonl").read_bytes()
        self.report()
        self.assertEqual((self.run / "run-log.jsonl").read_bytes(), before)

    def test_a_crash_report_keeps_its_status_and_error(self):
        exit_report.write_exit_report(self.run, exit_report.exit_info(
            "crashed", RuntimeError("boom"), "Traceback\nRuntimeError: boom"))
        self.report()
        record = json.loads((self.run / "exit.json").read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "crashed")
        self.assertEqual(record["error"], "RuntimeError: boom")

    def test_a_live_supervisor_is_reported_as_still_running(self):
        mark_alive(self.run)
        self.report()
        record = json.loads((self.run / "exit.json").read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "running")

    def test_a_directory_that_is_no_run_is_refused(self):
        empty = self.tmp / "not-a-run"
        empty.mkdir()
        with quiet() as output:
            code = cli.main(["report", "--run", str(empty)])
        self.assertEqual(code, cli.EXIT_FAIL)
        self.assertIn("not an ohflow run directory", output.out)
        self.assertEqual(list(empty.iterdir()), [])


class ReportOnAFinishedRun(TempCase):

    def test_a_finished_run_keeps_its_own_status(self):
        run = copy_tree(G1_RUN, self.tmp / "r-g1")
        with quiet():
            code = cli.main(["report", "--run", str(run)])
        self.assertEqual(code, cli.EXIT_OK)
        record = json.loads((run / "exit.json").read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "finished")
        # The G1 run: one deferral on a 429, one auto-resume pass, both agents passed.
        self.assertIn("2 of 2 agents passed, 1 restart", record["verdict"])
        html = (run / "exit-report.html").read_text(encoding="utf-8")
        self.assertIn("<svg", html, "the timeline is inline SVG")
        self.assertIn("01.sweep/01.flaky #01", html)
        md = (run / "exit-report.md").read_text(encoding="utf-8")
        self.assertIn("01 deferred (429) \u2192 02 auto_resume \u2192 passed", md)
        self.assertNotIn("<svg", md, "the timeline is in the HTML report only")

"""Dashboard S2, test 8: an exit report for every exit path that runs code.

`ohflow run` writes `exit.json`, `exit-report.md` and `exit-report.html` when it
stops, whatever stopped it (spec §11). Three paths come from the engine's own
verdict: finished, failed, paused. Two come from an exception `cmd_run` caught:
crashed and interrupted. Those two are simulated by an `Engine.run` that raises
after writing the first run log record, and neither may write a run log event
of its own: a crashed run must stay resumable exactly as an orphaned one is.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from fixtures.real_errors import SCOUT2_RATE_LIMIT_RESULT_ERROR
from ohflow import cli
from ohflow.engine import Engine, PreflightError
from ohflow.workflow import CheckSpec, GateSpec
from support import (FakeHarnessExecutor, TempCase, AgentScript, git_repo,
                     install_fake_harness_executor, quiet, read_run_log, simple_workflow,
                     stub_preflight, agent_step)

FAILING_GATE = GateSpec(checks=(CheckSpec("final_message_matches",
                                          {"regex": r"NEVER-SAID"}),))


class EveryExitPath(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        self.out = self.tmp / "runs"

    def run_cli(self, workflow, run_id: str, **flags):
        original = cli._load
        cli._load = lambda ns: workflow
        self.addCleanup(setattr, cli, "_load", original)
        ns = SimpleNamespace(
            workflow="unused", args=[], max_parallel=None, auto_resume=None,
            out=str(self.out), resume=None, run_id=run_id, detach=False,
            dry_run=False, only_phase=None, no_dashboard=True,
            dashboard_port=None, open_dashboard=False,
            harness_executors=self.harness_executors)
        for k, v in flags.items():
            setattr(ns, k, v)
        with quiet() as output:
            code = cli.cmd_run(ns)
        return code, output.out, self.out / run_id

    def assert_three_files(self, run_dir: Path, status: str) -> dict:
        record = json.loads((run_dir / "exit.json").read_text(encoding="utf-8"))
        self.assertEqual(record["status"], status)
        self.assertRegex(record["at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        md = (run_dir / "exit-report.md").read_text(encoding="utf-8")
        html = (run_dir / "exit-report.html").read_text(encoding="utf-8")
        self.assertIn(record["verdict"], md)
        self.assertTrue(record["verdict"].startswith(
            f"Run {run_dir.name} {status}: "), record["verdict"])
        # The page template, with the final read-out embedded as data.
        self.assertIn('<script id="ohflow-data" type="application/json">{',
                      html)
        self.assertNotIn("<!--OHFLOW:TIMELINE-->", html)
        embedded = html.split('<script id="ohflow-data" type="application/json">',
                              1)[1].split("</script>", 1)[0]
        read_out = json.loads(embedded)
        self.assertEqual(read_out["schema"], "ohflow.read-out/2")
        self.assertEqual(read_out["exit"]["status"], status)
        self.assertEqual(read_out["report"]["verdict"], record["verdict"])
        return record

    def test_finished(self):
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript()))
        workflow = simple_workflow(self.repo, steps=[agent_step("a"),
                                                     agent_step("b")])
        code, out, run_dir = self.run_cli(workflow, "r-finished")
        self.assertEqual(code, cli.EXIT_OK)
        record = self.assert_three_files(run_dir, "finished")
        self.assertIsNone(record["error"])
        self.assertEqual(record["traceback_tail"], [])
        self.assertIn("exit report:", out)
        # The verdict agrees with summary.json, which the engine wrote.
        summary = json.loads((run_dir / "summary.json").read_text(
            encoding="utf-8"))
        statuses = [s["status"] for p in summary["phases"].values()
                    for s in p["steps"].values()]
        self.assertEqual(statuses, ["passed", "passed"])
        self.assertIn("2 of 2 agents passed, 0 restarts", record["verdict"])
        self.assertTrue(json.loads((run_dir / "exit-report.html").read_text(
            encoding="utf-8").split('type="application/json">', 1)[1]
            .split("</script>", 1)[0])["report"]["summary_used"])

    def test_failed(self):
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript()))
        workflow = simple_workflow(self.repo, on_step_failure="abort",
                                   steps=[agent_step("a", gate=FAILING_GATE)])
        code, _out, run_dir = self.run_cli(workflow, "r-failed")
        self.assertEqual(code, cli.EXIT_FAIL)
        record = self.assert_three_files(run_dir, "failed")
        self.assertIn("1 failed", record["verdict"])
        md = (run_dir / "exit-report.md").read_text(encoding="utf-8")
        self.assertIn("## What needs a person", md)
        self.assertIn("`01.only-phase/01.a` failed", md)
        self.assertIn("gate final_message_matches failed", md)
        self.assertIn("### `01.only-phase/01.a` attempt 1 - failed", md)

    def test_paused(self):
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript(
            final_text="", error=SCOUT2_RATE_LIMIT_RESULT_ERROR)))
        workflow = simple_workflow(self.repo, steps=[agent_step("a")])
        code, _out, run_dir = self.run_cli(workflow, "r-paused")
        self.assertEqual(code, cli.EXIT_FAIL)
        record = self.assert_three_files(run_dir, "paused")
        self.assertIn("1 deferred", record["verdict"])
        md = (run_dir / "exit-report.md").read_text(encoding="utf-8")
        self.assertIn("Resume the run with:", md)
        self.assertIn("--resume r-paused", md)

    def _raising_run(self, exc: BaseException):
        def run(engine):
            engine.run_dir.mkdir(parents=True, exist_ok=True)
            engine.run_log.append("run_started", payload={
                "run_id": engine.run_id, "workflow": engine.workflow.name})
            raise exc
        original = Engine.run
        Engine.run = run
        self.addCleanup(setattr, Engine, "run", original)

    def test_crashed(self):
        self._raising_run(RuntimeError("the supervisor fell over"))
        workflow = simple_workflow(self.repo, steps=[agent_step("a")])
        with self.assertRaises(RuntimeError):
            self.run_cli(workflow, "r-crashed")
        run_dir = self.out / "r-crashed"
        record = self.assert_three_files(run_dir, "crashed")
        self.assertEqual(record["error"], "RuntimeError: the supervisor fell over")
        self.assertTrue(record["traceback_tail"])
        self.assertLessEqual(len(record["traceback_tail"]), 20)
        self.assertIn("RuntimeError", record["traceback_tail"][-1])
        events = [r["event"] for r in read_run_log(run_dir)]
        self.assertEqual(events, ["run_started"],
                         "the crash path writes no run log event")

    def test_a_preflight_failure_is_a_crash_and_keeps_its_exit_code(self):
        self._raising_run(PreflightError("preflight failed:\n  - no repo"))
        workflow = simple_workflow(self.repo, steps=[agent_step("a")])
        code, out, run_dir = self.run_cli(workflow, "r-preflight")
        self.assertEqual(code, cli.EXIT_FAIL)
        self.assertIn("preflight failed", out)
        record = self.assert_three_files(run_dir, "crashed")
        self.assertIn("PreflightError: preflight failed", record["error"])

    def test_interrupted(self):
        self._raising_run(KeyboardInterrupt())
        workflow = simple_workflow(self.repo, steps=[agent_step("a")])
        with self.assertRaises(KeyboardInterrupt):
            self.run_cli(workflow, "r-interrupted")
        run_dir = self.out / "r-interrupted"
        record = self.assert_three_files(run_dir, "interrupted")
        self.assertEqual(record["error"], "KeyboardInterrupt")
        events = [r["event"] for r in read_run_log(run_dir)]
        self.assertNotIn("run_finished", events)

    def test_a_dry_run_writes_no_exit_report(self):
        workflow = simple_workflow(self.repo, steps=[agent_step("a")])
        code, _out, run_dir = self.run_cli(workflow, "r-dry", dry_run=True)
        self.assertEqual(code, cli.EXIT_OK)
        self.assertTrue((run_dir / "summary.json").exists())
        for name in ("exit.json", "exit-report.md", "exit-report.html"):
            self.assertFalse((run_dir / name).exists(), name)

    def test_a_directory_another_engine_owns_is_never_written(self):
        run_dir = self.out / "r-owned"
        run_dir.mkdir(parents=True)
        (run_dir / ".ohflow-handoff.json").write_text(json.dumps(
            {"run_id": "r-owned", "token": "the-real-token"}), encoding="utf-8")
        workflow = simple_workflow(self.repo, steps=[agent_step("a")])
        code, out, _ = self.run_cli(workflow, "r-owned",
                                    reservation_token="a-forged-token")
        self.assertEqual(code, cli.EXIT_FAIL)
        self.assertIn("reservation token does not match", out)
        self.assertEqual(sorted(p.name for p in run_dir.iterdir()),
                         [".ohflow-handoff.json"])

"""Dashboard S3: the CLI starts, forwards and stops the dashboard (spec §12).

`ohflow run` starts one dashboard per run after it claims the run directory,
prints `dashboard: http://127.0.0.1:PORT/`, and stops it after the exit report
is written. `--no-dashboard` runs without it, `--dry-run` never starts one,
and a port that cannot be bound is named while the run goes on: a viewer is
never a reason to lose a run. A detached run forwards the flags, and its
supervisor, not the short-lived launcher, is the process that serves.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import unittest
import urllib.request
from pathlib import Path
from types import SimpleNamespace

from ohflow import cli, dashboard
from support import (FakeHarnessExecutor, TempCase, AgentScript, git_repo,
                     install_fake_harness_executor, quiet, simple_workflow, stub_preflight,
                     agent_step, real_process)

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _closed(port: int) -> bool:
    # An open local port answers at once. Windows retries a refused connection
    # for about 1.3 s, so a short timeout tells closed from open in 0.3 s.
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) != 0


class RunStartsItsDashboard(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        self.out = self.tmp / "runs"

    def run_cli(self, run_id: str, **flags):
        workflow = simple_workflow(self.repo, steps=[agent_step("a")])
        original = cli._load
        cli._load = lambda ns: workflow
        self.addCleanup(setattr, cli, "_load", original)
        ns = SimpleNamespace(
            workflow="unused", args=[], max_parallel=None, auto_resume=None,
            out=str(self.out), resume=None, run_id=run_id, detach=False,
            dry_run=False, only_phase=None, no_dashboard=False,
            dashboard_port=None, open_dashboard=False,
            harness_executors=self.harness_executors)
        for k, v in flags.items():
            setattr(ns, k, v)
        with quiet() as output:
            code = cli.cmd_run(ns)
        return code, output.out, self.out / run_id

    def test_the_run_serves_itself_while_it_runs_and_stops_after(self):
        seen: dict = {}
        run_dir = self.out / "r-served"

        def during():
            record = json.loads((run_dir / "dashboard.json").read_text(
                encoding="utf-8"))
            with OPENER.open(record["url"] + "api/read-out", timeout=10) as r:
                seen["read_out"] = json.loads(r.read())
            seen["record"] = record
            return None

        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript(on_poll=during)))
        code, out, _ = self.run_cli("r-served")
        self.assertEqual(code, cli.EXIT_OK)
        record = seen["record"]
        self.assertIn(f"dashboard: http://127.0.0.1:{record['port']}/", out)
        self.assertEqual(record["pid"], os.getpid())
        self.assertTrue(record["supervisor"])
        read_out = seen["read_out"]
        self.assertEqual(read_out["run"]["status"], "running")
        self.assertEqual(read_out["agents"][0]["display"]["state"], "running")
        self.assertTrue(read_out["run"]["supervisor_alive"])
        self.assertTrue(_closed(record["port"]),
                        "the dashboard outlived its run")
        self.assertTrue((run_dir / "exit.json").exists())

    def test_no_dashboard_runs_without_one_and_still_reports(self):
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript()))
        code, out, run_dir = self.run_cli("r-quiet", no_dashboard=True)
        self.assertEqual(code, cli.EXIT_OK)
        self.assertNotIn("dashboard:", out)
        self.assertFalse((run_dir / "dashboard.json").exists())
        self.assertTrue((run_dir / "exit-report.html").exists())

    def test_a_dry_run_starts_no_dashboard(self):
        code, out, run_dir = self.run_cli("r-dry", dry_run=True)
        self.assertEqual(code, cli.EXIT_OK)
        self.assertNotIn("dashboard:", out)
        self.assertFalse((run_dir / "dashboard.json").exists())

    def test_a_taken_port_is_named_and_the_run_goes_on(self):
        blocker = dashboard.start(self.tmp, write_record=False)
        self.addCleanup(blocker.stop)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript()))
        code, out, run_dir = self.run_cli("r-port",
                                          dashboard_port=blocker.port)
        self.assertEqual(code, cli.EXIT_OK)
        self.assertIn("dashboard: not started", out)
        self.assertFalse((run_dir / "dashboard.json").exists())
        self.assertTrue((run_dir / "exit.json").exists())

    def test_open_dashboard_asks_the_browser_and_nothing_else_does(self):
        import webbrowser
        opened: list = []
        original = webbrowser.open
        webbrowser.open = lambda url, *a, **k: opened.append(url) or True
        self.addCleanup(setattr, webbrowser, "open", original)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript()))
        self.run_cli("r-closed")
        self.assertEqual(opened, [], "the browser opens only when asked")
        self.run_cli("r-open", open_dashboard=True)
        self.assertEqual(len(opened), 1)
        self.assertTrue(opened[0].startswith("http://127.0.0.1:"))


class TheFlagsReachTheDetachedSupervisor(TempCase):

    WORKFLOW = ("from pathlib import Path\n"
                "from ohflow.workflow import Phase, Workflow, Step\n"
                "def build(args):\n"
                "    step = Step(id='wait', kind='command', "
                "command='sleep 2; echo DONE', execution_timeout_s=30)\n"
                "    return Workflow(name='detach-dashboard', repo=Path(args['repo']), "
                "phases=(Phase(name='Wait', steps=(step,)),))\n")

    def _capture(self):
        captured: dict = {}

        class FakePopen:
            def __init__(self, argv, **kw):
                captured["argv"] = list(argv)
                self.pid = 4242

        original = subprocess.Popen
        subprocess.Popen = FakePopen
        self.addCleanup(setattr, subprocess, "Popen", original)
        return captured

    def test_the_flags_are_forwarded_only_when_given(self):
        repo = git_repo(self.tmp / "repo")
        workflow = self.tmp / "workflow.py"
        workflow.write_text(self.WORKFLOW, encoding="utf-8")
        captured = self._capture()
        with quiet() as output:
            cli.main(["run", "--workflow", str(workflow), "--out", str(self.tmp / "a"),
                      "--run-id", "r-plain", "--detach", "--json",
                      "--args", f"repo={repo}"])
        argv = captured["argv"]
        for flag in ("--no-dashboard", "--dashboard-port", "--open-dashboard"):
            self.assertNotIn(flag, argv)
        launched = json.loads(output.out)
        self.assertEqual(launched["dashboard"],
                         str(self.tmp / "a" / "r-plain" / "dashboard.json"))

        with quiet():
            cli.main(["run", "--workflow", str(workflow), "--out", str(self.tmp / "b"),
                      "--run-id", "r-flags", "--detach", "--dashboard-port",
                      "8765", "--open-dashboard", "--args", f"repo={repo}"])
        argv = captured["argv"]
        self.assertEqual(argv[argv.index("--dashboard-port") + 1], "8765")
        self.assertIn("--open-dashboard", argv)

        with quiet():
            cli.main(["run", "--workflow", str(workflow), "--out", str(self.tmp / "c"),
                      "--run-id", "r-none", "--detach", "--no-dashboard",
                      "--args", f"repo={repo}"])
        self.assertIn("--no-dashboard", captured["argv"])

    @real_process
    @unittest.skipUnless(sys.platform == "win32", "the detach path is Windows")
    def test_the_detached_supervisor_serves_and_logs_the_url(self):
        # The launcher runs inside a kill-on-close job that permits breakaway,
        # the arrangement `test_defect_07` proves a detached run survives. The
        # harness's own job may forbid breakaway, and that is not the subject.
        from test_defect_07_detached_run_survives import _await_supervisor, _job_for, _kernel32, _supervisor_log

        repo = git_repo(self.tmp / "repo")
        workflow = self.tmp / "workflow.py"
        workflow.write_text(self.WORKFLOW, encoding="utf-8")
        scripts = Path(__file__).resolve().parents[1] / "scripts"
        out = self.tmp / "runs"
        go = self.tmp / "go"
        launcher = self.tmp / "launcher.py"
        launcher.write_text(
            "from pathlib import Path\n"
            "import sys, time\n"
            "while not Path(sys.argv[1]).exists(): time.sleep(0.01)\n"
            "from ohflow.cli import main\n"
            "raise SystemExit(main(['run', '--workflow', sys.argv[2], '--out', "
            "sys.argv[3], '--run-id', 'r-detached', '--detach', '--json', "
            "'--args', "
            "sys.argv[4]]))\n", encoding="utf-8")
        env = dict(os.environ)
        env["PYTHONPATH"] = str(scripts) + os.pathsep + env.get("PYTHONPATH", "")
        env["OHFLOW_BASH"] = os.environ.get(
            "OHFLOW_BASH", r"C:\Program Files\Git\bin\bash.exe")
        log_path = self.tmp / "launcher.log"
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [sys.executable, str(launcher), str(go), str(workflow), str(out),
                 f"repo={repo}"], cwd=str(self.tmp), env=env, stdout=log,
                stderr=subprocess.STDOUT, creationflags=CREATE_NO_WINDOW)
            job = _job_for(process, allow_breakaway=True)
            self.addCleanup(_kernel32().CloseHandle, job)
            go.touch()
            self.assertEqual(process.wait(timeout=60), 0,
                             log_path.read_text(encoding="utf-8"))
        launched = json.loads(log_path.read_text(encoding="utf-8"))
        run_dir = out / "r-detached"
        log = run_dir / "supervisor.log"

        def url_line():
            if not log.exists():
                return None
            for text in log.read_text(encoding="utf-8",
                                      errors="replace").splitlines():
                if text.startswith("dashboard: http://127.0.0.1:"):
                    return text
            return None

        line = _await_supervisor(launched["pid"], url_line)
        self.assertIsNotNone(line, "the detached supervisor logged no URL:\n"
                             + _supervisor_log(run_dir))
        record = json.loads((run_dir / "dashboard.json").read_text(
            encoding="utf-8"))
        self.assertEqual(line, f"dashboard: {record['url']}")
        self.assertEqual(record["pid"], launched["pid"],
                         "the supervisor serves, not the launcher")

        _await_supervisor(launched["pid"], (run_dir / "exit.json").exists)
        self.assertTrue((run_dir / "exit.json").exists(),
                        "the detached supervisor wrote no exit.json:\n"
                        + _supervisor_log(run_dir))
        exit_record = json.loads((run_dir / "exit.json").read_text(
            encoding="utf-8"))
        self.assertEqual(exit_record["status"], "finished")
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not _closed(record["port"]):
            time.sleep(0.2)
        self.assertTrue(_closed(record["port"]))


class TheDashboardCommand(TempCase):

    def setUp(self) -> None:
        super().setUp()
        original = cli._serve_forever
        cli._serve_forever = lambda handle: None
        self.addCleanup(setattr, cli, "_serve_forever", original)
        self.run = self.run_dir("r-view")
        self.run.mkdir(parents=True)
        (self.run / "run-log.jsonl").write_text("", encoding="utf-8")

    def test_it_serves_an_existing_run_directory(self):
        with quiet() as output:
            code = cli.main(["dashboard", "--run", str(self.run)])
        self.assertEqual(code, cli.EXIT_OK)
        record = json.loads((self.run / "dashboard.json").read_text(
            encoding="utf-8"))
        self.assertFalse(record["supervisor"])
        self.assertIn(f"dashboard: {record['url']}", output.out)
        self.assertTrue(_closed(record["port"]))

    def test_a_missing_directory_is_refused(self):
        with quiet() as output:
            code = cli.main(["dashboard", "--run", str(self.tmp / "nope")])
        self.assertEqual(code, cli.EXIT_FAIL)
        self.assertIn("no run directory", output.out)

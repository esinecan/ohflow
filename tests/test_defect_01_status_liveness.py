"""D-01: runs record liveness and status calls dead supervisors orphaned."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import unittest
from types import SimpleNamespace

from ohflow import cli, rundir
from ohflow.engine import Engine
from ohflow.run_log import RunLog
from support import (FakeHarnessExecutor, TempCase, AgentScript, git_repo,
                     install_fake_harness_executor, quiet, simple_workflow, stub_preflight)


class StatusLiveness(TempCase):

    def test_engine_records_its_pid(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript()))
        run_dir = self.run_dir()
        Engine(simple_workflow(repo), run_dir, run_id=run_dir.name,
               verbose=False,
               harness_executors=self.harness_executors).run()
        self.assertGreater(int((run_dir / "supervisor.pid").read_text()), 0)

    def test_dead_unsettled_supervisor_is_orphaned(self):
        run_dir = self.run_dir()
        RunLog(run_dir).append("run_started", payload={
            "run_id": run_dir.name, "workflow": "liveness"})
        (run_dir / "supervisor.pid").write_text("2147483646", encoding="utf-8")
        with quiet() as output:
            code = cli.cmd_status(SimpleNamespace(run=str(run_dir), watch=False))
        self.assertEqual(code, cli.EXIT_OK)
        self.assertTrue(output.out.startswith("orphaned: "), output.out)

    def test_liveness_query_leaves_a_live_process_running(self):
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            creationflags=flags,
        )
        def stop_child():
            if child.poll() is None:
                child.kill()
            child.wait(timeout=5)
        self.addCleanup(stop_child)
        run_dir = self.run_dir()
        RunLog(run_dir).append("run_started", payload={
            "run_id": run_dir.name, "workflow": "live"})
        (run_dir / "supervisor.pid").write_text(str(child.pid), encoding="utf-8")

        state = rundir.open_run(run_dir)

        self.assertEqual(state.status, "running")
        self.assertIsNone(child.poll(), "the liveness query stopped the process")

    @unittest.skipUnless(sys.platform == "win32", "PID reuse is checked on Windows")
    def test_a_reused_pid_is_not_the_supervisor(self):
        """A live process created after the PID file was written is a stranger."""
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        def stop_child():
            if child.poll() is None:
                child.kill()
            child.wait(timeout=5)
        self.addCleanup(stop_child)
        run_dir = self.run_dir()
        RunLog(run_dir).append("run_started", payload={
            "run_id": run_dir.name, "workflow": "reused"})
        pid_file = run_dir / "supervisor.pid"
        pid_file.write_text(str(child.pid), encoding="utf-8")
        an_hour_ago = time.time() - 3600
        os.utime(pid_file, (an_hour_ago, an_hour_ago))

        state = rundir.open_run(run_dir)

        self.assertEqual(state.status, "orphaned")
        self.assertIsNone(child.poll(), "the liveness query stopped the process")

"""Defect 72: `run --detach` printed the pid of the process it launched.

`detach.launch` returns the pid of the process it started. That process is the
supervisor only when nothing wraps it. Under the `wmi` launch method it is the
`cmd.exe` that runs the supervisor, and a Windows virtual environment puts a
redirector in front of the interpreter, so the supervisor is a child of the
launched process. `run --detach` printed the launched pid as `supervisor pid`,
put it in the `pid` of the launch record, and wrote it to `supervisor.pid`.

Now the pid comes from the record the supervisor writes in the run directory:
`.ohflow-owner.json` for a fresh run, and the `supervisor.pid` the engine
writes for a resume. The launched pid is the answer only when no record
arrives before the launcher stops waiting.

The first class fakes `detach.launch`. The second starts a real detached run
through a wrapper script that does not `exec`, which is the wrapped shape on a
POSIX box. Every process it starts is its own, and the cleanup kills by the
recorded pid only.

The wait for the record ends at once when the launched process has died. Off
Windows that process is the launcher's own child, and a dead child answers a
signal until its parent reaps it, so the launcher asks the `Popen` it started.
The third class launches a real process that exits at once.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from ohflow import cli, detach, proc
from support import TempCase, git_repo, real_process
from verb_support import call, live_child

POSIX = os.name != "nt"
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
DEAD_PID = "2147483646"

WORKFLOW = """
from pathlib import Path
from ohflow.workflow import Phase, Workflow, Step

def build(args):
    step = Step(id="a", kind="command", command="sleep 2; echo DONE",
                execution_timeout_s=30)
    return Workflow(name="detach-pid", repo=Path(args["repo"]),
                    phases=(Phase(name="P", steps=(step,)),))
"""

LAUNCHER = """
import sys
sys.executable = sys.argv[1]
from ohflow.cli import main
raise SystemExit(main(["run", "--workflow", sys.argv[2], "--out", sys.argv[3],
                       "--run-id", "r-wrapped", "--detach", "--json",
                       "--no-dashboard", "--args", sys.argv[4]]))
"""

WRAPPER = """#!/bin/sh
"{python}" "$@"
status=$?
exit $status
"""


class RunDetachCase(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.repo = git_repo(self.tmp / "repo")
        self.workflow = self.tmp / "workflow.py"
        self.workflow.write_text(WORKFLOW, encoding="utf-8")
        self.out = self.tmp / "runs"


class RunDetachNamesTheSupervisorNotTheLaunchedProcess(RunDetachCase):

    def setUp(self) -> None:
        super().setUp()
        self.wrapper = live_child(self).pid
        self.supervisor = live_child(self).pid

    def detach(self, run_id: str, *extra, launch):
        with mock.patch.object(detach, "launch", launch):
            return call("run", "--workflow", self.workflow, "--out", self.out,
                        "--run-id", run_id, "--detach", "--no-dashboard",
                        "--args", f"repo={self.repo.as_posix()}", *extra)

    def claims(self, run_id: str):
        """A launch whose supervisor claims the run directory at once, as the
        engine does, while the launched process is a wrapper around it."""
        def launch(argv, **kw):
            (self.out / run_id / ".ohflow-owner.json").write_text(json.dumps(
                {"run_id": run_id, "pid": self.supervisor,
                 "detached_handoff": True}), encoding="utf-8")
            return detach.Launched(pid=self.wrapper, method="wmi")
        return launch

    def resumable(self, run_id: str) -> Path:
        run_dir = self.out / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "run-log.jsonl").write_text("", encoding="utf-8")
        (run_dir / ".ohflow-owner.json").write_text(json.dumps(
            {"run_id": run_id, "pid": int(DEAD_PID)}), encoding="utf-8")
        (run_dir / "supervisor.pid").write_text(DEAD_PID, encoding="utf-8")
        return run_dir

    def test_the_line_names_the_pid_the_owner_file_records(self):
        code, lines = self.detach("r-line", launch=self.claims("r-line"))
        self.assertEqual(code, cli.EXIT_OK, lines)
        self.assertIn(f"supervisor pid: {self.supervisor}", lines)
        self.assertNotIn(f"supervisor pid: {self.wrapper}", lines)

    def test_the_launch_record_and_the_pid_file_name_it_too(self):
        code, lines = self.detach("r-json", "--json",
                                  launch=self.claims("r-json"))
        self.assertEqual(code, cli.EXIT_OK, lines)
        launched = json.loads("\n".join(lines))
        self.assertEqual(launched["pid"], self.supervisor)
        self.assertEqual(launched["launch_method"], "wmi")
        self.assertEqual(
            (self.out / "r-json" / "supervisor.pid").read_text(encoding="utf-8"),
            str(self.supervisor))

    def test_a_resume_names_the_pid_the_engine_writes_after_the_launch(self):
        """A resume claims nothing, so the owner file names the supervisor
        that died. The record is the `supervisor.pid` the engine writes with
        its next run log line."""
        run_dir = self.resumable("r-resume")

        def launch(argv, **kw):
            writer = threading.Timer(0.3, lambda: (
                run_dir / "supervisor.pid").write_text(
                    str(self.supervisor), encoding="utf-8"))
            writer.start()
            self.addCleanup(writer.join)
            return detach.Launched(pid=self.wrapper, method="wmi")

        with mock.patch.object(cli, "DASHBOARD_WAIT_S", 30.0):
            code, lines = self.detach("r-resume", "--resume", "r-resume",
                                      "--json", launch=launch)
        self.assertEqual(code, cli.EXIT_OK, lines)
        self.assertEqual(json.loads("\n".join(lines))["pid"], self.supervisor)

    def test_a_resume_keeps_the_pid_the_engine_wrote_before_the_launcher(self):
        """The `wmi` launch returns seconds after the supervisor started. The
        launcher then finds the engine's `supervisor.pid` and leaves it."""
        run_dir = self.resumable("r-resume")

        def launch(argv, **kw):
            (run_dir / "supervisor.pid").write_text(str(self.supervisor),
                                                    encoding="utf-8")
            return detach.Launched(pid=self.wrapper, method="wmi")

        code, lines = self.detach("r-resume", "--resume", "r-resume",
                                  "--json", launch=launch)
        self.assertEqual(code, cli.EXIT_OK, lines)
        self.assertEqual(json.loads("\n".join(lines))["pid"], self.supervisor)
        self.assertEqual((run_dir / "supervisor.pid").read_text(encoding="utf-8"),
                         str(self.supervisor))

    def test_with_no_record_the_launched_pid_is_the_answer(self):
        code, lines = self.detach(
            "r-none", "--json", launch=lambda argv, **kw: detach.Launched(
                pid=self.wrapper, method="direct"))
        self.assertEqual(code, cli.EXIT_OK, lines)
        self.assertEqual(json.loads("\n".join(lines))["pid"], self.wrapper)
        self.assertEqual(
            (self.out / "r-none" / "supervisor.pid").read_text(encoding="utf-8"),
            str(self.wrapper))


@real_process
@unittest.skipUnless(POSIX, "the wrapper is a shell script")
class ADetachedRunBehindAWrapperNamesItsSupervisor(RunDetachCase):

    def _kill(self, pid: int) -> None:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass

    def test_the_printed_pid_is_the_process_that_owns_the_run(self):
        wrapper = self.tmp / "python-wrapper.sh"
        wrapper.write_text(WRAPPER.format(python=sys.executable),
                           encoding="utf-8")
        wrapper.chmod(0o755)
        launcher = self.tmp / "launcher.py"
        launcher.write_text(LAUNCHER, encoding="utf-8")
        env = proc.agent_env()
        env["PYTHONPATH"] = str(SCRIPTS) + os.pathsep + env.get("PYTHONPATH", "")
        done = subprocess.run(
            [sys.executable, str(launcher), str(wrapper), str(self.workflow),
             str(self.out), f"repo={self.repo.as_posix()}"],
            cwd=str(self.tmp), env=env, capture_output=True, text=True,
            stdin=subprocess.DEVNULL, timeout=120)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        launched = json.loads(done.stdout)
        self.addCleanup(self._kill, launched["pid"])
        run_dir = self.out / "r-wrapped"
        owner_file = run_dir / ".ohflow-owner.json"
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline and not owner_file.exists():
            time.sleep(0.05)
        owner = json.loads(owner_file.read_text(encoding="utf-8"))
        self.assertEqual(launched["pid"], owner["pid"],
                         "the launch record names the wrapper, not the "
                         "supervisor")

        deadline = time.monotonic() + 120
        while time.monotonic() < deadline and proc.pid_alive(owner["pid"]) \
                and not (run_dir / "exit.json").exists():
            time.sleep(0.1)
        self.assertTrue((run_dir / "exit.json").exists(),
                        "the detached run wrote no exit.json")
        self.assertEqual(
            (run_dir / "supervisor.pid").read_text(encoding="utf-8"),
            str(owner["pid"]))


@real_process
class ADeadLaunchedProcessEndsTheWait(RunDetachCase):

    def test_the_launcher_returns_when_the_supervisor_died_at_once(self):
        real_launch = detach.launch
        launched: list[detach.Launched] = []

        def launch(argv, **kw):
            launched.append(real_launch(
                [sys.executable, "-c", "raise SystemExit(3)"], **kw))
            return launched[0]

        began = time.monotonic()
        with mock.patch.object(detach, "launch", launch), \
                mock.patch.object(cli, "DASHBOARD_WAIT_S", 30.0):
            code, lines = call(
                "run", "--workflow", self.workflow, "--out", self.out,
                "--run-id", "r-dead", "--detach", "--no-dashboard", "--json",
                "--args", f"repo={self.repo.as_posix()}")
        waited = time.monotonic() - began
        self.assertEqual(code, cli.EXIT_OK, lines)
        self.assertEqual(json.loads("\n".join(lines))["pid"], launched[0].pid)
        self.assertLess(waited, 15.0,
                        "the launcher waited out a process that had died")
        self.assertFalse(launched[0].alive())


if __name__ == "__main__":
    unittest.main()

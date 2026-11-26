"""Defect 07: a detached run died when its launcher's Windows job closed.

The launcher can itself be a member of a kill-on-close Job Object.  A normal
``Popen`` keeps the detached supervisor in that job, so the CLI returns success
even though closing the launcher job kills the promised background run.

A wait on the detached run ends on the run's own signals: the event reaches the
run log, or the supervisor process exits. Fixed bounds of 10 s, 15 s and 60 s
each failed under the load of a parallel suite run. `LOADED_BOX_WAIT_S` bounds
only the launcher, which exits by itself.

These are real-process tests.  The first assigns a launcher to a kill-on-close
job that permits breakaway, waits until the command step is running, closes the
job, and requires the run log to reach ``run_finished``.  The second uses a
restrictive job; the run must then start through WMI and still finish after the
job closes.  The third uses a restrictive job and no hidden-launch shim, and
requires an explicit, actionable failure.  Silently retrying without breakaway
would make that case lie about being detached.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from ohflow import detach, proc
from support import real_process


WINDOWS = sys.platform == "win32"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
JOB_OBJECT_LIMIT_BREAKAWAY_OK = 0x00000800
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
    )]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def _kernel32():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
    ]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE,
                                                   wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    return kernel32


def _job_for(process: subprocess.Popen, *, allow_breakaway: bool):
    kernel32 = _kernel32()
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    info = _ExtendedLimitInformation()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if allow_breakaway:
        info.BasicLimitInformation.LimitFlags |= JOB_OBJECT_LIMIT_BREAKAWAY_OK
    if not kernel32.SetInformationJobObject(
            job, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(info),
            ctypes.sizeof(info)):
        error = ctypes.WinError(ctypes.get_last_error())
        kernel32.CloseHandle(job)
        raise error
    if not kernel32.AssignProcessToJobObject(
            job, wintypes.HANDLE(process._handle)):
        error = ctypes.WinError(ctypes.get_last_error())
        kernel32.CloseHandle(job)
        raise error
    return job


def _run_log_has(run_dir: Path, event: str, timeout_s: float) -> bool:
    run_log = run_dir / "run-log.jsonl"
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if run_log.exists():
            for line in run_log.read_text(encoding="utf-8").splitlines():
                try:
                    if json.loads(line).get("event") == event:
                        return True
                except json.JSONDecodeError:
                    # A concurrent append can expose the final line briefly.
                    pass
        time.sleep(0.05)
    return False


LOADED_BOX_WAIT_S = 60

SUPERVISOR_HANG_S = 600


def _supervisor_log(run_dir: Path) -> str:
    log = run_dir / "supervisor.log"
    if not log.exists():
        return "(no supervisor.log)"
    return log.read_text(encoding="utf-8", errors="replace")[-2000:]


def _await_supervisor(pid: int, found):
    started = time.monotonic()
    while True:
        alive = proc.pid_alive(pid)
        value = found()
        if value or not alive or time.monotonic() - started > SUPERVISOR_HANG_S:
            return value
        time.sleep(0.1)


def _await_event(run_dir: Path, event: str, pid: int) -> bool:
    """Wait for `event` in the run log while the supervisor `pid` lives."""
    return bool(_await_supervisor(
        pid, lambda: _run_log_has(run_dir, event, 0.01)))


@unittest.skipUnless(WINDOWS, "Windows console creation flags are required")
class SupervisorCommandsStayWindowless(unittest.TestCase):

    def test_command_runner_sets_create_no_window(self):
        """A command step starts through `proc.spawn_managed`, which sets the flag."""
        from ohflow import exec as ohexec, proc

        captured = {}
        original = proc.popen

        def fake_popen(argv, **kwargs):
            captured.update(kwargs)
            return original(argv, **kwargs)

        proc.popen = fake_popen
        try:
            done = ohexec.run("echo DONE", Path(tempfile.gettempdir()))
        finally:
            proc.popen = original

        self.assertTrue(done.ok, done.tail)
        self.assertTrue(captured.get("creationflags", 0) & CREATE_NO_WINDOW)


@real_process
@unittest.skipUnless(WINDOWS, "Windows Job Objects are required")
class DetachedRunSurvivesItsLauncher(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="ohflow-detach-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.scripts = Path(__file__).resolve().parents[1] / "scripts"
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        git_env = dict(os.environ)
        git_env.update({
            "GIT_AUTHOR_NAME": "ohflow tests",
            "GIT_AUTHOR_EMAIL": "tests@localhost",
            "GIT_COMMITTER_NAME": "ohflow tests",
            "GIT_COMMITTER_EMAIL": "tests@localhost",
            "GIT_CONFIG_GLOBAL": str(self.tmp / ".gitconfig-none"),
            "GIT_CONFIG_SYSTEM": str(self.tmp / ".gitconfig-none"),
        })
        self._run(["git", "init", "-q", "-b", "main"], cwd=self.repo,
                  env=git_env)
        (self.repo / "seed").write_text("seed\n", encoding="utf-8")
        self._run(["git", "add", "seed"], cwd=self.repo, env=git_env)
        self._run(["git", "commit", "-qm", "seed"], cwd=self.repo,
                  env=git_env)

        self.workflow = self.tmp / "workflow.py"
        self.workflow.write_text(
            "from pathlib import Path\n"
            "from ohflow.workflow import Phase, Workflow, Step\n"
            "def build(args):\n"
            "    step = Step(id='wait', kind='command', "
            "command='sleep 3; echo DONE', execution_timeout_s=20)\n"
            f"    return Workflow(name='detach-test', repo=Path({str(self.repo)!r}), "
            "phases=(Phase(name='Wait', steps=(step,)),))\n",
            encoding="utf-8",
        )
        self.launcher = self.tmp / "launcher.py"
        self.launcher.write_text(
            "from pathlib import Path\n"
            "import sys, time\n"
            "while not Path(sys.argv[1]).exists(): time.sleep(0.01)\n"
            "from ohflow.cli import main\n"
            "raise SystemExit(main(['run', '--workflow', sys.argv[2], '--out', "
            "sys.argv[3], '--run-id', 'probe', '--detach', '--json']))\n",
            encoding="utf-8",
        )

    def _run(self, argv, *, cwd=None, env=None):
        return subprocess.run(
            argv, cwd=str(cwd) if cwd else None, env=env, check=True,
            capture_output=True, creationflags=CREATE_NO_WINDOW,
        )

    def _launch_in_job(self, *, allow_breakaway: bool,
                       env_extra: dict | None = None):
        go = self.tmp / ("go-allowed" if allow_breakaway else "go-restricted")
        runs = self.tmp / ("runs-allowed" if allow_breakaway else
                           "runs-restricted")
        log_path = self.tmp / ("allowed.log" if allow_breakaway else
                               "restricted.log")
        env = dict(os.environ)
        env["PYTHONPATH"] = str(self.scripts) + os.pathsep + env.get(
            "PYTHONPATH", "")
        env["OHFLOW_BASH"] = os.environ.get(
            "OHFLOW_BASH", r"C:\Program Files\Git\bin\bash.exe")
        env.update(env_extra or {})
        log = log_path.open("w", encoding="utf-8", errors="replace")
        process = subprocess.Popen(
            [sys.executable, str(self.launcher), str(go), str(self.workflow),
             str(runs)],
            cwd=str(self.tmp), env=env, stdout=log,
            stderr=subprocess.STDOUT, creationflags=CREATE_NO_WINDOW,
        )
        try:
            job = _job_for(process, allow_breakaway=allow_breakaway)
        except Exception:
            process.kill()
            process.wait(timeout=10)
            log.close()
            raise
        go.touch()
        return process, job, log, log_path, runs / "probe"

    def test_run_finishes_after_the_launcher_job_closes(self):
        process, job, log, log_path, run_dir = self._launch_in_job(
            allow_breakaway=True)
        try:
            returncode = process.wait(timeout=LOADED_BOX_WAIT_S)
            log.close()
            self.assertEqual(returncode, 0, log_path.read_text(encoding="utf-8"))
            text = log_path.read_text(encoding="utf-8")
            launched = json.loads(text[text.index("{"):])
            self.assertTrue(_await_event(run_dir, "attempt_started",
                                         launched["pid"]),
                            "the command step never started"
                            + ":\n" + _supervisor_log(run_dir))
            self.assertFalse(_run_log_has(run_dir, "run_finished", 0.01),
                             "the command finished before the job-close test")
            self.assertTrue(_kernel32().CloseHandle(job))
            job = None
            self.assertTrue(_await_event(run_dir, "run_finished",
                                         launched["pid"]),
                            "closing the launcher job killed the detached run"
                            + ":\n" + _supervisor_log(run_dir))
        finally:
            if not log.closed:
                log.close()
            if job:
                _kernel32().CloseHandle(job)
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)

    @unittest.skipUnless(detach.run_hidden_shim().is_file(),
                         "the run-hidden.vbs shim is required for the WMI launch method")
    def test_restrictive_job_starts_the_run_through_wmi(self):
        process, job, log, log_path, run_dir = self._launch_in_job(
            allow_breakaway=False)
        try:
            returncode = process.wait(timeout=LOADED_BOX_WAIT_S)
            log.close()
            output = log_path.read_text(encoding="utf-8")
            self.assertEqual(returncode, 0, output)
            self.assertIn('"launch_method": "wmi"', output)
            launched = json.loads(output[output.index("{"):])
            self.assertTrue(_await_event(run_dir, "attempt_started",
                                         launched["pid"]),
                            "the command step never started"
                            + ":\n" + _supervisor_log(run_dir))
            self.assertTrue(_kernel32().CloseHandle(job))
            job = None
            self.assertTrue(_await_event(run_dir, "run_finished",
                                         launched["pid"]),
                            "closing the launcher job killed the WMI run"
                            + ":\n" + _supervisor_log(run_dir))
        finally:
            if not log.closed:
                log.close()
            if job:
                _kernel32().CloseHandle(job)
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)

    def test_restrictive_job_without_a_shim_fails_with_guidance(self):
        process, job, log, log_path, run_dir = self._launch_in_job(
            allow_breakaway=False,
            env_extra={"OHFLOW_RUN_HIDDEN": str(self.tmp / "no-shim.vbs")})
        try:
            returncode = process.wait(timeout=15)
            log.close()
            output = log_path.read_text(encoding="utf-8")
            self.assertEqual(returncode, 1, output)
            self.assertIn("restrictive Windows Job Object", output)
            self.assertIn("outside that job", output)
            self.assertIn("independent broker", output)
            self.assertNotIn("Traceback", output)
            self.assertFalse((run_dir / "supervisor.pid").exists())
        finally:
            if not log.closed:
                log.close()
            if job:
                _kernel32().CloseHandle(job)
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()

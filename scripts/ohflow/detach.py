"""Start a background process that outlives the process that started it.

`run --detach` and `campaign run --detach` both call `launch`. It tries three
launch methods in order and reports the one that worked:

- ``direct``: this process is not in a Windows Job Object, or the platform is
  not Windows. A plain `Popen` is enough on Windows. Off Windows the child
  also starts in a new session, so it outlives the launcher's terminal.
- ``breakaway``: this process is in a job and the job allows
  `CREATE_BREAKAWAY_FROM_JOB`. The child leaves the job, so closing the job
  does not kill it.
- ``wmi``: the job denied breakaway (WinError 5). The child is created by
  `Win32_Process.Create`, so WMI is its parent and the job is not. WMI cannot
  redirect output, so the command runs from a small `.cmd` file that appends
  to the log. A PowerShell script makes the WMI call, and `run-hidden.vbs`
  starts that script with no console window. The script inherits the caller's
  environment from the shim and hands it to WMI as
  `Win32_ProcessStartup.EnvironmentVariables`, so no file holds an
  environment value.

When no launch method works, `launch` raises `DetachFailed`. Its text tells the
operator what to do. The caller prints it and exits 1; nobody prints a traceback.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

from . import proc

WINERROR_ACCESS_DENIED = 5
SHIM_TIMEOUT_S = 60
CREATE_NO_WINDOW = 0x08000000


def run_hidden_shim() -> Path:
    override = os.environ.get("OHFLOW_RUN_HIDDEN")
    if override:
        return Path(override)
    return Path(__file__).with_name("run-hidden.vbs")


@dataclass(frozen=True)
class Launched:
    pid: int
    method: str
    process: subprocess.Popen | None = field(default=None, repr=False,
                                             compare=False)

    def alive(self) -> bool:
        """Whether the launched process still runs.

        Off Windows a `direct` launch is this process's child, and a dead
        child answers a signal until its parent reaps it, so the answer comes
        from the `Popen`. The `wmi` launch has none, and its pid is asked.
        """
        if self.process is not None:
            return self.process.poll() is None
        return proc.pid_alive(self.pid)


class DetachFailed(Exception):
    """No launch method could start a process outside the launcher's job."""


def creationflags() -> tuple[int, bool]:
    """Flags for a windowless child, and whether breakaway was requested."""
    if sys.platform != "win32":
        return 0, False

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.IsProcessInJob.argtypes = [
        wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL),
    ]
    kernel32.IsProcessInJob.restype = wintypes.BOOL
    in_job = wintypes.BOOL()
    if not kernel32.IsProcessInJob(kernel32.GetCurrentProcess(), None,
                                   ctypes.byref(in_job)):
        raise ctypes.WinError(ctypes.get_last_error())
    flags = subprocess.CREATE_NO_WINDOW
    if in_job.value:
        flags |= subprocess.CREATE_BREAKAWAY_FROM_JOB
    return flags, bool(in_job.value)


def _launch_cmd_text(argv: Sequence[str], cwd: str, log_path: Path) -> str:
    lines = [
        "@echo off",
        f'cd /d "{cwd}"',
        f'{subprocess.list2cmdline(list(argv))} >> "{log_path}" 2>&1',
    ]
    return "\r\n".join(lines) + "\r\n"


def _ps_literal(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def _launch_ps1_text(cmd_file: Path, cwd: str, pid_file: Path) -> str:
    command_line = f'cmd.exe /d /s /c ""{cmd_file}""'
    return "\r\n".join([
        "$ErrorActionPreference = 'Stop'",
        "try {",
        "  $pairs = [string[]]@([Environment]::GetEnvironmentVariables()"
        ".GetEnumerator() | Where-Object { $_.Key -notmatch '^=' } | "
        "ForEach-Object { '{0}={1}' -f $_.Key, $_.Value })",
        "  $startup = New-CimInstance -ClassName Win32_ProcessStartup "
        "-ClientOnly -Property @{ ShowWindow = [uint16]0; "
        "EnvironmentVariables = $pairs }",
        "  $made = Invoke-CimMethod -ClassName Win32_Process -MethodName Create "
        f"-Arguments @{{ CommandLine = {_ps_literal(command_line)}; "
        f"CurrentDirectory = {_ps_literal(cwd)}; "
        "ProcessStartupInformation = $startup }",
        "  if ($made.ReturnValue -ne 0) { exit 1 }",
        f"  Set-Content -LiteralPath {_ps_literal(str(pid_file))} "
        "-Value $made.ProcessId -Encoding ascii",
        "  exit 0",
        "} catch { exit 1 }",
        "",
    ])


def _launch_through_wmi(argv: Sequence[str], cwd: str, env: Mapping[str, str],
                        log_path: Path) -> Launched:
    shim = run_hidden_shim()
    if not shim.is_file():
        raise DetachFailed(f"the hidden-launch shim is missing: {shim}")
    cmd_file = log_path.with_name(log_path.name + ".launch.cmd")
    ps1_file = log_path.with_name(log_path.name + ".launch.ps1")
    pid_file = log_path.with_name(log_path.name + ".launch.pid")
    for stale in (pid_file, cmd_file, ps1_file):
        stale.unlink(missing_ok=True)
    try:
        return _start_through_shim(shim, argv, cwd, env, log_path,
                                   cmd_file, ps1_file, pid_file)
    except DetachFailed:
        for leftover in (cmd_file, ps1_file):
            leftover.unlink(missing_ok=True)
        raise


def _start_through_shim(shim: Path, argv: Sequence[str], cwd: str,
                        env: Mapping[str, str], log_path: Path,
                        cmd_file: Path, ps1_file: Path,
                        pid_file: Path) -> Launched:
    cmd_file.write_text(_launch_cmd_text(argv, cwd, log_path),
                        encoding="utf-8", newline="")
    ps1_file.write_text(_launch_ps1_text(cmd_file, cwd, pid_file),
                        encoding="utf-8-sig", newline="")
    try:
        done = proc.run(
            ["wscript.exe", "//B", "//Nologo", str(shim), "powershell.exe",
             "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
             str(ps1_file)],
            env=dict(env), timeout=SHIM_TIMEOUT_S,
            creationflags=CREATE_NO_WINDOW, capture_output=True)
    except (OSError, subprocess.SubprocessError) as error:
        raise DetachFailed(f"the hidden-launch shim did not run: {error}")
    if done.returncode != 0:
        raise DetachFailed(
            f"the hidden-launch shim exited {done.returncode}")
    try:
        pid = int(pid_file.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        raise DetachFailed("WMI Win32_Process.Create returned no process id")
    finally:
        pid_file.unlink(missing_ok=True)
    return Launched(pid=pid, method="wmi")


def launch(argv: Sequence[str], *, cwd: str | os.PathLike,
           env: Mapping[str, str], log_path: str | os.PathLike,
           append: bool = False) -> Launched:
    """Start `argv` in the background with its output going to `log_path`."""
    log_path = Path(log_path)
    cwd = str(cwd)
    flags, breakaway_requested = creationflags()
    log = log_path.open("a" if append else "w", encoding="utf-8",
                        errors="replace")
    try:
        # Off Windows the child leads a new session, so the hangup of the
        # launcher's terminal and an interrupt of its group do not reach it.
        session = {} if sys.platform == "win32" else {"start_new_session": True}
        p = proc.popen(list(argv), env=dict(env), stdout=log,
                       stderr=subprocess.STDOUT, cwd=cwd,
                       creationflags=flags, **session)
        return Launched(pid=p.pid,
                        method="breakaway" if breakaway_requested else "direct",
                        process=p)
    except OSError as error:
        if not (breakaway_requested
                and getattr(error, "winerror", None) == WINERROR_ACCESS_DENIED):
            raise
    finally:
        log.close()

    try:
        return _launch_through_wmi(argv, cwd, env, log_path)
    except DetachFailed as error:
        raise DetachFailed(
            "cannot detach: this launcher is inside a restrictive Windows "
            "Job Object that denied CREATE_BREAKAWAY_FROM_JOB (WinError 5), "
            f"and the WMI launch method failed too ({error}). Run ohflow from "
            "outside that job or through an independent broker.")

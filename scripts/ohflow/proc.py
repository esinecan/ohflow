"""Child processes whose whole tree ends with them.

On Windows a managed child is windowless and sits in a kill-on-close Job
Object. Off Windows it leads its own process group, and the group is the tree.
A group watcher (`group_watcher.py`) ends the groups of an owner that died
without ending them, as the kernel ends the job of a dead owner on Windows.
"""

from __future__ import annotations

import atexit
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

_CURRENT_JOB: Any = None
_CREATE_SUSPENDED = 0x00000004

# Variables a parent Claude Code session exports. An agent inherits none of
# them: it is a fresh signed-in harness, not a child of whatever launched ohflow. Measured
# 2026-09-30 from a desktop-app session: 25 CLAUDE* names plus an
# ANTHROPIC_BASE_URL that points at the desktop app's own proxy.
_PARENT_SESSION_VARS = re.compile(r"^(CLAUDE|CLAUDECODE$|ANTHROPIC_BASE_URL$)")


def agent_env(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """The environment an agent starts with: `base` (default: this process's)
    without the variables of the session that launched ohflow. Every harness executor
    builds an agent's environment from this, so no agent takes its identity
    from the launcher. A variable a harness executor sets on purpose is added afterwards.
    """
    source = os.environ if base is None else base
    return {k: v for k, v in source.items() if not _PARENT_SESSION_VARS.match(k)}


def _kernel32():
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                  ctypes.c_void_p, wintypes.DWORD]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.ResumeThread.argtypes = [wintypes.HANDLE]
    kernel32.ResumeThread.restype = wintypes.DWORD
    kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateJobObject.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    return kernel32


@dataclass
class ManagedProcess:
    process: subprocess.Popen
    job_handle: Any = None
    #: Off Windows: the process group this child leads, or None for a child
    #: that stays in the group of a guarded runner.
    pgid: int | None = None

    @property
    def pid(self) -> int:
        return self.process.pid

    @property
    def returncode(self) -> int | None:
        return self.process.returncode

    def poll(self) -> int | None:
        return self.process.poll()

    def wait(self, timeout: float | None = None) -> int:
        return self.process.wait(timeout=timeout)

    def kill_tree(self, timeout_s: float = 15) -> None:
        if sys.platform != "win32":
            self._posix_kill_tree(timeout_s)
            return
        if self.process.poll() is not None:
            self.close()
            return
        if self.job_handle:
            # KILL_ON_JOB_CLOSE is the ownership contract. Closing the last
            # handle takes descendants even after the direct child re-parented
            # them by exiting, where taskkill /T can no longer find the tree.
            self.close()
        else:
            run(["taskkill", "/F", "/T", "/PID", str(self.process.pid)],
                capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            self.process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            self.process.kill()
        self.close()

    def _posix_kill_tree(self, timeout_s: float) -> None:
        """SIGTERM to the tree, then SIGKILL to what is left after `timeout_s`.

        A child that leads its own group is ended through the group, which
        also holds the descendants of a child that already exited. A child in
        a guarded runner's group is ended with the descendants the process
        table names; that route cannot find descendants once the child exited.
        """
        if self.pgid is not None:
            pgid = self.pgid
            _signal_group(pgid, signal.SIGTERM)
            if not self._group_gone(pgid, timeout_s):
                _signal_group(pgid, signal.SIGKILL)
                self._group_gone(pgid, _REAP_WAIT_S)
            self.pgid = None
            _forget_group(pgid)
        elif self.process.poll() is None:
            victims = [self.process.pid, *_descendants(self.process.pid)]
            for pid in victims:
                _signal_pid(pid, signal.SIGTERM)
            deadline = time.monotonic() + timeout_s
            while time.monotonic() < deadline:
                self.process.poll()
                if not any(_pid_running(pid) for pid in victims):
                    break
                time.sleep(_POLL_S)
            for pid in victims:
                if _pid_running(pid):
                    _signal_pid(pid, signal.SIGKILL)
        try:
            self.process.wait(timeout=_REAP_WAIT_S)
        except subprocess.TimeoutExpired:
            pass

    def _group_gone(self, pgid: int, timeout_s: float) -> bool:
        deadline = time.monotonic() + timeout_s
        while True:
            self.process.poll()  # reap the leader, or it stays a group member
            if not _group_alive(pgid):
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(_POLL_S)

    def close(self) -> None:
        if sys.platform == "win32":
            if self.job_handle:
                _kernel32().CloseHandle(self.job_handle)
                self.job_handle = None
        elif self.pgid is not None:
            # What closing the job does on Windows: nothing of the tree stays.
            pgid, self.pgid = self.pgid, None
            _signal_group(pgid, signal.SIGKILL)
            _forget_group(pgid)


_POLL_S = 0.05
_REAP_WAIT_S = 5.0
_EXIT_GRACE_S = 2.0

# Off Windows: the process groups this process started and has not ended yet.
# On Windows the kernel ends a job when its owner dies. Here the owner ends
# its groups itself, when the interpreter exits and on SIGTERM and SIGHUP.
# The group watcher ends them when the owner dies any other way.
_OWNED_GROUPS: set[int] = set()
_OWNED_LOCK = threading.RLock()

_WATCHER_SCRIPT = Path(__file__).with_name("group_watcher.py")
_WATCHER: subprocess.Popen | None = None
_WATCHER_PIPE: int | None = None
_WATCHER_WAIT_S = 1.0


def _start_watcher() -> None:
    """Start this process's group watcher. It leads its own session, so no
    signal to this process's group reaches it, and it holds the read end of a
    pipe whose write end no other process inherits: the pipe ends when this
    process does. Without a watcher a SIGKILL of this process leaves its
    groups, as before."""
    global _WATCHER, _WATCHER_PIPE
    read_fd, write_fd = os.pipe()
    try:
        _WATCHER = subprocess.Popen(
            [sys.executable, "-I", "-S", str(_WATCHER_SCRIPT),
             str(_EXIT_GRACE_S)],
            stdin=read_fd, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, cwd="/", start_new_session=True)
    except OSError:
        os.close(write_fd)
        return
    finally:
        os.close(read_fd)
    _WATCHER_PIPE = write_fd


def _tell_watcher(word: str) -> None:
    global _WATCHER_PIPE
    if _WATCHER_PIPE is None:
        return
    try:
        os.write(_WATCHER_PIPE, f"{word}\n".encode("ascii"))
    except OSError:
        # The watcher is gone. This process goes on without one. The name is
        # cleared before the close, so a signal handler that lands on the
        # close finds no pipe and cannot close it a second time.
        pipe, _WATCHER_PIPE = _WATCHER_PIPE, None
        if pipe is not None:
            os.close(pipe)


def _close_watcher() -> None:
    global _WATCHER, _WATCHER_PIPE
    with _OWNED_LOCK:
        watcher, _WATCHER = _WATCHER, None
        pipe, _WATCHER_PIPE = _WATCHER_PIPE, None
    if pipe is not None:
        os.close(pipe)
    if watcher is not None:
        try:
            watcher.wait(timeout=_WATCHER_WAIT_S)
        except subprocess.TimeoutExpired:
            pass


def _own_group(pgid: int) -> None:
    with _OWNED_LOCK:
        _OWNED_GROUPS.add(pgid)
        if _WATCHER is None:
            _start_watcher()
        _tell_watcher(f"+{pgid}")


def _forget_group(pgid: int) -> None:
    with _OWNED_LOCK:
        _OWNED_GROUPS.discard(pgid)
        _tell_watcher(f"-{pgid}")


def end_owned_groups(grace_s: float = _EXIT_GRACE_S) -> None:
    """End every process group this process still owns: SIGTERM, then SIGKILL
    to what is left after `grace_s`. Does nothing on Windows, where closing
    the job does this."""
    with _OWNED_LOCK:
        groups = sorted(_OWNED_GROUPS)
        _OWNED_GROUPS.clear()
    if not groups:
        return
    for pgid in groups:
        _signal_group(pgid, signal.SIGTERM)
    deadline = time.monotonic() + grace_s
    while time.monotonic() < deadline and any(_group_alive(g) for g in groups):
        time.sleep(_POLL_S)
    for pgid in groups:
        _signal_group(pgid, signal.SIGKILL)
    with _OWNED_LOCK:
        for pgid in groups:
            _tell_watcher(f"-{pgid}")


def install_exit_signals() -> None:
    """Make SIGTERM and SIGHUP end this process's managed children first.

    An interrupt needs no handler: it raises `KeyboardInterrupt`, the
    interpreter exits, and the exit hook ends the groups. SIGTERM and SIGHUP
    end a process at once by default, so each gets a handler that ends the
    groups and then lets the signal end this process as it would have. A
    handler someone else set stays. Call it from the main thread of a
    command-line process; it does nothing on Windows.
    """
    if sys.platform == "win32":
        return
    if threading.current_thread() is not threading.main_thread():
        return

    def handler(signum, _frame):
        end_owned_groups()
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)

    for signum in (signal.SIGTERM, signal.SIGHUP):
        if signal.getsignal(signum) is signal.SIG_DFL:
            signal.signal(signum, handler)


if sys.platform != "win32":
    # Exit hooks run last registered first: the groups end, then the watcher.
    atexit.register(_close_watcher)
    atexit.register(end_owned_groups)


def _signal_group(pgid: int, sig: int) -> None:
    try:
        os.killpg(pgid, sig)
    except (ProcessLookupError, PermissionError):
        pass  # the group is empty, or holds only processes not yet reaped


def _signal_pid(pid: int, sig: int) -> None:
    try:
        os.kill(pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except (ProcessLookupError, PermissionError):
        # macOS answers EPERM for a group that holds only zombies.
        return False
    return True


def _pid_running(pid: int) -> bool:
    """Whether `pid` is a process that still runs; a zombie does not."""
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    try:
        state = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)],
                               capture_output=True, text=True,
                               timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return True
    return bool(state) and not state.startswith("Z")


def _descendants(pid: int) -> list[int]:
    """Every live descendant of `pid`, nearest first, from the process table."""
    children: dict[int, list[int]] = {}
    for child, parent in _process_table():
        children.setdefault(parent, []).append(child)
    found: list[int] = []
    queue = [pid]
    while queue:
        parent = queue.pop(0)
        for child in children.get(parent, []):
            if child not in found and _started_under(child, parent):
                found.append(child)
                queue.append(child)
    return found


def _process_table() -> list[tuple[int, int]]:
    """The pid and the parent pid of every process."""
    if sys.platform == "win32":
        return _nt_process_table()
    try:
        table = subprocess.run(["ps", "-axo", "pid=,ppid="],
                               capture_output=True, text=True,
                               timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    pairs = []
    for line in table.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            pairs.append((int(parts[0]), int(parts[1])))
    return pairs


def _nt_process_table() -> list[tuple[int, int]]:
    import ctypes
    from ctypes import wintypes

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel32 = _kernel32()
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE,
                                         ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE,
                                        ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32NextW.restype = wintypes.BOOL

    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)  # SNAPPROCESS
    if not snapshot or snapshot == ctypes.c_void_p(-1).value:
        return []
    pairs = []
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        more = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            pairs.append((int(entry.th32ProcessID),
                          int(entry.th32ParentProcessID)))
            more = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return pairs


def _started_under(child: int, parent: int) -> bool:
    """Whether `child` can be a child of the process that holds `parent` now.

    Windows keeps the parent's pid in a child after the parent died and reuses
    pids, so a process older than `parent` is a stranger whose parent once
    held that number. Elsewhere a child of a dead parent gets a new parent.
    """
    if sys.platform != "win32":
        return True
    born, parent_born = _nt_created(child), _nt_created(parent)
    return born is not None and parent_born is not None and born >= parent_born


def _nt_created(pid: int) -> int | None:
    """When the process `pid` was created, in FILETIME ticks; None when it
    cannot be read."""
    import ctypes
    from ctypes import wintypes

    kernel32 = _kernel32()
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL,
                                     wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [
        ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        times = [wintypes.FILETIME() for _ in range(4)]
        if not kernel32.GetProcessTimes(handle,
                                        *(ctypes.byref(t) for t in times)):
            return None
        return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
    finally:
        kernel32.CloseHandle(handle)


def end_descendants() -> None:
    """End every live descendant of this process at once, on any platform.

    For a process about to leave through `os._exit`, after `end_owned_groups`.
    A child started through plain `subprocess` is in no job and no owned
    group, and it holds the stdout and stderr it inherited: whoever reads this
    process through a pipe gets no end of file while such a child lives. A
    descendant whose parent already exited is not found.
    """
    # Windows has no SIGKILL; there `os.kill` ends the process for any signal.
    sig = getattr(signal, "SIGKILL", signal.SIGTERM)
    for pid in _descendants(os.getpid()):
        try:
            os.kill(pid, sig)
        except OSError:
            pass


def _job_for(process: subprocess.Popen) -> Any:
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    kernel32 = _kernel32()
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError()

    class BASIC_LIMIT(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                    ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class EXTENDED_LIMIT(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", BASIC_LIMIT),
                    ("IoInfo", IO_COUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    info = EXTENDED_LIMIT()
    info.BasicLimitInformation.LimitFlags = 0x00002000  # KILL_ON_JOB_CLOSE
    if not kernel32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
        kernel32.CloseHandle(job)
        raise ctypes.WinError()
    if not kernel32.AssignProcessToJobObject(job, wintypes.HANDLE(process._handle)):
        kernel32.CloseHandle(job)
        raise ctypes.WinError()
    return job


def _nt_resume_process(process: subprocess.Popen) -> bool:
    """Resume a CREATE_SUSPENDED child from its handle. False when the call fails."""
    import ctypes
    from ctypes import wintypes
    try:
        resume = ctypes.WinDLL("ntdll").NtResumeProcess
        resume.argtypes = [wintypes.HANDLE]
        resume.restype = ctypes.c_long
        return resume(wintypes.HANDLE(process._handle)) == 0
    except (OSError, AttributeError):
        return False


def _resume_process(process: subprocess.Popen) -> None:
    """Resume every thread in a process created with CREATE_SUSPENDED.

    A thread snapshot lists every thread on the machine and costs about 0.36 s
    here, so it is the fallback.
    """
    if not _nt_resume_process(process):
        _resume_threads_by_snapshot(process)


def _resume_threads_by_snapshot(process: subprocess.Popen) -> None:
    import ctypes
    from ctypes import wintypes

    class THREADENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ThreadID", wintypes.DWORD),
            ("th32OwnerProcessID", wintypes.DWORD),
            ("tpBasePri", wintypes.LONG),
            ("tpDeltaPri", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
        ]

    kernel32 = _kernel32()
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Thread32First.argtypes = [wintypes.HANDLE,
                                       ctypes.POINTER(THREADENTRY32)]
    kernel32.Thread32First.restype = wintypes.BOOL
    kernel32.Thread32Next.argtypes = [wintypes.HANDLE,
                                      ctypes.POINTER(THREADENTRY32)]
    kernel32.Thread32Next.restype = wintypes.BOOL
    kernel32.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenThread.restype = wintypes.HANDLE

    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000004, 0)  # SNAPTHREAD
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    resumed = 0
    try:
        entry = THREADENTRY32()
        entry.dwSize = ctypes.sizeof(entry)
        more = kernel32.Thread32First(snapshot, ctypes.byref(entry))
        while more:
            if entry.th32OwnerProcessID == process.pid:
                thread = kernel32.OpenThread(0x0002, False, entry.th32ThreadID)
                if thread:
                    try:
                        if kernel32.ResumeThread(thread) != 0xFFFFFFFF:
                            resumed += 1
                    finally:
                        kernel32.CloseHandle(thread)
            more = kernel32.Thread32Next(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    if not resumed:
        raise ctypes.WinError(ctypes.get_last_error())


def guard_current_process_tree() -> Any:
    """Put the runner in a kill-on-close job before it may spawn descendants.

    Children inherit job membership, which closes the Popen/Assign race: an
    immediate child cannot escape between process creation and assignment.
    """
    global _CURRENT_JOB
    if _CURRENT_JOB:
        return _CURRENT_JOB
    if sys.platform != "win32":
        # A runner that `spawn_managed` started leads its own process group.
        # Its children stay in that group, so ending the runner's group ends
        # them with it, as job membership does on Windows.
        if os.getpgrp() == os.getpid():
            _CURRENT_JOB = "process-group"
        return _CURRENT_JOB
    job = _job_for_current_process()
    _CURRENT_JOB = job
    return job


def _job_for_current_process() -> Any:
    import ctypes
    from ctypes import wintypes
    kernel32 = _kernel32()
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())

    class BASIC_LIMIT(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                    ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class EXTENDED_LIMIT(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", BASIC_LIMIT), ("IoInfo", IO_COUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    info = EXTENDED_LIMIT()
    info.BasicLimitInformation.LimitFlags = 0x00002000
    if not kernel32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
        kernel32.CloseHandle(job)
        raise ctypes.WinError(ctypes.get_last_error())
    if not kernel32.AssignProcessToJobObject(job, kernel32.GetCurrentProcess()):
        kernel32.CloseHandle(job)
        raise ctypes.WinError(ctypes.get_last_error())
    return job


#: Seconds between 1601-01-01 (FILETIME's epoch) and 1970-01-01.
_FILETIME_EPOCH_OFFSET_S = 11644473600


PID_FILE_SLACK_S = 2.0


def pid_alive(pid: int, started_before: float | None = None) -> bool:
    """Whether `pid` is a live process that could be the recorded supervisor.

    Windows reuses PIDs. A supervisor exists before it writes its PID file, so
    with `started_before` set to that file's mtime, a live process created
    after it is a stranger that inherited the number, and counts as dead. On
    2026-09-28 a `cmd` started that morning held the PID of a supervisor that
    died on 2026-09-16, and `status` called that run live.

    A file's mtime ticks coarser than a process's creation time, so a
    supervisor that writes its file within a few milliseconds of its start
    can show a creation time just after the mtime. `PID_FILE_SLACK_S` is that
    allowance; a stranger that inherited the number starts minutes or days
    later.
    """
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL,
                                         wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE,
                                                ctypes.POINTER(wintypes.DWORD))
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (
            ctypes.POINTER(wintypes.FILETIME),) * 4
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(process_query_limited_information,
                                      False, pid)
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            if code.value != still_active:
                return False
            if started_before is None:
                return True
            times = [wintypes.FILETIME() for _ in range(4)]
            if not kernel32.GetProcessTimes(handle,
                                            *(ctypes.byref(t) for t in times)):
                return True
            ticks = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
            created = ticks / 1e7 - _FILETIME_EPOCH_OFFSET_S
            return created <= started_before + PID_FILE_SLACK_S
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError, ValueError):
        return False
    return True


def _own_stdin(kwargs: dict[str, Any]) -> dict[str, Any]:
    """A child that is fed no input gets the null device for stdin.

    A process started without a console (`run-hidden.vbs`, a scheduled task)
    has no stdin handle, and `subprocess` fails on it with `WinError 6` when
    the child inherits stdin. A caller that feeds input, or names a stdin,
    keeps its choice.
    """
    if "input" not in kwargs and kwargs.get("stdin") is None:
        kwargs["stdin"] = subprocess.DEVNULL
    return kwargs


def run_managed(argv: Sequence[str], *, env: Mapping[str, str],
                timeout: float, cwd: Path | None = None,
                input_bytes: bytes | None = None
                ) -> subprocess.CompletedProcess:
    """`subprocess.run` for a child whose whole tree ends at the timeout.

    Output goes to temp files, so a grandchild cannot hold a pipe open. A
    timeout kills the tree and raises `subprocess.TimeoutExpired`. The child
    reads `input_bytes` on stdin, from a temp file, else nothing.
    """
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err, \
            tempfile.TemporaryFile() as feed:
        if input_bytes is not None:
            feed.write(input_bytes)
            feed.seek(0)
        managed = spawn_managed(argv, cwd=cwd or Path.cwd(), env=env,
                                stdin=feed if input_bytes is not None else subprocess.DEVNULL,
                                stdout=out, stderr=err)
        try:
            returncode = managed.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            managed.kill_tree()
            raise
        finally:
            managed.close()
        out.seek(0)
        err.seek(0)
        return subprocess.CompletedProcess(
            list(argv), returncode, out.read().decode("utf-8", "replace"),
            err.read().decode("utf-8", "replace"))


def run(argv: Any, **kwargs: Any) -> subprocess.CompletedProcess:
    """`subprocess.run` for a child that is fed no input."""
    return subprocess.run(argv, **_own_stdin(kwargs))


def popen(argv: Any, **kwargs: Any) -> subprocess.Popen:
    """`subprocess.Popen` for a child that is fed no input."""
    return subprocess.Popen(argv, **_own_stdin(kwargs))


def ensure_stdin() -> None:
    """Give this process a stdin handle when it has none.

    For a process whose code starts children through plain `subprocess`, as
    the test suite does. Product code uses `run` and `popen` instead.
    """
    if os.name != "nt":
        return
    import ctypes
    import msvcrt
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetStdHandle.argtypes = [wintypes.DWORD]
    kernel32.GetStdHandle.restype = wintypes.HANDLE
    kernel32.GetFileType.argtypes = [wintypes.HANDLE]
    kernel32.GetFileType.restype = wintypes.DWORD
    kernel32.SetStdHandle.argtypes = [wintypes.DWORD, wintypes.HANDLE]
    kernel32.SetStdHandle.restype = wintypes.BOOL
    std_input = wintypes.DWORD(-10 & 0xFFFFFFFF)
    handle = kernel32.GetStdHandle(std_input)
    if handle and kernel32.GetFileType(handle):
        return
    fd = os.open(os.devnull, os.O_RDONLY)
    kernel32.SetStdHandle(std_input, msvcrt.get_osfhandle(fd))


def spawn_managed(argv: Sequence[str] | str, *, cwd: Path, env: Mapping[str, str],
                  stdin: Any, stdout: Any, stderr: Any) -> ManagedProcess:
    """Start a child whose tree ends with it: inside a kill-on-close job on
    Windows, at the head of its own process group elsewhere. A string `argv`
    is the raw Windows command line, for `cmd /c` text that must not be
    re-quoted."""
    kwargs: dict[str, Any] = {}
    suspended = False
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        if not _CURRENT_JOB:
            # Assignment after an ordinary Popen races the new process: it can
            # spawn and exit before the parent puts it in the job. Start it
            # suspended, assign first, and only then allow user code to run.
            kwargs["creationflags"] |= _CREATE_SUSPENDED
            suspended = True
    elif not _CURRENT_JOB:
        # The child leads a new session and process group, so the group is
        # its tree. A terminal interrupt therefore reaches the supervisor
        # only, as it does on Windows.
        kwargs["start_new_session"] = True
    process = popen(argv if isinstance(argv, str) else list(argv), cwd=str(cwd), env=dict(env), stdin=stdin,
                    stdout=stdout, stderr=stderr, text=True,
                    encoding="utf-8", errors="replace", **kwargs)
    try:
        job = None if _CURRENT_JOB else _job_for(process)
        if suspended:
            _resume_process(process)
    except Exception:
        process.kill()
        process.wait(timeout=10)
        if "job" in locals() and job:
            _kernel32().CloseHandle(job)
        raise
    pgid = process.pid if kwargs.get("start_new_session") else None
    if pgid is not None:
        _own_group(pgid)
    return ManagedProcess(process=process, job_handle=job, pgid=pgid)

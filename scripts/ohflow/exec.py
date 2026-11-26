"""Command execution. The shell is always named, never inferred.

stdout and stderr go to files under the step directory. The return value
carries the exit code, the byte counts, the log paths and a tail of at most 4 KB.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal, Mapping

from . import proc
from .paths import bash_exe, posix, win

__all__ = ["Completed", "run", "git", "TAIL_BYTES"]

TAIL_BYTES = 4096
STOP_POLL_S = 1.0
STOPPED_EXIT = 137
Shell = Literal["sh", "cmd"]

_SAFE = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."


def _slugify(name: str) -> str:
    return "".join(ch if ch in _SAFE else "-" for ch in name)[:80] or "cmd"


def _read(path: Path) -> str:
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


@dataclass
class Completed:
    cmd: str
    shell: str
    cwd: str
    returncode: int
    duration_s: float
    stdout_path: str | None = None
    stderr_path: str | None = None
    stdout_bytes: int = 0
    stderr_bytes: int = 0
    tail: str = ""
    timed_out: bool = False
    stdout: str = field(default="", repr=False)
    stderr: str = field(default="", repr=False)
    stopped: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


def _wait(managed, timeout: float,
          stop: Callable[[], bool] | None) -> tuple[int, bool, bool]:
    deadline = time.monotonic() + timeout
    while True:
        left = deadline - time.monotonic()
        try:
            return (managed.wait(timeout=max(0.0, left if stop is None
                                             else min(left, STOP_POLL_S))),
                    False, False)
        except subprocess.TimeoutExpired:
            if time.monotonic() >= deadline:
                managed.kill_tree()
                return 124, True, False
            if stop is not None and stop():
                managed.kill_tree()
                return STOPPED_EXIT, False, True


def run(cmd: str, cwd: Path, shell: Shell = "sh", timeout: int = 900,
        log_dir: Path | None = None, name: str | None = None,
        env: Mapping[str, str] | None = None,
        stop: Callable[[], bool] | None = None) -> Completed:
    """Run one command string in a named shell.

    `sh` is Git Bash and receives a POSIX-rendered working directory.
    `cmd` is cmd.exe and receives a backslash-rendered one.
    """
    cwd = Path(cwd)
    t0 = time.time()
    if shell == "sh":
        argv = [bash_exe(), "-lc", cmd]
    elif shell == "cmd":
        argv = ["cmd", "/c", cmd]
    else:
        raise ValueError(f"unknown shell {shell!r}; use 'sh' or 'cmd'")

    # cmd.exe gets the raw string, wrapped the way `shell=True` wraps it.
    # Passing the same string as one argv element makes Python quote it, and
    # cmd.exe then sees escaped quotes it cannot parse -- that is what broke
    # `mklink /J "a" "b"`.
    target = (f'{os.environ.get("COMSPEC", "cmd.exe")} /c "{cmd}"'
              if shell == "cmd" else argv)
    child_env = dict(os.environ)
    if env:
        child_env.update({str(k): str(v) for k, v in env.items()})

    # The child writes straight to its log files, so no pipe stays open for a
    # grandchild to hold, and a timeout can end the whole job.
    scratch = None
    if log_dir is None:
        scratch = tempfile.TemporaryDirectory(prefix="ohflow-exec-")
        files_dir = Path(scratch.name)
    else:
        files_dir = Path(log_dir)
        files_dir.mkdir(parents=True, exist_ok=True)
    stem = _slugify(name or cmd)
    op = files_dir / f"{stem}.out.log"
    ep = files_dir / f"{stem}.err.log"
    timed_out = stopped = False
    try:
        with op.open("wb") as out_file, ep.open("wb") as err_file:
            managed = proc.spawn_managed(target, cwd=cwd, env=child_env,
                                         stdin=subprocess.DEVNULL,
                                         stdout=out_file, stderr=err_file)
            try:
                rc, timed_out, stopped = _wait(managed, timeout, stop)
            finally:
                managed.close()
        out = _read(op)
        err = _read(ep)
    finally:
        if scratch is not None:
            scratch.cleanup()
    said = (f"\n[ohflow] timed out after {timeout}s\n" if timed_out
            else "\n[ohflow] stopped on request\n" if stopped else "")
    if said:
        err += said
        if log_dir is not None:
            with ep.open("a", encoding="utf-8") as err_file:
                err_file.write(said)
    if log_dir is None:
        op = ep = None

    dur = round(time.time() - t0, 2)
    combined = (out + err)
    return Completed(
        cmd=cmd,
        shell=shell,
        cwd=win(cwd),
        returncode=rc,
        duration_s=dur,
        stdout_path=str(op) if op else None,
        stderr_path=str(ep) if ep else None,
        stdout_bytes=len(out.encode("utf-8", "replace")),
        stderr_bytes=len(err.encode("utf-8", "replace")),
        tail=combined[-TAIL_BYTES:],
        timed_out=timed_out,
        stdout=out,
        stderr=err,
        stopped=stopped,
    )


def git(args: str, cwd: Path, timeout: int = 300,
        log_dir: Path | None = None, name: str | None = None) -> Completed:
    """git always goes through the POSIX renderer, per the path rule."""
    return run(f"git {args}", cwd=Path(cwd), shell="sh", timeout=timeout,
               log_dir=log_dir, name=name or f"git-{args.split()[0]}")


def git_out(args: str, cwd: Path) -> str:
    c = git(args, cwd)
    if c.returncode != 0:
        raise RuntimeError(f"git {args} in {posix(cwd)} exited {c.returncode}\n{c.tail}")
    return c.stdout.strip()

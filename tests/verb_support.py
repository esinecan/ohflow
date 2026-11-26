"""Shared helpers for the `test_verb_*` files: run a verb through `cli.main`."""

from __future__ import annotations

import subprocess
import sys

from ohflow import cli
from support import quiet

__all__ = ["call", "live_child", "NO_ANSI"]

NO_ANSI = "\x1b"


def live_child(case) -> subprocess.Popen:
    """A live process that is not the test process; `case` kills it on cleanup."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, creationflags=flags)

    def stop() -> None:
        child.kill()
        child.wait()

    case.addCleanup(stop)
    return child


def call(*argv, harness_executors=None) -> tuple[int, list[str]]:
    """Run `ohflow <argv>` through `cli.main`; return the exit code and the
    output lines (stdout and stderr together)."""
    with quiet() as output:
        code = cli.main([str(a) for a in argv], harness_executors=harness_executors)
    return code, output.out.splitlines()

"""Shared bits of the fake signed-in harness executables. Stdlib only; runs as a real process."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SCENARIO = os.environ.get("OHFLOW_FAKE_SIGNED_IN_SCENARIO", "success")


def emit(event) -> None:
    sys.stdout.write(json.dumps(event, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def replay(path: Path) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            sys.stdout.write(line + "\n")
            sys.stdout.flush()


def arg(args, flag, default=None):
    return args[args.index(flag) + 1] if flag in args else default


def spawn_grandchild() -> None:
    """A descendant process: the harness executor must kill the whole tree."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, creationflags=flags)
    state = Path(os.environ["OHFLOW_FAKE_SIGNED_IN_STATE"])
    state.mkdir(parents=True, exist_ok=True)
    (state / "grandchild.pid").write_text(str(child.pid), encoding="ascii")
    time.sleep(60)

"""The durable host that ships inside ohflow, and its install on a machine.

`ohflow/host/` is a Node package: `ohflow-step.mjs` opens a pi-durable
`Harness` over the step's `session.sqlite`. ohflow installs it on each machine
that runs a durable step, this one for box `local` and a box over ssh for the
others, so no machine needs a clone of anything but Node 22.19 or newer.

The install is one `node` process fed a program on stdin: `install.cjs` with
the host's files embedded. It writes them to
`~/.pi-durable/ohflow-host/<version>/`, runs `npm ci` there and prints one
`durable_host` line naming the folder. The version is a hash of the files, so
a changed host installs beside the old one and a step that runs keeps its own.
A folder that already holds the version answers at once.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from . import proc

__all__ = ["HOST_DIR", "LOCAL_BOX", "host_files", "host_version",
           "installer_program", "node_argv", "install", "ensure_local"]

HOST_DIR = Path(__file__).resolve().parents[2] / "host"
LOCAL_BOX = "local"
INSTALL_TIMEOUT_S = 900
_SKIP_DIRS = {"node_modules", "bin"}


def host_files(root: Path = HOST_DIR) -> dict[str, bytes]:
    """The host's files by forward-slash path, line endings made LF."""
    files: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if not path.is_file() or rel.parts[0] in _SKIP_DIRS or rel.name.startswith("."):
            continue
        files[rel.as_posix()] = path.read_bytes().replace(b"\r\n", b"\n")
    if "ohflow-step.mjs" not in files or "package-lock.json" not in files:
        raise FileNotFoundError(f"{root} holds no durable host")
    return files


def host_version(files: dict[str, bytes] | None = None) -> str:
    files = host_files() if files is None else files
    digest = hashlib.sha256()
    for name in sorted(files):
        digest.update(name.encode("utf-8") + b"\0" + files[name] + b"\0")
    return digest.hexdigest()[:16]


def installer_program(files: dict[str, bytes] | None = None) -> bytes:
    """`install.cjs` with the host's files in a `BUNDLE` constant before it."""
    files = host_files() if files is None else files
    bundle = {"version": host_version(files),
              "files": {name: base64.b64encode(data).decode("ascii")
                        for name, data in files.items() if name != "install.cjs"}}
    return (f"const BUNDLE = {json.dumps(bundle)};\n".encode("utf-8")
            + files["install.cjs"])


def node_argv() -> list[str]:
    """The argv prefix of this machine's node; a `.py` override runs under
    this interpreter, which is how the test fakes run."""
    override = os.environ.get("OHFLOW_DURABLE_NODE")
    if override:
        return [sys.executable, override] if override.lower().endswith(".py") else [override]
    return ["node"]


def _host_line(done: subprocess.CompletedProcess, where: str) -> str:
    fault = None
    for line in (done.stdout or "").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        if record.get("type") == "durable_host" and record.get("dir"):
            return str(record["dir"])
        if record.get("type") == "durable_error":
            fault = record.get("message")
    detail = fault or ((done.stdout or "") + (done.stderr or ""))[-400:]
    raise RuntimeError(f"the durable host install on {where} exited "
                       f"{done.returncode}: {detail}")


def install(argv: Sequence[str], where: str) -> str:
    """Run the installer through `argv` (a node, maybe behind ssh) and return
    the folder the host sits in, in that machine's own spelling."""
    program = installer_program()
    try:
        done = proc.run_managed(list(argv), env=proc.agent_env(),
                                timeout=INSTALL_TIMEOUT_S, input_bytes=program)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"the durable host install on {where} timed out after "
                           f"{INSTALL_TIMEOUT_S} s") from error
    except OSError as error:
        raise RuntimeError(f"the durable host install on {where} could not start "
                           f"{argv[0]}: {error}") from error
    return _host_line(done, where)


def ensure_local() -> str:
    """The host's folder on this machine, installed on first use."""
    return install(node_argv(), LOCAL_BOX)

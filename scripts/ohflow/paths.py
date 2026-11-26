"""The Windows path rule: one renderer per destination.

The orchestrator holds every path as a `pathlib.Path`. Nothing interpolates a
path into a string without passing it through one of the three renderers below.
Git Bash tolerates backslashes inside double quotes, so a mistake here is
invisible until the day it is not.
"""

from __future__ import annotations

import ntpath
import os
import shutil
import sys
from pathlib import Path, PurePath

__all__ = ["win", "posix", "as_path", "bash_exe", "python_cmd"]


def as_path(p) -> Path:
    """Accept a str or a PurePath, return a resolved concrete Path."""
    if isinstance(p, Path):
        return p
    if isinstance(p, PurePath):
        return Path(str(p))
    return Path(str(p))


def win(p) -> str:
    """The path as this platform's shells and agents read it: backslashes on
    Windows, for cmd.exe, PowerShell and any text an agent reads. Off Windows
    a backslash is a file-name character, so the path stays as it is."""
    if os.name != "nt":
        return str(as_path(p))
    return str(as_path(p)).replace("/", "\\")


def python_cmd() -> str:
    """The interpreter name a printed command hint starts with: the file name
    of the running interpreter, so a Mac prints `python3` and a Windows install
    prints `python`."""
    name = ntpath.basename(sys.executable or "") or "python"
    if name.lower().endswith(".exe"):
        name = name[:-4]
    return name or "python"


def posix(p) -> str:
    """Forward slashes. For Git Bash and for git arguments."""
    return str(as_path(p)).replace("\\", "/")


def _is_wsl_launcher(path: str) -> bool:
    """True for a WSL launcher, in any letter case: a `bash.exe` under
    %SystemRoot%, or the app execution alias in a `WindowsApps` directory."""
    norm = ntpath.normcase(ntpath.normpath(path))
    if "windowsapps" in norm.split("\\")[:-1]:
        return True
    root = os.environ.get("SystemRoot") or os.environ.get("windir")
    return bool(root) and norm.startswith(
        ntpath.normcase(ntpath.normpath(root)) + "\\")


def bash_exe() -> str:
    """Locate Git Bash. OHFLOW_BASH overrides; otherwise PATH, then the usual
    install locations. Raising here is better than silently running cmd.exe."""
    override = os.environ.get("OHFLOW_BASH")
    if override and Path(override).exists():
        return override
    found = shutil.which("bash")
    if found and not _is_wsl_launcher(found):
        return found
    for candidate in (
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
    ):
        if Path(candidate).exists():
            return candidate
    if found:
        return found
    raise FileNotFoundError(
        "Git Bash not found. Set OHFLOW_BASH to the full path of bash.exe."
    )

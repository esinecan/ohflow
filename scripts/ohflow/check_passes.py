from __future__ import annotations

import json
import os
import time
from pathlib import Path

from . import exec as ohexec

FILE = "check-passes.jsonl"


def clean_tree(worktree: Path) -> str | None:
    status = ohexec.git("status --porcelain", Path(worktree), name="check-pass-status")
    if status.returncode != 0 or status.stdout.strip():
        return None
    tree = ohexec.git("rev-parse HEAD^{tree}", Path(worktree), name="check-pass-tree")
    if tree.returncode != 0:
        return None
    return tree.stdout.strip() or None


def _place(cwd: Path) -> str:
    return os.path.normcase(os.path.realpath(str(cwd)))


def _key(cmd: str, shell: str, cwd: Path, tree: str) -> dict:
    return {"cmd": cmd, "shell": shell, "cwd": _place(cwd), "tree": tree}


def find(run_dir: Path | None, cmd: str, shell: str, cwd: Path,
         tree: str | None) -> dict | None:
    if run_dir is None or tree is None:
        return None
    path = Path(run_dir) / FILE
    if not path.is_file():
        return None
    want = _key(cmd, shell, cwd, tree)
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if all(rec.get(k) == v for k, v in want.items()):
            return rec
    return None


def record(run_dir: Path | None, cmd: str, shell: str, cwd: Path, tree: str | None,
           *, by: str, log: str | None) -> None:
    if run_dir is None or tree is None:
        return
    rec = {**_key(cmd, shell, cwd, tree), "by": by, "log": log,
           "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    Path(run_dir).mkdir(parents=True, exist_ok=True)
    with open(Path(run_dir) / FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def reused_note(rec: dict) -> str:
    return (f"reused the pass of {rec.get('by')} on tree {str(rec.get('tree'))[:12]}"
            f" (log: {rec.get('log')})")

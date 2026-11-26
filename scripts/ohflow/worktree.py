"""Worktree lifecycle, and the four hazards that come with it.

1. Concurrent `git worktree add` calls race on `.git/worktrees`. `create` takes a
   process-wide lock, so worktree creation is serial even inside a parallel phase.
2. On Windows the shared `node_modules` is a junction, made with
   `cmd /c mklink /J`, which needs no administrator right. Off Windows it is a
   symbolic link.
3. `revert` removes the link FIRST: `rmdir "<wt>\\node_modules"` on Windows,
   which removes the junction only, and an unlink off Windows. This package
   never deletes a worktree path recursively itself, because a recursive delete
   can follow a junction into the real `node_modules`.
4. `revert` ends by checking that a sentinel path under the source
   `node_modules` still exists. That turns a silent catastrophe into a loud one.

The teardown is one code path on every platform: the engine writes
`revert.json`, and `ohflow revert --run <dir>` reads it and calls `revert`.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, asdict
from pathlib import Path

from . import exec as ohexec, proc
from .paths import posix, win
from .workflow import Workspace, WorktreeSpec

__all__ = ["WorktreeHandle", "create", "link_node_modules", "REVERT_PLAN",
           "write_revert_plan", "read_revert_plan", "revert",
           "is_git", "ensure_workspace", "workspace_faults"]

#: The file in a run directory that lists what `ohflow revert` removes.
REVERT_PLAN = "revert.json"

_CREATE_LOCK = threading.Lock()


@dataclass
class WorktreeHandle:
    name: str
    path: str
    branch: str
    base: str
    base_sha: str
    node_modules_mode: str
    node_modules_source: str | None
    sentinel: str
    created_by: str
    existed: bool = False
    workspace: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def is_git(path: Path) -> bool:
    return (Path(path) / ".git").exists()


def workspace_faults(space: Workspace) -> list[str]:
    """Why `space` is no repository a run can start in. An owned workspace
    whose folder is absent or empty has no fault: the run creates it."""
    path = Path(space.path)
    if is_git(path):
        return []
    if not space.owned:
        return [f"not a git repository: {win(path)}"]
    if path.exists() and not path.is_dir():
        return [f"workspace {space.name!r}: {win(path)} is a file; ohflow "
                f"creates an owned workspace in a folder"]
    if path.is_dir() and any(path.iterdir()):
        return [f"workspace {space.name!r}: {win(path)} holds files and no "
                f"git repository; ohflow creates an owned workspace only in "
                f"an empty folder"]
    return []


def ensure_workspace(space: Workspace) -> str | None:
    """Create the repository of an owned workspace that has none yet: `git
    init`, the base branch, and one empty root commit for the worktrees to
    start from. Returns what was done, or None when nothing was."""
    if not space.owned:
        return None
    path = Path(space.path)
    faults = workspace_faults(space)
    if faults:
        raise RuntimeError(faults[0])
    repo = str(path)
    said = None
    if not is_git(path):
        path.mkdir(parents=True, exist_ok=True)
        for args in (("init",),
                     ("symbolic-ref", "HEAD", f"refs/heads/{space.base_branch}")):
            code, out = _git(repo, *args)
            if code != 0:
                raise RuntimeError(f"workspace {space.name!r}: git "
                                   f"{' '.join(args)} exited {code}\n{out}")
        for key, value in (("user.name", "ohflow"),
                           ("user.email", "ohflow@localhost")):
            if _git(repo, "config", key)[0] != 0:
                _git(repo, "config", key, value)
        code, out = _git(repo, "commit", "--allow-empty", "-m",
                         f"Start workspace {space.name}")
        if code != 0:
            raise RuntimeError(f"workspace {space.name!r}: the root commit "
                               f"exited {code}\n{out}")
        said = f"created {win(path)} on {space.base_branch}"
    if space.remote and _git(repo, "remote", "get-url", "origin")[0] != 0:
        code, out = _git(repo, "remote", "add", "origin", space.remote)
        if code != 0:
            raise RuntimeError(f"workspace {space.name!r}: git remote add "
                               f"origin exited {code}\n{out}")
        said = f"{said}, origin set" if said else "origin set"
    return said


def source_dir(repo: Path, spec: WorktreeSpec) -> Path:
    return Path(spec.node_modules_source) if spec.node_modules_source else Path(repo) / "node_modules"


def create(repo: Path, spec: WorktreeSpec, *, created_by: str,
           log_dir: Path | None = None,
           workspace: str | None = None) -> WorktreeHandle:
    """Serial by design. `git worktree add` writes shared state under .git."""
    repo = Path(repo)
    path = Path(spec.path)
    with _CREATE_LOCK:
        existed = path.exists()
        if existed and not spec.reuse_existing:
            raise RuntimeError(
                f"worktree path already exists and reuse_existing is False: {win(path)}"
            )
        if not existed:
            path.parent.mkdir(parents=True, exist_ok=True)
            branch_exists = ohexec.git(
                f"rev-parse --verify --quiet refs/heads/{spec.branch}", repo
            ).returncode == 0
            if branch_exists:
                args = f'worktree add "{posix(path)}" {spec.branch}'
            else:
                args = f'worktree add -b {spec.branch} "{posix(path)}" {spec.base}'
            c = ohexec.git(args, repo, log_dir=log_dir, name=f"worktree-add-{spec.name}")
            if c.returncode != 0:
                raise RuntimeError(f"git {args} exited {c.returncode}\n{c.tail}")
        if existed and spec.base_sha_mode == "merge_base":
            # The commit the work in this worktree started from. `rev-parse
            # HEAD` would name the tip of that work instead, so a gate asking
            # "how many commits past the base" would read zero and a diff
            # against the base would come back empty.
            base_sha = ohexec.git_out(f"merge-base {spec.base} HEAD", path)
        else:
            base_sha = ohexec.git_out("rev-parse HEAD", path)

    link_node_modules(repo, spec, log_dir=log_dir)

    return WorktreeHandle(
        name=spec.name,
        path=str(path),
        branch=spec.branch,
        base=spec.base,
        base_sha=base_sha,
        node_modules_mode=spec.node_modules_mode,
        node_modules_source=str(source_dir(repo, spec)),
        sentinel=spec.node_modules_sentinel,
        created_by=created_by,
        existed=existed,
        workspace=workspace or spec.workspace or "",
    )


def link_node_modules(repo: Path, spec: WorktreeSpec,
                      log_dir: Path | None = None) -> None:
    """mode: 'junction' (stage 0 default), 'install', or 'none'."""
    path = Path(spec.path)
    target = path / "node_modules"
    mode = spec.node_modules_mode
    if mode == "none":
        return
    if target.exists():
        return
    if mode == "junction":
        src = source_dir(repo, spec)
        if not src.exists():
            raise RuntimeError(f"node_modules source missing: {win(src)}")
        if os.name != "nt":
            try:
                os.symlink(src, target, target_is_directory=True)
            except OSError as e:
                raise RuntimeError(f"symlink failed for {win(target)}: {e}")
            return
        c = ohexec.run(f'mklink /J "{win(target)}" "{win(src)}"', cwd=path,
                       shell="cmd", timeout=120, log_dir=log_dir,
                       name=f"mklink-{spec.name}")
        if c.returncode != 0:
            raise RuntimeError(f"mklink /J failed for {win(target)}\n{c.tail}")
    elif mode == "install":
        c = ohexec.run(spec.install_cmd or "npm ci --no-audit --no-fund",
                       cwd=path, shell="sh", timeout=3600, log_dir=log_dir,
                       name=f"install-{spec.name}")
        if c.returncode != 0:
            raise RuntimeError(f"install failed in {win(path)}\n{c.tail}")
    else:
        raise ValueError(f"unknown node_modules_mode {mode!r}")


def write_revert_plan(run_dir: Path, repo: Path, specs: list[WorktreeSpec],
                      workspaces: list[Workspace] | None = None) -> Path:
    """Write `revert.json`: every workspace and every worktree the workflow
    declares, with what `revert` needs to take each worktree out. `repo` is
    the default workspace's repository, where a worktree that names no
    workspace sits."""
    spaces = {w.name: w for w in (workspaces or [])}

    def home(s: WorktreeSpec) -> Path:
        space = spaces.get(s.workspace or "")
        return Path(space.path) if space else Path(repo)

    plan = {"repo": str(repo),
            "workspaces": [{"name": w.name, "path": str(w.path),
                            "owned": w.owned} for w in spaces.values()],
            "worktrees": [{
                "name": s.name, "path": str(s.path), "branch": s.branch,
                "workspace": s.workspace, "repo": str(home(s)),
                "node_modules_mode": s.node_modules_mode,
                "sentinel": (str(source_dir(home(s), s).parent
                                 / Path(s.node_modules_sentinel))
                             if s.node_modules_mode == "junction" else None),
            } for s in specs]}
    path = Path(run_dir) / REVERT_PLAN
    path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    return path


def read_revert_plan(run_dir: Path) -> dict | None:
    try:
        plan = json.loads((Path(run_dir) / REVERT_PLAN).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return plan if isinstance(plan, dict) else None


def _git(repo: str, *args: str) -> tuple[int, str]:
    p = proc.run(["git", "-C", repo, *args], capture_output=True, text=True)
    return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()


def _remove_link(link: Path) -> str | None:
    """Take out the shared `node_modules` link and never its target. Returns
    what was done, or None when there is no link."""
    if link.is_symlink():
        link.unlink()
        return f"unlinked {win(link)}"
    if os.name == "nt" and link.exists():
        # `rmdir` on a junction removes the link only. On a real directory with
        # content it fails, which is the safe outcome.
        p = proc.run(["cmd", "/c", "rmdir", str(link)], capture_output=True,
                     text=True)
        if p.returncode != 0:
            return f"rmdir failed for {win(link)}: {(p.stderr or '').strip()}"
        return f"removed junction {win(link)}"
    return None


def revert(plan: dict) -> tuple[bool, list[str]]:
    """Remove every worktree and branch of `plan`, through git. Links come out
    before anything else. Returns whether the teardown is clean, and the lines
    that say what happened. A worktree or a branch that is already gone is no
    failure; a worktree that stays, or a missing sentinel, is."""
    default = str(plan.get("repo") or "")
    entries = [e for e in (plan.get("worktrees") or []) if isinstance(e, dict)]
    several = len({str(e.get("repo") or default) for e in entries}) > 1
    lines: list[str] = []
    ok = True

    def repo_of(e: dict) -> str:
        return str(e.get("repo") or default)

    def place(e: dict) -> str:
        return (f" in workspace {e['workspace']}"
                if several and e.get("workspace") else "")
    for e in entries:
        if e.get("node_modules_mode") == "junction":
            said = _remove_link(Path(e["path"]) / "node_modules")
            if said:
                lines.append(said)
    for e in entries:
        path = Path(e["path"])
        if not path.exists():
            lines.append(f"worktree {e.get('name')}{place(e)}: not there, "
                         f"{win(path)}")
            continue
        code, out = _git(repo_of(e), "worktree", "remove", "--force", str(path))
        if code == 0 and not path.exists():
            lines.append(f"worktree {e.get('name')}{place(e)}: removed "
                         f"{win(path)}")
        else:
            ok = False
            lines.append(f"worktree {e.get('name')}{place(e)}: NOT removed "
                         f"{win(path)}: {out}")
    for repo in dict.fromkeys([repo_of(e) for e in entries] or [default]):
        _git(repo, "worktree", "prune")
    for e in entries:
        branch = e.get("branch")
        if not branch:
            continue
        repo = repo_of(e)
        if _git(repo, "rev-parse", "--verify", "--quiet",
                f"refs/heads/{branch}")[0] != 0:
            continue
        code, out = _git(repo, "branch", "-D", branch)
        if code == 0:
            lines.append(f"branch {branch}{place(e)}: deleted")
        else:
            ok = False
            lines.append(f"branch {branch}{place(e)}: NOT deleted: {out}")
    for e in entries:
        sentinel = e.get("sentinel")
        if not sentinel:
            continue
        if Path(sentinel).exists():
            lines.append(f"sentinel present: {win(sentinel)}")
        else:
            ok = False
            lines.append(f"SENTINEL MISSING: {win(sentinel)} -- node_modules "
                         f"may be damaged")
    return ok, lines

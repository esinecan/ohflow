"""Preflight: what must be true before a run starts, as data.

A `Check` names a need, how to observe it, and what to do when it fails. The
checks are a list, so a new need is one more entry. `run_checks` runs them
and `render` prints the verdict first: `PREFLIGHT PASS: N checks` or
`PREFLIGHT FAIL: F of N checks`, then one `FAIL <need>: <observed>; <fix>`
line for each failed check.

`Engine.preflight` asks `workflow_problems` at the start of every fresh run, so
the engine and the verb stop on the same facts and say the same words.

This module holds the check framework, the Git Bash check and the workflow checks.
`harness_executor_checks` asks each harness executor's `HarnessExecutor.preflight()`,
which is its runner module's `preflight()`. `HARNESS_EXECUTOR_FIX` holds the fix hint for each harness executor, so it
names every harness executor too.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import exec as ohexec
from . import worktree as ohwt
from .paths import bash_exe, win
from .workflow import WorktreeSpec, carried_by_git

__all__ = ["Check", "Result", "run_checks", "render", "bash_check",
           "workflow_load_check", "harness_executor_checks", "workflow_checks",
           "workflow_problems"]

WINDOWS_PATH_LIMIT = 260

#: What to do when a harness executor's own preflight finds a fault.
HARNESS_EXECUTOR_FIX = {
    "pi": "install pi, or set OHFLOW_PI_EXE",
    "claude": "run `claude auth login`, or set OHFLOW_CLAUDE_EXE",
    "codex": "run `codex login`, or set OHFLOW_CODEX_EXE",
    "durable": "set durable.box in ohflow.settings.local.json to local or "
               "a box's ssh host alias, and check that node 22.19 or newer "
               "runs there (`ssh <box> node --version` for a box)",
    "pi-cloud": "set PI_CLOUD_TOKEN to the Worker's bearer token, and "
                "pi_cloud.url in ohflow.settings.local.json to the Worker",
    "claude-cloud": "set PI_CLOUD_TOKEN and pi_cloud.url as for pi-cloud; the "
                    "Worker needs the secret CLAUDE_CODE_OAUTH_TOKEN",
    "codex-cloud": "set PI_CLOUD_TOKEN and pi_cloud.url as for pi-cloud, and run "
                   "`node worker/scripts/codex-login.mjs` in the ohflow skill folder",
}


@dataclass(frozen=True)
class Check:
    """`observe` returns the faults it finds, an empty list when the need
    holds."""
    need: str
    observe: Callable[[], list[str]]
    fix: str


@dataclass(frozen=True)
class Result:
    need: str
    status: str            # PASS or FAIL
    observed: str = ""
    fix: str = ""


def run_checks(checks: list[Check]) -> list[Result]:
    out = []
    for check in checks:
        try:
            faults = check.observe()
        except Exception as e:  # noqa: BLE001 - a broken check is a finding
            faults = [f"{type(e).__name__}: {e}"]
        if faults:
            observed = " | ".join(" ".join(str(f).split()) for f in faults)
            out.append(Result(check.need, "FAIL", observed[:300], check.fix))
        else:
            out.append(Result(check.need, "PASS"))
    return out


def render(results: list[Result], verbose: bool = False) -> list[str]:
    """The verdict line first, then the failures; `verbose` adds the rest."""
    failed = [r for r in results if r.status == "FAIL"]
    head = (f"PREFLIGHT FAIL: {len(failed)} of {len(results)} checks"
            if failed else f"PREFLIGHT PASS: {len(results)} checks")
    lines = [head]
    for r in results:
        if r.status == "FAIL":
            lines.append(f"FAIL {r.need}: {r.observed}; {r.fix}")
        elif verbose:
            lines.append(f"PASS {r.need}")
    return lines


# ------------------------------------------------------------------ the checks


def bash_check() -> Check:
    def observe() -> list[str]:
        try:
            bash_exe()
        except FileNotFoundError as e:
            return [str(e)]
        return []
    if os.name == "nt":
        fix = ("install Git for Windows; OHFLOW_BASH is optional and names "
               "bash.exe when it is not on PATH")
    else:
        fix = ("install bash; OHFLOW_BASH is optional and names bash when "
               "it is not on PATH")
    return Check("Git Bash", observe, fix)


def workflow_load_check(fault: str) -> Check:
    """The `preflight` verb's check for a workflow module that did not load
    with its `--args`."""
    return Check("workflow", lambda: [fault],
                 "fix the workflow module or its --args")


def harness_executor_checks(names: list[str], resolver: Callable) -> list[Check]:
    """One check per harness executor, from the harness executor's own `preflight`."""
    def make(name: str) -> Check:
        def observe() -> list[str]:
            harness_executor = resolver(name)
            ask = getattr(harness_executor, "preflight", None)
            return list(ask()) if ask is not None else []
        return Check(f"{name} harness executor", observe,
                     HARNESS_EXECUTOR_FIX.get(name, "fix the harness executor as the fault says"))
    return [make(n) for n in names]


def _workflow_harness_executors(workflow) -> list[str]:
    return sorted({s.agent.harness_executor for _, _, _, s in workflow.steps()
                   if s.agent is not None})


def _tracked_at_base(repo: Path, base: str) -> list[str] | None:
    """The tracked paths `git worktree add` checks out at `base`, or None
    when `base` does not resolve in `repo`."""
    found = ohexec.git(f"-c core.quotepath=off ls-tree -r --name-only {base}",
                       repo)
    if found.returncode != 0:
        return None
    return found.stdout.splitlines()


def _tracked_in_index(repo: Path) -> list[str]:
    """The tracked paths of the branch `repo` has checked out."""
    return ohexec.git("-c core.quotepath=off ls-files", repo).stdout.splitlines()


def workflow_checks(workflow, resolver: Callable) -> list[Check]:
    """The workspaces, the key variables, the harness executors and the worktrees a workflow
    needs. Every workspace is checked. The checks that read a repository hold
    their tongue for a workspace that is not one, because the first check has
    already said so, and for an owned workspace the run has yet to create."""
    spaces = list(workflow.all_workspaces())
    several = len(spaces) > 1

    def subject(space) -> str:
        return f"workspace {space.name!r}" if several else "repo"

    def is_repo() -> list[str]:
        if not spaces:
            return ["the workflow names no workspace"]
        return [fault for space in spaces
                for fault in ohwt.workspace_faults(space)]

    def keys() -> list[str]:
        names = {s.agent.model.api_key_env for _, _, _, s in workflow.steps()
                 if s.agent is not None and s.agent.model.api_key_env}
        return [f"model key variable {var} is empty or unset"
                for var in sorted(names) if not os.environ.get(var)]

    def branch() -> list[str]:
        out = []
        for space in spaces:
            repo = Path(space.path)
            if not ohwt.is_git(repo):
                continue
            now = ohexec.git("rev-parse --abbrev-ref HEAD", repo).stdout.strip()
            if now != space.base_branch:
                out.append(f"{subject(space)} is on branch {now!r}, workflow "
                           f"expects {space.base_branch!r}")
        return out

    def clean() -> list[str]:
        out = []
        for space in spaces:
            repo = Path(space.path)
            if not ohwt.is_git(repo):
                continue
            dirty = ohexec.git("status --porcelain --untracked-files=no",
                               repo).stdout.strip()
            if dirty:
                out.append(f"{subject(space)} tree is dirty:\n{dirty[:500]}")
        return out

    def remotes() -> list[str]:
        out = []
        for space in spaces:
            repo = Path(space.path)
            if not space.remote or not ohwt.is_git(repo):
                continue
            found = ohexec.git("remote get-url origin", repo)
            origin = found.stdout.strip() if found.returncode == 0 else ""
            if space.owned and not origin:
                continue
            if origin != space.remote:
                out.append(f"workspace {space.name!r}: origin is "
                           f"{origin or 'not set'}, the workflow names "
                           f"{space.remote}")
        return out

    def junctions() -> list[str]:
        out = []
        for w in workflow.worktrees:
            # A prior phase may create this base; the phase boundary resolves
            # it where the worktree is first needed.
            if w.node_modules_mode == "junction":
                try:
                    repo = Path(workflow.workspace(w.workspace).path)
                except KeyError:
                    continue
                src = ohwt.source_dir(repo, w)
                if not src.exists():
                    out.append(f"worktree {w.name!r}: node_modules source "
                               f"missing at {win(src)}")
        return out

    def long_paths() -> list[str]:
        if os.name != "nt":
            return []
        roots: dict[str, list[WorktreeSpec]] = {}
        default = spaces[0].name if spaces else ""
        for _, _, _, step in workflow.steps():
            if not step.worktree or (step.agent is not None
                                     and carried_by_git(step.agent)):
                continue
            spec = next((w for w in workflow.worktrees
                         if w.name == step.worktree), None)
            if spec is None:
                continue
            roots.setdefault(spec.workspace or default, []).append(spec)
        out = []
        for space in spaces:
            mine = roots.get(space.name) or []
            if not mine:
                continue
            repo = Path(space.path)
            if not ohwt.is_git(repo):
                continue
            enabled = ohexec.git("config --type=bool core.longpaths", repo)
            if enabled.returncode == 0 and enabled.stdout.strip() == "true":
                continue
            tracked_at: dict[str, list[str]] = {}
            index: list[str] | None = None
            measured = []
            for spec in mine:
                if spec.base not in tracked_at:
                    at = _tracked_at_base(repo, spec.base)
                    if at is None:
                        if index is None:
                            index = _tracked_in_index(repo)
                        at = index
                    tracked_at[spec.base] = at
                longest = max((len(p) for p in tracked_at[spec.base]), default=0)
                measured.append((len(str(spec.path)) + 1 + longest, spec,
                                 longest))
            full, root, longest = max(measured, key=lambda m: m[0])
            if full >= WINDOWS_PATH_LIMIT:
                out.append(f"workspace {space.name!r} at {win(repo)}: no "
                           f"core.longpaths, and the worktree root "
                           f"{root.name!r} ({len(str(root.path))}) plus the "
                           f"longest tracked path ({longest}) gives a full "
                           f"path of {full}, past the "
                           f"{WINDOWS_PATH_LIMIT - 1} Windows allows")
        return out

    bases = " or ".join(dict.fromkeys(s.base_branch for s in spaces)) or "the base"
    return [
        Check("repository", is_repo,
              "pass the repo path the workflow names" if not several else
              "pass the path of each workspace the workflow names"),
        Check("model keys", keys, "set the variable in this shell"),
        *harness_executor_checks(_workflow_harness_executors(workflow), resolver),
        Check("base branch", branch,
              f"run `git checkout {bases}` in the "
              + ("workspace" if several else "repo")),
        Check("clean tree", clean, "commit or set aside the changes"),
        Check("workspace remote", remotes,
              "point origin at the remote the workflow names, or correct "
              "the Workspace"),
        Check("worktree path length", long_paths,
              "git -C <repo> config core.longpaths true"),
        Check("node_modules source", junctions,
              "install the dependencies, or change the worktree's mode"),
    ]


def workflow_problems(workflow, resolver: Callable) -> list[str]:
    """The faults the engine refuses to start on, in the words it always used.

    A repository that is not one stops the list at that fault: nothing else
    can be read from it.
    """
    faults: list[str] = []
    for check in workflow_checks(workflow, resolver):
        found = check.observe()
        faults += found
        if check.need == "repository" and found:
            break
    return faults

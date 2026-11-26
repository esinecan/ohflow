"""The git transport between this machine's worktree and the box.

The run's worktree sits on this machine and the agent works on the box, so git
carries the step. `push_start` moves the step's start commit to the project's
own remote on an `ohflow/` branch, the box clones from that remote, the agent
pushes its result to the same branch, `fetch_result` moves the answer back
into the run's worktree with a fast-forward, and `delete_branch` removes the
branch once its commit is in the worktree. The `pi-cloud` harness executor
uses the same transport and the same `attempt_key`, which is why both live here
and not inside one harness executor's runner.

Nothing here imports a harness executor module, and nothing here names the box:
the transport is git only. Every branch it exchanges sits under `ohflow/`,
and `push_start` refuses any other prefix.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from . import exec as ohexec
from .paths import posix, win

__all__ = ["remote_url", "push_start", "fetch_result", "delete_branch",
           "attempt_key", "rewrite_paths", "transport_position"]

#: Every branch this transport exchanges sits under this prefix. `push_start`
#: refuses anything else, so every transport branch is found in one place.
BRANCH_RULE = "ohflow/"

_KEY_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def attempt_key(coord: str, attempt: int, out_dir: Path) -> str:
    """The name of one execution's folder on the other machine and branch on
    origin.

    The coordinate and the attempt name the work; the hash of the resolved
    attempt directory makes the key unique across runs that share a coordinate,
    so two run directories never share a remote folder or a branch. Every
    harness executor that runs its step elsewhere mints its key here, so the
    durable box folder and the pi-cloud Durable Object name follow one rule.
    """
    base = _KEY_SAFE.sub("-", str(coord))
    digest = hashlib.sha1(
        str(Path(out_dir).resolve()).encode("utf-8")).hexdigest()[:8]
    return f"{base}-a{int(attempt):02d}-{digest}"


def remote_url(worktree: Path) -> str:
    """The project's own remote, the one the box clones from.

    The transport refuses a repository with no `origin` rather than
    guessing a fork or an URL, because the branch the box pushes back to must
    be the branch this worktree fetches.
    """
    worktree = Path(worktree)
    found = ohexec.git("remote get-url origin", worktree, timeout=60)
    if found.returncode != 0:
        raise ValueError(
            f"a step on another machine works from the project's own remote; "
            f"{win(worktree)} has no origin")
    url = found.stdout.strip()
    if not url:
        raise ValueError(
            f"a step on another machine works from the project's own remote; "
            f"{win(worktree)} has an empty origin")
    return url


def rewrite_paths(text: str, pairs) -> str:
    """Replace each local path in `text` with its remote spelling.

    Every harness executor that runs its step on another machine points the
    brief away from this machine's folders, and the rule is one: each
    `(local, remote)` couple in `pairs` replaces both renderings of `local`
    (`paths.win` and `paths.posix`, because the position block and the brief
    mix them) with `remote`. A couple whose local side is empty, or whose
    rendering already is the remote spelling, is skipped.
    """
    for old, new in pairs:
        if not old:
            continue
        for rendered in (win(old), posix(old)):
            if rendered and rendered != new:
                text = text.replace(rendered, new)
    return text


_POSITION_BRANCH = re.compile(
    r"^(Worktree:[ \t]+[^\n]*\n)([ \t]+)branch (\S+), created from ([^\n]+)$",
    re.MULTILINE)


def transport_position(text: str, branch: str, start_sha: str) -> str:
    if not branch:
        return text

    def put(found: re.Match) -> str:
        head, indent, local, base = found.groups()
        start = start_sha[:7] if start_sha else "the start commit"
        return (f"{head}{indent}current branch {branch}, the transport checkout "
                f"cloned at {start}\n"
                f"{indent}after the step, ohflow fetches this branch's commits onto "
                f"the worktree's branch {local}, created from {base}")

    return _POSITION_BRANCH.sub(put, text, count=1)


def push_start(worktree: Path, branch: str) -> str:
    """Push the start commit to `branch` on origin and return its sha.

    Refuses a branch outside `ohflow/`, because every branch this transport
    exchanges - any harness executor's - sits under that prefix, and a stray
    name would leak transport branches into the project's branch list.
    Refuses a dirty tree, naming the paths: anything uncommitted here never
    reaches the other machine, and an agent would answer a different question
    than the one this worktree asked.
    """
    worktree = Path(worktree)
    if not branch.startswith(BRANCH_RULE):
        raise ValueError(
            f"a transport branch must sit under {BRANCH_RULE}, got {branch!r}")
    dirty = ohexec.git("status --porcelain", worktree, timeout=120).stdout.strip()
    if dirty:
        raise ValueError(
            f"a step on another machine starts from the start commit this "
            f"transport pushes from {win(worktree)}, and uncommitted work "
            f"would not reach the other machine; commit or set aside:\n{dirty[:1500]}")
    head = ohexec.git_out("rev-parse HEAD", worktree)
    pushed = ohexec.git(f"push --force origin HEAD:refs/heads/{branch}",
                        worktree, timeout=600)
    if pushed.returncode != 0:
        raise RuntimeError(
            f"git push origin HEAD:refs/heads/{branch} in {posix(worktree)} "
            f"exited {pushed.returncode}\n{pushed.tail}")
    return head


def fetch_result(worktree: Path, branch: str, start_sha: str) -> str:
    """Fetch the step's answer from `branch` and return the worktree's new HEAD.

    The move is a fast-forward from the start commit this worktree pushed, or
    nothing at all when the worktree already holds the fetched commit. Anything
    else - the branch moved sideways, the worktree moved on its own - is
    refused with both shas, because silently merging an unrelated history would
    hide a step that answered someone else's question.
    """
    worktree = Path(worktree)
    fetched = ohexec.git(f"fetch origin refs/heads/{branch}", worktree, timeout=600)
    if fetched.returncode != 0:
        raise RuntimeError(
            f"git fetch origin refs/heads/{branch} in {posix(worktree)} exited "
            f"{fetched.returncode}\n{fetched.tail}")
    their_head = ohexec.git_out("rev-parse FETCH_HEAD", worktree)
    our_head = ohexec.git_out("rev-parse HEAD", worktree)
    if our_head == their_head:
        return our_head
    if our_head != start_sha:
        # Two different faults, two messages: this one is about this machine's
        # worktree, and the fetched commit may descend from the attempt just
        # fine. Blaming the branch here would hide what actually moved.
        raise ValueError(
            f"the worktree {win(worktree)} moved on its own: it is at "
            f"{our_head} and the attempt started at {start_sha}, so "
            f"refs/heads/{branch} ({their_head}) cannot be merged here")
    ancestor = ohexec.git(f"merge-base --is-ancestor {start_sha} {their_head}",
                          worktree, timeout=120)
    if ancestor.returncode != 0:
        raise ValueError(
            f"refs/heads/{branch} on origin holds {their_head}, which does "
            f"not descend from this attempt's start commit {start_sha}; the "
            f"worktree {win(worktree)} is still at {our_head}")
    merged = ohexec.git("merge --ff-only FETCH_HEAD", worktree, timeout=600)
    if merged.returncode != 0:
        raise RuntimeError(
            f"git merge --ff-only FETCH_HEAD in {posix(worktree)} exited "
            f"{merged.returncode}\n{merged.tail}")
    return ohexec.git_out("rev-parse HEAD", worktree)


def delete_branch(worktree: Path, branch: str) -> bool:
    """Delete `branch` from origin; False when origin refused.

    Called once the fetched commit is in the worktree, so the branch has served
    its purpose. A refusal is no error - the branch only lingers - so the
    caller records it rather than raising, and a reattach after this point
    pushes the branch again anyway.
    """
    worktree = Path(worktree)
    done = ohexec.git(f"push origin --delete {branch}", worktree, timeout=300)
    return done.returncode == 0

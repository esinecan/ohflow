"""The cache key. Content-keyed, not resume-by-call-order.

The fingerprint covers the rendered brief including the position block, the tool
policy, the model identity, the gate specification, the base commit of the
step's worktree, and the fingerprints of every step this one depends on.

Editing phase 4 therefore does not invalidate phase 2.

The run id is excluded on purpose: a resume of the same run must hit the cache
whatever its run id, and the cache reads only the current run's own history, so
a new run directory reuses nothing.

The attempt number is excluded for the same reason. A fingerprint names the
work, not how many tries it took: a step that passed on its second attempt must
be `cached` on the next resume, otherwise every retried step re-runs an agent
forever. The attempt is also the attempt history key's partner, so keeping it out of the
key is what lets `ohflow.attempts` count attempts against one stable identity.

The hashed body still carries `"attempt": 1` and still renders the position
block with `attempt=1`. Both are hardcoded, so the attempt cannot make a
fingerprint drift within one cache-key version. An explicit fingerprint-version
bump may still invalidate older run directories once, as versions 2 to 7 do.

Every field of the workflow dataclasses is either hashed here or named, with a
reason, in `tests/test_fingerprint_fields.py`. A new field fails that test until
it is one or the other.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from . import proc
from .coords import coord, render_position
from .run_log import RunState
from .workflow import Workflow, Step, to_jsonable

__all__ = ["FINGERPRINT_VERSION", "fingerprint", "fingerprint_input",
           "worktree_dirty_digest"]


# Version 2 adds the live, uncommitted worktree state and the command time cap.
# Version 3 adds merge_message and skills_dir, which a step could change without
# changing its key.  The explicit version makes each intentional one-time
# invalidation visible in a run's cache input instead of leaving readers to
# infer it from a changed hash.
# Version 4 follows the glossary rename: the position block says "Write scope" and
# "workflow", and the hashed body names the renamed fields (agent, harness_executor,
# write_scope, execution_timeout_s, tool policy).
# Version 5 adds explicit handover contracts, readers and consumed content digests.
# Version 6 names the command time cap command_time_cap_s in the hashed body.
# Version 7 names the local MCP blocklist profile fields explicitly.
FINGERPRINT_VERSION = 7


#: Hardcoded so the hash stays what it was when the attempt was a parameter.
#: Never make this a parameter again: an attempt-dependent cache key means a
#: step that passed on attempt 2 misses the cache on every later resume.
_CACHE_KEY_ATTEMPT = 1


def _git_bytes(worktree: Path, *args: str) -> bytes:
    kwargs = ({"creationflags": subprocess.CREATE_NO_WINDOW}
              if os.name == "nt" else {})
    completed = proc.run(
        ["git", "-C", str(worktree), *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(
            f"git {' '.join(args)} in {worktree} exited "
            f"{completed.returncode}: {detail}")
    return completed.stdout


def _hash_part(digest, label: bytes, value: bytes) -> None:
    """Length-prefix a field so path/content boundaries cannot collide."""
    digest.update(label)
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


def worktree_dirty_digest(worktree: Path) -> str:
    """Digest tracked edits and non-ignored untracked paths plus contents.

    `git diff HEAD` sees staged and unstaged tracked changes.  `ls-files
    --others --exclude-standard` supplies exactly the untracked set ordinary
    `git status --porcelain` reports, so ignored build output stays outside the
    cache identity.  HEAD itself is deliberately absent: an agent that commits
    its output returns to the same fixed clean digest it started with.
    """
    root = Path(worktree)
    if not root.is_dir():
        # Workflow-only callers can compare cache inputs after their temporary
        # repository has gone away.  This value cannot match a prior clean
        # tree, so a real resume still misses and reaches the engine's normal
        # missing-worktree failure instead of approving stale work.
        return hashlib.sha256(b"ohflow-worktree-missing-v1\0").hexdigest()
    tracked = _git_bytes(root, "diff", "HEAD", "--binary", "--no-ext-diff", "--")
    untracked_raw = _git_bytes(
        root, "-c", "core.quotepath=false", "ls-files", "--others",
        "--exclude-standard", "-z", "--")
    paths = sorted(path for path in untracked_raw.split(b"\0") if path)

    digest = hashlib.sha256()
    digest.update(b"ohflow-worktree-dirty-v1\0")
    _hash_part(digest, b"tracked\0", tracked)
    for raw_path in paths:
        relative = raw_path.decode("utf-8", "surrogateescape")
        content = (root / relative).read_bytes()
        _hash_part(digest, b"path\0", raw_path)
        _hash_part(digest, b"content\0", content)
    return digest.hexdigest()


def fingerprint_input(workflow: Workflow, state: RunState, step: Step) -> dict[str, Any]:
    pi, phase, si, _ = workflow.step_by_id(step.id)
    c = coord(pi, phase.slug, si, step.id)
    wt_live = (state.meta.get("worktrees") or {}).get(step.worktree or "", {})
    spec = workflow.worktree(step.worktree) if step.worktree else None
    workspace = Path(spec.path) if spec else Path(workflow.repo)

    body = {
        "fingerprint_version": FINGERPRINT_VERSION,
        "coord": c,
        "kind": step.kind,
        "attempt": _CACHE_KEY_ATTEMPT,
        "position": render_position(workflow, state, step,
                                    attempt=_CACHE_KEY_ATTEMPT,
                                    include_run_id=False),
        "command": step.command,
        "shell": step.shell,
        "merge_branch": step.merge_branch,
        "gate": to_jsonable(step.gate),
        "schema": to_jsonable(step.schema),
        "consumes": list(step.consumes),
        "handover": to_jsonable(step.handover),
        "handovers": {},
        "write_scope": list(step.write_scope),
        "execution_timeout_s": step.execution_timeout_s,
        "worktree": {
            "name": step.worktree,
            "branch": spec.branch if spec else None,
            "base": spec.base if spec else None,
            "base_sha": wt_live.get("base_sha"),
            "node_modules_mode": spec.node_modules_mode if spec else None,
            "dirty_digest": worktree_dirty_digest(workspace),
        },
        "deps": {},
    }
    if spec is not None and spec.workspace is not None:
        body["worktree"]["workspace"] = spec.workspace
    # Keep optional execution fields absent at their defaults.  That is the v2
    # body contract, kept in v3; future additions should either preserve it or bump the
    # explicit fingerprint version.
    if step.stall_timeout_s is not None:
        body["stall_timeout_s"] = step.stall_timeout_s
    if step.merge_message is not None:
        body["merge_message"] = step.merge_message
    if step.retry.carry_context:
        body["retry"] = {"carry_context": True}
    if step.agent is not None:
        w = step.agent
        body["agent"] = {
            "role": w.role,
            "brief": w.brief,
            "harness_executor": w.harness_executor,
            "model": to_jsonable(w.model),
            # MCP narrowing remains an extension of the four base tool fields.
            "tools": {
                "preset": w.tools.preset,
                "enable_browser": w.tools.enable_browser,
                "enable_sub_agents": w.tools.enable_sub_agents,
                "only": list(w.tools.only),
            },
            "skills": sorted(w.skills),
            "max_iterations": w.max_iterations,
            "command_time_cap_s": w.command_time_cap_s,
            "mcp_config": to_jsonable(w.mcp_config),
        }
        if w.fork_session:
            body["agent"]["fork_session"] = w.fork_session
        if w.agent_profile is not None:
            body["agent"]["agent_profile"] = w.agent_profile
        if w.box is not None:
            body["agent"]["box"] = w.box
        if w.skills_dir is not None:
            body["agent"]["skills_dir"] = str(w.skills_dir)
        if w.tools.allow or w.tools.block:
            body["agent"]["mcp_tool_policy"] = {
                "allow": list(w.tools.allow), "mcp_blocklist_profile": None}
        if w.tools.block:
            body["agent"]["mcp_tool_policy"]["block"] = list(w.tools.block)
    for dep in sorted(step.depends_on):
        dpi, dphase, dsi, dstep = workflow.step_by_id(dep)
        dcoord = coord(dpi, dphase.slug, dsi, dstep.id)
        rec = state.steps.get(dcoord)
        body["deps"][dep] = rec.fingerprint if rec else None
    for dep in step.consumes:
        dpi, dphase, dsi, dstep = workflow.step_by_id(dep)
        rec = state.steps.get(coord(dpi, dphase.slug, dsi, dstep.id))
        body["handovers"][dep] = rec.handover_sha256 if rec else None
    return body


def fingerprint(workflow: Workflow, state: RunState, step: Step) -> str:
    payload = json.dumps(fingerprint_input(workflow, state, step),
                         sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

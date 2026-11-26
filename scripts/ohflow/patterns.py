"""The six workflow patterns that `ohflow construct` builds a milestone in.

A constructed milestone directory holds `milestone.json`, the briefs it names
and a `workflow.py` that calls `build_milestone`. The JSON names the pattern,
the workspaces, the agent steps with their executor, box and tier, and the
mechanical checks. The judge of a campaign may edit the JSON and the briefs, and
the next round builds the workflow from what they say.

Every worktree bases on the campaign's integration branch. Each workspace a
step writes in has one worktree on the milestone's output branch, named after
the workspace, so the campaign lands the milestone in every workspace it
wrote in.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from . import settings, tiers
from .workflow import (AgentSpec, CheckSpec, GateSpec, HandoverSpec, ModelConfig,
                       Phase, Step, ToolPolicy, Unit, UnitPath, Workflow,
                       WorkflowError, Workspace, WorktreeSpec, clean_commit_checks)

__all__ = ["PATTERNS", "ROLES", "PIECE_PATTERNS", "REVIEW_VERDICT", "REVIEW_SCHEMA",
           "build_milestone", "expand", "model_config"]

PATTERNS = ("single-agent", "relay", "fan-out", "fan-out-with-consolidation",
            "fan-out-under-contracts", "implement-and-review")

PIECE_PATTERNS = ("relay", "fan-out", "fan-out-with-consolidation",
                  "fan-out-under-contracts")

ROLES = {
    "single-agent": ("agent",),
    "relay": (),
    "fan-out": (),
    "fan-out-with-consolidation": ("consolidate",),
    "fan-out-under-contracts": ("review",),
    "implement-and-review": ("implement", "review"),
}

REVIEW_VERDICT = r"VERDICT:\s*MERGEABLE"

FINDING = {
    "type": "object",
    "required": ["piece", "path", "claim"],
    "properties": {
        "piece": {"type": "string"},
        "path": {"type": "string"},
        "line": {"type": "integer"},
        "contract": {"type": "string"},
        "claim": {"type": "string"},
        "fix": {"type": "string"},
    },
}

REVIEW_SCHEMA = {
    "type": "object",
    "required": ["blocking", "should_fix", "notes", "summary"],
    "properties": {
        "blocking": {"type": "array", "items": FINDING},
        "should_fix": {"type": "array", "items": FINDING},
        "notes": {"type": "array", "items": FINDING},
        "summary": {"type": "string"},
    },
}

PLACEHOLDER = re.compile(r"(?<!\$)\{([a-z0-9][a-z0-9-]*)\}")
WRITER_ITERATIONS = 150
REVIEW_ITERATIONS = 80
MAX_PARALLEL = 5


def expand(cmd: str, here: str, written: set[str] | frozenset[str]) -> str:
    """`cmd` with each `{workspace}` replaced by a Git Bash expression for the
    output worktree of that workspace, as seen from the output worktree of
    `here`. The worktrees of one milestone are sibling folders named after
    their workspaces, and a pilot suffixes every folder alike, so the sibling
    is found from `$PWD` in both runs."""
    def sub(match: re.Match) -> str:
        name = match[1]
        if name not in written:
            return match[0]
        if name == here:
            return '"$PWD"'
        return f'"$(dirname "$PWD")/{name}${{PWD##*/{here}}}"'
    return PLACEHOLDER.sub(sub, cmd)


def model_config(executor: str, tier: str) -> ModelConfig:
    """The model of a constructed agent step: its tier, with what the
    executor needs beside it. A `pi` step names the variable that holds its
    provider's key: `pi.api_key_env.<provider>` in the operator settings,
    else `<PROVIDER>_API_KEY`, and `pi.base_url.<provider>` when set."""
    if executor == "pi":
        provider = tiers.model_for(tier, "pi").split("/", 1)[0]
        key = (settings.get(f"pi.api_key_env.{provider}")
               or re.sub(r"[^A-Za-z0-9]", "_", provider).upper() + "_API_KEY")
        return ModelConfig(model=tier,
                           base_url=settings.get(f"pi.base_url.{provider}") or "",
                           api_key_env=str(key), params={"thinking": "high"})
    if executor in ("durable", "pi-cloud"):
        return ModelConfig(model=tier, base_url="", api_key_env="",
                           params={"thinking": "high"})
    if executor == "claude":
        return ModelConfig(model=tier, base_url="", api_key_env="",
                           params={"effort": "high"})
    if executor == "codex":
        return ModelConfig(model=tier, base_url="", api_key_env="",
                           params={"reasoning_effort": "high"})
    return ModelConfig(model=tier, base_url="", api_key_env="")


def _agent(step: Mapping[str, Any], mdir: Path, *, review: bool) -> AgentSpec:
    executor = step["executor"]
    tools, profile = ToolPolicy(), None
    if review and executor in ("pi", "durable"):
        tools = ToolPolicy(only=("terminal",))
    elif review and executor == "claude":
        tools, profile = ToolPolicy(only=("terminal",)), "hermetic"
    brief = mdir / step["brief"]
    try:
        text = brief.read_text(encoding="utf-8")
    except OSError as error:
        raise WorkflowError(f"step {step['id']!r}: brief unreadable: {brief}: {error}") from None
    return AgentSpec(
        role=step["id"], brief=text, model=model_config(executor, step["tier"]),
        tools=tools, agent_profile=profile,
        box=step.get("box") if executor == "durable" else None,
        max_iterations=REVIEW_ITERATIONS if review else WRITER_ITERATIONS,
        harness_executor=executor)


def _objective(step: Mapping[str, Any], title: str) -> str:
    text = f"{step['id']}: {title}".replace("\n", " ")
    return text if len(text) <= 120 else text[:117] + "..."


def _commands(data: Mapping[str, Any], workspace: str,
              written: frozenset[str]) -> tuple[CheckSpec, ...]:
    out = []
    for c in data.get("commands", ()):
        if c["workspace"] != workspace:
            continue
        cmd = expand(c["cmd"], workspace, written)
        args = {"cmd": cmd, "expect": 0}
        if cmd != expand(c["cmd"], workspace, frozenset({workspace})):
            args["reuse"] = False
        out.append(CheckSpec("command_exit", args))
    return tuple(out)


def _path(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def build_milestone(milestone_file: str | Path, args: Mapping[str, Any]) -> Workflow:
    """The workflow of one constructed milestone, from its `milestone.json`."""
    milestone_file = Path(milestone_file)
    mdir = milestone_file.parent
    data = json.loads(milestone_file.read_text(encoding="utf-8"))
    pattern = data["pattern"]
    if pattern not in PATTERNS:
        raise WorkflowError(f"{milestone_file}: unknown pattern {pattern!r}; use one of "
                            f"{', '.join(PATTERNS)}")
    root = Path(args["campaign_root"])
    base = args["integration_branch"]
    mid = data["id"]
    branch = data["branch"]
    timeout = int(data.get("execution_timeout_s") or 5400)
    steps = list(data["steps"])
    written = frozenset(s["workspace"] for s in steps
                        if s["role"] not in ("review",))
    spaces = tuple(Workspace(name=w["name"], path=_path(root, w["path"]),
                             base_branch=w.get("base_branch") or "main",
                             remote=w.get("remote") or None,
                             baseline_cmd=w.get("baseline_cmd") or None,
                             owned=bool(w.get("owned")))
                   for w in data["workspaces"])
    trees = root / "worktrees" / mid
    worktrees = [WorktreeSpec(name=w.name, path=trees / w.name, branch=branch,
                              base=base, node_modules_mode="none", workspace=w.name)
                 for w in spaces if w.name in written]
    title = data.get("title") or mid
    build = _BUILDERS[pattern]
    phases, extra, paths, units = build(data, steps, mdir, title, timeout, written,
                                        trees, branch, base)
    return Workflow(name=mid, workspaces=spaces, worktrees=tuple(worktrees + extra),
                    phases=tuple(phases), max_parallel=MAX_PARALLEL, args=dict(args),
                    paths=paths, units=units)


def _writer(step, mdir, title, timeout, *, worktree, since="base", min_commits=1,
            commands=()) -> Step:
    writes = tuple(step.get("writes") or ("**",))
    return Step(id=step["id"], kind="agent", worktree=worktree, write_scope=writes,
                execution_timeout_s=timeout,
                gate=GateSpec(clean_commit_checks(writes, since=since,
                                                  min_commits=min_commits) + tuple(commands)),
                objective=_objective(step, title),
                agent=_agent(step, mdir, review=False))


def _single(data, steps, mdir, title, timeout, written, trees, branch, base):
    step = steps[0]
    ws = step["workspace"]
    agent = _writer(step, mdir, title, timeout, worktree=ws,
                    commands=_commands(data, ws, written))
    return [Phase("Build", (agent,), "abort", "all", 1)], [], (), ()


def _implement_review(data, steps, mdir, title, timeout, written, trees, branch, base):
    implement = next(s for s in steps if s["role"] == "implement")
    review = next(s for s in steps if s["role"] == "review")
    ws = implement["workspace"]
    commands = _commands(data, ws, written)
    first = _writer(implement, mdir, title, timeout, worktree=ws, commands=commands)
    first = replace(first, handover=HandoverSpec(audience="reviewer"))
    second = Step(id=review["id"], kind="agent", worktree=ws, execution_timeout_s=timeout,
                  depends_on=(first.id,), consumes=(first.id,),
                  gate=GateSpec((CheckSpec("final_message_matches", {"regex": REVIEW_VERDICT}),
                                 CheckSpec("tree_clean", {})) + commands),
                  objective=_objective(review, title),
                  agent=_agent(review, mdir, review=True))
    return [Phase("Implement", (first,), "abort", "all", 1),
            Phase("Review", (second,), "continue", "all", 1)], [], (), ()


def _relay(data, steps, mdir, title, timeout, written, trees, branch, base):
    last = {s["workspace"]: s["id"] for s in steps}
    phases, previous = [], None
    for n, step in enumerate(steps, start=1):
        ws = step["workspace"]
        commands = _commands(data, ws, written) if last[ws] == step["id"] else ()
        agent = _writer(step, mdir, title, timeout, worktree=ws, since="step_start",
                        commands=commands)
        if previous:
            agent = replace(agent, depends_on=(previous,), consumes=(previous,))
        phases.append(Phase(f"Relay {n} {step['id']}", (agent,), "abort", "all", 1))
        previous = step["id"]
    return phases, [], (), ()


def _pieces(data, steps, mdir, title, timeout, trees, branch, base):
    pieces = [s for s in steps if s["role"] == "piece"]
    extra, built, merges = [], [], []
    for piece in pieces:
        name = piece["id"]
        handle = f"piece-{name}"
        extra.append(WorktreeSpec(name=handle, path=trees / handle,
                                  branch=f"{branch}-{name}", base=base,
                                  node_modules_mode="none", workspace=piece["workspace"]))
        step = _writer(piece, mdir, title, timeout, worktree=handle)
        built.append(replace(step, unit=name,
                             handover=HandoverSpec(audience="consolidator")))
        merges.append(Step(id=f"merge-{name}", kind="merge", worktree=piece["workspace"],
                           depends_on=(name,), merge_branch=f"{branch}-{name}",
                           merge_message=f"{data['id']}: merge {name}", unit=name))
    parallel = min(MAX_PARALLEL, len(built))
    phases = [Phase("Build pieces", tuple(built), "abort", "all", parallel),
              Phase("Merge pieces", tuple(merges), "abort", "all", 1)]
    paths = (UnitPath("piece", "one piece of the milestone"),)
    units = tuple(Unit(id=p["id"], path="piece") for p in pieces)
    return phases, extra, paths, units, tuple(s.id for s in built + merges), \
        tuple(s.id for s in built)


def _checks(data, written, after) -> list[Phase]:
    commands = [Step(id=f"check-{c['name']}", kind="command", worktree=c["workspace"],
                     command=expand(c["cmd"], c["workspace"], written),
                     depends_on=after, note=f"acceptance command in {c['workspace']}")
                for c in data.get("commands", ())]
    return [Phase("Check", tuple(commands), "continue", "all", 1)] if commands else []


def _fan_out(data, steps, mdir, title, timeout, written, trees, branch, base):
    phases, extra, paths, units, done, _ = _pieces(data, steps, mdir, title, timeout,
                                                   trees, branch, base)
    return phases + _checks(data, written, done), extra, paths, units


def _consolidate(data, steps, mdir, title, timeout, written, trees, branch, base):
    phases, extra, paths, units, done, pieces = _pieces(data, steps, mdir, title,
                                                        timeout, trees, branch, base)
    lead = next(s for s in steps if s["role"] == "consolidate")
    step = _writer(lead, mdir, title, timeout, worktree=lead["workspace"],
                   since="last_merge", min_commits=0)
    step = replace(step, depends_on=done, consumes=pieces)
    phases.append(Phase("Consolidate", (step,), "abort", "all", 1))
    return phases + _checks(data, written, done + (step.id,)), extra, paths, units


def _contracts(data, steps, mdir, title, timeout, written, trees, branch, base):
    from .workflows.contract_fanout import blocking_gate_cmd
    phases, extra, paths, units, done, pieces = _pieces(data, steps, mdir, title,
                                                        timeout, trees, branch, base)
    lead = next(s for s in steps if s["role"] == "review")
    review = Step(id=lead["id"], kind="agent", worktree=lead["workspace"],
                  depends_on=done, consumes=pieces, execution_timeout_s=timeout,
                  schema=REVIEW_SCHEMA,
                  gate=GateSpec((CheckSpec("tree_clean", {}), CheckSpec("schema_valid", {}),
                                 CheckSpec("command_exit", {"cmd": blocking_gate_cmd(),
                                                            "expect": 0}))),
                  objective=_objective(lead, title),
                  agent=_agent(lead, mdir, review=True))
    phases.append(Phase("Review", (review,), "continue", "all", 1))
    return phases + _checks(data, written, done + (review.id,)), extra, paths, units


_BUILDERS = {
    "single-agent": _single,
    "relay": _relay,
    "fan-out": _fan_out,
    "fan-out-with-consolidation": _consolidate,
    "fan-out-under-contracts": _contracts,
    "implement-and-review": _implement_review,
}

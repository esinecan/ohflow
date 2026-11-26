"""The workflow model: frozen dataclasses plus `validate`.

A workflow file is a Python module that exports `build(args: dict) -> Workflow`. The
engine imports it once, calls `build` once, and never executes workflow code again.
"""

from __future__ import annotations

import fnmatch
import importlib
import importlib.util
import math
import os
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

__all__ = [
    "Workflow", "Phase", "Step", "AgentSpec", "GateSpec", "CheckSpec", "HandoverSpec",
    "Unit", "UnitPath", "clean_commit_checks", "house_checks", "WorktreeSpec", "Workspace", "RetryPolicy", "ModelConfig", "ToolPolicy",
    "BASE_SHA_MODES", "OBJECTIVE_MAX", "objective_warnings",
    "WorkflowError", "validate", "load_workflow", "slug", "to_jsonable",
    "from_jsonable",
    "mcp_glob_regex", "mcp_matches_glob",
]

# Retrying these two repeats a brief that produced the wrong behaviour.
FORBIDDEN_RETRY_ON = frozenset({"gate:ownership", "gate:no_ai_attribution"})
STEP_KINDS = frozenset({"agent", "command", "gate", "merge"})
FAILURE_POLICIES = frozenset({"abort", "continue", "quarantine"})
NODE_MODULES_MODES = frozenset({"junction", "install", "none"})
BASE_SHA_MODES = frozenset({"head", "merge_base"})
from . import settings, tiers  # noqa: E402
from .harness_executors import (CAP_BOX, CAP_CARRY, CAP_AGENT_PROFILE, CAP_STALL,  # noqa: E402
                    HARNESS_EXECUTORS, harness_executor_info, harness_executor_module, harness_executors_with)


class WorkflowError(Exception):
    """Raised by `validate`. The CLI turns this into exit code 2.

    `problems` holds one entry for each fault; the message joins them.
    """

    def __init__(self, message: str = "", problems: list[str] | None = None):
        super().__init__(message)
        self.problems = list(problems) if problems else (
            [message] if message else [])


class WorkflowArgMissing(WorkflowError, KeyError):
    """A workflow or campaign read an `--args` key that was not given.

    It is a `KeyError` too, so a workflow that catches `KeyError` around its own
    lookup keeps working. The CLI prints `message` and exits 2.
    """

    def __init__(self, name: str):
        super().__init__(name)
        self.name = name

    @property
    def message(self) -> str:
        return (f"workflow argument missing: {self.name} "
                f"(pass --args {self.name}=...)")

    def __str__(self) -> str:
        return self.message


class WorkflowArgs(dict):
    """The `args` dict a workflow's `build` reads: a missing key is named."""

    def __missing__(self, key):
        raise WorkflowArgMissing(str(key))


def slug(text: str) -> str:
    """'Generate: batch A' -> 'batch-a'. Used for phase directory names."""
    text = text.split(":")[-1] if ":" in text else text
    out = re.sub(r"[^A-Za-z0-9]+", "-", text.strip().lower()).strip("-")
    return out or "phase"


# --------------------------------------------------------------- leaf records


@dataclass(frozen=True)
class ModelConfig:
    model: str
    base_url: str
    api_key_env: str          # a variable NAME. The key itself never lands here.
    # Each harness executor accepts a closed set of keys, for example pi's
    # `thinking` and codex's `reasoning_effort`. Its `agent_errors` names the set.
    params: Mapping[str, Any] = field(default_factory=dict)
    # Every harness executor refuses a non-empty `extra_body`. The field stays
    # because the step fingerprint hashes the whole ModelConfig.
    extra_body: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolPolicy:
    preset: str = "default"
    enable_browser: bool = False
    enable_sub_agents: bool = False
    only: tuple[str, ...] = ()   # narrow the preset to these tool names
    allow: tuple[str, ...] = ()
    block: tuple[str, ...] = ()


@dataclass(frozen=True)
class CheckSpec:
    name: str                            # a key in ohflow.gates.REGISTRY
    args: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GateSpec:
    checks: tuple[CheckSpec, ...] = ()

    def names(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.checks)


def house_checks(since: str = "base") -> tuple[CheckSpec, ...]:
    """The checks the operator's settings turn on for every committing agent.

    `commit_checks.no_ai_attribution` adds the check that no commit names an
    AI tool as author or co-author.
    """
    if settings.get("commit_checks.no_ai_attribution", False):
        return (CheckSpec("no_ai_attribution", {"since": since}),)
    return ()


def clean_commit_checks(write_scope: Sequence[str], *, since: str = "base",
                        min_commits: int = 1,
                        marker: str | None = None) -> tuple[CheckSpec, ...]:
    """The checks that every committing agent repeats.

    The agent made at least `min_commits` commit(s) past `since`, left a clean
    tree and touched only `write_scope`. The operator's house checks follow. A
    `marker` regex adds a check on the final message.
    """
    checks = [
        CheckSpec("commits_past_base", {"min": min_commits, "since": since}),
        CheckSpec("tree_clean"),
        CheckSpec("ownership", {"allowed": list(write_scope), "since": since}),
        *house_checks(since),
    ]
    if marker is not None:
        checks.append(CheckSpec("final_message_matches", {"regex": marker}))
    return tuple(checks)


@dataclass(frozen=True)
class RetryPolicy:
    max: int = 0
    on: tuple[str, ...] = ()
    carry_context: bool = False


@dataclass(frozen=True)
class Workspace:
    """One substrate a workflow works on: a git repository with a name.

    `owned=True` is a workspace that ohflow creates: the engine runs `git init`
    in `path` when the folder holds no repository yet, so work that is not code
    gets branches, diffs, handovers and `revert` as code does. `remote` is the
    URL of the workspace's `origin`, the remote a step on another machine
    clones from; None leaves the repository's own `origin` as it is.
    `baseline_cmd` must exit 0 at the base before a run starts.
    """
    name: str
    path: Path
    base_branch: str = "main"
    remote: str | None = None
    baseline_cmd: str | None = None
    owned: bool = False


@dataclass(frozen=True)
class WorktreeSpec:
    name: str                       # workflow-local handle, e.g. "integration"
    path: Path                      # where the worktree lives on disk
    branch: str                     # branch the worktree checks out
    base: str                       # branch name or sha it is created from
    node_modules_mode: str = "junction"
    node_modules_source: Path | None = None   # defaults to <repo>/node_modules
    node_modules_sentinel: str = "node_modules/.package-lock.json"
    install_cmd: str | None = None            # used when mode == "install"
    reuse_existing: bool = False
    # How `base_sha` is resolved for a worktree that already existed.
    #
    #   "head"        `git rev-parse HEAD`, which is what every workflow gets
    #                 today and what a fresh worktree means.
    #   "merge_base"  `git merge-base <base> HEAD`, the commit the work in this
    #                 worktree started from.
    #
    # The two differ only for a reused worktree that already carries commits.
    # `implement_review.py --mode review` is exactly that case: the worktree
    # holds the implementer's commits, and `HEAD` would make
    # `commits_past_base` read zero and the diff come back empty.
    base_sha_mode: str = "head"
    workspace: str | None = None


@dataclass(frozen=True)
class AgentSpec:
    """The authoring half of an agent. `ohflow.harness_executor.spec_json` turns this,
    plus the run-time coordinate and directories, into `spec.json`."""
    role: str
    brief: str
    model: ModelConfig
    tools: ToolPolicy = field(default_factory=ToolPolicy)
    skills: tuple[str, ...] = ()
    skills_dir: Path | None = None
    mcp_config: Mapping[str, Any] | None = None
    max_iterations: int = 150
    # No default: `validate` refuses an agent step that names none.
    harness_executor: str | None = None
    fork_session: str | None = None
    # None follows the step execution timeout. A value is an explicitly tighter cap.
    command_time_cap_s: int | None = None
    # Harness executors claude and codex only. None starts the agent in the signed-in harness's
    # usual setup: user hooks, memory, skills and the full MCP fleet.
    # "hermetic" strips that setup. A set value enters the step fingerprint.
    agent_profile: str | None = None
    box: str | None = None


@dataclass(frozen=True)
class HandoverSpec:
    audience: str = "next"
    extra: tuple[str, ...] = ()
    max_chars: int = 6000


@dataclass(frozen=True)
class Step:
    id: str
    kind: str                                  # agent | command | gate | merge
    worktree: str | None = None                # a WorktreeSpec.name
    write_scope: tuple[str, ...] = ()                 # glob patterns, repo-relative
    depends_on: tuple[str, ...] = ()           # step ids in earlier phases
    gate: GateSpec | None = None
    agent: AgentSpec | None = None
    command: str | None = None                 # kind == "command"
    shell: str = "sh"                          # "sh" (Git Bash) or "cmd"
    merge_branch: str | None = None            # kind == "merge": branch to merge
    merge_message: str | None = None
    execution_timeout_s: int = 5400
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    schema: Mapping[str, Any] | None = None
    pool: str | None = None                    # reserved, unused in v1
    note: str | None = None                    # one line, shown in the board
    # `CliAgentRuntime` kills an agent whose event stream is silent this long,
    # on every harness executor that has the stall capability. None sets no deadline, and
    # the fingerprint leaves the field out.
    stall_timeout_s: int | None = None
    # One line, at most OBJECTIVE_MAX characters: what this step is for, in the
    # words a person watching the run dashboard reads on the agent's card.
    #
    # Display data only. `fingerprint_input` names its fields one by one and
    # does not name this one, and `render_position` does not render it, so a
    # workflow that adds or edits an objective keeps every cached step cached.
    objective: str | None = None
    consumes: tuple[str, ...] = ()
    handover: HandoverSpec | None = None
    unit: str | None = None


@dataclass(frozen=True)
class Contracts:
    path: Path
    text: str

    @classmethod
    def read(cls, path: str | Path) -> "Contracts":
        p = Path(str(path))
        try:
            return cls(path=p, text=p.read_text(encoding="utf-8"))
        except OSError as e:
            raise WorkflowError(f"contracts file unreadable: {p}: {e}") from None


@dataclass(frozen=True)
class UnitPath:
    name: str
    description: str = ""


@dataclass(frozen=True)
class Unit:
    id: str
    path: str
    size: float = 1


#: The longest `Step.objective` a card shows on one line.
OBJECTIVE_MAX = 120


def objective_warnings(workflow: "Workflow") -> list[str]:
    """One line per agent step that states no `objective`.

    A warning and not a refusal: the dashboard falls back to `Step.note` and
    then to the first plain sentence of the brief, and a workflow written before
    the field existed must still run. `ohflow validate` prints these.
    """
    out: list[str] = []
    for pi, phase, si, step in workflow.steps():
        if step.kind != "agent" or (step.objective or "").strip():
            continue
        where = f"{pi:02d}.{phase.slug}/{si:02d}.{step.id}"
        fallback = ("its note" if (step.note or "").strip()
                    else "the first plain sentence of its brief")
        out.append(f"{where}: agent step has no objective; the run dashboard "
                   f"shows {fallback} instead")
    return out


def default_command_time_cap(execution_timeout_s: int) -> int:
    """Keep a monotonic reserve inside an agent's execution timeout.

    The original two-tier proposal reserved two minutes immediately above a
    120-second execution timeout, making the cap fall from 108 seconds to 1. Holding the
    short-timeout cap at 108 until the long-timeout formula catches up is the
    smallest monotonic correction. It preserves the plan's 120-second reserve
    for legitimate long tasks and its ten-percent exception for short faults.
    """
    wall = int(execution_timeout_s)
    proportional = max(1, math.ceil(wall * 0.10))
    if wall <= 120:
        return max(1, wall - proportional)
    return max(108, wall - max(120, proportional))


def effective_command_time_cap(execution_timeout_s: int,
                          requested: int | None) -> int:
    """Resolve a defensive runtime cap after workflow validation."""
    default = default_command_time_cap(execution_timeout_s)
    return default if requested is None else min(int(requested), default)


@dataclass(frozen=True)
class Phase:
    name: str
    steps: tuple[Step, ...]
    on_step_failure: str = "quarantine"
    min_success: Any = "all"                   # "all" | "any" | int
    max_parallel: int | None = None            # None means the workflow default
    slug_override: str | None = None

    @property
    def slug(self) -> str:
        return self.slug_override or slug(self.name)


@dataclass(frozen=True)
class Workflow:
    name: str
    repo: Path | None = None
    phases: tuple[Phase, ...] = ()
    worktrees: tuple[WorktreeSpec, ...] = ()
    args: Mapping[str, Any] = field(default_factory=dict)
    max_parallel: int = 3
    base_branch: str = "main"
    baseline_cmd: str | None = None            # preflight: must exit 0 at base
    # Seconds to wait after a transient step failure before the next step in the
    # same phase starts. Doubles per further transient hit, capped at ten times
    # this value. 0 disables the wait and keeps the no-cascade behaviour.
    transient_backoff_s: int = 60
    # How many times a phase that settled `deferred` may re-run its deferred
    # steps by itself, after the cooldown. 0 is the behaviour a workflow has today:
    # the run pauses and a human runs `--resume`. Each auto-resume pass is counted in the
    # run log and never refreshes, and the two-failure exclusion stops it
    # whatever this number says.
    auto_resume: int = 0
    token_budget: int | None = None
    token_reserve: int | None = None
    paths: tuple[UnitPath, ...] = ()
    units: tuple[Unit, ...] = ()
    contracts: Contracts | None = None
    workspaces: tuple[Workspace, ...] = ()

    def __post_init__(self) -> None:
        """A workflow that declares `workspaces` leaves `repo` unset; `repo`
        and `base_branch` then read as the first workspace's."""
        first = self.workspaces[0] if self.workspaces else None
        if isinstance(first, Workspace) and self.repo is None:
            object.__setattr__(self, "repo", Path(first.path))
            object.__setattr__(self, "base_branch", first.base_branch)

    def all_workspaces(self) -> tuple[Workspace, ...]:
        """Every workspace, the default one first. `repo`, `base_branch` and
        `baseline_cmd` alone declare one workspace named after the folder."""
        if self.workspaces:
            return tuple(self.workspaces)
        if self.repo is None:
            return ()
        return (Workspace(name=Path(self.repo).name or "repo",
                          path=Path(self.repo), base_branch=self.base_branch,
                          baseline_cmd=self.baseline_cmd),)

    def workspace(self, name: str | None = None) -> Workspace:
        """The workspace `name`. None is the default workspace, the first one,
        where a step with no worktree runs."""
        every = self.all_workspaces()
        if name is None:
            if every:
                return every[0]
            raise KeyError(f"workflow {self.name!r} names no workspace")
        for w in every:
            if w.name == name:
                return w
        raise KeyError(f"no workspace named {name!r} in workflow {self.name!r}")

    def workspace_of(self, worktree: str | None) -> Workspace:
        """The workspace a worktree sits in, by the worktree's name."""
        if worktree is None:
            return self.workspace()
        return self.workspace(self.worktree(worktree).workspace)

    def worktree(self, name: str) -> WorktreeSpec:
        for w in self.worktrees:
            if w.name == name:
                return w
        raise KeyError(f"no worktree named {name!r} in workflow {self.name!r}")

    def steps(self):
        """Yield (phase_index, phase, step_index, step), both indexes 1-based."""
        for pi, phase in enumerate(self.phases, start=1):
            for si, step in enumerate(phase.steps, start=1):
                yield pi, phase, si, step

    def step_by_id(self, step_id: str):
        for pi, phase, si, step in self.steps():
            if step.id == step_id:
                return pi, phase, si, step
        raise KeyError(f"no step {step_id!r} in workflow {self.name!r}")

    def steps_consuming(self, step_id: str) -> list[Step]:
        return [s for _, _, _, s in self.steps() if step_id in s.consumes]


# ------------------------------------------------------------------ validate


def normalize_handovers(workflow: Workflow) -> Workflow:
    """Resolve inferred producer contracts and their gates idempotently."""
    from .handover import questions
    consumed = {sid for _, _, _, s in workflow.steps() for sid in s.consumes}
    phases = []
    for phase in workflow.phases:
        steps = []
        for step in phase.steps:
            spec = step.handover or (HandoverSpec() if step.id in consumed and step.kind == "agent" else None)
            if spec is not None:
                check = CheckSpec("handover_written", {
                    "headings": [h for h, _ in questions(spec)], "max_chars": spec.max_chars})
                checks = tuple(c for c in (step.gate.checks if step.gate else ()) if c.name != "handover_written")
                step = replace(step, handover=spec, gate=GateSpec(checks + (check,)))
            steps.append(step)
        phases.append(replace(phase, steps=tuple(steps)))
    return replace(workflow, phases=tuple(phases))


def _overlaps(a: Sequence[str], b: Sequence[str]) -> list[str]:
    """Two write scopes overlap when either pattern matches the other as a
    glob, or the two patterns are equal."""
    hits = []
    for x in a:
        for y in b:
            if x == y or fnmatch.fnmatch(x, y) or fnmatch.fnmatch(y, x):
                hits.append(f"{x} ~ {y}")
    return hits


def _model_param_errors(where: str, model: ModelConfig) -> list[str]:
    """Shape faults in `ModelConfig.params` and `ModelConfig.extra_body`.

    Each harness executor's `agent_errors` checks the keys it accepts.
    """
    errs: list[str] = []
    for name, value in (("params", model.params), ("extra_body", model.extra_body)):
        if value is None:
            continue
        if not isinstance(value, Mapping):
            errs.append(f"{where}: model {name} must be a mapping, "
                        f"got {type(value).__name__}")
            continue
        for key in value:
            if not isinstance(key, str):
                errs.append(f"{where}: model {name} key {key!r} is not a string")
    return errs


def mcp_glob_regex(pattern: str) -> str:
    """Translate an MCP tool glob without letting ``*`` cross a dot.

    ``*`` and ``?`` stay inside one ``server.tool`` segment, while ``**`` may
    cross the separator.
    """
    out: list[str] = []
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "*":
            if index + 1 < len(pattern) and pattern[index + 1] == "*":
                out.append(".*")
                index += 2
                continue
            out.append("[^.]*")
        elif char == "?":
            out.append("[^.]")
        else:
            out.append(re.escape(char))
        index += 1
    return "^" + "".join(out) + "$"


def mcp_matches_glob(pattern: str, address: str) -> bool:
    """Return whether one ``server.tool`` address matches one MCP tool glob."""
    return re.fullmatch(mcp_glob_regex(pattern)[1:-1], address) is not None


def _mcp_tool_policy_errors(where: str, agent: AgentSpec) -> list[str]:
    errs: list[str] = []
    config = agent.mcp_config
    if config is not None:
        if not isinstance(config, Mapping):
            errs.append(f"{where}: mcp_config must be a flat {{name: server}} mapping")
        else:
            for name, server in config.items():
                if not isinstance(name, str) or not isinstance(server, Mapping):
                    errs.append(f"{where}: mcp_config must be a flat {{name: server}} mapping")
                    continue
                if not server.get("command") and not server.get("url"):
                    errs.append(
                        f"{where}: mcp_config server {name!r} needs command or url; "
                        "the shape is a flat {name: server} mapping")

    tool_policy = agent.tools
    if tool_policy.allow:
        configured = set(config or {}) if isinstance(config, Mapping) else set()
        if agent.harness_executor in HARNESS_EXECUTORS:
            configured |= harness_executor_info(agent.harness_executor).mcp_servers
        for item in tool_policy.allow:
            if not isinstance(item, str) or "." not in item:
                errs.append(f"{where}: tools.allow entry {item!r} must be server.tool")
                continue
            server, tool = item.split(".", 1)
            if not server or not tool:
                errs.append(f"{where}: tools.allow entry {item!r} must be server.tool")
            elif server not in configured:
                errs.append(f"{where}: tools.allow names unconfigured server {server!r}")
    for item in tool_policy.block:
        if not isinstance(item, str) or "." not in item:
            errs.append(f"{where}: tools.block entry {item!r} must be a server.tool glob")
    return errs


def _positive_int_error(where: str, field: str, value: Any,
                        *, minimum: int = 1, allow_none: bool = False) -> str | None:
    """One message for every numeric knob, or None when the value is sound.

    `bool` is rejected explicitly. `isinstance(True, int)` is true in Python, so
    a workflow that wrote `max_parallel=True` would otherwise run at a limit of one
    and never be told.
    """
    if value is None:
        if allow_none:
            return None
        return f"{where}: {field} may not be None"
    if isinstance(value, bool):
        return (f"{where}: {field} must be an integer, got the boolean "
                f"{value!r}")
    if not isinstance(value, int):
        return (f"{where}: {field} must be an integer, got "
                f"{type(value).__name__} {value!r}")
    if value < minimum:
        return f"{where}: {field} must be at least {minimum}, got {value}"
    return None


#: The two tokens in `RetryPolicy.on` that are not a gate check name.
RETRY_BARE_TOKENS = frozenset({"timeout", "agent_error"})


def _retry_errors(where: str, step: Step,
                  known_checks: frozenset[str]) -> list[str]:
    """Faults in a step's `RetryPolicy`, in the words the author must fix."""
    errs: list[str] = []
    if not isinstance(step.retry.carry_context, bool):
        errs.append(
            f"{where}: retry.carry_context must be a boolean, got "
            f"{type(step.retry.carry_context).__name__} "
            f"{step.retry.carry_context!r}")
    err = _positive_int_error(where, "retry.max", step.retry.max, minimum=0)
    if err:
        errs.append(err)
        return errs

    for token in step.retry.on:
        if token in RETRY_BARE_TOKENS:
            continue
        if token.startswith("gate:"):
            name = token[len("gate:"):]
            if name not in known_checks:
                errs.append(
                    f"{where}: retry.on names unknown check {name!r}; "
                    f"known: {', '.join(sorted(known_checks))}")
            continue
        errs.append(
            f"{where}: retry.on token {token!r} is not understood; use "
            f"{sorted(RETRY_BARE_TOKENS)} or 'gate:<check name>'")

    if step.retry.max > 0:
        if step.kind != "agent":
            # A command, a merge and a bare gate are deterministic, which is
            # why `failure.classify` calls their failures structural without
            # reading any text. Repeating a merge that already conflicted and
            # restored gives that same conflict.
            errs.append(
                f"{where}: retry.max is {step.retry.max} on a {step.kind!r} "
                f"step. Only an agent step retries; a {step.kind!r} step is "
                f"deterministic and repeating it gives the same answer.")
        if not step.retry.on:
            errs.append(
                f"{where}: retry.max is {step.retry.max} with an empty "
                f"retry.on, so the budget can never be spent. Name the "
                f"failures worth repeating, or set retry.max to 0.")
    return errs


def validate(workflow: Workflow, *, known_checks: frozenset[str] | None = None) -> Workflow:
    """Raise WorkflowError listing every fault found. Each message names the step
    ids at fault, because those are what the author must go and edit."""
    from . import gates
    if known_checks is None:
        known_checks = frozenset(gates.REGISTRY)

    errs: list[str] = []
    seen: dict[str, str] = {}          # step id -> where it was first seen
    phase_of: dict[str, int] = {}

    if not workflow.phases:
        errs.append("workflow has no phases")
    errs.extend(_workspace_errors(workflow))
    home = _workspace_names(workflow)

    for pi, phase, si, step in workflow.steps():
        where = f"{pi:02d}.{phase.slug}/{si:02d}.{step.id}"
        if step.id in seen:
            errs.append(f"duplicate step id {step.id!r}: {seen[step.id]} and {where}")
        seen[step.id] = where
        phase_of.setdefault(step.id, pi)

        if step.kind not in STEP_KINDS:
            errs.append(f"{where}: unknown step kind {step.kind!r}")
        if step.kind == "agent" and step.agent is None:
            errs.append(f"{where}: kind 'agent' with no agent spec")
        if step.kind == "command" and not step.command:
            errs.append(f"{where}: kind 'command' with no command")
        if step.kind == "merge" and not step.merge_branch:
            errs.append(f"{where}: kind 'merge' with no merge_branch")
        if step.agent is not None and step.agent.harness_executor is None:
            errs.append(f"{where}: agent names no harness_executor; set one of "
                        f"{sorted(HARNESS_EXECUTORS)}")
        elif step.agent is not None and step.agent.harness_executor not in HARNESS_EXECUTORS:
            errs.append(f"{where}: unknown harness executor {step.agent.harness_executor!r}")
        elif step.agent is not None:
            errs.extend(_model_param_errors(where, step.agent.model))
            errs.extend(_mcp_tool_policy_errors(where, step.agent))
            command_err = _positive_int_error(
                where, "agent.command_time_cap_s", step.agent.command_time_cap_s,
                minimum=1, allow_none=True)
            if command_err:
                errs.append(command_err)
            elif (step.agent.command_time_cap_s is not None and
                  step.agent.command_time_cap_s > default_command_time_cap(step.execution_timeout_s)):
                errs.append(
                    f"{where}: agent.command_time_cap_s is "
                    f"{step.agent.command_time_cap_s}, above the default effective cap "
                    f"{default_command_time_cap(step.execution_timeout_s)} for "
                    f"execution_timeout_s={step.execution_timeout_s}")
            info = harness_executor_info(step.agent.harness_executor)
            try:
                resolved = tiers.resolve(step.agent)
            except settings.SettingsError as error:
                errs.append(f"{where}: {error}")
            else:
                errs.extend(harness_executor_module(info.name).agent_errors(where, resolved))
            if step.stall_timeout_s is not None and not info.has(CAP_STALL):
                errs.append(f"{where}: stall_timeout_s is supported only by "
                            f"harness executors {harness_executors_with(CAP_STALL)}")
            if step.retry.carry_context and not info.has(CAP_CARRY):
                errs.append(f"{where}: retry.carry_context is supported only by "
                            f"harness executors {harness_executors_with(CAP_CARRY)}")
            if step.agent.agent_profile is not None and not info.has(CAP_AGENT_PROFILE):
                errs.append(f"{where}: agent.agent_profile is supported only by harness executors "
                            f"{harness_executors_with(CAP_AGENT_PROFILE)}")
            if step.agent.box is not None and not info.has(CAP_BOX):
                errs.append(f"{where}: agent.box is supported only by harness executors "
                            f"{harness_executors_with(CAP_BOX)}")
        if step.shell not in ("sh", "cmd"):
            errs.append(f"{where}: unknown shell {step.shell!r}")
        if step.execution_timeout_s <= 0:
            errs.append(f"{where}: execution_timeout_s must be positive")
        err = _positive_int_error(where, "stall_timeout_s", step.stall_timeout_s,
                                  minimum=1, allow_none=True)
        if err:
            errs.append(err)
        if step.objective is not None:
            if not isinstance(step.objective, str):
                errs.append(f"{where}: objective must be a string, got "
                            f"{type(step.objective).__name__}")
            elif "\n" in step.objective or "\r" in step.objective:
                errs.append(f"{where}: objective must be one line; the "
                            f"dashboard card shows it on one line")
            elif len(step.objective) > OBJECTIVE_MAX:
                errs.append(f"{where}: objective is {len(step.objective)} "
                            f"characters, above the {OBJECTIVE_MAX} a card "
                            f"shows; put the detail in the brief")

        if step.worktree is not None:
            try:
                workflow.worktree(step.worktree)
            except KeyError:
                errs.append(f"{where}: undeclared worktree {step.worktree!r}")

        if step.gate is not None:
            for check in step.gate.checks:
                if check.name not in known_checks:
                    errs.append(
                        f"{where}: gate names unknown check {check.name!r}; "
                        f"known: {', '.join(sorted(known_checks))}"
                    )
                    continue
                errs.extend(f"{where}: gate {err}"
                            for err in gates.argument_errors(check.name, check.args))
        bad = set(step.retry.on) & FORBIDDEN_RETRY_ON
        if bad:
            errs.append(
                f"{where}: retry.on may never list {sorted(bad)} - those two "
                "failures mean the agent did the wrong thing"
            )
        errs.extend(_retry_errors(where, step, known_checks))

    # dependencies must sit in a strictly earlier phase
    for pi, phase, si, step in workflow.steps():
        where = f"{pi:02d}.{phase.slug}/{si:02d}.{step.id}"
        if step.consumes and step.kind != "agent":
            errs.append(f"{where}: only an agent step consumes handovers")
        if len(set(step.consumes)) != len(step.consumes):
            errs.append(f"{where}: consumes contains duplicate step ids")
        for sid in step.consumes:
            if sid not in phase_of:
                errs.append(f"{where}: consumes names unknown step {sid!r}")
            elif workflow.step_by_id(sid)[3].kind != "agent":
                errs.append(f"{where}: consumes {sid!r}, which is not an agent step")
            if sid not in step.depends_on:
                errs.append(f"{where}: consumes {sid!r}, so it must also depend on it")
        if step.handover is not None:
            from .handover import AUDIENCES, CORE
            spec = step.handover
            if step.kind != "agent":
                errs.append(f"{where}: only an agent step writes a handover")
            if not isinstance(spec, HandoverSpec):
                errs.append(f"{where}: handover must be HandoverSpec")
            else:
                if spec.audience not in AUDIENCES:
                    errs.append(f"{where}: unknown handover audience {spec.audience!r}")
                err = _positive_int_error(where, "handover.max_chars", spec.max_chars)
                if err:
                    errs.append(err)
                existing = {h for h, _ in CORE + AUDIENCES.get(spec.audience, ())}
                if any(not isinstance(h, str) or not h.strip() or h != h.strip() or "\n" in h or "\r" in h or h in existing for h in spec.extra) or len(set(spec.extra)) != len(spec.extra):
                    errs.append(f"{where}: handover.extra headings must be nonempty, single-line and unique")
        for dep in step.depends_on:
            if dep not in phase_of:
                errs.append(f"{where}: depends_on names unknown step {dep!r}")
            elif phase_of[dep] >= pi:
                errs.append(
                    f"{where}: depends_on {dep!r} sits in phase {phase_of[dep]}, "
                    f"which is not earlier than phase {pi}"
                )

    # two steps in one phase may not own overlapping paths of one workspace
    for pi, phase in enumerate(workflow.phases, start=1):
        for i in range(len(phase.steps)):
            for j in range(i + 1, len(phase.steps)):
                a, b = phase.steps[i], phase.steps[j]
                if home.get(a.worktree) != home.get(b.worktree):
                    continue
                hits = _overlaps(a.write_scope, b.write_scope)
                if hits:
                    errs.append(
                        f"phase {pi:02d}.{phase.slug}: steps {a.id!r} and {b.id!r} "
                        f"both own {', '.join(hits)}"
                    )

    # a worktree may not be used before the phase that builds its base branch
    first_use: dict[str, int] = {}
    for pi, phase, si, step in workflow.steps():
        if step.worktree and step.worktree not in first_use:
            first_use[step.worktree] = pi
    branch_owner = {(home.get(w.name), w.branch): w.name
                    for w in workflow.worktrees}
    for w in workflow.worktrees:
        if w.node_modules_mode not in NODE_MODULES_MODES:
            errs.append(f"worktree {w.name!r}: unknown node_modules_mode "
                        f"{w.node_modules_mode!r}")
        if w.node_modules_mode == "install" and not w.install_cmd:
            errs.append(f"worktree {w.name!r}: mode 'install' needs install_cmd")
        if w.base_sha_mode not in BASE_SHA_MODES:
            errs.append(f"worktree {w.name!r}: unknown base_sha_mode "
                        f"{w.base_sha_mode!r}; use one of "
                        f"{sorted(BASE_SHA_MODES)}")
        if w.name not in first_use:
            continue
        producer = branch_owner.get((home.get(w.name), w.base))
        if producer and producer != w.name and producer in first_use:
            if first_use[w.name] <= first_use[producer]:
                errs.append(
                    f"worktree {w.name!r} is used in phase {first_use[w.name]} but "
                    f"its base branch {w.base!r} belongs to worktree {producer!r}, "
                    f"first used in phase {first_use[producer]}"
                )

    for field_name, value, minimum in (
            ("max_parallel", workflow.max_parallel, 1),
            ("transient_backoff_s", workflow.transient_backoff_s, 0),
            ("auto_resume", workflow.auto_resume, 0),
    ):
        err = _positive_int_error("workflow", field_name, value, minimum=minimum)
        if err:
            errs.append(err)
    for field_name in ("token_budget", "token_reserve"):
        err = _positive_int_error("workflow", field_name,
                                  getattr(workflow, field_name), minimum=1,
                                  allow_none=True)
        if err:
            errs.append(err)
    if workflow.token_reserve is not None and workflow.token_budget is None:
        errs.append("workflow: token_reserve needs a token_budget")
    elif (isinstance(workflow.token_reserve, int)
          and isinstance(workflow.token_budget, int)
          and not isinstance(workflow.token_reserve, bool)
          and not isinstance(workflow.token_budget, bool)
          and workflow.token_reserve > workflow.token_budget):
        errs.append(f"workflow: token_reserve {workflow.token_reserve} is larger "
                    f"than token_budget {workflow.token_budget}")

    for phase in workflow.phases:
        if phase.on_step_failure not in FAILURE_POLICIES:
            errs.append(f"phase {phase.name!r}: unknown on_step_failure "
                        f"{phase.on_step_failure!r}")
        ms = phase.min_success
        if not (ms in ("all", "any") or isinstance(ms, int)) or isinstance(ms, bool):
            errs.append(f"phase {phase.name!r}: min_success must be 'all', 'any' "
                        f"or an integer, got {ms!r}")
        err = _positive_int_error(f"phase {phase.name!r}", "max_parallel",
                                  phase.max_parallel, minimum=1, allow_none=True)
        if err:
            errs.append(err)

    errs.extend(_unit_errors(workflow))

    if errs:
        raise WorkflowError("\n".join(errs), errs)
    return normalize_handovers(workflow)


def _workspace_names(workflow: Workflow) -> dict[str | None, str | None]:
    """Worktree name -> the name of its workspace. The key None is a step with
    no worktree, which runs in the default workspace."""
    every = workflow.all_workspaces()
    default = every[0].name if every else None
    home: dict[str | None, str | None] = {None: default}
    for w in workflow.worktrees:
        home[w.name] = w.workspace if w.workspace is not None else default
    return home


def carried_by_git(agent: AgentSpec) -> bool:
    """Whether a step's commits travel to another machine and back by git."""
    if agent.harness_executor in ("pi-cloud", "claude-cloud", "codex-cloud"):
        return True
    if agent.harness_executor == "durable":
        return (agent.box or settings.get("durable.box", "local")) != "local"
    return False


def _workspace_errors(workflow: Workflow) -> list[str]:
    errs: list[str] = []
    declared = workflow.workspaces
    if not all(isinstance(w, Workspace) for w in declared):
        return ["workflow: workspaces must hold Workspace records"]
    if not declared and workflow.repo is None:
        return ["workflow names no workspace: set repo=, or workspaces= for "
                "more than one"]
    if declared and Path(workflow.repo) != Path(declared[0].path):
        errs.append("workflow sets both repo= and workspaces=; declare the "
                    "repository as a Workspace and leave repo= unset")
    if declared and workflow.baseline_cmd:
        errs.append("workflow sets baseline_cmd beside workspaces=; put the "
                    "command on the Workspace it runs in")
    every = workflow.all_workspaces()
    names: set[str] = set()
    paths: dict[str, str] = {}
    for w in every:
        if not isinstance(w.name, str) or not w.name.strip():
            errs.append(f"workspace {w.name!r}: a workspace needs a nonempty name")
            continue
        if w.name in names:
            errs.append(f"workspace {w.name!r} is declared twice")
        names.add(w.name)
        key = os.path.normcase(str(Path(w.path).resolve()))
        if paths.get(key, w.name) != w.name:
            errs.append(f"workspaces {paths[key]!r} and {w.name!r} name one "
                        f"path, {Path(w.path)}")
        paths.setdefault(key, w.name)
        if not isinstance(w.base_branch, str) or not w.base_branch.strip():
            errs.append(f"workspace {w.name!r}: base_branch may not be empty")
    for wt in workflow.worktrees:
        if wt.workspace is None:
            if len(every) > 1:
                errs.append(f"worktree {wt.name!r} names no workspace; the "
                            f"workflow has {len(every)}: "
                            f"{', '.join(w.name for w in every)}")
            continue
        if wt.workspace not in names:
            errs.append(f"worktree {wt.name!r}: undeclared workspace "
                        f"{wt.workspace!r}")
            continue
        if (workflow.workspace(wt.workspace).owned
                and wt.node_modules_mode != "none"):
            errs.append(f"worktree {wt.name!r}: workspace {wt.workspace!r} is "
                        f"owned by ohflow and holds no node_modules; set "
                        f"node_modules_mode='none'")
    home = _workspace_names(workflow)
    branches: dict[str, set[str | None]] = {}
    for wt in workflow.worktrees:
        branches.setdefault(wt.branch, set()).add(home.get(wt.name))
    known = {wt.name for wt in workflow.worktrees}
    for pi, phase, si, step in workflow.steps():
        if step.worktree is not None and step.worktree not in known:
            continue
        where = f"{pi:02d}.{phase.slug}/{si:02d}.{step.id}"
        mine = home.get(step.worktree)
        if step.kind == "merge" and step.merge_branch in branches \
                and mine not in branches[step.merge_branch]:
            other = ", ".join(sorted(str(n) for n in branches[step.merge_branch]))
            errs.append(f"{where}: merges branch {step.merge_branch!r} of "
                        f"workspace {other} into workspace {mine}; a branch "
                        f"merges only inside its own workspace")
        if step.agent is None or mine not in names:
            continue
        space = workflow.workspace(mine)
        if space.owned and not space.remote and carried_by_git(step.agent):
            errs.append(f"{where}: runs on another machine and writes in "
                        f"workspace {mine!r}, which ohflow owns and which has "
                        f"no remote; give the Workspace a remote, or run the "
                        f"step on a local harness executor")
    return errs


def _unit_errors(workflow: Workflow) -> list[str]:
    errs: list[str] = []
    path_names: set[str] = set()
    for path in workflow.paths:
        name = path.name if isinstance(path, UnitPath) else None
        if not isinstance(name, str) or not name.strip():
            errs.append(f"path {path!r}: a path needs a nonempty name")
            continue
        if name in path_names:
            errs.append(f"path {name!r} is declared twice")
        path_names.add(name)
    unit_ids: set[str] = set()
    for unit in workflow.units:
        if not isinstance(unit, Unit) or not isinstance(unit.id, str) \
                or not unit.id.strip():
            errs.append(f"unit {unit!r}: a unit needs a nonempty id")
            continue
        if unit.id in unit_ids:
            errs.append(f"unit {unit.id!r} is declared twice")
        unit_ids.add(unit.id)
        if unit.path not in path_names:
            errs.append(f"unit {unit.id!r}: path {unit.path!r} is not declared "
                        f"in Workflow.paths")
        if isinstance(unit.size, bool) or not isinstance(unit.size, (int, float)) \
                or not unit.size > 0:
            errs.append(f"unit {unit.id!r}: size must be a positive number, got "
                        f"{unit.size!r}")
    used: set[str] = set()
    for pi, phase, si, step in workflow.steps():
        if step.unit is None:
            continue
        where = f"{pi:02d}.{phase.slug}/{si:02d}.{step.id}"
        if step.unit not in unit_ids:
            errs.append(f"{where}: unit {step.unit!r} is not declared in "
                        f"Workflow.units")
        used.add(step.unit)
    for unit in workflow.units:
        if isinstance(unit, Unit) and unit.id in unit_ids and unit.id not in used:
            errs.append(f"unit {unit.id!r} has no step; set Step.unit="
                        f"{unit.id!r} on the steps that do its work")
    return errs


# ------------------------------------------------------------------- loading


def load_workflow(module_path: str | Path, args: Mapping[str, Any]) -> Workflow:
    """Import a workflow module by file path or dotted name and call `build(args)`."""
    p = Path(str(module_path))
    if p.suffix == ".py" and p.exists():
        spec = importlib.util.spec_from_file_location(f"ohflow_workflow_{p.stem}", p)
        if spec is None or spec.loader is None:
            raise WorkflowError(f"cannot import workflow module at {p}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    else:
        mod = importlib.import_module(str(module_path))
    if not hasattr(mod, "build"):
        raise WorkflowError(f"workflow module {module_path} exports no build(args) -> Workflow")
    workflow = mod.build(WorkflowArgs(args))
    if not isinstance(workflow, Workflow):
        raise WorkflowError(f"workflow module {module_path} build() returned {type(workflow)}")
    if args.get("contracts") and workflow.contracts is None:
        workflow = replace(workflow, contracts=Contracts.read(args["contracts"]))
    return workflow


# ------------------------------------------------------------- serialisation


_RECORD_TYPES = {cls.__name__: cls for cls in (
    Workflow, Phase, Step, WorktreeSpec, Workspace, GateSpec, CheckSpec, AgentSpec,
    ModelConfig, ToolPolicy, RetryPolicy, HandoverSpec, UnitPath, Unit, Contracts)}


def _from_record(cls, data: Mapping[str, Any]):
    from dataclasses import fields

    kwargs = {}
    for f in fields(cls):
        if f.name in data:
            kwargs[f.name] = _coerce(str(f.type), data[f.name])
    return cls(**kwargs)


def _coerce(hint: str, value: Any) -> Any:
    hint = hint.replace(" | None", "").strip()
    if value is None:
        return None
    if hint.startswith("tuple["):
        inner = hint[len("tuple["):].split(",", 1)[0].strip()
        items = list(value) if isinstance(value, (list, tuple)) else [value]
        if inner in _RECORD_TYPES:
            return tuple(_from_record(_RECORD_TYPES[inner], v)
                         for v in items if isinstance(v, Mapping))
        return tuple(items)
    if hint == "Path":
        return Path(value)
    if hint in _RECORD_TYPES:
        return (_from_record(_RECORD_TYPES[hint], value)
                if isinstance(value, Mapping) else None)
    return value


def from_jsonable(data: Mapping[str, Any]) -> Workflow:
    """`workflow.json` back into the dataclasses: the inverse of `to_jsonable`.

    The dashboard needs the `Workflow` object to render a step's position
    block from the recorded file alone. A key the dataclass does not know is
    ignored and a missing one takes the dataclass default, so a record an
    older ohflow wrote still loads. Nothing is validated here.
    """
    if not isinstance(data, Mapping):
        raise WorkflowError("a workflow record is a JSON object")
    return _from_record(Workflow, data)


def to_jsonable(obj: Any) -> Any:
    """Recursive, deterministic, secret-free. Used for workflow.json and for the
    fingerprint input, so ordering must never depend on a dict's history."""
    from dataclasses import fields, is_dataclass

    if is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_jsonable(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, Mapping):
        return {str(k): to_jsonable(v)
                for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)

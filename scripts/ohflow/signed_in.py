"""Shared parts of the claude and codex runners.

These two harness executors start a signed-in harness: an agent CLI that signs in with its own login
and, by default, loads the signed-in harness's usual setup. Each harness executor is one adapter module
on `cli_harness_executor.CliAgentRuntime`; this module holds what the two share.

Two launch rules hold for both:

- The npm `.cmd` shim is resolved to its real target (`claude.exe`, or `node`
  plus a `.js` entry point). No argument passes through `cmd.exe`, so quotes,
  `&` and `%` in an argument arrive intact, and the 8191-character `cmd.exe`
  limit does not apply.
- The agent gets one short bootstrap prompt that points at `brief.md`. The
  brief itself never goes on the command line.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from . import activity as act
from . import attempt_record, proc
from .harness_executors import CAP_TOOLS_ONLY, harness_executor_info, harness_executors_with
from .proc import guard_current_process_tree


NPM_DIR = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "npm"

def signed_in_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    env = proc.agent_env()
    env["PYTHONIOENCODING"] = "utf-8"
    env.update(extra or {})
    return env


def _shim_target(shim: Path) -> list[str] | None:
    """Read the command an npm `.cmd` shim runs."""
    try:
        text = shim.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    found = re.findall(r'"%dp0%\\([^"]+\.(?:exe|js|cjs|mjs))"', text)
    if not found:
        return None
    target = shim.parent / found[-1]
    if target.suffix.lower() == ".exe":
        return [str(target)]
    node = shutil.which("node") or shutil.which("node.exe")
    return [node, str(target)] if node else None


def executable_argv(env_var: str, shim_name: str, *,
                    path_fallback: bool = False) -> list[str]:
    """The argv prefix that starts one signed-in harness's CLI.

    `env_var` overrides. A `.py` override runs under this interpreter, which
    is how the test fakes run. Otherwise the npm shim is resolved to its
    target; PATH is never searched first, because on this box the `claude`
    on PATH is a broken fnm shim. A harness executor whose CLI is not an npm shim (pi)
    sets `path_fallback` and takes the first PATH hit when no shim resolves.
    """
    override = os.environ.get(env_var)
    if override:
        if override.lower().endswith(".py"):
            return [sys.executable, override]
        if override.lower().endswith(".cmd"):
            resolved = _shim_target(Path(override))
            if resolved:
                return resolved
        return [override]
    if os.name != "nt":
        # No `.cmd` shim exists off Windows: npm, a native installer and
        # Homebrew all put an executable with the plain name on PATH.
        found = shutil.which(shim_name)
        if found:
            return [found]
        raise FileNotFoundError(
            f"{shim_name} executable not found on PATH; set {env_var}")
    shim = NPM_DIR / f"{shim_name}.cmd"
    resolved = _shim_target(shim)
    if resolved:
        return resolved
    found = shutil.which(f"{shim_name}.cmd")
    if found:
        resolved = _shim_target(Path(found))
        if resolved:
            return resolved
    if path_fallback:
        found = shutil.which(f"{shim_name}.cmd") or shutil.which(shim_name)
        if found:
            return [found]
    raise FileNotFoundError(f"{shim_name} executable not found; set {env_var}")


def is_fake(argv: list[str]) -> bool:
    return len(argv) == 2 and argv[1].lower().endswith(".py")


def run_quiet(argv: list[str], *, timeout: float = 30,
              env: Mapping[str, str] | None = None) -> subprocess.CompletedProcess:
    return proc.run_managed(argv, timeout=timeout,
                            env=dict(env) if env is not None else signed_in_env())


def version_of(argv: list[str], flag: str = "--version") -> str:
    if is_fake(argv):
        return "fake"
    try:
        out = run_quiet([*argv, flag], timeout=20).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return out.splitlines()[-1].strip() if out else "unknown"


def bootstrap_prompt(out_dir: Path) -> str:
    brief = (Path(out_dir) / "brief.md").resolve()
    return f"Your brief is at {brief}. Read it and follow it."


def read_schema(spec: Mapping[str, Any], out_dir: Path) -> dict | None:
    if not spec.get("schema_path"):
        return None
    return json.loads((Path(out_dir) / str(spec["schema_path"])).read_text(encoding="utf-8"))


def runner_main(adapter_factory: Callable[[], Any], argv: list[str] | None = None) -> int:
    """The `python -m ohflow.<harness executor>_runner spec.json` entry point."""
    from .cli_harness_executor import CliAgentRuntime

    argv = argv or sys.argv
    if len(argv) < 2:
        return 2
    spec_path = Path(argv[1]).resolve()
    try:
        guard_current_process_tree()
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        CliAgentRuntime(adapter_factory()).run(spec, spec_path.parent)
        return 0
    except Exception as exc:
        try:
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
        except Exception:
            spec = {}
        attempt_record.write(
            spec_path.parent,
            {**attempt_record.empty_record(spec, f"{type(exc).__name__}: {exc}"),
             "record_source": attempt_record.SOURCE_RUNNER})
        return 1


# ------------------------------------------------------------ agent rules

#: Shared tool policy names a hermetic agent may narrow to.
SIGNED_IN_SHARED_TOOLS = frozenset({"terminal", "file_editor", "task_tracker"})


@dataclass(frozen=True)
class SignedInRules:
    """What one signed-in harness executor accepts in an agent spec.

    A signed-in harness signs in with its own login and starts in its usual setup. A workflow
    that names tools, skills or an MCP fleet would claim a tool policy the signed-in harness does
    not control, so only the hermetic profile lets a workflow set the tool policy.
    """
    harness_executor: str
    #: Model params the harness executor turns into a flag, each with its allowed values.
    model_params: Mapping[str, frozenset] = field(default_factory=dict)
    #: `agent.agent_profile` values the harness executor accepts; None means any profile directory.
    profiles: tuple[str, ...] | None = ("hermetic",)
    #: `mcp_config` needs the hermetic profile.
    hermetic_mcp: bool = True


def signed_in_agent_errors(rules: SignedInRules, where: str, agent: Any) -> list[str]:
    harness_executor = rules.harness_executor
    errs: list[str] = []
    model = agent.model
    if not isinstance(model.model, str) or not model.model.strip():
        errs.append(f"{where}: {harness_executor} model must name a model")
    elif any(ch.isspace() for ch in model.model):
        errs.append(f"{where}: {harness_executor} model may not contain whitespace, got {model.model!r}")
    known = rules.model_params
    params = model.params if isinstance(model.params, Mapping) else {}
    for key, value in params.items():
        if key not in known:
            errs.append(f"{where}: {harness_executor} model params are closed; unsupported "
                        f"{key!r}. Known: {sorted(known)}")
        elif value not in known[key]:
            errs.append(f"{where}: {harness_executor} model param {key!r} must be one of "
                        f"{sorted(known[key])}, got {value!r}")
    if model.extra_body:
        errs.append(f"{where}: {harness_executor} refuses ModelConfig.extra_body")

    tool_policy = agent.tools
    if tool_policy.preset != "default":
        errs.append(f"{where}: {harness_executor} supports only tools.preset='default'")
    if tool_policy.enable_browser:
        errs.append(f"{where}: {harness_executor} harness executor refuses enable_browser=True")
    if tool_policy.enable_sub_agents:
        errs.append(f"{where}: {harness_executor} harness executor refuses enable_sub_agents=True")
    if tool_policy.allow or tool_policy.block:
        errs.append(f"{where}: {harness_executor} refuses tools.allow and tools.block; "
                    "MCP tool narrowing applies to pi")
    if agent.skills or agent.skills_dir:
        errs.append(f"{where}: {harness_executor} loads the signed-in harness's own skills; skills= applies to pi")

    profile = agent.agent_profile
    hermetic = profile == "hermetic"
    if profile is not None and rules.profiles is not None and profile not in rules.profiles:
        errs.append(f"{where}: {harness_executor} agent.agent_profile must be None or one of "
                    f"{list(rules.profiles)}, got {profile!r}")
    if tool_policy.only:
        if not hermetic or not harness_executor_info(harness_executor).has(CAP_TOOLS_ONLY):
            only_harness_executors = " or ".join(f"harness_executor={n!r}" for n in harness_executors_with(CAP_TOOLS_ONLY))
            errs.append(f"{where}: {harness_executor} tools.only needs {only_harness_executors} with "
                        "agent_profile='hermetic'; the usual setup brings the signed-in harness's tools")
        unknown = sorted(repr(n) for n in tool_policy.only if n not in SIGNED_IN_SHARED_TOOLS)
        if unknown:
            errs.append(f"{where}: {harness_executor} tools.only has unsupported names {unknown}; "
                        f"known: {sorted(SIGNED_IN_SHARED_TOOLS)}")
    if agent.mcp_config is not None and not (hermetic and rules.hermetic_mcp):
        errs.append(f"{where}: {harness_executor} mcp_config needs agent_profile='hermetic'; the "
                    "usual setup brings the signed-in harness's MCP fleet")
    return errs


# ---------------------------------------------------------------- activity

def signed_in_activity(attempt_dir: Path, harness_executor: str, event_log: str,
                       entry: Callable[[act.Activity, dict, float], None] | None, *,
                       now: float | None, running: bool, limit: int,
                       note: str | None = None) -> dict:
    """The signed-in harness's copy of the agent's stdout, read as live activity.

    Neither stream carries timestamps, so a line is stamped when it is read.
    The heartbeat and stderr clocks say when a quiet signed-in harness last moved. `entry`
    is None for a harness executor whose stream holds no events to parse.
    """
    attempt_dir = Path(attempt_dir)
    now = time.time() if now is None else float(now)
    model = act.model_for(attempt_dir)
    with model.lock:
        path = attempt_dir / "logs" / event_log
        lines, reset = model.tail.read(path)
        if reset:
            model.reset()
            lines, _ = model.tail.read(path)
        for raw in lines:
            model.touch(now)
            if entry is None:
                continue
            try:
                event = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(event, dict):
                entry(model, event, now)
        clocks = []
        for name in ("heartbeat.json", f"{harness_executor}-stderr.log"):
            try:
                clocks.append((attempt_dir / "logs" / name).stat().st_mtime)
            except OSError:
                pass
        if note is None and not model.replied:
            note = act.STARTING_NOTE
        return act.activity_out(model, harness_executor=harness_executor,
                                root=act.worktree_root(attempt_dir), now=now,
                                running=running, limit=limit,
                                fallback_at=max(clocks) if clocks else None,
                                note=note)


def signed_in_transcript(attempt_dir: Path, event_log: str) -> tuple[Path | None, str | None]:
    """A signed-in harness keeps its transcript as the runner's copy of the agent's stdout."""
    path = Path(attempt_dir) / "logs" / event_log
    if path.is_file():
        return path, None
    return None, f"no event log at {path}"

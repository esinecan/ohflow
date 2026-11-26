"""The agent-spawn abstraction: one protocol, one handle, and the spec record.

Each harness executor spawns one operating-system process per agent. A hung
agent is killable, and a crashed agent does not take the run with it.

Both spec and result are JSON and both are written to disk. That is what makes
resume work.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from . import tiers
from .paths import win
from .workflow import AgentSpec, to_jsonable

__all__ = ["Handle", "HarnessExecutor", "spec_json", "AgentLaunchError"]

RUNNING, FINISHED, ERROR = "running", "finished", "error"


class AgentLaunchError(RuntimeError):
    pass


@dataclass
class Handle:
    coord: str
    harness_executor: str
    out_dir: Path
    spec_path: Path
    started: float = field(default_factory=time.time)
    pid: int | None = None
    process: Any = None
    conversation_id: str | None = None
    error: str | None = None

    @property
    def elapsed(self) -> float:
        return time.time() - self.started


class HarnessExecutor(Protocol):
    name: str

    def launch(self, spec: dict, out_dir: Path) -> Handle: ...
    def poll(self, handle: Handle) -> str: ...
    def collect(self, handle: Handle) -> dict: ...
    def kill(self, handle: Handle) -> None: ...


# ----------------------------------------------------------------- spec.json


def spec_json(agent: AgentSpec, *, coord: str, workspace: Path, out_dir: Path,
              brief_path: str = "brief.md", schema: dict | None = None,
              execution_timeout_s: int = 5400, attempt: int = 1,
              write_scope: tuple[str, ...] = (), stall_timeout_s: int | None = None,
              fork_session: str | None = None) -> dict:
    """The §4.9 record. The key is named, never carried: `api_key_env` holds a
    variable name, and only the harness executor that launches the agent reads it.
    A model that names a tier is resolved through the settings here, and the
    record keeps the tier beside the model it resolved to."""
    named = agent.model.model
    agent = tiers.resolve(agent)
    return {
        "coord": coord,
        "attempt": attempt,
        "role": agent.role,
        "harness_executor": agent.harness_executor,
        "workspace": win(workspace),
        "model": {
            "model": agent.model.model,
            "base_url": agent.model.base_url,
            "api_key_env": agent.model.api_key_env,
            # Provider options as plain JSON. Neither can carry a key.
            "params": to_jsonable(agent.model.params or {}),
            "extra_body": to_jsonable(agent.model.extra_body or {}),
            **({"tier": named} if tiers.is_tier(named) else {}),
        },
        "tools": {
            "preset": agent.tools.preset,
            "enable_browser": agent.tools.enable_browser,
            "enable_sub_agents": agent.tools.enable_sub_agents,
            "only": list(agent.tools.only),
            "allow": list(agent.tools.allow),
            "block": list(agent.tools.block),
        },
        "skills": list(agent.skills),
        "skills_dir": win(agent.skills_dir) if agent.skills_dir else None,
        "mcp_config": to_jsonable(agent.mcp_config),
        "max_iterations": agent.max_iterations,
        "command_time_cap_s": agent.command_time_cap_s,
        "execution_timeout_s": execution_timeout_s,
        "stall_timeout_s": stall_timeout_s,
        "write_scope": list(write_scope),
        "fork_session": fork_session or agent.fork_session,
        "brief_path": brief_path,
        "schema_path": "schema.json" if schema else None,
        "out_dir": ".",
        # Absent at None, so a pi spec.json keeps its historic shape.
        **({"agent_profile": agent.agent_profile} if agent.agent_profile is not None else {}),
        **({"box": agent.box} if agent.box is not None else {}),
    }

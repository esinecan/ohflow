"""The harness executor registry: one row per harness executor.

Outside the harness executor modules, one other place names every harness executor: `HARNESS_EXECUTOR_FIX` in
`preflight.py`, the fix hint for a failed harness executor check.

Each harness executor owns its artifact format in one module. The registry row names that
module and the capabilities validation reads. Every other module reaches a harness executor
through `harness_executor_module(name)` and asks these questions of it:

- `agent_errors(where, agent)`: the faults in an agent spec for this harness executor.
- `usage(attempt_dir)`: the tokens this attempt recorded, as `(tokens, None)`
  or `(None, why)`, in the one vocabulary of `attempt_record.TOKEN_KEYS`.
- `activity(attempt_dir, ...)`: the live reasoning, tool calls and idle clock.
- `resume_target(prior_result, attempt_dir)`: what a retry resumes from, or
  None when the harness executor cannot resume.
- `reattach_target(attempt_dir)`: `<box>:<dir>` where a dead supervisor's
  attempt continues, or None when the directory holds nothing to reattach.
- `transcript(attempt_dir, result)`: where a human reads this attempt's transcript.
- `make_harness_executor()`: the `HarnessExecutor` object the engine launches agents through.

This module imports nothing from the rest of ohflow at import time, so
`workflow.py` can read it without a cycle.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

from . import settings

__all__ = ["HarnessExecutorInfo", "HARNESS_EXECUTOR_INFO", "HARNESS_EXECUTORS", "harness_executor_info",
           "harness_executor_module", "harness_executor_for", "harness_executors_with"]

#: The event stream feeds a stall deadline.
CAP_STALL = "stall_timeout"
#: A retry can resume the failed attempt's conversation.
CAP_CARRY = "carry_context"
#: The harness executor signs in with the signed-in harness's own login, so `api_key_env` may be empty.
CAP_SIGNED_IN = "signed_in"
#: `agent.agent_profile` selects a setup the harness executor starts in.
CAP_AGENT_PROFILE = "profile"
#: `agent.box` names the ssh machine the harness executor runs its agent on.
CAP_BOX = "box"
#: `tools.only` narrows the harness executor's built-in tools (hermetic profile only).
CAP_TOOLS_ONLY = "tools_only"
#: A dead supervisor's attempt continues where it stopped, in the same attempt
#: directory and under the same attempt number.
CAP_REATTACH = "reattach"


@dataclass(frozen=True)
class HarnessExecutorInfo:
    name: str
    #: The harness executor's own module, imported on first use.
    module: str
    caps: frozenset[str] = frozenset()
    #: The setting that lists the MCP servers the harness executor's own box
    #: serves, which `tools.allow` may name without a workflow `mcp_config`.
    mcp_setting: str | None = None

    def has(self, cap: str) -> bool:
        return cap in self.caps

    @property
    def mcp_servers(self) -> frozenset[str]:
        if self.mcp_setting is None:
            return frozenset()
        return frozenset(settings.get(self.mcp_setting, []))


HARNESS_EXECUTOR_INFO: dict[str, HarnessExecutorInfo] = {
    "pi": HarnessExecutorInfo("pi", "ohflow.pi_runner",
                              frozenset({CAP_STALL, CAP_CARRY})),
    "claude": HarnessExecutorInfo("claude", "ohflow.claude_runner",
                                  frozenset({CAP_STALL, CAP_CARRY, CAP_SIGNED_IN, CAP_AGENT_PROFILE, CAP_TOOLS_ONLY})),
    "codex": HarnessExecutorInfo("codex", "ohflow.codex_runner",
                                 frozenset({CAP_STALL, CAP_SIGNED_IN, CAP_AGENT_PROFILE})),
    "durable": HarnessExecutorInfo("durable", "ohflow.durable_runner",
                                   frozenset({CAP_STALL, CAP_BOX, CAP_REATTACH})),
    "pi-cloud": HarnessExecutorInfo("pi-cloud", "ohflow.pi_cloud_runner",
                                    frozenset({CAP_STALL, CAP_REATTACH}),
                                    "pi_cloud.mcp_servers"),
    "claude-cloud": HarnessExecutorInfo("claude-cloud", "ohflow.claude_cloud_runner",
                                        frozenset({CAP_STALL, CAP_REATTACH})),
    "codex-cloud": HarnessExecutorInfo("codex-cloud", "ohflow.codex_cloud_runner",
                                       frozenset({CAP_STALL, CAP_REATTACH})),
}

HARNESS_EXECUTORS = frozenset(HARNESS_EXECUTOR_INFO)


def harness_executor_info(name: str) -> HarnessExecutorInfo:
    try:
        return HARNESS_EXECUTOR_INFO[name]
    except KeyError:
        raise ValueError(f"unknown harness executor {name!r}") from None


def harness_executors_with(cap: str) -> list[str]:
    return sorted(n for n, i in HARNESS_EXECUTOR_INFO.items() if i.has(cap))


def harness_executor_module(name: str) -> Any:
    """Import the module that owns this harness executor's artifacts."""
    return importlib.import_module(harness_executor_info(name).module)


def harness_executor_for(name: str):
    """Build the `HarnessExecutor` object the engine talks to."""
    return harness_executor_module(name).make_harness_executor()

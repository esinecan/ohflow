"""The attempt record: the one module that knows what `result.json` holds.

Every runner, every recovery path and the engine write the record through
`write`. The keys, the empty record, the error record, the settings block and
the token vocabulary live here and nowhere else.

Token vocabulary: `prompt_tokens` already includes cache reads and cache
writes. `cache_read_tokens` and `cache_write_tokens` are parts of it, never
added again. The total is `prompt_tokens + completion_tokens`.

`record_source` says what built an agent attempt's record. `runner`: the
runner wrote it itself. `event_log`: the runner died, and the record was
rebuilt from its event log. `attempt_files`: that log gave no event, as for a
runner that died before it opened the log, and the attempt's other files were
all there was. `none`: nothing could be read. A rebuilt record says more in
`recovery` (`cli_harness_executor.recover_cli_result`).

This module imports only the standard library, so any agent child process can
load it.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

__all__ = ["TOKEN_KEYS", "zero_tokens", "token_subset", "is_count",
           "checked_tokens", "mcp_servers_of",
           "command_time_cap", "settings_record", "empty_record", "write",
           "SOURCE_RUNNER", "SOURCE_EVENT_LOG", "SOURCE_ATTEMPT_FILES",
           "SOURCE_NONE"]

#: The token fields every runner writes into `result.json`.
TOKEN_KEYS = ("prompt_tokens", "completion_tokens", "cache_read_tokens",
              "cache_write_tokens", "reasoning_tokens")


SOURCE_RUNNER = "runner"
SOURCE_EVENT_LOG = "event_log"
SOURCE_ATTEMPT_FILES = "attempt_files"
SOURCE_NONE = "none"


#: The `effective` default of `empty_record`: a harness executor that reports no settings.
NO_SETTINGS: Mapping[str, Any] = MappingProxyType({})


def zero_tokens() -> dict[str, int]:
    return {key: 0 for key in TOKEN_KEYS}


def token_subset(raw: Mapping[str, Any] | None) -> dict[str, int]:
    """Keep only `TOKEN_KEYS` from a provider's usage dict, as integers."""
    out = zero_tokens()
    for key in TOKEN_KEYS:
        value = (raw or {}).get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            out[key] = int(value)
    return out


def is_count(value: Any) -> bool:
    """Whether `value` is a token count that can be reconciled."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def checked_tokens(value: Any, where: str) -> tuple[dict[str, int] | None, str | None]:
    """The five token fields of a record, or `(None, why)` when one is wrong."""
    if not isinstance(value, dict):
        return None, f"{where}: tokens are missing or not an object"
    missing = [key for key in TOKEN_KEYS if key not in value]
    if missing:
        return None, f"{where}: tokens missing {', '.join(missing)}"
    bad = [key for key in TOKEN_KEYS if not is_count(value[key])]
    if bad:
        return None, f"{where}: token counts are malformed ({', '.join(bad)})"
    return {key: value[key] for key in TOKEN_KEYS}, None


def mcp_servers_of(tools: list[str]) -> list[str]:
    """`mcp__<server>__<tool>` names, reduced to their server names."""
    servers: list[str] = []
    for name in tools:
        parts = str(name).split("__")
        if len(parts) >= 3 and parts[0] == "mcp" and parts[1] not in servers:
            servers.append(parts[1])
    return servers


def command_time_cap(spec: Mapping[str, Any]) -> int:
    """The longest one shell command may run, for this attempt's spec."""
    from .workflow import effective_command_time_cap

    return effective_command_time_cap(int(spec.get("execution_timeout_s") or 5400),
                                 spec.get("command_time_cap_s"))


def settings_record(spec: Mapping[str, Any],
                    effective: Mapping[str, Any] | None) -> dict[str, Any]:
    """What the workflow asked for, and what the harness executor reports it got.

    `effective=None` means the harness executor never reached a state to report (an
    interrupted attempt). A mapping gains the resolved `command_time_cap_s`.
    """
    requested = {"model": dict(spec.get("model") or {}),
                 "tools": dict(spec.get("tools") or {}),
                 "mcp_servers": sorted((spec.get("mcp_config") or {}).keys()),
                 "agent_profile": spec.get("agent_profile"),
                 "command_time_cap_s": spec.get("command_time_cap_s")}
    if spec.get("box") is not None:
        requested["box"] = spec["box"]
    if effective is None:
        return {"requested": requested, "effective": None}
    return {"requested": requested,
            "effective": {**dict(effective), "command_time_cap_s": command_time_cap(spec)}}


def empty_record(spec: Mapping[str, Any], error: str, *,
                 tokens: Mapping[str, int] | None = None, cost: float = 0.0,
                 cost_source: str = "unpriced",
                 effective: Mapping[str, Any] | None = NO_SETTINGS) -> dict[str, Any]:
    """The record of an attempt that produced nothing, or the base of one that did."""
    return {"coord": spec.get("coord"), "attempt": spec.get("attempt"),
            "conversation_id": None, "transcript_dir": None,
            "execution_status": "error", "tools": [], "mcp_servers": [],
            "skills": [], "tool_calls": 0, "observation_errors": 0, "llm_calls": 0,
            "wall_seconds": 0.0,
            "tokens": dict(tokens) if tokens is not None else zero_tokens(),
            "cost": cost, "cost_source": cost_source, "final_text_path": None,
            "structured": None, "schema_error": None, "error": error,
            "settings": settings_record(spec, effective)}


def write(out_dir: Path, record: Mapping[str, Any],
          final_text: str | None = None) -> dict[str, Any]:
    """Persist `result.json`, and `final.md` when the harness executor has a final message."""
    out_dir = Path(out_dir)
    if final_text is not None:
        (out_dir / "final.md").write_text(final_text, encoding="utf-8")
    materialized = dict(record)
    (out_dir / "result.json").write_text(
        json.dumps(materialized, indent=2, default=str), encoding="utf-8")
    return materialized

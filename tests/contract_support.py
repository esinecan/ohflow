"""Shared assertions for the harness executor contract tests.

Every harness executor answers the same questions about an attempt directory. These helpers
ask them the same way, so a harness executor's test file only names its fixture and the
facts the fixture holds.
"""

from __future__ import annotations

import json
from pathlib import Path

from ohflow.attempt_record import TOKEN_KEYS

__all__ = ["recorded_result", "assert_usage_matches_result",
           "last_tool_call"]


def recorded_result(attempt: Path) -> dict:
    return json.loads((Path(attempt) / "result.json").read_text(encoding="utf-8"))


def assert_usage_matches_result(case, module, attempt: Path) -> dict:
    """The harness executor's usage equals the five token fields its `result.json` holds."""
    tokens, why = module.usage(attempt)
    case.assertIsNone(why)
    recorded = recorded_result(attempt)["tokens"]
    case.assertEqual(tokens, {key: recorded[key] for key in TOKEN_KEYS})
    return tokens


def last_tool_call(module, attempt: Path, *, now: float, running: bool = False) -> dict:
    """The newest tool call the harness executor's activity reports."""
    activity = module.activity(attempt, now=now, running=running)
    calls = activity["tool_calls"]
    assert calls, f"{module.__name__} reported no tool calls"
    return calls[0]

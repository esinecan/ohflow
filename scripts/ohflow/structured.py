"""Shared parsing for schema-bearing agent final messages.

The five harness executor runners import it. A `command` step's JSON is parsed by a
separate copy, `_fenced_json` in `engine.py`."""

from __future__ import annotations

import json
import re
from typing import Any, Mapping

FENCED_JSON = re.compile(r"```json\s*(.+?)\s*```", re.DOTALL | re.IGNORECASE)


def parse_structured(text: str, schema: Mapping[str, Any] | None, *,
                     bare_ok: bool = False) -> tuple[Any, str | None]:
    """The last fenced json block of a final message.

    `bare_ok` also accepts a final message that is one bare JSON value. The
    claude and codex harness executors pass it, because `--json-schema` and
    `--output-schema` make the CLI answer with bare JSON.
    """
    if not schema:
        return None, None
    blocks = FENCED_JSON.findall(text or "")
    if not blocks and bare_ok and (text or "").strip()[:1] in ("{", "["):
        try:
            return json.loads(text.strip()), None
        except json.JSONDecodeError as exc:
            return None, f"bare json final message did not parse: {exc}"
    if not blocks:
        return None, "no fenced json block in the final message"
    try:
        return json.loads(blocks[-1]), None
    except json.JSONDecodeError as exc:
        return None, f"fenced json block did not parse: {exc}"

"""Operator settings: the shipped base file, with the operator's local file over it.

ohflow ships `ohflow.settings.json` at the skill root. It names every setting
and holds the value a new operator starts with. An operator's own values, such
as the ssh alias of a durable box or the URL of a pi-cloud Worker, go in
`ohflow.settings.local.json` beside it. git ignores that file, so a pull never
conflicts with it. `OHFLOW_SETTINGS` names another local file; an empty value
reads the base file alone, which is how the test suite runs.

The local file is merged over the base key by key. A nested object merges the
same way; any other value, a list included, replaces the base value.

Every read opens the files again. They are a few hundred bytes, and a test or
an operator who changes one sees the change at once.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

__all__ = ["SKILL_ROOT", "BASE_FILE", "LOCAL_FILE", "SETTINGS_ENV",
           "local_file", "load", "get", "SettingsError"]

SKILL_ROOT = Path(__file__).resolve().parents[2]
BASE_FILE = SKILL_ROOT / "ohflow.settings.json"
LOCAL_FILE = SKILL_ROOT / "ohflow.settings.local.json"
SETTINGS_ENV = "OHFLOW_SETTINGS"


class SettingsError(ValueError):
    """A settings file is not a JSON object, or a setting holds a value its
    reader cannot use."""


def local_file() -> Path | None:
    """The operator's local file: `OHFLOW_SETTINGS`, else the default path.
    None when `OHFLOW_SETTINGS` is set and empty."""
    if SETTINGS_ENV in os.environ:
        raw = os.environ[SETTINGS_ENV].strip()
        return Path(raw) if raw else None
    return LOCAL_FILE


def _read(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SettingsError(f"{path}: {error}") from None
    if not isinstance(data, dict):
        raise SettingsError(f"{path}: the file must hold one JSON object")
    return data


def _merge(base: Mapping[str, Any], over: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in over.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load() -> dict[str, Any]:
    """The merged settings."""
    merged = _read(BASE_FILE)
    local = local_file()
    if local is not None and local.is_file():
        merged = _merge(merged, _read(local))
    return merged


def get(dotted: str, default: Any = None) -> Any:
    """One setting by its dotted name, such as `durable.box`."""
    value: Any = load()
    for part in dotted.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return default
        value = value[part]
    return default if value is None else value

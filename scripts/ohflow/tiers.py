"""Model tiers: a step names `heavy` or `light`, and the operator settings name the model.

A workflow, a skill or a reference names the rung of the inference ladder a
step needs, and never a model. `tiers.<tier>.<harness executor>` in the
operator settings holds the model that tier runs on that harness executor,
such as the alias the Claude CLI takes or the `provider/id` pi takes. The
shipped base file maps both tiers for every harness executor, and the
operator's local file overrides any of them.

`resolve` turns an agent spec whose model names a tier into one that names the
model. Validation checks the resolved spec, and the spec a harness executor
launches carries the resolved model with the tier beside it. An explicit model
id passes through untouched, so a workflow that names one keeps working.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from . import settings

__all__ = ["TIERS", "is_tier", "model_for", "resolve", "label"]

TIERS = ("heavy", "light")


def is_tier(name: Any) -> bool:
    return isinstance(name, str) and name in TIERS


def model_for(tier: str, harness_executor: str) -> str:
    """The model `tier` runs on `harness_executor`, from the settings.

    An unmapped tier, or a value that is not one model name, raises
    `SettingsError` naming the setting to correct."""
    key = f"tiers.{tier}.{harness_executor}"
    value = settings.get(key)
    if not isinstance(value, str) or not value.strip() or any(ch.isspace() for ch in value):
        raise settings.SettingsError(
            f"the setting {key} must name the model the {tier} tier runs on "
            f"{harness_executor}, got {value!r}; set it in the operator settings")
    return value


def resolve(agent: Any) -> Any:
    """`agent` with its tier replaced by the model the settings map it to.

    An agent that names a model, or no harness executor, comes back as it is."""
    model = agent.model
    if agent.harness_executor is None or not is_tier(model.model):
        return agent
    return replace(agent, model=replace(
        model, model=model_for(model.model, agent.harness_executor)))


def label(agent: Any) -> str:
    """The model an agent runs, with its tier when it names one."""
    named = agent.model.model
    if not is_tier(named) or agent.harness_executor is None:
        return str(named)
    try:
        return f"{model_for(named, agent.harness_executor)} tier={named}"
    except settings.SettingsError:
        return f"{named} (unmapped)"

"""A step names the tier `heavy` or `light`, and the settings name the model per harness executor.

Before: every workflow, reference and the campaign judge named a model id, so
an operator on another provider rewrote each one, and the Claude CLI 2.1.258
refused the judge's id `claude-opus-5-5`.
Now: `tiers.<tier>.<harness executor>` in `ohflow.settings.json` maps both
tiers for every harness executor, the operator's local file overrides any of
them, validation checks the resolved model, and the spec a harness executor
launches carries the resolved model with the tier beside it. An explicit
model id passes through untouched.
"""

from __future__ import annotations

import json
import warnings
from dataclasses import replace

from ohflow import settings, tiers
from ohflow.harness_executor import spec_json
from ohflow.harness_executors import HARNESS_EXECUTORS
from ohflow.workflow import (AgentSpec, ModelConfig, Phase, Step, Workflow,
                             WorkflowError, validate)
from support import TempCase, use_settings

PROVIDERS = {"durable": {"box": "buildbox", "providers": ["zai"]},
             "pi_cloud": {"providers": ["zai"]}}


def agent_on(harness_executor: str, model: str) -> AgentSpec:
    api_key_env = "ZAI_CODING_CN_API_KEY" if harness_executor == "pi" else ""
    return AgentSpec(role="r", brief="b", harness_executor=harness_executor,
                     model=ModelConfig(model=model, base_url="", api_key_env=api_key_env),
                     max_iterations=5,
                     box="buildbox" if harness_executor == "durable" else None)


class TiersResolve(TempCase):

    def workflow(self, agent: AgentSpec) -> Workflow:
        step = Step(id="w", kind="agent", agent=agent)
        return Workflow(name="tiers", repo=self.tmp, phases=(Phase(name="Only", steps=(step,)),))

    def validate_quietly(self, workflow: Workflow) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            validate(workflow)

    def test_the_base_file_maps_both_tiers_for_every_harness_executor(self):
        base = json.loads(settings.BASE_FILE.read_text(encoding="utf-8"))
        for tier in tiers.TIERS:
            self.assertEqual(set(base["tiers"][tier]), set(HARNESS_EXECUTORS), tier)
            for harness_executor in HARNESS_EXECUTORS:
                model = tiers.model_for(tier, harness_executor)
                self.assertTrue(model and not any(ch.isspace() for ch in model))

    def test_claude_heavy_is_the_alias_the_cli_takes(self):
        self.assertEqual(tiers.model_for("heavy", "claude"), "opus")

    def test_both_tiers_resolve_and_validate_on_every_harness_executor(self):
        use_settings(self, PROVIDERS)
        for tier in tiers.TIERS:
            for harness_executor in sorted(HARNESS_EXECUTORS):
                with self.subTest(tier=tier, harness_executor=harness_executor):
                    agent = agent_on(harness_executor, tier)
                    resolved = tiers.resolve(agent)
                    self.assertEqual(resolved.model.model,
                                     tiers.model_for(tier, harness_executor))
                    self.assertEqual(replace(resolved, model=agent.model), agent)
                    self.validate_quietly(self.workflow(agent))

    def test_the_local_file_overrides_one_mapping_and_keeps_the_rest(self):
        use_settings(self, {"tiers": {"heavy": {"pi": "deepseek/deepseek-v4-pro"}}})
        self.assertEqual(tiers.model_for("heavy", "pi"), "deepseek/deepseek-v4-pro")
        self.assertEqual(tiers.model_for("light", "pi"), "zai/glm-5.3-flash")
        self.assertEqual(tiers.model_for("heavy", "claude"), "opus")

    def test_the_spec_carries_the_resolved_model_and_the_tier(self):
        spec = spec_json(agent_on("claude", "heavy"), coord="01.a/01.w",
                         workspace=self.tmp, out_dir=self.tmp)
        self.assertEqual(spec["model"]["model"], "opus")
        self.assertEqual(spec["model"]["tier"], "heavy")

    def test_an_explicit_model_id_passes_through_untouched(self):
        agent = agent_on("claude", "claude-haiku-4-5-20251001")
        self.assertIs(tiers.resolve(agent), agent)
        spec = spec_json(agent, coord="01.a/01.w", workspace=self.tmp, out_dir=self.tmp)
        self.assertEqual(spec["model"]["model"], "claude-haiku-4-5-20251001")
        self.assertNotIn("tier", spec["model"])
        self.validate_quietly(self.workflow(agent))

    def test_an_unmapped_tier_is_refused_naming_the_setting(self):
        use_settings(self, {"tiers": {"light": {"codex": None, "pi": "two words"}}})
        for harness_executor in ("codex", "pi"):
            with self.assertRaises(WorkflowError) as raised:
                self.validate_quietly(self.workflow(agent_on(harness_executor, "light")))
            self.assertIn(f"tiers.light.{harness_executor}", str(raised.exception))

    def test_the_resolved_model_meets_the_harness_executors_own_rules(self):
        use_settings(self, {"tiers": {"heavy": {"pi": "no-provider"}}})
        with self.assertRaises(WorkflowError) as raised:
            self.validate_quietly(self.workflow(agent_on("pi", "heavy")))
        self.assertIn("pi model must be provider/id", str(raised.exception))

    def test_the_label_names_the_model_and_its_tier(self):
        self.assertEqual(tiers.label(agent_on("claude", "heavy")), "opus tier=heavy")
        self.assertEqual(tiers.label(agent_on("claude", "claude-x")), "claude-x")


if __name__ == "__main__":
    import unittest
    unittest.main()

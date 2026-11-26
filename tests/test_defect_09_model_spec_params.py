"""Defect 9: a ModelConfig carries provider parameters, and old workflows still build.

Fixed in `e7f85c0`, "ohflow: a ModelSpec can carry provider parameters".

`ModelConfig` was three fields - model, base url, key variable. Widening a
frozen dataclass is where workflows break, so both halves are asserted here:
the two new fields work, and every workflow in `tests/fixtures/workflows`
still builds and still validates.

The tests also hold the harness executor rule: an agent step names its harness
executor, because there is no default.
"""

from __future__ import annotations

import json
from dataclasses import replace

from ohflow.workflow import (ModelConfig, WorkflowError,
                             load_workflow, to_jsonable, validate)
from ohflow.harness_executor import spec_json
from support import TempCase, simple_workflow, agent_step

DEEPSEEK_THINKING_OFF = {"thinking": {"type": "disabled"}}


class TheThreeFieldFormStillWorks(TempCase):
    """Every workflow written before the widening uses exactly this call."""

    def test_a_three_field_spec_serialises_with_both_new_keys(self):
        out = to_jsonable(ModelConfig("m", "u", "E"))
        self.assertEqual(out, {"model": "m", "base_url": "u",
                               "api_key_env": "E",
                               "params": {}, "extra_body": {}})

    def test_the_spec_names_a_key_variable_and_holds_no_key(self):
        spec = ModelConfig("m", "u", "ZAI_CODING_CN_API_KEY",
                           params={"temperature": 0.2})
        rendered = to_jsonable(spec)
        self.assertEqual(rendered["api_key_env"], "ZAI_CODING_CN_API_KEY")
        self.assertNotIn("api_key", rendered,
                         "a key field appeared where only a name belongs")


class ProviderParametersReachTheAgentSpec(TempCase):

    def test_params_and_extra_body_both_land_in_spec_json(self):
        step = agent_step("s1")
        agent = step.agent.__class__(
            role="r", brief="b",
            model=ModelConfig("openai/deepseek-flash",
                              "https://api.deepseek.com/v1",
                              "DEEPSEEK_API_KEY",
                              params={"temperature": 0.0, "num_retries": 3},
                              extra_body=DEEPSEEK_THINKING_OFF))
        spec = spec_json(agent, coord="01.p/01.s1",
                         workspace=self.tmp, out_dir=self.tmp)
        self.assertEqual(spec["model"]["params"],
                         {"num_retries": 3, "temperature": 0.0})
        self.assertEqual(spec["model"]["extra_body"], DEEPSEEK_THINKING_OFF)
        self.assertEqual(spec["model"]["api_key_env"], "DEEPSEEK_API_KEY")
        self.assertNotIn("api_key", spec["model"])


class ValidateGuardsTheNewFields(TempCase):

    def _workflow_with(self, harness_executor="pi", **model_kw):
        step = agent_step("s1")
        agent = step.agent.__class__(
            role="r", brief="b", harness_executor=harness_executor,
            model=ModelConfig("zai/glm-5.3-flash", "u", "E", **model_kw))
        return simple_workflow(self.tmp / "repo",
                               steps=[replace(step, agent=agent)])

    def test_a_non_mapping_is_refused(self):
        with self.assertRaises(WorkflowError) as caught:
            validate(self._workflow_with(params=["temperature", 0.2]))
        self.assertIn("must be a mapping", str(caught.exception))

    def test_a_non_empty_extra_body_is_refused(self):
        with self.assertRaises(WorkflowError) as caught:
            validate(self._workflow_with(extra_body={"thinking": {"type": "disabled"}}))
        self.assertIn("extra_body", str(caught.exception))

    def test_an_agent_that_names_no_harness_executor_is_refused(self):
        with self.assertRaises(WorkflowError) as caught:
            validate(self._workflow_with(harness_executor=None))
        self.assertIn("names no harness_executor", str(caught.exception))
        self.assertIn("'pi'", str(caught.exception))

    def test_the_host_harness_executor_is_refused(self):
        with self.assertRaises(WorkflowError) as caught:
            validate(self._workflow_with(harness_executor="host"))
        self.assertIn("unknown harness executor 'host'", str(caught.exception))


class EveryShippedWorkflowStillBuilds(TempCase):
    """The regression the widening could have caused. Each of these workflow modules
    was written against the three-field `ModelConfig`."""

    #: Workflows that must build and must pass `validate`.
    VALID = ("stage1_demo.py", "stage2_gates.py", "stage3_one_worker.py",
             "stage4_fanout.py")
    #: `stage1_overlap.py` is deliberately invalid: it is the negative half of
    #: the stage 1 acceptance check, two steps in one phase owning one file. It
    #: must still *build*, because the widening could break that too.
    INVALID = ("stage1_overlap.py",)

    def _workflows_dir(self):
        from tests import TESTS_ROOT
        return TESTS_ROOT / "fixtures" / "workflows"

    def _args(self) -> dict:
        skill = self.tmp / "skills" / "codebase-design"
        skill.mkdir(parents=True, exist_ok=True)
        (skill / "SKILL.md").write_text("# skill\n", encoding="utf-8")
        return {"repo": str(self.tmp / "repo"), "wt": str(self.tmp / "wt"),
                "skills_dir": str(self.tmp / "skills")}

    def test_each_valid_demo_workflow_builds_and_validates(self):
        for filename in self.VALID:
            path = self._workflows_dir() / filename
            with self.subTest(workflow=filename):
                self.assertTrue(path.exists(), f"{path} is missing")
                workflow = validate(load_workflow(path, self._args()))
                self.assertTrue(workflow.phases, f"{filename} built no phases")

    def test_the_deliberately_invalid_workflow_builds_and_is_still_rejected(self):
        path = self._workflows_dir() / "stage1_overlap.py"
        workflow = load_workflow(path, self._args())          # building must work
        with self.assertRaises(WorkflowError) as caught:
            validate(workflow)
        self.assertIn("both own", str(caught.exception))

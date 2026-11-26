"""Pi workflows are accepted only when every requested tool policy maps to pi."""

from __future__ import annotations

import warnings
from dataclasses import replace

from ohflow.workflow import (ModelConfig, Phase, Workflow, WorkflowError, RetryPolicy, Step,
                             ToolPolicy, AgentSpec, validate)
from support import TempCase


PI_MODEL = ModelConfig(
    model="zai/glm-5.3-flash",
    base_url="https://api.z.ai/api/coding/paas/v4",
    api_key_env="OHFLOW_TEST_FAKE_KEY",
)


class PiValidation(TempCase):

    def _agent(self, **changes) -> AgentSpec:
        base = AgentSpec(role="pi-test", brief="say DONE", model=PI_MODEL,
                         harness_executor="pi", max_iterations=2)
        return replace(base, **changes)

    def _workflow(self, agent: AgentSpec | None = None, **step_changes) -> Workflow:
        step = Step(id="agent", kind="agent", agent=agent or self._agent())
        step = replace(step, **step_changes)
        return Workflow(name="pi-validation", repo=self.tmp,
                        phases=(Phase(name="Only", steps=(step,)),))

    def test_pi_harness_executor_and_every_supported_tool_name_validate(self):
        names = ("terminal", "file_editor", "read", "bash", "edit", "write",
                 "grep", "find", "ls", "powershell")
        validate(self._workflow())                       # default preset
        for name in names:
            with self.subTest(name=name):
                validate(self._workflow(self._agent(
                    tools=ToolPolicy(only=(name,)))))

    def test_task_tracker_is_dropped_with_a_warning(self):
        agent = self._agent(tools=ToolPolicy(
            only=("terminal", "task_tracker")))
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            validate(self._workflow(agent))
        self.assertTrue(any("task_tracker" in str(w.message)
                            and "drop" in str(w.message).lower()
                            for w in caught), caught)

    def test_unmappable_tool_browser_and_subagents_are_refused(self):
        bad_tool_policies = (
            ToolPolicy(only=("made_up",)),
            ToolPolicy(enable_browser=True),
            ToolPolicy(enable_sub_agents=True),
        )
        for tool_policy in bad_tool_policies:
            with self.subTest(tool_policy=tool_policy):
                with self.assertRaises(WorkflowError):
                    validate(self._workflow(self._agent(tools=tool_policy)))

    def test_pi_model_is_provider_slash_id_and_params_are_closed(self):
        validate(self._workflow(self._agent(model=replace(
            PI_MODEL, params={"thinking": "high"}))))

        bad_models = (
            replace(PI_MODEL, model="glm-5.3-flash"),
            replace(PI_MODEL, model="zai/"),
            replace(PI_MODEL, params={"num_retries": 0}),
            replace(PI_MODEL, params={"thinking": ""}),
            replace(PI_MODEL, params={"thinking": "hgh"}),
            replace(PI_MODEL, extra_body={"thinking": {"type": "disabled"}}),
        )
        for model in bad_models:
            with self.subTest(model=model):
                with self.assertRaises(WorkflowError):
                    validate(self._workflow(self._agent(model=model)))

    def test_named_skills_need_a_directory_and_an_existing_skill(self):
        with self.assertRaises(WorkflowError):
            validate(self._workflow(self._agent(skills=("demo",))))

        skills_dir = self.tmp / "skills"
        (skills_dir / "demo").mkdir(parents=True)
        (skills_dir / "demo" / "SKILL.md").write_text("# demo\n", encoding="utf-8")
        validate(self._workflow(self._agent(
            skills=("demo",), skills_dir=skills_dir)))

        with self.assertRaises(WorkflowError):
            validate(self._workflow(self._agent(
                skills=("missing",), skills_dir=skills_dir)))

    def test_more_than_three_pi_mcp_servers_warns_but_validates(self):
        config = {f"s{i}": {"url": f"http://127.0.0.1:{9000 + i}/mcp"}
                  for i in range(4)}
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            validate(self._workflow(self._agent(mcp_config=config)))
        self.assertTrue(any("more than three" in str(w.message).lower()
                            for w in caught), caught)

    def test_stall_timeout_and_carry_context_are_typed(self):
        validate(self._workflow(stall_timeout_s=30,
                                retry=RetryPolicy(carry_context=True)))
        for changes in (
                {"stall_timeout_s": 0},
                {"stall_timeout_s": True},
                {"retry": RetryPolicy(carry_context="yes")},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(WorkflowError):
                    validate(self._workflow(**changes))

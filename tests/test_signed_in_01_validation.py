"""The claude and codex harness executors: the registry, validation and the fingerprint.

These harness executors start a signed-in harness in its usual setup, so a workflow may not name tools,
skills or MCP servers for them unless it asks for agent_profile='hermetic'.
"""

from __future__ import annotations

import warnings
from dataclasses import replace

from ohflow import harness_executors
from ohflow.workflow import (ModelConfig, Phase, Workflow, WorkflowError, RetryPolicy, Step,
                             ToolPolicy, AgentSpec, validate)
from ohflow.harness_executor import spec_json
from support import TempCase

MODELS = {
    "claude": ModelConfig(model="claude-haiku-4-5-20251001", base_url="", api_key_env=""),
    "codex": ModelConfig(model="gpt-5.6-luna", base_url="", api_key_env=""),
}


class SignedInValidation(TempCase):

    def _agent(self, harness_executor: str, **changes) -> AgentSpec:
        return replace(AgentSpec(role="rollcall", brief="report", model=MODELS[harness_executor],
                                 harness_executor=harness_executor, max_iterations=5), **changes)

    def _workflow(self, agent: AgentSpec, **step_changes) -> Workflow:
        step = replace(Step(id="w", kind="agent", agent=agent), **step_changes)
        return Workflow(name="signed_in", repo=self.tmp, phases=(Phase(name="Only", steps=(step,)),))

    def _refused(self, workflow: Workflow, text: str) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with self.assertRaises(WorkflowError) as caught:
                validate(workflow)
        self.assertIn(text, str(caught.exception))

    def test_registry_names_every_harness_executor_once(self):
        self.assertEqual(harness_executors.HARNESS_EXECUTORS,
                         {"pi", "claude", "codex", "durable",
                          "pi-cloud", "claude-cloud", "codex-cloud"})
        for name in harness_executors.HARNESS_EXECUTORS:
            with self.subTest(harness_executor=name):
                self.assertEqual(harness_executors.harness_executor_for(name).name, name)
        with self.assertRaises(ValueError):
            harness_executors.harness_executor_for("nope")

    def test_usual_setup_validates_with_an_empty_key_variable(self):
        for harness_executor in MODELS:
            with self.subTest(harness_executor=harness_executor), warnings.catch_warnings():
                warnings.simplefilter("ignore")
                validate(self._workflow(self._agent(harness_executor), stall_timeout_s=120))

    def test_stall_and_carry_follow_the_capability_table(self):
        validate(self._workflow(self._agent("claude"),
                                retry=RetryPolicy(max=1, on=("agent_error",), carry_context=True)))
        self._refused(self._workflow(self._agent("codex"),
                                     retry=RetryPolicy(max=1, on=("agent_error",),
                                                       carry_context=True)),
                      "carry_context is supported only by harness executors ['claude', 'pi']")

    def test_tool_policy_is_the_signed_in_harness_own_in_the_usual_setup(self):
        cases = (
            (dict(tools=ToolPolicy(only=("terminal",))), "tools.only needs"),
            (dict(mcp_config={"forum": {"command": "x"}}), "mcp_config needs agent_profile='hermetic'"),
            (dict(skills=("x",)), "loads the signed-in harness's own skills"),
            (dict(tools=ToolPolicy(enable_browser=True)), "refuses enable_browser"),
            (dict(tools=ToolPolicy(enable_sub_agents=True)), "refuses enable_sub_agents"),
            (dict(tools=ToolPolicy(allow=("forum.post",))), "refuses tools.allow"),
        )
        for harness_executor in MODELS:
            for changes, text in cases:
                with self.subTest(harness_executor=harness_executor, text=text):
                    self._refused(self._workflow(self._agent(harness_executor, **changes)), text)

    def test_hermetic_claude_takes_a_tool_policy(self):
        validate(self._workflow(self._agent(
            "claude", agent_profile="hermetic", tools=ToolPolicy(only=("terminal", "file_editor")),
            mcp_config={"forum": {"command": "node", "args": ["forum.js"]}})))
        validate(self._workflow(self._agent(
            "codex", agent_profile="hermetic", mcp_config={"forum": {"command": "node"}})))
        self._refused(self._workflow(self._agent(
            "claude", agent_profile="hermetic", tools=ToolPolicy(only=("made_up",)))),
            "unsupported names")
        self._refused(self._workflow(self._agent(
            "codex", agent_profile="hermetic", tools=ToolPolicy(only=("terminal",)))),
            "tools.only needs harness_executor='claude'")

    def test_profile_values(self):
        self._refused(self._workflow(self._agent("claude", agent_profile="lite")),
                      "agent.agent_profile must be None or one of ['hermetic']")
        self._refused(self._workflow(replace(self._agent("claude"), harness_executor="pi",
                                             model=ModelConfig("zai/glm", "u", "K"),
                                             agent_profile="hermetic")),
                      "agent.agent_profile is supported only by harness executors")

    def test_model_params_are_closed(self):
        validate(self._workflow(self._agent(
            "codex", model=replace(MODELS["codex"], params={"reasoning_effort": "low"}))))
        validate(self._workflow(self._agent(
            "claude", model=replace(MODELS["claude"], params={"effort": "high"}))))
        self._refused(self._workflow(self._agent(
            "codex", model=replace(MODELS["codex"], params={"temperature": 0.2}))),
            "model params are closed")
        self._refused(self._workflow(self._agent(
            "claude", model=replace(MODELS["claude"], model=""))), "model must name a model")
        self._refused(self._workflow(self._agent(
            "claude", model=replace(MODELS["claude"], extra_body={"x": 1}))),
            "refuses ModelConfig.extra_body")

    def test_spec_json_carries_profile_only_when_set(self):
        spec = spec_json(self._agent("codex"), coord="c", workspace=self.tmp, out_dir=self.tmp)
        self.assertNotIn("agent_profile", spec)
        spec = spec_json(self._agent("codex", agent_profile="hermetic"), coord="c",
                         workspace=self.tmp, out_dir=self.tmp)
        self.assertEqual(spec["agent_profile"], "hermetic")

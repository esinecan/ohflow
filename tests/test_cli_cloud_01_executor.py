"""The claude-cloud and codex-cloud executors: refusals, routes and one recorded attempt.

Both executors are pi-cloud's adapter behind another route prefix, so one
recorded step from the fake Worker exercises the launch, the `/claude` route
prefix, the branch prefix and the fetch-back.
"""

from __future__ import annotations

import json
from pathlib import Path

from ohflow import harness_executors
from ohflow.workflow import AgentSpec, ModelConfig, ToolPolicy

from pi_cloud_support import PiCloudCase, git


def _agent(harness_executor: str, **changes) -> AgentSpec:
    model = changes.pop("model", None) or ModelConfig(
        model="claude-haiku-4-5-20251001" if harness_executor == "claude-cloud" else "gpt-5.6-luna",
        base_url="", api_key_env="")
    return AgentSpec(role="r", brief="b", model=model,
                     harness_executor=harness_executor, **changes)


class CliCloudRules(PiCloudCase):

    def test_the_usual_agent_has_no_fault(self):
        for name in ("claude-cloud", "codex-cloud"):
            with self.subTest(harness_executor=name):
                module = harness_executors.harness_executor_module(name)
                self.assertEqual(module.agent_errors("s", _agent(name)), [])

    def test_keys_params_and_tool_policies_are_refused(self):
        module = harness_executors.harness_executor_module("claude-cloud")
        cases = (
            (dict(model=ModelConfig(model="gpt-5.6-luna", base_url="", api_key_env="")), "must be a Claude model id"),
            (dict(model=ModelConfig(model="claude-haiku-4-5-20251001", base_url="", api_key_env="ANTHROPIC_API_KEY")), "holds the subscription login"),
            (dict(model=ModelConfig(model="claude-haiku-4-5-20251001", base_url="", api_key_env="", params={"effort": "low"})), "takes no model params"),
            (dict(tools=ToolPolicy(block=("brave-search.*",))), "refuses tools.allow and tools.block"),
            (dict(mcp_config={"forum": {"command": "x"}}), "refuses mcp_config"),
            (dict(skills_dir=Path("/x")), "refuses skills_dir"),
        )
        for changes, text in cases:
            with self.subTest(text=text):
                errors = module.agent_errors("s", _agent("claude-cloud", **changes))
                self.assertTrue(any(text in error for error in errors), errors)


    def test_named_skills_are_accepted(self):
        for name in ("claude-cloud", "codex-cloud"):
            with self.subTest(harness_executor=name):
                module = harness_executors.harness_executor_module(name)
                agent = _agent(name, skills=("codebase-design",))
                self.assertEqual(module.agent_errors("s", agent), [])


class CliCloudAttempt(PiCloudCase):

    def setUp(self):
        super().setUp()
        self.executor = harness_executors.harness_executor_for("claude-cloud")
        self.module = harness_executors.harness_executor_module("claude-cloud")

    def test_a_recorded_step_runs_under_the_claude_prefix(self):
        key = self.key_of(self.tmp / "claude")
        self.worker.plan(key, 1, ["success"])
        out_dir, result = self.run_attempt(
            "claude", model={"model": "claude-haiku-4-5-20251001", "base_url": "",
                             "api_key_env": "", "params": {}, "extra_body": None})
        self.assertIsNone(result["error"], result["error"])
        remote = json.loads((out_dir / "remote.json").read_text(encoding="utf-8"))
        self.assertTrue(remote["url"].endswith("/claude"), remote["url"])
        self.assertEqual(remote["branch"], f"ohflow/claude-cloud/{key}")
        self.assertTrue(any(request["path"].startswith("/claude/attempts/")
                            for request in self.worker.requests))
        self.assertEqual(result["pi_cloud"]["head"], git(self.repo, "rev-parse", "HEAD"))
        self.assertTrue((out_dir / "logs" / "claude-cloud-events.jsonl").is_file())
        tokens, why = self.module.usage(out_dir)
        self.assertIsNone(why)
        self.assertEqual(tokens["prompt_tokens"], result["tokens"]["prompt_tokens"])
        self.assertEqual((result["cost"], result["cost_source"]), (0.0, "subscription"))

    def test_the_step_post_carries_the_named_skills(self):
        key = self.key_of(self.tmp / "skills")
        self.worker.plan(key, 1, ["success"])
        _out_dir, result = self.run_attempt(
            "skills", skills=["codebase-design"],
            model={"model": "claude-haiku-4-5-20251001", "base_url": "",
                   "api_key_env": "", "params": {}, "extra_body": None})
        posted = next(r["body"] for r in self.worker.requests
                      if r["path"].endswith("/step"))
        self.assertEqual(posted["skills"], ["codebase-design"])
        self.assertEqual(result["skills"], ["codebase-design"])

    def test_a_recovered_record_keeps_the_subscription_cost_source(self):
        from ohflow import cli_cloud_runner
        out_dir = self.tmp / "recovered"
        out_dir.mkdir()
        result, _final = cli_cloud_runner._recover(
            {"coord": "01.p/01.s", "attempt": 1}, out_dir, [], "runner was killed")
        self.assertEqual((result["cost"], result["cost_source"]), (0.0, "subscription"))
        self.assertEqual(result["error"], "runner was killed")

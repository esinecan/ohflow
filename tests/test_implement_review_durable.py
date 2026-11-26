"""The implement-review workflow's durable agents: rules R4-R6 on the box.

Both agents of `workflows/implement_review.py` can run on the durable
harness executor. The box holds its own model keys and its own copy of the
skills tree, so a durable agent takes an empty `base_url` and `api_key_env`,
a `box` naming the box's ssh host alias, and no `skills_dir` - the
box resolves `skills` names itself. The tests mirror the builders of
`test_implement_review_reviewer_model.py`: `_agents` builds the workflow
through the workflow's own `validate`, so every test that reaches its
assertions has already proved the built workflow reports no error.
"""

from __future__ import annotations

from pathlib import Path

from ohflow.workflow import load_workflow, validate
from support import TempCase

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
WORKFLOW_MODULE = SCRIPTS / "ohflow" / "workflows" / "implement_review.py"


class DurableAgents(TempCase):

    def setUp(self):
        super().setUp()
        for name in ("impl.md", "review.md"):
            (self.tmp / name).write_text(f"# {name}\n", encoding="utf-8")
        skill = self.tmp / "skills" / "codebase-design"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("# skill\n", encoding="utf-8")

    def _args(self, **extra) -> dict:
        return {"repo": str(self.tmp / "repo"), "branch": "feat/x", "base": "main",
                "worktree": str(self.tmp / "wt"), "mode": "all",
                "impl_brief": str(self.tmp / "impl.md"),
                "review_brief": str(self.tmp / "review.md"),
                "skills_dir": str(self.tmp / "skills"),
                "test_cmd": "python -V", "install_cmd": "python -V", **extra}

    def _agents(self, **extra):
        # validate() raises WorkflowError on any fault, so building the agents
        # is the workflow's own validation reporting no error.
        workflow = validate(load_workflow(WORKFLOW_MODULE, self._args(**extra)))
        return {step.agent.role: step.agent
                for _pi, _phase, _si, step in workflow.steps() if step.agent}

    def test_r4_a_durable_implementer_names_the_box_and_keeps_the_skill(self):
        agents = self._agents(harness_executor="durable", model="zai/glm-5.3",
                              impl_skills="codebase-design")
        impl = agents["implement"]
        self.assertEqual(impl.harness_executor, "durable")
        self.assertEqual(impl.box, "buildbox")
        self.assertIsNone(impl.agent_profile)
        self.assertEqual(impl.skills, ("codebase-design",))
        self.assertIsNone(impl.skills_dir)
        self.assertEqual(impl.model.model, "zai/glm-5.3")
        self.assertEqual(impl.model.base_url, "")
        self.assertEqual(impl.model.api_key_env, "")
        self.assertEqual(impl.model.params, {"thinking": "high"})
        # Without a model the durable default applies, and `box` names the box.
        agents = self._agents(harness_executor="durable", box="attic")
        self.assertEqual(agents["implement"].model.model, "light")
        self.assertEqual(agents["implement"].box, "attic")

    def test_r5_a_durable_reviewer_runs_terminal_only_on_the_box(self):
        agents = self._agents(harness_executor="pi",
                              review_harness_executor="durable")
        review = agents["review"]
        self.assertEqual(review.harness_executor, "durable")
        self.assertEqual(review.tools.only, ("terminal",))
        self.assertEqual(review.skills, ())
        self.assertIsNone(review.skills_dir)
        self.assertEqual(review.box, "buildbox")
        self.assertEqual(review.model.base_url, "")
        self.assertEqual(review.model.api_key_env, "")
        self.assertEqual(review.model.params, {"thinking": "high"})

    def test_r6_the_reviewer_takes_review_model_then_model_then_the_durable_default(self):
        agents = self._agents(harness_executor="durable", model="zai/glm-5.3",
                              review_model="zai/glm-5.3")
        self.assertEqual(agents["review"].model.model, "zai/glm-5.3")
        # A reviewer on the implementer's harness executor takes `model`.
        agents = self._agents(harness_executor="durable", model="zai/glm-5.3")
        self.assertEqual(agents["implement"].model.model, "zai/glm-5.3")
        self.assertEqual(agents["review"].model.model, "zai/glm-5.3")
        # A reviewer moved onto durable takes durable's own default.
        agents = self._agents(harness_executor="pi", model="zai/glm-5.3",
                              review_harness_executor="durable")
        self.assertEqual(agents["review"].model.model, "light")

    def test_r4_and_r6_a_pi_reviewer_behind_a_durable_implementer_gets_the_zai_route(self):
        agents = self._agents(harness_executor="durable",
                              review_harness_executor="pi", model="zai/glm-5.3")
        review = agents["review"]
        self.assertEqual(review.harness_executor, "pi")
        self.assertEqual(review.model.model, "light")
        self.assertEqual(review.model.api_key_env, "ZAI_CODING_CN_API_KEY")
        self.assertEqual(review.model.base_url,
                         "https://api.z.ai/api/coding/paas/v4")
        self.assertIsNone(review.agent_profile)
        self.assertIsNone(review.box)
        self.assertEqual(review.skills_dir, Path(self.tmp / "skills"))
        self.assertEqual(review.model.params, {"thinking": "high"})

    def test_r5_and_r6_a_pi_implementer_keeps_its_settings_before_a_durable_reviewer(self):
        agents = self._agents(harness_executor="pi",
                              review_harness_executor="durable",
                              model="zai/glm-5.3")
        impl = agents["implement"]
        self.assertEqual(impl.harness_executor, "pi")
        self.assertEqual(impl.model.api_key_env, "ZAI_CODING_CN_API_KEY")
        self.assertEqual(impl.skills_dir, Path(self.tmp / "skills"))
        self.assertIsNone(impl.agent_profile)
        self.assertIsNone(impl.box)
        review = agents["review"]
        self.assertEqual(review.model.model, "light")
        self.assertEqual(review.model.api_key_env, "")
        self.assertEqual(review.box, "buildbox")

    def test_an_implementer_loads_only_the_skills_impl_skills_names(self):
        self.assertEqual(self._agents(harness_executor="pi")["implement"].skills, ())
        impl = self._agents(harness_executor="pi",
                            impl_skills=" codebase-design ,")["implement"]
        self.assertEqual(impl.skills, ("codebase-design",))


if __name__ == "__main__":
    import unittest
    unittest.main()

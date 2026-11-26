from __future__ import annotations

from pathlib import Path

from ohflow.workflow import load_workflow, validate
from support import TempCase

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
WORKFLOW_MODULE = SCRIPTS / "ohflow" / "workflows" / "implement_review.py"


class ReviewerModel(TempCase):

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
        workflow = validate(load_workflow(WORKFLOW_MODULE, self._args(**extra)))
        return {step.agent.role: step.agent
                for _pi, _phase, _si, step in workflow.steps() if step.agent}

    def test_r1_without_the_arguments_both_agents_share_executor_and_model(self):
        agents = self._agents(harness_executor="pi", model="zai/glm-5.3", thinking="high")
        for agent in agents.values():
            self.assertEqual(agent.harness_executor, "pi")
            self.assertEqual(agent.model.model, "zai/glm-5.3")
            self.assertEqual(agent.model.params, {"thinking": "high"})

    def test_r3_review_model_sets_the_reviewer_alone(self):
        agents = self._agents(harness_executor="pi", model="zai/glm-5.3",
                              review_model="zai/glm-5.3-flash")
        self.assertEqual(agents["implement"].model.model, "zai/glm-5.3")
        self.assertEqual(agents["review"].model.model, "zai/glm-5.3-flash")

    def test_r5_the_reviewer_has_the_terminal_alone_and_codex_is_refused(self):
        agents = self._agents(harness_executor="pi", review_harness_executor="durable")
        self.assertEqual(agents["review"].tools.only, ("terminal",))
        for refused in ("codex",):
            with self.assertRaisesRegex(ValueError, "terminal alone; use one of"):
                load_workflow(WORKFLOW_MODULE, self._args(
                    harness_executor="pi", review_harness_executor=refused))

    def test_r6_params_follow_the_reviewer_executor(self):
        agents = self._agents(harness_executor="pi", thinking="low",
                              review_harness_executor="claude",
                              review_model="claude-sonnet-4-6")
        self.assertEqual(agents["implement"].model.params, {"thinking": "low"})
        self.assertEqual(agents["review"].model.params, {})

    def test_r2_r3_r5_a_claude_reviewer_runs_hermetic_on_the_terminal(self):
        agents = self._agents(harness_executor="pi", review_harness_executor="claude",
                              review_model="claude-sonnet-4-6")
        review = agents["review"]
        self.assertEqual(review.harness_executor, "claude")
        self.assertEqual(review.agent_profile, "hermetic")
        self.assertEqual(review.tools.only, ("terminal",))
        self.assertIsNone(review.skills_dir)
        self.assertEqual((review.model.model, review.model.base_url, review.model.api_key_env),
                         ("claude-sonnet-4-6", "", ""))
        with self.assertRaisesRegex(ValueError, "claude reviewer needs review_model"):
            load_workflow(WORKFLOW_MODULE, self._args(
                harness_executor="pi", review_harness_executor="claude"))

    def test_r1_r3_review_mode_takes_review_model_over_model(self):
        (self.tmp / "wt").mkdir()
        agents = self._agents(mode="review", harness_executor="pi", model="zai/glm-5.3",
                              review_model="zai/glm-5.3-flash")
        self.assertEqual(list(agents), ["review"])
        self.assertEqual(agents["review"].model.model, "zai/glm-5.3-flash")


if __name__ == "__main__":
    import unittest
    unittest.main()

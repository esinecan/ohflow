"""The implement-review workflow builds pi agents."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from ohflow.workflow import validate
from support import TempCase

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


class PiImplementReviewWorkflow(TempCase):

    def test_implement_review_workflow_builds_two_pi_agents_with_thinking(self):
        workflow_module = _load(SCRIPTS / "ohflow" / "workflows" / "implement_review.py",
                                "pi_implement_review_workflow")
        impl = self.tmp / "impl.md"
        review = self.tmp / "review.md"
        impl.write_text("implement", encoding="utf-8")
        review.write_text("review", encoding="utf-8")
        skills = self.tmp / "skills"
        (skills / "codebase-design").mkdir(parents=True)
        (skills / "codebase-design" / "SKILL.md").write_text("# skill\n", encoding="utf-8")
        built = validate(workflow_module.build({
            "repo": str(self.tmp), "branch": "feat/pi", "base": "main",
            "worktree": str(self.tmp / "wt"), "mode": "all",
            "impl_brief": str(impl), "review_brief": str(review),
            "harness_executor": "pi", "thinking": "xhigh",
            "skills_dir": str(skills),
            "test_cmd": "python -V", "install_cmd": "python -V",
        }))
        agents = [step.agent for _pi, _phase, _si, step in built.steps()
                  if step.agent]
        self.assertEqual([w.harness_executor for w in agents], ["pi", "pi"])
        self.assertTrue(all(w.model.model == "light" for w in agents))
        self.assertTrue(all(w.model.params == {"thinking": "xhigh"} for w in agents))
        steps = [step for _pi, _phase, _si, step in built.steps()]
        self.assertEqual(steps[0].write_scope, ("**",))
        self.assertEqual(steps[1].write_scope, ())

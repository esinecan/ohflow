"""The durable box has a field of its own: `AgentSpec.box`.

`durable` runs its agent on a machine the operator owns, and the step names
that machine by its ssh host alias. The alias used to travel in
`agent_profile`, which names a harness setup. Five rules, one test each:

- A durable agent with no `box` is refused, and the error names `agent.box`.
- A durable agent with an `agent_profile` is refused, by the harness executor
  and by the capability table.
- Any other harness executor refuses `box`.
- `box` enters the step fingerprint only when it is set, so no step of another
  harness executor changes its fingerprint.
- `spec.json` carries `box` only when it is set, and the attempt record names
  it among the requested settings.
"""

from __future__ import annotations

import warnings
from dataclasses import replace

from ohflow import attempt_record, durable_runner, harness_executors
from ohflow.fingerprint import fingerprint_input
from ohflow.harness_executor import spec_json
from ohflow.run_log import RunState
from ohflow.workflow import (AgentSpec, ModelConfig, Phase, Step, Workflow,
                             WorkflowError, validate)
from support import TempCase, git_repo

WHERE = "01.p/01.s"
DURABLE_MODEL = ModelConfig(model="zai/glm-5.3-flash", base_url="", api_key_env="",
                            params={"thinking": "low"})
CLAUDE_MODEL = ModelConfig(model="claude-haiku-4-5-20251001", base_url="", api_key_env="")


class DurableBox(TempCase):

    def _durable(self, **changes) -> AgentSpec:
        return replace(AgentSpec(role="implement", brief="x", model=DURABLE_MODEL,
                                 harness_executor="durable", box="buildbox"), **changes)

    def _claude(self, **changes) -> AgentSpec:
        return replace(AgentSpec(role="review", brief="x", model=CLAUDE_MODEL,
                                 harness_executor="claude"), **changes)

    def _workflow(self, agent: AgentSpec) -> Workflow:
        step = Step(id="w", kind="agent", agent=agent)
        return Workflow(name="box", repo=self.tmp, phases=(Phase(name="Only", steps=(step,)),))

    def _refusal(self, workflow: Workflow) -> str:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with self.assertRaises(WorkflowError) as caught:
                validate(workflow)
        return str(caught.exception)

    def test_a_durable_agent_must_name_its_box(self):
        self.assertEqual(durable_runner.agent_errors(WHERE, self._durable()), [])
        for bad in (None, "", "build box", "user@host"):
            with self.subTest(box=bad):
                errs = durable_runner.agent_errors(WHERE, self._durable(box=bad))
                self.assertEqual(len(errs), 1, errs)
                self.assertIn("durable agent.box must name the ssh host alias", errs[0])
        self.assertIn("durable agent.box must name the ssh host alias",
                      self._refusal(self._workflow(self._durable(box=None))))

    def test_a_durable_agent_refuses_an_agent_profile(self):
        errs = durable_runner.agent_errors(WHERE, self._durable(agent_profile="buildbox"))
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("durable refuses agent.agent_profile", errs[0])
        self.assertFalse(harness_executors.harness_executor_info("durable").has(
            harness_executors.CAP_AGENT_PROFILE))
        refusal = self._refusal(self._workflow(self._durable(agent_profile="hermetic")))
        self.assertIn("agent.agent_profile is supported only by harness executors "
                      "['claude', 'codex']", refusal)

    def test_every_other_harness_executor_refuses_a_box(self):
        self.assertEqual(harness_executors.harness_executors_with(harness_executors.CAP_BOX),
                         ["durable"])
        self.assertIn("agent.box is supported only by harness executors ['durable']",
                      self._refusal(self._workflow(self._claude(box="buildbox"))))

    def test_box_enters_the_fingerprint_only_when_set(self):
        state = RunState()
        repo = git_repo(self.tmp / "repo")
        plain = replace(self._workflow(self._claude()), repo=repo)
        boxed = replace(self._workflow(self._durable()), repo=repo)
        attic = replace(self._workflow(self._durable(box="attic")), repo=repo)
        body = fingerprint_input(plain, state, plain.phases[0].steps[0])
        self.assertNotIn("box", body["agent"])
        body = fingerprint_input(boxed, state, boxed.phases[0].steps[0])
        self.assertEqual(body["agent"]["box"], "buildbox")
        self.assertNotIn("agent_profile", body["agent"])
        self.assertNotEqual(
            body, fingerprint_input(attic, state, attic.phases[0].steps[0]))

    def test_spec_json_and_the_attempt_record_carry_box_only_when_set(self):
        spec = spec_json(self._claude(), coord="c", workspace=self.tmp, out_dir=self.tmp)
        self.assertNotIn("box", spec)
        self.assertNotIn("box", attempt_record.settings_record(spec, None)["requested"])
        spec = spec_json(self._durable(), coord="c", workspace=self.tmp, out_dir=self.tmp)
        self.assertEqual(spec["box"], "buildbox")
        self.assertNotIn("agent_profile", spec)
        self.assertEqual(attempt_record.settings_record(spec, None)["requested"]["box"],
                         "buildbox")


if __name__ == "__main__":
    import unittest
    unittest.main()

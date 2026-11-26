"""`/api/workflow` carries what a reviewer reads before a step runs.

A held run has no invocation to inspect, so the page shows the plan instead:
each step's `plan` holds the brief, tool policy, model, write scope, worktree,
retry, consumed handovers, dependencies, gate checks, limits and handover
spec; each phase's `plan` holds its failure policy, minimum success and
parallel limit. The source is `workflow.json`, as `to_jsonable` writes it.
"""

from __future__ import annotations

import json
from dataclasses import replace

from dashboard_support import T0
from ohflow import dashboard_data
from ohflow.workflow import (CheckSpec, GateSpec, HandoverSpec, Phase,
                             RetryPolicy, Step, to_jsonable, validate)
from support import TempCase, agent_step, git_repo, simple_workflow


class PlannedStepFields(TempCase):

    def setUp(self) -> None:
        super().setUp()
        repo = git_repo(self.tmp / "repo")
        first = agent_step("a", brief="Scout the module.")
        second = Step(
            id="b", kind="agent", worktree=None,
            write_scope=("src/**", "tests/**"),
            depends_on=("a",), consumes=("a",),
            retry=RetryPolicy(max=2, on=("agent_error",)),
            execution_timeout_s=1200, stall_timeout_s=300,
            gate=GateSpec(checks=(CheckSpec("final_message_matches",
                                            {"regex": "DONE"}),)),
            handover=HandoverSpec(audience="next", max_chars=4000),
            # The host harness executor has no stall deadline, so the step that
            # declares one runs on pi.
            agent=replace(agent_step("b", brief="Build on the scout's findings.").agent,
                          harness_executor="pi"))
        # A command step records `"gate": null`, which the step reader once
        # read as a dict; the plan of such a step has no brief and no checks.
        third = Step(id="c", kind="command", command="echo DONE",
                     execution_timeout_s=60)
        workflow = validate(simple_workflow(repo, phases=(
            Phase(name="Scout", steps=(first,), on_step_failure="abort",
                  min_success="all", max_parallel=1),
            Phase(name="Build", steps=(second, third), min_success="any"))))
        self.dir = self.run_dir("r-plan")
        self.dir.mkdir(parents=True)
        (self.dir / "workflow.json").write_text(
            json.dumps(to_jsonable(workflow), indent=2, sort_keys=True),
            encoding="utf-8")
        self.payload = dashboard_data.workflow_data(self.dir, now=T0)

    def step(self, step_id: str) -> dict:
        return next(s for s in self.payload["steps"] if s["id"] == step_id)

    def test_each_step_carries_its_plan(self):
        plan = self.step("b")["plan"]
        self.assertEqual(plan["brief"], "Build on the scout's findings.")
        self.assertEqual(plan["tool_policy"]["preset"], "default")
        self.assertEqual(plan["harness_executor"], "pi")
        self.assertEqual(plan["model"], "fake/deterministic")
        self.assertEqual(plan["write_scope"], ["src/**", "tests/**"])
        self.assertIsNone(plan["worktree"])
        self.assertEqual(plan["retry"], {"max": 2, "on": ["agent_error"],
                                         "carry_context": False})
        self.assertEqual(plan["consumes"], ["a"])
        self.assertEqual(plan["depends_on"], ["a"])
        self.assertEqual(plan["gate"], ["final_message_matches",
                                        "handover_written"])
        self.assertEqual(plan["limits"], {"execution_timeout_s": 1200,
                                          "stall_timeout_s": 300,
                                          "max_iterations": 5})
        self.assertEqual(plan["handover"]["audience"], "next")
        self.assertEqual(plan["handover"]["max_chars"], 4000)

    def test_a_step_without_the_optional_fields_still_has_a_plan(self):
        plan = self.step("a")["plan"]
        self.assertEqual(plan["brief"], "Scout the module.")
        self.assertEqual(plan["write_scope"], [])
        self.assertEqual(plan["consumes"], [])
        self.assertEqual(plan["depends_on"], [])
        self.assertEqual(plan["retry"]["max"], 0)
        self.assertIsNone(plan["limits"]["stall_timeout_s"])

    def test_a_command_step_with_no_gate_has_an_empty_plan(self):
        step = self.step("c")
        self.assertEqual(step["gate_checks"], [])
        plan = step["plan"]
        self.assertIsNone(plan["brief"])
        self.assertIsNone(plan["model"])
        self.assertEqual(plan["gate"], [])
        self.assertEqual(plan["limits"]["execution_timeout_s"], 60)

    def test_each_phase_carries_its_policy(self):
        scout, build = self.payload["phases"]
        self.assertEqual(scout["plan"], {"on_step_failure": "abort",
                                         "min_success": "all",
                                         "max_parallel": 1})
        self.assertEqual(build["plan"], {"on_step_failure": "quarantine",
                                         "min_success": "any",
                                         "max_parallel": None})

    def test_the_brief_is_capped_like_every_graph_string(self):
        long_brief = "x" * (dashboard_data.STRING_CAP + 50)
        workflow = validate(simple_workflow(
            git_repo(self.tmp / "repo2"),
            steps=[agent_step("long", brief=long_brief)]))
        run_dir = self.run_dir("r-cap")
        run_dir.mkdir(parents=True)
        (run_dir / "workflow.json").write_text(
            json.dumps(to_jsonable(workflow)), encoding="utf-8")
        payload = dashboard_data.workflow_data(run_dir, now=T0)
        brief = payload["steps"][0]["plan"]["brief"]
        self.assertTrue(brief.startswith("x" * dashboard_data.STRING_CAP))
        self.assertIn("capped at", brief)


if __name__ == "__main__":
    import unittest
    unittest.main()

"""m5: the eight roll-call scenarios build, validate and take their arguments.

Every scenario is a workflow of trivial tasks: write who you are, commit, report JSON.
Asserted here, with no agent started:

- Every scenario and alias builds and validates on a scratch repository that has
  no merge commit.
- `count` gives each agent its own step id, `<harness executor>-<k>`.
- `consolidator`, `reviewer` and `judge` pick the harness executor of that role.
- An unknown scenario, an unknown harness executor and a harness executor named twice are refused with a
  message that lists what is allowed.
- The retry scenario fails its first attempt on a token that its brief never names.
- `--config` changes a harness executor's model; the `hermetic` profile reaches only the
  signed-in harness executors that accept it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))

from support import TempCase, git_repo  # noqa: E402

from ohflow.workflow import load_workflow, validate  # noqa: E402

WORKFLOW = "ohflow.workflows.rollcall"
SCENARIOS = ("single", "fanout", "relay", "merge", "retry", "review", "campaign",
             "silent")
THREE = "pi,claude,codex"
HARNESS_EXECUTORS_OF = {"single": "pi", "retry": "pi", "campaign": "pi",
                        "review": "pi,claude", "silent": "pi"}


class ScenarioCase(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.repo = git_repo(self.tmp / "repo")

    def build(self, scenario: str, harness_executors: str | None = None, **extra):
        args = {"repo": str(self.repo), "scenario": scenario,
                "harness_executors": harness_executors or HARNESS_EXECUTORS_OF.get(scenario, THREE),
                "wt_root": str(self.tmp / "wt"), **extra}
        return validate(load_workflow(WORKFLOW, args))

    def steps(self, workflow) -> dict:
        return {s.id: s for _p, _i, _j, s in workflow.steps()}

    def harness_executor_of(self, workflow, step_id: str) -> str:
        return self.steps(workflow)[step_id].agent.harness_executor


class EveryScenarioBuilds(ScenarioCase):

    def test_each_scenario_builds_and_validates(self):
        for scenario in SCENARIOS:
            workflow = self.build(scenario)
            self.assertEqual(workflow.name, f"rollcall-{scenario}")
            self.assertTrue(list(workflow.steps()), scenario)

    def test_each_alias_builds_the_scenario_it_names(self):
        for alias, scenario in (("r0", "fanout"), ("r1", "relay"),
                                ("r2", "merge")):
            old, new = self.build(alias), self.build(scenario)
            self.assertEqual(list(self.steps(old)), list(self.steps(new)),
                             alias)

    def test_a_default_run_names_the_signed_in_and_pi_harness_executors(self):
        workflow = load_workflow(WORKFLOW, {"repo": str(self.repo), "scenario": "fanout",
                                            "wt_root": str(self.tmp / "wt")})
        self.assertEqual(list(self.steps(validate(workflow))),
                         ["pi-1", "claude-1", "codex-1"])


class Silent(ScenarioCase):

    def test_silent_sleeps_twice_the_stall_limit_and_gates_on_its_token(self):
        from ohflow.workflows.rollcall import SILENT_STALL_S, SILENT_TOKEN
        step = self.steps(self.build("silent"))["pi-1"]
        self.assertEqual(step.stall_timeout_s, SILENT_STALL_S)
        self.assertIn(f"time.sleep({2 * SILENT_STALL_S + 10})", step.agent.brief)
        texts = [c.args.get("text") for c in step.gate.checks if c.name == "file_contains"]
        self.assertIn(SILENT_TOKEN, texts)

    def test_silent_takes_the_stall_override(self):
        step = self.steps(self.build("silent", stall_timeout_s=20))["pi-1"]
        self.assertEqual(step.stall_timeout_s, 20)
        self.assertIn("time.sleep(50)", step.agent.brief)


class Scale(ScenarioCase):

    def test_count_gives_unique_step_ids_per_harness_executor(self):
        workflow = self.build("fanout", "pi,claude", count=3)
        ids = list(self.steps(workflow))
        self.assertEqual(ids, ["pi-1", "pi-2", "pi-3",
                               "claude-1", "claude-2", "claude-3"])
        self.assertEqual(len(set(ids)), 6)

    def test_every_agent_has_its_own_worktree(self):
        workflow = self.build("fanout", "pi,claude", count=2)
        self.assertEqual(len({s.worktree for s in self.steps(workflow).values()}),
                         4)

    def test_a_relay_shares_one_worktree_in_series(self):
        workflow = self.build("relay", "pi,claude", count=2)
        steps = self.steps(workflow)
        self.assertEqual({s.worktree for s in steps.values()}, {"relay"})
        self.assertEqual(steps["pi-2"].depends_on, ("pi-1",))

    def test_a_single_case_refuses_a_count_above_one(self):
        with self.assertRaisesRegex(Exception, "count 1"):
            self.build("single", count=2)


class RolesPickTheirHarnessExecutor(ScenarioCase):

    def test_the_consolidator_runs_on_the_harness_executor_asked_for(self):
        for harness_executor in ("pi", "codex"):
            workflow = self.build("merge", "pi,codex", consolidator=harness_executor)
            self.assertEqual(self.harness_executor_of(workflow, "consolidate"), harness_executor)

    def test_a_consolidator_outside_the_fanout_harness_executors_is_allowed(self):
        workflow = self.build("merge", "pi", consolidator="claude")
        self.assertEqual(self.harness_executor_of(workflow, "consolidate"), "claude")
        self.assertEqual(self.harness_executor_of(workflow, "pi-1"), "pi")

    def test_each_agent_merges_into_integration(self):
        workflow = self.build("merge", "pi,claude", count=2)
        merges = [s for s in self.steps(workflow).values() if s.kind == "merge"]
        self.assertEqual(len(merges), 4)
        self.assertEqual({m.worktree for m in merges}, {"integration"})

    def test_the_reviewer_runs_on_the_harness_executor_asked_for(self):
        workflow = self.build("review", "pi", reviewer="codex")
        self.assertEqual(self.harness_executor_of(workflow, "pi-1"), "pi")
        self.assertEqual(self.harness_executor_of(workflow, "reviewer"), "codex")

    def test_a_two_harness_executor_review_reads_agent_then_reviewer(self):
        workflow = self.build("review", "pi,claude")
        self.assertEqual(self.harness_executor_of(workflow, "pi-1"), "pi")
        self.assertEqual(self.harness_executor_of(workflow, "reviewer"), "claude")

    def test_the_reviewer_ends_with_a_verdict_line(self):
        workflow = self.build("review", "pi,claude")
        checks = {c.name: dict(c.args)
                  for c in self.steps(workflow)["reviewer"].gate.checks}
        self.assertIn("VERDICT", checks["final_message_matches"]["regex"])

    def test_the_judge_runs_on_the_harness_executor_asked_for(self):
        from ohflow.workflows.rollcall import judge_spec
        args = {"repo": str(self.repo), "scenario": "campaign", "harness_executors": "pi"}
        self.assertEqual(judge_spec({**args, "judge": "codex"}).harness_executor, "codex")
        self.assertEqual(judge_spec(args).harness_executor, "claude")
        self.assertEqual(judge_spec(args).model.model,
                         "claude-haiku-4-5-20251001")


class Refusals(ScenarioCase):

    def refused(self, pattern: str, scenario: str = "single", harness_executors: str = "pi",
                **extra) -> None:
        with self.assertRaisesRegex(Exception, pattern):
            self.build(scenario, harness_executors, **extra)

    def test_an_unknown_scenario_lists_the_scenarios(self):
        self.refused(r"unknown roll-call scenario 'triple'.*single.*fanout",
                     scenario="triple")

    def test_an_unknown_harness_executor_lists_the_harness_executors(self):
        self.refused(r"unknown roll-call harness executors \['gpt'\].*known", harness_executors="gpt")

    def test_an_unknown_consolidator_is_refused(self):
        self.refused(r"consolidator 'gpt' is not a harness executor", scenario="merge",
                     consolidator="gpt")

    def test_a_harness_executor_named_twice_points_at_count(self):
        self.refused(r"harness executor twice.*use count", scenario="fanout",
                     harness_executors="pi,pi")

    def test_a_bad_count_is_refused(self):
        self.refused(r"count must be 1 or more", scenario="fanout", count=0)
        self.refused(r"count must be a whole number", scenario="fanout",
                     count="many")

    def test_a_profile_other_than_hermetic_is_refused(self):
        self.refused(r"profile must be 'hermetic'", agent_profile="loose")

    def test_a_missing_repo_is_a_named_argument_error(self):
        from ohflow.workflow import WorkflowArgMissing
        with self.assertRaises(WorkflowArgMissing) as ctx:
            load_workflow(WORKFLOW, {"scenario": "single"})
        self.assertIn("repo", ctx.exception.message)


class Retry(ScenarioCase):

    def test_the_first_attempt_fails_on_a_token_the_brief_never_names(self):
        from ohflow.workflows.rollcall import RETRY_TOKEN
        step = self.steps(self.build("retry", "pi"))["pi-1"]
        self.assertNotIn(RETRY_TOKEN, step.agent.brief)
        gate = [c for c in step.gate.checks if c.name == "file_contains"]
        self.assertEqual(len(gate), 1)
        self.assertEqual(dict(gate[0].args)["text"], RETRY_TOKEN)

    def test_the_retry_policy_reads_that_one_gate_failure(self):
        step = self.steps(self.build("retry", "pi"))["pi-1"]
        self.assertEqual((step.retry.max, step.retry.on),
                         (1, ("gate:file_contains",)))
        self.assertFalse(step.retry.carry_context)

    def test_carry_context_reaches_the_policy(self):
        step = self.steps(self.build("retry", "claude",
                                     carry_context="true"))["claude-1"]
        self.assertTrue(step.retry.carry_context)


class Routes(ScenarioCase):

    def test_the_default_routes_are_the_cheap_ones(self):
        workflow = self.build("fanout", "pi,claude,codex")
        steps = self.steps(workflow)
        self.assertEqual(steps["pi-1"].agent.model.model, "zai/glm-5.3-flash")
        self.assertEqual(steps["claude-1"].agent.model.model,
                         "claude-haiku-4-5-20251001")
        codex = steps["codex-1"].agent.model
        self.assertEqual((codex.model, dict(codex.params)),
                         ("gpt-5.6-luna", {"reasoning_effort": "low"}))

    def test_config_overrides_a_harness_executor_and_keeps_the_rest(self):
        path = self.tmp / "route.json"
        path.write_text(json.dumps({"name": "other", "harness_executors": {
            "claude": {"model": "claude-sonnet-5"}}}), encoding="utf-8")
        steps = self.steps(self.build("fanout", "pi,claude",
                                      config=str(path)))
        self.assertEqual(steps["claude-1"].agent.model.model, "claude-sonnet-5")
        self.assertEqual(steps["pi-1"].agent.model.model, "zai/glm-5.3-flash")

    def test_a_config_with_an_unknown_harness_executor_or_key_is_refused(self):
        path = self.tmp / "bad.json"
        path.write_text(json.dumps({"harness_executors": {"gpt": {}}}), encoding="utf-8")
        self.refused_config(path, "unknown harness executor 'gpt'")
        path.write_text(json.dumps({"harness_executors": {"pi": {"colour": "red"}}}),
                        encoding="utf-8")
        self.refused_config(path, "may set only")

    def refused_config(self, path: Path, pattern: str) -> None:
        with self.assertRaisesRegex(Exception, pattern):
            self.build("single", "pi", config=str(path))

    def test_hermetic_reaches_claude_and_codex_only(self):
        workflow = self.build("fanout", "pi,claude,codex",
                              agent_profile="hermetic")
        got = {sid: s.agent.agent_profile for sid, s in self.steps(workflow).items()}
        self.assertEqual(got, {"pi-1": None, "claude-1": "hermetic",
                               "codex-1": "hermetic"})

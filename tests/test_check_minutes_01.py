from __future__ import annotations

import json

from ohflow import campaign, estimate
from ohflow.gates import (GateContext, GateReport, GateResult, check_seconds,
                          command_exit)
from support import TempCase, agent_step, simple_workflow
from test_estimate_01_prior_from_history import attempt, summary


class CommandExitRecordsItsTime(TempCase):

    def test_a_command_records_its_seconds_and_other_checks_record_none(self):
        d = self.tmp / "attempt"
        ctx = GateContext(coord="01.s/01.s", repo=self.tmp, worktree=self.tmp,
                          base_sha="", base_ref="main", attempt_dir=d,
                          log_dir=d / "logs")
        ran = command_exit(ctx, cmd="true")
        self.assertIsInstance(ran.duration_s, float)
        report = GateReport(coord="01.s/01.s", passed=True,
                            checks=[ran, GateResult("tree_clean", True)])
        checks = report.to_dict()["checks"]
        self.assertIn("duration_s", checks[0])
        self.assertNotIn("duration_s", checks[1])

    def test_check_seconds_sums_the_command_checks_only(self):
        gate = {"checks": [{"name": "command_exit", "duration_s": 600.0},
                           {"name": "command_exit", "duration_s": 30.5},
                           {"name": "tree_clean", "duration_s": 99.0},
                           {"name": "command_exit"}]}
        self.assertEqual(check_seconds(gate), 630.5)
        self.assertIsNone(check_seconds({"checks": [{"name": "tree_clean"}]}))


class TheEstimatePricesTheChecks(TempCase):

    def prior(self, *, gate: dict | None = None, step_wall: float | None = None):
        history = self.tmp / "history"
        path = summary(history / "runs" / "r1", "r1", [
            {"role": "implementer", "executor": "codex", "model": "m",
             "attempts": [attempt(300)]}])
        data = json.loads(path.read_text(encoding="utf-8"))
        step = data["phases"]["01.only"]["steps"]["01.only/01.s1"]
        if gate is not None:
            step["gate"] = gate
        if step_wall is not None:
            step["wall_seconds"] = step_wall
        path.write_text(json.dumps(data), encoding="utf-8")
        return estimate.Prior.from_history([history])

    def test_recorded_seconds_are_the_checks_of_the_step(self):
        prior = self.prior(gate={"checks": [{"name": "command_exit",
                                             "duration_s": 120.0}]},
                           step_wall=900.0)
        self.assertEqual(prior.lookup("implementer", "codex", "m").checks.p50, 120.0)

    def test_without_recorded_seconds_the_step_less_its_agent_is_the_checks(self):
        prior = self.prior(step_wall=900.0)
        self.assertEqual(prior.lookup("implementer", "codex", "m").checks.p50, 600.0)

    def test_the_estimate_tables_carry_a_checks_column(self):
        workflow = simple_workflow(self.tmp, steps=[agent_step("a")])
        data = estimate.estimate_workflow(workflow, self.prior(step_wall=900.0))
        self.assertEqual(data["run"]["checks_s"]["p50"], 600)
        text = estimate.render_text(data)
        self.assertIn("checks ~10 min", text.splitlines()[0])
        self.assertIn("| phase | agents | p50 | p80 | checks p50 |", text)
        self.assertIn("| step | p50 | p80 | checks p50 |", text)


class TheJudgeIsToldThePriceOfARound(TempCase):

    def test_the_role_names_the_rounds_minutes_from_the_estimate(self):
        self.assertIn("A REVISE costs one more round,\n{round_minutes} by the "
                      "estimate in this packet.", campaign.JUDGE_ROLE)
        run = self.tmp / "run"
        estimate.write_estimate(run, {"schema": estimate.SCHEMA,
                                      "run": {"wall_s": {"p50": 1008},
                                              "checks_s": {"p50": 192}}})
        self.assertEqual(campaign.round_minutes(run), "about 20 minutes")
        self.assertEqual(campaign.round_minutes(self.tmp / "none"),
                         "an unknown number of minutes")

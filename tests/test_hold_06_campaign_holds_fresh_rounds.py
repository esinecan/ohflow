"""`campaign run --hold` holds the first fresh round, and never a resume after
an interruption.

A later fresh round, and a round that a judge's REVISE starts, go ahead unless
the estimate exceeds the first round's actual minutes by half. A held round is
named in `campaign-status.json` with the go command, and the status reads
`running` again once go arrives.
"""

from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))

from ohflow import campaign as oc  # noqa: E402
from ohflow import cli, live, rundir, supervisor  # noqa: E402
from ohflow.supervisor import RunOutcome  # noqa: E402
from pilot_support import start_in_thread, wait_until  # noqa: E402
from support import (AgentScript, FakeHarnessExecutor,  # noqa: E402
                     install_fake_harness_executor)
from test_campaign_01_loop import (JUDGE_STEP, PRODUCT_STEP,  # noqa: E402
                                   CampaignCase, decision)

HOLD_JOIN_S = 60.0


class CampaignHoldsFreshRounds(CampaignCase):

    def setUp(self) -> None:
        super().setUp()
        self.captured: list = []

        def fake_run_workflow(workflow, run_dir, options):
            self.captured.append(options)
            return RunOutcome(Path(run_dir), "finished",
                              summary={"status": "finished", "phases": {}})

        original = oc.run_workflow
        self.real_run_workflow = original
        oc.run_workflow = fake_run_workflow
        self.addCleanup(setattr, oc, "run_workflow", original)

    def controller(self, hold: bool) -> oc.CampaignController:
        return oc.CampaignController(self.campaign(), no_dashboard=True,
                                     hold=hold, say=lambda _m: None,
                                     harness_executors=self.harness_executors)

    def test_a_fresh_round_holds_and_a_resumed_round_does_not(self):
        controller = self.controller(hold=True)
        m = controller.camp.milestones[0]
        workflow = controller._load_workflow(m, 1)
        run_dir = self.root / m.dir / "runs" / m.id

        controller._run_workflow(m, workflow, run_dir, 1)
        self.assertTrue(self.captured[0].hold)
        status = json.loads((self.root / oc.STATUS).read_text(encoding="utf-8"))
        self.assertEqual(status["state"], "held")
        self.assertIn("-m ohflow.cli go --run", status["go"])

        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run-log.jsonl").write_text("", encoding="utf-8")
        controller._run_workflow(m, workflow, run_dir, 2)
        self.assertFalse(self.captured[1].hold,
                         "a resumed round already started; it cannot hold")

    def later_round(self, estimate_s):
        controller = self.controller(hold=True)
        controller.campaign_log.append("judged", milestone="m1", round=1,
                                       decision="REVISE", round_s=600.0)
        controller._round_estimate_s = lambda _workflow: estimate_s
        m = controller.camp.milestones[0]
        workflow = controller._load_workflow(m, 2)
        controller._run_workflow(m, workflow, self.root / m.dir / "runs" / "fresh", 2)
        return self.captured[-1].hold

    def test_a_later_round_within_half_again_of_the_first_goes_ahead(self):
        self.assertFalse(self.later_round(900.0))

    def test_a_later_round_past_half_again_of_the_first_holds(self):
        self.assertTrue(self.later_round(901.0))

    def test_a_later_round_without_an_estimate_holds(self):
        self.assertTrue(self.later_round(None))

    def test_without_the_flag_no_round_holds(self):
        controller = self.controller(hold=False)
        m = controller.camp.milestones[0]
        workflow = controller._load_workflow(m, 1)
        controller._run_workflow(m, workflow, self.root / m.dir / "runs" / m.id, 1)
        self.assertFalse(self.captured[0].hold)

    def status(self) -> dict:
        path = self.root / oc.STATUS
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def test_go_releases_the_round_and_the_status_reads_running(self):
        oc.run_workflow = self.real_run_workflow
        install_fake_harness_executor(self, FakeHarnessExecutor(
            default=AgentScript()))
        original_poll = supervisor.HOLD_POLL_S
        supervisor.HOLD_POLL_S = 0.02
        self.addCleanup(setattr, supervisor, "HOLD_POLL_S", original_poll)
        controller = self.controller(hold=True)
        m = controller.camp.milestones[0]
        workflow = controller._load_workflow(m, 1)
        run_dir = self.root / m.dir / "runs" / m.id

        thread, result = start_in_thread(
            lambda: controller._run_workflow(m, workflow, run_dir, 1))
        self.assertTrue(wait_until(lambda: self.status().get("state") == "held"
                                   and (run_dir / rundir.HOLD_FILE).exists()),
                        "the campaign never held the round")
        self.assertIn("-m ohflow.cli go --run", self.status()["go"])

        (run_dir / rundir.GO_FILE).write_text("go\n", encoding="utf-8")
        thread.join(HOLD_JOIN_S)
        self.assertFalse(thread.is_alive(), "the round did not release on go")
        self.assertNotIn("error", result, result.get("error"))

        status = self.status()
        self.assertEqual(status["state"], "running")

    def test_an_interrupted_rounds_resume_does_not_hold(self):
        controller = self.controller(hold=True)
        controller._round_estimate_s = lambda _workflow: None
        m = controller.camp.milestones[0]
        run_dir = self.root / m.dir / "runs" / m.id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run-log.jsonl").write_text("", encoding="utf-8")
        log = controller.campaign_log
        log.append("milestone_started", milestone=m.id, index=1, run_dir=str(run_dir))
        log.append("judged", milestone=m.id, round=1, decision="REVISE",
                   summary="REVISE summary", findings=[], revisions=[],
                   question=None, judge_dir=None, handover=None, packet=None,
                   round_s=600.0)
        log.append("revision_committed", milestone=m.id, round=1, commit="0" * 40)
        controller._judge = lambda _m, _r, _p: (None, None, self.tmp / "judge")

        state = oc.replay(controller.camp)[m.id]
        self.assertEqual(controller._milestone(1, m, state), oc.EXIT_ESCALATED)
        self.assertEqual(len(self.captured), 1)
        self.assertFalse(self.captured[0].hold,
                         "round 2 started before the interruption; its resume "
                         "cannot hold")

    def test_a_revise_round_under_pilot_holds_and_pilots_nothing(self):
        controller = oc.CampaignController(self.campaign(), no_dashboard=True,
                                           hold=True, pilot=True,
                                           say=lambda _m: None,
                                           harness_executors=self.harness_executors)
        m = controller.camp.milestones[0]
        workflow = controller._load_workflow(m, 2)
        run_dir = self.root / m.dir / "runs" / m.id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run-log.jsonl").write_text("", encoding="utf-8")
        controller._run_workflow(m, workflow, run_dir, 2, revised=True)
        options = self.captured[0]
        self.assertTrue(options.hold)
        self.assertTrue(options.hold_resume)
        self.assertFalse(options.pilot)


class ARoundAfterAReviseHolds(CampaignCase):

    def setUp(self) -> None:
        super().setUp()
        original_poll = supervisor.HOLD_POLL_S
        supervisor.HOLD_POLL_S = 0.02
        self.addCleanup(setattr, supervisor, "HOLD_POLL_S", original_poll)

    def held_round(self) -> int | None:
        path = self.root / oc.STATUS
        if not path.exists():
            return None
        status = json.loads(path.read_text(encoding="utf-8"))
        return status.get("round") if status.get("state") == "held" else None

    def test_a_revise_round_holds_and_go_releases_it(self):
        product = AgentScript(final_text="DONE\n")
        edit = lambda: (self.mdir / "briefs" / "impl.md").write_text(  # noqa
            "Do the thing, and X.\n", encoding="utf-8")
        judge = self.judge(
            [decision("REVISE", revisions=[{"path": "milestones/m1/briefs/impl.md",
                                            "why": "adds X"}]),
             decision("PASS")],
            edits={1: edit})
        install_fake_harness_executor(self, FakeHarnessExecutor(
            scripts={PRODUCT_STEP: product, JUDGE_STEP: judge}))
        controller = oc.CampaignController(self.campaign(), no_dashboard=True,
                                           hold=True, say=lambda _m: None,
                                           harness_executors=self.harness_executors)
        controller._round_estimate_s = lambda _workflow: None
        m = controller.camp.milestones[0]
        run_dir = self.root / m.dir / "runs" / m.id

        thread, result = start_in_thread(controller.run)
        for round_no in (1, 2):
            self.assertTrue(wait_until(lambda: self.held_round() == round_no
                                       and rundir.hold_alive(run_dir),
                                       timeout=HOLD_JOIN_S),
                            f"round {round_no} never held")
            self.assertFalse((run_dir / rundir.GO_FILE).exists(),
                             "an earlier round's go must not release this hold")
            self.assertEqual(product.launches, round_no - 1)
            if round_no == 2:
                self.assertEqual(judge.launches, 1)
                self.assertEqual(rundir.open_run(run_dir).status, rundir.HELD)
                self.assertEqual(live.read_out(run_dir)["run"]["status"],
                                 rundir.HELD)
            self.assertEqual(cli.cmd_go(Namespace(run=str(run_dir),
                                                  predictions=None)),
                             cli.EXIT_OK)
        thread.join(HOLD_JOIN_S)
        self.assertFalse(thread.is_alive(), "the revise round did not release on go")
        self.assertNotIn("error", result, result.get("error"))
        self.assertEqual(result["outcome"], oc.EXIT_DELIVERED)
        self.assertEqual(product.launches, 2)
        self.assertFalse((run_dir / rundir.HOLD_FILE).exists())


if __name__ == "__main__":
    import unittest
    unittest.main()

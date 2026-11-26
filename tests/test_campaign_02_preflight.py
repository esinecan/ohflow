"""A milestone run that fails preflight stops the campaign without a judge.

Before: a run that stopped on a preflight fault was judged like a run that
had worked and failed. The judge read a run that never ran, and the campaign
spent a revision on it.
Now: the controller stops at once. `ESCALATION.md` and `campaign-status.json` carry
the problem, the campaign log gets a `preflight_failed` event, no judge launches and
no revision is spent. The milestone stays `running`, so the next `campaign
run` starts the same round again. Each round loads the milestone workflow once.
"""

from __future__ import annotations

import json
from unittest import mock

from ohflow import campaign as oc
from support import FakeHarnessExecutor, AgentScript

from test_campaign_01_loop import (JUDGE_STEP, PRODUCT_STEP, CampaignCase,
                                   decision)

PROBLEM = "the model endpoint is down: PREFLIGHT-MARKER"


class BrokenHarnessExecutor(FakeHarnessExecutor):

    def preflight(self) -> list[str]:
        return [PROBLEM]


class CampaignPreflightStopsTheCampaign(CampaignCase):

    def broken_drive(self, judge: AgentScript) -> int:
        self.broken_product = AgentScript(final_text="DONE\n")
        harness_executor = BrokenHarnessExecutor(scripts={PRODUCT_STEP: self.broken_product,
                                                          JUDGE_STEP: judge})
        return self.drive(self.campaign(), harness_executor)

    def test_campaign_preflight_fault_stops_without_a_judge(self):
        judge = self.judge([decision("PASS")])
        code = self.broken_drive(judge)

        self.assertEqual(code, oc.EXIT_ESCALATED)
        self.assertEqual(judge.launches, 0, "a judge read a run that never ran")
        self.assertEqual(self.broken_product.launches, 0)
        self.assertEqual(self.events(), ["campaign_started",
                                         "milestone_started",
                                         "preflight_failed"])

    def test_campaign_preflight_fault_is_written_where_the_operator_looks(self):
        self.broken_drive(self.judge([decision("PASS")]))

        escalation = (self.root / oc.ESCALATION).read_text(encoding="utf-8")
        self.assertIn("ACTION NEEDED FROM THE OPERATOR", escalation)
        self.assertIn("PREFLIGHT-MARKER", escalation)
        self.assertIn("no revision was spent", escalation)
        status = json.loads((self.root / oc.STATUS).read_text(encoding="utf-8"))
        self.assertEqual(status["state"], "preflight_failed")
        self.assertEqual(status["milestone"], "m1")
        self.assertTrue(any("PREFLIGHT-MARKER" in line
                            for line in status["problems"]))

    def test_campaign_preflight_fault_spends_no_revision_and_loads_the_workflow_once(self):
        loads = []
        real = oc.load_workflow

        def counting(path, args=None):
            loads.append(str(path))
            return real(path, args)

        with mock.patch.object(oc, "load_workflow", counting):
            self.broken_drive(self.judge([decision("PASS")]))

        state = oc.replay(self.campaign())["m1"]
        self.assertEqual(state.status, "running")
        self.assertEqual(state.judgements, 0)
        self.assertEqual(state.revisions, 0)
        self.assertEqual(len(loads), 1, loads)

    def test_campaign_preflight_rerun_retries_the_same_round(self):
        self.broken_drive(self.judge([decision("PASS")]))

        product = AgentScript(final_text="DONE\n")
        judge = self.judge([decision("PASS")])
        healthy = FakeHarnessExecutor(scripts={PRODUCT_STEP: product, JUDGE_STEP: judge})
        code = self.drive(self.campaign(), healthy)

        self.assertEqual(code, oc.EXIT_DELIVERED)
        self.assertEqual(product.launches, 1)
        self.assertEqual(judge.launches, 1)
        events = self.events()
        self.assertEqual(events.count("milestone_started"), 1,
                         "the rerun started the milestone over")
        self.assertEqual(events[-3:], ["judged", "milestone_landed",
                                       "campaign_delivered"])
        judged = [e for e in oc.CampaignLog(self.root).events()
                  if e["event"] == "judged"]
        self.assertEqual([e["round"] for e in judged], [1])
        self.assertFalse((self.root / oc.ESCALATION).exists())
        kept = self.mdir / "runs" / "m1.not-started-01"
        self.assertTrue(kept.is_dir(), "the failed start's evidence is gone")
        self.assertTrue((self.mdir / "runs" / "m1" / "run-log.jsonl").exists())


if __name__ == "__main__":
    import unittest
    unittest.main()

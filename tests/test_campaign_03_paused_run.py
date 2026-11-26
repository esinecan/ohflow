"""A milestone run that pauses on a transient failure stops the campaign without a judge.

Before: a run whose steps were deferred by a rate limit ended `paused`, and the
controller judged it like a run that had worked and failed. In the cdp-mode
campaign (m1b, 2026-10-03) the implementer hit Z.AI's 5-hour usage limit after
21 minutes, the run paused, every functional acceptance check failed, and an Opus
judge started on work that never got done. A decision there spends a revision
on the provider's fault.
Now: the controller stops at once. `ESCALATION.md` and `campaign-status.json` name
the deferred steps and the provider's own error text (which carries the reset
time), the campaign log gets a `run_paused` event, no judge launches and no revision
is spent. The milestone stays `running`, so the next `campaign run` resumes the
same round and its deferred steps.
"""

from __future__ import annotations

import json

from ohflow import campaign as oc
from support import FakeHarnessExecutor, AgentScript

from test_campaign_01_loop import (JUDGE_STEP, PRODUCT_STEP, CampaignCase,
                                   decision)

#: The error text of the real m1b implement attempts.
LIMIT = ('429: {"code":"1308","message":"Usage limit reached for 5 hour. '
         'Your limit will reset at 2026-10-03 13:10:59"}')


class CampaignPausedRunStopsTheCampaign(CampaignCase):

    def drive_with(self, product: AgentScript, judge: AgentScript) -> int:
        harness_executor = FakeHarnessExecutor(scripts={PRODUCT_STEP: product, JUDGE_STEP: judge})
        return self.drive(self.campaign(), harness_executor)

    def test_campaign_paused_run_stops_without_a_judge(self):
        judge = self.judge([decision("PASS")])
        code = self.drive_with(AgentScript(error=LIMIT), judge)

        self.assertEqual(code, oc.EXIT_ESCALATED)
        self.assertEqual(judge.launches, 0,
                         "a judge read a run whose steps never got an answer")
        self.assertEqual(self.events(), ["campaign_started",
                                         "milestone_started",
                                         "run_paused"])

    def test_campaign_paused_run_names_the_provider_error_where_the_operator_looks(self):
        self.drive_with(AgentScript(error=LIMIT), self.judge([decision("PASS")]))

        escalation = (self.root / oc.ESCALATION).read_text(encoding="utf-8")
        self.assertIn("ACTION NEEDED FROM THE OPERATOR", escalation)
        self.assertIn("Usage limit reached for 5 hour", escalation)
        self.assertIn("2026-10-03 13:10:59", escalation)
        self.assertIn("no revision was spent", escalation)
        status = json.loads((self.root / oc.STATUS).read_text(encoding="utf-8"))
        self.assertEqual(status["state"], "paused")
        self.assertEqual(status["milestone"], "m1")
        self.assertTrue(any("Usage limit reached" in line
                            for line in status["problems"]))

    def test_campaign_paused_run_spends_no_revision_and_resumes_the_same_round(self):
        product = AgentScript(sequence=[{"error": LIMIT}, {"error": None}])
        judge = self.judge([decision("PASS")])
        self.drive_with(product, judge)

        state = oc.replay(self.campaign())["m1"]
        self.assertEqual(state.status, "running")
        self.assertEqual(state.judgements, 0)
        self.assertEqual(state.revisions, 0)

        code = self.drive_with(product, judge)
        self.assertEqual(code, oc.EXIT_DELIVERED)
        self.assertEqual(judge.launches, 1)
        judged = [e for e in oc.CampaignLog(self.root).events()
                  if e["event"] == "judged"]
        self.assertEqual([e["round"] for e in judged], [1])

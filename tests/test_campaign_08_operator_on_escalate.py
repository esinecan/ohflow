"""An escalation reaches the operator through the `operator.on_escalate` setting.

Before: only a campaign's own `Campaign.on_escalate` ran on an escalation, and
`ohflow construct` writes a campaign with none, so the campaign the operator
actually starts wrote `ESCALATION.md` and told nobody: the managing session had
to relay each escalation in chat, which `references/local.md` asks of no
campaign. The alert command belongs to the operator, not to each campaign.
Now: every escalation path in the controller - the judge's ESCALATE and every
refusal, the run that did not start, the run that paused - runs
`operator.on_escalate` from the operator settings when the campaign names no
command of its own, with `{file}` replaced by the escalation file's path. A
campaign's own `on_escalate` still wins.
"""

from __future__ import annotations

import json

from ohflow import campaign as oc
from ohflow import settings
from support import FakeHarnessExecutor, AgentScript, use_settings

from test_campaign_01_loop import (JUDGE_STEP, PRODUCT_STEP, CampaignCase,
                                   decision)
from test_campaign_02_preflight import BrokenHarnessExecutor
from test_campaign_03_paused_run import LIMIT

OPERATOR_ALERT = "cp {file} operator-alerted.md"
CAMPAIGN_ALERT = "cp {file} campaign-alerted.md"


class OperatorOnEscalate(CampaignCase):

    def escalated_campaign(self, **kw) -> int:
        judge = self.judge([decision("ESCALATE")])
        harness_executor = FakeHarnessExecutor(scripts={JUDGE_STEP: judge})
        return self.drive(self.campaign(**kw), harness_executor)

    def alerted(self, name: str) -> str:
        return (self.root / name).read_text(encoding="utf-8")

    def test_the_base_file_names_the_setting_null(self):
        base = json.loads(settings.BASE_FILE.read_text(encoding="utf-8"))
        self.assertIsNone(base["operator"]["on_escalate"])

    def test_the_operators_command_runs_where_a_campaign_names_none(self):
        use_settings(self, {"operator": {"on_escalate": OPERATOR_ALERT}})
        code = self.escalated_campaign()

        self.assertEqual(code, oc.EXIT_ESCALATED)
        self.assertEqual(self.alerted("operator-alerted.md"),
                         (self.root / oc.ESCALATION).read_text(encoding="utf-8"))

    def test_the_campaigns_own_command_wins(self):
        use_settings(self, {"operator": {"on_escalate": OPERATOR_ALERT}})
        code = self.escalated_campaign(on_escalate=CAMPAIGN_ALERT)

        self.assertEqual(code, oc.EXIT_ESCALATED)
        self.assertEqual(self.alerted("campaign-alerted.md"),
                         (self.root / oc.ESCALATION).read_text(encoding="utf-8"))
        self.assertFalse((self.root / "operator-alerted.md").exists())

    def test_a_run_that_did_not_start_runs_the_operators_command(self):
        use_settings(self, {"operator": {"on_escalate": OPERATOR_ALERT}})
        product = AgentScript(final_text="DONE\n")
        harness_executor = BrokenHarnessExecutor(
            scripts={PRODUCT_STEP: product, JUDGE_STEP: self.judge([decision("PASS")])})
        code = self.drive(self.campaign(), harness_executor)

        self.assertEqual(code, oc.EXIT_ESCALATED)
        self.assertEqual(product.launches, 0)
        self.assertEqual(self.alerted("operator-alerted.md"),
                         (self.root / oc.ESCALATION).read_text(encoding="utf-8"))

    def test_a_run_that_paused_runs_the_operators_command(self):
        use_settings(self, {"operator": {"on_escalate": OPERATOR_ALERT}})
        judge = self.judge([decision("PASS")])
        harness_executor = FakeHarnessExecutor(
            scripts={PRODUCT_STEP: AgentScript(error=LIMIT), JUDGE_STEP: judge})
        code = self.drive(self.campaign(), harness_executor)

        self.assertEqual(code, oc.EXIT_ESCALATED)
        self.assertEqual(judge.launches, 0)
        self.assertEqual(self.alerted("operator-alerted.md"),
                         (self.root / oc.ESCALATION).read_text(encoding="utf-8"))


if __name__ == "__main__":
    import unittest
    unittest.main()

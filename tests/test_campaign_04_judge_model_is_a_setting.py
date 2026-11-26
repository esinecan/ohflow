"""The default judge runs on the operator setting `campaign.judge_model`, a tier or a model.

Before: `campaign.py` pinned the default judge to one model id in a module
constant, and later the shipped base file held that id. The Claude CLI 2.1.258
refused it and takes the alias instead.
Now: `default_judge()` reads `campaign.judge_model` each time a `Campaign`
names no judge. The shipped base file holds the tier `heavy`, which the
`claude` harness executor resolves through `tiers.heavy.claude`, the alias
`opus` on the base settings. An operator may name another tier or a model id.
A campaign or a milestone that names its own judge does not read the setting.

A value that is not a non-empty string is refused when the campaign is built.
Before: the judge started with an empty or made-up model name, and the fault
showed only after the milestone's run was paid for.
"""

from __future__ import annotations

import json

from ohflow import campaign as oc
from ohflow import settings
from ohflow.workflow import WorkflowError
from support import use_settings
from verb_support import call

from test_campaign_01_loop import CampaignCase

BASE_MODEL = "heavy"
OPERATOR_MODEL = "claude-operator-choice"

CAMPAIGN_PY = """
from pathlib import Path
from ohflow.campaign import Campaign, Milestone

def build(args):
    return Campaign(
        name="t", root=Path(args.get("root")), repo=Path(args.get("product")),
        charter="charter.md", integration_branch="integration-branch",
        milestones=(Milestone(id="m1", title="the first milestone",
                              workflow="milestones/m1/workflow.py",
                              spec="milestones/m1/spec.md"),))
"""


class JudgeModelIsASetting(CampaignCase):

    def default_campaign(self) -> oc.Campaign:
        named = self.campaign()
        return oc.Campaign(name="t", root=self.root, repo=self.product,
                           charter="charter.md", milestones=named.milestones,
                           integration_branch="integration-branch", auto_resume=0)

    def judge_step(self, camp: oc.Campaign):
        m = camp.milestones[0]
        packet = self.mdir / "judge" / "r01" / "packet.md"
        packet.parent.mkdir(parents=True, exist_ok=True)
        packet.write_text("PACKET-MARKER\n", encoding="utf-8")
        controller = oc.CampaignController(camp, no_dashboard=True, say=lambda _: None)
        workflow = controller._judge_workflow(m, 1, packet, self.handover(1))
        return workflow.phases[0].steps[0]

    def test_base_file_names_the_judge_model(self):
        base = json.loads(settings.BASE_FILE.read_text(encoding="utf-8"))
        self.assertEqual(base["campaign"]["judge_model"], BASE_MODEL)

    def test_default_judge_runs_on_the_base_model_without_a_local_value(self):
        judge = self.default_campaign().judge
        self.assertEqual(judge.model.model, BASE_MODEL)
        self.assertEqual(judge.harness_executor, "claude")
        self.assertEqual(judge.model.params, {"effort": "high"})
        self.assertEqual(judge.role, "milestone-judge")

    def test_default_judge_runs_on_the_operators_model(self):
        use_settings(self, {"campaign": {"judge_model": OPERATOR_MODEL}})
        self.assertEqual(oc.judge_model(), OPERATOR_MODEL)
        camp = self.default_campaign()
        self.assertEqual(camp.judge.model.model, OPERATOR_MODEL)
        step = self.judge_step(camp)
        self.assertEqual(step.agent.model.model, OPERATOR_MODEL)
        self.assertEqual(step.agent.harness_executor, "claude")
        self.assertIn("PACKET-MARKER", step.agent.brief)

    def test_a_local_null_keeps_the_base_model(self):
        use_settings(self, {"campaign": {"judge_model": None}})
        self.assertEqual(self.default_campaign().judge.model.model, BASE_MODEL)

    def test_a_value_that_names_no_model_is_refused(self):
        for bad in ("", "   ", 7, ["claude-opus-5-5"], {"model": "x"}, False):
            use_settings(self, {"campaign": {"judge_model": bad}})
            with self.assertRaises(settings.SettingsError, msg=repr(bad)) as raised:
                self.default_campaign()
            self.assertIn("campaign.judge_model", str(raised.exception))
            self.assertIn(repr(bad), str(raised.exception))

    def test_a_bad_value_does_not_stop_a_campaign_that_names_its_judge(self):
        use_settings(self, {"campaign": {"judge_model": ""}})
        self.assertEqual(self.campaign().judge.harness_executor, "pi")

    def test_campaign_validate_names_the_bad_setting_before_anything_runs(self):
        file = self.root / "campaign.py"
        file.write_text(CAMPAIGN_PY, encoding="utf-8")
        args = {"root": str(self.root), "product": str(self.product)}
        self.assertEqual(oc.load_campaign(file, args).judge.model.model, BASE_MODEL)
        use_settings(self, {"campaign": {"judge_model": ""}})
        with self.assertRaises(WorkflowError) as raised:
            oc.load_campaign(file, args)
        self.assertIn("campaign.judge_model", str(raised.exception))
        code, lines = call("campaign", "validate", "--campaign", file,
                           "--args", f"root={self.root}",
                           "--args", f"product={self.product}")
        self.assertEqual(code, 2, lines)
        self.assertEqual(lines[0], "WORKFLOW INVALID")
        self.assertIn("campaign.judge_model must name a model", lines[1])
        self.assertFalse([ln for ln in lines if "Traceback" in ln], lines)

    def test_a_named_judge_does_not_read_the_setting(self):
        use_settings(self, {"campaign": {"judge_model": OPERATOR_MODEL}})
        camp = self.campaign()
        self.assertEqual(camp.judge.harness_executor, "pi")
        self.assertNotEqual(camp.judge.model.model, OPERATOR_MODEL)
        self.assertEqual(self.judge_step(camp).agent.model, camp.judge.model)


if __name__ == "__main__":
    import unittest
    unittest.main()

"""Defect 49: a watcher's cursor file counted as a judge's stray edit.

What went wrong. `ohflow campaign watch` keeps its cursor in
`<campaign root>/.watch.<name>.json`. While judge r01 of milestone m7 ran, the
campaign supervisor polled with that verb, as SKILL.md tells agents to do. The
controller's `_stray_edits` read `git status`, saw the new cursor file outside the
milestone directory, blamed the judge, refused its REVISE and escalated with
"the judge changed files outside its write scope: .watch.agent.json".

What is asserted here. A fake harness executor campaign has a judge that REVISEs. A
`campaign watch` call runs between the judge's start and its decision. The
revision commits, the milestone is delivered, no escalation is written, and the
cursor file is ignored by git.
"""

from __future__ import annotations

from ohflow import campaign as oc
from ohflow import watch
from support import FakeHarnessExecutor, AgentScript
from test_campaign_01_loop import (JUDGE_STEP, PRODUCT_STEP, CampaignCase, _git,
                                   decision)


class WatcherCursorIsNotAStrayEdit(CampaignCase):

    def test_a_watch_during_the_judge_does_not_escalate_a_revise(self):
        camp = self.campaign()
        product = AgentScript(final_text="DONE\n")

        def revise_while_watched():
            (self.mdir / "briefs" / "impl.md").write_text(
                "Do the thing, and X.\n", encoding="utf-8")
            watch.watch_campaign(camp, timeout=0)

        judge = self.judge(
            [decision("REVISE", revisions=[
                {"path": "milestones/m1/briefs/impl.md", "why": "adds X"}]),
             decision("PASS")],
            edits={1: revise_while_watched})
        harness_executor = FakeHarnessExecutor(scripts={PRODUCT_STEP: product, JUDGE_STEP: judge})

        code = self.drive(camp, harness_executor)

        self.assertTrue((self.root / ".watch.agent.json").is_file(),
                        "the watch must have written its cursor")
        self.assertEqual(code, oc.EXIT_DELIVERED)
        self.assertNotIn("escalated", self.events())
        self.assertFalse((self.root / oc.ESCALATION).exists())
        self.assertIn("revision_committed", self.events())
        self.assertNotIn(".watch.agent.json",
                         _git(self.root, "status", "--porcelain"))


if __name__ == "__main__":
    import unittest
    unittest.main()

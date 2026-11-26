"""`campaign-status.json` names the dashboard that serves while a run is live.

Before: the controller wrote the status file before it started each run, so the
file never held a URL. `ohflow campaign watch` found the URL by reading run
directories, and any other reader of the file saw none.
Now: the controller writes the file again as soon as the dashboard of the
milestone run, and then of the judge run, serves. The test drives a whole
campaign and reads the file from inside each run.
"""

from __future__ import annotations

import json

from ohflow import campaign as oc
from support import FakeHarnessExecutor, AgentScript, install_fake_harness_executor, quiet

from test_campaign_01_loop import (JUDGE_STEP, PRODUCT_STEP, CampaignCase,
                                   decision)


class TheStatusFileNamesTheServingDashboard(CampaignCase):

    def read_status(self) -> dict:
        return json.loads((self.root / oc.STATUS).read_text(encoding="utf-8"))

    def served_url(self, run_dir) -> str:
        record = json.loads((run_dir / "dashboard.json").read_text(
            encoding="utf-8"))
        return record["url"]

    def test_status_names_the_milestone_dashboard_then_the_judge_dashboard(self):
        camp = self.campaign()
        m = camp.milestones[0]
        milestone_run = self.root / m.dir / "runs" / m.id
        judge_run = oc.judge_run_dir(self.root, m, 1)
        seen: dict[str, dict] = {}

        product = AgentScript(final_text="DONE\n")
        product.on_poll = lambda: seen.setdefault("product", {
            **self.read_status(), "served": self.served_url(milestone_run)})
        judge = self.judge([decision("PASS")])
        write_handover = judge.on_poll

        def judge_poll():
            seen.setdefault("judge", {
                **self.read_status(), "served": self.served_url(judge_run)})
            return write_handover()

        judge.on_poll = judge_poll
        install_fake_harness_executor(self, FakeHarnessExecutor(scripts={PRODUCT_STEP: product,
                                                                         JUDGE_STEP: judge}))
        with quiet():
            code = oc.CampaignController(camp, no_dashboard=False,
                                         say=lambda _m: None,
                                         harness_executors=self.harness_executors).run()

        self.assertEqual(code, oc.EXIT_DELIVERED)
        self.assertEqual(seen["product"]["state"], "running")
        self.assertEqual(seen["product"].get("dashboard"),
                         seen["product"]["served"])
        self.assertEqual(seen["judge"]["state"], "judging")
        self.assertEqual(seen["judge"].get("dashboard"),
                         seen["judge"]["served"])
        self.assertNotEqual(seen["judge"]["served"],
                            seen["product"]["served"])


if __name__ == "__main__":
    import unittest
    unittest.main()

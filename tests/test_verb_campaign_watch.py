"""m4: `ohflow campaign watch` prints the campaign's status, then one line per
campaign log event since this watcher's last call.

The cursor lives in the campaign root, under a name. Exit codes follow `watch`:
0 delivered, 1 ended otherwise, 10 still going.
"""

from __future__ import annotations

import json
import textwrap

from dashboard_support import G1_RUN, RunLog, copy_tree, workflow_json, agent
from ohflow import campaign as oc
from ohflow import runstatus, watch
from support import TempCase
from verb_support import call, live_child

CAMPAIGN_PY = """
from pathlib import Path
from ohflow.campaign import Campaign, Milestone

def build(args):
    root = Path(args["root"])
    m = Milestone(id="m1", title="the first", workflow="milestones/m1/workflow.py",
                  spec="milestones/m1/spec.md")
    return Campaign(name="demo", root=root, repo=root, charter="charter.md",
                    milestones=(m,), integration_branch="integration_branch")
"""


class CampaignCase(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.root = self.tmp / "camp"
        self.root.mkdir()
        self.file = self.tmp / "campaign.py"
        self.file.write_text(textwrap.dedent(CAMPAIGN_PY), encoding="utf-8")
        self.campaign_log = oc.CampaignLog(self.root)

    def watch(self, *extra):
        return call("campaign", "watch", "--campaign", self.file.as_posix(),
                    "--args", f"root={self.root.as_posix()}", "--timeout", 0,
                    *extra)


class CampaignWatch(CampaignCase):

    def test_campaign_watch_reports_each_event_once_and_the_status_first(self):
        self.campaign_log.append("campaign_started", milestones=["m1"])
        self.campaign_log.append("milestone_started", milestone="m1",
                                 run_dir=str(self.tmp / "no-run"))
        code, first = self.watch()
        self.assertEqual(code, watch.EXIT_GOING)
        self.assertRegex(first[0], r"^demo: 0 of 1 milestones passed, m1 running")
        self.assertIn("m1 started", first)
        self.assertLessEqual(len(first), 6)

        self.campaign_log.append("judged", milestone="m1", round=1,
                                 decision="REVISE", summary="the brief lacks X")
        code, second = self.watch()
        self.assertEqual(code, watch.EXIT_GOING)
        self.assertEqual(second[1:], ["m1 judged round 1: REVISE - the "
                                      "brief lacks X"])

    def test_campaign_watch_a_delivered_campaign_exits_0(self):
        self.campaign_log.append("campaign_started", milestones=["m1"])
        self.campaign_log.append("milestone_started", milestone="m1",
                                 run_dir=str(self.tmp / "no-run"))
        self.campaign_log.append("milestone_landed", milestone="m1")
        self.campaign_log.append("campaign_delivered")
        code, lines = self.watch()
        self.assertEqual(code, watch.EXIT_ENDED_GOOD)
        self.assertRegex(lines[0], r"^demo: 1 of 1 milestones passed, delivered")
        self.assertLessEqual(len(lines), 6)

    def test_campaign_watch_an_escalated_milestone_exits_1(self):
        self.campaign_log.append("campaign_started", milestones=["m1"])
        self.campaign_log.append("milestone_started", milestone="m1",
                                 run_dir=str(self.tmp / "no-run"))
        self.campaign_log.append("escalated", milestone="m1", why="out of revisions")
        code, lines = self.watch()
        self.assertEqual(code, watch.EXIT_ENDED_BAD)
        self.assertIn("m1 escalated: out of revisions", lines)


SEVEN_PY = """
from pathlib import Path
from ohflow.campaign import Campaign, Milestone

def build(args):
    root = Path(args["root"])
    ms = tuple(Milestone(id=f"m{i}", title=f"the {i}th", workflow=f"m{i}/workflow.py",
                         spec=f"m{i}/spec.md") for i in range(1, 8))
    return Campaign(name="demo", root=root, repo=root, charter="charter.md",
                    milestones=ms, integration_branch="integration_branch")
"""


class CampaignWatchFirstCall(CampaignCase):
    """A first call on a long campaign reads a short report, as `watch` does."""

    def setUp(self) -> None:
        super().setUp()
        self.file.write_text(textwrap.dedent(SEVEN_PY), encoding="utf-8")
        self.campaign_log.append("campaign_started",
                                 milestones=[f"m{i}" for i in range(1, 8)])
        for i in range(1, 7):
            self.campaign_log.append("milestone_started", milestone=f"m{i}",
                                     run_dir=str(self.tmp / f"no-run-{i}"))
            self.campaign_log.append("judged", milestone=f"m{i}", round=1,
                                     decision="PASS", summary="fine")
            self.campaign_log.append("milestone_landed", milestone=f"m{i}")
        self.campaign_log.append("milestone_started", milestone="m7",
                                 run_dir=str(self.tmp / "no-run-7"))

    def test_the_first_call_caps_its_event_lines_and_keeps_the_newest(self):
        code, first = self.watch()
        self.assertEqual(code, watch.EXIT_GOING)
        self.assertRegex(first[0], r"^demo: 6 of 7 milestones passed, m7")
        self.assertLessEqual(len(first), runstatus.FIRST_CALL_LINES + 2)
        self.assertIn("m7 started", first)
        self.assertRegex(first[1], r"^\.\.\. \d+ earlier events")

    def test_a_second_call_prints_nothing_that_the_first_call_left_out(self):
        self.watch()
        _code, again = self.watch()
        self.assertEqual(len(again), 1)


JUDGE_URL = "http://127.0.0.1:52277/"
MILESTONE_URL = "http://127.0.0.1:60396/"


class CampaignWatchDuringJudging(CampaignCase):
    """A milestone has two runs: the milestone run, then the judge run. The
    controller serves both dashboards and outlives both, so a dashboard record
    whose pid is alive does not say the run still serves it."""

    def setUp(self) -> None:
        super().setUp()
        self.controller = live_child(self)
        self.milestone = self.camp_dir("milestone-run")
        copy_tree(G1_RUN, self.milestone)
        self.record(self.milestone, MILESTONE_URL)
        self.campaign_log.append("campaign_started", milestones=["m1"])
        self.campaign_log.append("milestone_started", milestone="m1",
                                 run_dir=str(self.milestone))

    def camp_dir(self, name):
        return self.tmp / name

    def record(self, run_dir, url) -> None:
        (run_dir / "dashboard.json").write_text(json.dumps(
            {"url": url, "pid": self.controller.pid, "supervisor": True}),
            encoding="utf-8")

    def judge_run(self):
        m = oc.load_campaign(self.file, {"root": str(self.root)}).milestones[0]
        run = oc.judge_run_dir(self.root, m, 1)
        workflow_json(run, [("Judge", [agent("judge")], 1)])
        RunLog(run).phase(1, "01.judge", "Judge", ["01.judge/01.judge"]) \
            .start(2, "01.judge/01.judge")
        (run / "supervisor.pid").write_text(str(self.controller.pid),
                                            encoding="utf-8")
        self.record(run, JUDGE_URL)
        return run

    def test_campaign_watch_names_the_judging_round_and_the_judge_dashboard(self):
        self.judge_run()
        (self.root / oc.STATUS).write_text(json.dumps(
            {"state": "judging", "milestone": "m1", "round": 1}),
            encoding="utf-8")
        code, lines = self.watch()
        self.assertEqual(code, watch.EXIT_GOING)
        self.assertRegex(lines[0], r"m1 judging round 1")
        self.assertIn(f"dashboard: {JUDGE_URL}", lines)
        self.assertNotIn(MILESTONE_URL, "\n".join(lines))

    def test_line_one_says_starting_while_the_judge_run_does_not_exist(self):
        (self.root / oc.STATUS).write_text(json.dumps(
            {"state": "judging", "milestone": "m1", "round": 1}),
            encoding="utf-8")
        code, lines = self.watch()
        self.assertEqual(code, watch.EXIT_GOING)
        self.assertRegex(lines[0], r"m1 judging round 1 · starting$")
        self.assertNotIn("milestone-run", lines[0])

    def test_campaign_watch_reports_a_judge_url_only_once(self):
        self.judge_run()
        (self.root / oc.STATUS).write_text(json.dumps(
            {"state": "judging", "milestone": "m1", "round": 1}),
            encoding="utf-8")
        _code, first = self.watch()
        self.assertIn(f"dashboard: {JUDGE_URL}", first)
        _code, again = self.watch()
        self.assertNotIn(f"dashboard: {JUDGE_URL}", again)

    def test_the_status_file_names_a_dashboard_only_while_it_serves(self):
        controller = oc.CampaignController(
            oc.load_campaign(self.file, {"root": str(self.root)}),
            no_dashboard=True, say=lambda _msg: None)
        controller._status(state="judging", milestone="m1", round=1,
                           run_dir=self.milestone)
        written = json.loads((self.root / oc.STATUS).read_text(encoding="utf-8"))
        self.assertNotIn("dashboard", written)
        run = self.judge_run()
        controller._status(state="judging", milestone="m1", round=1, run_dir=run)
        written = json.loads((self.root / oc.STATUS).read_text(encoding="utf-8"))
        self.assertEqual(written["dashboard"], JUDGE_URL)


if __name__ == "__main__":
    import unittest
    unittest.main()

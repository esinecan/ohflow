"""`ohflow campaign estimate` forecasts a whole campaign, not one run.

Before this existed, `ohflow estimate` answered for one workflow run, and the
question before a campaign starts is the campaign's: how long, how many tokens
and how much money for every milestone that is left. The forecast is the sum
of `(1 + r) x E(m)`: each milestone's run estimate, times one plus the median
number of REVISE rounds a milestone takes in the campaign logs the history
holds. A milestone that already landed counts 0.

Asserted here, with campaign logs and an estimate history written in a
temporary directory:

- `r` is the median over the finished milestones of two campaigns, and a
  milestone still running is no sample.
- With no finished milestone anywhere, `r` is 0 and the output says so.
- A landed milestone counts 0 and is marked `landed`.
- The total is the sum of the scaled milestones.
- The verb prints the block and the dict, and prints `estimate`'s one line
  when no history is named.
"""

from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path
from unittest import mock

from ohflow import campaign as oc
from ohflow import campaign_estimate as ce
from ohflow import estimate as ohestimate
from support import TempCase
from test_estimate_01_prior_from_history import attempt, summary
from verb_support import call

WORKFLOW_PY = '''
from pathlib import Path
from ohflow.workflow import (CheckSpec, GateSpec, ModelConfig, Phase, Workflow,
                             Step, AgentSpec)

MODEL = ModelConfig(model="fake/deterministic",
                    base_url="http://127.0.0.1:0/never-called",
                    api_key_env="OHFLOW_TEST_FAKE_KEY")


def build(args):
    step = Step(id="s1", kind="agent",
                gate=GateSpec(checks=(CheckSpec("final_message_matches",
                                                {"regex": "DONE"}),)),
                agent=AgentSpec(role=args["milestone"], brief="do it",
                                model=MODEL, harness_executor="pi",
                                max_iterations=3))
    return Workflow(name=args["milestone"] + "-workflow",
                    repo=Path(args["campaign_root"]), base_branch="main",
                    max_parallel=1, transient_backoff_s=0,
                    phases=(Phase(name="Only", steps=(step,)),))
'''

CAMPAIGN_PY = '''
from pathlib import Path
from ohflow.campaign import Campaign, Milestone

def build(args):
    root = Path(args["root"])
    ms = tuple(Milestone(id=i, title=i, workflow=f"milestones/{i}/workflow.py",
                         spec=f"milestones/{i}/spec.md") for i in ("m1", "m2"))
    return Campaign(name="demo", root=root, repo=root, charter="charter.md",
                    milestones=ms, integration_branch="integration")
'''


def write_log(root: Path, milestones: dict) -> Path:
    """A `campaign.jsonl` under `root`, one entry per milestone id mapped to
    `(REVISE rounds, how it ended)`; `None` ends nothing."""
    root.mkdir(parents=True, exist_ok=True)
    lines = []

    def add(event, **payload):
        lines.append(json.dumps({"t": "2026-11-01T00:00:00Z", "event": event,
                                 **payload}))

    for mid, (revises, end) in milestones.items():
        add("milestone_started", milestone=mid, index=1, run_dir=f"runs/{mid}")
        for n in range(revises):
            add("judged", milestone=mid, round=n + 1, decision="REVISE")
            add("revision_committed", milestone=mid, round=n + 1, commit="c0ffee")
        if end == "PASS":
            add("judged", milestone=mid, round=revises + 1, decision="PASS")
            add("milestone_landed", milestone=mid)
        elif end == "ESCALATE":
            add("judged", milestone=mid, round=revises + 1, decision="ESCALATE")
            add("escalated", milestone=mid, why="the operator decides")
    path = root / oc.CAMPAIGN_LOG
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    return path


class CampaignEstimateCase(TempCase):
    """A campaign of two milestones, and three finished runs as the history.

    Every run of the history took 100 s and 1000 tokens as `m1` and 300 s and
    2000 tokens as `m2`, one attempt each, so the retry multiplier is 1 and
    each milestone's run estimate is its own numbers.
    """

    def setUp(self) -> None:
        super().setUp()
        self.root = self.tmp / "camp"
        for mid in ("m1", "m2"):
            mdir = self.root / "milestones" / mid
            mdir.mkdir(parents=True)
            (mdir / "workflow.py").write_text(textwrap.dedent(WORKFLOW_PY),
                                              encoding="utf-8")
            (mdir / "spec.md").write_text(f"# {mid}\n", encoding="utf-8")
        self.module = self.root / "campaign.py"
        self.module.write_text(textwrap.dedent(CAMPAIGN_PY), encoding="utf-8")
        self.history = self.tmp / "history"
        for n in range(3):
            summary(self.history / "runs" / f"r{n}", f"r{n}", [
                {"role": "m1", "executor": "pi", "model": "fake/deterministic",
                 "attempts": [attempt(100, 1000, 0.0, "subscription")]},
                {"role": "m2", "executor": "pi", "model": "fake/deterministic",
                 "attempts": [attempt(300, 2000, 0.0, "subscription")]},
            ])
        patch = mock.patch.dict(os.environ)
        patch.start()
        self.addCleanup(patch.stop)
        os.environ.pop(ohestimate.HISTORY_ENV, None)

    def campaign(self) -> oc.Campaign:
        return oc.load_campaign(self.module, {"root": str(self.root)})

    def estimate(self, *history) -> dict:
        prior = ohestimate.Prior.from_history([self.history])
        return ce.estimate_campaign(self.campaign(), prior,
                                    [str(p) for p in history])


class TheRevisionFactor(CampaignEstimateCase):

    def test_r_is_the_median_over_the_finished_milestones_of_every_campaign(self):
        logs = self.tmp / "campaigns"
        write_log(logs / "a", {"one": (0, "PASS"), "two": (1, "PASS"),
                               "three": (9, None)})
        write_log(logs / "b" / "deep", {"four": (1, "ESCALATE"),
                                        "five": (3, "PASS")})
        data = self.estimate(logs)
        self.assertEqual(data["revise"]["counts"], [0, 1, 1, 3])
        self.assertEqual(data["revise"]["median"], 1)
        self.assertEqual(data["revise"]["factor"], 2)
        self.assertEqual(data["revise"]["milestones"], 4)
        self.assertEqual([e["factor"] for e in data["milestones"]], [2, 2])
        self.assertEqual(data["milestones"][0]["run"]["wall_s"]["p50"], 100)
        self.assertEqual(data["milestones"][0]["wall_s"]["p50"], 200)
        self.assertEqual(data["milestones"][1]["wall_s"]["p50"], 600)

    def test_a_campaign_log_deeper_than_four_levels_is_not_read(self):
        logs = self.tmp / "campaigns"
        write_log(logs / "a" / "b" / "c" / "d" / "e", {"one": (5, "PASS")})
        self.assertEqual(self.estimate(logs)["revise"]["counts"], [])

    def test_with_no_finished_milestone_r_is_zero_and_the_text_says_so(self):
        logs = self.tmp / "campaigns"
        write_log(logs / "a", {"one": (2, None)})
        data = self.estimate(logs)
        self.assertEqual(data["revise"]["median"], 0)
        self.assertEqual(data["revise"]["factor"], 1)
        self.assertEqual(data["revise"]["milestones"], 0)
        self.assertEqual(data["milestones"][0]["wall_s"]["p50"], 100)
        self.assertIn(ce.NO_CAMPAIGN_HISTORY, ce.render_text(data).splitlines())

    def test_the_campaigns_own_log_counts_when_it_holds_a_finished_milestone(self):
        write_log(self.root, {"m1": (2, "PASS")})
        data = self.estimate()
        self.assertEqual(data["revise"]["counts"], [2])
        self.assertEqual(data["revise"]["factor"], 3)
        self.assertNotIn(ce.NO_CAMPAIGN_HISTORY, ce.render_text(data).splitlines())


class TheTotalAndTheLandedMilestone(CampaignEstimateCase):

    def test_a_landed_milestone_counts_zero_and_is_marked_landed(self):
        write_log(self.root, {"m1": (1, "PASS")})
        data = self.estimate()
        m1, m2 = data["milestones"]
        self.assertTrue(m1["landed"])
        self.assertFalse(m2["landed"])
        # Its run estimate stays as evidence; what it adds to the total is 0.
        self.assertEqual(m1["run"]["wall_s"]["p50"], 100)
        self.assertEqual(m1["wall_s"], {"p50": 0, "p80": 0})
        self.assertEqual(m1["tokens"], {"p50": 0, "p80": 0})
        self.assertEqual(m1["cost_usd"], 0.0)
        self.assertEqual(m1["factor"], 0.0)
        self.assertEqual(data["total"]["milestones"], 1)
        self.assertEqual(data["total"]["wall_s"]["p50"], m2["wall_s"]["p50"])
        self.assertIn("| `m1` | 0 s | 0 s | 0 s | 0 | 0 | $0.00 | x0.00 | landed |",
                      ce.render_text(data))

    def test_the_total_is_the_sum_of_the_scaled_milestones(self):
        logs = self.tmp / "campaigns"
        write_log(logs / "a", {"one": (1, "PASS"), "two": (1, "PASS")})
        data = self.estimate(logs)
        total, milestones = data["total"], data["milestones"]
        for which in ("p50", "p80"):
            self.assertEqual(total["wall_s"][which],
                             sum(e["wall_s"][which] for e in milestones))
            self.assertEqual(total["tokens"][which],
                             sum(e["tokens"][which] for e in milestones))
        self.assertEqual(total["cost_usd"], sum(e["cost_usd"] for e in milestones))
        self.assertEqual(total["milestones"], 2)
        self.assertEqual(total["wall_s"]["p50"], 2 * (100 + 300))
        self.assertEqual(total["tokens"]["p50"], 2 * (1000 + 2000))


class TheVerb(CampaignEstimateCase):

    def verb(self, *extra):
        return call("campaign", "estimate", "--campaign", self.module.as_posix(),
                    "--args", f"root={self.root.as_posix()}", *extra)

    def test_the_text_opens_with_the_verdict_line_and_ends_with_the_total(self):
        logs = self.tmp / "campaigns"
        write_log(logs / "a", {"one": (1, "PASS"), "two": (1, "PASS")})
        code, lines = self.verb("--history", str(self.history),
                                "--history", str(logs))
        self.assertEqual(code, 0, lines)
        self.assertTrue(lines[0].startswith("CAMPAIGN ESTIMATE demo:"), lines[0])
        self.assertIn("13 min (p50)", lines[0])
        self.assertIn("for 2 milestones left", lines[0])
        self.assertIn("REVISE median 1 over 2 finished milestones, x2.00", lines[0])
        self.assertIn("6 attempts from 3 summaries", lines[0])
        self.assertTrue(lines[-1].startswith("| total | 13 min |"), lines[-1])
        self.assertEqual([l for l in lines if l.startswith("| `")], [
            "| `m1` | 3 min | 3 min | - | 2.0 k | 2.0 k | $0.00 | x2.00 | left | ok |",
            "| `m2` | 10 min | 10 min | - | 4.0 k | 4.0 k | $0.00 | x2.00 | left | ok |",
        ])

    def test_json_carries_every_milestone_the_factor_and_the_total(self):
        code, lines = self.verb("--history", str(self.history), "--json")
        self.assertEqual(code, 0, lines)
        data = json.loads("\n".join(lines))
        self.assertEqual(data["schema"], ce.SCHEMA)
        self.assertEqual(data["campaign"], "demo")
        self.assertEqual([e["id"] for e in data["milestones"]], ["m1", "m2"])
        self.assertEqual(data["revise"]["factor"], 1)
        self.assertEqual(data["total"]["wall_s"]["p50"], 400)
        self.assertEqual(data["history"]["samples"], 6)
        self.assertEqual(data["milestones"][0]["run"]["confidence"], "ok")

    def test_without_an_estimate_history_it_prints_one_line_and_exits_0(self):
        code, lines = self.verb()
        self.assertEqual(code, 0, lines)
        self.assertEqual(lines, [ohestimate.NO_HISTORY])

    def test_the_environment_variable_names_the_default_history(self):
        os.environ[ohestimate.HISTORY_ENV] = str(self.history)
        code, lines = self.verb("--json")
        self.assertEqual(code, 0, lines)
        self.assertEqual(json.loads("\n".join(lines))["history"]["samples"], 6)

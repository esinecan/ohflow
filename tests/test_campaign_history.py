"""`ohflow campaign history` lists every milestone round of a campaign.

Before: the decision of each round, the judge's reason, the revision commit,
the acceptance-check result and the run directory sat in four places: the
campaign log, the judge handover, the packet and git. An orchestrating agent
joined them by hand. Now one call prints one line per round and one reason
line under it, each with its evidence, under a size cap. It reads files only.

The spec is `docs/history/orchestrator-visibility.md`, "Utility 5".
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

from ohflow import campaign as oc
from ohflow import campaign_history as ch
from ohflow import handover
from ohflow.paths import win
from ohflow.workflow import HandoverSpec
from support import TempCase
from verb_support import call

FRONT = "---\nseat: claude\nnext_session_for: the next judge\n---\n\n"
QUESTIONS = "\n## Questions\n\n### Core\n\n1. **Authoritative state.** x\n"

CAMPAIGN_PY = """
from pathlib import Path
from ohflow.campaign import Campaign, Milestone

def build(args):
    root = Path(args["root"])
    ms = tuple(Milestone(id=i, title=i, workflow=f"milestones/{i}/workflow.py",
                         spec=f"milestones/{i}/spec.md") for i in ("m1", "m2"))
    return Campaign(name="demo", root=root, repo=root, charter="charter.md",
                    milestones=ms, integration_branch="integration_branch")
"""


def packet(checks: list[tuple[str, object]] | None, *, old: bool = False) -> str:
    """A packet with an acceptance-check section, as `render_packet` writes it."""
    heading = ("## Exit checks the driver ran" if old
               else "## Acceptance checks the controller ran")
    out = ["# Judge packet", "", "## What ran", "", "- Run status: `finished`",
           "", heading, ""]
    if not checks:
        out.append("(the milestone defines none)")
    for name, code in checks or []:
        out += [f"### {name}: exit {code}", "", f"`run {name}` in `land`", "",
                "```", "## not a heading: tail output", "```", ""]
    out += ["## Lineage", "", "### Round 1: REVISE", ""]
    return "\n".join(out) + "\n"


class HistoryCase(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.root = self.tmp / "camp"
        self.root.mkdir()
        self.lines: list[str] = []

    def log(self, event: str | None = None, **payload) -> int:
        """Append one campaign log line (a blank one for no event); return its
        1-based line number."""
        self.lines.append("" if event is None else json.dumps(
            {"t": "2026-10-11T00:00:00Z", "event": event, **payload}))
        (self.root / oc.CAMPAIGN_LOG).write_text(
            "\n".join(self.lines) + "\n", encoding="utf-8")
        return len(self.lines)

    def judge_dir(self, mid: str, n: int, *, old: bool = False) -> Path:
        d = self.root / "milestones" / mid / "judge" / f"{'a' if old else 'r'}{n:02d}"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def handover(self, d: Path, title: str, lead: str | None) -> str:
        body = FRONT + f"# {title}\n\n" + (f"{lead}\n" if lead else "") + QUESTIONS
        path = d / "judge-handover.md"
        path.write_text(body, encoding="utf-8")
        return str(path)

    def packet(self, d: Path, checks, *, old: bool = False) -> str:
        path = d / "packet.md"
        path.write_text(packet(checks, old=old), encoding="utf-8")
        return str(path)

    def judged(self, mid: str, n: int, decision: str | None, *,
               lead: str | None = "the lead", checks=(), old: bool = False,
               handover: bool = True, with_packet: bool = True) -> int:
        d = self.judge_dir(mid, n, old=old)
        hpath = self.handover(d, f"Judge {n} of {mid}", lead) if handover else None
        ppath = (self.packet(d, list(checks), old=old) if with_packet
                 else str(d / "packet.md"))
        keys = ({"attempt": n, "verdict": decision} if old
                else {"round": n, "decision": decision})
        return self.log("judged", milestone=mid, **keys, summary="NOT THE REASON",
                        findings=[], revisions=[], question=None,
                        judge_dir=str(d / "run"), handover=hpath, packet=ppath)

    def history(self, *extra, target=None):
        return call("campaign", "history", "--campaign",
                    (target or self.root).as_posix(), *extra)


class TheLeadParagraphAndTheChecks(HistoryCase):

    def test_the_lead_is_the_text_between_the_title_and_the_next_heading(self):
        path = self.tmp / "h.md"
        path.write_text(FRONT + "# Judge 2: REVISE\n\nVerdict: **REVISE**. The\n"
                        "fix   pass is in findings.md.\n\nSecond paragraph.\n"
                        + QUESTIONS, encoding="utf-8")
        self.assertEqual(ch.handover_lead(path), "Verdict: **REVISE**. The fix "
                         "pass is in findings.md. Second paragraph.")

    def test_a_handover_with_no_lead_has_none(self):
        path = self.tmp / "h.md"
        path.write_text(FRONT + "# Judge 1: PASS\n\n" + QUESTIONS, encoding="utf-8")
        self.assertIsNone(ch.handover_lead(path))

    def test_the_front_matter_is_never_the_lead(self):
        path = self.tmp / "h.md"
        path.write_text("---\ntitle: x\n# not the title\n---\n# The title\n"
                        "The lead.\n## Questions\n", encoding="utf-8")
        self.assertEqual(ch.handover_lead(path), "The lead.")

    def test_packet_checks_reads_names_and_exit_codes_of_both_spellings(self):
        new = self.tmp / "new.md"
        new.write_text(packet([("suite: >= 12 tests", 0), ("docs", 1),
                               ("live", None)]), encoding="utf-8")
        self.assertEqual(ch.packet_checks(new), [
            {"name": "suite: >= 12 tests", "exit": 0},
            {"name": "docs", "exit": 1}, {"name": "live", "exit": None}])
        old = self.tmp / "old.md"
        old.write_text(packet([("tests", 0)], old=True), encoding="utf-8")
        self.assertEqual(ch.packet_checks(old), [{"name": "tests", "exit": 0}])

    def test_packet_checks_none_defined_is_empty_and_no_section_is_unknown(self):
        none = self.tmp / "none.md"
        none.write_text(packet(None), encoding="utf-8")
        self.assertEqual(ch.packet_checks(none), [])
        bare = self.tmp / "bare.md"
        bare.write_text("# Judge packet\n\n## What ran\n", encoding="utf-8")
        self.assertIsNone(ch.packet_checks(bare))
        self.assertIsNone(ch.packet_checks(self.tmp / "missing.md"))


class OneLinePerRound(HistoryCase):

    def test_new_keys_print_each_round_with_its_reason_checks_revision_and_run(self):
        run = self.root / "milestones" / "m1" / "runs" / "m1"
        self.log("campaign_started", name="camp", milestones=["m1"])
        self.log("milestone_started", milestone="m1", index=1, run_dir=str(run),
                 integration_sha="abc")
        r1 = self.judged("m1", 1, "REVISE", lead="Verdict: REVISE. The brief\n"
                         "lacks the gate.", checks=[("suite", 0), ("docs", 1),
                                                    ("live", None)])
        self.log()                                           # a blank line counts
        self.log("revision_committed", milestone="m1", round=1,
                 commit="0123456789abcdef0123")
        r2 = self.judged("m1", 2, "PASS", lead=None, checks=[])
        landed = self.log("milestone_landed", milestone="m1")
        code, lines = self.history()
        self.assertEqual(code, 0, lines)
        h1 = self.root / "milestones/m1/judge/r01/judge-handover.md"
        h2 = self.root / "milestones/m1/judge/r02/judge-handover.md"
        self.assertEqual(lines, [
            "HISTORY camp: 1 milestone, 2 rounds, 1 REVISE, 0 ESCALATE · campaign.jsonl",
            f"m1 round 1: REVISE · checks 1/3 passed (failed: docs, live) · "
            f"revision 0123456789 · run {win(run)} · campaign.jsonl:{r1}",
            f"  reason: Verdict: REVISE. The brief lacks the gate. · {win(h1)}",
            f"m1 round 2: PASS · checks none · run {win(run)} · campaign.jsonl:{r2}",
            f"  reason: the handover has no lead paragraph · {win(h2)}",
            f"m1 landed · campaign.jsonl:{landed}",
        ])
        self.assertEqual(r2, 6)
        self.assertNotIn("NOT THE REASON", "\n".join(lines))

    def test_old_keys_read_the_same_way(self):
        run = self.root / "milestones" / "m1" / "runs" / "m1"
        self.log("campaign_started", name="camp", milestones=["m1"],
                 trunk="t", trunk_sha="abc")
        self.log("milestone_started", milestone="m1", index=1, run_dir=str(run),
                 trunk_sha="abc")
        r1 = self.judged("m1", 1, "REVISE", old=True, lead="Old lead.",
                         checks=[("tests", 0)])
        self.log("revision_committed", milestone="m1", attempt=1,
                 commit="fedcba9876543210")
        r2 = self.judged("m1", 2, "PASS", old=True, lead=None, checks=[("tests", 0)])
        passed = self.log("milestone_passed", milestone="m1", trunk_before="a",
                          trunk_after="b")
        code, lines = self.history()
        self.assertEqual(code, 0, lines)
        h1 = self.root / "milestones/m1/judge/a01/judge-handover.md"
        self.assertEqual(lines[1], f"m1 round 1: REVISE · checks 1/1 passed · "
                                   f"revision fedcba9876 · run {win(run)} · "
                                   f"campaign.jsonl:{r1}")
        self.assertEqual(lines[2], f"  reason: Old lead. · {win(h1)}")
        self.assertTrue(lines[3].startswith("m1 round 2: PASS · checks 1/1 passed · run "))
        self.assertTrue(lines[3].endswith(f"campaign.jsonl:{r2}"))
        self.assertEqual(lines[-1], f"m1 landed · campaign.jsonl:{passed}")

    def test_a_missing_handover_or_packet_and_a_null_decision_say_so(self):
        self.log("milestone_started", milestone="m1", index=1,
                 run_dir=str(self.root / "run"))
        r1 = self.judged("m1", 1, None, handover=False, with_packet=False)
        code, lines = self.history()
        self.assertEqual(code, 0, lines)
        jdir = self.root / "milestones/m1/judge/r01/run"
        self.assertEqual(lines[1], f"m1 round 1: NO DECISION · checks unknown · "
                                   f"run {win(self.root / 'run')} · campaign.jsonl:{r1}")
        self.assertEqual(lines[2], f"  reason: no handover file · judge {win(jdir)}")

    def test_a_recorded_handover_path_whose_file_is_gone_is_no_handover_file(self):
        r1 = self.judged("m1", 1, "PASS")
        (self.root / "milestones/m1/judge/r01/judge-handover.md").unlink()
        code, lines = self.history()
        self.assertEqual(code, 0, lines)
        self.assertTrue(lines[1].endswith(f"campaign.jsonl:{r1}"))
        self.assertTrue(lines[2].startswith("  reason: no handover file · judge "))

    def test_escalated_and_granted_lines_sit_between_the_rounds_in_log_order(self):
        self.log("milestone_started", milestone="m1", index=1, run_dir="r")
        self.judged("m1", 1, "ESCALATE")
        esc = self.log("escalated", milestone="m1", why="a design\nchoice is the operator's",
                       judge_dir="j")
        grant = self.log("granted", milestone="m1", revisions=1)
        self.judged("m1", 2, "PASS")
        code, lines = self.history()
        self.assertEqual(code, 0, lines)
        self.assertEqual(lines[0], "HISTORY camp: 1 milestone, 2 rounds, "
                                   "0 REVISE, 1 ESCALATE · campaign.jsonl")
        self.assertEqual(lines[3], f"m1 escalated: a design choice is the operator's · "
                                   f"campaign.jsonl:{esc}")
        self.assertEqual(lines[4], f"m1 granted 1 revision · campaign.jsonl:{grant}")
        self.assertTrue(lines[5].startswith("m1 round 2: PASS"))

    def test_milestones_group_in_first_appearance_order_and_filter_by_id(self):
        self.log("milestone_started", milestone="m2", index=1, run_dir="r2")
        self.judged("m2", 1, "PASS")
        self.log("milestone_started", milestone="m1", index=2, run_dir="r1")
        self.judged("m1", 1, "REVISE")
        self.judged("m2", 2, "PASS")
        code, lines = self.history()
        self.assertEqual(code, 0, lines)
        heads = [l.split(" ·")[0] for l in lines[1:] if not l.startswith("  ")]
        self.assertEqual(heads, ["m2 round 1: PASS", "m2 round 2: PASS",
                                 "m1 round 1: REVISE"])
        code, lines = self.history("--milestone", "m1")
        self.assertEqual(code, 0, lines)
        self.assertEqual(lines[0], "HISTORY camp: 1 milestone, 1 round, "
                                   "1 REVISE, 0 ESCALATE · campaign.jsonl")
        self.assertEqual(len(lines), 3)
        code, lines = self.history("--milestone", "m9")
        self.assertEqual(code, 1)
        self.assertEqual(len(lines), 1)

    def test_the_run_is_the_latest_start_of_that_milestone_before_the_round(self):
        self.log("milestone_started", milestone="m1", index=1, run_dir="first")
        self.judged("m1", 1, "REVISE")
        self.log("milestone_started", milestone="m1", index=1, run_dir="second")
        self.judged("m1", 2, "PASS")
        _code, lines = self.history()
        self.assertIn("· run first ·", lines[1])
        self.assertIn("· run second ·", lines[3])


class TheJsonAndTheCaps(HistoryCase):

    def test_json_carries_every_round_and_event_with_its_log_line(self):
        self.log("milestone_started", milestone="m1", index=1, run_dir="run1")
        r1 = self.judged("m1", 1, "REVISE", checks=[("suite", 2)])
        self.log("revision_committed", milestone="m1", round=1, commit="c0ffee")
        landed = self.log("milestone_landed", milestone="m1")
        code, lines = self.history("--json")
        self.assertEqual(code, 0, lines)
        data = json.loads("\n".join(lines))
        d = self.root / "milestones/m1/judge/r01"
        self.assertEqual(data, {"campaign": "camp", "milestones": [{
            "id": "m1",
            "rounds": [{"round": 1, "decision": "REVISE", "reason": "the lead",
                        "handover": str(d / "judge-handover.md"),
                        "checks": [{"name": "suite", "exit": 2}],
                        "revision": "c0ffee", "run_dir": "run1",
                        "judge_dir": str(d / "run"), "log_line": r1}],
            "events": [{"event": "landed", "log_line": landed}]}]})

    def test_a_long_reason_is_cut_to_300_characters_and_keeps_its_pointer(self):
        self.judged("m1", 1, "PASS", lead="word " * 200)
        _code, lines = self.history()
        reason, pointer = lines[2].rsplit(" · ", 1)
        self.assertEqual(pointer, win(self.root / "milestones/m1/judge/r01/"
                                                  "judge-handover.md"))
        text = reason[len("  reason: "):]
        self.assertLessEqual(len(text), 300)
        self.assertGreater(len(text), 290)
        self.assertTrue(text.endswith("…"))

    def test_the_whole_text_is_cut_at_8000_characters_after_the_history_line(self):
        for n in range(1, 60):
            self.judged("m1", n, "REVISE", lead="reason " * 60)
        code, lines = self.history()
        self.assertEqual(code, 0, lines)
        self.assertLessEqual(len("\n".join(lines)), 8000)
        self.assertTrue(lines[0].startswith("HISTORY camp: 1 milestone, 59 rounds"))
        self.assertEqual(lines[-1], "(cut at 8,000 characters; narrow with "
                                    "--milestone or read --json)")
        # A round never loses its reason line to the cut.
        self.assertTrue(lines[-2].startswith("  reason: "))


class TheCampaignModule(HistoryCase):

    def test_a_module_gives_the_campaign_name_and_its_milestone_order(self):
        module = self.tmp / "campaign.py"
        module.write_text(textwrap.dedent(CAMPAIGN_PY), encoding="utf-8")
        self.judged("m2", 1, "PASS")
        self.judged("m1", 1, "PASS")
        code, lines = call("campaign", "history", "--campaign", module.as_posix(),
                           "--args", f"root={self.root.as_posix()}")
        self.assertEqual(code, 0, lines)
        self.assertTrue(lines[0].startswith("HISTORY demo: 2 milestones"))
        self.assertTrue(lines[1].startswith("m1 round 1: PASS"))
        self.assertTrue(lines[3].startswith("m2 round 1: PASS"))

    def test_a_folder_with_no_campaign_log_exits_1(self):
        (self.tmp / "empty").mkdir()
        code, lines = self.history(target=self.tmp / "empty")
        self.assertEqual(code, 1)
        self.assertEqual(len(lines), 1)

    def test_the_judge_brief_asks_for_the_lead_paragraph_history_shows(self):
        brief = " ".join(oc.JUDGE_ROLE.split())
        self.assertIn("one paragraph right under its title", brief)
        self.assertIn("the decision and the reason for it", brief)
        self.assertIn("`ohflow campaign history` shows that paragraph", brief)

    def test_the_judge_brief_carries_the_handover_format_and_names_no_skill(self):
        brief = " ".join(oc.JUDGE_ROLE.split())
        self.assertNotIn("Invoke the handover skill", brief)
        self.assertIn("it needs no skill", brief)
        at = [brief.find(f"- `## {h}`: {q}") for h, q in handover.CORE]
        self.assertNotIn(-1, at)
        self.assertEqual(at, sorted(at))
        for rule in ("`not established`", "`[verified]` or `[assumed]`",
                     "already done, do not repeat", "Keep secrets out"):
            self.assertIn(rule, brief)
        self.assertFalse([line for line in oc.JUDGE_ROLE.splitlines()[1:]
                          if line.startswith("#")])

    def test_a_handover_in_the_brief_format_passes_the_core_check_and_has_its_lead(self):
        body = "".join(f"## {h}\n\nnot established\n\n" for h, _ in handover.CORE)
        path = self.tmp / "judge-handover.md"
        path.write_text("# m1, round 1: REVISE\n\nREVISE: the fix has no test.\n\n"
                        + body, encoding="utf-8")
        self.assertEqual(ch.handover_lead(path), "REVISE: the fix has no test.")
        self.assertIsNone(handover.check_text(path.read_text(encoding="utf-8"),
                                              HandoverSpec()))

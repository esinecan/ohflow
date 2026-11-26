"""The campaign loop: run, judge, revise, rerun, land or escalate.

What went wrong before this existed: a milestone check needed the session that
wrote the workflow. Nothing above one workflow run could judge the result, change the
inputs and run again, so every milestone boundary waited for a human with the
whole context in their head. `ohflow.campaign` moves that context into a
packet and gives the judgement to a fresh agent.

Asserted here, with a fake harness executor and two real git repositories:

- A REVISE commits the judge's edit in the campaign repo and resumes the run;
  the changed step reruns, and the next packet carries the earlier decision.
- A judge that edits outside its milestone directory, or edits `spec.md`,
  escalates and commits nothing.
- A REVISE that changes nothing escalates, because a rerun would repeat itself.
- A PASS over a failing acceptance check escalates: the decision is a claim and the
  check is the evidence.
- A spent revision budget escalates and keeps the proposal on its own branch;
  `grant` reopens the milestone.
- A PASS fast-forwards the integration branch to the output branch, and refuses to move it
  backwards. Without an output branch, a PASS still lands and moves no branch.
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))

from support import (FAKE_MODEL, FakeHarnessExecutor, TempCase, AgentScript,  # noqa: E402
                     git_repo, install_fake_harness_executor, quiet)

from ohflow import campaign as oc  # noqa: E402
from ohflow.workflow import AgentSpec  # noqa: E402

PRODUCT_STEP = "01.only-phase/01.s1"
JUDGE_STEP = "01.judge/01.judge"

WORKFLOW_PY = textwrap.dedent('''
    from pathlib import Path
    from ohflow.workflow import (CheckSpec, GateSpec, ModelConfig, Phase, Workflow,
                                 Step, AgentSpec)

    def build(args):
        here = Path(__file__).resolve().parent
        brief = (here / "briefs" / "impl.md").read_text(encoding="utf-8")
        model = ModelConfig(model="fake/deterministic",
                            base_url="http://127.0.0.1:0/never-called",
                            api_key_env="OHFLOW_TEST_FAKE_KEY")
        step = Step(id="s1", kind="agent", worktree=None,
                    gate=GateSpec(checks=(CheckSpec("final_message_matches",
                                                    {"regex": "DONE"}),)),
                    agent=AgentSpec(harness_executor="pi", role="impl", brief=brief, model=model,
                                    max_iterations=5))
        return Workflow(name="m1-workflow", repo=Path(args["product"]),
                        base_branch="main", baseline_cmd=None, worktrees=(),
                        phases=(Phase(name="Only phase", steps=(step,)),),
                        transient_backoff_s=0)
''')


def _git(cwd: Path, *args: str) -> str:
    return oc._git(cwd, *args)


class CampaignCase(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.product = git_repo(self.tmp / "product")
        self.root = git_repo(self.tmp / "camp")
        mdir = self.root / "milestones" / "m1"
        (mdir / "briefs").mkdir(parents=True)
        (self.root / "charter.md").write_text(
            "# Charter\n\nShip it polished. CHARTER-MARKER\n", encoding="utf-8")
        (mdir / "spec.md").write_text("# m1\n\nSPEC-MARKER\n", encoding="utf-8")
        (mdir / "workflow.py").write_text(WORKFLOW_PY, encoding="utf-8")
        (mdir / "briefs" / "impl.md").write_text("Do the thing.\n",
                                                 encoding="utf-8")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-m", "campaign inputs")
        self.mdir = mdir

    def campaign(self, **kw) -> oc.Campaign:
        m = oc.Milestone(id="m1", title="the first milestone",
                         workflow="milestones/m1/workflow.py",
                         spec="milestones/m1/spec.md",
                         args={"product": str(self.product)},
                         output_branch=kw.pop("output_branch", None),
                         acceptance_checks=kw.pop("acceptance_checks", ()),
                         max_revisions=kw.pop("max_revisions", None))
        judge = AgentSpec(harness_executor="pi", role="milestone-judge", brief="", model=FAKE_MODEL,
                          max_iterations=5)
        return oc.Campaign(name="t", root=self.root, repo=self.product,
                           charter="charter.md", milestones=(m,),
                           integration_branch="integration-branch", judge=judge, auto_resume=0, **kw)

    def handover(self, round_no: int) -> Path:
        return self.mdir / "judge" / f"r{round_no:02d}" / "judge-handover.md"

    def judge(self, decisions: list[dict], edits=None) -> AgentScript:
        """A judge that answers `decisions[i]` on launch i+1, writes its
        handover file, and makes `edits[i]` (a callable) on that launch."""
        edits = edits or {}
        script = AgentScript(
            sequence=[{"final_text": "```json\n" + json.dumps(v) + "\n```\n",
                       "structured": v} for v in decisions])

        def act():
            n = script.launches
            h = self.handover(n)
            h.parent.mkdir(parents=True, exist_ok=True)
            h.write_text("# handover\n", encoding="utf-8")
            fn = edits.get(n)
            if fn is not None:
                fn()
            return None

        script.on_poll = act
        return script

    def drive(self, camp: oc.Campaign, harness_executor: FakeHarnessExecutor) -> int:
        install_fake_harness_executor(self, harness_executor)
        with quiet():
            return oc.CampaignController(camp, no_dashboard=True,
                                         say=lambda _m: None,
                                         harness_executors=self.harness_executors).run()

    def events(self) -> list[str]:
        return [e["event"] for e in oc.CampaignLog(self.root).events()]


def decision(kind: str, *, revisions=(), findings=()) -> dict:
    return {"decision": kind, "summary": f"{kind} summary",
            "findings": list(findings), "revisions": list(revisions),
            "question_for_operator": None}


FINDING = {"severity": "blocking", "what": "FINDING-MARKER brief lacks X",
           "evidence": "diff line 3", "cause": "brief"}


class StepHandoversInThePacket(CampaignCase):

    def test_packet_reads_earlier_and_failed_handovers_and_refuses_modified_text(self):
        import hashlib
        from ohflow import rundir
        from ohflow.run_log import RunLog
        run_dir = self.tmp / "run"
        log = RunLog(run_dir)
        log.append("run_started", payload={"run_id": "test", "workflow": "packet-test"})
        for coord, status, marker in (("01.produce/01.scout", "passed", "SCOUT-MARKER"),
                                      ("02.check/01.reviewer", "quarantined", "FAILED-MARKER"),
                                      ("03.finish/01.leaf", "passed", None)):
            payload = {"step_id": coord.split('.')[-1], "kind": "agent", "status": status}
            if marker:
                path = run_dir / "phases" / coord / "attempts/01/handover.md"
                path.parent.mkdir(parents=True)
                path.write_bytes(marker.encode())
                payload.update(handover_path=path.relative_to(run_dir).as_posix(),
                               handover_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            log.append("attempt_finished", coord=coord, attempt=1, payload=payload)
        camp = self.campaign()
        controller = oc.CampaignController(camp, no_dashboard=True, say=lambda _: None)
        def packet():
            return oc.render_packet(controller, 1, camp.milestones[0], oc.MilestoneState(),
                                    run_dir, rundir.open_run(run_dir).summary(), [], 1,
                                    self.handover(1), None)
        text = packet()
        self.assertIn("SCOUT-MARKER", text)
        self.assertIn("02.check/01.reviewer: quarantined", text)
        self.assertIn("FAILED-MARKER", text)
        path.write_bytes(b"MODIFIED-MARKER")
        changed = packet()
        self.assertIn("handover unavailable: recorded handover content changed", changed)
        self.assertNotIn("MODIFIED-MARKER", changed)


class ReviseThenPass(CampaignCase):

    def test_revision_is_committed_and_the_changed_step_reruns(self):
        product = AgentScript(final_text="DONE\n")
        edit = lambda: (self.mdir / "briefs" / "impl.md").write_text(  # noqa
            "Do the thing, and X.\n", encoding="utf-8")
        judge = self.judge(
            [decision("REVISE", findings=[FINDING],
                      revisions=[{"path": "milestones/m1/briefs/impl.md",
                                  "why": "adds X"}]),
             decision("PASS")],
            edits={1: edit})
        harness_executor = FakeHarnessExecutor(scripts={PRODUCT_STEP: product, JUDGE_STEP: judge})
        code = self.drive(self.campaign(), harness_executor)

        self.assertEqual(code, oc.EXIT_DELIVERED)
        self.assertEqual(product.launches, 2,
                         "the revised brief must rerun the product step")
        self.assertEqual(judge.launches, 2)
        log = _git(self.root, "log", "--format=%s")
        self.assertIn("m1 r01: REVISE summary", log)
        self.assertEqual(self.events(),
                         ["campaign_started", "milestone_started", "judged",
                          "revision_committed", "judged", "milestone_landed",
                          "campaign_delivered"])
        packet2 = (self.mdir / "judge" / "r02" / "packet.md").read_text(
            encoding="utf-8")
        for marker in ("CHARTER-MARKER", "SPEC-MARKER", "FINDING-MARKER",
                       "Round 1: REVISE", str(self.handover(1)),
                       "Revision commit"):
            self.assertIn(marker, packet2)
        self.assertEqual(_git(self.root, "status", "--porcelain"), "")

    def test_unchanged_step_stays_cached_across_a_revision(self):
        product = AgentScript(final_text="DONE\n")
        note = lambda: (self.mdir / "notes.md").write_text(  # noqa
            "a snippet\n", encoding="utf-8")
        judge = self.judge([decision("REVISE", revisions=[
            {"path": "milestones/m1/notes.md", "why": "reference"}]),
            decision("PASS")], edits={1: note})
        harness_executor = FakeHarnessExecutor(scripts={PRODUCT_STEP: product, JUDGE_STEP: judge})
        self.assertEqual(self.drive(self.campaign(), harness_executor), oc.EXIT_DELIVERED)
        self.assertEqual(product.launches, 1,
                         "an edit the workflow does not read must not rerun it")


class Escalations(CampaignCase):

    def test_edit_outside_scope_escalates_and_commits_nothing(self):
        head = _git(self.root, "rev-parse", "HEAD")
        stray = lambda: (self.root / "charter.md").write_text(  # noqa
            "moved goalposts\n", encoding="utf-8")
        judge = self.judge([decision("REVISE")], edits={1: stray})
        harness_executor = FakeHarnessExecutor(scripts={JUDGE_STEP: judge})
        self.assertEqual(self.drive(self.campaign(), harness_executor), oc.EXIT_ESCALATED)
        self.assertIn("outside its write scope",
                      (self.root / oc.ESCALATION).read_text(encoding="utf-8"))
        self.assertIn("ACTION NEEDED FROM THE OPERATOR",
                      (self.root / oc.ESCALATION).read_text(encoding="utf-8"))
        # Only the controller's own .gitignore commit may follow the inputs.
        subjects = _git(self.root, "log", "--format=%s", f"{head}..HEAD")
        self.assertNotIn("r01", subjects)

    def test_editing_the_spec_escalates(self):
        spec = lambda: (self.mdir / "spec.md").write_text(  # noqa
            "easier target\n", encoding="utf-8")
        judge = self.judge([decision("REVISE")], edits={1: spec})
        harness_executor = FakeHarnessExecutor(scripts={JUDGE_STEP: judge})
        self.assertEqual(self.drive(self.campaign(), harness_executor), oc.EXIT_ESCALATED)
        self.assertIn("spec.md",
                      (self.root / oc.ESCALATION).read_text(encoding="utf-8"))

    def test_revise_without_a_change_escalates(self):
        judge = self.judge([decision("REVISE")])
        harness_executor = FakeHarnessExecutor(scripts={JUDGE_STEP: judge})
        self.assertEqual(self.drive(self.campaign(), harness_executor), oc.EXIT_ESCALATED)
        self.assertIn("changed nothing",
                      (self.root / oc.ESCALATION).read_text(encoding="utf-8"))

    def test_pass_over_a_failing_exit_check_escalates(self):
        judge = self.judge([decision("PASS")])
        harness_executor = FakeHarnessExecutor(scripts={JUDGE_STEP: judge})
        camp = self.campaign(acceptance_checks=(
            oc.AcceptanceCheck(name="suite", cmd="exit 7", cwd="repo"),))
        self.assertEqual(self.drive(camp, harness_executor), oc.EXIT_ESCALATED)
        text = (self.root / oc.ESCALATION).read_text(encoding="utf-8")
        self.assertIn("acceptance checks failed: suite", text)
        self.assertNotIn("milestone_landed", self.events())

    def test_judge_escalate_carries_the_question(self):
        v = decision("ESCALATE")
        v["question_for_operator"] = "QUESTION-MARKER fork or direct CDP?"
        harness_executor = FakeHarnessExecutor(scripts={JUDGE_STEP: self.judge([v])})
        self.assertEqual(self.drive(self.campaign(), harness_executor), oc.EXIT_ESCALATED)
        self.assertIn("QUESTION-MARKER",
                      (self.root / oc.ESCALATION).read_text(encoding="utf-8"))

    def test_spent_budget_keeps_the_proposal_and_grant_reopens(self):
        edit = lambda: (self.mdir / "briefs" / "impl.md").write_text(  # noqa
            "Proposal.\n", encoding="utf-8")
        judge = self.judge([decision("REVISE"), decision("PASS")],
                           edits={1: edit})
        harness_executor = FakeHarnessExecutor(scripts={JUDGE_STEP: judge})
        camp = self.campaign(max_revisions=0)
        self.assertEqual(self.drive(camp, harness_executor), oc.EXIT_ESCALATED)
        self.assertIn("budget", (self.root / oc.ESCALATION).read_text(
            encoding="utf-8"))
        self.assertEqual(_git(self.root, "status", "--porcelain"), "")
        self.assertTrue(oc._rev(self.root, "campaign-proposal/m1-r01"))

        # A second run without a grant stops at once.
        self.assertEqual(self.drive(camp, harness_executor), oc.EXIT_ESCALATED)
        self.assertEqual(judge.launches, 1)

        oc.grant(camp, "m1", 1)
        self.assertEqual(self.drive(camp, harness_executor), oc.EXIT_DELIVERED)
        self.assertFalse((self.root / oc.ESCALATION).exists())


class Landing(CampaignCase):

    def _output_branch(self, name: str, base: str = "main") -> str:
        _git(self.product, "checkout", "-q", "-b", name, base)
        (self.product / f"{name.replace('/', '-')}.txt").write_text(
            "work\n", encoding="utf-8")
        _git(self.product, "add", "-A")
        _git(self.product, "commit", "-q", "-m", f"work on {name}")
        sha = _git(self.product, "rev-parse", "HEAD")
        _git(self.product, "checkout", "-q", "main")
        return sha

    def test_pass_fast_forwards_the_integration_branch(self):
        sha = self._output_branch("feat/m1")
        harness_executor = FakeHarnessExecutor(scripts={JUDGE_STEP: self.judge([decision("PASS")])})
        self.assertEqual(self.drive(self.campaign(output_branch="feat/m1"), harness_executor),
                         oc.EXIT_DELIVERED)
        self.assertEqual(oc._rev(self.product, "integration-branch"), sha)

    def test_pass_without_an_output_branch_lands_and_moves_no_branch(self):
        base = _git(self.product, "rev-parse", "main")
        _git(self.product, "branch", "integration-branch", base)
        harness_executor = FakeHarnessExecutor(scripts={JUDGE_STEP: self.judge([decision("PASS")])})
        self.assertEqual(self.drive(self.campaign(), harness_executor), oc.EXIT_DELIVERED)
        self.assertIn("milestone_landed", self.events())
        self.assertEqual(oc._rev(self.product, "integration-branch"), base)

    def test_output_branch_that_drops_integration_branch_work_escalates(self):
        base = _git(self.product, "rev-parse", "main")
        _git(self.product, "branch", "integration-branch", base)
        integration_sha = self._output_branch("integration-branch-extra", base="integration-branch")
        _git(self.product, "update-ref", "refs/heads/integration-branch", integration_sha, base)
        self._output_branch("feat/m1", base="main")
        harness_executor = FakeHarnessExecutor(scripts={JUDGE_STEP: self.judge([decision("PASS")])})
        self.assertEqual(self.drive(self.campaign(output_branch="feat/m1"), harness_executor),
                         oc.EXIT_ESCALATED)
        self.assertEqual(oc._rev(self.product, "integration-branch"), integration_sha)


class Validation(CampaignCase):

    def test_missing_charter_and_split_milestone_dir_are_refused(self):
        camp = self.campaign()
        bad = oc.Campaign(
            name="t", root=self.root, repo=self.product, charter="nope.md",
            integration_branch="integration-branch",
            milestones=(oc.Milestone(id="m1", title="x",
                                     workflow="milestones/m1/workflow.py",
                                     spec="charter.md"),))
        problems = oc.validate_campaign(bad)
        self.assertTrue(any("charter missing" in p for p in problems))
        self.assertTrue(any("one milestone directory" in p for p in problems))
        self.assertEqual(oc.validate_campaign(camp), [])

    def test_land_check_without_output_branch_is_refused(self):
        camp = self.campaign(acceptance_checks=(oc.AcceptanceCheck("suite", "true"),))
        self.assertTrue(any("names no output branch" in p
                            for p in oc.validate_campaign(camp)))

from __future__ import annotations

import json
import textwrap
import threading
import time
from pathlib import Path

from ohflow import campaign as oc
from ohflow import rundir, supervisor
from ohflow.fingerprint import fingerprint
from ohflow.run_log import RunState
from ohflow.workflow import load_workflow
from support import (AgentScript, FakeHarnessExecutor,
                     install_fake_harness_executor, quiet)

from test_campaign_01_loop import JUDGE_STEP, CampaignCase, _git, decision

CONTRACT = "# Contracts\n\n- `parse(text) -> Tree`, owned by step a. CONTRACT-MARKER\n"

PARALLEL_WORKFLOW_PY = textwrap.dedent('''
    from pathlib import Path
    from ohflow.workflow import (CheckSpec, GateSpec, ModelConfig, Phase, Workflow,
                                 Step, AgentSpec)

    def build(args):
        model = ModelConfig(model="fake/deterministic",
                            base_url="http://127.0.0.1:0/never-called",
                            api_key_env="OHFLOW_TEST_FAKE_KEY")
        def step(sid):
            return Step(id=sid, kind="agent", worktree=None,
                        gate=GateSpec(checks=(CheckSpec("final_message_matches",
                                                        {"regex": "DONE"}),)),
                        agent=AgentSpec(harness_executor="pi", role=sid,
                                        brief=f"Build part {sid}.", model=model,
                                        max_iterations=5))
        return Workflow(name="m1-parallel", repo=Path(args["product"]),
                        base_branch="main", baseline_cmd=None, worktrees=(),
                        phases=(Phase(name="Only phase",
                                      steps=(step("a"), step("b"))),),
                        max_parallel=2, transient_backoff_s=0)
''')

STEPS = ("01.only-phase/01.a", "01.only-phase/02.b")
STEP_REPORT = "DONE STEP-REPORT-MARKER\n"


class ContractsCase(CampaignCase):

    def setUp(self) -> None:
        super().setUp()
        (self.mdir / "workflow.py").write_text(PARALLEL_WORKFLOW_PY, encoding="utf-8")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-m", "parallel workflow")

    def with_contracts(self, rel: str = "contracts.md") -> Path:
        path = self.root / rel
        path.write_text(CONTRACT, encoding="utf-8")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-m", "contracts")
        return path

    def brief(self, step: str) -> str:
        return (self.mdir / "runs" / "m1" / "phases" / step / "attempts" / "01"
                / "brief.md").read_text(encoding="utf-8")

    def packet(self) -> str:
        return (self.mdir / "judge" / "r01" / "packet.md").read_text(encoding="utf-8")

    def run_with_pass(self) -> int:
        harness_executor = FakeHarnessExecutor(
            scripts={JUDGE_STEP: self.judge([decision("PASS")])},
            default=AgentScript(final_text=STEP_REPORT))
        return self.drive(self.campaign(), harness_executor)

    def judge_edits(self, kind: str, path: Path, **kw) -> int:
        def edits():
            path.write_text("JUDGE-REWRITE\n", encoding="utf-8")
            (self.mdir / "notes.md").write_text("a note\n", encoding="utf-8")

        harness_executor = FakeHarnessExecutor(
            scripts={JUDGE_STEP: self.judge([decision(kind)], edits={1: edits})},
            default=AgentScript(final_text="DONE\n"))
        return self.drive(self.campaign(**kw), harness_executor)

    def assert_contracts_intact(self, path: Path, rel: str, **kw) -> None:
        self.assertEqual(path.read_text(encoding="utf-8"), CONTRACT)
        self.assertNotIn(rel, _git(self.root, "status", "--porcelain"))
        self.assertIn(f"judge edit to {rel} on m1 r01",
                      _git(self.root, "stash", "list"))
        text = (self.root / oc.ESCALATION).read_text(encoding="utf-8")
        self.assertIn(f"The judge also edited `{rel}`", text)
        camp = self.campaign(**kw)
        wf = load_workflow(self.root / camp.milestones[0].workflow,
                           oc.milestone_args(camp, camp.milestones[0]))
        self.assertEqual(wf.contracts.text, CONTRACT)


class ContractsReachEveryStep(ContractsCase):

    def test_both_parallel_steps_and_the_packet_carry_the_contract(self):
        self.with_contracts()
        self.assertEqual(self.run_with_pass(), oc.EXIT_DELIVERED)
        path = str(self.root / "contracts.md")
        for step in STEPS:
            brief = self.brief(step)
            self.assertIn("CONTRACT-MARKER", brief, step)
            self.assertIn(path.replace("/", "\\"), brief.replace("/", "\\"), step)
            self.assertIn("Fixed for this run", brief, step)
            self.assertIn("If a contract is unworkable, stop", brief, step)
            self.assertIn("Running beside you right now", brief, step)
        packet = self.packet()
        self.assertIn("## The contracts", packet)
        self.assertIn("CONTRACT-MARKER", packet)
        self.assertIn("- Contracts: `", packet)
        for step in STEPS:
            self.assertIn(f"### {step}: passed (its final message", packet)
        self.assertIn("STEP-REPORT-MARKER", packet)

    def test_a_held_round_released_by_go_still_carries_the_contract(self):
        self.with_contracts()
        original = supervisor.HOLD_POLL_S
        supervisor.HOLD_POLL_S = 0.02
        self.addCleanup(setattr, supervisor, "HOLD_POLL_S", original)
        install_fake_harness_executor(self, FakeHarnessExecutor(
            scripts={JUDGE_STEP: self.judge([decision("PASS")])},
            default=AgentScript(final_text="DONE\n")))
        run_dir = self.mdir / "runs" / "m1"
        result: dict = {}

        def target():
            with quiet():
                result["code"] = oc.CampaignController(
                    self.campaign(), no_dashboard=True, hold=True,
                    say=lambda _m: None,
                    harness_executors=self.harness_executors).run()

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        deadline = time.monotonic() + 30
        while not (run_dir / rundir.HOLD_FILE).exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue((run_dir / rundir.HOLD_FILE).exists(), "the round held")
        (run_dir / rundir.GO_FILE).write_text("now", encoding="utf-8")
        thread.join(120)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result.get("code"), oc.EXIT_DELIVERED)
        recorded = json.loads((run_dir / "workflow.json").read_text(encoding="utf-8"))
        self.assertIn("CONTRACT-MARKER", json.dumps(recorded["contracts"]))
        for step in STEPS:
            self.assertIn("CONTRACT-MARKER", self.brief(step), step)

    def test_an_edited_contract_changes_every_fingerprint(self):
        self.with_contracts()
        camp = self.campaign()
        m = camp.milestones[0]

        def prints() -> list[str]:
            wf = load_workflow(self.root / m.workflow, oc.milestone_args(camp, m))
            return [fingerprint(wf, RunState(), s) for s in wf.phases[0].steps]

        before = prints()
        (self.root / "contracts.md").write_text(CONTRACT + "- one more\n", encoding="utf-8")
        after = prints()
        for b, a in zip(before, after):
            self.assertNotEqual(b, a)


class JudgesCannotChangeTheContracts(ContractsCase):

    def test_a_revise_that_edits_the_contracts_escalates_and_restores_them(self):
        path = self.with_contracts()
        head = _git(self.root, "rev-parse", "HEAD")
        self.assertEqual(self.judge_edits("REVISE", path), oc.EXIT_ESCALATED)
        text = (self.root / oc.ESCALATION).read_text(encoding="utf-8")
        self.assertIn("outside its write scope: contracts.md", text)
        self.assertNotIn("r01", _git(self.root, "log", "--format=%s", f"{head}..HEAD"))
        self.assert_contracts_intact(path, "contracts.md")

    def test_an_escalate_that_edits_the_contracts_restores_them(self):
        path = self.with_contracts()
        self.assertEqual(self.judge_edits("ESCALATE", path), oc.EXIT_ESCALATED)
        self.assert_contracts_intact(path, "contracts.md")

    def test_contracts_inside_the_milestone_directory_are_still_frozen(self):
        rel = "milestones/m1/contracts.md"
        path = self.with_contracts(rel)
        head = _git(self.root, "rev-parse", "HEAD")
        self.assertEqual(self.judge_edits("REVISE", path, contracts=rel),
                         oc.EXIT_ESCALATED)
        text = (self.root / oc.ESCALATION).read_text(encoding="utf-8")
        self.assertIn(f"outside its write scope: {rel}", text)
        self.assertNotIn("r01", _git(self.root, "log", "--format=%s", f"{head}..HEAD"))
        self.assert_contracts_intact(path, rel, contracts=rel)

    def test_a_contracts_path_outside_the_root_fails_validation(self):
        (self.tmp / "outside.md").write_text(CONTRACT, encoding="utf-8")
        problems = oc.validate_campaign(self.campaign(contracts="../outside.md"))
        self.assertTrue(any("contracts outside the campaign root" in p
                            for p in problems), problems)


class NoContracts(ContractsCase):

    def test_a_campaign_without_contracts_renders_none(self):
        camp = self.campaign()
        self.assertIsNone(oc.contracts_path(camp))
        self.assertNotIn("contracts", oc.milestone_args(camp, camp.milestones[0]))
        self.assertEqual(self.run_with_pass(), oc.EXIT_DELIVERED)
        for step in STEPS:
            self.assertNotIn("Contracts:", self.brief(step))
        packet = self.packet()
        self.assertNotIn("## The contracts", packet)
        self.assertNotIn("- Contracts: `", packet)
        self.assertNotIn("STEP-REPORT-MARKER", packet)

    def test_a_named_contracts_file_that_is_missing_fails_validation(self):
        camp = self.campaign(contracts="interfaces.md")
        problems = oc.validate_campaign(camp)
        self.assertTrue(any("contracts missing" in p for p in problems), problems)

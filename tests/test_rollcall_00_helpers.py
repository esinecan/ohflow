"""m5: the pieces the roll-call workflows stand on.

`file_contains` is the check that makes the retry scenario fail on purpose: the
brief never names the token, so only the failure line can teach it.
`clean_commit_checks` is the four checks every committing agent repeats.

The r1 defect: the relay and merge scenarios (r1 and r2) built a shell check on
`git log --merges -1`. A repository with no merge commit has none to find, so
the check read an empty ref and failed a correct agent. The scenarios now say
`since` to the checks that already exist.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))

from support import TempCase, git_repo, use_settings  # noqa: E402

from ohflow.gates import REGISTRY, GateContext, file_contains  # noqa: E402
from ohflow.workflow import clean_commit_checks, load_workflow, validate  # noqa: E402

TOKEN = "ROLLCALL-RETRY-5K2M"


class FileContains(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.repo = git_repo(self.tmp / "repo")

    def ctx(self) -> GateContext:
        return GateContext(
            coord="01.p/01.s", repo=self.repo, worktree=self.repo,
            base_sha="", base_ref="main", attempt_dir=self.tmp / "step",
            log_dir=self.tmp / "step" / "logs")

    def test_a_file_that_holds_the_text_passes(self):
        (self.repo / "a.md").write_text(f"x\n{TOKEN}\n", encoding="utf-8")
        r = file_contains(self.ctx(), path="a.md", text=TOKEN)
        self.assertTrue(r.passed, r)
        self.assertEqual(r.observed, "present")

    def test_the_failure_names_the_token(self):
        (self.repo / "a.md").write_text("x\n", encoding="utf-8")
        r = file_contains(self.ctx(), path="a.md", text=TOKEN, hidden=True)
        self.assertFalse(r.passed)
        self.assertIn(TOKEN, r.observed)

    def test_an_absent_file_fails_and_says_so(self):
        r = file_contains(self.ctx(), path="nope.md", text=TOKEN)
        self.assertFalse(r.passed)
        self.assertIn("nope.md is absent", r.observed)

    def test_bad_arguments_fail_instead_of_reading_outside(self):
        for kw in ({"path": "../x", "text": "t"}, {"path": "", "text": "t"},
                   {"path": "a.md", "text": ""},
                   {"path": str(self.tmp / "x"), "text": "t"}):
            r = file_contains(self.ctx(), **kw)
            self.assertFalse(r.passed, kw)
            self.assertEqual(r.observed, "bad arguments")

    def test_a_hidden_token_stays_out_of_the_description(self):
        describe = REGISTRY["file_contains"].describe
        hidden = describe({"path": "a.md", "text": TOKEN, "hidden": True})
        shown = describe({"path": "a.md", "text": TOKEN})
        self.assertNotIn(TOKEN, hidden)
        self.assertIn(TOKEN, shown)


class CleanCommitChecks(TempCase):

    def test_the_base_checks_carry_since_and_the_owned_path(self):
        checks = clean_commit_checks(("a.md",), since="step_start")
        self.assertEqual([c.name for c in checks],
                         ["commits_past_base", "tree_clean", "ownership"])
        by_name = {c.name: dict(c.args) for c in checks}
        self.assertEqual(by_name["ownership"],
                         {"allowed": ["a.md"], "since": "step_start"})
        self.assertEqual(by_name["commits_past_base"],
                         {"min": 1, "since": "step_start"})

    def test_the_attribution_setting_adds_its_check(self):
        use_settings(self, {"commit_checks": {"no_ai_attribution": True}})
        checks = clean_commit_checks(("a.md",), since="step_start")
        self.assertEqual(checks[-1].name, "no_ai_attribution")
        self.assertEqual(dict(checks[-1].args), {"since": "step_start"})

    def test_a_marker_adds_a_final_message_check(self):
        checks = clean_commit_checks(("a.md",), marker="^DONE$")
        self.assertEqual(checks[-1].name, "final_message_matches")
        self.assertEqual(dict(checks[-1].args), {"regex": "^DONE$"})

    def test_every_check_is_a_registered_gate(self):
        for c in clean_commit_checks(("a.md",), marker="x"):
            self.assertIn(c.name, REGISTRY)


class RelayDefectOnARepoWithNoMergeCommit(TempCase):
    """Red on the old workflow: it shelled out to `git log --merges -1`."""

    def setUp(self) -> None:
        super().setUp()
        self.repo = git_repo(self.tmp / "repo")

    def workflow(self, scenario: str):
        return validate(load_workflow("ohflow.workflows.rollcall", {
            "repo": str(self.repo), "scenario": scenario, "harness_executors": "pi,claude",
            "wt_root": str(self.tmp / "wt")}))

    def commands(self, workflow) -> list[str]:
        found = []
        for _p, _i, _j, step in workflow.steps():
            if step.gate is None:
                continue
            for c in step.gate.checks:
                found.append(str(dict(c.args).get("cmd", "")))
        return found

    def test_no_scenario_asks_git_for_a_merge_commit(self):
        for scenario in ("r0", "r1", "r2", "relay", "merge"):
            for cmd in self.commands(self.workflow(scenario)):
                self.assertNotIn("--merges", cmd, f"{scenario}: {cmd}")

    def test_r1_uses_the_ownership_check_since_its_own_start(self):
        workflow = self.workflow("r1")
        for _p, _i, _j, step in workflow.steps():
            owner = [c for c in step.gate.checks if c.name == "ownership"]
            self.assertEqual(len(owner), 1, step.id)
            self.assertEqual(dict(owner[0].args)["since"], "step_start")

    def test_r2_consolidator_measures_from_the_last_merge(self):
        workflow = self.workflow("r2")
        steps = {s.id: s for _p, _i, _j, s in workflow.steps()}
        owner = [c for c in steps["consolidate"].gate.checks
                 if c.name == "ownership"]
        self.assertEqual(dict(owner[0].args)["since"], "last_merge")

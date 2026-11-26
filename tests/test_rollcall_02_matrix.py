"""m5: the matrix runner, over a fake harness executor that does the roll-call task.

`ohflow rollcall` prints one verdict line per test case and a last line. These tests
run real test cases through `supervisor.run_workflow` with `RollcallHarnessExecutor`, so a scenario that
the workflow builds is a scenario that the engine runs, gates and resumes. No model is
called.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))

from rollcall_support import RollcallHarnessExecutor, resolver, write_config  # noqa: E402
from support import TempCase, AgentScript, stub_preflight  # noqa: E402

from ohflow import rollcall  # noqa: E402

VERDICT_LINE = re.compile(r"^(PASS|FAIL|SKIP) ")


class MatrixCase(TempCase):

    def setUp(self) -> None:
        super().setUp()
        stub_preflight(self)
        patch = mock.patch.dict(os.environ, {"OHFLOW_TEST_FAKE_KEY": "x"})
        patch.start()
        self.addCleanup(patch.stop)
        self.config = write_config(self.tmp / "config.json")
        self.out = self.tmp / "out"

    def run_cases(self, harness_executor: RollcallHarnessExecutor, cases: list[str], **kw):
        lines: list[str] = []
        code = rollcall.run_matrix(
            cases=cases, out=str(self.out), config=self.config,
            harness_executors=kw.pop("harness_executors", resolver(harness_executor)), write=lines.append, **kw)
        return code, lines

    def matrix_json(self) -> dict:
        return json.loads((self.out / "matrix.json").read_text(encoding="utf-8"))


class OneLinePerCase(MatrixCase):
    """Each test case costs about 13 s of git calls, so one run carries many asserts."""

    def test_two_cases_print_two_pass_lines_and_the_last_line(self):
        code, lines = self.run_cases(RollcallHarnessExecutor(),
                                     ["single:pi", "relay:pi,claude"])
        self.assertEqual(code, rollcall.EXIT_OK, lines)
        self.assertEqual(len(lines), 3, lines)
        self.assertRegex(lines[0], r"^PASS single pi count=1  \d+m\d\ds  "
                                   r"[\d.]+ k tokens  .*run$")
        self.assertTrue(lines[1].startswith("PASS relay pi,claude count=1 "))
        self.assertEqual(lines[-1], "ROLLCALL PASS: 2 of 2 test cases")
        cases = self.matrix_json()["cases"]
        self.assertEqual([c["resume"] for c in cases], ["ok", "ok"])

    def test_a_case_runs_in_its_own_directory_and_worktree_root(self):
        self.run_cases(RollcallHarnessExecutor(skip=("claude-1",)),
                       ["single:pi", "single:claude"])
        dirs = sorted(p.name for p in self.out.iterdir()
                      if p.is_dir() and p.name != "repo")
        self.assertEqual(dirs, ["01-single-pi-1", "02-single-claude-1"])
        roots = {d: json.loads(next((self.out / d / "run").rglob("spec.json"))
                               .read_text(encoding="utf-8"))["workspace"]
                 for d in dirs}
        self.assertEqual(len(set(roots.values())), 2)
        for d, workspace in roots.items():
            self.assertIn(d, workspace)

    def test_fanout_merge_and_review_pass_on_the_fake_harness_executor(self):
        cases = ["fanout:pi,claude", "merge:pi,claude", "review:pi,claude"]
        code, lines = self.run_cases(RollcallHarnessExecutor(), cases)
        self.assertEqual(code, rollcall.EXIT_OK, "\n".join(lines))
        self.assertEqual(lines[-1], "ROLLCALL PASS: 3 of 3 test cases")

    def test_a_resume_that_started_a_step_reads_as_a_fault(self):
        with mock.patch.object(rollcall, "_started", side_effect=[1, 2]):
            code, lines = self.run_cases(RollcallHarnessExecutor(), ["single:pi"])
        self.assertEqual(code, rollcall.EXIT_FAIL)
        self.assertRegex(lines[0], r"^FAIL .*resume check: resume started 1 "
                                   r"step\(s\)")


class AFailingCaseNamesItsStep(MatrixCase):

    def test_a_fail_line_names_the_first_failing_step_and_check(self):
        harness_executor = RollcallHarnessExecutor(skip=("pi-1",))
        code, lines = self.run_cases(harness_executor, ["single:pi", "single:claude"])
        self.assertEqual(code, rollcall.EXIT_FAIL)
        self.assertRegex(lines[0], r"^FAIL single pi count=1 ")
        self.assertIn("step pi-1: gate commits_past_base failed", lines[0])
        self.assertTrue(lines[1].startswith("PASS "), lines)
        self.assertEqual(lines[-1],
                         "ROLLCALL FAIL: 1 of 2 test cases failed, 0 skipped")

    def test_a_case_that_does_not_build_is_a_fail_with_the_reason(self):
        code, lines = self.run_cases(RollcallHarnessExecutor(), ["fanout:pi,pi"])
        self.assertEqual(code, rollcall.EXIT_FAIL)
        self.assertRegex(lines[0], r"^FAIL fanout pi,pi count=1  0m00s  "
                                   r"0 tokens  workflow does not build: .*harness executor "
                                   r"twice")


class ASkippedHarnessExecutor(MatrixCase):

    def test_a_harness_executor_that_fails_preflight_gives_skip_and_matrix_json_holds_all(self):
        good = RollcallHarnessExecutor()
        bad = RollcallHarnessExecutor(preflight_faults=["claude is not signed in"])
        code, lines = self.run_cases(
            good, ["single:pi", "single:claude", "fanout:pi,claude"],
            harness_executors=resolver(good, bad={"claude": bad}))
        self.assertEqual(code, rollcall.EXIT_OK, lines)
        self.assertTrue(lines[0].startswith("PASS "), lines)
        self.assertRegex(lines[1], r"^SKIP single claude count=1  .*"
                                   r"claude is not signed in")
        self.assertTrue(lines[2].startswith("SKIP fanout pi,claude "), lines)
        self.assertEqual(lines[-1], "ROLLCALL PASS: 1 of 3 test cases, 2 skipped")
        self.assertEqual(bad.launched, [])
        self.assertEqual(len(good.launched), 1)
        doc = self.matrix_json()
        self.assertEqual(doc["configuration"], "fake-config")
        self.assertEqual(doc["cases_total"], 3)
        self.assertEqual([c["verdict"] for c in doc["cases"]],
                         ["PASS", "SKIP", "SKIP"])
        self.assertEqual(doc["cases"][1]["label"], "single claude count=1")
        self.assertIn("not signed in", doc["cases"][1]["reason"])
        self.assertGreater(doc["cases"][0]["tokens"], 0)

    def test_a_run_of_only_skips_reads_fail(self):
        bad = RollcallHarnessExecutor(preflight_faults=["no login"])
        code, lines = self.run_cases(bad, ["single:pi"])
        self.assertEqual(code, rollcall.EXIT_FAIL)
        self.assertEqual(lines[-1],
                         "ROLLCALL FAIL: 0 of 1 test cases failed, 1 skipped")
        self.assertEqual(bad.launched, [])

    def test_matrix_json_is_rewritten_after_each_case(self):
        bad = RollcallHarnessExecutor(preflight_faults=["no login"])
        seen: list[int] = []

        def write(line: str) -> None:
            if VERDICT_LINE.match(line):
                seen.append(len(self.matrix_json()["cases"]))

        rollcall.run_matrix(cases=["single:pi", "single:claude"],
                            out=str(self.out), config=self.config,
                            harness_executors=resolver(bad), write=write)
        self.assertEqual(seen, [1, 2])

    def test_a_harness_executor_whose_key_is_unset_gives_skip(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("OHFLOW_TEST_FAKE_KEY")
            code, lines = self.run_cases(RollcallHarnessExecutor(), ["single:pi"])
        self.assertEqual(code, rollcall.EXIT_FAIL)
        self.assertRegex(lines[0], r"^SKIP single pi count=1  pi harness executor: "
                                   r"OHFLOW_TEST_FAKE_KEY is empty or unset")


class RetryCase(MatrixCase):

    def test_a_retry_case_runs_two_attempts_and_the_second_learns_the_token(self):
        harness_executor = RollcallHarnessExecutor()
        code, lines = self.run_cases(harness_executor, ["retry:pi"])
        self.assertEqual(code, rollcall.EXIT_OK, lines)
        self.assertEqual(harness_executor.attempts["pi-1"], 2)
        target = next(self.out.rglob("rollcall/pi-1.md"))
        self.assertRegex(target.read_text(encoding="utf-8"),
                         r"ROLLCALL-RETRY-\w+")


class CampaignCase(MatrixCase):

    def judge(self) -> AgentScript:
        def verdict(kind, revisions=()):
            return {"decision": kind, "summary": f"{kind} summary",
                    "findings": [], "revisions": list(revisions),
                    "question_for_operator": None}

        judge = AgentScript(sequence=[
            {"final_text": "x", "structured": verdict("REVISE", [
                {"path": "milestones/m1/briefs/impl.md",
                 "why": "adds the line"}])},
            {"final_text": "x", "structured": verdict("PASS")}])

        def act() -> None:
            n = judge.launches
            camp = next(self.out.glob("*campaign*/campaign"))
            m = camp / "milestones" / "m1"
            handover = m / "judge" / f"r{n:02d}" / "judge-handover.md"
            handover.parent.mkdir(parents=True, exist_ok=True)
            handover.write_text("# handover\n", encoding="utf-8")
            if n == 1:
                brief = m / "briefs" / "impl.md"
                brief.write_text(
                    brief.read_text(encoding="utf-8")
                    + "\n4. Add the line `Campaign-Token: M5-ROLLCALL` to "
                      "your file before you commit.\n", encoding="utf-8")

        judge.on_poll = act
        return judge

    def test_a_campaign_case_revises_once_then_delivers(self):
        harness_executor = RollcallHarnessExecutor(judge=self.judge())
        code, lines = self.run_cases(harness_executor, ["campaign:pi"])
        self.assertEqual(code, rollcall.EXIT_OK, "\n".join(lines))
        self.assertRegex(lines[0], r"^PASS campaign pi count=1 ")
        self.assertEqual(lines[-1], "ROLLCALL PASS: 1 of 1 test cases")


class TheTable(MatrixCase):

    def test_liveness_is_one_silent_case_per_harness_executor(self):
        self.assertEqual([c.label for c in rollcall.MATRICES["liveness"]],
                         [f"silent {h} count=1" for h in rollcall.THREE])

    def test_smoke_is_single_pi_claude_and_codex(self):
        self.assertEqual([c.label for c in rollcall.MATRICES["smoke"]],
                         ["single pi count=1", "single claude count=1",
                          "single codex count=1"])

    def test_full_adds_scale_campaign_hermetic_and_carry_context(self):
        extra = [c.label for c in rollcall.MATRICES["full"][8:]]
        self.assertEqual(extra, [
            "fanout pi count=3", "campaign pi count=1",
            "single claude count=1 agent_profile=hermetic",
            "single codex count=1 agent_profile=hermetic",
            "retry claude count=1 carry_context"])

    def test_list_prints_every_matrix_and_its_cases(self):
        lines = rollcall.list_lines()
        self.assertEqual([x for x in lines if not x.startswith(" ")],
                         ["smoke: 3 test cases", "quick: 8 test cases",
                          "full: 13 test cases", "liveness: 3 test cases"])
        self.assertEqual(len(lines), 4 + 3 + 8 + 13 + 3)

    def test_parse_case_reads_harness_executors_count_and_options(self):
        case = rollcall.parse_case("fanout:pi,claude:3:agent_profile=hermetic")
        self.assertEqual((case.scenario, case.harness_executors, case.count, case.options),
                         ("fanout", ("pi", "claude"), 3,
                          (("agent_profile", "hermetic"),)))
        flag = rollcall.parse_case("retry:claude:carry_context")
        self.assertEqual(flag.options, (("carry_context", "true"),))

    def test_parse_case_refuses_a_malformed_case(self):
        for text in ("single", ":pi", "single:pi:what"):
            with self.assertRaises(ValueError, msg=text):
                rollcall.parse_case(text)

    def test_a_malformed_case_on_the_command_line_is_a_workflow_error(self):
        code, lines = self.run_cases(RollcallHarnessExecutor(), ["single"])
        self.assertEqual(code, rollcall.EXIT_WORKFLOW)
        self.assertRegex(lines[-1], r"^ROLLCALL INVALID: test case 'single' must "
                                    r"read scenario:harness-executors")

    def test_an_unknown_matrix_is_a_workflow_error_that_lists_the_matrices(self):
        lines: list[str] = []
        code = rollcall.run_matrix(matrix="huge", out=str(self.out),
                                   write=lines.append)
        self.assertEqual(code, rollcall.EXIT_WORKFLOW)
        self.assertIn("['smoke', 'quick', 'full', 'liveness']", lines[-1])


class DryRun(MatrixCase):

    def test_a_dry_run_builds_every_case_and_starts_nothing(self):
        harness_executor = RollcallHarnessExecutor()
        lines: list[str] = []
        code = rollcall.run_matrix(matrix="full", dry=True, out=str(self.out),
                                   config=self.config, harness_executors=resolver(harness_executor),
                                   write=lines.append)
        self.assertEqual(code, rollcall.EXIT_OK, lines)
        self.assertEqual(lines[-1], "ROLLCALL DRY: 13 test cases valid")
        self.assertEqual(sum(x.startswith("WORKFLOW ") for x in lines), 13)
        self.assertEqual(harness_executor.launched, [])
        self.assertFalse((self.out / "repo").exists())

    def test_a_dry_run_names_a_case_that_does_not_build(self):
        lines: list[str] = []
        code = rollcall.run_matrix(cases=["fanout:pi,pi", "single:pi"],
                                   dry=True, out=str(self.out),
                                   write=lines.append)
        self.assertEqual(code, rollcall.EXIT_WORKFLOW)
        self.assertTrue(lines[0].startswith("INVALID fanout pi,pi"), lines)
        self.assertEqual(lines[-1], "ROLLCALL DRY: 1 of 2 test cases invalid")

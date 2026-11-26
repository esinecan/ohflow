"""Stage 12: review fan-out by named dimension and deterministic consolidation."""

from __future__ import annotations

import json
import os

from ohflow.engine import Engine
from ohflow.workflow import validate
from ohflow.workflows.review_by_dimension import REVIEW_SCHEMA, build, consolidate
from support import (FakeHarnessExecutor, TempCase, AgentScript, git_repo,
                     install_fake_harness_executor, stub_preflight)


def report(dimension: str, verdict: str, *, finding: bool = False) -> dict:
    findings = ([{"severity": "BLOCKING", "path": "src/a.py", "line": 7,
                  "claim": "the boundary accepts an invalid value"}]
                if finding else [])
    return {"dimension": dimension, "verdict": verdict,
            "findings": findings, "summary": f"{dimension} says {verdict}"}


class ReviewByDimensionFlow(TempCase):

    def _run(self, verdicts: dict[str, str], *, retry_security: bool = False):
        repo = git_repo(self.tmp / ("repo-" + "-".join(verdicts.values())))
        briefs = self.tmp / ("briefs-" + "-".join(verdicts.values()))
        briefs.mkdir()
        for dimension in verdicts:
            (briefs / f"{dimension}.md").write_text(
                f"Judge {dimension}.\n", encoding="utf-8")
        run_dir = self.run_dir("run-" + "-".join(verdicts.values()))
        scripts = {}
        for dimension, verdict in verdicts.items():
            valid = report(dimension, verdict, finding=verdict == "BLOCKED")
            if retry_security and dimension == "security":
                scripts[f"review-{dimension}"] = AgentScript(sequence=[
                    {"structured": None}, {"structured": valid},
                ])
            else:
                scripts[f"review-{dimension}"] = AgentScript(structured=valid)
        harness_executor = install_fake_harness_executor(
            self, FakeHarnessExecutor(scripts=scripts, gate_at=len(verdicts)))
        stub_preflight(self)
        args = {
            "repo": str(repo), "worktree": str(repo), "branch": "main",
            "base": "main", "dimensions": ",".join(verdicts),
            "brief_dir": str(briefs), "harness_executor": "pi",
            "harness_executors": "security=pi",
            "schema_retry": 1,
        }
        workflow = validate(build(args))
        summary = Engine(workflow, run_dir, run_id=run_dir.name,
                         verbose=False,
                         harness_executors=self.harness_executors).run()
        attempt = (run_dir / "phases" / "02.consolidate" / "01.consolidate"
                   / "attempts" / "01")
        self.assertTrue((attempt / "verdict.json").exists(),
                        json.dumps(summary, indent=2, default=str))
        return workflow, harness_executor, summary, attempt

    def test_fanout_harness_executor_override_schema_retry_and_blocked_artifacts(self):
        workflow, harness_executor, summary, attempt = self._run(
            {"correctness": "PASS", "security": "BLOCKED"},
            retry_security=True)

        self.assertEqual(workflow.phases[0].max_parallel, 2)
        self.assertEqual([s.agent.harness_executor for s in workflow.phases[0].steps],
                         ["pi", "pi"])
        self.assertIs(workflow.phases[0].steps[0].schema, REVIEW_SCHEMA)
        self.assertEqual(harness_executor.peak, 2)
        self.assertEqual(harness_executor.script_for("review-security").launches, 2)
        self.assertEqual(summary["status"], "finished")

        verdict = json.loads((attempt / "verdict.json").read_text(
            encoding="utf-8"))
        markdown = (attempt / "review.md").read_text(encoding="utf-8")
        self.assertEqual(verdict["verdict"], "BLOCKED")
        self.assertEqual([r["dimension"] for r in verdict["dimensions"]],
                         ["correctness", "security"])
        self.assertIn("VERDICT: BLOCKED", markdown)
        self.assertLess(markdown.index("## correctness"),
                        markdown.index("## security"))
        self.assertIn("`src/a.py:7`", markdown)
        command_result = json.loads((attempt / "result.json").read_text(
            encoding="utf-8"))
        run_var, attempt_var = (
            ("%OHFLOW_RUN_DIR%", "%OHFLOW_ATTEMPT_DIR%") if os.name == "nt"
            else ("$OHFLOW_RUN_DIR", "$OHFLOW_ATTEMPT_DIR"))
        self.assertIn(run_var, command_result["cmd"])
        self.assertIn(attempt_var, command_result["cmd"])

    def test_all_passing_dimensions_consolidate_to_pass(self):
        _workflow, _harness_executor, _summary, attempt = self._run(
            {"correctness": "PASS", "security": "PASS"})
        verdict = json.loads((attempt / "verdict.json").read_text(
            encoding="utf-8"))
        markdown = (attempt / "review.md").read_text(encoding="utf-8")
        self.assertEqual(verdict["verdict"], "PASS")
        self.assertIn("VERDICT: PASS", markdown)


class ReviewByDimensionValidation(TempCase):

    def _args(self) -> dict:
        briefs = self.tmp / "briefs"
        briefs.mkdir(exist_ok=True)
        (briefs / "correctness.md").write_text("check it", encoding="utf-8")
        return {"dimensions": "correctness", "brief_dir": str(briefs),
                "harness_executor": "pi"}

    def test_dimensions_reject_empty_duplicate_and_unsafe_names(self):
        for value in ("", "correctness,", "correctness,correctness", "../escape"):
            args = self._args(); args["dimensions"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                build(args)

    def test_missing_brief_is_named(self):
        args = self._args(); args["dimensions"] = "correctness,security"
        with self.assertRaisesRegex(ValueError, "security.md"):
            build(args)

    def test_harness_executor_overrides_must_name_a_dimension_and_known_harness_executor(self):
        for value in ("other=pi", "correctness=container", "correctness",
                      "correctness=pi,correctness=pi", "correctness=host"):
            args = self._args(); args["harness_executors"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                build(args)

    def test_schema_retry_is_non_negative_and_public_args_are_sufficient(self):
        for value in (-1, "many"):
            args = self._args(); args["schema_retry"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                build(args)
        self.assertEqual(build(self._args()).args["dimensions"], "correctness")

    def test_consolidation_reads_and_writes_the_latest_attempt(self):
        run = self.tmp / "run"
        for attempt, verdict in (("01", "BLOCKED"), ("02", "PASS")):
            source = (run / "phases" / "01.review-by-dimension" /
                      "01.review-correctness" / "attempts" / attempt)
            source.mkdir(parents=True)
            (source / "result.json").write_text(json.dumps({
                "structured": report("correctness", verdict)}), encoding="utf-8")
        for attempt in ("01", "02"):
            (run / "phases" / "02.consolidate" / "01.consolidate" /
             "attempts" / attempt).mkdir(parents=True)

        review, verdict = consolidate(run, ("correctness",))

        self.assertEqual(review.parent.name, "02")
        self.assertEqual(verdict.parent.name, "02")
        self.assertEqual(json.loads(verdict.read_text(encoding="utf-8"))["verdict"],
                         "PASS")

    def test_attempt_numbers_are_ordered_numerically_past_99(self):
        run = self.tmp / "run"
        for attempt, verdict in (("99", "BLOCKED"), ("100", "PASS")):
            source = (run / "phases" / "01.review-by-dimension" /
                      "01.review-correctness" / "attempts" / attempt)
            source.mkdir(parents=True)
            (source / "result.json").write_text(json.dumps({
                "structured": report("correctness", verdict)}), encoding="utf-8")
            (run / "phases" / "02.consolidate" / "01.consolidate" /
             "attempts" / attempt).mkdir(parents=True)

        _review, verdict = consolidate(run, ("correctness",))

        self.assertEqual(verdict.parent.name, "100")
        self.assertEqual(json.loads(verdict.read_text(encoding="utf-8"))["verdict"],
                         "PASS")


if __name__ == "__main__":
    import unittest
    unittest.main()

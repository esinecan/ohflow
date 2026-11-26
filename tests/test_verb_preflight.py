"""m4: `ohflow preflight` prints `PREFLIGHT PASS: N checks` or `PREFLIGHT FAIL:
F of N checks`, then one `FAIL <need>: <observed>; <what to do>` per failure.

The checks are data (`ohflow.preflight.Check`), and `-v` lists the passed
checks too.
"""

from __future__ import annotations

import os
from unittest import mock

from ohflow import cli
from support import FakeHarnessExecutor, TempCase, fake_pi_executable
from verb_support import call


DUPLICATE_IDS = """
from pathlib import Path
from ohflow.workflow import Phase, Workflow, Step

def build(args):
    step = Step(id="a", kind="command", command="echo DONE")
    return Workflow(name="dup", repo=Path("."),
                    phases=(Phase(name="p", steps=(step, step)),))
"""


class BrokenHarnessExecutor(FakeHarnessExecutor):

    def preflight(self) -> list[str]:
        return ["the model endpoint is down; start it with `serve`"]


class PreflightVerdict(TempCase):

    def setUp(self) -> None:
        super().setUp()
        # A fake pi: the pi preflight looks for the pi CLI, and the suite
        # runs from a fresh clone with no pi installed.
        patch = mock.patch.dict(os.environ, {
            "OHFLOW_PI_EXE": str(fake_pi_executable(self.tmp))})
        patch.start()
        self.addCleanup(patch.stop)

    def test_preflight_a_harness_executor_with_no_problem_passes(self):
        code, lines = call("preflight", "--harness-executors", "pi", harness_executors=self.harness_executors)
        self.assertEqual(code, cli.EXIT_OK)
        self.assertRegex(lines[0], r"^PREFLIGHT PASS: \d+ checks?$")
        self.assertEqual(len(lines), 1)

    def test_preflight_a_failing_harness_executor_names_the_failure_and_exits_1(self):
        code, lines = call("preflight", "--harness-executors", "pi",
                           harness_executors=lambda name: BrokenHarnessExecutor())
        self.assertEqual(code, cli.EXIT_FAIL)
        self.assertRegex(lines[0], r"^PREFLIGHT FAIL: 1 of \d+ checks?$")
        self.assertRegex(lines[1], r"^FAIL .+: .+; .+")
        self.assertIn("the model endpoint is down", "\n".join(lines))
        self.assertLessEqual(len(lines), 6)

    def test_preflight_verbose_adds_a_line_for_each_passed_check(self):
        _code, plain = call("preflight", "--harness-executors", "pi", harness_executors=self.harness_executors)
        code, verbose = call("preflight", "--harness-executors", "pi", "-v",
                             harness_executors=self.harness_executors)
        self.assertEqual(code, cli.EXIT_OK)
        self.assertEqual(verbose[0], plain[0])
        self.assertTrue(any(line.startswith("PASS ") for line in verbose[1:]),
                        verbose)

    def test_preflight_a_workflow_that_does_not_load_is_one_failed_check(self):
        code, lines = call("preflight", "--workflow", "no_such_workflow_module",
                           "--harness-executors", "pi", harness_executors=self.harness_executors)
        self.assertEqual(code, cli.EXIT_FAIL)
        self.assertRegex(lines[0], r"^PREFLIGHT FAIL: 1 of \d+ checks?$")
        self.assertRegex(lines[1], r"^FAIL workflow: ModuleNotFoundError: .+; "
                                   r"fix the workflow module or its --args$")
        self.assertLessEqual(len(lines), 3)

    def test_preflight_a_workflow_that_fails_validate_is_one_failed_check(self):
        workflow = self.tmp / "dup.py"
        workflow.write_text(DUPLICATE_IDS, encoding="utf-8")
        code, lines = call("preflight", "--workflow", workflow.as_posix(),
                           "--harness-executors", "pi", harness_executors=self.harness_executors)
        self.assertEqual(code, cli.EXIT_FAIL)
        self.assertRegex(lines[0], r"^PREFLIGHT FAIL: 1 of \d+ checks?$")
        self.assertRegex(lines[1], r"^FAIL workflow: WorkflowError: .+; fix the workflow "
                                   r"module or its --args$")

    def test_preflight_json_carries_the_verdict_and_each_check(self):
        import json
        code, lines = call("preflight", "--harness-executors", "pi", "--json",
                           harness_executors=self.harness_executors)
        self.assertEqual(code, cli.EXIT_OK)
        data = json.loads("\n".join(lines))
        self.assertTrue(data["pass"])
        self.assertTrue(data["results"])
        self.assertTrue(all(r["status"] in ("PASS", "SKIP")
                            for r in data["results"]))

        code, lines = call("preflight", "--harness-executors", "pi", "--json",
                           harness_executors=lambda name: BrokenHarnessExecutor())
        self.assertEqual(code, cli.EXIT_FAIL)
        data = json.loads("\n".join(lines))
        self.assertFalse(data["pass"])
        failed = [r for r in data["results"] if r["status"] == "FAIL"]
        self.assertEqual(len(failed), 1, data["results"])
        self.assertIn("the model endpoint is down", failed[0]["observed"])
        self.assertTrue(failed[0]["need"])
        self.assertTrue(failed[0]["fix"])


if __name__ == "__main__":
    import unittest
    unittest.main()

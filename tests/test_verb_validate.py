"""m4: `ohflow validate` prints a verdict on line one.

Before: it printed `OK <workflow>` and a listing of every step. Now line one is
`VALID <workflow>: X phases, Y steps; harness executors <harness executor>:<n>, ...` (exit 0) or `INVALID
<workflow>: N problems` (exit 2). `-v` adds the per-step detail.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from ohflow import cli
from support import TempCase
from verb_support import call

WORKFLOWS = Path(__file__).resolve().parents[1] / "scripts" / "ohflow" / "workflows"
ROLLCALL = ["validate", "--workflow", (WORKFLOWS / "rollcall.py").as_posix(),
            "--args", "repo=.", "--args", "scenario=r0", "--args", "harness_executors=pi"]

DUPLICATE_IDS = """
from pathlib import Path
from ohflow.workflow import Phase, Workflow, Step

def build(args):
    step = Step(id="a", kind="command", command="echo DONE")
    return Workflow(name="dup", repo=Path("."),
                    phases=(Phase(name="p", steps=(step, step)),))
"""


class ValidateVerdict(TempCase):

    def test_validate_a_good_workflow_reads_valid_with_its_harness_executor_counts(self):
        code, lines = call(*ROLLCALL)
        self.assertEqual(code, cli.EXIT_OK)
        self.assertRegex(
            lines[0], r"^VALID rollcall-r0: 1 phases?, 1 steps?; harness executors pi:1")
        self.assertLessEqual(len(lines), 4)

    def test_validate_verbose_adds_the_detail_of_each_step(self):
        _code, plain = call(*ROLLCALL)
        code, verbose = call(*ROLLCALL, "-v")
        self.assertEqual(code, cli.EXIT_OK)
        self.assertEqual(verbose[0], plain[0])
        self.assertGreater(len(verbose), len(plain))
        self.assertTrue(any("harness_executor=pi" in line for line in verbose), verbose)

    def test_validate_a_bad_workflow_reads_invalid_and_exits_2(self):
        workflow = self.tmp / "dup.py"
        workflow.write_text(textwrap.dedent(DUPLICATE_IDS), encoding="utf-8")
        code, lines = call("validate", "--workflow", workflow.as_posix())
        self.assertEqual(code, cli.EXIT_WORKFLOW)
        self.assertRegex(lines[0], r"^INVALID dup: \d+ problems?$")
        self.assertTrue(any("duplicate step id" in line for line in lines[1:]),
                        lines)
        self.assertLessEqual(len(lines), 6)

    def test_validate_a_workflow_that_will_not_build_reads_invalid_and_exits_2(self):
        code, lines = call("validate", "--workflow", (WORKFLOWS / "rollcall.py").as_posix(),
                           "--args", "repo=.", "--args", "scenario=bogus",
                           "--args", "harness_executors=pi")
        self.assertEqual(code, cli.EXIT_WORKFLOW)
        self.assertEqual(lines[0], "INVALID rollcall: 1 problem")
        self.assertRegex(lines[1], r"^- ValueError: .*bogus")
        self.assertLessEqual(len(lines), 3)

    def test_validate_a_module_name_is_named_by_its_last_part(self):
        code, lines = call("validate", "--workflow", "no_such_pkg.no_such_workflow")
        self.assertEqual(code, cli.EXIT_WORKFLOW)
        self.assertEqual(lines[0], "INVALID no_such_workflow: 1 problem")
        self.assertRegex(lines[1], r"^- ModuleNotFoundError: ")

    def test_validate_a_missing_argument_keeps_its_pinned_text(self):
        code, lines = call("validate", "--workflow", (WORKFLOWS / "rollcall.py").as_posix())
        self.assertEqual(code, cli.EXIT_WORKFLOW)
        self.assertRegex(lines[0], r"^workflow argument missing: \w+ "
                                   r"\(pass --args \w+=\.\.\.\)$")

    def test_validate_json_names_the_verdict(self):
        import json
        code, lines = call(*ROLLCALL, "--json")
        self.assertEqual(code, cli.EXIT_OK)
        data = json.loads("\n".join(lines))
        self.assertTrue(data["valid"])
        self.assertEqual(data["harness_executors"], {"pi": 1})


if __name__ == "__main__":
    import unittest
    unittest.main()

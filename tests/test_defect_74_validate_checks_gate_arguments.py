"""Defect 74: `validate` accepted a check argument that the check does not take.

What went wrong. `validate` looked only at the name of each `CheckSpec`. A
misspelt argument, `CheckSpec("command_exit", {"cmdd": "npm test"})`, read VALID.
The run started, the agent did its work, and only then `gates.run_gate` called
the check and recorded `TypeError: command_exit() got an unexpected keyword
argument 'cmdd'` as a gate failure.

What is asserted here. `validate` reads each check's arguments against the
signature of the check in `gates.REGISTRY` and refuses the workflow with a
message that names the step, the check and the argument. `ctx` is the engine's
own argument and no workflow may pass it. The `validate` verb reads INVALID for
such a workflow, and every check a helper in `workflow.py` builds still passes.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from ohflow import cli, gates
from ohflow.workflow import (CheckSpec, GateSpec, Phase, Step, Workflow, WorkflowError,
                             clean_commit_checks, house_checks, validate)
from support import TempCase
from verb_support import call

MISSPELT = """
from pathlib import Path
from ohflow.workflow import CheckSpec, GateSpec, Phase, Step, Workflow

def build(args):
    step = Step(id="tests", kind="command", command="echo DONE",
                gate=GateSpec((CheckSpec("command_exit", {"cmdd": "npm test"}),)))
    return Workflow(name="misspelt", repo=Path("."),
                    phases=(Phase(name="check", steps=(step,)),))
"""


def one_step(*checks: CheckSpec) -> Workflow:
    step = Step(id="tests", kind="command", command="echo DONE", gate=GateSpec(checks))
    return Workflow(name="w", repo=Path("."), phases=(Phase(name="check", steps=(step,)),))


class ValidateChecksGateArguments(TempCase):

    def problems(self, *checks: CheckSpec) -> list[str]:
        with self.assertRaises(WorkflowError) as caught:
            validate(one_step(*checks))
        return str(caught.exception).splitlines()

    def test_an_argument_the_check_does_not_take_is_refused_by_name(self):
        problems = self.problems(CheckSpec("command_exit", {"cmdd": "npm test"}))
        self.assertEqual(problems, [
            "01.check/01.tests: gate check 'command_exit' takes no argument 'cmdd'; "
            "it takes: cmd, expect, shell, timeout, reuse"])

    def test_a_check_without_arguments_says_so(self):
        problems = self.problems(CheckSpec("tree_clean", {"since": "base"}))
        self.assertEqual(problems, [
            "01.check/01.tests: gate check 'tree_clean' takes no argument 'since'; "
            "it takes: no arguments"])

    def test_the_gate_context_is_not_a_workflow_argument(self):
        problems = self.problems(CheckSpec("tree_clean", {"ctx": None}))
        self.assertIn("takes no argument 'ctx'", problems[0])

    def test_every_bad_argument_of_every_check_is_listed(self):
        problems = self.problems(
            CheckSpec("command_exit", {"cmd": "true", "expects": 0}),
            CheckSpec("file_contains", {"path": "a.txt", "contains": "x", "regex": "y"}))
        self.assertEqual(len(problems), 3, problems)
        self.assertIn("'command_exit' takes no argument 'expects'", problems[0])
        self.assertIn("'file_contains' takes no argument 'contains'", problems[1])
        self.assertIn("'file_contains' takes no argument 'regex'", problems[2])

    def test_a_check_that_needs_an_argument_is_refused_without_it(self):
        def needs_path(ctx, path):
            return gates.GateResult("needs_path", True)
        gates.REGISTRY["needs_path"] = needs_path
        self.addCleanup(gates.REGISTRY.pop, "needs_path")
        problems = self.problems(CheckSpec("needs_path"))
        self.assertEqual(problems, [
            "01.check/01.tests: gate check 'needs_path' needs the argument 'path'"])

    def test_arguments_that_are_no_mapping_are_refused_and_pairs_still_pass(self):
        problems = self.problems(CheckSpec("command_exit", None))
        self.assertEqual(problems, [
            "01.check/01.tests: gate check 'command_exit' takes its arguments as a "
            "mapping, not NoneType"])
        pairs = CheckSpec("command_exit", [("cmd", "true")])
        self.assertIs(validate(one_step(pairs)).name, "w")

    def test_the_arguments_each_check_takes_still_pass(self):
        checks = (*house_checks(), *clean_commit_checks(("src/**",), marker="^DONE$"),
                  CheckSpec("command_exit", {"cmd": "true", "expect": 0, "shell": "sh",
                                             "timeout": 60}),
                  CheckSpec("file_contains", {"path": "a.txt", "text": "x"}),
                  CheckSpec("paths_untouched", {"globs": ["docs/**"]}),
                  CheckSpec("schema_valid", {}))
        self.assertIs(validate(one_step(*checks)).name, "w")

    def test_the_validate_verb_reads_invalid_and_names_the_argument(self):
        workflow = self.tmp / "misspelt.py"
        workflow.write_text(textwrap.dedent(MISSPELT), encoding="utf-8")
        code, lines = call("validate", "--workflow", workflow.as_posix())
        self.assertEqual(code, cli.EXIT_WORKFLOW)
        self.assertEqual(lines[0], "INVALID misspelt: 1 problem")
        self.assertTrue(any("01.check/01.tests: gate check 'command_exit' takes no "
                            "argument 'cmdd'" in line for line in lines[1:]), lines)


if __name__ == "__main__":
    import unittest
    unittest.main()

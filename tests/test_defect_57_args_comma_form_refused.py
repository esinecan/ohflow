"""Defect NN: `--args repo=X,sweep=0` was read as one `repo` value."""

from support import TempCase
from verb_support import call
from ohflow.cli import EXIT_OK, EXIT_WORKFLOW, parse_args_kv

ONE_STEP = """
from pathlib import Path
from ohflow.workflow import Phase, Workflow, Step

def build(args):
    step = Step(id="a", kind="command", command="echo DONE")
    return Workflow(name="one", repo=Path("."),
                    phases=(Phase(name="p", steps=(step,)),))
"""


class ArgsCommaFormIsRefused(TempCase):

    def test_validate_refuses_the_comma_form_and_names_the_repeated_form(self):
        code, lines = call("validate", "--workflow", str(self.tmp / "absent.py"),
                           "--args", "repo=X,sweep=0")
        self.assertEqual(code, 2)
        self.assertTrue(any("--args repo=X --args sweep=0" in line for line in lines), lines)

    def test_a_comma_in_a_key_is_refused(self):
        workflow = self.tmp / "one.py"
        workflow.write_text(ONE_STEP, encoding="utf-8")
        code, lines = call("validate", "--workflow", workflow.as_posix(),
                           "--args", "a=1")
        self.assertEqual(code, EXIT_OK, lines)
        code, lines = call("validate", "--workflow", workflow.as_posix(),
                           "--args", "a,b=1")
        self.assertEqual(code, EXIT_WORKFLOW, lines)
        self.assertTrue(any("a,b=1" in line for line in lines), lines)

    def test_pair_lists_and_plain_lists_still_parse(self):
        self.assertEqual(
            parse_args_kv(["harness_executors=security=pi,correctness=host",
                           "dimensions=correctness,security", "rounds=4"]),
            {"harness_executors": "security=pi,correctness=host",
             "dimensions": "correctness,security", "rounds": 4})

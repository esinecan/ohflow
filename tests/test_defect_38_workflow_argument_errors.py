"""D-38: a missing workflow argument is named, and any other crash shows its traceback.

Before: `cli.main` mapped every `KeyError` to exit 2 with `not found: 'repo'`.
A workflow that read `args["repo"]` printed the key and nothing else, and a real
`KeyError` bug inside a workflow looked the same as a missing argument.
Now: a workflow's `args` dict names a missing key as
`workflow argument missing: <name> (pass --args <name>=...)` and exits 2. Any other
exception reads `INVALID <workflow>: 1 problem` with `<Type>: <first line>` and
exits 2 (m4 fix 4: a workflow that does not load is a verdict, not a traceback).
"""

from __future__ import annotations

import textwrap

from ohflow import cli
from support import TempCase, quiet

NEEDS_REPO = """
from ohflow.workflow import Workflow

def build(args):
    repo = args["repo"]
    raise SystemExit("unreachable: the repo argument is required")
"""

BUGGY = """
def build(args):
    table = {}
    return table["no such key"]
"""

CRASHES = """
def build(args):
    raise RuntimeError("the workflow fell over")
"""

OPTIONAL = """
def build(args):
    flavour = args.get("flavour", "plain")
    raise RuntimeError("flavour was " + flavour)
"""


class WorkflowArgumentErrors(TempCase):

    def run_validate(self, source: str, *extra: str):
        workflow = self.tmp / "the_workflow.py"
        workflow.write_text(textwrap.dedent(source), encoding="utf-8")
        with quiet() as output:
            code = cli.main(["validate", "--workflow", str(workflow), *extra])
        return code, output.out

    def test_a_missing_workflow_argument_is_named_and_exits_2(self):
        code, out = self.run_validate(NEEDS_REPO)
        self.assertEqual(code, cli.EXIT_WORKFLOW)
        self.assertIn("workflow argument missing: repo (pass --args repo=...)", out)
        self.assertNotIn("Traceback", out)

    def test_a_key_error_inside_the_workflow_is_a_crash_not_a_missing_argument(self):
        code, out = self.run_validate(BUGGY)
        self.assertEqual(code, cli.EXIT_WORKFLOW)
        self.assertNotIn("workflow argument missing", out)
        self.assertTrue(out.startswith("INVALID the_workflow: 1 problem\n"), out)
        self.assertIn("KeyError: 'no such key'", out)

    def test_any_other_exception_reads_invalid_with_its_type_and_exits_2(self):
        code, out = self.run_validate(CRASHES)
        self.assertEqual(code, cli.EXIT_WORKFLOW)
        self.assertTrue(out.startswith("INVALID the_workflow: 1 problem\n"), out)
        self.assertIn("RuntimeError: the workflow fell over", out)
        self.assertNotIn("Traceback", out)

    def test_an_optional_argument_with_a_default_is_not_an_error(self):
        code, out = self.run_validate(OPTIONAL)
        self.assertEqual(code, cli.EXIT_WORKFLOW)
        self.assertIn("flavour was plain", out)
        self.assertNotIn("workflow argument missing", out)

    def test_a_given_argument_is_read(self):
        code, out = self.run_validate(OPTIONAL, "--args", "flavour=spicy")
        self.assertIn("flavour was spicy", out)


if __name__ == "__main__":
    import unittest
    unittest.main()

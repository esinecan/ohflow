from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

import run_tests
from run_tests import OWN_TESTS, SMOKE, Pick, fit_budget, select

SOURCES = {
    "support.py": "from ohflow import cli, workflow\n",
    "test_reads_check.py": "from ohflow.gates import GateContext\n",
    "test_lists_check.py": "from ohflow import (\n    engine,\n    gates as ohgates,\n)\n",
    "test_imports_check.py": "import os, ohflow.gates\n",
    "test_gates_by_name.py": "import os\n",
    "test_through_support.py": "from support import TempCase\n",
    "test_near_names.py": "from ohflow.gates_extra import x\nfrom ohflow import gatesx\n",
    "test_reads_readme.py": 'README = ROOT / "README.md"\n',
    "test_reads_construct.py": 'TEXT = (ROOT / "references" / "construct.md").read_text()\n',
    "test_fixture_readme.py": '(repo / "README.md").write_text("x")\nTREE = {"README.md": "left"}\n',
}


class AChangeSelectsTheTestsItReaches(unittest.TestCase):

    def test_a_module_runs_its_direct_importers_and_the_files_named_after_it(self):
        picks = select(["scripts/ohflow/gates.py"], SOURCES)
        self.assertEqual(sorted(picks), ["test_gates_by_name.py", "test_imports_check.py",
                                         "test_lists_check.py", "test_reads_check.py"])
        self.assertEqual(picks["test_reads_check.py"].reasons, ["imports ohflow.gates"])
        self.assertEqual(picks["test_gates_by_name.py"].reasons, ["name holds gates"])
        self.assertFalse(picks["test_gates_by_name.py"].direct)

    def test_a_changed_test_file_runs_itself_alone(self):
        picks = select(["tests/test_reads_check.py"], SOURCES)
        self.assertEqual(list(picks), ["test_reads_check.py"])
        self.assertTrue(picks["test_reads_check.py"].changed)

    def test_shared_machinery_runs_its_own_tests_and_the_smoke_list(self):
        sources = {name: "" for name in (*OWN_TESTS["support.py"], *SMOKE)}
        picks = select(["tests/support.py"], sources)
        self.assertEqual(set(picks), set(sources))
        self.assertTrue(all(picks[t].direct for t in OWN_TESTS["support.py"]))

    def test_markdown_runs_the_test_files_that_name_it(self):
        picks = select(["README.md", "references/construct.md",
                        "docs/glossary.md"], SOURCES)
        self.assertEqual(sorted(picks), ["test_reads_construct.py",
                                         "test_reads_readme.py"])
        self.assertEqual(picks["test_reads_construct.py"].reasons,
                         ["names references/construct.md"])
        self.assertTrue(picks["test_reads_construct.py"].direct)


class ADocsOnlyChangeRunsCheckDocsAlone(unittest.TestCase):

    def test_main_runs_check_docs_and_no_unittest(self):
        with mock.patch.object(run_tests, "changed_files",
                               return_value=("0" * 40, "main", ["references/" + "-".join(
                                   ["nobody", "names", "this"]) + ".md"])), \
                mock.patch.object(run_tests, "run_check_docs", return_value=0) as docs, \
                mock.patch.object(unittest.TestLoader, "loadTestsFromNames") as load, \
                redirect_stdout(io.StringIO()) as out:
            code = run_tests.main(["--changed", "main"])
        self.assertEqual(code, 0)
        docs.assert_called_once_with()
        load.assert_not_called()
        self.assertIn("no unittest, check_docs.py only", out.getvalue())


class TheBudgetKeepsTheDirectPartCheapestFirst(unittest.TestCase):

    def test_past_the_budget_the_changed_tests_and_the_cheapest_direct_files_run(self):
        picks = {"test_changed.py": Pick(["changed test file"], True, True),
                 "test_slow.py": Pick(["imports ohflow.engine"], True),
                 "test_fast.py": Pick(["imports ohflow.engine"], True),
                 "test_named.py": Pick(["name holds engine"], False)}
        seconds = {"test_changed.py": 250, "test_slow.py": 100, "test_fast.py": 20,
                   "test_named.py": 5}
        fit = fit_budget(picks, seconds, 3, budget_s=300)
        self.assertEqual(fit.keep, ["test_changed.py", "test_fast.py"])
        self.assertEqual(fit.left, ["test_slow.py", "test_named.py"])
        self.assertEqual((fit.total_s, fit.keep_s), (375, 270))

    def test_within_the_budget_every_selected_file_runs(self):
        picks = {"test_a.py": Pick(["x"], True), "test_b.py": Pick(["y"], False)}
        fit = fit_budget(picks, {}, 3, budget_s=300)
        self.assertEqual((fit.keep, fit.left), (["test_a.py", "test_b.py"], []))

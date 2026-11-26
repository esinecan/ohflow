"""The check table of `preflight` in references/ohflow.md names every check preflight.py builds.

The managed run of 24.11.2026 added the `worktree path length` check, its worker's brief kept
the reference out of reach, and no check failed; the reference also lacked `model keys` and
`node_modules source`. Asserted here, on edited copies of the reference text:

- A check with no row fails the check, which names the check.
- A row for a check preflight.py does not build fails it, which names the row.
- A reference with no table after the preflight paragraph fails it.
- `check()` carries the same error, so `tests/check_docs.py` exits 1 when a new check has no row.
"""
import unittest
from pathlib import Path
from unittest import mock

import check_docs
from check_docs import preflight_check_names, preflight_table_errors

REFERENCE = Path(__file__).resolve().parents[1] / "references" / "ohflow.md"


class PreflightCheckTable(unittest.TestCase):

    def setUp(self):
        self.text = REFERENCE.read_text(encoding="utf-8")
        self.row = "| `model keys` |"
        self.assertEqual(self.text.count(self.row), 1)

    def test_the_reference_names_every_check(self):
        self.assertEqual(preflight_table_errors(self.text), [])

    def test_a_check_without_a_row_fails(self):
        self.assertEqual(preflight_table_errors(self.text.replace(self.row, "| model keys |")),
                         ["references/ohflow.md: the preflight check table has no row for `model keys`"])

    def test_a_row_for_an_unknown_check_fails(self):
        extra = self.text.replace(self.row, f"| `disk space` | x |\n{self.row}")
        self.assertEqual(preflight_table_errors(extra),
                         ["references/ohflow.md: the preflight check table names `disk space`, "
                          "which preflight.py does not build"])

    def test_a_reference_without_the_table_fails(self):
        start = self.text.index("`preflight` runs each check as data")
        prose = self.text[:start] + "`preflight` runs each check as data.\n\nNo table.\n"
        self.assertEqual(preflight_table_errors(prose),
                         ['references/ohflow.md: no check table follows "`preflight` runs each check as data"'])

    def test_check_reports_a_new_check_without_a_row(self):
        more = preflight_check_names() + ["disk space"]
        with mock.patch.object(check_docs, "preflight_check_names", lambda: more):
            errors = check_docs.check()[0]
        self.assertEqual(errors, ["references/ohflow.md: the preflight check table has no row for `disk space`"])

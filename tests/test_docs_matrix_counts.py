"""The Matrices table of CONTRIBUTING.md gives each test matrix the number of test cases `MATRICES` holds.

The retire-dsh run changed the matrices, its docs step left the counts in that table
as they were, and no check failed. Asserted here, on edited copies of that text:

- A count that differs from `MATRICES` fails the check, which names the matrix and both numbers.
- A matrix with no row, and a row for a matrix that `MATRICES` does not hold, each fail it.
- `check()` carries the same error, so `tests/check_docs.py` exits 1 on a drifted count.
"""
import unittest
from pathlib import Path
from unittest import mock

import check_docs
from check_docs import MATRICES, matrix_count_errors

CONTRIBUTING = Path(__file__).resolve().parents[1] / "CONTRIBUTING.md"


class ReadmeMatrixCounts(unittest.TestCase):

    def setUp(self):
        self.text = CONTRIBUTING.read_text(encoding="utf-8")
        self.full = len(MATRICES["full"])
        self.row = f"| `full` | {self.full} |"
        self.assertEqual(self.text.count(self.row), 1)

    def test_a_drifted_count_fails_and_names_both_numbers(self):
        drifted = self.text.replace(self.row, f"| `full` | {self.full + 1} |")
        self.assertEqual(matrix_count_errors(drifted),
                         [f"CONTRIBUTING.md: the Matrices table gives `full` {self.full + 1} test cases; "
                          f"MATRICES holds {self.full}"])

    def test_a_matrix_without_a_row_fails(self):
        self.assertEqual(matrix_count_errors(self.text.replace(self.row, "| full | many |")),
                         ["CONTRIBUTING.md: the Matrices table has no row for `full`"])

    def test_a_row_for_an_unknown_matrix_fails(self):
        extra = self.text.replace(self.row, f"{self.row}\n| `nightly` | 4 | none | none |")
        self.assertEqual(matrix_count_errors(extra),
                         ["CONTRIBUTING.md: the Matrices table names `nightly`, which MATRICES does not hold"])

    def test_check_reports_a_matrix_that_lost_a_test_case(self):
        shorter = dict(MATRICES, full=MATRICES["full"][:-1])
        with mock.patch.object(check_docs, "MATRICES", shorter):
            errors = check_docs.check()[0]
        self.assertEqual(errors, [f"CONTRIBUTING.md: the Matrices table gives `full` {self.full} test cases; "
                                  f"MATRICES holds {self.full - 1}"])

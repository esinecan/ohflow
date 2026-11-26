"""The baseline records the exit code and the output tail, and counts only a known format.

Before: `Engine.baseline` always read the output with the vitest parser. A
unittest or pytest baseline came back with every count at zero, which looks
like a real "no tests" answer.
Now: the record holds `exit` and `tail` for every command, and `counts` plus
`format` only when vitest, unittest or pytest printed its summary line.
"""

from __future__ import annotations

import dataclasses
import unittest

from ohflow.engine import Engine
from support import TempCase, git_repo, simple_workflow


class BaselineRecord(TempCase):
    def baseline(self, command: str) -> dict:
        repo = git_repo(self.tmp / "repo")
        workflow = dataclasses.replace(simple_workflow(repo), baseline_cmd=command)
        run_dir = self.run_dir()
        run_dir.mkdir(parents=True, exist_ok=True)
        return Engine(workflow, run_dir, run_id=run_dir.name).baseline()

    def test_unittest_summary_gives_counts_and_format(self):
        record = self.baseline("echo 'Ran 3 tests in 0.001s'; echo OK")
        self.assertEqual(record["exit"], 0)
        self.assertEqual(record["format"], "unittest")
        self.assertEqual(record["counts"]["total"], 3)
        self.assertEqual(record["counts"]["passed"], 3)

    def test_vitest_summary_gives_counts_and_format(self):
        record = self.baseline("echo ' Tests  4 passed (4)'")
        self.assertEqual(record["format"], "vitest")
        self.assertEqual(record["counts"]["passed"], 4)

    def test_pytest_summary_gives_counts_and_format(self):
        record = self.baseline("echo '2 passed, 1 skipped in 0.30s'")
        self.assertEqual(record["format"], "pytest")
        self.assertEqual(record["counts"]["passed"], 2)

    def test_an_unknown_format_has_no_counts_but_keeps_exit_and_tail(self):
        record = self.baseline("echo 'all fine, trust me'; exit 3")
        self.assertEqual(record["exit"], 3)
        self.assertIn("all fine, trust me", record["tail"])
        self.assertNotIn("counts", record)
        self.assertNotIn("format", record)


if __name__ == "__main__":
    unittest.main()

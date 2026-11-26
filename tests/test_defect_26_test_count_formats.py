"""D-26: test_counts understands unittest, node --test, and pytest."""

from ohflow.gates import PARSERS
from support import TempCase


class CommonTestSummariesAreParsed(TempCase):

    def test_unittest_summary(self):
        text = "Ran 7 tests in 0.12s\n\nFAILED (failures=2, skipped=1)\n"
        self.assertEqual(PARSERS["unittest"](text), {
            "passed": 4, "failed": 2, "skipped": 1, "todo": 0, "total": 7})

    def test_node_test_summary(self):
        text = "# tests 8\n# pass 6\n# fail 1\n# skipped 1\n# todo 0\n"
        self.assertEqual(PARSERS["node"](text), {
            "passed": 6, "failed": 1, "skipped": 1, "todo": 0, "total": 8})

    def test_node_spec_reporter_summary(self):
        text = ("\u2139 tests 842\n\u2139 suites 97\n\u2139 pass 842\n"
                "\u2139 fail 0\n\u2139 cancelled 0\n\u2139 skipped 0\n"
                "\u2139 todo 0\n\u2139 duration_ms 12345.6\n")
        self.assertEqual(PARSERS["node"](text), {
            "passed": 842, "failed": 0, "skipped": 0, "todo": 0,
            "total": 842})

    def test_pytest_summary(self):
        text = "====== 5 passed, 2 failed, 1 skipped in 0.42s ======\n"
        self.assertEqual(PARSERS["pytest"](text), {
            "passed": 5, "failed": 2, "skipped": 1, "todo": 0, "total": 8})

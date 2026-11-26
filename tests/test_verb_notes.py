"""m4: `ohflow notes log` and `ohflow notes check`.

Before: the agent opened four files by hand, appended to `notes.md` by hand and
read the other three to see whether any was empty. Now `notes log` appends one
timestamped line and prints it, and `notes check` prints `NOTES COMPLETE` or
`NOTES INCOMPLETE: G gaps` with one line per gap.
"""

from __future__ import annotations

import json

from dashboard_support import RunLog
from ohflow import check_passes
from support import TempCase, git_repo
from verb_support import call

FILLED_RETRO = """# Retro

<!-- ohflow:auto begin -->
2 of 2 steps passed.
<!-- ohflow:auto end -->
"""
FILLED_PREDICTIONS = "# Predictions\n\n1. The run passes: yes, both steps.\n"
FILLED_GROUND_TRUTH = ("# Ground truth\n\n- Test command: python -m unittest\n"
                       "- Result: ok\n")
SECTION_ONE = ("- The gate's recorded pass on this tree, or the CI run on the "
               "pushed head:")


class NotesCheck(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.run = self.run_dir("r-notes")
        RunLog(self.run).run_finished(5, "finished")

    def test_notes_check_names_each_missing_file_as_a_gap(self):
        code, lines = call("notes", "check", "--run", self.run)
        self.assertEqual(code, 1)
        self.assertRegex(lines[0], r"^NOTES INCOMPLETE: 3 gaps$")
        self.assertEqual(len(lines), 4)
        self.assertIn("predictions.md is missing", lines)

    def test_notes_check_reads_complete_when_no_gap_is_left(self):
        (self.run / "predictions.md").write_text(FILLED_PREDICTIONS,
                                                 encoding="utf-8")
        (self.run / "retro.md").write_text(FILLED_RETRO, encoding="utf-8")
        (self.run / "ground-truth.md").write_text(FILLED_GROUND_TRUTH,
                                                  encoding="utf-8")
        code, lines = call("notes", "check", "--run", self.run)
        self.assertEqual(code, 0)
        self.assertEqual(lines, ["NOTES COMPLETE"])

    def test_notes_check_an_empty_prediction_is_one_gap(self):
        (self.run / "predictions.md").write_text(
            "1. The run passes: yes\n2. The steps that will burn the most wall time and tokens:\n",
            encoding="utf-8")
        (self.run / "retro.md").write_text(FILLED_RETRO, encoding="utf-8")
        (self.run / "ground-truth.md").write_text(FILLED_GROUND_TRUTH,
                                                  encoding="utf-8")
        code, lines = call("notes", "check", "--run", self.run)
        self.assertEqual(code, 1)
        self.assertRegex(lines[0], r"^NOTES INCOMPLETE: 1 gap$")
        self.assertIn("predictions.md line 2 is empty", lines[1])

    def test_untouched_predictions_are_no_gap(self):
        (self.run / "predictions.md").write_text(
            "1. The run passes:\n2. The steps that will burn the most wall time and tokens:\n",
            encoding="utf-8")
        (self.run / "retro.md").write_text(FILLED_RETRO, encoding="utf-8")
        (self.run / "ground-truth.md").write_text(FILLED_GROUND_TRUTH,
                                                  encoding="utf-8")
        code, lines = call("notes", "check", "--run", self.run)
        self.assertEqual((code, lines), (0, ["NOTES COMPLETE"]))

    def test_notes_check_of_an_unknown_run_exits_2(self):
        code, lines = call("notes", "check", "--run", self.tmp / "nowhere")
        self.assertEqual(code, 2)
        self.assertLessEqual(len(lines), 2)


class SectionOneTakesTheGatesPass(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.repo = git_repo(self.tmp / "repo")
        self.run = self.run_dir("r-gate")
        RunLog(self.run).run_finished(5, "finished")
        (self.run / "predictions.md").write_text("1. The run passes:\n",
                                                 encoding="utf-8")
        (self.run / "retro.md").write_text(FILLED_RETRO, encoding="utf-8")
        (self.run / "workflow.json").write_text(
            json.dumps({"repo": str(self.repo), "base_branch": "main"}),
            encoding="utf-8")

    def check(self, evidence: str = "") -> tuple[int, list[str]]:
        (self.run / "ground-truth.md").write_text(
            f"# Ground truth\n\n{SECTION_ONE} {evidence}\n", encoding="utf-8")
        return call("notes", "check", "--run", self.run)

    def record(self, tree: str) -> None:
        check_passes.record(self.run, "python -m unittest", "sh", self.repo, tree,
                            by="01.implement/01.implement attempt 1", log=None)

    def test_a_pass_on_the_merged_heads_tree_closes_section_one(self):
        self.record(check_passes.clean_tree(self.repo))
        self.assertEqual(self.check(), (0, ["NOTES COMPLETE"]))

    def test_a_pass_on_another_tree_leaves_the_gap(self):
        self.record("0" * 40)
        code, lines = self.check()
        self.assertEqual(code, 1)
        self.assertIn("ground-truth.md: section 1 names no CI run, and the run "
                      "recorded no gate pass on the merged head's tree", lines)

    def test_a_linked_ci_run_closes_section_one(self):
        self.assertEqual(
            self.check("https://github.com/o/r/actions/runs/1"),
            (0, ["NOTES COMPLETE"]))


class NotesLog(TempCase):

    def test_notes_log_prints_the_line_it_appended(self):
        run = self.run_dir("r-log")
        RunLog(run)
        code, lines = call("notes", "log", "--run", run,
                           "tried   the rerun by hand")
        self.assertEqual(code, 0)
        self.assertRegex(lines[0], r"^\d\d:\d\d \| tried the rerun by hand$")
        self.assertEqual(len(lines), 1)
        notes = (run / "notes.md").read_text(encoding="utf-8")
        self.assertTrue(notes.rstrip("\n").endswith(lines[0]))

    def test_notes_log_twice_appends_twice(self):
        run = self.run_dir("r-log-2")
        RunLog(run)
        call("notes", "log", "--run", run, "first")
        call("notes", "log", "--run", run, "second")
        notes = (run / "notes.md").read_text(encoding="utf-8").splitlines()
        self.assertTrue(notes[-2].endswith("| first"), notes)
        self.assertTrue(notes[-1].endswith("| second"), notes)


if __name__ == "__main__":
    import unittest
    unittest.main()

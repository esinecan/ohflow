"""Run notes: every fresh run starts with the four files a retrospective needs.

Why. The run log records what the engine did. It cannot record what the person
predicted, did by hand, or judged afterwards, and none of that can be rebuilt
from the artefacts once the run is over. A fresh run therefore writes
`predictions.md`, `notes.md`, `retro.md` and `ground-truth.md` at the root of
its run directory, from the templates in `ohflow/run_notes/`.

What is asserted here.

* A fresh run writes all four at the run root, filled in: no `{{name}}` is left,
  the run id and workflow name appear, and `retro.md` has one row per step under
  that step's coordinate. A pipe or a newline in an objective keeps the row
  whole.
* The notes are never overwritten, and a resume leaves the person's edits alone.
* Editing a note re-runs nothing: a resume after an edit starts no step.
* A dry run writes none.
* A missing template directory is reported and the run finishes anyway. A note
  is not a gate.
* The template folder holds exactly the four named notes, so a template cannot
  drift from `NOTE_FILES` unseen.
"""

from __future__ import annotations

import dataclasses
import re
from unittest import mock

from ohflow import runnotes
from ohflow.coords import coord_of
from ohflow.engine import Engine
from support import (FakeHarnessExecutor, TempCase, AgentScript, git_repo,
                     install_fake_harness_executor, read_run_log, simple_workflow,
                     stub_preflight, agent_step)


def prepare(case: TempCase, steps=None):
    """A repo, a fake harness executor and a workflow. Returns (workflow, run_dir)."""
    repo = git_repo(case.tmp / "repo")
    stub_preflight(case)
    install_fake_harness_executor(case, FakeHarnessExecutor(default=AgentScript(final_text="DONE\n")))
    workflow = simple_workflow(repo, steps=steps or [agent_step("alpha"),
                                              agent_step("beta")])
    return workflow, case.run_dir()


def judge_rows(run_dir) -> list[str]:
    """The step rows of `retro.md`'s "What I judge" table. The engine's own
    per-step table above it also has rows that start the same way."""
    text = (run_dir / "retro.md").read_text(encoding="utf-8")
    part = text.split("## What I judge", 1)[1].split("## Seven questions", 1)[0]
    return [ln for ln in part.splitlines() if ln.startswith("| 01.")]


def started(run_dir) -> int:
    return sum(1 for e in read_run_log(run_dir) if e["event"] == "attempt_started")


class AFreshRunWritesFourNotes(TempCase):

    def test_all_four_sit_at_the_run_root_and_hold_text(self):
        workflow, run_dir = prepare(self)
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors).run()
        for name in runnotes.NOTE_FILES:
            note = run_dir / name
            self.assertTrue(note.is_file(), f"{name} is not at the run root")
            self.assertGreater(len(note.read_text(encoding="utf-8").strip()), 40)

    def test_no_placeholder_is_left_in_any_note(self):
        workflow, run_dir = prepare(self)
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors).run()
        for name in runnotes.NOTE_FILES:
            text = (run_dir / name).read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"\{\{\w+\}\}", text),
                              f"{name} still carries a placeholder")

    def test_the_notes_name_the_run_and_the_workflow(self):
        workflow, run_dir = prepare(self)
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors).run()
        for name in ("predictions.md", "retro.md"):
            text = (run_dir / name).read_text(encoding="utf-8")
            self.assertIn(run_dir.name, text)
            self.assertIn("test-workflow", text)

    def test_retro_has_one_row_per_step_under_its_coordinate(self):
        workflow, run_dir = prepare(self)
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors).run()
        rows = judge_rows(run_dir)
        self.assertEqual(len(rows), 2)
        for step_id in ("alpha", "beta"):
            wanted = coord_of(workflow, step_id)
            self.assertEqual(sum(ln.startswith(f"| {wanted} |") for ln in rows), 1,
                             f"no single row for {wanted}")

    def test_a_pipe_or_newline_in_an_objective_keeps_the_row_whole(self):
        step = dataclasses.replace(agent_step("alpha"),
                                   objective="keep|split\nhere")
        workflow, run_dir = prepare(self, steps=[step])
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors).run()
        rows = judge_rows(run_dir)
        self.assertEqual(len(rows), 1)
        self.assertIn("keep/split here", rows[0])
        self.assertEqual(rows[0].count("|"), 7, "the row has the wrong cell count")


class NotesAreNeverOverwritten(TempCase):

    def test_scaffold_keeps_a_file_that_is_already_there(self):
        workflow, run_dir = prepare(self)
        run_dir.mkdir(parents=True)
        (run_dir / "predictions.md").write_text("MINE", encoding="utf-8")
        created, problems = runnotes.scaffold(run_dir, workflow, run_id="r-x",
                                              base_sha="0" * 40)
        self.assertEqual(problems, [])
        self.assertNotIn("predictions.md", created)
        self.assertEqual((run_dir / "predictions.md").read_text(encoding="utf-8"),
                         "MINE")

    def test_a_resume_leaves_the_persons_edits_alone_and_starts_no_step(self):
        workflow, run_dir = prepare(self)
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors).run()
        before = started(run_dir)
        (run_dir / "predictions.md").write_text("MY PREDICTION", encoding="utf-8")
        with (run_dir / "notes.md").open("a", encoding="utf-8") as fh:
            fh.write("15:10 | did | resumed | test\n")

        Engine(workflow, run_dir, run_id=run_dir.name, resume=True,
               verbose=False,
               harness_executors=self.harness_executors).run()

        self.assertEqual((run_dir / "predictions.md").read_text(encoding="utf-8"),
                         "MY PREDICTION")
        self.assertIn("resumed", (run_dir / "notes.md").read_text(encoding="utf-8"))
        self.assertEqual(started(run_dir), before,
                         "editing a note made a resume start a step")


class ANoteNeverStopsARun(TempCase):

    def test_a_dry_run_writes_no_notes(self):
        workflow, run_dir = prepare(self)
        Engine(workflow, run_dir, run_id=run_dir.name, dry_run=True,
               verbose=False,
               harness_executors=self.harness_executors).run()
        for name in runnotes.NOTE_FILES:
            self.assertFalse((run_dir / name).exists(),
                             f"a dry run wrote {name}")

    def test_a_missing_template_directory_is_reported_and_the_run_finishes(self):
        workflow, run_dir = prepare(self)
        with mock.patch.object(runnotes, "TEMPLATE_DIR", self.tmp / "no-such-dir"):
            summary = Engine(workflow, run_dir, run_id=run_dir.name,
                             verbose=False,
                             harness_executors=self.harness_executors).run()
            created, problems = runnotes.scaffold(
                self.tmp / "elsewhere", workflow, run_id="r-x", base_sha="0" * 40)
        self.assertEqual(summary.get("status"), "finished")
        for name in runnotes.NOTE_FILES:
            self.assertFalse((run_dir / name).exists())
        self.assertEqual(created, [])
        self.assertEqual(len(problems), len(runnotes.NOTE_FILES))
        self.assertTrue(problems[0].startswith("predictions.md:"))


class TheTemplatesMatchTheNames(TempCase):

    def test_the_template_folder_holds_exactly_the_four_notes(self):
        held = sorted(p.name for p in runnotes.TEMPLATE_DIR.iterdir())
        self.assertEqual(held, sorted(runnotes.NOTE_FILES))

from __future__ import annotations

import json
import os

from ohflow import cli, rundir
from support import TempCase
from verb_support import call

FIVE = "".join(f"{i}. prediction {i}\n" for i in range(1, 6))
TEMPLATE = "".join(f"{i}. Label {i}:\n" for i in range(1, 6))


class GoTakesPredictions(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.dir = self.run_dir("r-go-predictions")
        self.dir.mkdir(parents=True)
        (self.dir / "workflow.json").write_text("{}", encoding="utf-8")
        (self.dir / rundir.HOLD_FILE).write_text(
            json.dumps({"pid": os.getpid(), "since": "2026-10-26T10:50:01Z"}), encoding="utf-8")
        self.source = self.tmp / "predictions.txt"
        self.source.write_text(FIVE, encoding="utf-8")

    def test_go_writes_the_predictions_over_the_template_then_releases(self):
        (self.dir / "predictions.md").write_text(TEMPLATE, encoding="utf-8")
        code, lines = call("go", "--run", self.dir, "--predictions", self.source)
        self.assertEqual(code, cli.EXIT_OK, lines)
        self.assertTrue(lines[0].startswith("predictions.md written from "), lines)
        self.assertTrue(lines[1].startswith("go sent to "), lines)
        self.assertEqual((self.dir / "predictions.md").read_text(encoding="utf-8"), FIVE)
        self.assertIn("predictions.md written by go",
                      (self.dir / "notes.md").read_text(encoding="utf-8"))
        self.assertTrue((self.dir / rundir.GO_FILE).exists())

    def test_go_refuses_when_predictions_are_already_written(self):
        (self.dir / "predictions.md").write_text(FIVE, encoding="utf-8")
        code, lines = call("go", "--run", self.dir, "--predictions", self.source)
        self.assertEqual(code, cli.EXIT_FAIL)
        self.assertIn("already holds predictions", lines[0])
        self.assertFalse((self.dir / rundir.GO_FILE).exists())

    def test_go_refuses_an_unreadable_predictions_file(self):
        code, lines = call("go", "--run", self.dir, "--predictions", self.tmp / "missing.txt")
        self.assertEqual(code, cli.EXIT_FAIL)
        self.assertIn("cannot read", lines[0])
        self.assertFalse((self.dir / rundir.GO_FILE).exists())


if __name__ == "__main__":
    import unittest
    unittest.main()

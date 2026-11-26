"""Defect 67: printed command hints said `python`, whatever ran ohflow.

A Mac may have only `python3` on PATH, so the resume command that status, the
dashboard and the exit report print did not run when pasted. A hint now names
the running interpreter: `python3` on a Mac, `python` on a Windows install.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

from ohflow import live, paths
from support import TempCase


class AHintNamesTheRunningInterpreter(TempCase):

    def test_python_cmd_is_the_file_name_of_the_interpreter(self):
        name = Path(sys.executable).name
        if name.lower().endswith(".exe"):
            name = name[:-4]
        self.assertEqual(paths.python_cmd(), name)
        with mock.patch.object(sys, "executable", "/opt/venv/bin/python3"):
            self.assertEqual(paths.python_cmd(), "python3")
        with mock.patch.object(sys, "executable", r"C:\Python314\python.exe"):
            self.assertEqual(paths.python_cmd(), "python")
        with mock.patch.object(sys, "executable", ""):
            self.assertEqual(paths.python_cmd(), "python")

    def test_the_resume_command_starts_with_it(self):
        run = self.tmp / "run"
        run.mkdir()
        (run / "run.json").write_text(json.dumps({
            "run_id": "r-1", "workflow_path": "/w/p.py"}), encoding="utf-8")
        with mock.patch.object(sys, "executable", "/opt/venv/bin/python3"):
            command = live.resume_command(run)
        self.assertTrue(command.startswith("python3 -m ohflow.cli run "), command)

    def test_no_printed_hint_hard_codes_python(self):
        root = Path(live.__file__).resolve().parent
        for name in ("campaign.py", "live.py"):
            text = (root / name).read_text(encoding="utf-8")
            self.assertNotIn('"    python -m ohflow.cli', text, name)
            self.assertNotIn('["python", "-m"', text, name)


if __name__ == "__main__":
    import unittest
    unittest.main()

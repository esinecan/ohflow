"""m4: `ohflow run` ends with a verdict, and `run --detach` names the dashboard.

Before: an attached run ended with a raw dict of step results, and a detached
run printed JSON that an agent parsed to find the dashboard. Now an attached
run ends with the exit verdict, the exit-report path and, when the run paused or
a step did not pass, the resume command. A detached run prints
`dashboard: <url>` once the dashboard is up, else `dashboard: pending (see
<run>/dashboard.json)`. `--predictions FILE` seeds `predictions.md`.
"""

from __future__ import annotations

import json
import os
import subprocess
import textwrap

from support import TempCase, git_repo, stub_preflight
from verb_support import call

PASSING = """
from pathlib import Path
from ohflow.workflow import Phase, Workflow, Step

def build(args):
    step = Step(id="a", kind="command", command="echo DONE", execution_timeout_s=30)
    return Workflow(name="verb-run", repo=Path(args["repo"]),
                    phases=(Phase(name="P", steps=(step,)),))
"""

FAILING = PASSING.replace("echo DONE", "exit 3")


class RunVerbCase(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        self.out = self.tmp / "runs"

    def workflow(self, source: str):
        path = self.tmp / "workflow.py"
        path.write_text(textwrap.dedent(source), encoding="utf-8")
        return path

    def run_verb(self, source: str, run_id: str, *extra):
        return call("run", "--workflow", self.workflow(source).as_posix(),
                    "--out", self.out.as_posix(), "--run-id", run_id,
                    "--args", f"repo={self.repo.as_posix()}", *extra)


class RunEndsWithAVerdict(RunVerbCase):

    def test_run_a_passing_run_ends_with_the_verdict_and_no_raw_dict(self):
        code, lines = self.run_verb(PASSING, "r-pass", "--no-dashboard")
        self.assertEqual(code, 0)
        self.assertRegex(lines[-1], r"^Run r-pass finished: 1 of 1 agents passed")
        self.assertTrue(any(line.startswith("exit report: ") for line in lines))
        self.assertFalse(any(line.startswith("resume: ") for line in lines))
        self.assertFalse(any("'results'" in line or line.startswith("{")
                             for line in lines), lines)
        self.assertLessEqual(len(lines), 12)

    def test_run_a_failing_run_ends_with_the_resume_command(self):
        code, lines = self.run_verb(FAILING, "r-fail", "--no-dashboard")
        self.assertEqual(code, 1)
        self.assertRegex(lines[-2],
                         r"^Run r-fail finished: 0 of 1 agents passed, "
                         r"1 quarantined")
        self.assertRegex(lines[-1], r"^resume: .* --resume r-fail ")
        self.assertLessEqual(len(lines), 14)

    def test_run_a_dry_run_says_nothing_ran(self):
        code, lines = self.run_verb(PASSING, "r-dry", "--dry-run",
                                    "--no-dashboard")
        self.assertEqual(code, 0)
        self.assertRegex(lines[-1], r"^dry run finished: nothing ran; run dir ")
        self.assertLessEqual(len(lines), 12)


class RunJsonNeedsDetach(RunVerbCase):
    """`--json` on an attached run was accepted and changed nothing."""

    def test_an_attached_run_refuses_json_in_one_line_and_starts_nothing(self):
        code, lines = self.run_verb(PASSING, "r-json", "--no-dashboard",
                                    "--json")
        self.assertEqual(code, 2)
        self.assertEqual(lines, ["--json works only with --detach: an "
                                 "attached run prints lines."])
        self.assertFalse((self.out / "r-json").exists())


class RunPredictionsSeedTheNotes(RunVerbCase):

    def test_run_predictions_file_becomes_predictions_md(self):
        seed = self.tmp / "my-predictions.md"
        seed.write_text("# Predictions\n\n1. It passes: SEED-MARKER\n",
                        encoding="utf-8")
        code, _lines = self.run_verb(PASSING, "r-seeded", "--no-dashboard",
                                     "--predictions", seed.as_posix())
        self.assertEqual(code, 0)
        written = (self.out / "r-seeded" / "predictions.md").read_text(
            encoding="utf-8")
        self.assertIn("SEED-MARKER", written)

    def test_run_an_unreadable_predictions_file_exits_2_before_any_step(self):
        code, lines = self.run_verb(PASSING, "r-unread", "--no-dashboard",
                                    "--predictions",
                                    (self.tmp / "absent.md").as_posix())
        self.assertEqual(code, 2)
        self.assertLessEqual(len(lines), 2)
        self.assertFalse((self.out / "r-unread").exists())


class RunDetachNamesTheDashboard(RunVerbCase):

    def detach(self, run_id: str, *extra, on_start=None):
        started = {}

        class FakePopen:
            def __init__(inner, argv, **kw):
                started["argv"] = list(argv)
                inner.pid = os.getppid()
                if on_start:
                    on_start()

        original = subprocess.Popen
        subprocess.Popen = FakePopen
        self.addCleanup(setattr, subprocess, "Popen", original)
        code, lines = self.run_verb(PASSING, run_id, "--detach", *extra)
        return code, lines, started

    def test_run_detach_without_a_dashboard_yet_says_pending(self):
        code, lines, _ = self.detach("r-pending")
        self.assertEqual(code, 0)
        self.assertRegex(lines[0], r"^dashboard: pending \(see .*dashboard\.json\)$")
        self.assertTrue(any(line.startswith("supervisor pid: ") for line in lines))
        self.assertLessEqual(len(lines), 4)

    def test_run_detach_with_the_dashboard_up_prints_its_url(self):
        record = self.out / "r-up" / "dashboard.json"

        def serve():
            record.parent.mkdir(parents=True, exist_ok=True)
            record.write_text(json.dumps({
                "url": "http://127.0.0.1:8765/", "port": 8765,
                "pid": os.getppid(), "supervisor": True}), encoding="utf-8")

        code, lines, _ = self.detach("r-up", on_start=serve)
        self.assertEqual(code, 0)
        self.assertEqual(lines[0], "dashboard: http://127.0.0.1:8765/")
        self.assertLessEqual(len(lines), 4)

    def test_run_detach_with_no_dashboard_says_off(self):
        code, lines, started = self.detach("r-off", "--no-dashboard")
        self.assertEqual(code, 0)
        self.assertEqual(lines[0], "dashboard: off")
        self.assertIn("--no-dashboard", started["argv"])

    def test_run_detach_forwards_predictions_by_absolute_path(self):
        seed = self.tmp / "p.md"
        seed.write_text("1. x: y\n", encoding="utf-8")
        _code, _lines, started = self.detach("r-fwd", "--predictions",
                                             seed.as_posix())
        argv = started["argv"]
        self.assertEqual(argv[argv.index("--predictions") + 1], str(seed))


if __name__ == "__main__":
    import unittest
    unittest.main()

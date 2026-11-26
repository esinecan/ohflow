from __future__ import annotations

import json
import os
import textwrap
from unittest import mock

from dashboard_support import boot_page
from ohflow import dashboard, dashboard_data, estimate, pilot, rundir, watch
from ohflow.workflow import load_workflow, to_jsonable, validate
from pilot_support import UNITS, two_paths, write_module
from support import TempCase
from test_pilot_02_projection import attempt, summary_of
from verb_support import call

NO_UNITS_MODULE = '''
from pathlib import Path
from ohflow.workflow import AgentSpec, ModelConfig, Phase, Step, Workflow

MODEL = ModelConfig(model="fake/deterministic", base_url="http://127.0.0.1:0/x",
                    api_key_env="OHFLOW_TEST_FAKE_KEY")


def build(args):
    step = Step(id="a", kind="agent", objective="do a",
                agent=AgentSpec(harness_executor="pi", role="a", brief="do a", model=MODEL))
    return Workflow(name="no-units", repo=Path(args["repo"]),
                    phases=(Phase(name="Only", steps=(step,)),))
'''


class VerbsAndPage(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.module = write_module(self.tmp / "wf.py")
        self.full = validate(load_workflow(self.module, {"repo": str(self.repo)}))
        self.small = pilot.pilot_workflow(self.full)
        patch = mock.patch.dict(os.environ)
        patch.start()
        self.addCleanup(patch.stop)
        os.environ.pop(estimate.HISTORY_ENV, None)

    def held_run(self, state: str = "finished"):
        run_dir = self.run_dir("r-held-pilot")
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "workflow.json").write_text(
            json.dumps(to_jsonable(self.full)), encoding="utf-8")
        (run_dir / rundir.HOLD_FILE).write_text(
            json.dumps({"pid": os.getpid(), "since": "2026-11-07T10:00:00Z"}),
            encoding="utf-8")
        pilot_dir = run_dir / pilot.PILOT_DIR
        if state == pilot.RUNNING:
            record = pilot.started_record(self.full, self.small, pilot_dir)
        else:
            record = pilot.finished_record(self.full, self.small, pilot_dir, state,
                                           summary_of({
                "fix-s2": ("passed", [attempt(60, 900, 100)]),
                "fix-p2": ("passed", [attempt(300, 4000, 1000)]),
                "report": ("passed", [attempt(30, 400, 100)])}))
        pilot.write_pilot(run_dir, record)
        return run_dir

    def test_run_pilot_refuses_a_dry_run_a_resume_and_a_workflow_without_units(self):
        base = ["run", "--workflow", self.module, "--args", f"repo={self.repo}",
                "--out", self.tmp / "runs", "--pilot"]
        code, lines = call(*base, "--dry-run")
        self.assertEqual(code, 2, lines)
        self.assertIn("--pilot with --dry-run is refused", lines[0])
        code, lines = call(*base, "--resume", "r-x")
        self.assertEqual(code, 2, lines)
        self.assertIn("--pilot with --resume is refused", lines[0])
        bare = self.tmp / "bare.py"
        bare.write_text(textwrap.dedent(NO_UNITS_MODULE), encoding="utf-8")
        code, lines = call("run", "--workflow", bare, "--args", f"repo={self.repo}",
                           "--out", self.tmp / "runs", "--pilot")
        self.assertEqual(code, 2, lines)
        self.assertEqual(lines[0], pilot.NO_UNITS)

    def test_estimate_projects_the_module_as_it_reads_now(self):
        run_dir = self.held_run()
        write_module(self.module, [u for u in UNITS if u[0] not in ("s1", "s3")])
        code, lines = call("estimate", "--workflow", self.module, "--args",
                           f"repo={self.repo}", "--pilot", run_dir)
        self.assertEqual(code, 0, lines)
        self.assertEqual(lines[0], estimate.NO_HISTORY)
        head = next(line for line in lines if line.startswith("PILOT two-paths:"))
        self.assertIn("for 3 units on 2 paths", head)
        self.assertIn("| single | 1 | s2 | passed |", "\n".join(lines))

    def test_estimate_refuses_a_directory_with_no_pilot(self):
        code, lines = call("estimate", "--workflow", self.module, "--args",
                           f"repo={self.repo}", "--pilot", self.tmp)
        self.assertEqual(code, 1, lines)
        self.assertIn("--pilot: no pilot.json", lines[0])

    def test_status_shows_the_projection_while_held(self):
        run_dir = self.held_run()
        code, lines = call("status", "--run", run_dir)
        self.assertEqual(code, 0, lines)
        self.assertRegex(lines[0], r"^held: ")
        self.assertTrue(lines[1].startswith("pilot: projected "), lines)
        self.assertTrue(any(line.startswith("pilot single: 3 units x 1 min, 1.0 k "
                                            "tokens, unpriced = 3 min, 3.0 k tokens")
                            for line in lines), lines)
        self.assertTrue(any(line.startswith("pilot shared steps: 1 step,")
                            for line in lines), lines)

    def test_watch_says_the_pilot_runs_first_then_names_go(self):
        run_dir = self.held_run(pilot.RUNNING)
        code, lines = call("watch", "--run", run_dir, "--timeout", 0)
        self.assertEqual(code, watch.EXIT_GOING, lines)
        self.assertIn("pilot: running the smallest unit of each path (s2, p2)",
                      "\n".join(lines))
        self.assertTrue(lines[-1].startswith("held: the pilot runs first · "
                                             "ohflow watch --run"), lines)
        finished = pilot.finished_record(self.full, self.small,
                                         run_dir / pilot.PILOT_DIR, "finished",
                                         summary_of({}))
        pilot.write_pilot(run_dir, {**finished, "generated": "later"})
        code, lines = call("watch", "--run", run_dir, "--timeout", 0)
        self.assertEqual(code, watch.EXIT_GOING, lines)
        self.assertIn("-m ohflow.cli go --run", lines[-1])

    def test_the_page_data_carries_the_pilot(self):
        run_dir = self.held_run()
        payload = dashboard_data.workflow_data(run_dir)
        view = payload["run"]["pilot"]
        self.assertEqual(view["state"], "finished")
        self.assertEqual([p["units"] for p in view["projection"]["paths"]], [3, 2])
        self.assertTrue(view["head"].startswith("projected "))

    def test_the_page_renders_a_pilot_panel(self):
        payload = dashboard_data.workflow_data(self.held_run())
        view = payload["run"]["pilot"]
        seen = boot_page(payload, ids=("digest-panel",), classes=("digest-pilot",))
        if seen is None:
            self.skipTest("node is not installed")
        self.assertEqual(seen["errors"], [])
        panels = seen["classes"]["digest-pilot"]
        self.assertEqual(len(panels), 1, "the digest shows no pilot panel")
        panel = panels[0]
        self.assertFalse(panel["hidden"])
        self.assertIn("digest-pilot", seen["ids"]["digest-panel"]["children"][0],
                      "a held run's digest does not open on the pilot")
        self.assertIn(view["head"], panel["text"])
        self.assertIn(view["run_dir"], panel["text"])
        shown = {row[0]: row[1:4] for row in panel["rows"][1:]}
        for path in view["projection"]["paths"]:
            self.assertEqual(shown[path["name"]],
                             [str(path["units"]), path["pilot_unit"], path["status"]])
        css = (dashboard.ASSET_ROOT / "dashboard.css").read_text(encoding="utf-8")
        self.assertIn(".pilot-table", css)


if __name__ == "__main__":
    import unittest
    unittest.main()

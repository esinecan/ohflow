from __future__ import annotations

import json
import os

from ohflow import pilot, rundir, supervisor
from ohflow.supervisor import RunOptions, run_workflow
from ohflow.workflow import load_workflow, validate
from pilot_support import (UNITS, WAIT_S, start_in_thread, two_paths, wait_until,
                           write_module)
from support import (AgentScript, FakeHarnessExecutor, TempCase, git_repo,
                     install_fake_harness_executor, quiet, simple_workflow,
                     stub_preflight, agent_step)
from verb_support import call


def pilot_state(run_dir):
    record = pilot.read_pilot(run_dir)
    return record.get("state") if record else None


class PilotThenHold(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript(
            tokens={"prompt_tokens": 10, "completion_tokens": 5})))
        original = supervisor.HOLD_POLL_S
        supervisor.HOLD_POLL_S = 0.02
        self.addCleanup(setattr, supervisor, "HOLD_POLL_S", original)
        self.said: list[str] = []

    def options(self, **extra) -> RunOptions:
        extra.setdefault("dashboard", False)
        extra.setdefault("harness_executors", self.harness_executors)
        extra.setdefault("say", self.said.append)
        return RunOptions(**extra)

    def held(self, run_dir) -> bool:
        return any(line.startswith("held: waiting for go") for line in self.said)

    def test_the_pilot_runs_one_unit_per_path_then_the_run_holds(self):
        run_dir = self.tmp / "runs" / "r-pilot"
        thread, result = start_in_thread(lambda: run_workflow(
            two_paths(self.repo), run_dir, self.options(pilot=True)))
        self.assertTrue(wait_until(lambda: self.held(run_dir)), self.said)
        self.assertNotIn("error", result, result.get("error"))

        pilot_dir = run_dir / pilot.PILOT_DIR
        pilot_run = rundir.open_run(pilot_dir)
        self.assertEqual({v.step_id: v.status for v in pilot_run.steps()},
                         {"fix-s2": "passed", "fix-p2": "passed", "report": "passed"})
        self.assertFalse((run_dir / "run-log.jsonl").exists(),
                         "the full run writes no run log line while held")
        self.assertTrue((run_dir / rundir.HOLD_FILE).exists())

        record = pilot.read_pilot(run_dir)
        self.assertEqual(record["state"], "finished")
        self.assertEqual(record["units"], ["s2", "p2"])
        single, probe = record["projection"]["paths"]
        self.assertEqual((single["units"], probe["units"]), (3, 2))
        self.assertEqual(single["unit"]["tokens"], 15)
        self.assertEqual(single["projected"]["tokens"], 45)
        self.assertEqual(probe["projected"]["tokens"], 30)
        self.assertEqual(record["projection"]["total"]["tokens"], 45 + 30 + 15)
        self.assertTrue(any(line.startswith("PILOT two-paths: projected")
                            for line in self.said), self.said)

        (run_dir / rundir.GO_FILE).write_text("go\n", encoding="utf-8")
        thread.join(WAIT_S)
        self.assertFalse(thread.is_alive(), "the run did not release on go")
        self.assertNotIn("error", result, result.get("error"))
        outcome = result["outcome"]
        self.assertEqual(outcome.status, "finished")
        statuses = {v.step_id: v.status for v in outcome.run.steps()}
        self.assertEqual(statuses, {f"fix-{u}": "passed" for u, _p, _s in UNITS}
                         | {"report": "passed"},
                         "the full run runs every unit, the pilot's included")

    def test_go_reloads_the_module_and_the_projection_follows_it(self):
        module = write_module(self.tmp / "wf.py")
        args = {"repo": str(self.repo)}
        workflow = validate(load_workflow(module, args))
        run_dir = self.tmp / "runs" / "r-reload"
        thread, result = start_in_thread(lambda: run_workflow(
            workflow, run_dir, self.options(pilot=True, workflow_path=str(module),
                                            workflow_args=args)))
        self.assertTrue(wait_until(lambda: self.held(run_dir)), self.said)
        write_module(module, [u for u in UNITS if u[0] != "s3"])
        (run_dir / rundir.GO_FILE).write_text("go\n", encoding="utf-8")
        thread.join(WAIT_S)
        self.assertNotIn("error", result, result.get("error"))
        record = pilot.read_pilot(run_dir)
        self.assertEqual([p["units"] for p in record["projection"]["paths"]], [2, 2])
        self.assertNotIn("fix-s3", {v.step_id for v in result["outcome"].run.steps()})

    def test_a_workflow_without_units_cannot_pilot(self):
        workflow = simple_workflow(self.repo, steps=[agent_step("a")])
        with quiet():
            outcome = run_workflow(workflow, self.tmp / "runs" / "r-none",
                                   self.options(pilot=True))
        self.assertEqual(outcome.status, "refused")
        self.assertEqual(outcome.problem, pilot.NO_UNITS)

    def test_a_dry_run_ignores_the_pilot(self):
        run_dir = self.tmp / "runs" / "r-dry"
        with quiet():
            outcome = run_workflow(two_paths(self.repo), run_dir,
                                   self.options(pilot=True, dry_run=True))
        self.assertEqual(outcome.status, "finished")
        self.assertFalse((run_dir / pilot.PILOT_DIR).exists())

    def test_go_is_refused_while_the_pilot_runs(self):
        run_dir = self.tmp / "runs" / "r-busy"
        run_dir.mkdir(parents=True)
        (run_dir / rundir.HOLD_FILE).write_text(
            json.dumps({"pid": os.getpid(), "since": "2026-11-07T10:00:00Z"}),
            encoding="utf-8")
        full = two_paths(self.repo)
        pilot.write_pilot(run_dir, pilot.started_record(
            full, pilot.pilot_workflow(full), run_dir / pilot.PILOT_DIR))
        code, lines = call("go", "--run", run_dir)
        self.assertEqual(code, 1, lines)
        self.assertIn("the pilot is still running", lines[0])
        self.assertFalse((run_dir / rundir.GO_FILE).exists())


if __name__ == "__main__":
    import unittest
    unittest.main()

"""The pre-run hold gate: `run_workflow(hold=True)` waits for `go`.

Before: a run started its agents the moment the directory was claimed, so an
operator who wanted to read the plan on the dashboard first had to read the
workflow module instead. Now a held run writes `workflow.json` and
`.ohflow-hold`, serves its dashboard, passes preflight and then waits for
`<run-dir>/go`. Nothing in the run log exists until the go arrives.

Asserted here, with a fake harness executor and no dashboard:

- a held run leaves `.ohflow-hold` and `workflow.json` and no run log, says
  how to release it, and finishes once `go` is written;
- a resume cannot hold: the run already started;
- a dry run ignores the hold, because a rehearsal launches nothing;
- a preflight fault ends a held run as `crashed`, with the exit report.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from ohflow import rundir, supervisor
from ohflow.engine import Engine
from ohflow.supervisor import RunOptions, run_workflow
from support import (FakeHarnessExecutor, TempCase, AgentScript, git_repo,
                     install_fake_harness_executor, quiet, simple_workflow,
                     stub_preflight, agent_step)

HOLD_WAIT_S = 15.0


def wait_for(path: Path, timeout: float = HOLD_WAIT_S) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return True
        time.sleep(0.02)
    return path.exists()


class HeldRun(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript()))
        original = supervisor.HOLD_POLL_S
        supervisor.HOLD_POLL_S = 0.02
        self.addCleanup(setattr, supervisor, "HOLD_POLL_S", original)
        self.said: list[str] = []

    def options(self, **extra) -> RunOptions:
        extra.setdefault("dashboard", False)
        extra.setdefault("harness_executors", self.harness_executors)
        extra.setdefault("say", self.said.append)
        return RunOptions(**extra)

    def start_held(self, workflow, run_dir: Path, **extra):
        """Run the workflow in a thread; return the thread and the result slot."""
        result: dict = {}

        def target():
            with quiet():
                try:
                    result["outcome"] = run_workflow(
                        workflow, run_dir, self.options(hold=True, **extra))
                except BaseException as e:      # noqa: BLE001 - reported by the test
                    result["error"] = e

        thread = threading.Thread(target=target, name="held-run", daemon=True)
        thread.start()
        return thread, result

    def test_the_run_holds_then_finishes_on_go(self):
        workflow = simple_workflow(self.repo, steps=[agent_step("a")])
        run_dir = self.tmp / "runs" / "r-held"
        thread, result = self.start_held(workflow, run_dir)
        self.assertTrue(wait_for(run_dir / rundir.HOLD_FILE),
                        "the hold file never appeared")
        self.assertTrue((run_dir / "workflow.json").exists(),
                        "a held run writes workflow.json before it waits")
        self.assertFalse((run_dir / "run-log.jsonl").exists(),
                         "a held run writes no run log line")
        record = json.loads((run_dir / rundir.HOLD_FILE).read_text(encoding="utf-8"))
        self.assertEqual(record["pid"], os.getpid())
        self.assertIn("since", record)
        self.assertEqual(rundir.open_run(run_dir).status_without_run_log,
                         rundir.HELD)
        held_lines = [line for line in self.said if line.startswith("held: waiting for go")]
        self.assertEqual(len(held_lines), 1, self.said)
        self.assertIn("-m ohflow.cli go --run", held_lines[0])

        (run_dir / rundir.GO_FILE).write_text("2026-10-09T12:00:00Z", encoding="utf-8")
        thread.join(HOLD_WAIT_S)
        self.assertFalse(thread.is_alive(), "the run did not release on go")
        self.assertNotIn("error", result, result.get("error"))
        outcome = result["outcome"]
        self.assertEqual(outcome.status, "finished")
        self.assertFalse((run_dir / rundir.HOLD_FILE).exists(),
                         "go removes the hold file")
        self.assertTrue((run_dir / rundir.GO_FILE).exists(),
                        "the go file stays as evidence")
        self.assertTrue((run_dir / "exit.json").exists())
        self.assertEqual({v.coord: v.status for v in outcome.run.steps()},
                         {"01.only-phase/01.a": "passed"})

    def test_a_resume_cannot_hold(self):
        workflow = simple_workflow(self.repo, steps=[agent_step("a")])
        run_dir = self.tmp / "runs" / "r-done"
        with quiet():
            first = run_workflow(workflow, run_dir, self.options())
        self.assertEqual(first.status, "finished")
        with quiet():
            outcome = run_workflow(workflow, run_dir,
                                   self.options(hold=True, resume="yes"))
        self.assertEqual(outcome.status, "refused")
        self.assertEqual(outcome.problem,
                         "a resume cannot hold: the run already started")
        self.assertFalse((run_dir / rundir.HOLD_FILE).exists())

    def test_a_dry_run_ignores_the_hold(self):
        workflow = simple_workflow(self.repo, steps=[agent_step("a")])
        run_dir = self.tmp / "runs" / "r-dry"
        with quiet():
            outcome = run_workflow(workflow, run_dir,
                                   self.options(hold=True, dry_run=True))
        self.assertEqual(outcome.status, "finished")
        self.assertFalse((run_dir / rundir.HOLD_FILE).exists(),
                         "a rehearsal launches nothing, so it holds nothing")

    def test_a_preflight_fault_ends_a_held_run_as_crashed(self):
        Engine.preflight = lambda self: ["the repository is missing"]
        workflow = simple_workflow(self.repo, steps=[agent_step("a")])
        run_dir = self.tmp / "runs" / "r-preflight"
        with quiet():
            outcome = run_workflow(workflow, run_dir, self.options(hold=True))
        self.assertEqual(outcome.status, "crashed")
        self.assertIn("preflight failed", outcome.problem)
        self.assertIn("the repository is missing", outcome.problem)
        record = json.loads((run_dir / "exit.json").read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "crashed")
        self.assertFalse((run_dir / rundir.HOLD_FILE).exists(),
                         "a run that stopped holds nothing")
        self.assertFalse((run_dir / "run-log.jsonl").exists())


if __name__ == "__main__":
    import unittest
    unittest.main()

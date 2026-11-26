"""A held run writes `estimate.json` before it waits, and again after `go`.

The estimate used to be written after the reload that follows `go`, so the
held page had no forecast while the person read the plan. Now the supervisor
estimates once after preflight, before `held: waiting for go` is printed, and
once more after the reload, so the file describes the workflow that runs.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from ohflow import estimate, rundir, supervisor
from ohflow.supervisor import RunOptions, run_workflow
from support import (AgentScript, FakeHarnessExecutor, TempCase, agent_step,
                     git_repo, install_fake_harness_executor, quiet,
                     simple_workflow, stub_preflight)
from test_estimate_01_prior_from_history import attempt, summary

HOLD_WAIT_S = 15.0


def wait_for(path: Path, timeout: float = HOLD_WAIT_S) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return True
        time.sleep(0.02)
    return path.exists()


class EstimateAtHold(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript()))
        original = supervisor.HOLD_POLL_S
        supervisor.HOLD_POLL_S = 0.02
        self.addCleanup(setattr, supervisor, "HOLD_POLL_S", original)
        self.history = self.tmp / "history"
        for n, wall in enumerate((60, 120, 180)):
            summary(self.history / f"r{n}", f"r{n}", [
                {"role": "role-a", "executor": "host", "model": "fake/deterministic",
                 "attempts": [attempt(wall, 500, 0.0, "unpriced")]}])
        self.run = self.tmp / "runs" / "r-held"
        self.said: list[str] = []
        self.stamp_at_hold: int | None = None

    def say(self, line: str) -> None:
        self.said.append(line)
        if line.startswith("held: waiting for go"):
            path = self.run / estimate.ESTIMATE_FILE
            self.stamp_at_hold = path.stat().st_mtime_ns if path.exists() else None

    def test_the_file_exists_at_the_hold_line_and_is_rewritten_after_go(self):
        workflow = simple_workflow(self.repo, steps=[agent_step("a")])
        result: dict = {}

        def target():
            with quiet():
                try:
                    result["outcome"] = run_workflow(workflow, self.run, RunOptions(
                        hold=True, dashboard=False, history=(str(self.history),),
                        harness_executors=self.harness_executors, say=self.say))
                except BaseException as e:
                    result["error"] = e

        thread = threading.Thread(target=target, name="held-run", daemon=True)
        thread.start()
        self.assertTrue(wait_for(self.run / rundir.HOLD_FILE))
        deadline = time.monotonic() + HOLD_WAIT_S
        while self.stamp_at_hold is None and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertIsNotNone(self.stamp_at_hold,
                             "estimate.json was not there when the hold line was said")
        (self.run / rundir.GO_FILE).write_text("go", encoding="utf-8")
        thread.join(HOLD_WAIT_S)
        self.assertFalse(thread.is_alive(), "the run did not release on go")
        self.assertNotIn("error", result, result.get("error"))
        self.assertEqual(result["outcome"].status, "finished")
        after = (self.run / estimate.ESTIMATE_FILE).stat().st_mtime_ns
        self.assertNotEqual(after, self.stamp_at_hold,
                            "the estimate was not rewritten after go")
        blocks = [i for i, line in enumerate(self.said)
                  if line.startswith("ESTIMATE ")]
        self.assertEqual(len(blocks), 2, self.said)
        held = next(i for i, line in enumerate(self.said)
                    if line.startswith("held: waiting for go"))
        self.assertLess(blocks[0], held)
        self.assertGreater(blocks[1], held)


if __name__ == "__main__":
    import unittest
    unittest.main()

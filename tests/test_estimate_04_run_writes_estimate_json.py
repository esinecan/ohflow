"""`run --history DIR` writes `estimate.json`, and `/api/workflow` carries it.

The supervisor computes the estimate once the engine that will run is known,
so an edit made while a run was held is what gets estimated. The dashboard's
graph route then carries the run, phase and step estimates, and an ETA: from
the prior until the first agent step finishes, from the run's own finished
steps after that. The basis text says which.
"""

from __future__ import annotations

import json

from dashboard_support import RunLog, agent, mark_alive, workflow_json
from ohflow import dashboard_data, estimate
from ohflow.supervisor import RunOptions, run_workflow
from support import (AgentScript, FakeHarnessExecutor, TempCase, agent_step,
                     git_repo, install_fake_harness_executor, quiet,
                     simple_workflow, stub_preflight)
from test_estimate_01_prior_from_history import attempt, summary

A, B = "01.build/01.a", "01.build/02.b"


class RunWritesTheEstimate(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript()))
        self.history = self.tmp / "history"
        for n, wall in enumerate((60, 120, 180)):
            summary(self.history / f"r{n}", f"r{n}", [
                {"role": "role-a", "executor": "pi", "model": "fake/deterministic",
                 "attempts": [attempt(wall, 500, 0.0, "unpriced")]}])
        self.said: list[str] = []

    def run_it(self, **options):
        options.setdefault("dashboard", False)
        options.setdefault("harness_executors", self.harness_executors)
        options.setdefault("say", self.said.append)
        workflow = simple_workflow(self.repo, steps=[agent_step("a")])
        with quiet():
            return run_workflow(workflow, self.tmp / "runs" / "r-one",
                                RunOptions(**options))

    def test_estimate_json_is_written_before_the_run_and_the_page_carries_it(self):
        outcome = self.run_it(history=(str(self.history),))
        self.assertEqual(outcome.status, "finished")
        path = outcome.run_dir / estimate.ESTIMATE_FILE
        self.assertTrue(path.exists())
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], estimate.SCHEMA)
        self.assertEqual(data["run"]["wall_s"]["p50"], 120)
        self.assertTrue(any(line.startswith("ESTIMATE test-workflow:")
                            for line in self.said), self.said)
        payload = dashboard_data.workflow_data(outcome.run_dir)
        run = payload["run"]
        self.assertEqual(run["estimate"]["wall_s"]["p50"], 120)
        self.assertIn("eta_s", run)
        self.assertIsNone(run["eta_s"])          # the run is over
        self.assertIn("actual", run)
        self.assertIsNotNone(run["actual"]["wall_s"])
        self.assertEqual(payload["phases"][0]["estimate"]["wall_s"]["p50"], 120)
        self.assertEqual(payload["phases"][0]["estimate"]["n"], 3)
        step = payload["steps"][0]
        self.assertEqual(step["estimate"]["wall_s"]["p50"], 120)
        self.assertEqual(step["estimate"]["confidence"], "low")   # unpriced

    def test_without_history_the_run_says_so_once_and_writes_no_file(self):
        outcome = self.run_it()
        self.assertFalse((outcome.run_dir / estimate.ESTIMATE_FILE).exists())
        self.assertEqual(self.said.count(estimate.NO_HISTORY), 1)
        payload = dashboard_data.workflow_data(outcome.run_dir)
        self.assertIsNone(payload["run"]["estimate"])
        self.assertIsNone(payload["phases"][0]["estimate"])


def live_run(run_dir, *, finish_a: bool):
    """Two agents under one slot. `a` runs; with `finish_a`, it has finished
    and `b` runs instead."""
    workflow_json(run_dir, [("Build", [agent("a"), agent("b")], 1)])
    log = RunLog(run_dir)
    log.phase(1, "01.build", "Build", [A, B], 1)
    log.start(2, A, 1)
    if finish_a:
        log.finish(42, A, 1, "passed", wall=40.0)
        log.start(43, B, 1)
    mark_alive(run_dir)
    (run_dir / estimate.ESTIMATE_FILE).write_text(json.dumps({
        "schema": estimate.SCHEMA, "generated": "2026-09-30T11:59:00Z",
        "workflow": "synthetic",
        "history": {"sources": 3, "samples": 3, "retry_multiplier": 1.0,
                    "paths": []},
        "run": {"wall_s": {"p50": 200, "p80": 260}, "tokens": {"p50": 1000, "p80": 1200},
                "cost_usd": None, "confidence": "low", "basis": "fixture"},
        "phases": [{"coord": "01.build", "name": "Build", "max_parallel": 1,
                    "agents": 2, "wall_s": {"p50": 200, "p80": 260},
                    "tokens": {"p50": 1000, "p80": 1200}, "cost_usd": None,
                    "n": 3, "basis": "fixture", "confidence": "low"}],
        "steps": [{"coord": c, "kind": "agent", "key": ["role a", "pi", "m"],
                   "basis": "fixture", "n": 3, "fallback": False,
                   "confidence": "low", "wall_s": {"p50": 100, "p80": 130},
                   "tokens": {"p50": 500, "p80": 600}, "cost_usd": None}
                  for c in (A, B)],
    }), encoding="utf-8")
    return run_dir


class TheLiveEta(TempCase):

    def test_before_any_finish_the_eta_comes_from_the_prior(self):
        from dashboard_support import T0
        run_dir = live_run(self.tmp / "live", finish_a=False)
        payload = dashboard_data.workflow_data(run_dir, now=T0 + 12)
        run = payload["run"]
        # `a` has 90 s of its 100 s left; `b` waits one wave of 100 s.
        self.assertEqual(run["eta_s"], 190)
        self.assertIn("estimate", run["eta_basis"])
        self.assertEqual(run["estimate"]["wall_s"]["p50"], 200)

    def test_after_one_finish_the_run_s_own_median_takes_over(self):
        from dashboard_support import T0
        run_dir = live_run(self.tmp / "live", finish_a=True)
        payload = dashboard_data.workflow_data(run_dir, now=T0 + 53)
        run = payload["run"]
        # `b` started at 43 s and has 30 s of a 40 s median left.
        self.assertEqual(run["eta_s"], 30)
        self.assertIn("median 40 s over 1 finished agent step", run["eta_basis"])

    def test_the_read_out_route_blends_the_same_way(self):
        from dashboard_support import T0
        from ohflow import live
        run_dir = live_run(self.tmp / "live", finish_a=False)
        read_out = live.read_out(run_dir, now=T0 + 12)
        self.assertEqual(read_out["run"]["eta_s"], 190)
        self.assertIn("estimate", read_out["run"]["eta_basis"])

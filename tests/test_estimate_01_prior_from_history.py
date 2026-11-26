"""`estimate.Prior.from_history`: one sample per attempt, keyed for fallback.

A prior is the history of finished runs read as numbers: for every agent
attempt in every `summary.json`, its wall seconds, its tokens and its cost,
under the key `(role, harness executor, model)`. A workflow step whose exact
key has no history falls back to `(executor, model)`, then `(executor,)`, then
the whole corpus. The retry multiplier is attempts divided by steps.

These tests build their own summaries. Each attempt directory carries the
`spec.json` the engine writes, because that file is where the harness
executor and the model of a finished attempt are recorded.
"""

from __future__ import annotations

import json
from pathlib import Path

from ohflow import estimate
from support import TempCase


def summary(run_dir: Path, run_id: str, steps: list[dict]) -> Path:
    """Write an ohflow-shaped `summary.json` under `run_dir`.

    `steps` is a list of `{"role", "executor", "model", "attempts": [...]}`,
    each attempt `{"wall", "tokens", "cost", "cost_source", "status"}`.
    """
    phases: dict = {}
    for i, step in enumerate(steps, start=1):
        coord = f"01.only/{i:02d}.s{i}"
        attempts = []
        for n, att in enumerate(step["attempts"], start=1):
            adir = run_dir / "phases" / "01.only" / f"{i:02d}.s{i}" / "attempts" / f"{n:02d}"
            adir.mkdir(parents=True, exist_ok=True)
            (adir / "spec.json").write_text(json.dumps({
                "harness_executor": step["executor"],
                "model": {"model": step["model"]}}), encoding="utf-8")
            attempts.append({
                "attempt": n, "kind": "agent", "status": att.get("status", "passed"),
                "start_kind": "initial" if n == 1 else "retry",
                "wall_seconds": att["wall"],
                "tokens": {"prompt_tokens": att["tokens"], "completion_tokens": 0},
                "cost": att.get("cost"), "cost_source": att.get("cost_source"),
                "dir": str(adir),
            })
        phases.setdefault("01.only", {"name": "Only", "steps": {}})
        phases["01.only"]["steps"][coord] = {
            "step_id": f"s{i}", "kind": step.get("kind", "agent"),
            "role": step["role"], "status": "passed",
            "attempts": attempts, "executions": len(attempts),
        }
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "summary.json"
    path.write_text(json.dumps({
        "run_id": run_id, "workflow": "w", "status": "finished",
        "started": "2026-10-01T10:00:00Z", "finished": "2026-10-01T10:30:00Z",
        "phases": phases}), encoding="utf-8")
    return path


def attempt(wall: float, tokens: int = 1000, cost=None, source=None,
            status: str = "passed") -> dict:
    return {"wall": wall, "tokens": tokens, "cost": cost, "cost_source": source,
            "status": status}


class SamplesAndKeys(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.history = self.tmp / "history"
        summary(self.history / "runs" / "r1", "r1", [
            {"role": "implementer", "executor": "codex", "model": "gpt-5.6-sol",
             "attempts": [attempt(100, 1000, 0.0, "subscription")]},
            {"role": "reviewer", "executor": "pi", "model": "zai/glm-5.3-flash",
             "attempts": [attempt(300, 5000, 0.25, "pi-catalog")]},
        ])
        summary(self.history / "runs" / "r2", "r2", [
            {"role": "implementer", "executor": "codex", "model": "gpt-5.6-sol",
             "attempts": [attempt(200, 2000, 0.0, "subscription"),
                          attempt(400, 4000, 0.0, "subscription")]},
        ])
        self.prior = estimate.Prior.from_history([self.history])

    def test_one_sample_per_attempt(self):
        self.assertEqual(self.prior.sample_count, 4)
        self.assertEqual(self.prior.source_count, 2)

    def test_the_exact_key_carries_n_p50_and_p80(self):
        hit = self.prior.lookup("implementer", "codex", "gpt-5.6-sol")
        self.assertEqual(hit.key, ("implementer", "codex", "gpt-5.6-sol"))
        self.assertFalse(hit.fallback)
        self.assertEqual(hit.wall.n, 3)
        self.assertEqual(hit.wall.p50, 200)
        # The 80th percentile stays inside the samples: 100, 200, 400.
        self.assertGreater(hit.wall.p80, 200)
        self.assertLessEqual(hit.wall.p80, 400)
        self.assertEqual(hit.tokens.p50, 2000)

    def test_a_single_sample_is_its_own_p50_and_p80(self):
        hit = self.prior.lookup("reviewer", "pi", "zai/glm-5.3-flash")
        self.assertEqual((hit.wall.n, hit.wall.p50, hit.wall.p80), (1, 300, 300))

    def test_fallback_order_is_executor_model_then_executor_then_global(self):
        by_model = self.prior.lookup("stranger", "codex", "gpt-5.6-sol")
        self.assertEqual(by_model.key, ("codex", "gpt-5.6-sol"))
        self.assertTrue(by_model.fallback)
        self.assertEqual(by_model.wall.n, 3)
        by_executor = self.prior.lookup("stranger", "codex", "gpt-7-unseen")
        self.assertEqual(by_executor.key, ("codex",))
        self.assertEqual(by_executor.wall.n, 3)
        everything = self.prior.lookup("stranger", "nohost", "unseen-model")
        self.assertEqual(everything.key, ("global",))
        self.assertEqual(everything.wall.n, 4)

    def test_retry_multiplier_is_attempts_over_steps(self):
        # Three agent steps ran four attempts.
        self.assertAlmostEqual(self.prior.retry_multiplier, 4 / 3)

    def test_cost_is_known_only_from_priced_attempts(self):
        priced = self.prior.lookup("reviewer", "pi", "zai/glm-5.3-flash")
        self.assertEqual(priced.cost.n, 1)
        self.assertAlmostEqual(priced.cost.p50, 0.25)
        seat = self.prior.lookup("implementer", "codex", "gpt-5.6-sol")
        self.assertEqual(seat.cost.n, 3)
        self.assertEqual(seat.cost.p50, 0.0)


class WhatIsLeftOut(TempCase):

    def test_an_attempt_without_a_wall_adds_no_wall_sample(self):
        history = self.tmp / "h"
        summary(history / "r", "r", [
            {"role": "x", "executor": "pi", "model": "m",
             "attempts": [attempt(0.0, 10), attempt(50, 20)]}])
        prior = estimate.Prior.from_history([history])
        hit = prior.lookup("x", "pi", "m")
        self.assertEqual(hit.wall.n, 1)
        self.assertEqual(hit.tokens.n, 2)

    def test_mechanical_steps_are_not_samples(self):
        history = self.tmp / "h"
        summary(history / "r", "r", [
            {"role": "command", "kind": "command", "executor": None, "model": None,
             "attempts": [attempt(5, 0)]}])
        prior = estimate.Prior.from_history([history])
        self.assertEqual(prior.sample_count, 0)
        self.assertIsNone(prior.lookup("a", "b", "c"))

    def test_the_search_reaches_four_levels_down_and_no_further(self):
        history = self.tmp / "h"
        summary(history / "a" / "b" / "c" / "r4", "r4", [
            {"role": "x", "executor": "pi", "model": "m",
             "attempts": [attempt(10, 10)]}])
        summary(history / "a" / "b" / "c" / "d" / "r5", "r5", [
            {"role": "x", "executor": "pi", "model": "m",
             "attempts": [attempt(99, 99)]}])
        prior = estimate.Prior.from_history([history])
        self.assertEqual(prior.sample_count, 1)
        self.assertEqual(prior.lookup("x", "pi", "m").wall.p50, 10)

    def test_a_malformed_summary_is_named_and_skipped(self):
        history = self.tmp / "h"
        (history / "bad").mkdir(parents=True)
        (history / "bad" / "summary.json").write_text("{not json", encoding="utf-8")
        summary(history / "good", "good", [
            {"role": "x", "executor": "pi", "model": "m",
             "attempts": [attempt(10, 10)]}])
        prior = estimate.Prior.from_history([history])
        self.assertEqual(prior.sample_count, 1)
        self.assertEqual(len(prior.problems), 1)
        self.assertIn("bad", prior.problems[0])

    def test_no_history_at_all_gives_an_empty_prior(self):
        prior = estimate.Prior.from_history([self.tmp / "nothing-here"])
        self.assertEqual(prior.sample_count, 0)
        self.assertEqual(prior.retry_multiplier, 1.0)

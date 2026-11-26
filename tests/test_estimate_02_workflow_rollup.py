"""`estimate.estimate_workflow`: steps roll up to phases, phases to the run.

The phase rule is the barrier rule the live ETA already uses: a phase of N
agents at `max_parallel` M takes `ceil(N / M)` waves of the median step. A
cached step and a mechanical step (command, gate, merge) add nothing. The run
is the sum of its phases times the corpus retry multiplier. Confidence reads
`low` when a key has fewer than three samples, when a fallback key answered,
or when the cost is unpriced; `ok` otherwise.
"""

from __future__ import annotations

from ohflow import estimate
from ohflow.coords import coord
from ohflow.workflow import Phase, Step
from support import FAKE_MODEL, TempCase, agent_step, simple_workflow


def sample(role: str, wall: float, tokens: int, *, executor: str = "pi",
           model: str = FAKE_MODEL.model, cost=None, source=None) -> estimate.Sample:
    return estimate.Sample(role=role, executor=executor, model=model,
                           wall_s=wall, tokens=tokens, cost=cost,
                           cost_source=source, status="passed",
                           start_kind="initial", run_id="r", coord="c")


def prior_of(samples, *, retry: float = 1.0) -> estimate.Prior:
    return estimate.Prior(samples, retry_multiplier=retry, sources=["fixture"])


class PhaseRollup(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        # Three agents under a limit of two: two waves of the median step.
        self.workflow = simple_workflow(self.repo, phases=(
            Phase(name="Build", max_parallel=2,
                  steps=(agent_step("a"), agent_step("b"), agent_step("c"))),
            Phase(name="Ship", steps=(
                Step(id="tests", kind="command", command="echo ok"),
                agent_step("d"))),
        ))
        samples = []
        for step in ("a", "b", "c", "d"):
            for wall in (100.0, 200.0, 300.0):
                samples.append(sample(f"role-{step}", wall, 1000, cost=0.1,
                                      source="pi-catalog"))
        self.prior = prior_of(samples)

    def test_a_phase_is_rounds_times_the_median_step(self):
        out = estimate.estimate_workflow(self.workflow, self.prior)
        build = out["phases"][0]
        self.assertEqual(build["agents"], 3)
        self.assertEqual(build["max_parallel"], 2)
        self.assertEqual(build["wall_s"]["p50"], 2 * 200)
        self.assertEqual(build["tokens"]["p50"], 3 * 1000)
        self.assertAlmostEqual(build["cost_usd"], 0.3)

    def test_a_mechanical_step_adds_nothing_and_says_so(self):
        out = estimate.estimate_workflow(self.workflow, self.prior)
        tests = next(s for s in out["steps"] if s["coord"].endswith("tests"))
        self.assertEqual(tests["basis"], estimate.MECHANICAL)
        self.assertEqual(tests["wall_s"]["p50"], 0)
        ship = out["phases"][1]
        self.assertEqual(ship["agents"], 1)
        self.assertEqual(ship["wall_s"]["p50"], 200)

    def test_a_cached_step_costs_zero(self):
        cached = {coord(1, "build", 1, "a")}
        out = estimate.estimate_workflow(self.workflow, self.prior, cached=cached)
        a = next(s for s in out["steps"] if s["coord"] == coord(1, "build", 1, "a"))
        self.assertEqual(a["basis"], "cached")
        self.assertEqual(a["wall_s"]["p50"], 0)
        self.assertEqual(a["cost_usd"], 0.0)
        # Two live agents under a limit of two: one wave.
        self.assertEqual(out["phases"][0]["wall_s"]["p50"], 200)

    def test_the_run_is_the_phases_times_the_retry_multiplier(self):
        out = estimate.estimate_workflow(self.workflow, prior_of(
            list(self.prior.samples), retry=1.5))
        phases = sum(p["wall_s"]["p50"] for p in out["phases"])
        self.assertEqual(phases, 400 + 200)
        self.assertEqual(out["run"]["wall_s"]["p50"], round(phases * 1.5))
        self.assertEqual(out["run"]["tokens"]["p50"], round(4000 * 1.5))
        self.assertEqual(out["history"]["retry_multiplier"], 1.5)

    def test_the_cli_parallel_override_caps_every_phase(self):
        out = estimate.estimate_workflow(self.workflow, self.prior, max_parallel=1)
        self.assertEqual(out["phases"][0]["wall_s"]["p50"], 3 * 200)


class Confidence(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.workflow = simple_workflow(self.repo, steps=[agent_step("a")])
        self.coord = coord(1, "only-phase", 1, "a")

    def step(self, prior) -> dict:
        out = estimate.estimate_workflow(self.workflow, prior)
        return next(s for s in out["steps"] if s["coord"] == self.coord)

    def test_three_priced_samples_on_the_exact_key_read_ok(self):
        prior = prior_of([sample("role-a", w, 10, cost=0.1, source="pi-catalog")
                          for w in (1, 2, 3)])
        step = self.step(prior)
        self.assertEqual(step["confidence"], "ok")
        self.assertEqual(step["n"], 3)
        self.assertFalse(step["fallback"])

    def test_fewer_than_three_samples_read_low(self):
        prior = prior_of([sample("role-a", w, 10, cost=0.1, source="pi-catalog")
                          for w in (1, 2)])
        self.assertEqual(self.step(prior)["confidence"], "low")

    def test_a_fallback_key_reads_low(self):
        prior = prior_of([sample("other", w, 10, cost=0.1, source="pi-catalog")
                          for w in (1, 2, 3)])
        step = self.step(prior)
        self.assertTrue(step["fallback"])
        self.assertEqual(step["confidence"], "low")

    def test_a_subscription_cost_is_a_known_zero_and_reads_ok(self):
        prior = prior_of([sample("role-a", w, 10, cost=0.0, source="subscription")
                          for w in (1, 2, 3)])
        step = self.step(prior)
        self.assertEqual(step["cost_usd"], 0.0)
        self.assertEqual(step["confidence"], "ok")

    def test_an_unpriced_cost_reads_low_and_none(self):
        prior = prior_of([sample("role-a", w, 10, cost=0.0, source="unpriced")
                          for w in (1, 2, 3)])
        step = self.step(prior)
        self.assertIsNone(step["cost_usd"])
        self.assertEqual(step["confidence"], "low")

    def test_no_history_leaves_the_numbers_unknown(self):
        out = estimate.estimate_workflow(self.workflow, prior_of([]))
        step = next(s for s in out["steps"] if s["coord"] == self.coord)
        self.assertIsNone(step["wall_s"]["p50"])
        self.assertEqual(step["basis"], "no history")
        self.assertIsNone(out["run"]["wall_s"]["p50"])
        self.assertEqual(out["run"]["confidence"], "low")

    def test_the_text_rendering_names_n_and_the_range_per_phase(self):
        prior = prior_of([sample("role-a", w, 6000, cost=0.1, source="pi-catalog")
                          for w in (60, 120, 180)])
        text = estimate.render_text(estimate.estimate_workflow(self.workflow, prior))
        self.assertIn("Only phase", text)
        self.assertIn("p50", text)
        self.assertIn("p80", text)
        self.assertIn("| 3 |", text)
        self.assertIn("2 min", text)

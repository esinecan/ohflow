"""Inside one phase the step with the longest estimate takes its slot first.

A phase that holds more steps than its `max_parallel` ends soonest when its
longest step starts first. The engine reads each step's p50 wall time from the
run's `estimate.json` and grants the slots in that order. A step the estimate
holds no p50 for keeps its place, and a run without an estimate starts its
steps in workflow order.

Every phase here runs at one slot, so the order the attempts start in is the
order the slots were granted in. The run log says it.
"""

from __future__ import annotations

import time

from ohflow.run_log import RunLog
from ohflow.supervisor import RunOptions, run_workflow
from ohflow.workflow import Phase, Step
from support import (AgentScript, FakeHarnessExecutor, TempCase, agent_step,
                     git_repo, install_fake_harness_executor, quiet,
                     simple_workflow, stub_preflight)
from test_estimate_01_prior_from_history import attempt, summary


def _phase(steps: list[Step], limit: int = 1) -> Phase:
    return Phase(name="Only phase", steps=tuple(steps),
                 on_step_failure="continue", min_success="any",
                 max_parallel=limit)


class TheLongestStepStartsFirst(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        self.harness_executor = install_fake_harness_executor(
            self, FakeHarnessExecutor(default=AgentScript(final_text="DONE\n")))
        self.history = self.tmp / "history"

    def record(self, walls: dict[str, float]) -> None:
        for step_id, wall in walls.items():
            summary(self.history / f"r-{step_id}", f"r-{step_id}", [
                {"role": f"role-{step_id}", "executor": "pi",
                 "model": "fake/deterministic",
                 "attempts": [attempt(wall, 500, 0.0, "unpriced")]}])

    def started(self, steps: list[Step], *, history: bool = True,
                limit: int = 1) -> list[str]:
        workflow = simple_workflow(self.repo, phases=(_phase(steps, limit),))
        options = RunOptions(
            dashboard=False, harness_executors=self.harness_executors,
            say=lambda _line: None,
            history=(str(self.history),) if history else None)
        with quiet():
            outcome = run_workflow(workflow, self.tmp / "runs" / "r-one", options)
        self.assertEqual(outcome.status, "finished")
        return [e["coord"].split(".")[-1] for e in RunLog(outcome.run_dir).read()
                if e.get("event") == "attempt_started"]

    def test_the_steps_start_in_the_order_of_their_p50_longest_first(self):
        self.record({"a": 60, "b": 300, "c": 120})
        order = self.started([agent_step(i) for i in "abc"])
        self.assertEqual(order, ["b", "c", "a"],
                         "the engine must start the step with the longest "
                         "estimate first")

    def test_a_run_without_an_estimate_keeps_the_workflow_order(self):
        order = self.started([agent_step(i) for i in "abcd"], history=False)
        self.assertEqual(order, ["a", "b", "c", "d"])

    def test_equal_estimates_keep_the_workflow_order(self):
        self.record({"a": 90, "b": 90, "c": 90})
        order = self.started([agent_step(i) for i in "abc"])
        self.assertEqual(order, ["a", "b", "c"])

    def test_a_step_without_a_p50_keeps_its_place_among_ordered_steps(self):
        """A command step has no p50. It stays second, and the three agent
        steps share out the first, third and fourth place, longest first."""
        self.record({"a": 60, "c": 120, "d": 300})
        order = self.started([
            agent_step("a"), Step(id="b", kind="command", command="echo hi"),
            agent_step("c"), agent_step("d")])
        self.assertEqual(order, ["d", "b", "c", "a"])

    def test_the_longest_steps_hold_the_first_slots_of_a_wider_phase(self):
        """Two steps granted together race to their `attempt_started` line, so
        the first two are a set. `b` then holds its slot until all four have
        launched, which leaves one slot for `a` and `d` to take in turn."""
        def hold_until_all_four_launched() -> None:
            deadline = time.monotonic() + 10
            while (len(self.harness_executor.launched) < 4
                   and time.monotonic() < deadline):
                time.sleep(0.01)

        self.harness_executor.scripts["b"] = AgentScript(
            final_text="DONE\n", on_poll=hold_until_all_four_launched)
        self.record({"a": 60, "b": 300, "c": 120, "d": 30})
        order = self.started([agent_step(i) for i in "abcd"], limit=2)
        self.assertEqual(set(order[:2]), {"b", "c"})
        self.assertEqual(order[2:], ["a", "d"])

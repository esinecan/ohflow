"""Defect 47: one 180 s stall limit killed a quiet-reasoning codex step.

The first live full matrix gave every harness executor `stall_timeout_s=180`. A codex
agent thinks for minutes without an event, so the limit killed it as a
`stall` and the test case failed. The roll call now takes the limit per harness executor.
`STALL_S` holds the table and codex gets at least 600 s. The workflow argument
`stall_timeout_s` still overrides the table for every harness executor.
"""

from __future__ import annotations

from ohflow.harness_executors import CAP_STALL, harness_executor_info
from ohflow.workflows import rollcall
from support import TempCase

HARNESS_EXECUTORS = "pi,claude,codex"


class RollcallStallPerHarnessExecutor(TempCase):

    def _limits(self, **args) -> dict[str, int | None]:
        workflow = rollcall.build({"repo": str(self.tmp / "repo"), "scenario": "fanout",
                                   "harness_executors": HARNESS_EXECUTORS, **args})
        return {step.id.rsplit("-", 1)[0]: step.stall_timeout_s
                for phase in workflow.phases for step in phase.steps}

    def test_codex_gets_at_least_ten_minutes(self):
        self.assertGreaterEqual(self._limits()["codex"], 600)

    def test_every_harness_executor_that_takes_a_limit_gets_one(self):
        for harness_executor, limit in self._limits().items():
            if harness_executor_info(harness_executor).has(CAP_STALL):
                self.assertGreater(limit, 0, harness_executor)
            else:
                self.assertIsNone(limit, harness_executor)

    def test_the_table_has_a_row_only_for_harness_executors_that_take_a_limit(self):
        for harness_executor in HARNESS_EXECUTORS.split(","):
            self.assertEqual(harness_executor in rollcall.STALL_S,
                             harness_executor_info(harness_executor).has(CAP_STALL), harness_executor)

    def test_the_argument_overrides_every_harness_executor(self):
        for harness_executor, limit in self._limits(stall_timeout_s=45).items():
            self.assertEqual(limit, 45 if harness_executor_info(harness_executor).has(CAP_STALL) else None, harness_executor)

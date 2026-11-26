"""Defect 46: the roll-call gate passed a report that named the wrong harness executor.

The report holds a `harness_executor` field, and nothing compared it with the harness executor of the
step. An agent that copied another harness executor's report, or a step that ran on the
wrong harness executor, passed the gate when its tool list was inside the announced one.
`rollcall_matches` now takes the step's harness executor and fails a report that names
another. The roll-call workflow passes that harness executor on every report check.
"""

from __future__ import annotations

import json

from ohflow.gates import GateContext, rollcall_matches
from ohflow.workflows import rollcall
from support import TempCase

RESULT = {"tools": ["Bash"], "mcp_servers": ["forum"]}


class ReportHarnessExecutor(TempCase):

    def _ctx(self, report) -> GateContext:
        (self.tmp / "result.json").write_text(json.dumps(RESULT), encoding="utf-8")
        return GateContext(coord="c", repo=self.tmp, worktree=self.tmp, base_sha="x",
                           base_ref="main", attempt_dir=self.tmp, log_dir=self.tmp,
                           structured=report)

    def _report(self, harness_executor):
        return {"harness_executor": harness_executor, "tools": ["Bash"], "mcp_servers": ["forum"]}

    def test_report_harness_executor_naming_another_harness_executor_fails(self):
        result = rollcall_matches(self._ctx(self._report("pi")), harness_executor="codex")
        self.assertFalse(result.passed)
        self.assertIn("'pi'", result.detail)
        self.assertIn("'codex'", result.detail)

    def test_report_harness_executor_naming_the_step_harness_executor_passes(self):
        self.assertTrue(rollcall_matches(self._ctx(self._report("codex")),
                                         harness_executor="codex").passed)

    def test_report_harness_executor_missing_fails_when_the_step_names_one(self):
        report = {"tools": ["Bash"], "mcp_servers": ["forum"]}
        self.assertFalse(rollcall_matches(self._ctx(report), harness_executor="codex").passed)

    def test_report_harness_executor_is_not_checked_when_the_step_names_none(self):
        self.assertTrue(rollcall_matches(self._ctx(self._report("pi"))).passed)

    def test_report_harness_executor_reaches_every_report_check_of_the_workflow(self):
        workflow = rollcall.build({"repo": str(self.tmp / "repo"), "scenario": "merge",
                                   "harness_executors": "pi,claude"})
        seen = {}
        for phase in workflow.phases:
            for step in phase.steps:
                for check in step.gate.checks if step.gate else ():
                    if check.name == "rollcall_matches":
                        seen[step.id] = check.args["harness_executor"]
        self.assertEqual(seen, {"pi-1": "pi", "claude-1": "claude",
                                "consolidate": "claude"})

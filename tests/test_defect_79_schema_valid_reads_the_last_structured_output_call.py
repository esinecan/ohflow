"""A claude step with a schema reports through its last `StructuredOutput` call.

Observed 19.11.2026 in run `sleep-ontology/runs/a1`, step `bootstrap`: the
agent called `StructuredOutput` with a valid object, then a background subagent
reported in, and the agent ended on prose. That later turn closed with a
`result` event that carried no `structured_output`, and `schema_valid` failed
with "no fenced json block in the final message".

The gate judges the agent's latest `StructuredOutput` call, whatever prose
follows it. A later invalid call replaces an earlier valid one, and a
subagent's own call is not the step's report.
"""

from __future__ import annotations

from ohflow.gates import GateContext, schema_valid
from test_signed_in_02_runner_harness_executor import SCHEMA, SignedInHarnessExecutorCase


class TheLastStructuredOutputCallIsTheReport(SignedInHarnessExecutorCase):
    harness_executor_name = "claude"
    exe_var = "OHFLOW_CLAUDE_EXE"

    def _gate(self, result: dict, scenario: str):
        attempt = self.tmp / scenario
        ctx = GateContext(coord="01.only/01.claude", repo=self.workspace,
                          worktree=self.workspace, base_sha="", base_ref="",
                          attempt_dir=attempt, log_dir=attempt / "logs",
                          final_text=(attempt / "final.md").read_text(encoding="utf-8"),
                          structured=result["structured"], schema=SCHEMA)
        return schema_valid(ctx)

    def test_a_valid_call_passes_whatever_prose_follows(self):
        result = self._run("structured-then-prose", schema=SCHEMA)
        self.assertEqual(result["structured"], {"answer": "ok", "count": 2})
        self.assertIsNone(result["schema_error"])
        final = (self.tmp / "structured-then-prose" / "final.md").read_text(encoding="utf-8")
        self.assertEqual(final, "All readers reported. The report stands.")
        gate = self._gate(result, "structured-then-prose")
        self.assertTrue(gate.passed, gate.observed)

    def test_an_invalid_later_call_is_judged_not_the_earlier_valid_one(self):
        result = self._run("structured-invalid-later", schema=SCHEMA)
        self.assertEqual(result["structured"], {"answer": "ok", "count": "two"})
        gate = self._gate(result, "structured-invalid-later")
        self.assertFalse(gate.passed)
        self.assertIn("$.count", str(gate.observed))


if __name__ == "__main__":
    import unittest
    unittest.main()

"""Stage 7: invalid structured output is evidence, quarantine, and retry input."""

from __future__ import annotations

import json
from dataclasses import replace

from ohflow.engine import Engine
from ohflow.workflow import CheckSpec, GateSpec, Phase, RetryPolicy
from ohflow.structured import parse_structured
from support import (FakeHarnessExecutor, TempCase, AgentScript, git_repo,
                     install_fake_harness_executor, simple_workflow, step_statuses,
                     stub_preflight, agent_step)


SCHEMA = {
    "type": "object",
    "required": ["answer"],
    "properties": {"answer": {"type": "string"}},
}
SCHEMA_GATE = GateSpec(checks=(CheckSpec("schema_valid", {}),))
INVALID = "```json\n{not json}\n```\n"
VALID = '```json\n{"answer":"ok"}\n```\n'


class StructuredFakeHarnessExecutor(FakeHarnessExecutor):
    """Give FakeHarnessExecutor the same structured-result boundary as the real harness executors."""

    def collect(self, handle):
        result = super().collect(handle)
        schema_path = handle.out_dir / "schema.json"
        if not schema_path.exists():
            return result
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        final = (handle.out_dir / "final.md").read_text(encoding="utf-8")
        result["structured"], result["schema_error"] = parse_structured(
            final, schema)
        (handle.out_dir / "result.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8")
        return result


class InvalidJsonFlow(TempCase):

    def test_parse_error_is_preserved_while_quarantine_and_retry_continue(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        harness_executor = install_fake_harness_executor(self, StructuredFakeHarnessExecutor(scripts={
            "01.invalid": AgentScript(final_text=INVALID),
            "02.retrying": AgentScript(sequence=[
                {"final_text": INVALID}, {"final_text": VALID},
            ]),
            "01.after": AgentScript(final_text="DONE\n"),
        }))

        invalid = agent_step("invalid", gate=SCHEMA_GATE, schema=SCHEMA)
        retrying = replace(
            agent_step("retrying", gate=SCHEMA_GATE, schema=SCHEMA),
            retry=RetryPolicy(max=1, on=("gate:schema_valid",)),
        )
        workflow = simple_workflow(repo, max_parallel=1, phases=(
            Phase(name="Structured", steps=(invalid, retrying),
                  on_step_failure="quarantine", min_success="all"),
            Phase(name="After", steps=(agent_step("after"),),
                  on_step_failure="quarantine", min_success="all"),
        ))
        run_dir = self.run_dir()
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors).run()

        statuses = step_statuses(run_dir)
        self.assertEqual(statuses["01.structured/01.invalid"], "quarantined")
        self.assertEqual(statuses["02.after/01.after"], "passed")

        bad_dir = (run_dir / "phases" / "01.structured" / "01.invalid"
                   / "attempts" / "01")
        result = json.loads((bad_dir / "result.json").read_text(encoding="utf-8"))
        gate = json.loads((bad_dir / "gate.json").read_text(encoding="utf-8"))
        check = gate["checks"][0]
        self.assertFalse(check["passed"])
        self.assertIn("fenced json block did not parse", result["schema_error"])
        self.assertEqual(check["observed"], result["schema_error"])
        self.assertEqual(check["detail"], result["schema_error"])

        retry_dir = run_dir / "phases" / "01.structured" / "02.retrying"
        first_gate = json.loads((retry_dir / "attempts" / "01" / "gate.json")
                                .read_text(encoding="utf-8"))
        second_gate = json.loads((retry_dir / "attempts" / "02" / "gate.json")
                                 .read_text(encoding="utf-8"))
        self.assertFalse(first_gate["checks"][0]["passed"])
        self.assertTrue(second_gate["checks"][0]["passed"])
        self.assertEqual(statuses["01.structured/02.retrying"], "passed")
        self.assertEqual(harness_executor.script_for("01.structured/02.retrying").launches, 2)

        position = (retry_dir / "attempts" / "02" / "position.md").read_text(
            encoding="utf-8")
        self.assertIn("What failed last time (attempt 1)", position)
        self.assertIn("schema_valid", position)


if __name__ == "__main__":
    import unittest
    unittest.main()

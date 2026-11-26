"""Defect 5: the agent is shown the output contract it is judged against.

Fixed in `ebdbba3`, "ohflow: the agent is shown the contract it is judged
against".

What went wrong. A step could carry a `schema`, and the `schema_valid` gate
checked the agent's fenced json block against it, while the brief said nothing
about that schema beyond whatever the brief's author had typed by hand. The
agent was judged against a contract it had never read, and a brief that drifted
from the schema drifted silently.

What is asserted here. `render_position` walks the step's schema and states the
required keys, the types and the enumerated values, and names the gate that will
check them. The outline is generated from the same dict the gate reads, so no
brief author can make the two disagree. `_prepare_step_dir` writes `schema.json`
beside the brief and the position block points at it.

The schema in these tests is the shape the Cortea scouts were judged against:
a `dimension`, an array of `findings`, and a `summary`.
"""

from __future__ import annotations

import json

from ohflow.coords import render_position, render_schema_contract
from ohflow.engine import Engine
from ohflow.run_log import RunState
from support import (FakeHarnessExecutor, TempCase, AgentScript, git_repo,
                     install_fake_harness_executor, simple_workflow, stub_preflight,
                     agent_step)

SCOUT_SCHEMA = {
    "type": "object",
    "required": ["dimension", "findings", "summary"],
    "properties": {
        "dimension": {"type": "string"},
        "summary": {"type": "string"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["severity", "location", "finding"],
                "properties": {
                    "severity": {"type": "string",
                                 "enum": ["BLOCKING", "MINOR"]},
                    "location": {"type": "string"},
                    "finding": {"type": "string"},
                },
            },
        },
    },
}


class TheContractIsRendered(TempCase):

    def test_no_schema_renders_nothing(self):
        self.assertEqual(render_schema_contract(None), [])
        self.assertEqual(render_schema_contract({}), [])

    def test_the_gate_that_will_check_it_is_named(self):
        lines = "\n".join(render_schema_contract(SCOUT_SCHEMA))
        self.assertIn("schema_valid", lines,
                      "the agent is not told which gate judges this")
        self.assertIn("fenced ```json block", lines)

    def test_every_required_top_level_key_is_stated(self):
        lines = "\n".join(render_schema_contract(SCOUT_SCHEMA))
        for key in ("dimension", "findings", "summary"):
            self.assertIn(key, lines, f"{key} is required and is not shown")
        self.assertIn("Required at the top level:", lines)

    def test_types_and_nesting_are_stated(self):
        lines = "\n".join(render_schema_contract(SCOUT_SCHEMA))
        self.assertIn("array", lines)
        self.assertIn("each item is an object with:", lines)
        for key in ("severity", "location", "finding"):
            self.assertIn(key, lines)

    def test_enumerated_values_are_stated(self):
        lines = "\n".join(render_schema_contract(SCOUT_SCHEMA))
        self.assertIn("BLOCKING", lines)
        self.assertIn("MINOR", lines)
        self.assertIn("one of:", lines)

    def test_the_schema_file_is_named_when_a_path_is_given(self):
        lines = "\n".join(render_schema_contract(
            SCOUT_SCHEMA, schema_path=r"C:\runs\r-1\phases\01.p\01.s\schema.json"))
        self.assertIn("schema.json", lines)

    def test_a_huge_schema_is_truncated_and_says_so(self):
        big = {"type": "object", "required": ["a"], "properties": {
            f"key_{i}": {"type": "string"} for i in range(400)}}
        lines = render_schema_contract(big)
        self.assertLess(len(lines), 400)
        self.assertIn("the rest of the contract is in schema.json",
                      "\n".join(lines))


class ThePositionBlockCarriesTheContract(TempCase):

    def _position(self, **kw) -> str:
        workflow = simple_workflow(self.tmp / "repo",
                                   steps=[agent_step("scout", schema=SCOUT_SCHEMA)])
        step = workflow.phases[0].steps[0]
        return render_position(workflow, RunState(), step, **kw)

    def test_the_contract_is_in_the_position_block(self):
        text = self._position()
        self.assertIn("Your output contract", text)
        self.assertIn("schema_valid", text)
        self.assertIn("BLOCKING", text)

    def test_a_step_without_a_schema_gets_no_contract_block(self):
        workflow = simple_workflow(self.tmp / "repo", steps=[agent_step("plain")])
        text = render_position(workflow, RunState(), workflow.phases[0].steps[0])
        self.assertNotIn("Your output contract", text)

    def test_the_fingerprint_sees_the_keys_but_not_the_run_directory(self):
        """`include_run_id=False` is the fingerprint's view. A changed contract
        must change the fingerprint, and a new run directory must not."""
        without = self._position(include_run_id=False,
                                 schema_path=r"C:\runs\r-1\schema.json")
        self.assertIn("dimension", without)
        self.assertNotIn(r"C:\runs\r-1", without,
                         "the run directory leaked into the cache key")


class TheStepDirectoryCarriesTheContract(TempCase):

    def test_the_brief_and_schema_json_are_both_written(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript(final_text="DONE\n")))
        workflow = simple_workflow(repo,
                                   steps=[agent_step("scout", schema=SCOUT_SCHEMA)])
        run_dir = self.run_dir()
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors).run()

        d = run_dir / "phases" / "01.only-phase" / "01.scout"
        self.assertTrue((d / "schema.json").exists(),
                        "the raw JSON Schema was not written for the agent")
        self.assertEqual(json.loads((d / "schema.json").read_text(encoding="utf-8")),
                         SCOUT_SCHEMA)

        brief = (d / "brief.md").read_text(encoding="utf-8")
        self.assertIn("Your output contract", brief,
                      "the agent's brief does not carry the contract it is "
                      "judged against")
        self.assertIn("schema_valid", brief)
        self.assertIn("BLOCKING", brief)

        position = (d / "position.md").read_text(encoding="utf-8")
        self.assertIn("schema.json", position,
                      "the position block does not point at the schema file")

    def test_the_spec_tells_the_agent_process_where_the_schema_is(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript(final_text="DONE\n")))
        workflow = simple_workflow(repo,
                                   steps=[agent_step("scout", schema=SCOUT_SCHEMA)])
        run_dir = self.run_dir()
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors).run()
        spec = json.loads((run_dir / "phases" / "01.only-phase" / "01.scout" /
                           "spec.json").read_text(encoding="utf-8"))
        self.assertEqual(spec["schema_path"], "schema.json")

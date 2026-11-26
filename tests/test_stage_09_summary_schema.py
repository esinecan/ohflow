"""Stage 9a: every ohflow summary has a small, executable schema contract.

The regression was a report shape that was only described by convention.  A
summary with a missing required key, a malformed nested list item, or an
unknown status must now fail the same stdlib validator used by the schema gate.
The suite runner enables the same report-boundary audit for every Engine
summary, including child Python processes.  This module supplies the nested
mutation controls and also checks the preserved legacy examples shipped with
the skill.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest import mock

from ohflow import gates, rundir, summary_audit
from ohflow.engine import Engine
from support import (FakeHarnessExecutor, TempCase, AgentScript, git_repo,
                     install_fake_harness_executor, simple_workflow, stub_preflight,
                     agent_step)
from summary_schema_audit import SummarySchemaAudit


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "references" / "summary.schema.json"
EXAMPLES = ROOT / "references" / "examples"
FIXTURES = ROOT / "tests" / "fixtures" / "implement-review"
SUPPORTED_SCHEMA_KEYS = {
    "type", "required", "properties", "items", "enum",
    "additionalProperties",
}


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _assert_supported_subset(test: TempCase, node: object, path: str = "$") -> None:
    test.assertIsInstance(node, dict, path)
    for key, value in node.items():
        test.assertIn(key, SUPPORTED_SCHEMA_KEYS, f"unsupported schema keyword at {path}")
        if key == "type":
            test.assertIsInstance(value, (str, list),
                                  f"type at {path} must be a string or list")
            if isinstance(value, list):
                test.assertTrue(value, f"type list at {path} must not be empty")
                test.assertTrue(all(isinstance(item, str) for item in value), path)
        elif key == "required":
            test.assertIsInstance(value, list, f"required at {path} must be a list")
            test.assertTrue(all(isinstance(item, str) for item in value), path)
        elif key == "properties":
            test.assertIsInstance(value, dict, path)
            for name, child in value.items():
                _assert_supported_subset(test, child, f"{path}.properties[{name!r}]")
        elif key == "items":
            _assert_supported_subset(test, value, f"{path}.items")
        elif key == "enum":
            test.assertIsInstance(value, list, f"enum at {path} must be a list")
        elif key == "additionalProperties":
            test.assertIsInstance(value, (bool, dict), path)
            if isinstance(value, dict):
                _assert_supported_subset(test, value, f"{path}.additionalProperties")


class SummarySchema(TempCase):
    def _engine_summary(self, *, failing: bool = False) -> dict:
        repo = git_repo(self.tmp / ("repo-failed" if failing else "repo"))
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript(
            final_text="NOPE\n" if failing else "DONE\n")))
        run_dir = self.run_dir("summary-schema-failed" if failing
                              else "summary-schema")
        summary = Engine(
            simple_workflow(repo, name="summary-schema",
                            steps=[agent_step("only")]),
            run_dir, run_id=run_dir.name, verbose=False,
            harness_executors=self.harness_executors).run()
        persisted = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary, persisted)
        return persisted

    def test_schema_uses_only_the_validator_subset(self):
        _assert_supported_subset(self, _schema())

    def test_dynamic_map_schema_validates_each_value(self):
        schema = {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "required": ["count"],
                "properties": {"count": {"type": "integer"}},
                "additionalProperties": False,
            },
        }
        self.assertEqual(gates._validate_schema({"phase-a": {"count": 1}}, schema), [])
        wrong_type = gates._validate_schema(
            {"phase-a": {"count": "one"}}, schema)
        self.assertTrue(any("['phase-a'].count" in error
                            and "expected integer" in error
                            for error in wrong_type), wrong_type)
        unknown = gates._validate_schema(
            {"phase-a": {"count": 1, "surprise": True}}, schema)
        self.assertTrue(any("unexpected key 'surprise'" in error
                            for error in unknown), unknown)

    def test_engine_and_preserved_example_summaries_validate(self):
        schema = _schema()
        summaries = [("engine-passed", self._engine_summary()),
                     ("engine-failed", self._engine_summary(failing=True))]
        summaries.extend(
            (str(path), json.loads(path.read_text(encoding="utf-8")))
            for path in sorted([*EXAMPLES.rglob("*.summary.json"),
                                *FIXTURES.glob("*.summary.json")])
        )
        self.assertGreaterEqual(len(summaries), 4)
        for source, summary in summaries:
            with self.subTest(source=source):
                self.assertEqual(gates._validate_schema(summary, schema), [])

    def test_missing_required_key_fails(self):
        schema = _schema()
        summary = self._engine_summary()
        summary.pop("phases")
        errors = gates._validate_schema(summary, schema)
        self.assertTrue(any("missing required key 'phases'" in error for error in errors), errors)

    def test_nested_item_type_and_enum_fail(self):
        schema = _schema()
        summary = self._engine_summary()

        wrong_item = copy.deepcopy(summary)
        wrong_item["quarantined"] = [17]
        errors = gates._validate_schema(wrong_item, schema)
        self.assertTrue(any("quarantined[0]" in error for error in errors), errors)

        wrong_enum = copy.deepcopy(summary)
        wrong_enum["status"] = "not-a-run-status"
        errors = gates._validate_schema(wrong_enum, schema)
        self.assertTrue(any("not-a-run-status" in error for error in errors), errors)

    def test_engine_report_boundary_rejects_a_nested_output_mutation(self):
        repo = git_repo(self.tmp / "repo-boundary-mutation")
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript(final_text="DONE\n")))
        run_dir = self.run_dir("summary-schema-boundary-mutation")
        real_attempt_records = rundir.Run.attempts

        def malformed_attempts(*args, **kwargs):
            records = real_attempt_records(*args, **kwargs)
            self.assertTrue(records, "the Engine run must produce an actual attempt")
            records[0]["attempt"] = "not-an-integer"
            return records

        with SummarySchemaAudit():
            with mock.patch.object(rundir.Run, "attempts", autospec=True,
                                   side_effect=malformed_attempts):
                with self.assertRaisesRegex(
                        summary_audit.SummarySchemaAuditError,
                        r"attempt.*expected integer"):
                    Engine(
                        simple_workflow(repo, name="summary-schema",
                                        steps=[agent_step("only")]),
                        run_dir, run_id=run_dir.name, verbose=False,
                        harness_executors=self.harness_executors).run()

        self.assertFalse((run_dir / "summary.json").exists(),
                         "the malformed actual output must be rejected before write")

    def test_engine_report_boundary_rejects_a_missing_required_key(self):
        repo = git_repo(self.tmp / "repo-boundary-missing-key")
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript(final_text="DONE\n")))
        run_dir = self.run_dir("summary-schema-boundary-missing-key")
        real_audit = summary_audit.audit_summary

        def remove_required_key(actual_run_dir, summary):
            summary.pop("phases")
            return real_audit(actual_run_dir, summary)

        with SummarySchemaAudit():
            with mock.patch.object(summary_audit, "audit_summary",
                                   side_effect=remove_required_key):
                with self.assertRaisesRegex(
                        summary_audit.SummarySchemaAuditError,
                        r"missing required key 'phases'"):
                    Engine(
                        simple_workflow(repo, name="summary-schema",
                                        steps=[agent_step("only")]),
                        run_dir, run_id=run_dir.name, verbose=False,
                        harness_executors=self.harness_executors).run()

        self.assertFalse((run_dir / "summary.json").exists(),
                         "the missing key must be rejected before write")

    def test_child_engine_inherits_the_report_boundary_audit(self):
        repo = git_repo(self.tmp / "repo-child-boundary")
        good_run = self.run_dir("summary-schema-child-valid")
        bad_run = self.run_dir("summary-schema-child-invalid")
        code = r'''from contextlib import nullcontext
from pathlib import Path
import sys
from unittest import mock

from ohflow import rundir
from ohflow.engine import Engine
from support import FakeHarnessExecutor, AgentScript, simple_workflow, agent_step

repo, run_dir = map(Path, sys.argv[1:3])
mutate = sys.argv[3] == "mutate"
harness_executor = FakeHarnessExecutor(default=AgentScript(final_text="DONE\n"))
real_attempt_records = rundir.Run.attempts

def malformed(*args, **kwargs):
    records = real_attempt_records(*args, **kwargs)
    records[0]["attempt"] = "child-not-an-integer"
    return records

mutation = (mock.patch.object(rundir.Run, "attempts", autospec=True, side_effect=malformed)
            if mutate else nullcontext())
with mock.patch.object(Engine, "preflight", return_value=[]), \
     mock.patch.object(Engine, "baseline", return_value={"skipped": "child test"}), \
\
     mutation:
    Engine(simple_workflow(repo, name="child-summary", steps=[agent_step("only")]),
           run_dir, run_id=run_dir.name, verbose=False,
           harness_executors=lambda name: harness_executor).run()
'''
        kwargs = ({"creationflags": subprocess.CREATE_NO_WINDOW}
                  if sys.platform == "win32" else {})
        with SummarySchemaAudit() as audit:
            env = dict(os.environ)
            existing = env.get("PYTHONPATH")
            roots = [str(ROOT / "scripts"), str(ROOT / "tests")]
            env["PYTHONPATH"] = os.pathsep.join(
                roots + ([existing] if existing else []))
            valid = subprocess.run(
                [sys.executable, "-c", code, str(repo), str(good_run), "valid"],
                cwd=ROOT, env=env, text=True, capture_output=True, **kwargs)
            child = subprocess.run(
                [sys.executable, "-c", code, str(repo), str(bad_run), "mutate"],
                cwd=ROOT, env=env, text=True, capture_output=True, **kwargs)

        self.assertEqual(valid.returncode, 0, valid.stderr + valid.stdout)
        self.assertTrue((good_run / "summary.json").exists())
        self.assertNotEqual(child.returncode, 0)
        self.assertIn("attempt: expected integer or null, got str",
                      child.stderr + child.stdout)
        self.assertEqual((audit.checked, audit.rejected), (2, 1))
        self.assertTrue(all(record["pid"] != os.getpid()
                            for record in audit.records))
        self.assertFalse((bad_run / "summary.json").exists())


if __name__ == "__main__":
    import unittest

    unittest.main()

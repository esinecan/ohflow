"""The `schema_valid` gate can read a JSON report file instead of the message.

A worker that writes its report to a file and ends with a plain summary has no
fenced block for the gate to read. With `path`, the gate validates the file,
and the brief names the file instead of the fenced block.
"""

from __future__ import annotations

import json

from ohflow.coords import render_schema_contract
from ohflow.gates import GateContext, schema_valid
from support import TempCase

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


GOOD = {"dimension": "d", "summary": "s",
        "findings": [{"severity": "MINOR", "location": "a.py:1", "finding": "f"}]}


class TheGateReadsTheReportFile(TempCase):

    def _ctx(self):
        tmp = self.tmp
        return GateContext(coord="01.p/01.s", repo=tmp, worktree=tmp,
                           base_sha="", base_ref="", attempt_dir=tmp / "a",
                           log_dir=tmp / "l", final_text="Summary: done.",
                           structured=None)

    def _write(self, value):
        out = self.tmp / "reports" / "out.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(value), encoding="utf-8")

    def test_a_valid_file_passes_without_a_fenced_block(self):
        self._write(GOOD)
        r = schema_valid(self._ctx(), schema=SCOUT_SCHEMA,
                         path="reports/out.json")
        self.assertTrue(r.passed, r.observed)

    def test_a_file_missing_a_required_key_fails_with_the_path(self):
        bad = json.loads(json.dumps(GOOD))
        del bad["findings"][0]["location"]
        self._write(bad)
        r = schema_valid(self._ctx(), schema=SCOUT_SCHEMA,
                         path="reports/out.json")
        self.assertFalse(r.passed)
        self.assertIn("$.findings[0]: missing required key 'location'",
                      str(r.observed))

    def test_an_absent_file_fails(self):
        r = schema_valid(self._ctx(), schema=SCOUT_SCHEMA,
                         path="reports/out.json")
        self.assertFalse(r.passed)
        self.assertEqual(r.observed, "reports/out.json is absent")

    def test_an_escaping_path_is_refused(self):
        r = schema_valid(self._ctx(), schema=SCOUT_SCHEMA, path="../x.json")
        self.assertFalse(r.passed)
        self.assertEqual(r.observed, "bad arguments")

    def test_the_contract_names_the_file_not_the_fenced_block(self):
        text = "\n".join(render_schema_contract(
            SCOUT_SCHEMA, report_path="reports/out.json"))
        self.assertIn("reports/out.json", text)
        self.assertNotIn("fenced", text)

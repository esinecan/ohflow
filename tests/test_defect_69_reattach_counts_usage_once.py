"""Defect 69: a reattached attempt had its usage counted twice.

A `pi-cloud` or `durable` step whose supervisor stops is closed `deferred` for
a reattach, and the resume continues the SAME attempt: one attempt number, one
attempt directory, one `result.json`. The run log then holds two executions
with that number. The read-out added the tokens of `result.json` once per
execution, so status, the dashboard and the exit report showed twice the usage
of the one attempt (seen live: 46.4 k for an attempt of 23.2 k).

Each attempt directory is counted once now.
"""

from __future__ import annotations

import json

from dashboard_support import T0, RunLog, agent, workflow_json
from ohflow import live, rundir
from support import TempCase

NOW = T0 + 100
COORD = "01.report/01.a"
TOKENS = {"prompt_tokens": 22842, "completion_tokens": 358,
          "cache_read_tokens": 14144, "cache_write_tokens": 0,
          "reasoning_tokens": 0}


class AReattachedAttemptCountsItsUsageOnce(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.run = self.run_dir("r-reattach")
        workflow_json(self.run, [("Report", [agent("a", harness_executor="pi-cloud")], 1)])

    def _result(self, attempt: int, tokens: dict) -> None:
        adir = rundir.attempt_dir(self.run, COORD, attempt)
        adir.mkdir(parents=True, exist_ok=True)
        (adir / "result.json").write_text(json.dumps({
            "coord": COORD, "attempt": attempt, "execution_status": "finished",
            "tokens": tokens}), encoding="utf-8")

    def _agent(self) -> dict:
        read_out = live.read_out(self.run, NOW)
        return next(a for a in read_out["agents"] if a["coord"] == COORD), read_out

    def test_one_attempt_closed_and_reattached(self):
        (RunLog(self.run)
         .phase(1, "01.report", "Report", [COORD])
         .start(2, COORD, 1)
         .finish(3, COORD, 1, "deferred",
                 error="reattach: the supervisor stopped while this attempt ran")
         .phase(4, "01.report", "Report", [COORD])
         .start(5, COORD, 1, kind="reattach")
         .finish(6, COORD, 1, "passed")
         .settle(7, "01.report", "passed", 1, 1)
         .run_finished(8, "finished"))
        self._result(1, TOKENS)
        a, read_out = self._agent()
        self.assertEqual(a["tokens"]["input"], TOKENS["prompt_tokens"])
        self.assertEqual(a["tokens"]["output"], TOKENS["completion_tokens"])
        self.assertEqual(read_out["run"]["tokens"]["input"], TOKENS["prompt_tokens"])

    def test_the_run_reads_the_numbers_of_the_attempt_once(self):
        (RunLog(self.run)
         .phase(1, "01.report", "Report", [COORD])
         .start(2, COORD, 1)
         .finish(3, COORD, 1, "deferred",
                 error="reattach: the supervisor stopped while this attempt ran")
         .start(5, COORD, 1, kind="reattach")
         .finish(6, COORD, 1, "passed")
         .settle(7, "01.report", "passed", 1, 1)
         .run_finished(8, "finished"))
        self._result(1, dict(TOKENS))
        rows = rundir.open_run(self.run).attempts(COORD)
        self.assertEqual(len(rows), 2)
        self.assertIsNone(rows[0]["tokens"])
        self.assertTrue(rows[0]["continued"])
        self.assertFalse(rows[1]["continued"])
        self.assertEqual(rows[1]["tokens"], TOKENS)
        total = sum((r["tokens"] or {}).get("prompt_tokens", 0) for r in rows)
        self.assertEqual(total, TOKENS["prompt_tokens"])

    def test_an_old_summary_with_both_copies_is_read_once(self):
        entry = {"attempt": 1, "dir": "/runs/r/phases/01.report/01.a/attempts/01",
                 "tokens": dict(TOKENS), "cost": 0.0019, "llm_calls": 3}
        summary = {"phases": {"01.report": {"steps": {COORD: {
            "status": "passed", "kind": "agent",
            "attempts": [dict(entry, status="deferred"),
                         dict(entry, status="passed")]}}}}}
        (item,) = rundir.walk_summary(summary)
        first, last = item.executions
        self.assertIsNone(first["tokens"])
        self.assertIsNone(first["cost"])
        self.assertEqual(last["tokens"], TOKENS)
        self.assertEqual(last["llm_calls"], 3)
        self.assertTrue(first["continued"])

    def test_the_table_row_keeps_its_totals(self):
        from ohflow import table
        entry = {"attempt": 1, "kind": "agent", "tool_calls": 2, "llm_calls": 3,
                 "wall_seconds": 10.0, "cost": 0.0019, "tokens": dict(TOKENS)}
        continued = {"attempt": 1, "kind": "agent", "continued": True,
                     "tool_calls": None, "llm_calls": None, "wall_seconds": None,
                     "cost": None, "tokens": None}
        row = table._fold([continued, entry])
        self.assertEqual(row["executions"], 2)
        self.assertEqual(row["agent_executions"], 2)
        self.assertEqual(row["prompt_tokens"], TOKENS["prompt_tokens"])
        self.assertEqual(row["llm_calls"], 3)
        self.assertEqual(row["cost"], "0.0019")

    def test_two_real_attempts_still_add_up(self):
        (RunLog(self.run)
         .phase(1, "01.report", "Report", [COORD])
         .start(2, COORD, 1)
         .finish(3, COORD, 1, "failed", error="gate")
         .start(4, COORD, 2, kind="retry")
         .finish(5, COORD, 2, "passed")
         .settle(6, "01.report", "passed", 1, 1)
         .run_finished(7, "finished"))
        self._result(1, TOKENS)
        self._result(2, TOKENS)
        a, _snap = self._agent()
        self.assertEqual(a["tokens"]["input"], 2 * TOKENS["prompt_tokens"])


if __name__ == "__main__":
    import unittest
    unittest.main()

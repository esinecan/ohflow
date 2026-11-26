"""The exit report and the retro draft read `estimate.json` back.

A run that was estimated ends with a "Predicted vs actual" table in
`exit-report.md`: per phase, the predicted p50 and p80 minutes and tokens
beside what the run recorded. The retro draft names every step whose actual
wall time went past its p80, so the person judging the run starts from the
misses. A run with no `estimate.json` gets neither, and nothing says
"predicted" about a number nobody predicted.
"""

from __future__ import annotations

import json

from dashboard_support import RunLog, agent, workflow_json
from ohflow import estimate, exit_report, retrodraft, rundir
from support import TempCase

A = "01.build/01.a"


def finished_run(run_dir, *, wall: float):
    workflow_json(run_dir, [("Build", [agent("a")], 1)])
    log = RunLog(run_dir)
    log.phase(1, "01.build", "Build", [A], 1)
    log.start(2, A, 1)
    log.finish(2 + wall, A, 1, "passed", wall=wall)
    log.settle(3 + wall, "01.build", "passed", 1, 1)
    log.run_finished(4 + wall, "finished")
    attempt = run_dir / "phases" / "01.build" / "01.a" / "attempts" / "01"
    attempt.mkdir(parents=True)
    (attempt / "result.json").write_text(json.dumps({
        "wall_seconds": wall, "tokens": {"prompt_tokens": 900, "completion_tokens": 100},
        "cost": 0.0, "cost_source": "unpriced", "tool_calls": 3, "llm_calls": 2}),
        encoding="utf-8")
    return run_dir


def write_estimate(run_dir):
    (run_dir / estimate.ESTIMATE_FILE).write_text(json.dumps({
        "schema": estimate.SCHEMA, "generated": "2026-09-30T11:59:00Z",
        "workflow": "synthetic",
        "history": {"sources": 3, "samples": 3, "retry_multiplier": 1.0, "paths": []},
        "run": {"wall_s": {"p50": 120, "p80": 300}, "tokens": {"p50": 500, "p80": 800},
                "cost_usd": None, "confidence": "low", "basis": "fixture"},
        "phases": [{"coord": "01.build", "name": "Build", "max_parallel": 1,
                    "agents": 1, "wall_s": {"p50": 120, "p80": 300},
                    "tokens": {"p50": 500, "p80": 800}, "cost_usd": None,
                    "n": 3, "basis": "fixture", "confidence": "low"}],
        "steps": [{"coord": A, "kind": "agent", "key": ["role a", "pi", "m"],
                   "basis": "fixture", "n": 3, "fallback": False,
                   "confidence": "low", "wall_s": {"p50": 120, "p80": 300},
                   "tokens": {"p50": 500, "p80": 800}, "cost_usd": None}],
    }), encoding="utf-8")


class ExitReport(TempCase):

    def test_the_markdown_carries_the_predicted_vs_actual_table(self):
        run_dir = finished_run(self.tmp / "run", wall=600.0)
        write_estimate(run_dir)
        paths = exit_report.write_exit_report(run_dir, exit_report.exit_info("finished"))
        md = paths["md"].read_text(encoding="utf-8")
        self.assertIn("## Predicted vs actual", md)
        section = md.split("## Predicted vs actual", 1)[1].split("## ", 1)[0]
        row = next(line for line in section.splitlines() if line.startswith("| `01.build`"))
        self.assertIn("2 min", row)          # p50
        self.assertIn("5 min", row)          # p80
        self.assertIn("10 min", row)         # actual
        self.assertIn("1.0 k", row)          # actual tokens
        run_row = next(line for line in section.splitlines() if line.startswith("| run |"))
        self.assertIn("2 min", run_row)

    def test_a_run_with_no_estimate_has_no_such_table(self):
        run_dir = finished_run(self.tmp / "run", wall=600.0)
        paths = exit_report.write_exit_report(run_dir, exit_report.exit_info("finished"))
        md = paths["md"].read_text(encoding="utf-8")
        self.assertNotIn("Predicted", md)


class RetroDraft(TempCase):

    def draft(self, *, wall: float, estimated: bool) -> str:
        run_dir = finished_run(self.tmp / "run", wall=wall)
        if estimated:
            write_estimate(run_dir)
        rundir.open_run(run_dir).write_summary()
        (run_dir / "retro.md").write_text(
            f"# retro\n\n{retrodraft.BEGIN}\n{retrodraft.END}\n\n| judged |\n",
            encoding="utf-8")
        status, note = retrodraft.write(run_dir)
        self.assertEqual(status, retrodraft.WRITTEN, note)
        return (run_dir / "retro.md").read_text(encoding="utf-8")

    def test_a_step_past_its_p80_earns_a_pointer(self):
        text = self.draft(wall=600.0, estimated=True)
        self.assertIn(f"`{A}` ran 600 s", text)
        self.assertIn("p80 was 300 s", text)
        self.assertIn("3 samples", text)

    def test_a_step_inside_its_p80_earns_none(self):
        text = self.draft(wall=200.0, estimated=True)
        self.assertNotIn("the estimate's p80 was", text)

    def test_no_estimate_means_no_estimate_pointer(self):
        text = self.draft(wall=600.0, estimated=False)
        self.assertNotIn("the estimate's p80 was", text)

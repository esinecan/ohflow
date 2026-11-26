"""Pi audit artifacts keep priced usage visible and export the right session.

What went wrong.  The first pi table draft had no direct artifact test for the
five host-compatible token fields.  The first transcript command also looked for
``transcript_dir`` in the summary's compact attempt record, although the summary
stores that field in ``<attempt>/result.json``.  It then chose list order and
filename order, which are not the attempt and session clocks.

What is asserted here.  A pi-catalog row shows its price and all five L8 token
fields.  Transcript export resolves a step by id or coordinate, ignores a synthetic
non-start, chooses the highest real attempt and its recorded session, launches
a Python ``OHFLOW_PI_EXE`` correctly, and writes both explicit and default HTML
paths.  No provider is called.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from dashboard_support import RunLog, workflow_json, agent
from ohflow import table
from ohflow.cli import EXIT_OK, main as cli_main
from support import TempCase, quiet


PINNED_BASH = r"C:\Program Files\Git\bin\bash.exe"


class PiTableAndTranscriptTests(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self._set_env("OHFLOW_BASH", PINNED_BASH)

    def _set_env(self, name: str, value: str) -> None:
        old = os.environ.get(name)
        os.environ[name] = value
        self.addCleanup(
            lambda: os.environ.pop(name, None) if old is None
            else os.environ.__setitem__(name, old))

    def _summary(self, run_dir: Path, attempts: list[dict]) -> None:
        summary = {
            "run_id": "r-pi-audit",
            "workflow": "pi-audit",
            "status": "finished",
            "started": "2026-09-28T00:00:00Z",
            "finished": "2026-09-28T00:01:00Z",
            "repo": str(self.tmp),
            "phases": {
                "01.audit": {
                    "steps": {
                        "01.audit/01.review": {
                            "step_id": "review",
                            "kind": "agent",
                            "status": "passed",
                            "attempts": attempts,
                            # The step-root projection may be stale while an
                            # attempt history still has the durable truth.
                            "result": {"conversation_id": "stale"},
                            "dir": str(run_dir / "phases" / "01.audit"
                                       / "01.review"),
                        }
                    }
                }
            },
        }
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8")

    def test_table_shows_priced_cost_and_every_l8_token_column(self):
        run_dir = self.tmp / "table-run"
        attempt = {
            "attempt": 1,
            "kind": "agent",
            "status": "passed",
            "started": "2026-09-28T00:00:01Z",
            "tool_calls": 2,
            "llm_calls": 3,
            "wall_seconds": 12.5,
            "tokens": {
                "prompt_tokens": 804,
                "completion_tokens": 26,
                "cache_read_tokens": 704,
                "cache_write_tokens": 7,
                "reasoning_tokens": 11,
            },
            "cost": 0.00125,
            "cost_source": "pi-catalog",
            "dir": str(run_dir / "attempt-01"),
        }
        self._summary(run_dir, [attempt])

        rows, problems = table.load_rows([run_dir], by="step")

        self.assertEqual(problems, [])
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["cost"], "0.0013")
        self.assertEqual(
            {key: row[key] for key in (
                "prompt_tokens", "completion_tokens", "cache_read_tokens",
                "cache_write_tokens", "reasoning_tokens")},
            {"prompt_tokens": 804, "completion_tokens": 26,
             "cache_read_tokens": 704, "cache_write_tokens": 7,
             "reasoning_tokens": 11})
        rendered = table.render_markdown(rows)
        for heading in ("Prompt tokens", "Completion tokens", "Cache read",
                        "Cache write", "Reasoning tokens", "Cost"):
            self.assertIn(heading, rendered)
        self.assertIn("0.0013", rendered)

    def test_transcript_exports_latest_real_attempt_with_python_pi_executable(self):
        """The run has a run log and no `summary.json`: `transcript` asks the run."""
        run_dir = self.tmp / "transcript-run"
        coord = "01.audit/01.review"
        step_root = run_dir / "phases" / "01.audit" / "01.review"
        old_dir = step_root / "attempts" / "01"
        new_dir = step_root / "attempts" / "02"
        for directory, session_id in ((old_dir, "old-session"),
                                      (new_dir, "new-session")):
            session = directory / "session"
            session.mkdir(parents=True)
            (session / f"{session_id}.jsonl").write_text(
                '{"type":"session"}\n', encoding="utf-8")
            (directory / "result.json").write_text(json.dumps({
                "conversation_id": session_id,
                # Relative transcript paths are useful in portable fixtures and
                # archived runs, so the resolver must anchor them correctly.
                "transcript_dir": "session",
            }), encoding="utf-8")

        workflow_json(run_dir, [("Audit", [agent("review")], 1)])
        (RunLog(run_dir)
         .phase(1, "01.audit", "Audit", [coord])
         .start(2, coord, 1)
         .finish(3, coord, 1, "failed")
         .start(4, coord, 2, "retry")
         .finish(5, coord, 2, "passed")
         # A cached finish launched no agent. Even with a high attempt
         # number it must not displace attempt 2.
         .finish(6, coord, 99, "cached"))
        self.assertFalse((run_dir / "summary.json").exists())

        marker = self.tmp / "export-argv.json"
        fake_pi = self.tmp / "fake pi.py"
        fake_pi.write_text(
            "from __future__ import annotations\n"
            "import json, os, sys\n"
            "from pathlib import Path\n"
            "Path(os.environ['OHFLOW_EXPORT_MARKER']).write_text(\n"
            "    json.dumps(sys.argv[1:]), encoding='utf-8')\n"
            "args = sys.argv[1:]\n"
            "source = Path(args[args.index('--export') + 1])\n"
            "target = Path(args[args.index('--export') + 2])\n"
            "target.parent.mkdir(parents=True, exist_ok=True)\n"
            "target.write_text('<html>' + source.name + '</html>', "
            "encoding='utf-8')\n",
            encoding="utf-8")
        self._set_env("OHFLOW_PI_EXE", str(fake_pi))
        self._set_env("OHFLOW_EXPORT_MARKER", str(marker))

        requested = self.tmp / "requested" / "audit.html"
        with quiet() as output:
            code = cli_main(["transcript", "--run", str(run_dir), "--step",
                             "review", "--html", "--out", str(requested)])
        self.assertEqual(code, EXIT_OK, output.out)
        self.assertEqual(requested.read_text(encoding="utf-8"),
                         "<html>new-session.jsonl</html>")
        argv = json.loads(marker.read_text(encoding="utf-8"))
        self.assertEqual(argv, ["--export",
                                str(new_dir / "session" / "new-session.jsonl"),
                                str(requested.resolve())])

        with quiet() as output:
            code = cli_main(["transcript", "--run", str(run_dir), "--step",
                             "01.audit/01.review", "--html"])
        default = run_dir / "review.transcript.html"
        self.assertEqual(code, EXIT_OK, output.out)
        self.assertEqual(default.read_text(encoding="utf-8"),
                         "<html>new-session.jsonl</html>")


if __name__ == "__main__":
    import unittest
    unittest.main()

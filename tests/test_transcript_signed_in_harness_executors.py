"""`ohflow transcript` answers for every harness executor, not only for pi.

What went wrong. The verb exported a pi session and refused every other harness executor
with "no pi transcript". A claude or codex attempt already leaves its event log
in `logs/`, so the verb had a transcript to show and did not look.

What is asserted here. For each signed-in harness executor, `ohflow transcript` on a run whose step
used that harness executor prints the path of the attempt's transcript and exits 0. For claude
and codex the transcript is the event log under `logs/`. A step with no transcript
still exits non-zero and says why.
"""

from __future__ import annotations

import json
from pathlib import Path

from dashboard_support import RunLog, workflow_json, agent
from ohflow.cli import EXIT_FAIL, EXIT_OK, main as cli_main
from support import TempCase, quiet

TRANSCRIPTS = {"claude": "logs/claude-events.jsonl", "codex": "logs/codex-events.jsonl"}
COORD = "01.audit/01.review"


class TranscriptSignedInHarnessExecutors(TempCase):

    def _run(self, harness_executor: str, *, with_log: bool = True, log: bytes = b"{}\n",
             transcript: str | None = None) -> Path:
        run_dir = self.tmp / f"{harness_executor}-run"
        attempt = run_dir / "phases" / "01.audit" / "01.review" / "attempts" / "01"
        (attempt / "logs").mkdir(parents=True)
        if with_log:
            path = attempt / (transcript or TRANSCRIPTS[harness_executor])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(log)
        (attempt / "result.json").write_text(
            json.dumps({"conversation_id": "c-1"}), encoding="utf-8")
        workflow_json(run_dir, [("Audit", [agent("review", harness_executor=harness_executor)], 1)])
        (RunLog(run_dir)
         .phase(1, "01.audit", "Audit", [COORD])
         .start(2, COORD, 1)
         .finish(3, COORD, 1, "passed"))
        return run_dir

    def test_transcript_prints_the_event_log_of_a_claude_attempt(self):
        self._assert_transcript("claude")

    def test_transcript_prints_the_event_log_of_a_codex_attempt(self):
        self._assert_transcript("codex")

    def _assert_transcript(self, harness_executor: str) -> None:
        run_dir = self._run(harness_executor)
        with quiet() as output:
            code = cli_main(["transcript", "--run", str(run_dir), "--step", "review", "--html"])
        self.assertEqual(code, EXIT_OK, output.out)
        printed = Path(output.out.strip())
        self.assertEqual(printed.name, Path(TRANSCRIPTS[harness_executor]).name)
        self.assertEqual(printed.parent.name, Path(TRANSCRIPTS[harness_executor]).parent.name)
        self.assertTrue(printed.is_file())

    def test_transcript_without_an_event_log_fails_and_says_why(self):
        run_dir = self._run("claude", with_log=False)
        with quiet() as output:
            code = cli_main(["transcript", "--run", str(run_dir), "--step", "review", "--html"])
        self.assertEqual(code, EXIT_FAIL)
        self.assertIn("no transcript for step 'review'", output.out)
        self.assertNotIn("no pi transcript", output.out)

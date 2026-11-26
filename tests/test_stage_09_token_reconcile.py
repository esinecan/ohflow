"""Stage 9: result token totals reconcile with the usage records the harness executor owns."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures" / "usage"
SCRIPTS = HERE.parent / "scripts"


class TokenReconciliation(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ohflow-u9b-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _summary(self, harness_executor: str, kind: str = "agent") -> dict:
        return {
            "run_id": f"u9b-{harness_executor}", "workflow": "u9b-fixture",
            "repo": "fixture", "started": "2026-09-28T00:00:00Z",
            "finished": "2026-09-28T00:00:01Z", "args": {"harness_executor": harness_executor},
            "phases": {"01.fixture": {"steps": {
                "01.fixture/01.attempt": {
                    "kind": kind, "status": "passed", "attempts": [{
                        "attempt": 1, "kind": kind, "started": "now",
                        "dir": "attempt",
                    }],
                },
            }}},
        }

    def _case(self, harness_executor: str, *, kind: str = "agent") -> Path:
        root = self.tmp / harness_executor
        attempt = root / "attempt"
        attempt.mkdir(parents=True)
        source = FIXTURES / harness_executor
        shutil.copy2(source / "result.json", attempt / "result.json")
        shutil.copy2(source / "spec.json", attempt / "spec.json")
        shutil.copytree(source / "session", attempt / "session")
        shutil.copytree(source / "logs", attempt / "logs")
        summary_harness_executor = "codex" if harness_executor.startswith("pi") else harness_executor
        (root / "summary.json").write_text(
            json.dumps(self._summary(summary_harness_executor, kind), indent=2),
            encoding="utf-8")
        return root

    def _run(self, root: Path) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(SCRIPTS) + os.pathsep + env.get("PYTHONPATH", "")
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        return subprocess.run(
            [sys.executable, "-m", "ohflow.cli", "table", "--runs",
             str(root), "--reconcile"], cwd=str(HERE.parent), env=env,
            capture_output=True, text=True, encoding="utf-8", **kwargs)

    def test_the_pi_fixture_reconciles_exactly(self):
        pi = self._run(self._case("pi"))
        self.assertEqual(pi.returncode, 0, pi.stderr)

    def test_missing_reasoning_defaults_to_zero_and_uses_attempt_harness_executor(self):
        completed = self._run(self._case("pi-missing-reasoning"))
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_altered_number_names_attempt_and_both_values(self):
        root = self._case("pi")
        result_path = root / "attempt" / "result.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        original = result["tokens"]["prompt_tokens"]
        result["tokens"]["prompt_tokens"] = original + 1
        result_path.write_text(json.dumps(result), encoding="utf-8")

        completed = self._run(root)
        self.assertEqual(completed.returncode, 1)
        output = completed.stdout + completed.stderr
        self.assertIn("attempt 1", output)
        self.assertIn(f'"prompt_tokens": {original + 1}', output)
        self.assertIn(f'"prompt_tokens": {original}', output)

    def test_malformed_usage_fails_closed(self):
        root = self._case("pi")
        event_log = root / "attempt" / "logs" / "pi-events.jsonl"
        lines = event_log.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            event = json.loads(line)
            if event.get("type") == "message_end" and event.get("message", {}).get("role") == "assistant":
                event["message"]["usage"]["input"] = "not-a-count"
                lines[index] = json.dumps(event)
                break
        event_log.write_text("\n".join(lines) + "\n", encoding="utf-8")
        completed = self._run(root)
        self.assertEqual(completed.returncode, 1)
        self.assertIn("usage is malformed", completed.stderr)

    def test_mechanical_step_is_skipped_without_agent_usage(self):
        root = self.tmp / "mechanical"
        root.mkdir()
        summary = self._summary("pi", kind="command")
        (root / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
        completed = self._run(root)
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()


"""The end-to-end test: the `smoke` matrix of `ohflow rollcall`, on real models.

    python ohflow/tests/run_tests.py --e2e

Skipped by default, and every skip prints its reason.

There is one end-to-end mechanism: the roll call. This test calls the same
`run_matrix` that `ohflow rollcall --matrix smoke` calls, so a green run here
means the verb works on this box.

Why this test exists. Every other test in this suite runs against a fake agent
harness executor, which is the right trade for speed and leaves one question open: does a
real provider still behave the way the engine expects.

What it costs. The key is `ZAI_CODING_CN_API_KEY`, a flat-rate subscription, so
pi's calls cost nothing per token; claude and codex run on their signed-in
seats. It costs wall time: three small agents, a few minutes.

What it does NOT do. It does not provoke a rate limit. Test cases run one after
another, so at most one Z.AI request is in flight, well inside the standing rule
in `references/ohflow.md` of at most five.

Everything is written into a temporary directory: the repository, its worktrees
and both runs.
"""

from __future__ import annotations

import os
import sys
import unittest

from e2e_support import KEY_ENV, why_skip
from support import TempCase

from ohflow import rollcall

#: Evaluated once, at import. `run_tests.py` sets `OHFLOW_E2E` before it
#: discovers any test module, so the flag is already in place here.
SKIP_REASON = why_skip()


@unittest.skipIf(SKIP_REASON is not None, SKIP_REASON or "")
class TheSmokeMatrixOnRealHarnessExecutors(TempCase):

    def test_the_smoke_matrix_passes(self):
        lines: list[str] = []

        def write(line: str) -> None:
            lines.append(line)
            print(f"  [e2e] {line}")
            sys.stdout.flush()

        out = self.tmp / "rollcall"
        code = rollcall.run_matrix(matrix="smoke", out=str(out), write=write)

        self.assertEqual(lines[-1], "ROLLCALL PASS: 3 of 3 test cases",
                         "\n".join(lines))
        self.assertEqual(code, rollcall.EXIT_OK)
        self.assertEqual(sum(x.startswith("PASS ") for x in lines), 3)
        self.assertTrue((out / "matrix.json").exists())
        self._assert_no_key_leaked(out)

    def _assert_no_key_leaked(self, root) -> None:
        """The key must appear in no artefact. Read, compared, never printed."""
        key = os.environ.get(KEY_ENV) or ""
        if not key:
            return
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in (".json", ".md", ".log",
                                                         ".cmd", ".jsonl"):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            self.assertNotIn(key, text, f"the key value was written into "
                                        f"{path.relative_to(root)}")

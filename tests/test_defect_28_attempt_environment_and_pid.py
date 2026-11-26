"""D-28: gates receive attempt env vars."""

import json
import sys

from ohflow.gates import GateContext, run_gate
from ohflow.workflow import CheckSpec, GateSpec
from support import TempCase


class AttemptFactsAreDurable(TempCase):

    def test_gate_command_reads_attempt_environment(self):
        attempt_dir = self.tmp / "attempts" / "03"
        attempt_dir.mkdir(parents=True)
        target = attempt_dir / "seen.json"
        py = sys.executable.replace("\\", "/")
        cmd = (f'"{py}" -c "import json,os,pathlib; '
               f'pathlib.Path(r\'{target}\').write_text(json.dumps('
               f'[os.environ[\'OHFLOW_ATTEMPT\'], '
               f'os.environ[\'OHFLOW_ATTEMPT_DIR\']]))"')
        ctx = GateContext(coord="01.p/01.s", repo=self.tmp,
                          worktree=self.tmp, base_sha="", base_ref="main",
                          attempt_dir=attempt_dir, log_dir=attempt_dir / "logs",
                          attempt=3)
        report = run_gate(ctx, GateSpec(checks=(
            CheckSpec("command_exit", {"cmd": cmd}),)))
        self.assertTrue(report.passed, report.failure_lines())
        seen = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(seen, ["3", str(attempt_dir.resolve())])

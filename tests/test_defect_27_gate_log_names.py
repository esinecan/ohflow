"""D-27: command gate evidence names include index and command hash."""

from ohflow.gates import GateContext, run_gate
from ohflow.workflow import CheckSpec, GateSpec
from support import TempCase


class GateLogsDoNotCollide(TempCase):

    def test_commands_with_the_same_long_prefix_get_distinct_logs(self):
        prefix = ": check=" + ("same-prefix-" * 8)
        gate = GateSpec(checks=(
            CheckSpec("command_exit", {"cmd": prefix + "one; echo one"}),
            CheckSpec("command_exit", {"cmd": prefix + "two; echo two"}),
        ))
        ctx = GateContext(coord="01.p/01.s", repo=self.tmp,
                          worktree=self.tmp, base_sha="", base_ref="main",
                          attempt_dir=self.tmp / "attempt",
                          log_dir=self.tmp / "attempt" / "logs")
        run_gate(ctx, gate)
        names = sorted(p.name for p in ctx.log_dir.glob("*.out.log"))
        self.assertEqual(len(names), 2)
        self.assertRegex(names[0], r"gate-01-command_exit-[0-9a-f]{10}\.out\.log")
        self.assertRegex(names[1], r"gate-02-command_exit-[0-9a-f]{10}\.out\.log")

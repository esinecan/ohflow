from __future__ import annotations

from types import SimpleNamespace

from ohflow.campaign import AcceptanceCheck, CampaignController
from ohflow.gates import GateContext, command_exit, with_base
from ohflow.paths import posix
from support import TempCase

SHA = "0123456789abcdef0123456789abcdef01234567"


class TheBasePlaceholder(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.out = self.tmp / "out.txt"
        self.cmd = 'echo "{base}" > "' + posix(self.out) + '"'

    def gate(self, base: str):
        d = self.tmp / "attempt"
        ctx = GateContext(coord="01.step/01.step", repo=self.tmp, worktree=self.tmp,
                          base_sha=base, base_ref="main", attempt_dir=d,
                          log_dir=d / "logs")
        return command_exit(ctx, cmd=self.cmd)

    def test_with_base_fills_only_the_placeholder(self) -> None:
        self.assertEqual(with_base("run --changed {base}", SHA), f"run --changed {SHA}")
        self.assertEqual(with_base("echo ${HOME} {app}", ""), "echo ${HOME} {app}")
        self.assertIsNone(with_base("run --changed {base}", ""))

    def test_command_exit_runs_the_command_on_the_steps_base_commit(self) -> None:
        result = self.gate(SHA)
        self.assertTrue(result.passed, result.detail)
        self.assertEqual(self.out.read_text(encoding="utf-8").strip(), SHA)
        self.assertIn(SHA, result.detail)

    def test_a_step_without_a_base_fails_and_runs_nothing(self) -> None:
        result = self.gate("")
        self.assertFalse(result.passed)
        self.assertEqual(result.observed, "no base commit")
        self.assertFalse(self.out.exists())

    def test_an_acceptance_check_fills_the_integration_commit_of_its_workspace(self) -> None:
        camp = SimpleNamespace(
            _check_dir=lambda cwd, land: self.tmp,
            spaces=[SimpleNamespace(name="app"), SimpleNamespace(name="docs")],
            _shas=lambda: {"app": "f" * 40, "docs": SHA},
            camp=SimpleNamespace(integration_branch="integration"))
        m = SimpleNamespace(acceptance_checks=[
            AcceptanceCheck("check-1", self.cmd, cwd="land:docs")])
        (out,) = CampaignController._acceptance_checks(camp, m, self.tmp / "run", [])
        self.assertEqual(out["exit"], 0, out)
        self.assertEqual(self.out.read_text(encoding="utf-8").strip(), SHA)

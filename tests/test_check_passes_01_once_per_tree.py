from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from ohflow import check_passes
from ohflow.campaign import AcceptanceCheck, CampaignController
from ohflow.engine import Engine
from ohflow.gates import GateContext, command_exit
from ohflow.paths import posix
from ohflow.run_log import RunLog
from ohflow.patterns import _commands
from ohflow.workflow import CheckSpec, GateSpec, Phase, Step, Workflow, WorktreeSpec
from support import TempCase, git_repo

HERE = Path(__file__).resolve().parent


def git(repo: Path, *args: str) -> None:
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@localhost",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@localhost")
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                   env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


class OncePerTree(TempCase):
    def setUp(self) -> None:
        super().setUp()
        self.repo = git_repo(self.tmp / "repo")
        self.run_dir = self.tmp / "run"
        self.counter = self.tmp / "counter.txt"
        self.cmd = f'echo ran >> "{posix(self.counter)}"'
        self.n = 0

    def gate(self, cmd: str | None = None, **args):
        self.n += 1
        d = self.tmp / f"attempt-{self.n}"
        ctx = GateContext(coord=f"0{self.n}.step/01.step", repo=self.repo,
                          worktree=self.repo, base_sha="", base_ref="main",
                          attempt_dir=d, log_dir=d / "logs", run_dir=self.run_dir)
        return command_exit(ctx, cmd=cmd or self.cmd, **args)

    def runs(self) -> int:
        return (len(self.counter.read_text(encoding="utf-8").splitlines())
                if self.counter.exists() else 0)

    def test_a_second_check_on_the_same_tree_reuses_the_pass(self) -> None:
        first = self.gate()
        second = self.gate()
        self.assertTrue(first.passed and second.passed)
        self.assertEqual(self.runs(), 1)
        self.assertIn("reused the pass of 01.step/01.step attempt 1", second.detail)
        self.assertEqual(second.evidence_path, first.evidence_path)

    def test_a_new_commit_runs_the_command_again(self) -> None:
        self.gate()
        (self.repo / "b.txt").write_text("b\n", encoding="utf-8")
        git(self.repo, "add", "b.txt")
        git(self.repo, "commit", "-m", "b")
        self.gate()
        self.assertEqual(self.runs(), 2)

    def test_a_dirty_tree_neither_reuses_nor_records(self) -> None:
        (self.repo / "loose.txt").write_text("x\n", encoding="utf-8")
        self.gate()
        self.gate()
        self.assertEqual(self.runs(), 2)
        self.assertFalse((self.run_dir / check_passes.FILE).exists())

    def test_a_failure_is_never_reused(self) -> None:
        cmd = self.cmd + " && exit 1"
        self.assertFalse(self.gate(cmd).passed)
        self.assertFalse(self.gate(cmd).passed)
        self.assertEqual(self.runs(), 2)

    def test_reuse_false_always_runs(self) -> None:
        self.gate(reuse=False)
        self.gate(reuse=False)
        self.assertEqual(self.runs(), 2)

    def test_the_acceptance_check_reuses_the_gates_pass(self) -> None:
        self.gate()
        camp = SimpleNamespace(_check_dir=lambda cwd, land: self.repo)
        m = SimpleNamespace(acceptance_checks=[AcceptanceCheck("check-1", self.cmd)])
        (out,) = CampaignController._acceptance_checks(camp, m, self.run_dir, [])
        self.assertEqual((out["exit"], out.get("reused")), (0, True))
        self.assertEqual(self.runs(), 1)

    def test_an_acceptance_check_with_no_prior_pass_runs(self) -> None:
        camp = SimpleNamespace(_check_dir=lambda cwd, land: self.repo)
        m = SimpleNamespace(acceptance_checks=[AcceptanceCheck("check-1", self.cmd)])
        (out,) = CampaignController._acceptance_checks(camp, m, self.run_dir, [])
        self.assertEqual((out["exit"], out.get("reused")), (0, None))
        self.assertEqual(self.runs(), 1)


class TheEngineRunsTheSuiteOncePerTree(TempCase):
    def test_a_second_step_on_the_unchanged_worktree_reuses_the_first_pass(self):
        repo = git_repo(self.tmp / "repo")
        counter = self.tmp / "counter.txt"
        check = GateSpec(checks=(CheckSpec(
            "command_exit", {"cmd": f'echo ran >> "{posix(counter)}"', "expect": 0}),))
        workflow = Workflow(
            name="once-per-tree", repo=repo, base_branch="main",
            baseline_cmd=None, max_parallel=1, transient_backoff_s=0,
            worktrees=(WorktreeSpec(name="w", path=self.tmp / "wt", branch="once",
                                    base="main", node_modules_mode="none"),),
            phases=(
                Phase(name="Implement", on_step_failure="quarantine", steps=(
                    Step(id="implement", kind="command", worktree="w",
                         command="git status --porcelain", gate=check),)),
                Phase(name="Review", on_step_failure="quarantine", steps=(
                    Step(id="review", kind="command", worktree="w",
                         command="git status --porcelain", gate=check),)),
            ),
        )
        run_dir = self.run_dir()
        engine = Engine(workflow, run_dir, run_id=run_dir.name, verbose=False)
        engine.poll_interval_s = 0.05
        engine.run()
        state = RunLog.replay(run_dir)
        self.assertEqual({c: r.status for c, r in state.steps.items()},
                         {"01.implement/01.implement": "passed",
                          "02.review/01.review": "passed"})
        self.assertEqual(counter.read_text(encoding="utf-8").splitlines(), ["ran"])


class ConstructMarksCrossWorkspaceCommands(TempCase):
    def test_a_command_naming_another_workspace_is_never_reused(self) -> None:
        data = {"commands": [{"cmd": "make -C {api}", "workspace": "web"},
                             {"cmd": "npm test", "workspace": "web"}]}
        checks = _commands(data, "web", frozenset({"web", "api"}))
        self.assertEqual([c.args.get("reuse") for c in checks], [False, None])


class AnEmptySelectionFails(TempCase):
    def test_a_k_pattern_that_matches_nothing_exits_1(self) -> None:
        done = subprocess.run([sys.executable, str(HERE / "run_tests.py"),
                               "-k", "zz_no_test_has_this_name", "-q"],
                              capture_output=True, text=True,
                              stdin=subprocess.DEVNULL,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertEqual(done.returncode, 1, done.stdout[-2000:])
        self.assertIn("NO TESTS RAN", done.stdout)

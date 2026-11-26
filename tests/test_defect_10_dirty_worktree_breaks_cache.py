"""Defect 10: a finished step's dirty worktree must invalidate its cache.

What went wrong.  The cache key named the workflow, agent, gate, base commit, and
dependencies, but it did not name uncommitted files.  A resume therefore
reported an agent as cached even when somebody had edited its finished tree.

What is asserted here.  These are real Engine runs over real git worktrees and
the deterministic FakeHarnessExecutor.  An agent's own commit leaves a clean tree and a
clean resume launches nothing.  A tracked edit or a non-ignored untracked file
re-runs only the step whose worktree changed.  An ignored file remains outside
the key.  The newly added command time cap is also agent identity and invalidates
only the step whose value changes.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import replace
from pathlib import Path

from ohflow.engine import Engine
from ohflow.fingerprint import (FINGERPRINT_VERSION, fingerprint_input,
                                worktree_dirty_digest)
from ohflow.run_log import RunLog
from ohflow.workflow import Phase, Workflow, WorktreeSpec
from support import (FakeHarnessExecutor, TempCase, AgentScript, git_repo,
                     install_fake_harness_executor, stub_preflight, agent_step)


class CommittingHarnessExecutor(FakeHarnessExecutor):
    """Make every dirty successful execution leave one real clean commit."""

    def collect(self, handle):
        result = super().collect(handle)
        spec = json.loads(handle.spec_path.read_text(encoding="utf-8"))
        workspace = Path(spec["workspace"])
        owned = workspace / "agent-owned.txt"
        if not owned.exists():
            owned.write_text(f"committed by {handle.coord}\n", encoding="utf-8")
        status = subprocess.run(
            ["git", "-C", str(workspace), "status", "--porcelain"],
            check=True, capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout
        if not status:
            return result
        subprocess.run(
            ["git", "-C", str(workspace), "add", "-A"],
            check=True, capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        subprocess.run(
            ["git", "-C", str(workspace),
             "-c", "user.name=ohflow tests",
             "-c", "user.email=tests@localhost",
             "commit", "-m", f"agent {handle.coord}"],
            check=True, capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return result


class DirtyWorktreeBreaksCache(TempCase):

    def setUp(self) -> None:
        super().setUp()
        stub_preflight(self)

    def _git(self, repo: Path, *args: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(repo), *args], check=True,
            capture_output=True, text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return completed.stdout.strip()

    def _fixture(self, name: str):
        root = self.tmp / name
        repo = git_repo(root / "repo")
        (repo / ".gitignore").write_text("ignored.tmp\n", encoding="utf-8")
        self._git(repo, "add", ".gitignore")
        self._git(repo, "-c", "user.name=ohflow tests",
                  "-c", "user.email=tests@localhost",
                  "commit", "-m", "ignore test scratch")

        worktrees = tuple(
            WorktreeSpec(
                name=f"w{i}", path=root / f"worktree-{i}",
                branch=f"{name}-agent-{i}", base="main",
                node_modules_mode="none",
            )
            for i in (1, 2)
        )
        steps = tuple(replace(agent_step(f"s{i}"), worktree=f"w{i}")
                      for i in (1, 2))
        workflow = Workflow(
            name=f"dirty-cache-{name}", repo=repo, base_branch="main",
            baseline_cmd=None, max_parallel=2, transient_backoff_s=0,
            worktrees=worktrees,
            phases=(Phase(name="Agents", steps=steps),),
        )
        harness_executor = install_fake_harness_executor(
            self, CommittingHarnessExecutor(default=AgentScript(final_text="DONE\n")))
        run_dir = root / "run"
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors).run()
        self.assertEqual(len(harness_executor.launched), 2)
        for worktree in worktrees:
            self.assertTrue(
                (worktree.path / "agent-owned.txt").is_file(),
                f"initial fake agent did not publish its owned file: {worktree.path}")

        # The agents moved both HEADs, but committed state is deliberately not
        # dirty state.  This clean resume is the regression's critical control.
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False,
               resume=True,
               harness_executors=self.harness_executors).run()
        self.assertEqual(len(harness_executor.launched), 2,
                         "a clean resume re-ran an agent after its own commit")
        return workflow, harness_executor, run_dir, worktrees

    def _assert_only_first_reran(self, harness_executor: FakeHarnessExecutor, before: int) -> None:
        self.assertEqual(len(harness_executor.launched), before + 1)
        self.assertTrue(harness_executor.launched[-1].endswith("/01.s1"), harness_executor.launched)

    def _assert_clean_resume_stays_cached(self, workflow, harness_executor, run_dir) -> None:
        before = len(harness_executor.launched)
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False,
               resume=True,
               harness_executors=self.harness_executors).run()
        self.assertEqual(
            len(harness_executor.launched), before,
            "the agent committed its dirty input, but the clean resume "
            "missed the cache")

    def test_a_missing_worktree_has_a_stable_nonclean_digest(self):
        repo = git_repo(self.tmp / "clean-repo")
        missing = self.tmp / "missing-worktree"
        expected = (
            "5783acb16e1a6ec159f1ecfb25781295789a310eae91bd707f281038f9d86059")
        self.assertEqual(worktree_dirty_digest(missing), expected)
        self.assertEqual(worktree_dirty_digest(missing), expected)
        self.assertNotEqual(worktree_dirty_digest(repo), expected)

    def test_a_tracked_edit_reruns_only_its_step(self):
        workflow, harness_executor, run_dir, worktrees = self._fixture("tracked")
        body = fingerprint_input(
            workflow, RunLog.replay(run_dir), workflow.phases[0].steps[0])
        self.assertEqual(body["fingerprint_version"], FINGERPRINT_VERSION)
        self.assertEqual(body["agent"]["command_time_cap_s"], None)
        self.assertEqual(len(body["worktree"]["dirty_digest"]), 64)
        target = worktrees[0].path / "agent-owned.txt"
        target.write_text(target.read_text(encoding="utf-8") + "dirty\n",
                          encoding="utf-8")
        before = len(harness_executor.launched)

        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False,
               resume=True,
               harness_executors=self.harness_executors).run()

        self._assert_only_first_reran(harness_executor, before)
        self._assert_clean_resume_stays_cached(workflow, harness_executor, run_dir)

    def test_an_untracked_file_reruns_only_its_step(self):
        workflow, harness_executor, run_dir, worktrees = self._fixture("untracked")
        (worktrees[0].path / "new.bin").write_bytes(b"\x00new\xffcontents\n")
        before = len(harness_executor.launched)

        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False,
               resume=True,
               harness_executors=self.harness_executors).run()

        self._assert_only_first_reran(harness_executor, before)
        self._assert_clean_resume_stays_cached(workflow, harness_executor, run_dir)

    def test_an_ignored_file_does_not_rerun_any_step(self):
        workflow, harness_executor, run_dir, worktrees = self._fixture("ignored")
        (worktrees[0].path / "ignored.tmp").write_text(
            "not an input\n", encoding="utf-8")
        before = len(harness_executor.launched)

        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False,
               resume=True,
               harness_executors=self.harness_executors).run()

        self.assertEqual(len(harness_executor.launched), before)

    def test_command_time_cap_seconds_invalidates_only_the_changed_agent(self):
        workflow, harness_executor, run_dir, _worktrees = self._fixture("command-time-cap")
        first, second = workflow.phases[0].steps
        changed_first = replace(
            first, agent=replace(first.agent, command_time_cap_s=60))
        changed = replace(
            workflow, phases=(replace(workflow.phases[0],
                                      steps=(changed_first, second)),))
        before = len(harness_executor.launched)

        Engine(changed, run_dir, run_id=run_dir.name, verbose=False,
               resume=True,
               harness_executors=self.harness_executors).run()

        self._assert_only_first_reran(harness_executor, before)


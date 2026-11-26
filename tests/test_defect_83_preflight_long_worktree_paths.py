"""Defect 83: preflight did not see a worktree path past 260 characters on Windows.

On 23.11.2026 the first milestone of the campaign `construct-issues-4-6`
crashed before any agent started: `git worktree add` failed with `Filename
too long`, because the run's clone had no `core.longpaths` and the worktree
root plus the longest tracked path under `ohflow/` passed 260. Preflight
now fails before the run for each workspace with no `core.longpaths` whose
worktree root plus the longest tracked path at the worktree's base makes a
full path of 260 characters or more, names the workspace, and says the fix.
The tracked paths are read at each worktree's `base`, so a base branch that
holds a path the checked-out branch lacks counts too, and the boundary is the
measured one: `git worktree add` succeeds at a full path of 259 characters
and fails at 260. A step that runs on another machine is skipped by the
check.

The platform is faked: the check reads Windows through the module's own `os`,
which the tests swap for a namespace, so pathlib and the real git calls keep
this platform's behaviour on every runner. A worktree root that passes the
limit is a path the workflow names and nothing on disk ever creates. A
tracked path that pins the boundary or sits on a base branch the checkout
lacks enters the repository's tree through `git mktree` and
`git commit-tree`, so no long path is ever written to disk.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from ohflow import cli
from ohflow import preflight as ohpreflight
from ohflow.engine import Engine, PreflightError
from ohflow.workflow import (AgentSpec, Phase, Step, Workflow, Workspace,
                             WorktreeSpec, validate)
from support import FAKE_MODEL, FakeHarnessExecutor, TempCase, git_repo
from verb_support import call

LONG_NAME = "w" * 250

WORKFLOW_PY = '''
from pathlib import Path

from ohflow.workflow import (AgentSpec, ModelConfig, Phase, Step, Workflow,
                             Workspace, WorktreeSpec)

MODEL = ModelConfig(model="fake/deterministic",
                    base_url="http://127.0.0.1:0/never-called",
                    api_key_env="OHFLOW_TEST_FAKE_KEY")


def build(args):
    root = Path(args["root"])
    spaces = (Workspace("short", Path(args["short"])),
              Workspace("long", Path(args["long"])))
    trees = (WorktreeSpec(name="short-wt", path=root / "wt-short",
                          branch="short-out", base="main",
                          node_modules_mode="none", workspace="short"),
             WorktreeSpec(name="long-wt", path=root / ("w" * 250),
                          branch="long-out", base="main",
                          node_modules_mode="none", workspace="long"))

    def step(sid, wt):
        return Step(id=sid, kind="agent", worktree=wt, write_scope=("**",),
                    agent=AgentSpec(role=sid, brief="do the thing",
                                    model=MODEL, harness_executor="pi"))

    return Workflow(name="long-paths", workspaces=spaces, worktrees=trees,
                    phases=(Phase("Build", (step("s1", "short-wt"),
                                            step("s2", "long-wt"))),),
                    transient_backoff_s=0)
'''


def build(repo_short: Path, repo_long: Path, root_short: Path,
          root_long: Path, executors: tuple[str, str] = ("pi", "pi"),
          bases: tuple[str, str] = ("main", "main")) -> Workflow:
    """Two workspaces, one worktree each. `executors` names the harness
    executor of the short step and of the long step, `bases` the base of the
    short worktree and of the long worktree."""
    spaces = (Workspace("short", repo_short), Workspace("long", repo_long))
    trees = (WorktreeSpec(name="short-wt", path=root_short,
                          branch="short-out", base=bases[0],
                          node_modules_mode="none", workspace="short"),
             WorktreeSpec(name="long-wt", path=root_long,
                          branch="long-out", base=bases[1],
                          node_modules_mode="none", workspace="long"))

    def step(sid: str, wt: str, executor: str) -> Step:
        return Step(id=sid, kind="agent", worktree=wt, write_scope=("**",),
                    agent=AgentSpec(role=sid, brief="do the thing",
                                    model=FAKE_MODEL, harness_executor=executor))

    return Workflow(
        name="long-paths", workspaces=spaces, worktrees=trees,
        phases=(Phase("Build", (step("s1", "short-wt", executors[0]),
                                step("s2", "long-wt", executors[1]))),),
        transient_backoff_s=0)


def repo_with_base_path(root: Path, base: str, name: str) -> Path:
    """A repository checked out on `main` and clean, whose branch `base`
    holds one tracked path `name` characters long beside the checkout's
    files. The path enters the branch through `git mktree` and
    `git commit-tree`, so no long path is ever written to or read from
    disk."""
    repo = git_repo(root)
    env = dict(os.environ,
               GIT_CONFIG_GLOBAL=str(repo / ".gitconfig-none"),
               GIT_CONFIG_SYSTEM=str(repo / ".gitconfig-none"))

    def git(*args: str, input: str | None = None) -> str:
        data = input.encode("utf-8") if input is not None else None
        done = subprocess.run(["git", "-C", str(repo), *args], input=data,
                              capture_output=True, check=True, env=env)
        return done.stdout.decode("utf-8").strip()

    blob = git("hash-object", "-w", "--stdin", input="x\n")
    readme = git("rev-parse", "HEAD:README.md")
    tree = git("mktree",
               input=f"100644 blob {readme}\tREADME.md\n"
                     f"100644 blob {blob}\t{name}\n")
    commit = git("commit-tree", tree, "-p", "HEAD", "-m",
                 "a long tracked path")
    git("update-ref", f"refs/heads/{base}", commit)
    return repo


class WindowsLongWorktreePaths(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.repo_short = git_repo(self.tmp / "short-repo")
        self.repo_long = git_repo(self.tmp / "long-repo")
        self.resolver = lambda name: FakeHarnessExecutor()

    def fake_windows(self):
        """The platform as Windows, for the check alone."""
        windows = SimpleNamespace(name="nt", environ=os.environ)
        return mock.patch.object(ohpreflight, "os", windows)

    def roots(self) -> tuple[Path, Path]:
        return self.tmp / "wt-short", self.tmp / LONG_NAME

    def test_a_workspace_each_side_of_the_limit(self):
        root_short, root_long = self.roots()
        workflow = build(self.repo_short, self.repo_long, root_short, root_long)
        self.assertEqual(validate(workflow).name, "long-paths")

        with self.fake_windows():
            problems = ohpreflight.workflow_problems(workflow, self.resolver)

        self.assertEqual(len(problems), 1, problems)
        self.assertRegex(
            problems[0],
            r"workspace 'long' at .+long-repo: no core\.longpaths, and the "
            r"worktree root 'long-wt' \(\d+\) plus the longest tracked path "
            r"\(9\) gives a full path of \d+, past the 259 Windows allows")
        self.assertNotIn("'short'", problems[0])

    def test_the_boundary_is_a_full_path_of_259(self):
        root_ok = self.tmp / "wt-ok"
        root_over = self.tmp / "wt-over"
        repo_ok = repo_with_base_path(self.tmp / "ok-repo", "ok-base",
                                      "p" * (259 - 1 - len(str(root_ok))))
        repo_over = repo_with_base_path(self.tmp / "over-repo", "over-base",
                                        "q" * (260 - 1 - len(str(root_over))))
        workflow = build(repo_ok, repo_over, root_ok, root_over,
                         bases=("ok-base", "over-base"))

        with self.fake_windows():
            problems = ohpreflight.workflow_problems(workflow, self.resolver)

        self.assertEqual(len(problems), 1, problems)
        self.assertIn("workspace 'long'", problems[0])
        self.assertRegex(problems[0],
                         r"gives a full path of 260, past the 259 Windows "
                         r"allows")

    def test_the_base_branch_supplies_the_tracked_paths(self):
        repo = repo_with_base_path(self.tmp / "repo", "long-base", "b" * 300)
        spaces = (Workspace("one", repo),)
        trees = (WorktreeSpec(name="wt", path=self.tmp / "wt", branch="out",
                              base="long-base", node_modules_mode="none",
                              workspace="one"),)
        step = Step(id="s1", kind="agent", worktree="wt", write_scope=("**",),
                    agent=AgentSpec(role="s1", brief="do the thing",
                                    model=FAKE_MODEL, harness_executor="pi"))
        workflow = Workflow(name="base-branch", workspaces=spaces,
                            worktrees=trees,
                            phases=(Phase("Build", (step,)),),
                            transient_backoff_s=0)

        with self.fake_windows():
            problems = ohpreflight.workflow_problems(workflow, self.resolver)

        self.assertEqual(len(problems), 1, problems)
        self.assertRegex(
            problems[0],
            r"workspace 'one' at .+repo: no core\.longpaths, and the "
            r"worktree root 'wt' \(\d+\) plus the longest tracked path "
            r"\(300\) gives a full path of \d+, past the 259 Windows allows")

    def test_another_platform_gets_no_fault(self):
        root_short, root_long = self.roots()
        workflow = build(self.repo_short, self.repo_long, root_short, root_long)
        other = SimpleNamespace(name="posix", environ=os.environ)
        with mock.patch.object(ohpreflight, "os", other):
            problems = ohpreflight.workflow_problems(workflow, self.resolver)
        self.assertEqual(problems, [])

    def test_a_workspace_that_sets_core_longpaths_passes(self):
        subprocess.run(["git", "-C", str(self.repo_long), "config",
                        "core.longpaths", "true"], check=True,
                       capture_output=True)
        root_short, root_long = self.roots()
        workflow = build(self.repo_short, self.repo_long, root_short, root_long)
        with self.fake_windows():
            problems = ohpreflight.workflow_problems(workflow, self.resolver)
        self.assertEqual(problems, [])

    def test_steps_that_run_on_another_machine_are_skipped(self):
        root_short, root_long = self.roots()
        workflow = build(self.repo_short, self.repo_long, root_short, root_long,
                         executors=("pi-cloud", "pi-cloud"))
        with self.fake_windows():
            problems = ohpreflight.workflow_problems(workflow, self.resolver)
        self.assertEqual(problems, [])

    def test_a_remote_step_skips_only_its_own_worktree(self):
        root_short, root_long = self.roots()
        workflow = build(self.repo_short, self.repo_long, root_short, root_long,
                         executors=("pi-cloud", "pi"))
        with self.fake_windows():
            problems = ohpreflight.workflow_problems(workflow, self.resolver)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("workspace 'long'", problems[0])

    def test_the_run_start_refuses_before_any_worktree_is_added(self):
        root_short, root_long = self.roots()
        workflow = build(self.repo_short, self.repo_long, root_short, root_long)
        engine = Engine(workflow, self.run_dir("r-long-paths"),
                        run_id="r-long-paths", dry_run=True, verbose=False,
                        harness_executors=self.resolver)
        with self.fake_windows():
            with self.assertRaises(PreflightError) as raised:
                engine.run()

        text = str(raised.exception)
        self.assertIn("workspace 'long'", text)
        self.assertIn("core.longpaths", text)
        self.assertTrue((self.run_dir("r-long-paths") / "workflow.json").exists())
        self.assertFalse((self.tmp / LONG_NAME).exists(),
                         "a worktree was added although preflight failed")
        self.assertFalse((self.tmp / "wt-short").exists())

    def test_the_preflight_verb_prints_the_failed_check(self):
        module = self.tmp / "workflow.py"
        module.write_text(WORKFLOW_PY, encoding="utf-8")
        with self.fake_windows():
            code, lines = call("preflight", "--workflow", module.as_posix(),
                               "--args", f"short={self.repo_short.as_posix()}",
                               "--args", f"long={self.repo_long.as_posix()}",
                               "--args", f"root={self.tmp.as_posix()}",
                               harness_executors=self.resolver)

        self.assertEqual(code, cli.EXIT_FAIL)
        self.assertRegex(lines[0], r"^PREFLIGHT FAIL: 1 of \d+ checks$")
        self.assertRegex(
            lines[1],
            r"^FAIL worktree path length: workspace 'long' at .+: no "
            r"core\.longpaths, and the worktree root 'long-wt' \(\d+\) plus "
            r"the longest tracked path \(9\) gives a full path of \d+, past "
            r"the 259 Windows allows; git -C <repo> config core\.longpaths "
            r"true$")
        self.assertEqual(len(lines), 2)


if __name__ == "__main__":
    import unittest
    unittest.main()

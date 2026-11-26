"""Workspaces: one workflow works on two repositories and on one workspace that
ohflow owns.

A workflow bound one repository: `Workflow.repo` was a single path, a worktree
named no repository, and preflight read that one repository. A change that
crossed two repositories, or work that is not code, had no place in one run.

A workflow now declares named workspaces and each worktree names its own. The
run below goes through the verbs an operator types: `validate`, `preflight`,
`run`, `revert`. Three agent steps commit, one in each workspace, and each later
step consumes the handover of the step before it across the workspace boundary.
"""

from __future__ import annotations

import json
import subprocess
import textwrap
from dataclasses import replace
from pathlib import Path

from ohflow import worktree as ohwt
from ohflow.coords import render_position
from ohflow.handover import questions
from ohflow.run_log import RunState
from ohflow.workflow import (AgentSpec, HandoverSpec, Phase, Step, Workflow,
                             WorkflowError, Workspace, WorktreeSpec,
                             from_jsonable, to_jsonable, validate)
from support import (FAKE_MODEL, AgentScript, FakeHarnessExecutor, TempCase,
                     agent_step, git_repo)
from verb_support import call

MODULE = """
from pathlib import Path
from ohflow.workflow import (AgentSpec, GateSpec, ModelConfig, Phase, Step,
                             Workflow, Workspace, WorktreeSpec,
                             clean_commit_checks)

MODEL = ModelConfig(model="fake/deterministic",
                    base_url="http://127.0.0.1:0/never-called",
                    api_key_env="OHFLOW_TEST_FAKE_KEY")


def build(args):
    root = Path(args["root"])
    spaces = (Workspace("code", Path(args["code"])),
              Workspace("docs", Path(args["docs"])),
              Workspace("notes", root / "notes", owned=True))

    def tree(name):
        return WorktreeSpec(name=name, path=root / "wt" / name,
                            branch=f"ohflow/{name}", base="main",
                            node_modules_mode="none", workspace=name)

    def agent(step_id, space, scope, consumes=()):
        return Step(id=step_id, kind="agent", worktree=space,
                    write_scope=(scope,), depends_on=consumes, consumes=consumes,
                    gate=GateSpec(clean_commit_checks((scope,))),
                    objective=f"commit one file in the {space} workspace",
                    agent=AgentSpec(role=step_id, brief="commit one file",
                                    model=MODEL, harness_executor="pi"))

    seen = " && ".join(f'test -d "{(root / "wt" / name).as_posix()}"'
                       for name in ("code", "docs", "notes"))
    return Workflow(
        name="three-substrates", workspaces=spaces,
        worktrees=tuple(tree(s.name) for s in spaces),
        phases=(
            Phase("Build", (agent("impl", "code", "src/**"),)),
            Phase("Document", (agent("doc", "docs", "src/**", ("impl",)),)),
            Phase("Record", (agent("note", "notes", "log/**", ("impl", "doc")),)),
            Phase("Check", (Step(id="see-all", kind="command", command=seen,
                                 execution_timeout_s=60),)),
        ),
        transient_backoff_s=0)
"""

FILES = {"impl": "src/feature.txt", "doc": "src/guide.md", "note": "log/run.md"}


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          text=True,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _handover(marker: str) -> str:
    return "\n\n".join(f"## {heading}\n[verified] {marker}"
                       for heading, _ in questions(HandoverSpec()))


class CommittingExecutor(FakeHarnessExecutor):
    """A fake agent that commits one file in the worktree the engine gave it."""

    def __init__(self, scripts: dict | None = None,
                 files: dict[str, str] | None = None) -> None:
        super().__init__(scripts if scripts is not None else {
            "impl": AgentScript(files={"handover.md": _handover("IMPL-TOKEN")}),
            "doc": AgentScript(files={"handover.md": _handover("DOC-TOKEN")}),
        })
        self.files = FILES if files is None else files
        self.worktrees: dict[str, Path] = {}

    def launch(self, spec: dict, out_dir: Path):
        self.worktrees[spec["coord"]] = Path(spec["workspace"])
        return super().launch(spec, out_dir)

    def collect(self, handle) -> dict:
        step_id = handle.coord.rsplit(".", 1)[-1]
        if not handle.collected and step_id in self.files:
            tree = self.worktrees[handle.coord]
            target = tree / self.files[step_id]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"written by {step_id}\n", encoding="utf-8")
            _git(tree, "add", "-A")
            _git(tree, "-c", "user.name=ohflow tests",
                 "-c", "user.email=tests@localhost", "commit", "-m",
                 f"Add {self.files[step_id]}")
        return super().collect(handle)


class ThreeSubstratesEndToEnd(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.code = git_repo(self.tmp / "code")
        self.docs = git_repo(self.tmp / "docs")
        self.root = self.tmp / "out"
        self.notes = self.root / "notes"
        self.module = self.tmp / "three_substrates.py"
        self.module.write_text(textwrap.dedent(MODULE), encoding="utf-8")
        self.fake = CommittingExecutor()

    def verb(self, name: str, *extra):
        return call(name, "--workflow", self.module.as_posix(),
                    "--args", f"root={self.root.as_posix()}",
                    "--args", f"code={self.code.as_posix()}",
                    "--args", f"docs={self.docs.as_posix()}", *extra,
                    harness_executors=lambda _name: self.fake)

    def test_validate_preflight_run_and_revert_cover_every_workspace(self):
        code, lines = self.verb("validate")
        self.assertEqual(code, 0, lines)
        self.assertRegex(lines[0], r"^VALID three-substrates: 4 phases, 4 steps; "
                                   r"harness executors pi:3; 3 workspaces$")

        code, lines = self.verb("preflight")
        self.assertEqual(code, 0, lines)
        self.assertRegex(lines[0], r"^PREFLIGHT PASS: \d+ checks$")
        self.assertFalse(self.notes.exists())

        (self.docs / "README.md").write_text("an edit nobody committed\n",
                                             encoding="utf-8")
        code, lines = self.verb("preflight")
        self.assertEqual(code, 1, lines)
        self.assertIn("FAIL clean tree: workspace 'docs' tree is dirty",
                      "\n".join(lines))
        _git(self.docs, "checkout", "--", "README.md")

        runs = self.tmp / "runs"
        code, lines = self.verb("run", "--out", runs.as_posix(),
                                "--run-id", "r-three", "--no-dashboard")
        self.assertEqual(code, 0, lines)
        self.assertRegex(lines[-1], r"^Run r-three finished: 4 of 4 agents passed")
        run_dir = runs / "r-three"

        for name, repo in (("code", self.code), ("docs", self.docs),
                           ("notes", self.notes)):
            step_id = {"code": "impl", "docs": "doc", "notes": "note"}[name]
            shown = _git(repo, "show", f"ohflow/{name}:{FILES[step_id]}")
            self.assertEqual(shown.stdout, f"written by {step_id}\n", name)
            ahead = _git(repo, "rev-list", "--count", f"main..ohflow/{name}")
            self.assertEqual(ahead.stdout.strip(), "1", name)
            self.assertTrue((self.root / "wt" / name).is_dir(), name)
        root_commit = _git(self.notes, "log", "--format=%s", "main").stdout
        self.assertEqual(root_commit.strip(), "Start workspace notes")

        brief = next(run_dir.glob("phases/*/*doc/attempts/01/brief.md")).read_text(
            encoding="utf-8")
        self.assertIn("IMPL-TOKEN", brief)
        self.assertIn("Other workspaces of this run", brief)
        self.assertIn("its work: workspace `code`", brief)
        self.assertIn(str(self.root / "wt" / "code"), brief)
        note_brief = next(run_dir.glob(
            "phases/*/*note/attempts/01/brief.md")).read_text(encoding="utf-8")
        self.assertIn("IMPL-TOKEN", note_brief)
        self.assertIn("DOC-TOKEN", note_brief)

        recorded = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        self.assertEqual([w["name"] for w in recorded["workspaces"]],
                         ["code", "docs", "notes"])
        self.assertEqual({w["workspace"] for w in recorded["worktrees"].values()},
                         {"code", "docs", "notes"})
        plan = ohwt.read_revert_plan(run_dir)
        self.assertEqual(len({entry["repo"] for entry in plan["worktrees"]}), 3)

        code, lines = call("revert", "--run", run_dir.as_posix())
        self.assertEqual(code, 0, lines)
        text = "\n".join(lines)
        for name, repo in (("code", self.code), ("docs", self.docs),
                           ("notes", self.notes)):
            self.assertIn(f"worktree {name} in workspace {name}: removed", text)
            self.assertIn(f"branch ohflow/{name} in workspace {name}: deleted", text)
            self.assertFalse((self.root / "wt" / name).exists(), name)
            self.assertEqual(_git(repo, "branch", "--list", "ohflow/*").stdout, "")
            self.assertEqual(len(_git(repo, "worktree", "list").stdout
                                 .splitlines()), 1, name)
        self.assertTrue(ohwt.is_git(self.notes))


class WorkspaceValidation(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.a, self.b = self.tmp / "a", self.tmp / "b"

    def spaces(self, **owned):
        return (Workspace("a", self.a), Workspace("b", self.b),
                Workspace("own", self.tmp / "own", owned=True, **owned))

    def tree(self, name: str, space: str | None, **kw) -> WorktreeSpec:
        return WorktreeSpec(name=name, path=self.tmp / "wt" / name,
                            branch=f"ohflow/{name}", base="main",
                            node_modules_mode="none", workspace=space, **kw)

    def step(self, step_id: str, worktree: str | None, scope: str = "src/**") -> Step:
        return replace(agent_step(step_id), worktree=worktree, write_scope=(scope,))

    def workflow(self, steps, trees, **kw) -> Workflow:
        kw.setdefault("workspaces", self.spaces())
        return Workflow(name="w", worktrees=tuple(trees),
                        phases=(Phase("P", tuple(steps)),), **kw)

    def problems(self, workflow: Workflow) -> str:
        with self.assertRaises(WorkflowError) as caught:
            validate(workflow)
        return "\n".join(caught.exception.problems)

    def test_two_steps_own_the_same_paths_in_two_workspaces(self):
        workflow = self.workflow(
            [self.step("one", "ta"), self.step("two", "tb")],
            [self.tree("ta", "a"), self.tree("tb", "b")])
        self.assertEqual(validate(workflow).workspace_of("tb").name, "b")
        same = self.workflow(
            [self.step("one", "ta"), self.step("two", "ta2")],
            [self.tree("ta", "a"), self.tree("ta2", "a")])
        self.assertIn("both own", self.problems(same))

    def test_a_worktree_names_a_declared_workspace(self):
        self.assertIn("worktree 'ta': undeclared workspace 'nowhere'",
                      self.problems(self.workflow(
                          [self.step("one", "ta")], [self.tree("ta", "nowhere")])))
        self.assertIn("worktree 'ta' names no workspace; the workflow has 3: "
                      "a, b, own",
                      self.problems(self.workflow(
                          [self.step("one", "ta")], [self.tree("ta", None)])))

    def test_repo_and_workspaces_are_one_or_the_other(self):
        both = self.workflow([self.step("one", "ta")], [self.tree("ta", "a")],
                             repo=self.tmp / "elsewhere")
        self.assertIn("sets both repo= and workspaces=", self.problems(both))
        neither = Workflow(name="w", phases=(Phase("P", (self.step("one", None),)),))
        self.assertIn("names no workspace", self.problems(neither))
        twice = self.workflow([self.step("one", "ta")], [self.tree("ta", "a")],
                              workspaces=(Workspace("a", self.a),
                                          Workspace("a", self.b)))
        self.assertIn("workspace 'a' is declared twice", self.problems(twice))
        one_path = self.workflow([self.step("one", "ta")], [self.tree("ta", "a")],
                                 workspaces=(Workspace("a", self.a),
                                             Workspace("b", self.a)))
        self.assertIn("name one path", self.problems(one_path))

    def test_a_branch_merges_only_inside_its_workspace(self):
        merge = Step(id="land", kind="merge", worktree="tb",
                     merge_branch="ohflow/ta")
        text = self.problems(self.workflow(
            [merge], [self.tree("ta", "a"), self.tree("tb", "b")]))
        self.assertIn("merges branch 'ohflow/ta' of workspace a into workspace b",
                      text)

    def test_an_owned_workspace_has_no_node_modules_and_no_cloud_step_without_a_remote(self):
        linked = replace(self.tree("to", "own"), node_modules_mode="junction")
        self.assertIn("owned by ohflow and holds no node_modules",
                      self.problems(self.workflow([self.step("one", "to")], [linked])))
        cloud = self.step("one", "to")
        cloud = replace(cloud, agent=replace(cloud.agent,
                                             harness_executor="pi-cloud"))
        self.assertIn("which ohflow owns and which has no remote",
                      self.problems(self.workflow([cloud], [self.tree("to", "own")])))
        with_remote = self.workflow(
            [cloud], [self.tree("to", "own")],
            workspaces=self.spaces(remote="git@example.invalid:me/own.git"))
        self.assertNotIn("no remote", "\n".join(
            self._problems_or_none(with_remote)))

    def _problems_or_none(self, workflow: Workflow) -> list[str]:
        try:
            validate(workflow)
        except WorkflowError as error:
            return list(error.problems)
        return []

    def test_the_one_repo_form_is_one_workspace_named_after_the_folder(self):
        workflow = Workflow(name="w", repo=self.tmp / "project",
                            base_branch="trunk", baseline_cmd="true",
                            phases=(Phase("P", (self.step("one", None),)),))
        (space,) = workflow.all_workspaces()
        self.assertEqual((space.name, space.path, space.base_branch,
                          space.baseline_cmd, space.owned),
                         ("project", self.tmp / "project", "trunk", "true", False))
        self.assertEqual(workflow.workspace_of(None), space)

    def test_a_declared_workflow_reads_repo_as_its_first_workspace(self):
        workflow = self.workflow(
            [self.step("one", "tb")], [self.tree("tb", "b")],
            workspaces=(Workspace("a", self.a, base_branch="trunk"),
                        Workspace("b", self.b)))
        self.assertEqual((workflow.repo, workflow.base_branch), (self.a, "trunk"))
        back = from_jsonable(json.loads(json.dumps(to_jsonable(workflow))))
        self.assertEqual(back.all_workspaces(), workflow.all_workspaces())
        self.assertEqual(back.worktree("tb").workspace, "b")

    def test_the_pilot_renames_a_base_only_inside_its_workspace(self):
        from ohflow import pilot
        from ohflow.workflow import Unit, UnitPath
        shared = "feat/shared"
        trees = [replace(self.tree("ta", "a"), branch=shared),
                 replace(self.tree("ta2", "a"), base=shared),
                 replace(self.tree("tb", "b"), base=shared)]
        steps = [replace(self.step(name, name, scope), unit="u")
                 for name, scope in (("ta", "x/**"), ("ta2", "y/**"), ("tb", "x/**"))]
        workflow = validate(replace(
            self.workflow(steps[:1], trees), paths=(UnitPath("p"),),
            units=(Unit("u", "p"),),
            phases=(Phase("One", (steps[0],)), Phase("Two", tuple(steps[1:])))))
        piloted = validate(pilot.pilot_workflow(workflow))
        self.assertEqual(piloted.worktree("ta").branch, shared + pilot.SUFFIX)
        self.assertEqual(piloted.worktree("ta2").base, shared + pilot.SUFFIX)
        self.assertEqual(piloted.worktree("tb").base, shared)
        self.assertEqual(piloted.worktree("tb").workspace, "b")

    def test_one_workspace_keeps_the_position_block_it_had(self):
        single = Workflow(name="w", repo=self.a,
                          phases=(Phase("P", (self.step("one", None),)),))
        text = render_position(single, RunState(), single.step_by_id("one")[3])
        self.assertNotIn("workspace", text.lower())
        several = self.workflow([self.step("one", "ta")], [self.tree("ta", "a")])
        text = render_position(several, RunState(), several.step_by_id("one")[3])
        self.assertIn("are in workspace `a` alone", text)
        self.assertIn("own - ", text)
        self.assertIn("owned by ohflow", text)
        self.assertIn("You may read them. Write nothing there.", text)


class OwnedWorkspace(TempCase):

    def test_the_run_creates_it_once_and_sets_its_origin(self):
        bare = self.tmp / "remote.git"
        subprocess.run(["git", "init", "--bare", str(bare)], capture_output=True,
                       check=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        space = Workspace("notes", self.tmp / "notes", base_branch="trunk",
                          owned=True, remote=bare.as_posix())
        self.assertEqual(ohwt.workspace_faults(space), [])
        said = ohwt.ensure_workspace(space)
        self.assertIn("created", said)
        self.assertIn("origin set", said)
        self.assertEqual(_git(space.path, "rev-parse", "--abbrev-ref",
                              "HEAD").stdout.strip(), "trunk")
        self.assertEqual(_git(space.path, "remote", "get-url",
                              "origin").stdout.strip(), bare.as_posix())
        self.assertIsNone(ohwt.ensure_workspace(space))
        self.assertEqual(_git(space.path, "rev-list", "--count",
                              "HEAD").stdout.strip(), "1")

    def test_a_folder_that_holds_files_is_refused(self):
        folder = self.tmp / "taken"
        folder.mkdir()
        (folder / "report.docx").write_text("not ohflow's", encoding="utf-8")
        space = Workspace("taken", folder, owned=True)
        self.assertIn("holds files and no git repository",
                      ohwt.workspace_faults(space)[0])
        with self.assertRaises(RuntimeError):
            ohwt.ensure_workspace(space)
        self.assertFalse(ohwt.is_git(folder))
        self.assertEqual(ohwt.workspace_faults(Workspace("code", folder)),
                         [f"not a git repository: {folder}"])

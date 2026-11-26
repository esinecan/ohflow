"""A campaign lands a milestone in every workspace it wrote in.

A campaign bound one product repository: `Campaign.repo` held the one
integration branch, and a milestone whose workflow wrote in a second
repository left that branch where it was. Nothing above the workflow run
joined the two.

A campaign now declares workspaces, and each workspace has its own
integration branch of the campaign's one name. On PASS the controller moves
the integration branch of each workspace where the milestone's workflow has a
worktree on the output branch. It checks every workspace before it moves any
branch, so a refusal in one leaves all of them where they were.

The run below goes through `campaign validate` and `campaign run`, with two
real repositories, one owned workspace and agents that commit.
"""

from __future__ import annotations

import json
import textwrap
from dataclasses import replace
from pathlib import Path

from ohflow import campaign as oc
from ohflow import worktree as ohwt
from ohflow.workflow import (AgentSpec, Phase, Step, Workflow, Workspace,
                             WorktreeSpec, validate)
from support import FAKE_MODEL, AgentScript, TempCase, git_repo, quiet
from test_workspaces_01_three_substrates import CommittingExecutor
from verb_support import call

JUDGE_STEP = "01.judge/01.judge"
BRANCH = "integration-branch"

CAMPAIGN_PY = """
from pathlib import Path
from ohflow.campaign import AcceptanceCheck, Campaign, Milestone
from ohflow.workflow import AgentSpec, ModelConfig, Workspace

MODEL = ModelConfig(model="fake/deterministic",
                    base_url="http://127.0.0.1:0/never-called",
                    api_key_env="OHFLOW_TEST_FAKE_KEY")


def build(args):
    root = Path(__file__).resolve().parent
    spaces = (Workspace("api", Path(args["api"])),
              Workspace("docs", Path(args["docs"])),
              Workspace("notes", Path(args["notes"]), owned=True))

    def milestone(mid, writes, checks=()):
        return Milestone(
            id=mid, title=f"milestone {mid}",
            workflow=f"milestones/{mid}/workflow.py",
            spec=f"milestones/{mid}/spec.md", output_branch=f"{mid}/out",
            acceptance_checks=checks,
            args={"api": args["api"], "docs": args["docs"],
                  "trees": args["trees"], "writes": writes})

    checks = (AcceptanceCheck("api-file", "test -f src/m1-api.txt"),
              AcceptanceCheck("docs-file", "test -f src/m1-docs.txt",
                              cwd="land:docs"),
              AcceptanceCheck("docs-repo",
                              "git rev-parse --verify integration-branch",
                              cwd="repo:docs"))
    judge = AgentSpec(harness_executor="pi", role="milestone-judge", brief="",
                      model=MODEL, max_iterations=5)
    return Campaign(name="two-repos", root=root, charter="charter.md",
                    workspaces=spaces,
                    milestones=(milestone("m1", "api+docs", checks),
                                milestone("m2", "docs")),
                    integration_branch="integration-branch", judge=judge,
                    auto_resume=0)
"""

WORKFLOW_PY = """
from pathlib import Path
from ohflow.workflow import (AgentSpec, GateSpec, ModelConfig, Phase, Step,
                             Workflow, Workspace, WorktreeSpec,
                             clean_commit_checks)

MODEL = ModelConfig(model="fake/deterministic",
                    base_url="http://127.0.0.1:0/never-called",
                    api_key_env="OHFLOW_TEST_FAKE_KEY")


def build(args):
    mid = args["milestone"]
    names = args["writes"].split("+")
    trees = Path(args["trees"]) / mid
    spaces = tuple(Workspace(n, Path(args[n])) for n in ("api", "docs"))
    worktrees = tuple(
        WorktreeSpec(name=n, path=trees / n, branch=f"{mid}/out",
                     base=args["integration_branch"], node_modules_mode="none",
                     workspace=n) for n in names)
    steps = tuple(
        Step(id=f"{mid}-{n}", kind="agent", worktree=n, write_scope=("src/**",),
             gate=GateSpec(clean_commit_checks(("src/**",))),
             objective=f"commit one file in the {n} workspace",
             agent=AgentSpec(role=f"{mid}-{n}", brief="commit one file",
                             model=MODEL, harness_executor="pi"))
        for n in names)
    return Workflow(name=f"{mid}-workflow", workspaces=spaces,
                    worktrees=worktrees, phases=(Phase("Build", steps),),
                    transient_backoff_s=0)
"""

FILES = {"m1-api": "src/m1-api.txt", "m1-docs": "src/m1-docs.txt",
         "m2-docs": "src/m2-docs.txt"}
PASS = {"decision": "PASS", "summary": "PASS summary", "findings": [],
        "revisions": [], "question_for_operator": None}


def _git(cwd: Path, *args: str) -> str:
    return oc._git(cwd, *args)


class TwoRepoCase(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.api = git_repo(self.tmp / "api")
        self.docs = git_repo(self.tmp / "docs")
        self.notes = self.tmp / "notes"
        self.root = git_repo(self.tmp / "camp")
        (self.root / "charter.md").write_text("# Charter\n\nShip it.\n",
                                              encoding="utf-8")
        (self.root / "campaign.py").write_text(textwrap.dedent(CAMPAIGN_PY),
                                               encoding="utf-8")
        for mid in ("m1", "m2"):
            mdir = self.root / "milestones" / mid
            mdir.mkdir(parents=True)
            (mdir / "spec.md").write_text(f"# {mid}\n", encoding="utf-8")
            (mdir / "workflow.py").write_text(textwrap.dedent(WORKFLOW_PY),
                                              encoding="utf-8")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-m", "campaign inputs")

    def args(self) -> list[str]:
        pairs = {"api": self.api, "docs": self.docs, "notes": self.notes,
                 "trees": self.tmp / "trees"}
        out = ["--campaign", (self.root / "campaign.py").as_posix()]
        for key, path in pairs.items():
            out += ["--args", f"{key}={path.as_posix()}"]
        return out

    def judge(self) -> AgentScript:
        script = AgentScript(final_text="```json\n" + json.dumps(PASS) + "\n```\n",
                             structured=PASS)

        def act():
            mid = ("m1", "m2")[min(script.launches, 2) - 1]
            handover = (self.root / "milestones" / mid / "judge" / "r01"
                        / "judge-handover.md")
            handover.parent.mkdir(parents=True, exist_ok=True)
            handover.write_text("# handover\n\nPASS.\n", encoding="utf-8")
            return None

        script.on_poll = act
        return script

    def packet(self, mid: str) -> str:
        return (self.root / "milestones" / mid / "judge" / "r01"
                / "packet.md").read_text(encoding="utf-8")


class AMilestoneLandsInEveryWorkspaceItWroteIn(TwoRepoCase):

    def test_campaign_validate_and_run_land_two_milestones(self):
        code, lines = call("campaign", "validate", *self.args())
        self.assertEqual((code, lines), (0, ["CAMPAIGN OK"]))

        fake = CommittingExecutor({JUDGE_STEP: self.judge()}, FILES)
        api_base = oc._rev(self.api, "main")
        docs_base = oc._rev(self.docs, "main")
        code, lines = call("campaign", "run", *self.args(), "--no-dashboard",
                           harness_executors=lambda _name: fake)
        text = "\n".join(lines)
        self.assertEqual(code, oc.EXIT_DELIVERED, text)

        api_m1 = oc._rev(self.api, "m1/out")
        docs_m1 = oc._rev(self.docs, "m1/out")
        docs_m2 = oc._rev(self.docs, "m2/out")
        notes_root = oc._rev(self.notes, "main")
        self.assertNotIn(None, (api_m1, docs_m1, docs_m2, notes_root))
        self.assertNotEqual(api_m1, api_base)
        self.assertEqual(oc._rev(self.api, BRANCH), api_m1)
        self.assertEqual(oc._rev(self.docs, BRANCH), docs_m2)
        self.assertEqual(oc._rev(self.notes, BRANCH), notes_root)
        self.assertIsNone(oc._rev(self.api, "m2/out"))
        self.assertEqual(_git(self.api, "show", f"{BRANCH}:src/m1-api.txt"),
                         "written by m1-api")
        for name in ("src/m1-docs.txt", "src/m2-docs.txt"):
            self.assertTrue(_git(self.docs, "show", f"{BRANCH}:{name}"), name)
        self.assertEqual(oc._rev(self.api, "main"), api_base)
        self.assertEqual(oc._rev(self.docs, "main"), docs_base)

        events = oc.CampaignLog(self.root).events()
        landed = {e["milestone"]: e["workspaces"] for e in events
                  if e["event"] == "milestone_landed"}
        self.assertEqual(landed["m1"], {
            "api": {"before": api_base, "after": api_m1},
            "docs": {"before": docs_base, "after": docs_m1},
            "notes": {"before": notes_root, "after": notes_root}})
        self.assertEqual(landed["m2"], {
            "api": {"before": api_m1, "after": api_m1},
            "docs": {"before": docs_m1, "after": docs_m2},
            "notes": {"before": notes_root, "after": notes_root}})
        started = next(e for e in events if e["event"] == "campaign_started")
        self.assertEqual(started["integration_sha"], api_base)
        self.assertEqual(started["integration_shas"],
                         {"api": api_base, "docs": docs_base, "notes": notes_root})

        first = self.packet("m1")
        self.assertIn("each has its own integration branch", first)
        self.assertIn("The milestone lands in `api`, `docs`.", first)
        self.assertIn("## The product change in workspace `api`", first)
        self.assertIn("## The product change in workspace `docs`", first)
        self.assertIn("owned by ohflow", first)
        for check in ("api-file", "docs-file", "docs-repo"):
            self.assertIn(f"### {check}: exit 0", first)
        second = self.packet("m2")
        self.assertIn("The milestone lands in `docs`.", second)
        self.assertNotIn("## The product change in workspace `api`", second)

        self.assertIn("workspace notes: created", text)
        self.assertIn(f"m1: PASS; integration branch at api {api_m1[:10]}, "
                      f"docs {docs_m1[:10]}, notes {notes_root[:10]}", text)
        self.assertIn(f"delivered: integration branch {BRANCH} at "
                      f"api {api_m1[:10]}, docs {docs_m2[:10]}", text)


class ARefusalInOneWorkspaceMovesNoBranch(TwoRepoCase):

    def commit(self, repo: Path, branch: str, base: str) -> str:
        _git(repo, "checkout", "-q", "-b", branch, base)
        (repo / f"{branch.replace('/', '-')}.txt").write_text("work\n",
                                                              encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", f"work on {branch}")
        sha = _git(repo, "rev-parse", "HEAD")
        _git(repo, "checkout", "-q", "main")
        return sha

    def test_an_output_branch_that_drops_work_in_docs_leaves_api_alone(self):
        camp = oc.load_campaign(self.root / "campaign.py", {
            "api": str(self.api), "docs": str(self.docs),
            "notes": str(self.notes), "trees": str(self.tmp / "trees")})
        api_base = oc._rev(self.api, "main")
        _git(self.api, "branch", BRANCH, "main")
        self.commit(self.api, "m1/out", BRANCH)
        moved = self.commit(self.docs, BRANCH, "main")
        self.commit(self.docs, "m1/out", "main")
        api, docs, _notes = camp.all_workspaces()
        with quiet():
            controller = oc.CampaignController(camp, no_dashboard=True,
                                               say=lambda _m: None)
            ohwt.ensure_workspace(camp.all_workspaces()[2])
            controller._ensure_integration_branch()
            code = controller._land(camp.milestones[0],
                                    [(api, None), (docs, None)])
        self.assertEqual(code, oc.EXIT_ESCALATED)
        self.assertEqual(oc._rev(self.api, BRANCH), api_base)
        self.assertEqual(oc._rev(self.docs, BRANCH), moved)
        why = (self.root / oc.ESCALATION).read_text(encoding="utf-8")
        self.assertIn("m1/out does not contain integration branch "
                      "integration-branch in workspace docs", why)


class CampaignWorkspaceValidation(TwoRepoCase):

    def campaign(self, **kw) -> oc.Campaign:
        base = oc.load_campaign(self.root / "campaign.py", {
            "api": str(self.api), "docs": str(self.docs),
            "notes": str(self.notes), "trees": str(self.tmp / "trees")})
        return replace(base, **kw)

    def workflow(self, trees: list[WorktreeSpec], spaces) -> Workflow:
        step = Step(id="s", kind="command", command="true", worktree=trees[0].name)
        return validate(Workflow(name="w", workspaces=tuple(spaces),
                                 worktrees=tuple(trees),
                                 phases=(Phase("P", (step,)),)))

    def tree(self, name: str, space: str, branch: str = "m1/out") -> WorktreeSpec:
        return WorktreeSpec(name=name, path=self.tmp / "wt" / name, branch=branch,
                            base="main", node_modules_mode="none", workspace=space)

    def test_repo_beside_workspaces_and_a_missing_repository_are_refused(self):
        both = self.campaign(repo=self.tmp / "elsewhere")
        self.assertIn("campaign sets both repo= and workspaces=",
                      "\n".join(oc.validate_campaign(both)))
        gone = self.campaign(workspaces=(Workspace("api", self.api),
                                         Workspace("lost", self.tmp / "lost")),
                             repo=None)
        self.assertIn("workspace 'lost' is not a git repository",
                      "\n".join(oc.validate_campaign(gone)))
        m = self.campaign().milestones[0]
        named = replace(m, acceptance_checks=(
            oc.AcceptanceCheck("c", "true", cwd="land:nowhere"),))
        self.assertIn("names workspace 'nowhere', which the campaign does not "
                      "declare",
                      "\n".join(oc.validate_campaign(
                          self.campaign(milestones=(named,)))))

    def test_one_repository_is_one_workspace_on_the_integration_base(self):
        m = self.campaign().milestones[0]
        single = oc.Campaign(name="one", root=self.root, repo=self.api,
                             charter="charter.md", milestones=(m,),
                             integration_branch=BRANCH, integration_base="trunk")
        (space,) = single.all_workspaces()
        self.assertEqual((space.name, space.path, space.base_branch),
                         ("api", self.api, "trunk"))
        flow = self.workflow([self.tree("anywhere", "x")],
                             [Workspace("x", self.docs)])
        self.assertEqual(oc.milestone_problems(single, m, flow), [])
        self.assertEqual(oc.milestone_landings(single, m, flow),
                         [(space, self.tmp / "wt" / "anywhere")])

    def test_a_milestone_must_land_in_a_workspace_of_the_campaign(self):
        camp = self.campaign()
        m = camp.milestones[0]
        api, docs, _notes = camp.all_workspaces()
        other = git_repo(self.tmp / "other")
        outside = self.workflow(
            [self.tree("a", "api"), self.tree("o", "other")],
            [Workspace("api", self.api), Workspace("other", other)])
        self.assertIn("worktree 'o' holds the output branch 'm1/out'",
                      "\n".join(oc.milestone_problems(camp, m, outside)))
        nowhere = self.workflow([self.tree("a", "api", branch="scratch")],
                                [Workspace("api", self.api),
                                 Workspace("docs", self.docs)])
        self.assertIn("so the milestone would land nowhere",
                      "\n".join(oc.milestone_problems(camp, m, nowhere)))
        both = self.workflow(
            [self.tree("a", "code"), self.tree("d", "manual")],
            [Workspace("code", self.api), Workspace("manual", self.docs)])
        self.assertEqual(oc.milestone_problems(camp, m, both), [])
        self.assertEqual(oc.milestone_landings(camp, m, both),
                         [(api, self.tmp / "wt" / "a"),
                          (docs, self.tmp / "wt" / "d")])

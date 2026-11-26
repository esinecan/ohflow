"""A campaign: milestones in order, each one run, judged and revised.

One ohflow workflow run delivers one milestone. A campaign is the level above it.
It runs the milestone's workflow, runs the milestone's acceptance checks itself, writes
a handover packet, and starts a fresh judge agent that reads the packet. The
judge returns one of three decisions:

- PASS: the controller moves the campaign integration branch to the milestone's output branch and
  starts the next milestone.
- REVISE: the judge has changed the milestone's inputs (briefs, workflow module,
  snippets). The controller commits that change in the campaign repository and
  resumes the same run. Fingerprints decide which steps run again.
- ESCALATE: a decision belongs to the operator. The controller writes ESCALATION.md and
  stops.

The judge never needs the session that wrote the campaign. Everything it needs
is in the packet: the charter, the milestone spec, what ran, the evidence, and
the lineage of earlier decisions, revisions and judge handovers. That packet is
the handover this module exists to make.

Every decision the controller takes is mechanical and recorded in the campaign log in
`campaign.jsonl`. Every change to an input is one git commit in the campaign
repository, so a bad outcome traces back to the revision that caused it.
"""

from __future__ import annotations

import datetime as _dt
import importlib.util
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import estimate as ohestimate
from . import check_passes, exec as ohexec, proc, rundir, settings
from . import worktree as ohwt
from .coords import coord
from .gates import BASE, with_base
from .handover import CORE
from .paths import posix, python_cmd, win
from .workflow import (CheckSpec, GateSpec, ModelConfig, Phase, Workflow, WorkflowArgs,
                       WorkflowError, Workspace, RetryPolicy, Step, AgentSpec,
                       load_workflow, validate)
from .supervisor import RunOptions, RunOutcome, go_command, run_workflow

#: Paths inside a milestone directory that the controller writes and git ignores.
GENERATED_DIRS = ("runs", "judge")
#: Inputs a judge may never change: they are the target, not the round.
FROZEN_INPUTS = ("spec.md",)
CONTRACTS = "contracts.md"
CAMPAIGN_LOG = "campaign.jsonl"
STATUS = "campaign-status.json"
ESCALATION = "ESCALATION.md"
PID_FILE = "campaign.pid"

#: Exit codes of `ohflow campaign run`.
EXIT_DELIVERED = 0
EXIT_FAILED = 1
EXIT_ESCALATED = 3

DECISION_SCHEMA: dict = {
    "type": "object",
    "required": ["decision", "summary", "findings", "revisions"],
    "properties": {
        "decision": {"type": "string", "enum": ["PASS", "REVISE", "ESCALATE"]},
        "summary": {"type": "string"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["severity", "what", "evidence"],
                "properties": {
                    "severity": {"type": "string",
                                 "enum": ["blocking", "major", "minor"]},
                    "where": {"type": "string"},
                    "what": {"type": "string"},
                    "evidence": {"type": "string"},
                    "cause": {"type": "string",
                              "enum": ["brief", "distribution", "tool_policy",
                                       "gate", "spec", "product"]},
                },
            },
        },
        "revisions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["path", "why"],
                "properties": {"path": {"type": "string"},
                               "why": {"type": "string"}},
            },
        },
        "question_for_operator": {"type": ["string", "null"]},
    },
}

def judge_model() -> str:
    """The tier or model of the default judge, from `campaign.judge_model`.

    The base value is the tier `heavy`, which the `claude` harness executor
    resolves through `tiers.heavy.claude` when the judge starts. A value that
    is not a non-empty string raises `SettingsError` here, when the campaign
    is built, and not after a milestone's run was paid for."""
    value = settings.get("campaign.judge_model", "heavy")
    if not isinstance(value, str) or not value.strip():
        raise settings.SettingsError(
            f"the setting campaign.judge_model must name a model or a tier in a "
            f"non-empty string, got {value!r}; correct it in the operator "
            f"settings, or name a judge in the campaign")
    return value


def default_judge() -> AgentSpec:
    """The default judge: a fresh agent on the judge's tier or model at high effort, in the
    signed-in harness's usual setup, so it has the operator's memory and the
    full fleet. The format of its handover is in `JUDGE_ROLE`."""
    return AgentSpec(
        role="milestone-judge",
        brief="",
        harness_executor="claude",
        model=ModelConfig(model=judge_model(), base_url="", api_key_env="",
                          params={"effort": "high"}),
        max_iterations=400,
    )


# ------------------------------------------------------------------ authoring


@dataclass(frozen=True)
class AcceptanceCheck:
    """One command the controller runs itself after a milestone run.

    `cwd` is `land` (the worktree that checks out the milestone's output
    branch), `repo` (the product repository) or an absolute path. In a campaign
    with several workspaces, `land` and `repo` mean the default workspace's,
    and `land:<workspace>` and `repo:<workspace>` name another one's.
    """
    name: str
    cmd: str
    cwd: str = "land"
    shell: str = "sh"
    timeout_s: int = 1800


@dataclass(frozen=True)
class Milestone:
    id: str
    title: str
    #: Paths relative to the campaign root.
    workflow: str
    spec: str
    #: The branch the milestone's workflow leaves its finished work on. On PASS
    #: the campaign integration branch fast-forwards to it. None: landing records
    #: the acceptance and leaves the integration branch where it is. In a
    #: campaign with several workspaces it is one name: the milestone lands in
    #: every workspace where its workflow has a worktree on this branch.
    output_branch: str | None = None
    acceptance_checks: tuple[AcceptanceCheck, ...] = ()
    args: Mapping[str, str] = field(default_factory=dict)
    #: None takes the campaign's value.
    max_revisions: int | None = None
    judge: AgentSpec | None = None

    @property
    def dir(self) -> str:
        return str(Path(self.workflow).parent).replace("\\", "/")


@dataclass(frozen=True)
class Campaign:
    """`repo` and `integration_base` are the one-repository form. A campaign
    that lands in several repositories sets `workspaces` and leaves `repo`
    unset; `repo` then reads as the first workspace's path."""
    name: str
    root: Path                     # the campaign repository
    repo: Path | None = field(default=None, kw_only=True)   # the product repository
    charter: str                   # path relative to root
    milestones: tuple[Milestone, ...]
    #: The branch that accumulates passed milestones. Every workspace has its
    #: own branch of this name. Created the first time at `integration_base`,
    #: or at each workspace's `base_branch` when the campaign sets `workspaces`.
    integration_branch: str
    integration_base: str = "main"
    judge: AgentSpec = field(default_factory=default_judge)
    judge_execution_timeout_s: int = 7200
    max_revisions: int = 2
    #: Run with `{file}` replaced by the escalation file's path. Use it to
    #: reach the operator, for example a chat message or an issue.
    on_escalate: str | None = None
    #: Passed to every milestone run as `--auto-resume`.
    auto_resume: int = 2
    contracts: str | None = None
    workspaces: tuple[Workspace, ...] = ()

    def __post_init__(self) -> None:
        first = self.workspaces[0] if self.workspaces else None
        if isinstance(first, Workspace) and self.repo is None:
            object.__setattr__(self, "repo", Path(first.path))

    def all_workspaces(self) -> tuple[Workspace, ...]:
        """Every workspace the campaign lands in, the default one first.
        `repo` and `integration_base` alone declare one workspace."""
        if self.workspaces:
            return tuple(self.workspaces)
        if self.repo is None:
            return ()
        return (Workspace(name=Path(self.repo).name or "repo",
                          path=Path(self.repo),
                          base_branch=self.integration_base),)


def _same_path(a: Path, b: Path) -> bool:
    return (os.path.normcase(str(Path(a).resolve()))
            == os.path.normcase(str(Path(b).resolve())))


def milestone_landings(camp: Campaign, m: Milestone, workflow: Workflow
                       ) -> list[tuple[Workspace, Path | None]]:
    """Where a milestone lands: each workspace of the campaign in which the
    workflow has a worktree on the output branch, with that worktree's path.
    A campaign with one workspace lands there whatever the workflow declares."""
    if not m.output_branch:
        return []
    spaces = camp.all_workspaces()
    on_branch = [w for w in workflow.worktrees if w.branch == m.output_branch]
    if len(spaces) == 1:
        return [(spaces[0], Path(on_branch[0].path) if on_branch else None)]
    out = []
    for space in spaces:
        for w in on_branch:
            if _same_path(workflow.workspace_of(w.name).path, space.path):
                out.append((space, Path(w.path)))
                break
    return out


def milestone_problems(camp: Campaign, m: Milestone, workflow: Workflow
                       ) -> list[str]:
    """Why a milestone's workflow cannot land in the campaign's workspaces.
    A campaign with one workspace has no such problem."""
    spaces = camp.all_workspaces()
    if len(spaces) < 2 or not m.output_branch:
        return []
    out = []
    for w in workflow.worktrees:
        if w.branch != m.output_branch:
            continue
        home = workflow.workspace_of(w.name)
        if not any(_same_path(home.path, space.path) for space in spaces):
            out.append(f"{m.id}: worktree {w.name!r} holds the output branch "
                       f"{m.output_branch!r} in {win(home.path)}, which is no "
                       f"workspace of the campaign")
    if not milestone_landings(camp, m, workflow):
        out.append(f"{m.id}: no worktree of its workflow is on the output "
                   f"branch {m.output_branch!r} in a workspace of the campaign, "
                   f"so the milestone would land nowhere")
    return out


def contracts_path(camp: Campaign) -> Path | None:
    if camp.contracts:
        return Path(camp.root) / camp.contracts
    default = Path(camp.root) / CONTRACTS
    return default if default.is_file() else None


def milestone_args(camp: Campaign, m: Milestone, *, round_no: int = 1,
                   integration_sha: str = "") -> dict:
    args = {**dict(m.args),
            "campaign_root": str(camp.root),
            "milestone": m.id,
            "integration_branch": camp.integration_branch,
            "integration_sha": integration_sha,
            "round": str(round_no)}
    contracts = contracts_path(camp)
    if contracts is not None:
        args["contracts"] = str(contracts)
    return args


def escalation_marker() -> str:
    """The heading that opens ESCALATION.md, from `operator.escalation_marker`."""
    return str(settings.get("operator.escalation_marker", "ACTION NEEDED FROM THE OPERATOR"))


def load_campaign(path: str | Path, args: Mapping[str, Any] | None = None
                  ) -> Campaign:
    p = Path(path)
    spec = importlib.util.spec_from_file_location(f"ohflow_campaign_{p.stem}", p)
    if spec is None or spec.loader is None:
        raise WorkflowError(f"cannot import campaign module at {p}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "build"):
        raise WorkflowError(f"campaign module {p} exports no build(args) -> Campaign")
    try:
        camp = mod.build(WorkflowArgs(args or {}))
    except settings.SettingsError as e:
        raise WorkflowError(f"campaign module {p}: {e}") from None
    if not isinstance(camp, Campaign):
        raise WorkflowError(f"campaign module {p} build() returned {type(camp)}")
    return camp


def validate_campaign(camp: Campaign) -> list[str]:
    """Problems that stop a campaign before anything runs. Empty means go."""
    out: list[str] = []
    root = Path(camp.root)
    if not (root / ".git").exists():
        out.append(f"campaign root is not a git repository: {win(root)}")
    out += _workspace_problems(camp)
    names = {w.name for w in camp.all_workspaces()}
    if not (root / camp.charter).is_file():
        out.append(f"charter missing: {win(root / camp.charter)}")
    if camp.contracts:
        named = root / camp.contracts
        if not named.resolve().is_relative_to(root.resolve()):
            out.append(f"contracts outside the campaign root: {win(named)}")
        elif not named.is_file():
            out.append(f"contracts missing: {win(named)}")
    if not camp.milestones:
        out.append("a campaign needs at least one milestone")
    seen: set[str] = set()
    for m in camp.milestones:
        if m.id in seen:
            out.append(f"milestone id {m.id!r} appears twice")
        seen.add(m.id)
        for label, rel in (("workflow", m.workflow), ("spec", m.spec)):
            if not (root / rel).is_file():
                out.append(f"{m.id}: {label} missing at {win(root / rel)}")
        if Path(m.spec).parent != Path(m.workflow).parent:
            out.append(f"{m.id}: spec and workflow must sit in one milestone "
                       f"directory; the judge's write scope is that directory")
        for c in m.acceptance_checks:
            kind, _, space = c.cwd.partition(":")
            if kind == "land" and not m.output_branch:
                out.append(f"{m.id}: acceptance check {c.name!r} runs in the land "
                           f"worktree, and the milestone names no output branch")
            if kind in ("land", "repo") and space and space not in names:
                out.append(f"{m.id}: acceptance check {c.name!r} names "
                           f"workspace {space!r}, which the campaign does not "
                           f"declare")
        if (m.max_revisions if m.max_revisions is not None
                else camp.max_revisions) < 0:
            out.append(f"{m.id}: max_revisions must be zero or more")
    return out


def _workspace_problems(camp: Campaign) -> list[str]:
    declared = camp.workspaces
    if not all(isinstance(w, Workspace) for w in declared):
        return ["campaign: workspaces must hold Workspace records"]
    if not declared:
        if camp.repo is None:
            return ["campaign names no repository: set repo=, or workspaces= "
                    "for more than one"]
        repo = Path(camp.repo)
        return ([] if ohwt.is_git(repo)
                else [f"product repo is not a git repository: {win(repo)}"])
    out: list[str] = []
    if not _same_path(camp.repo, declared[0].path):
        out.append("campaign sets both repo= and workspaces=; declare the "
                   "repository as a Workspace and leave repo= unset")
    seen: dict[str, str] = {}
    for w in declared:
        if not isinstance(w.name, str) or not w.name.strip():
            out.append(f"workspace {w.name!r}: a workspace needs a nonempty name")
            continue
        if w.name in seen.values():
            out.append(f"workspace {w.name!r} is declared twice")
        key = os.path.normcase(str(Path(w.path).resolve()))
        if seen.get(key, w.name) != w.name:
            out.append(f"workspaces {seen[key]!r} and {w.name!r} name one "
                       f"path, {win(w.path)}")
        seen.setdefault(key, w.name)
        out += [fault if fault.startswith("workspace ")
                else f"workspace {w.name!r} is {fault}"
                for fault in ohwt.workspace_faults(w)]
    return out


# ------------------------------------------------------------------ the campaign log


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class CampaignLog:
    """Append-only. The campaign's state is a replay of these lines."""

    def __init__(self, root: Path):
        self.path = Path(root) / CAMPAIGN_LOG

    def append(self, event: str, **payload: Any) -> dict:
        rec = {"t": _now(), "event": event, **payload}
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")
        return rec

    def events(self) -> list[dict]:
        return [e for _line, e in self.numbered()]

    def numbered(self) -> list[tuple[int, dict]]:
        """Each event with its 1-based line in the file; blank lines count."""
        if not self.path.exists():
            return []
        out = []
        for n, line in enumerate(
                self.path.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append((n, json.loads(line)))
            except json.JSONDecodeError:
                # A torn last line from a killed controller. Everything before it
                # stands.
                break
        return out


def judge_run_dir(root: Path, m: Milestone, round_no: int) -> Path:
    """Where the judge run of a milestone's round lives. Its parent holds the
    packet and the handover."""
    return Path(root) / m.dir / "judge" / f"r{round_no:02d}" / "run"


@dataclass
class MilestoneState:
    status: str = "pending"        # pending | running | passed | escalated
    judgements: int = 0            # judge decisions recorded
    revisions: int = 0             # REVISE decisions committed
    granted: int = 0               # extra revisions a human granted
    run_dir: str | None = None
    decisions: list = field(default_factory=list)


def replay(camp: Campaign) -> dict[str, MilestoneState]:
    states = {m.id: MilestoneState() for m in camp.milestones}
    for e in CampaignLog(camp.root).events():
        s = states.get(e.get("milestone", ""))
        if s is None:
            continue
        ev = e["event"]
        if ev == "milestone_started":
            s.status = "running"
            s.run_dir = e.get("run_dir")
        elif ev == "judged":
            s.judgements += 1
            s.decisions.append(e)
        elif ev == "revision_committed":
            s.revisions += 1
        elif ev == "milestone_landed":
            s.status = "passed"
        elif ev == "escalated":
            s.status = "escalated"
        elif ev == "granted":
            s.granted += int(e.get("revisions", 0))
            s.status = "running"
    return states


# ------------------------------------------------------------------ git


def _git(cwd: Path, *args: str, check: bool = True) -> str:
    flags = ({"creationflags": subprocess.CREATE_NO_WINDOW}
             if os.name == "nt" else {})
    env = dict(os.environ, GIT_PAGER="cat", PAGER="cat")
    p = proc.run(["git", *args], cwd=str(cwd), capture_output=True,
                 text=True, encoding="utf-8", errors="replace", env=env,
                 **flags)
    if check and p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} in {win(cwd)} exited "
                           f"{p.returncode}: {p.stderr.strip()[:400]}")
    return p.stdout.strip()


def _rev(repo: Path, ref: str) -> str | None:
    out = _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}",
               check=False)
    return out or None


def _changed_paths(root: Path) -> list[str]:
    """Every path git would commit, tracked or not, relative to root.

    `-z` output, read raw: a stripped porcelain line loses the leading space
    of its status column, and slicing at a fixed offset then cuts the path.
    """
    flags = ({"creationflags": subprocess.CREATE_NO_WINDOW}
             if os.name == "nt" else {})
    p = proc.run(["git", "status", "--porcelain=v1", "-z",
                  "--untracked-files=all"], cwd=str(root),
                 capture_output=True, **flags)
    if p.returncode != 0:
        raise RuntimeError(f"git status in {win(root)} exited {p.returncode}")
    fields = p.stdout.decode("utf-8", "replace").split("\0")
    paths, i = [], 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if len(entry) < 4:
            continue
        status, path = entry[:2], entry[3:]
        if "R" in status or "C" in status:
            i += 1                  # the rename source follows as its own field
        paths.append(path)
    return paths


def ensure_ignores(root: Path) -> None:
    gi = Path(root) / ".gitignore"
    want = [f"milestones/*/{d}/" for d in GENERATED_DIRS] + \
        [CAMPAIGN_LOG, STATUS, ESCALATION, "campaign.log", PID_FILE,
         "campaign.log.launch.*", ".watch.*.json", "__pycache__/"]
    have = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
    missing = [w for w in want if w not in have]
    if missing:
        with gi.open("a", encoding="utf-8") as fh:
            if have and have[-1].strip():
                fh.write("\n")
            fh.write("# written by ohflow campaign\n")
            fh.write("\n".join(missing) + "\n")


# ------------------------------------------------------------------ the controller


class CampaignController:
    def __init__(self, camp: Campaign, *, no_dashboard: bool = False,
                 hold: bool = False, say=None, harness_executors=None,
                 history: tuple[str, ...] | None = None, pilot: bool = False):
        self.camp = camp
        self.harness_executors = harness_executors
        # The history every milestone and judge run is estimated from.
        self.history = history
        self.root = Path(camp.root)
        self.spaces = camp.all_workspaces()
        self.repo = Path(camp.repo) if camp.repo is not None else None
        self.campaign_log = CampaignLog(self.root)
        self.no_dashboard = no_dashboard
        # The campaign's first fresh round waits for `ohflow go`. A later
        # fresh round waits only when its estimate exceeds the first round's
        # actual time by half.
        self.hold = hold
        self.pilot = pilot
        self._say = say or (lambda msg: print(msg, flush=True))
        self._state: dict[str, Any] = {}

    def say(self, msg: str) -> None:
        self._say(f"[campaign {self.camp.name}] {msg}")

    # ---- entry

    def run(self) -> int:
        problems = validate_campaign(self.camp)
        if problems:
            for p in problems:
                self.say(f"invalid: {p}")
            return EXIT_FAILED
        ensure_ignores(self.root)
        (self.root / PID_FILE).write_text(str(os.getpid()), encoding="utf-8")
        if _changed_paths(self.root):
            # The controller commits every revision. A tree that is already dirty
            # would fold a human's unfinished edit into a judge's revision.
            _git(self.root, "add", "-A")
            _git(self.root, "commit", "-m",
                 f"campaign {self.camp.name}: inputs before the run")
        for space in self.spaces:
            said = ohwt.ensure_workspace(space)
            if said:
                self.say(f"workspace {space.name}: {said}")
        self._ensure_integration_branch()
        if (self.root / ESCALATION).exists():
            (self.root / ESCALATION).unlink()
        states = replay(self.camp)
        if not self.campaign_log.events():
            self.campaign_log.append("campaign_started", name=self.camp.name,
                                     milestones=[m.id for m in self.camp.milestones],
                                     integration_branch=self.camp.integration_branch,
                                     **self._integration())
        for i, m in enumerate(self.camp.milestones, start=1):
            st = states[m.id]
            if st.status == "passed":
                continue
            if st.status == "escalated":
                self.say(f"{m.id} is escalated; grant revisions with "
                         f"`ohflow campaign grant` after acting on "
                         f"{ESCALATION}")
                return EXIT_ESCALATED
            code = self._milestone(i, m, st)
            if code != EXIT_DELIVERED:
                return code
        self.campaign_log.append("campaign_delivered", integration_branch=self.camp.integration_branch,
                                 **self._integration())
        self._status(state="delivered")
        self.say(f"delivered: integration branch {self.camp.integration_branch} at "
                 f"{self._at(self._shas())}")
        return EXIT_DELIVERED

    def _ensure_integration_branch(self) -> None:
        for space in self.spaces:
            repo = Path(space.path)
            if _rev(repo, self.camp.integration_branch):
                continue
            base = _rev(repo, space.base_branch)
            if not base:
                raise RuntimeError(f"integration branch base {space.base_branch!r} does not "
                                   f"resolve in {win(repo)}")
            _git(repo, "branch", self.camp.integration_branch, base)

    def _shas(self) -> dict[str, str | None]:
        """Workspace name -> the commit its integration branch is at."""
        return {space.name: _rev(Path(space.path), self.camp.integration_branch)
                for space in self.spaces}

    def _integration(self) -> dict:
        """The integration fields of a campaign log event: the default
        workspace's commit, and every workspace's when there are several."""
        shas = self._shas()
        fields: dict = {"integration_sha": shas[self.spaces[0].name]}
        if len(self.spaces) > 1:
            fields["integration_shas"] = shas
        return fields

    def _at(self, shas: Mapping[str, str | None]) -> str:
        if len(self.spaces) == 1:
            return (shas[self.spaces[0].name] or "")[:10]
        return ", ".join(f"{name} {(sha or '')[:10]}" for name, sha in shas.items())

    # ---- one milestone

    def _budget(self, m: Milestone, st: MilestoneState) -> int:
        base = m.max_revisions if m.max_revisions is not None \
            else self.camp.max_revisions
        return base + st.granted

    def _milestone(self, index: int, m: Milestone, st: MilestoneState) -> int:
        mdir = self.root / m.dir
        run_dir = Path(st.run_dir) if st.run_dir else mdir / "runs" / m.id
        if st.status != "running":
            self.campaign_log.append("milestone_started", milestone=m.id,
                                     index=index, run_dir=str(run_dir),
                                     **self._integration())
            st.status = "running"
        revised = False
        while True:
            round_no = st.judgements + 1
            self._status(state="running", milestone=m.id, round=round_no,
                         run_dir=run_dir)
            workflow = self._load_workflow(m, round_no)
            problems = milestone_problems(self.camp, m, workflow)
            if problems:
                return self._stop_on_problem(m, "\n".join(problems))
            land = self._land_path(m, workflow)
            outcome = self._run_workflow(m, workflow, run_dir, round_no,
                                         revised=revised)
            if outcome.problem:
                return self._stop_on_problem(m, outcome.problem)
            if outcome.status == "paused":
                return self._stop_on_pause(m, run_dir)
            summary = outcome.summary or {"status": outcome.status,
                                          "phases": {}}
            checks = self._acceptance_checks(m, run_dir, land)
            packet = self._packet(index, m, st, run_dir, summary, checks,
                                  round_no, land)
            self._status(state="judging", milestone=m.id, round=round_no,
                         run_dir=run_dir, packet=packet)
            decision, handover, judge_dir = self._judge(m, round_no, packet)
            rec = self.campaign_log.append(
                "judged", milestone=m.id, round=round_no,
                decision=(decision or {}).get("decision"),
                summary=(decision or {}).get("summary"),
                findings=(decision or {}).get("findings", []),
                revisions=(decision or {}).get("revisions", []),
                question=(decision or {}).get("question_for_operator"),
                judge_dir=str(judge_dir), handover=handover,
                packet=str(packet), round_s=round_seconds(summary))
            st.judgements += 1
            st.decisions.append(rec)
            contract_edit, note = self._restore_contracts(m, round_no)

            if decision is None:
                return self._escalate(m, "the judge produced no valid "
                                         "decision; see its run", judge_dir, note)
            kind = decision["decision"]
            if kind == "ESCALATE":
                return self._escalate(
                    m, decision.get("question_for_operator") or decision["summary"],
                    judge_dir, note)
            if kind == "PASS":
                refusal = self._pass_refusal(summary, checks, run_dir)
                if refusal:
                    self._discard_edits()
                    return self._escalate(m, f"the judge passed the milestone "
                                             f"but {refusal}", judge_dir, note)
                self._discard_edits()
                return self._land(m, land)
            # REVISE
            stray = ([contract_edit] if contract_edit else []) + self._stray_edits(m)
            if stray:
                return self._escalate(
                    m, "the judge changed files outside its write scope: "
                       + ", ".join(stray), judge_dir, note)
            if not _changed_paths(self.root):
                return self._escalate(m, "the judge asked for a revision and "
                                         "changed nothing, so a rerun would "
                                         "repeat the last one", judge_dir)
            if st.revisions >= self._budget(m, st):
                self._stash_edits(m, round_no)
                return self._escalate(
                    m, f"the revision budget ({self._budget(m, st)}) is spent "
                       f"and the judge still asks for a revision; its "
                       f"proposed edit is committed on branch "
                       f"campaign-proposal/{m.id}-r{round_no:02d}", judge_dir)
            sha = self._commit_revision(m, round_no, decision)
            st.revisions += 1
            self.campaign_log.append("revision_committed", milestone=m.id,
                                     round=round_no, commit=sha)
            self.say(f"{m.id}: revision {st.revisions} committed at "
                     f"{sha[:10]}; resuming the run")
            revised = True

    # ---- the workflow run

    def _workflow_args(self, m: Milestone, round_no: int) -> dict:
        return milestone_args(
            self.camp, m, round_no=round_no,
            integration_sha=_rev(self.repo, self.camp.integration_branch) or "")

    def _load_workflow(self, m: Milestone, round_no: int) -> Workflow:
        return validate(load_workflow(self.root / m.workflow,
                                      self._workflow_args(m, round_no)))

    def _run_workflow(self, m: Milestone, workflow: Workflow, run_dir: Path,
                      round_no: int, revised: bool = False) -> RunOutcome:
        resume = (run_dir / "run-log.jsonl").exists()
        run_dir.parent.mkdir(parents=True, exist_ok=True)
        if not resume and run_dir.exists():
            # A run that stopped on a preflight fault left an owner file and
            # an exit report but no run log. Keep them as evidence, and free
            # the name for the retry.
            n = 1
            while run_dir.with_name(f"{run_dir.name}.not-started-{n:02d}").exists():
                n += 1
            run_dir.rename(run_dir.with_name(f"{run_dir.name}.not-started-{n:02d}"))
        self.say(f"{m.id} round {round_no}: "
                 f"{'resuming' if resume else 'starting'} {win(run_dir)}")
        hold = (revised or not resume) and (
            self.pilot or (self.hold and self._holds(m, workflow, round_no)))
        pilot = self.pilot and not resume and bool(workflow.units)
        if hold:
            # The status file names the held round and its go command, so
            # `campaign watch` and the dashboard callback print the release
            # without reading the run directory.
            go = go_command(run_dir)
            self._status(**{**self._state, "state": "held", "go": go})
            self.say(f"{m.id} round {round_no}: "
                     + ("the pilot runs first, then " if pilot else "")
                     + f"held; release it with {go}")
        return run_workflow(workflow, run_dir, RunOptions(
            resume="auto", hold=hold, hold_resume=revised, pilot=pilot,
            dashboard=not self.no_dashboard,
            on_dashboard=self._dashboard_serves,
            on_release=lambda: self._hold_released(m, round_no, run_dir),
            auto_resume=self.camp.auto_resume, harness_executors=self.harness_executors,
            workflow_path=str(self.root / m.workflow),
            workflow_args=self._workflow_args(m, round_no),
            history=self.history))

    def _hold_released(self, m: Milestone, round_no: int, run_dir: Path) -> None:
        """`go` has arrived: the round runs, and the status file says so."""
        self._status(state="running", milestone=m.id, round=round_no,
                     run_dir=run_dir)

    def _holds(self, m: Milestone, workflow: Workflow, round_no: int) -> bool:
        first = self._first_round_s()
        if first is None:
            return True
        estimate = self._round_estimate_s(workflow)
        if estimate is None or estimate > HOLD_FACTOR * first:
            return True
        self.say(f"{m.id} round {round_no}: no hold: its estimate of "
                 f"{ohestimate._minutes(estimate)} is within {HOLD_FACTOR:g} x the "
                 f"first round's {ohestimate._minutes(first)}")
        return False

    def _first_round_s(self) -> float | None:
        judged = [e for e in self.campaign_log.events() if e.get("event") == "judged"]
        if not judged:
            return None
        value = judged[0].get("round_s")
        return float(value) if isinstance(value, (int, float)) and value > 0 else None

    def _round_estimate_s(self, workflow: Workflow) -> float | None:
        history = ohestimate.history_paths(self.history)
        if history is None:
            return None
        try:
            run = ohestimate.estimate_workflow(
                workflow, ohestimate.Prior.from_history(history))["run"]
        except Exception:  # noqa: BLE001 - a forecast never stops a campaign
            return None
        wall = run["wall_s"]["p50"]
        return None if wall is None else wall + (run["checks_s"]["p50"] or 0)

    def _land_path(self, m: Milestone, workflow: Workflow
                   ) -> list[tuple[Workspace, Path | None]]:
        """Each workspace the milestone lands in, with the worktree that
        checks out its output branch there."""
        return milestone_landings(self.camp, m, workflow)

    def _check_dir(self, cwd: str, land: list[tuple[Workspace, Path | None]]
                   ) -> Path | None:
        """Where an acceptance check runs. `land` and `repo` mean the default
        workspace's; `land:<workspace>` and `repo:<workspace>` name another."""
        kind, _, name = cwd.partition(":")
        if kind not in ("land", "repo"):
            return Path(cwd)
        name = name or self.spaces[0].name
        if kind == "repo":
            return next((Path(s.path) for s in self.spaces if s.name == name), None)
        return next((path for space, path in land if space.name == name), None)

    def _acceptance_checks(self, m: Milestone, run_dir: Path,
                           land: list[tuple[Workspace, Path | None]]) -> list[dict]:
        out = []
        logs = run_dir / "acceptance-checks"
        for c in m.acceptance_checks:
            cwd = self._check_dir(c.cwd, land)
            if cwd is None or not cwd.exists():
                out.append({"name": c.name, "cmd": c.cmd, "exit": None,
                            "tail": f"no directory to run in ({c.cwd})"})
                continue
            cmd = c.cmd
            if BASE in cmd:
                kind, _, named = c.cwd.partition(":")
                space = (named if kind in ("land", "repo") and named
                         else self.spaces[0].name)
                cmd = with_base(c.cmd, self._shas().get(space) or "")
            if cmd is None:
                out.append({"name": c.name, "cmd": c.cmd, "cwd": win(cwd), "exit": None,
                            "tail": f"{BASE} is the commit of {self.camp.integration_branch} "
                                    f"in workspace {space}, and it has none"})
                continue
            tree = check_passes.clean_tree(cwd)
            prior = check_passes.find(run_dir, cmd, c.shell, cwd, tree)
            if prior is not None:
                out.append({"name": c.name, "cmd": cmd, "cwd": win(cwd), "exit": 0,
                            "tail": check_passes.reused_note(prior), "log": prior.get("log"),
                            "reused": True})
                continue
            r = ohexec.run(cmd, cwd=cwd, shell=c.shell, timeout=c.timeout_s,
                           log_dir=logs, name=c.name)
            if r.returncode == 0:
                check_passes.record(run_dir, cmd, c.shell, cwd, tree,
                                    by=f"acceptance check {c.name}", log=r.stdout_path)
            out.append({"name": c.name, "cmd": cmd, "cwd": win(cwd),
                        "exit": r.returncode, "tail": r.tail[-2000:],
                        "log": r.stdout_path})
        return out

    @staticmethod
    def _pass_refusal(summary: dict, checks: list[dict],
                      run_dir: Path) -> str | None:
        bad = [c["name"] for c in checks if c.get("exit") != 0]
        if bad:
            return f"acceptance checks failed: {', '.join(bad)}"
        steps = {v.coord: v.status for v in rundir.open_run(run_dir).steps()}
        not_ok = [c for c, s in steps.items() if s not in ("passed", "cached")]
        if summary.get("status") != "finished" or not_ok:
            return (f"the run ended {summary.get('status')!r} with steps not "
                    f"passed: {', '.join(not_ok) or 'none'}")
        return None

    # ---- the packet

    def _packet(self, index: int, m: Milestone, st: MilestoneState,
                run_dir: Path, summary: dict, checks: list[dict],
                round_no: int, land: list[tuple[Workspace, Path | None]]) -> Path:
        jdir = judge_run_dir(self.root, m, round_no).parent
        jdir.mkdir(parents=True, exist_ok=True)
        handover_path = jdir / "judge-handover.md"
        text = render_packet(self, index, m, st, run_dir, summary, checks,
                             round_no, handover_path, land)
        path = jdir / "packet.md"
        path.write_text(text, encoding="utf-8")
        return path

    # ---- the judge

    def _judge_workflow(self, m: Milestone, round_no: int, packet: Path,
                        handover: Path) -> Workflow:
        spec = m.judge or self.camp.judge
        brief = packet.read_text(encoding="utf-8")
        branch = _git(self.root, "rev-parse", "--abbrev-ref", "HEAD")
        step = Step(
            id="judge", kind="agent", worktree=None,
            agent=replace(spec, brief=brief),
            schema=DECISION_SCHEMA,
            execution_timeout_s=self.camp.judge_execution_timeout_s,
            objective=f"judge {m.id} round {round_no}: pass, revise or "
                      f"escalate",
            gate=GateSpec(checks=(
                CheckSpec("schema_valid", {}),
                CheckSpec("command_exit",
                          {"cmd": f'test -s "{posix(handover)}"'}),
            )),
            retry=RetryPolicy(max=1, on=("gate:schema_valid",
                                         "gate:command_exit",
                                         "agent_error")),
        )
        return validate(Workflow(
            name=f"judge-{m.id}-r{round_no:02d}", repo=self.root,
            base_branch=branch, baseline_cmd=None, max_parallel=1,
            phases=(Phase(name="judge", steps=(step,)),),
            auto_resume=self.camp.auto_resume))

    def _judge(self, m: Milestone, round_no: int, packet: Path
               ) -> tuple[dict | None, str | None, Path]:
        jdir = packet.parent
        handover = jdir / "judge-handover.md"
        run_dir = judge_run_dir(self.root, m, round_no)
        workflow = self._judge_workflow(m, round_no, packet, handover)
        self.say(f"{m.id} round {round_no}: judging")
        run_workflow(workflow, run_dir, RunOptions(
            resume="auto", dashboard=not self.no_dashboard,
            on_dashboard=self._dashboard_serves,
            auto_resume=self.camp.auto_resume, harness_executors=self.harness_executors,
            history=self.history))
        if not (run_dir / "run-log.jsonl").exists():
            return None, None, run_dir
        run = rundir.open_run(run_dir)
        judge = coord(1, "judge", 1, "judge")
        result, gate = run.result(judge), run.gate(judge)
        decision = None
        if result is not None and (gate or {}).get("passed"):
            decision = result.get("structured")
        return (decision, str(handover) if handover.exists() else None,
                run_dir)

    # ---- the judge's edits

    def _stray_edits(self, m: Milestone) -> list[str]:
        scope = m.dir.rstrip("/") + "/"
        frozen = {f"{scope}{f}" for f in FROZEN_INPUTS}
        return [p for p in _changed_paths(self.root)
                if not p.replace("\\", "/").startswith(scope)
                or p.replace("\\", "/") in frozen]

    def _restore_contracts(self, m: Milestone, round_no: int
                           ) -> tuple[str | None, str | None]:
        rel = Path(os.path.normpath(self.camp.contracts or CONTRACTS)).as_posix()
        if rel not in {p.replace("\\", "/") for p in _changed_paths(self.root)}:
            return None, None
        entry = f"judge edit to {rel} on {m.id} r{round_no:02d}"
        _git(self.root, "stash", "push", "--include-untracked", "-m", entry,
             "--", rel)
        return rel, (f"The judge also edited `{rel}`, which every step builds "
                     f"against and no judge may change. The controller "
                     f"restored the file and kept the edit in the git stash "
                     f"entry \"{entry}\".")

    def _commit_revision(self, m: Milestone, round_no: int,
                         decision: dict) -> str:
        lines = [f"{m.id} r{round_no:02d}: {decision['summary'][:60]}", ""]
        for r in decision.get("revisions", []):
            lines.append(f"- {r['path']}: {r['why']}")
        blocking = [f for f in decision.get("findings", [])
                    if f.get("severity") == "blocking"]
        if blocking:
            lines += ["", "Blocking findings:"]
            lines += [f"- {f['what']}" for f in blocking]
        _git(self.root, "add", "-A", "--", m.dir)
        _git(self.root, "commit", "-m", "\n".join(lines))
        return _git(self.root, "rev-parse", "HEAD")

    def _discard_edits(self) -> None:
        """A PASS changes nothing; a judge that edited anyway is undone.

        The edit goes to a `git stash` entry, "judge edits on a PASS decision".
        No diff file is written."""
        if not _changed_paths(self.root):
            return
        _git(self.root, "stash", "push", "--include-untracked", "-m",
             "judge edits on a PASS decision")

    def _stash_edits(self, m: Milestone, round_no: int) -> None:
        branch = f"campaign-proposal/{m.id}-r{round_no:02d}"
        here = _git(self.root, "rev-parse", "--abbrev-ref", "HEAD")
        _git(self.root, "checkout", "-b", branch)
        _git(self.root, "add", "-A", "--", m.dir)
        _git(self.root, "commit", "-m",
             f"{m.id} r{round_no:02d}: proposal past the revision budget")
        _git(self.root, "checkout", here)

    # ---- outcomes

    def _land(self, m: Milestone,
              land: list[tuple[Workspace, Path | None]]) -> int:
        """Move the integration branch of every workspace the milestone lands
        in to the output branch there. Every workspace is checked before any
        branch moves, so a refusal in one leaves all of them where they were."""
        several = len(self.spaces) > 1
        before = self._shas()
        moves: list[tuple[Workspace, str, str]] = []
        for space, _path in land:
            repo = Path(space.path)
            where = f" in workspace {space.name}" if several else ""
            landed = _rev(repo, m.output_branch)
            if not landed:
                return self._escalate(m, f"output branch {m.output_branch!r} does not "
                                         f"exist{where}", None)
            ff = proc.run(
                ["git", "merge-base", "--is-ancestor", before[space.name], landed],
                cwd=str(repo), capture_output=True).returncode == 0
            if not ff:
                return self._escalate(m, f"{m.output_branch} does not contain integration branch "
                                         f"{self.camp.integration_branch}{where}; landing it "
                                         f"would drop work", None)
            moves.append((space, before[space.name], landed))
        ref = f"refs/heads/{self.camp.integration_branch}"
        done: list[tuple[Workspace, str, str]] = []
        try:
            for space, old, new in moves:
                _git(Path(space.path), "update-ref", ref, new, old)
                done.append((space, old, new))
        except RuntimeError as e:
            for space, old, new in done:
                _git(Path(space.path), "update-ref", ref, old, new, check=False)
            return self._escalate(m, f"the integration branch moved while the "
                                     f"milestone landed, and no workspace was "
                                     f"changed: {e}", None)
        after = {**before, **{space.name: new for space, _old, new in moves}}
        default = self.spaces[0].name
        extra = ({"workspaces": {name: {"before": before[name], "after": after[name]}
                                 for name in after}} if several else {})
        self.campaign_log.append("milestone_landed", milestone=m.id,
                                 integration_before=before[default],
                                 integration_after=after[default], **extra)
        self.say(f"{m.id}: PASS; integration branch at {self._at(after)}")
        return EXIT_DELIVERED

    def _run_on_escalate(self, m: Milestone, path: Path) -> None:
        """Run the escalation command: the campaign's own `on_escalate`,
        else the `operator.on_escalate` setting, so a campaign that names
        no command of its own still reaches the operator."""
        cmd = self.camp.on_escalate or settings.get("operator.on_escalate")
        if cmd:
            ohexec.run(cmd.replace("{file}", posix(path)),
                       cwd=self.root, timeout=300,
                       log_dir=self.root / m.dir / "judge", name="on-escalate")

    def _escalate(self, m: Milestone, why: str, judge_dir: Path | None,
                  note: str | None = None) -> int:
        self.campaign_log.append("escalated", milestone=m.id, why=why,
                                 judge_dir=str(judge_dir) if judge_dir else None)
        body = [
            f"# {escalation_marker()}: campaign {self.camp.name} "
            f"stopped at {m.id}",
            "",
            why,
            "",
        ]
        if note:
            body += [note, ""]
        body += [
            f"- Milestone: {m.id}, {m.title}",
            f"- Campaign root: {win(self.root)}",
            f"- Campaign log: {win(self.root / CAMPAIGN_LOG)}",
        ]
        if judge_dir:
            body.append(f"- Judge run: {win(judge_dir)}")
        body += ["",
                 "To continue after acting on this: edit the milestone's "
                 "inputs if needed, then run",
                 "",
                 f"    {python_cmd()} -m ohflow.cli campaign grant --campaign "
                 f"<campaign.py> --milestone {m.id} --revisions 1",
                 f"    {python_cmd()} -m ohflow.cli campaign run --campaign "
                 f"<campaign.py>", ""]
        path = self.root / ESCALATION
        path.write_text("\n".join(body), encoding="utf-8")
        self._status(state="escalated", milestone=m.id, why=why)
        self.say(f"{m.id}: ESCALATED - {why}")
        self._run_on_escalate(m, path)
        return EXIT_ESCALATED

    def _stop_on_problem(self, m: Milestone, problem: str) -> int:
        """The run could not start (preflight failed, or the run directory is
        not this run's). No judge reads a run that never ran. The campaign log holds
        a `preflight_failed` event and no `escalated` event, so the milestone
        stays `running`: the next `campaign run` starts the same round again
        and no revision is spent."""
        self.campaign_log.append("preflight_failed", milestone=m.id, problem=problem)
        body = [
            f"# {escalation_marker()}: campaign {self.camp.name} "
            f"stopped at {m.id}: the run did not start",
            "",
            "The run did not start, so the problem below is an environment "
            "fault, not a decision on the work. No judge ran and no revision "
            "was spent.",
            "",
            problem,
            "",
            f"- Milestone: {m.id}, {m.title}",
            f"- Campaign root: {win(self.root)}",
            f"- Campaign log: {win(self.root / CAMPAIGN_LOG)}",
            "",
            "To continue after fixing the problem above, run",
            "",
            f"    {python_cmd()} -m ohflow.cli campaign run --campaign <campaign.py>",
            ""]
        path = self.root / ESCALATION
        path.write_text("\n".join(body), encoding="utf-8")
        self._status(state="preflight_failed", milestone=m.id,
                     problems=problem.splitlines() or [problem])
        self.say(f"{m.id}: the run did not start - {problem}")
        self._run_on_escalate(m, path)
        return EXIT_ESCALATED

    def _stop_on_pause(self, m: Milestone, run_dir: Path) -> int:
        """The run paused on a transient failure (a rate limit, a provider
        outage), so its deferred steps never got an answer. No judge reads it:
        a decision on unfinished work spends a revision on the provider's fault.
        The campaign log holds a `run_paused` event and no `judged` event, so the
        milestone stays `running`, and the next `campaign run` resumes the same
        round and its deferred steps."""
        run = rundir.open_run(run_dir)
        lines = []
        for v in run.steps():
            if v.status != "deferred":
                continue
            errors = [a.get("error") for a in v.attempts if a.get("error")]
            last = (errors[-1] if errors else "no error recorded")
            lines.append(f"{v.coord}: {' '.join(str(last).split())[:400]}")
        lines = lines or ["the run paused with no deferred step recorded"]
        self.campaign_log.append("run_paused", milestone=m.id, deferred=lines)
        body = [
            f"# {escalation_marker()}: campaign {self.camp.name} "
            f"paused at {m.id}: a provider deferred its steps",
            "",
            "The run paused on a transient failure, so its work is unfinished. "
            "No judge ran and no revision was spent. The provider's own "
            "message, which usually says when its limit resets:",
            "",
            *[f"- {line}" for line in lines],
            "",
            f"- Milestone: {m.id}, {m.title}",
            f"- Run: {win(run_dir)}",
            f"- Campaign log: {win(self.root / CAMPAIGN_LOG)}",
            "",
            "To continue once the limit has reset, run",
            "",
            f"    {python_cmd()} -m ohflow.cli campaign run --campaign <campaign.py>",
            ""]
        path = self.root / ESCALATION
        path.write_text("\n".join(body), encoding="utf-8")
        self._status(state="paused", milestone=m.id, run_dir=run_dir,
                     problems=lines)
        self.say(f"{m.id}: the run paused on a transient failure - "
                 f"{lines[0]}")
        self._run_on_escalate(m, path)
        return EXIT_ESCALATED

    def _status(self, **fields: Any) -> None:
        self._state = {k: v for k, v in fields.items() if k != "dashboard"}
        rec = {"campaign": self.camp.name, "updated": _now(),
               **{k: (str(v) if isinstance(v, Path) else v)
                  for k, v in fields.items()}}
        from . import runstatus
        rd = fields.get("run_dir")
        if "dashboard" not in fields and rd:
            url = runstatus.dashboard_url(Path(rd))
            if url:
                rec["dashboard"] = url
        (self.root / STATUS).write_text(json.dumps(rec, indent=2),
                                        encoding="utf-8")

    def _dashboard_serves(self, url: str) -> None:
        """Write the status file again, now that a run's dashboard serves.

        A held round keeps its `held` state and `go` command beside the URL,
        so a reader of the file has both the page and the release in one
        place."""
        self._status(**{**self._state, "dashboard": url})
        if self._state.get("state") == "held":
            self.say(f"dashboard {url} shows the held plan; release it with "
                     f"{self._state.get('go')}")


def grant(camp: Campaign, milestone: str, revisions: int) -> None:
    CampaignLog(camp.root).append("granted", milestone=milestone,
                                  revisions=revisions)


# ------------------------------------------------------------------ rendering


JUDGE_HANDOVER = "\n".join(f"- `## {h}`: {q}" for h, q in CORE)
HOLD_FACTOR = 1.5


def round_minutes(run_dir: Path) -> str:
    run = (ohestimate.read_estimate(run_dir) or {}).get("run") or {}
    wall = (run.get("wall_s") or {}).get("p50")
    checks = (run.get("checks_s") or {}).get("p50")
    if not isinstance(wall, (int, float)):
        return "an unknown number of minutes"
    return f"about {round((wall + (checks or 0)) / 60)} minutes"


def round_seconds(summary: Mapping[str, Any]) -> float | None:
    try:
        started = _dt.datetime.fromisoformat(str(summary["started"]))
        finished = _dt.datetime.fromisoformat(str(summary["finished"]))
    except (KeyError, TypeError, ValueError):
        return None
    seconds = (finished - started).total_seconds()
    return round(seconds, 1) if seconds > 0 else None

JUDGE_ROLE = """\
## Your role: the milestone judge

You are a fresh agent. No earlier session is waiting for you, and none will
check your work. This packet and the paths it names are your whole context.
Read every section before you decide.

**The bar is the charter, not the gate.** The gates already passed or failed
mechanically. Your job starts where they stop. A REVISE costs one more round,
{round_minutes} by the estimate in this packet. Ask for one when a finding would
cost the operator more than that to live with, and list the rest as notes.

**Evidence over claims.** An agent's report is a claim. The diff, the test
output and the running program are the evidence. Read the logs of the acceptance
checks in your packet; do not rerun a check that passed on the commit you judge. To
test a specific doubt, run only the test file or `-k` selection that answers it. Read
the diff of the output branch against the integration branch. Open the files.

**A rubric check is yours to grade.** A `- rubric:` line in the spec's
Acceptance section is a check that no command decides. Grade each one against
the evidence, and say in a finding or in your summary whether it is met. PASS
only when every rubric check is met.

**You change inputs, never the product.** Your write scope is the milestone
directory named below, except `spec.md`, which is the target. You may change
the briefs, the workflow module (phases, distribution, file ownership, tool
policies, models, gates, retries) and any snippet or reference file you add
there. You do not edit the product repository: the next run does, from your
revised inputs. Every revised step reruns; every unchanged passed step stays
cached.

**Name the cause of each finding** with one word: `brief` (the agent was not
told), `distribution` (ownership or order was wrong), `tool_policy` (wrong tools or
model), `gate` (the check did not hold the field constant, or checked the wrong
thing), `product` (the code is wrong and the brief was right: add a fix step),
or `spec` (the spec or the milestone spec is wrong). A `spec` cause is an
ESCALATE: the spec is not yours to change.

**Decisions.**
- `PASS`: the milestone meets the charter and the spec. Change no file.
- `REVISE`: you changed the inputs. List every changed path with the finding it
  answers. A REVISE with no changed file is refused.
- `ESCALATE`: a decision belongs to the operator: the spec is wrong, a choice
  between designs is theirs, or the fault is outside this milestone. Put the one
  question the operator must answer in `question_for_operator`.

**Before you answer, write your handover.** It is the note the next judge of
this campaign starts from. You write it yourself, in the format below; it needs
no skill. Write the file to the path named under "Your handover" below. Give
it a `# ` title line. Open it with one paragraph right under its title that
names the decision and the reason for it: `ohflow campaign history` shows that
paragraph. Then answer each of these headings once, in this order:

""" + JUDGE_HANDOVER + """

Use `not established` where you have no answer. Cite exact paths and commands,
and reference a file rather than copy it. Label each finding `[verified]` or
`[assumed]`. Mark every side effect you completed "already done, do not
repeat". Keep secrets out.

**Your last message is one fenced ```json block** matching this schema, and
nothing after it:
"""


def _fmt_summary(summary: dict, run_dir: Path) -> list[str]:
    lines = [f"- Run status: `{summary.get('status')}`"]
    run = rundir.open_run(run_dir)
    for view in sorted(run.steps(), key=lambda v: v.coord):
        rec = run.state.steps.get(view.coord)
        gate = (rec.gate if rec else None) or {}
        failed = [ch.get("name") for ch in gate.get("checks", [])
                  if isinstance(ch, dict) and not ch.get("passed")]
        extra = f"; failed checks: {', '.join(failed)}" if failed else ""
        lines.append(f"  - `{view.coord}`: {view.status}"
                     f" (executions {len(view.attempts)}){extra}")
        if rec and rec.handover_path:
            lines.append(f"    handover: `{win(run_dir / rec.handover_path)}`")
    return lines


def _read(path: Path, limit: int = 60000) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return f"(unreadable: {e})"
    if len(text) > limit:
        return text[:limit] + f"\n\n(truncated at {limit} characters; the " \
                              f"file is {win(path)})"
    return text


def render_packet(controller: CampaignController, index: int, m: Milestone,
                  st: MilestoneState, run_dir: Path, summary: dict,
                  checks: list[dict], round_no: int,
                  handover_path: Path,
                  land: list[tuple[Workspace, Path | None]] | None) -> str:
    camp = controller.camp
    root, repo = Path(camp.root), Path(camp.repo)
    spaces = camp.all_workspaces()
    several = len(spaces) > 1
    land = list(land or [])
    paths = {space.name: path for space, path in land}
    budget = controller._budget(m, st)
    total = len(camp.milestones)
    out: list[str] = [
        f"# Judge packet: campaign `{camp.name}`, milestone {index} of "
        f"{total} (`{m.id}`), round {round_no}",
        "",
        f"Revisions used: {st.revisions} of {budget}. When the budget is "
        f"spent, a further REVISE stops the campaign.",
        "",
        JUDGE_ROLE.replace("{round_minutes}", round_minutes(run_dir)),
        "```json",
        json.dumps(DECISION_SCHEMA, indent=2),
        "```",
        "",
        "## Where things are",
        "",
        f"- Campaign root (your working directory): `{win(root)}`",
        f"- Your write scope: `{win(root / m.dir)}` (not `spec.md`)",
        f"- Workflow module: `{win(root / m.workflow)}`",
    ]
    if several:
        out.append(f"- Workspaces: the campaign lands in {len(spaces)} "
                   f"repositories, and each has its own integration branch "
                   f"`{camp.integration_branch}`. The milestone lands in "
                   + (", ".join(f"`{name}`" for name in paths) or "none of them")
                   + ".")
        for space in spaces:
            at = (_rev(Path(space.path), camp.integration_branch) or "?")[:12]
            out.append(f"  - `{space.name}`: `{win(space.path)}`, integration "
                       f"branch at `{at}`"
                       + (", owned by ohflow" if space.owned else ""))
    else:
        out += [f"- Product repository: `{win(repo)}`",
                f"- Integration branch: `{camp.integration_branch}` at "
                f"`{(_rev(repo, camp.integration_branch) or '?')[:12]}`"]
    contracts = contracts_path(camp)
    if contracts is not None:
        out.append(f"- Contracts: `{win(contracts)}` (fixed, like `spec.md`)")
    for space, path in land:
        at = (_rev(Path(space.path), m.output_branch) or "missing")[:12]
        out.append(f"- Output branch: `{m.output_branch}` at `{at}`"
                   + (f" in workspace `{space.name}`" if several else "")
                   + (f", checked out at `{win(path)}`" if path else ""))
    out += [f"- Run directory: `{win(run_dir)}` (run log, board.md, "
            f"summary.json, exit-report.md, retro.md, one directory per "
            f"attempt with brief, final message and gate)",
            f"- Your handover: `{win(handover_path)}`",
            f"- Campaign log: `{win(root / CAMPAIGN_LOG)}`",
            "", "## The charter", "", _read(root / camp.charter), "",
            f"## The milestone spec: {m.title}", "", _read(root / m.spec), ""]
    if contracts is not None:
        out += ["## The contracts", "",
                f"File: `{win(contracts)}`. Every step of every milestone builds "
                f"against it, and its position block carries it. It is fixed "
                f"like `spec.md`: an edit to it escalates. A step that reports a "
                f"contract unworkable has found a `spec` cause: ESCALATE.",
                "", _read(contracts), ""]

    out += ["## What ran", ""] + _fmt_summary(summary, run_dir) + [""]
    from .handover import recorded
    run = rundir.open_run(run_dir)
    remaining = 60000
    out += ["## Step handovers (agent claims; check against the evidence)", ""]
    for view in run.steps():
        rec = run.state.steps.get(view.coord)
        if not rec:
            continue
        if rec.handover_path:
            title = f"### {view.coord}: {view.status}"
            try:
                path, text = recorded(run_dir, rec)
            except ValueError as error:
                out += [title, f"(handover unavailable: {error})", ""]
                continue
        elif contracts is not None and view.kind == "agent" and view.attempt:
            path = run.attempt_dir(view.coord, view.attempt) / "final.md"
            if not path.is_file():
                continue
            title = (f"### {view.coord}: {view.status} (its final message; "
                     f"this step writes no handover)")
            text = path.read_text(encoding="utf-8", errors="replace")
        else:
            continue
        out += [title, f"File: `{win(path)}`"]
        excerpt = text[:remaining]
        out.append(excerpt)
        if len(excerpt) < len(text):
            out.append("(packet limit reached; read the linked file)")
        remaining = max(0, remaining-len(excerpt))
        out.append("")
    for name in ("exit-report.md", "retro.md"):
        p = run_dir / name
        if p.exists():
            out.append(f"- `{win(p)}`")
    verdicts = sorted(run_dir.rglob("verdict.json"))
    for v in verdicts[-3:]:
        out += ["", f"Review verdict `{win(v)}`:", "```json",
                _read(v, 4000), "```"]
    out.append("")

    for space, _path in land:
        home = Path(space.path)
        if not _rev(home, m.output_branch):
            continue
        rng = f"{camp.integration_branch}..{m.output_branch}"
        log = _git(home, "log", "--oneline", "-50", rng, check=False)
        stat = _git(home, "diff", "--stat", rng, check=False)
        out += ["## The product change"
                + (f" in workspace `{space.name}`" if several else ""), "",
                f"`git log --oneline {rng}`:", "```", log or "(no commits)",
                "```", "", f"`git diff --stat {rng}`:", "```",
                "\n".join(stat.splitlines()[-60:]) or "(no change)", "```", ""]

    out += ["## Acceptance checks the controller ran", ""]
    if not checks:
        out.append("(the milestone defines none)")
    for c in checks:
        out += [f"### {c['name']}: exit {c.get('exit')}", "",
                f"`{c['cmd']}` in `{c.get('cwd', '?')}`", "", "```",
                (c.get("tail") or "").strip()[-1500:], "```", ""]

    out += ["## Lineage", ""]
    earlier = [s for s in camp.milestones[:index - 1]]
    if earlier:
        out.append("Milestones already passed, with the last judge's "
                   "handover of each:")
        states = replay(camp)
        for e in earlier:
            last = (states[e.id].decisions or [{}])[-1]
            out.append(f"- `{e.id}` {e.title}: {last.get('summary', '')}"
                       + (f" Handover: `{last['handover']}`"
                          if last.get("handover") else ""))
        out.append("")
    if st.decisions:
        out.append("Earlier decisions on this milestone, oldest first:")
        commits = [e for e in CampaignLog(root).events()
                   if e["event"] == "revision_committed"
                   and e.get("milestone") == m.id]
        for v in st.decisions:
            out += ["", f"### Round {v.get('round')}: {v.get('decision')}",
                    "", v.get("summary") or ""]
            for f in v.get("findings") or []:
                out.append(f"- [{f.get('severity')}/{f.get('cause', '?')}] "
                           f"{f.get('what')} (evidence: {f.get('evidence')})")
            for r in v.get("revisions") or []:
                out.append(f"- revised `{r.get('path')}`: {r.get('why')}")
            if v.get("handover"):
                out.append(f"- That judge's handover: `{v['handover']}`")
            match = [c for c in commits if c.get("round") == v.get("round")]
            if match:
                out.append(f"- Revision commit: `{match[0]['commit'][:12]}` "
                           f"(`git -C {posix(root)} show {match[0]['commit'][:12]}`)")
        out += ["", "Judge whether the last revision worked before you add "
                    "another. A finding that returns after a revision means "
                    "the revision named the wrong cause.", ""]
    else:
        out += ["This is the first judgement of this milestone.", ""]
    return "\n".join(out)

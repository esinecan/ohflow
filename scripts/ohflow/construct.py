"""`ohflow construct`: a bundle of milestone specs in, a campaign out.

The orchestrator agent reads the specs with its own connectors and writes
the bundle; this module reads only the bundle.

    <bundle>/
      bundle.md                 the campaign's name, the operator's words, the
                                workspaces, and optionally the judge
      contracts.md              optional; a fan-out under contracts needs it
      milestones/<id>/spec.md   one milestone each; the folder names order them

`read_bundle` parses the bundle and refuses it with every fault it finds, each
naming the milestone and the field at fault. `write_campaign` writes the
campaign: the charter, `campaign.py`, the contracts, and per milestone the spec,
`milestone.json`, `workflow.py` and the briefs. `references/construct.md` is
the format a bundle follows.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import proc, settings
from .campaign import ensure_ignores
from .gates import BASE
from .paths import posix, win
from .patterns import PATTERNS, PIECE_PATTERNS, ROLES, expand
from .tiers import TIERS
from .workflow import slug

__all__ = ["BundleRefused", "Bundle", "Milestone", "read_bundle", "write_campaign",
           "executor_for", "VALID_PAIRS"]

NAME = re.compile(r"[a-z0-9][a-z0-9-]*")
BOX = re.compile(r"[A-Za-z0-9._-]+")
FIELD = re.compile(r"^([A-Za-z][A-Za-z ]*?)\s*:\s*(.*)$")
ACCEPTANCE = re.compile(r"^(command|rubric)(?:\s+in\s+(\S+))?\s*:\s*(.*)$", re.I)
BULLET = re.compile(r"^[-*]\s+(.*)$")
PLACEHOLDER = re.compile(r"(?<!\$)\{([a-z0-9][a-z0-9-]*)\}")

HARNESSES = {"pi": "pi", "claude": "claude", "claude code": "claude",
             "claude-code": "claude", "codex": "codex"}
CLOUD = {"pi": "pi-cloud", "claude": "claude-cloud", "codex": "codex-cloud"}
PATTERN_ALIASES = {"single": "single-agent", "fanout": "fan-out",
                 "implement-review": "implement-and-review",
                 "contract-fanout": "fan-out-under-contracts"}
YES = {"yes": True, "true": True, "no": False, "false": False}
AGENT_FIELDS = ("box", "harness", "tier", "durable")
STEP_FIELDS = AGENT_FIELDS + ("workspace", "writes")
HEADER_FIELDS = ("source", "pattern", "workspaces", "workspace") + STEP_FIELDS
BUNDLE_FIELDS = ("integration branch", "kind", "judge harness", "judge tier")
WORKSPACE_FIELDS = ("path", "base", "remote", "baseline", "owned")
RESERVED = frozenset({"agent", "implement", "review", "consolidate"})
KINDS = {
    "delivery": ("The objective is a delivery: it is open to revision, and a "
                 "judge may REVISE its inputs whenever the result misses the goal."),
    "empirical": ("The objective is an empirical procedure: it is fixed once "
                  "committed. A judge REVISEs only to fix a deviation; a design flaw "
                  "needs a changed procedure, which restarts every arm on the "
                  "operator's decision, and a miss is the result."),
}

VALID_PAIRS = ("box local with harness pi, claude or codex (pi with durable: yes "
               "runs on durable); an ssh box with pi; box cloud with pi, claude or codex")


class BundleRefused(Exception):
    """The bundle cannot become a campaign. `problems` names each fault."""

    def __init__(self, problems: list[str]):
        super().__init__("\n".join(problems))
        self.problems = problems


@dataclass
class Agent:
    id: str
    role: str
    workspace: str
    writes: tuple[str, ...]
    box: str
    harness: str
    tier: str
    executor: str
    durable_box: str | None
    text: str = ""


@dataclass
class Check:
    kind: str
    text: str
    workspace: str | None


@dataclass
class Milestone:
    id: str
    title: str
    source: str
    pattern: str
    workspaces: tuple[str, ...]
    agents: list[Agent]
    checks: list[Check]
    spec_text: str

    def written(self) -> tuple[str, ...]:
        seen: list[str] = []
        for a in self.agents:
            if a.role != "review" and a.workspace not in seen:
                seen.append(a.workspace)
        return tuple(seen)

    def commands(self) -> list[Check]:
        return [c for c in self.checks if c.kind == "command"]

    def rubrics(self) -> list[Check]:
        return [c for c in self.checks if c.kind == "rubric"]


@dataclass
class Workspace:
    name: str
    path: str
    base: str = "main"
    remote: str | None = None
    baseline: str | None = None
    owned: bool = False


@dataclass
class Bundle:
    root: Path
    title: str
    name: str
    integration_branch: str
    kind: str
    judge: tuple[str, str] | None
    charter: list[tuple[str, str]]
    workspaces: dict[str, Workspace]
    contracts: str | None
    milestones: list[Milestone] = field(default_factory=list)


def executor_for(box: str, harness: str, durable: bool) -> tuple[str, str | None]:
    """The harness executor a box and a harness give, and the durable box.

    Raises ValueError naming the valid pairs when the pair has no executor."""
    if box == "local":
        if harness == "pi":
            return ("durable", "local") if durable else ("pi", None)
        if durable:
            raise ValueError(f"box local with harness {harness} and durable: yes has "
                             f"no executor; durable applies to pi. Valid pairs: "
                             f"{VALID_PAIRS}")
        return harness, None
    if box == "cloud":
        return CLOUD[harness], None
    if harness == "pi":
        return "durable", box
    raise ValueError(f"box {box!r} with harness {harness} has no executor; an ssh "
                     f"box runs pi only. Valid pairs: {VALID_PAIRS}")


def _sections(lines: list[str], marker: str) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """The lines before the first `marker` heading, then each heading with its lines."""
    head: list[str] = []
    out: list[tuple[str, list[str]]] = []
    for line in lines:
        if line.startswith(marker):
            out.append((line[len(marker):].strip(), []))
        elif out:
            out[-1][1].append(line)
        else:
            head.append(line)
    return head, out


def _title(lines: list[str]) -> tuple[str | None, list[str]]:
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        if line.startswith("# "):
            return line[2:].strip(), lines[i + 1:]
        return None, lines[i:]
    return None, []


def _fields(lines: list[str], known: tuple[str, ...], where: str,
            problems: list[str], *, extra=lambda key: False) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in lines:
        if not line.strip():
            continue
        match = FIELD.match(line.strip())
        key = re.sub(r"\s+", " ", match[1].strip().lower()) if match else None
        if key is None or (key not in known and not extra(key)):
            problems.append(f"{where}: the line {line.strip()!r} is no field; "
                            f"above the first ## section each line is one of "
                            f"{', '.join(k + ':' for k in known)}")
            continue
        if key in out:
            problems.append(f"{where}: the field {key}: appears twice")
        out[key] = _unquote(match[2].strip())
    return out


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] == "`":
        return value[1:-1].strip()
    return value


def _text(lines: list[str]) -> str:
    return "\n".join(lines).strip()


def _flag(value: str | None, where: str, name: str, problems: list[str]) -> bool:
    if value is None or value == "":
        return False
    if value.lower() not in YES:
        problems.append(f"{where}: {name}: must be yes or no, got {value!r}")
        return False
    return YES[value.lower()]


def read_bundle(root: str | Path) -> Bundle:
    """Parse the bundle at `root`; raise BundleRefused with every fault."""
    root = Path(root).resolve()
    problems: list[str] = []
    top = root / "bundle.md"
    if not top.is_file():
        raise BundleRefused([f"bundle.md: missing at {win(top)}; the bundle names the "
                             f"campaign, the operator's words and the workspaces there"])
    title, rest = _title(top.read_text(encoding="utf-8").splitlines())
    if not title:
        problems.append("bundle.md: no # title line; the title names the campaign")
        title = root.name
    name = slug(title)
    head, sections = _sections(rest, "## ")
    fields = _fields(head, BUNDLE_FIELDS, "bundle.md", problems)
    kind = (fields.get("kind") or "delivery").lower()
    if kind not in KINDS:
        problems.append(f"bundle.md: kind: must be delivery or empirical, got {kind!r}")
    judge = None
    if "judge harness" in fields or "judge tier" in fields:
        harness = HARNESSES.get((fields.get("judge harness") or "claude").lower())
        tier = (fields.get("judge tier") or "heavy").lower()
        if harness is None:
            problems.append(f"bundle.md: judge harness: must be pi, claude or codex, "
                            f"got {fields.get('judge harness')!r}; the judge runs on "
                            f"this machine")
        if tier not in TIERS:
            problems.append(f"bundle.md: judge tier: must be heavy or light, got {tier!r}")
        judge = (harness or "claude", tier)
    workspaces: dict[str, Workspace] = {}
    charter: list[tuple[str, str]] = []
    for heading, body in sections:
        words = heading.split()
        if words and words[0].lower() == "workspace":
            space = _workspace(root, words[1:], body, problems)
            if space is not None:
                if space.name in workspaces:
                    problems.append(f"bundle.md: workspace {space.name!r} is declared twice")
                workspaces[space.name] = space
        else:
            charter.append((heading, _text(body)))
    words_given = [t for h, t in charter if h.lower() == "the operator's words"]
    if not words_given or not words_given[0]:
        problems.append("bundle.md: no ## The operator's words section with text; "
                        "paste the operator's request there verbatim")
    if not workspaces:
        problems.append("bundle.md: no ## Workspace <name> section; declare each "
                        "repository the campaign works on")
    contracts_file = root / "contracts.md"
    contracts = (contracts_file.read_text(encoding="utf-8")
                 if contracts_file.is_file() else None)
    bundle = Bundle(root=root, title=title, name=name,
                    integration_branch=fields.get("integration branch") or f"campaign/{name}",
                    kind=kind, judge=judge, charter=charter, workspaces=workspaces,
                    contracts=contracts)
    folder = root / "milestones"
    ids = sorted(p.name for p in folder.iterdir() if p.is_dir()) if folder.is_dir() else []
    if not ids:
        problems.append(f"bundle: no milestone; write milestones/<id>/spec.md under "
                        f"{win(root)}")
    for mid in ids:
        milestone = _milestone(bundle, mid, folder / mid / "spec.md", problems)
        if milestone is not None:
            bundle.milestones.append(milestone)
    if problems:
        raise BundleRefused(list(dict.fromkeys(problems)))
    return bundle


def _workspace(root: Path, words: list[str], body: list[str],
               problems: list[str]) -> Workspace | None:
    if len(words) != 1 or not NAME.fullmatch(words[0]):
        problems.append(f"bundle.md: ## Workspace {' '.join(words)!r}: a workspace "
                        f"name is one word of lowercase letters, digits and hyphens")
        return None
    name = words[0]
    if f"{{{name}}}" == BASE:
        problems.append(f"bundle.md: ## Workspace {name}: the name is taken, because "
                        f"{BASE} in a command is the step's base commit")
        return None
    where = f"bundle.md: workspace {name}"
    fields = _fields(body, WORKSPACE_FIELDS, where, problems)
    owned = _flag(fields.get("owned"), where, "owned", problems)
    path = fields.get("path")
    if path:
        path = posix((Path(path) if Path(path).is_absolute() else root / path).resolve())
    elif owned:
        path = f"workspaces/{name}"
    else:
        problems.append(f"{where}: path: is missing; a workspace that ohflow does not "
                        f"own is a repository at a path")
        return None
    return Workspace(name=name, path=path, base=fields.get("base") or "main",
                     remote=fields.get("remote") or None,
                     baseline=fields.get("baseline") or None, owned=owned)


def _pattern(value: str | None) -> str:
    if not value:
        return "implement-and-review"
    norm = re.sub(r"[\s_]+", "-", value.strip().lower())
    return PATTERN_ALIASES.get(norm, norm)


def _milestone(bundle: Bundle, mid: str, spec: Path,
               problems: list[str]) -> Milestone | None:
    before = len(problems)
    if not NAME.fullmatch(mid):
        problems.append(f"{mid}: a milestone id is lowercase letters, digits and "
                        f"hyphens; rename the folder milestones/{mid}")
        return None
    if not spec.is_file():
        problems.append(f"{mid}: spec.md is missing at {win(spec)}")
        return None
    text = spec.read_text(encoding="utf-8")
    title, rest = _title(text.splitlines())
    if not title:
        problems.append(f"{mid}: spec.md has no # title line")
    head, sections = _sections(rest, "## ")
    pattern_line = next((FIELD.match(l.strip())[2].strip() for l in head
                         if FIELD.match(l.strip())
                         and FIELD.match(l.strip())[1].strip().lower() == "pattern"), None)
    pattern = _pattern(_unquote(pattern_line) if pattern_line else None)
    roles = ROLES.get(pattern, ())
    named = roles if pattern in PATTERNS else tuple(r for rs in ROLES.values() for r in rs)
    fields = _fields(head, HEADER_FIELDS, mid, problems,
                     extra=lambda key: key == "shape" or (len(key.split()) == 2
                                                          and key.split()[0] in named
                                                          and key.split()[1] in STEP_FIELDS[:5]))
    if "shape" in fields:
        problems.append(f"{mid}: shape: is no field; name the workflow pattern on a "
                        f"pattern: line, such as pattern: "
                        f"{fields['shape'] or 'implement-and-review'}")
    if pattern not in PATTERNS:
        problems.append(f"{mid}: pattern: {pattern_line!r} is unknown; use one of "
                        f"{', '.join(PATTERNS)}")
    source = fields.get("source")
    if not source:
        problems.append(f"{mid}: no source: line; name the issue URL, the ticket key "
                        f"or the file path the milestone serves")
    if "workspace" in fields and "workspaces" in fields:
        problems.append(f"{mid}: give workspaces: once, not workspace: beside it")
    listed = fields.get("workspaces") or fields.get("workspace")
    if listed:
        spaces = tuple(w.strip() for w in listed.split(",") if w.strip())
    elif len(bundle.workspaces) == 1:
        spaces = tuple(bundle.workspaces)
    else:
        spaces = ()
        problems.append(f"{mid}: no workspaces: line; the bundle declares "
                        f"{', '.join(bundle.workspaces) or 'none'}")
    for name in spaces:
        if name not in bundle.workspaces:
            problems.append(f"{mid}: workspaces: names {name!r}, which bundle.md does "
                            f"not declare; declared: {', '.join(bundle.workspaces) or 'none'}")
    body = {h.lower(): lines for h, lines in sections}
    if not _text(body.get("scope", [])):
        problems.append(f"{mid}: no ## Scope section with text; the scope is the task "
                        f"every brief carries")
    agents: list[Agent] = []
    if pattern in PATTERNS and spaces:
        defaults = {k: fields.get(k) for k in STEP_FIELDS if k != "workspace"}
        for role in roles:
            given = {k: fields.get(f"{role} {k}") for k in STEP_FIELDS[:5]}
            values = {k: given.get(k) or defaults.get(k) for k in STEP_FIELDS}
            if role in ("agent", "implement"):
                values["writes"] = defaults.get("writes")
            agent = _agent(mid, role, role, values, spaces, problems,
                           where=f"{mid}: {role}",
                           own=frozenset(k for k, v in given.items() if v))
            if agent is not None:
                agents.append(agent)
        if pattern in PIECE_PATTERNS:
            counted = len(problems)
            pieces = _steps(mid, body.get("steps"), defaults, spaces, problems)
            if "steps" not in body:
                problems.append(f"{mid}: pattern {pattern} needs a ## Steps section with "
                                f"one ### <name> part per step")
            elif len(problems) == counted and len(pieces) < 2:
                problems.append(f"{mid}: pattern {pattern} needs at least two steps under "
                                f"## Steps, got {len(pieces)}")
            role = "relay" if pattern == "relay" else "piece"
            for piece in pieces:
                piece.role = role
            agents = pieces + agents
        if pattern == "fan-out-under-contracts" and bundle.contracts is None:
            problems.append(f"{mid}: pattern fan-out-under-contracts needs contracts.md "
                            f"in the bundle; it fixes the interfaces the steps share")
    milestone = Milestone(id=mid, title=title or mid, source=source or "", pattern=pattern,
                          workspaces=spaces, agents=agents, checks=[], spec_text=text)
    written = set(milestone.written())
    for agent in agents:
        if agent.role in ("review", "consolidate") and pattern in PIECE_PATTERNS \
                and agent.workspace not in written:
            problems.append(f"{mid}: {agent.role} workspace: {agent.workspace!r} holds "
                            f"no step's work; name a workspace a step writes in")
    milestone.checks = _checks(mid, body.get("acceptance", []), milestone, problems)
    return milestone if len(problems) == before else None


def _agent(mid: str, step_id: str, role: str, values: dict, spaces: tuple[str, ...],
           problems: list[str], *, where: str, own: frozenset[str] = frozenset(),
           text: str = "") -> Agent | None:
    before = len(problems)

    def at(*keys: str) -> str:
        return where if any(k in own for k in keys) else mid

    workspace = values.get("workspace") or spaces[0]
    if workspace not in spaces:
        problems.append(f"{at('workspace')}: workspace: {workspace!r} is not among the "
                        f"milestone's workspaces: {', '.join(spaces)}")
    box = (values.get("box") or "").strip()
    harness_given = (values.get("harness") or "").strip()
    tier = (values.get("tier") or "").strip().lower()
    if not box:
        problems.append(f"{at('box')}: no box: line; name local, cloud or an ssh box")
    elif box.lower() in ("local", "cloud"):
        box = box.lower()
    elif not BOX.fullmatch(box):
        problems.append(f"{at('box')}: box: {box!r} is no ssh host alias; use local, "
                        f"cloud or the alias of an ssh box")
    harness = HARNESSES.get(harness_given.lower())
    if not harness_given:
        problems.append(f"{at('harness')}: no harness: line; name pi, claude or codex")
    elif harness is None:
        problems.append(f"{at('harness')}: harness: {harness_given!r} is unknown; use "
                        f"pi, claude or codex")
    if not tier:
        problems.append(f"{at('tier')}: no tier: line; name heavy or light")
    elif tier not in TIERS:
        problems.append(f"{at('tier')}: tier: {tier!r} must be heavy or light")
    durable = _flag(values.get("durable"), at("durable"), "durable", problems)
    executor, durable_box = "", None
    if box and harness and len(problems) == before:
        try:
            executor, durable_box = executor_for(box, harness, durable)
        except ValueError as error:
            problems.append(f"{at('box', 'harness', 'durable')}: box and harness: {error}")
    if len(problems) != before:
        return None
    writes = tuple(w.strip() for w in (values.get("writes") or "**").split(",")
                   if w.strip())
    return Agent(id=step_id, role=role, workspace=workspace, writes=writes or ("**",),
                 box=box, harness=harness, tier=tier, executor=executor,
                 durable_box=durable_box, text=text)


def _steps(mid: str, lines: list[str] | None, defaults: dict, spaces: tuple[str, ...],
           problems: list[str]) -> list[Agent]:
    if not lines:
        return []
    _, parts = _sections(lines, "### ")
    out: list[Agent] = []
    seen: set[str] = set()
    for name, body in parts:
        where = f"{mid}: step {name}"
        if not NAME.fullmatch(name) or name in RESERVED \
                or name.startswith(("merge-", "check-", "piece-")):
            problems.append(f"{where}: a step name is lowercase letters, digits and "
                            f"hyphens, starts with none of merge-, check- and piece-, "
                            f"and is none of {', '.join(sorted(RESERVED))}")
            continue
        if name in seen:
            problems.append(f"{where}: the step is named twice")
            continue
        seen.add(name)
        given: dict[str, str] = {}
        i = 0
        while i < len(body):
            line = body[i].strip()
            match = FIELD.match(line) if line else None
            key = match[1].strip().lower() if match else None
            if not line and not given:
                i += 1
                continue
            if key in STEP_FIELDS:
                given[key] = _unquote(match[2].strip())
                i += 1
                continue
            break
        task = _text(body[i:])
        if not task:
            problems.append(f"{where}: no task text under the step's fields")
        values = {k: given.get(k) or defaults.get(k) for k in STEP_FIELDS}
        values["writes"] = given.get("writes")
        agent = _agent(mid, name, "piece", values, spaces, problems, where=where,
                       own=frozenset(given), text=task)
        if agent is not None:
            out.append(agent)
    return out


def _checks(mid: str, lines: list[str], milestone: Milestone,
            problems: list[str]) -> list[Check]:
    out: list[Check] = []
    written = milestone.written()
    for line in lines:
        bullet = BULLET.match(line.strip())
        if not bullet:
            continue
        match = ACCEPTANCE.match(bullet[1].strip())
        if not match or not match[3].strip():
            problems.append(f"{mid}: acceptance line {line.strip()!r} is neither "
                            f"- command: <command> nor - rubric: <what the judge grades>")
            continue
        kind, space, text = match[1].lower(), match[2], _unquote(match[3].strip())
        if kind == "rubric":
            if space:
                problems.append(f"{mid}: rubric {text!r} names a workspace; only a "
                                f"command runs in one")
            out.append(Check("rubric", text, None))
            continue
        space = space or (written[0] if written else None)
        if not written:
            out.append(Check("command", text, space))
            continue
        if space not in milestone.workspaces:
            problems.append(f"{mid}: command {text!r} runs in workspace {space!r}, which "
                            f"the milestone's workspaces: line does not name")
        elif space not in written:
            problems.append(f"{mid}: command {text!r} runs in workspace {space!r}, where "
                            f"no step of the milestone writes; name one of "
                            f"{', '.join(written) or 'none'}")
        for name in PLACEHOLDER.findall(text):
            if name in milestone.workspaces and name not in written:
                problems.append(f"{mid}: command {text!r} names {{{name}}}, where no "
                                f"step writes, so it has no worktree")
        out.append(Check("command", text, space))
    return out


def _attribution() -> str:
    if settings.get("commit_checks.no_ai_attribution", False):
        return " No commit message names an AI tool or model as author or co-author."
    return ""


def _base_note(commands: list[str]) -> str:
    if not any(BASE in c for c in commands):
        return ""
    return (f" In a command, `{BASE}` stands for the commit your position block names "
            "under \"created from\". ohflow fills it in when it runs the command; "
            "when you run the command yourself, write that commit in its place.")


def _check_lists(m: Milestone, agent: Agent, *, gated: bool) -> str:
    commands = [c for c in m.commands() if c.workspace == agent.workspace]
    blocks: list[str] = []
    if commands:
        lead = ("Your gate runs each command below once after you finish, and each "
                "must exit 0. While you work, run only the tests of the files you "
                "change and the tests you add, not these commands: the gate runs "
                "them." if gated else
                "The campaign runs each command below after the run.")
        lead += _base_note([c.text for c in commands])
        blocks.append(lead + "\n\n" + "\n".join(f"   - `{c.text}`" for c in commands))
    if m.rubrics():
        blocks.append("The campaign judge grades these rubric checks after the run:"
                      "\n\n" + "\n".join(f"   - {c.text}" for c in m.rubrics()))
    return "\n\n".join(blocks) or "The spec names no check for this worktree."


def _spec_block(m: Milestone) -> str:
    return ("## The milestone spec\n\nThe spec is fixed: neither you nor the campaign "
            "judge may change it. A spec that cannot be met as written is a finding "
            "for your handover.\n\n" + m.spec_text.strip() + "\n")


def _head(b: Bundle, m: Milestone, task: str) -> str:
    return (f"# Task: {task}\n\nThis step serves milestone `{m.id}` of the campaign "
            f"`{b.name}`: {m.title}. Its source is {m.source}.\n")


def brief(b: Bundle, m: Milestone, agent: Agent) -> str:
    """The brief of one agent step of a constructed milestone."""
    role = agent.role
    if role == "review" and m.pattern == "implement-and-review":
        return _review_brief(b, m, agent)
    if role == "review":
        return _contracts_review_brief(b, m, agent)
    last = {a.workspace: a.id for a in m.agents if a.role != "review"}
    gated = role in ("agent", "implement") or (role == "relay"
                                               and last[agent.workspace] == agent.id)
    parts = [_head(b, m, m.title if role in ("agent", "implement")
                   else f"{agent.id}, a step of {m.title}")]
    if role == "relay":
        order = [a.id for a in m.agents if a.role == "relay"]
        n = order.index(agent.id) + 1
        parts.append(f"## Your part\n\nYou are step {n} of {len(order)} of a relay: "
                     f"{', '.join(order)}. "
                     + (f"The handover of `{order[n - 2]}` above tells you what the step "
                        f"before you did. " if n > 1 else "")
                     + f"Your part:\n\n{agent.text}\n")
    elif role == "piece":
        others = [a.id for a in m.agents if a.role == "piece" and a.id != agent.id]
        contracts = (" The contracts in your position block fix every interface your "
                     "piece shares with another piece. Build against them exactly. If a "
                     "contract is unworkable for your piece, stop: commit nothing that "
                     "works around it, and name the contract and the reason in your "
                     "handover under Open." if m.pattern == "fan-out-under-contracts" else "")
        parts.append(f"## Your piece\n\nThe pieces {', '.join(others)} run at the same "
                     f"time on their own branches, and none of you sees the others' "
                     f"work.{contracts} Your piece:\n\n{agent.text}\n")
    elif role == "consolidate":
        pieces = [a.id for a in m.agents if a.role == "piece"]
        parts.append(f"## Your part\n\nThe pieces {', '.join(pieces)} are merged into "
                     f"this worktree, and their handovers are above. Make them fit "
                     f"together: fix every mismatch between the pieces inside your write "
                     f"scope, and run each check below. Commit each fix; a merge that "
                     f"already fits needs no commit.\n")
    else:
        parts.append("## What to do\n\nBuild what the milestone spec below asks, in "
                     "this worktree and inside your write scope. Your position block "
                     "above names the worktree, the branch and the write scope.\n")
    done = [
        "1. Every behaviour your part of the spec asks for exists, with tests where "
        "the workspace has a test suite.",
        "2. " + _check_lists(m, agent, gated=gated),
        "3. Every change is committed on your branch, and `git status --porcelain` "
        "prints nothing." + _attribution(),
        "4. Your handover names what you built, each command you ran with its result, "
        "and what you did not verify.",
    ]
    if role == "consolidate":
        done[0] = "1. The merged pieces work together as the spec asks."
    parts.append("## Definition of done\n\n" + "\n".join(done) + "\n")
    parts.append(_spec_block(m))
    return "\n".join(parts)


def _review_brief(b: Bundle, m: Milestone, agent: Agent) -> str:
    commands = [c.text for c in m.commands() if c.workspace == agent.workspace]
    run = ("3. The implementer's gate already ran each command below on the commit "
           "you review, and it passed. Your gate reuses that pass while the commit is "
           "unchanged. Do not run these commands or the full suite yourself. To check "
           "a specific doubt, run only the test file or `-k` selection that answers "
           "it, and name it in your findings." + _base_note(commands) + "\n\n"
           + "\n".join(f"   - `{c}`" for c in commands) + "\n"
           if commands else
           "3. The spec names no command. Run the tests of the files the change "
           "touches, not the whole suite, and record their exit.\n")
    rubrics = "".join(f"\n   - {c.text}" for c in m.rubrics())
    return "\n".join([
        _head(b, m, f"review the change for {m.title}"),
        "You have a terminal and nothing else. Do not edit, create or delete any "
        "file in this worktree, and do not commit: your gate fails on a dirty tree.\n",
        "1. Read the milestone spec below and the implementer's handover above.",
        "2. Read every commit on this branch since the commit your position block "
        "names under \"created from\": `git log --oneline <that commit>..HEAD` and "
        "`git diff <that commit>..HEAD`.",
        run,
        "4. Check the change against the spec's scope"
        + (" and each rubric check:" + rubrics + "\n" if rubrics else ".")
        + "\n   Check correctness, the tests, and the documents the change touches.",
        "5. End your final message with one line. Write `VERDICT: MERGEABLE` when "
        "you would merge the change as it is. Otherwise write `VERDICT: BLOCKED` and "
        "list the blocking findings above it, each with its path, its line and the "
        "fix in one sentence. BLOCKED fails this step on purpose, and the campaign "
        "judge then revises the work.\n",
        _spec_block(m)])


def _contracts_review_brief(b: Bundle, m: Milestone, agent: Agent) -> str:
    pieces = [a for a in m.agents if a.role == "piece"]
    listing = "\n".join(f"   - `{a.id}` in workspace `{a.workspace}`" for a in pieces)
    commands = "\n".join(f"   - `{c.text}` in workspace `{c.workspace}`"
                         for c in m.commands()) or "   - the spec names no command"
    return "\n".join([
        _head(b, m, f"review the merged pieces of {m.title}"),
        "You have a terminal and nothing else. Do not edit, create or delete any "
        "file, and do not commit: your gate fails on a dirty tree.\n",
        "1. Read the spec below and the contracts in your position block. Every "
        "piece's branch is merged into the output branch of its workspace; your "
        "position block lists the workspaces and their worktrees.\n\n" + listing + "\n",
        "2. For each piece, read its handover above and its commits in its "
        "workspace. Check the piece against its part of the spec and against every "
        "contract it makes or uses.",
        "3. Run each command once, in the output worktree of its workspace, and "
        "record its exit." + _base_note([c.text for c in m.commands()]) + "\n\n"
        + commands + "\n",
        "4. Sort every finding into one list. `blocking`: it breaks a contract, the "
        "spec or a command, and you would not merge over it. `should_fix`: it is "
        "wrong but the merge can stand. `notes`: anything else worth knowing. Give "
        "each finding its piece, a repository-relative path, the contract it breaks "
        "when one does, the claim, and the fix in one sentence.",
        "5. Answer with the structured result your schema names. A non-empty "
        "`blocking` list fails this step on purpose, and the campaign judge then "
        "revises the work.\n",
        _spec_block(m)])


WORKFLOW_PY = '''from pathlib import Path

from ohflow.patterns import build_milestone


def build(args):
    return build_milestone(Path(__file__).resolve().with_name("milestone.json"), args)
'''


def _workspace_record(space: Workspace) -> dict[str, Any]:
    return {"name": space.name, "path": space.path, "base_branch": space.base,
            "remote": space.remote, "baseline_cmd": space.baseline, "owned": space.owned}


def milestone_record(b: Bundle, m: Milestone) -> dict[str, Any]:
    return {
        "id": m.id,
        "title": m.title,
        "source": m.source,
        "pattern": m.pattern,
        "branch": f"milestone/{b.name}/{m.id}",
        "execution_timeout_s": 5400,
        "workspaces": [_workspace_record(b.workspaces[w]) for w in m.workspaces],
        "steps": [{"id": a.id, "role": a.role, "workspace": a.workspace,
                   "writes": [] if a.role == "review" else list(a.writes),
                   "box": a.durable_box,
                   "harness": a.harness, "executor": a.executor, "tier": a.tier,
                   "brief": f"briefs/{a.id}.md"} for a in m.agents],
        "commands": [{"name": str(i), "cmd": c.text, "workspace": c.workspace}
                     for i, c in enumerate(m.commands(), start=1)],
    }


def _path_code(path: str) -> str:
    return (f"Path({path!r})" if Path(path).is_absolute() else f"ROOT / {path!r}")


def campaign_py(b: Bundle) -> str:
    spaces = []
    for s in b.workspaces.values():
        extra = "".join([f", base_branch={s.base!r}",
                         f", remote={s.remote!r}" if s.remote else "",
                         f", baseline_cmd={s.baseline!r}" if s.baseline else "",
                         ", owned=True" if s.owned else ""])
        spaces.append(f"            Workspace({s.name!r}, {_path_code(s.path)}{extra}),")
    milestones = []
    for m in b.milestones:
        written = set(m.written())
        checks = [f"                    AcceptanceCheck({f'check-{i}'!r}, "
                  f"{expand(c.text, c.workspace, written)!r}, cwd={'land:' + c.workspace!r}),"
                  for i, c in enumerate(m.commands(), start=1)]
        lines = [
            "            Milestone(",
            f"                id={m.id!r},",
            f"                title={m.title!r},",
            f"                workflow={f'milestones/{m.id}/workflow.py'!r},",
            f"                spec={f'milestones/{m.id}/spec.md'!r},",
            f"                output_branch={f'milestone/{b.name}/{m.id}'!r},",
        ]
        if checks:
            lines += ["                acceptance_checks=("] + checks + ["                ),"]
        lines.append("            ),")
        milestones += lines
    judge = ""
    imports = "from ohflow.workflow import Workspace"
    if b.judge is not None:
        harness, tier = b.judge
        imports = ("from ohflow.patterns import model_config\n"
                   "from ohflow.workflow import AgentSpec, Workspace")
        judge = (f"        judge=AgentSpec(role='milestone-judge', brief='', "
                 f"harness_executor={harness!r}, model=model_config({harness!r}, "
                 f"{tier!r}), max_iterations=400),\n")
    contracts = "        contracts='contracts.md',\n" if b.contracts is not None else ""
    return (
        "from pathlib import Path\n\n"
        "from ohflow.campaign import AcceptanceCheck, Campaign, Milestone\n"
        f"{imports}\n\n"
        "ROOT = Path(__file__).resolve().parent\n\n\n"
        "def build(args):\n"
        "    return Campaign(\n"
        f"        name={b.name!r},\n"
        "        root=ROOT,\n"
        "        charter='charter.md',\n"
        "        workspaces=(\n" + "\n".join(spaces) + "\n        ),\n"
        f"        integration_branch={b.integration_branch!r},\n"
        f"{contracts}{judge}"
        "        milestones=(\n" + "\n".join(milestones) + "\n        ),\n"
        "    )\n")


def charter_md(b: Bundle) -> str:
    out = [f"# Charter: {b.title}", ""]
    decided = False
    for heading, text in b.charter:
        out += [f"## {heading}", ""]
        if heading.lower() == "decisions already made":
            text = (text + "\n" if text else "") + f"- {KINDS[b.kind]}"
            decided = True
        out += [text, ""] if text else []
    if not decided:
        out += ["## Decisions already made", "", f"- {KINDS[b.kind]}", ""]
    out += ["## Milestones", "",
            f"`ohflow construct` built this campaign from the bundle "
            f"`{posix(b.root)}`. Each milestone traces to its source.", "",
            "| Milestone | Pattern | Source |", "|---|---|---|"]
    out += [f"| `{m.id}` {m.title} | {m.pattern} | {m.source} |" for m in b.milestones]
    return "\n".join(out) + "\n"


def _git(cwd: Path, *args: str) -> None:
    flags = ({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {})
    p = proc.run(["git", *args], cwd=str(cwd), capture_output=True, text=True,
                 encoding="utf-8", errors="replace", **flags)
    if p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} in {win(cwd)} exited "
                           f"{p.returncode}: {p.stderr.strip()[:400]}")


def write_campaign(b: Bundle, out: str | Path) -> Path:
    """Write the campaign for bundle `b` into the new folder `out`."""
    out = Path(out).resolve()
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise BundleRefused([f"--out {win(out)} exists and is not an empty folder; "
                             f"construct writes a new campaign only"])
    out.mkdir(parents=True, exist_ok=True)
    _git(out, "init", "--quiet")
    (out / ".gitignore").write_text("# written by ohflow construct\nworktrees/\n"
                                    "workspaces/\n", encoding="utf-8")
    ensure_ignores(out)
    (out / "charter.md").write_text(charter_md(b), encoding="utf-8")
    if b.contracts is not None:
        (out / "contracts.md").write_text(b.contracts, encoding="utf-8")
    (out / "campaign.py").write_text(campaign_py(b), encoding="utf-8")
    for m in b.milestones:
        mdir = out / "milestones" / m.id
        (mdir / "briefs").mkdir(parents=True)
        (mdir / "spec.md").write_text(m.spec_text, encoding="utf-8")
        (mdir / "workflow.py").write_text(WORKFLOW_PY, encoding="utf-8")
        (mdir / "milestone.json").write_text(
            json.dumps(milestone_record(b, m), indent=2) + "\n", encoding="utf-8")
        for agent in m.agents:
            (mdir / "briefs" / f"{agent.id}.md").write_text(brief(b, m, agent),
                                                            encoding="utf-8")
    return out

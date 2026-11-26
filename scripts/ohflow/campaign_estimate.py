"""`ohflow campaign estimate`: the forecast of a whole campaign.

`ohflow estimate` forecasts one workflow run. A campaign is the level above
it, and the question asked before one starts is the campaign's: how many
hours, how many tokens and how much money for the work that is left. The
answer is the sum over the campaign's milestones of

    (1 + r) x E(m)

`E(m)` is the run estimate of the milestone's workflow, loaded the way the
controller loads it for round 1, against a `Prior` read from the estimate
history. `r` is the median number of REVISE rounds a milestone takes.

**`r` rests on finished milestones only.** One REVISE decision resumes the
milestone's run once, so a milestone's sample is the count of its `judged`
rounds whose decision was REVISE; a milestone that passed at its first
judging counts 0. Only a milestone that reached a PASS or an escalation is a
sample: a milestone still running has spent an unknown part of its revisions
and would drag the median down. The samples come from every `campaign.jsonl`
under the history directories and from the campaign's own log. With no
finished milestone anywhere, `r` is 0 and the output says so.

**The product is an upper bound.** A resume re-runs only the steps whose
fingerprints changed, and the rest are cached and cost nothing, while
`(1 + r) x E(m)` prices every revised round as a whole run.

**A landed milestone counts 0** and is marked `landed`, so the total is the
work that is left.

This module reads `campaign.jsonl` files and the milestone workflow modules.
It starts nothing and runs no git: the milestone workflows are built with an
empty `integration_sha`, as `campaign validate` builds them.
"""

from __future__ import annotations

import os
import statistics
from pathlib import Path
from typing import Iterable

from . import campaign as ohcamp
from . import estimate as ohestimate
from .paths import win
from .workflow import load_workflow, validate

__all__ = ["SCHEMA", "NO_CAMPAIGN_HISTORY", "FINISHED_EVENTS",
           "FINISHED_DECISIONS", "discover_campaign_roots", "revise_rounds",
           "estimate_campaign", "render_text"]

SCHEMA = "ohflow.campaign-estimate/1"
#: The line the text carries when no finished milestone was found anywhere.
NO_CAMPAIGN_HISTORY = ("campaign history: no finished milestone found, so one "
                       "round per milestone is all the forecast assumes")
#: Events that finish a milestone, in both spellings of the campaign log.
FINISHED_EVENTS = ("milestone_landed", "milestone_passed", "escalated")
#: Decisions that finish a milestone.
FINISHED_DECISIONS = ("PASS", "ESCALATE")


# ---------------------------------------------------------------- the median


def discover_campaign_roots(paths: Iterable[str | Path]) -> list[Path]:
    """Every campaign root under these paths, `HISTORY_DEPTH` levels down at
    most: a directory that holds a `campaign.jsonl`.

    A path that names a file is read as a campaign log, and its directory is
    the root. The walk is `estimate.discover_history`'s, one file name apart.
    """
    found: dict[Path, None] = {}
    for raw in paths:
        root = Path(raw)
        if root.is_file():
            found[root.resolve().parent] = None
            continue
        if not root.is_dir():
            continue
        base_depth = len(root.resolve().parts)
        for dirpath, dirnames, filenames in os.walk(root.resolve()):
            here = Path(dirpath)
            if len(here.parts) - base_depth >= ohestimate.HISTORY_DEPTH:
                dirnames[:] = []
            dirnames.sort()
            if ohcamp.CAMPAIGN_LOG in filenames:
                found[here] = None
    return list(found)


def revise_rounds(roots: Iterable[str | Path]) -> list[int]:
    """One REVISE count per finished milestone, over these campaign roots.

    Both spellings of the campaign log are read, so a campaign from before the
    rename counts too.
    """
    counts: list[int] = []
    for root in roots:
        revises: dict[str, int] = {}
        finished: set[str] = set()
        for e in ohcamp.CampaignLog(Path(root)).events():
            mid, ev = e.get("milestone"), e.get("event")
            if not mid:
                continue
            revises.setdefault(mid, 0)
            if ev == "judged":
                decision = e.get("decision") or e.get("verdict")
                if decision == "REVISE":
                    revises[mid] += 1
                elif decision in FINISHED_DECISIONS:
                    finished.add(mid)
            elif ev in FINISHED_EVENTS:
                finished.add(mid)
        counts += [n for mid, n in revises.items() if mid in finished]
    return counts


# -------------------------------------------------------------- the forecast


def _times(value, factor: float, digits: int | None = None):
    """`value` times `factor`, rounded, and 0 at factor 0: what a landed
    milestone adds is zero, not the unknown its own estimate may hold."""
    if not factor:
        return 0 if digits is None else 0.0
    if value is None:
        return None
    return round(value * factor) if digits is None else round(value * factor, digits)


def _pair(pair: dict, factor: float) -> dict:
    return {which: _times(pair[which], factor) for which in ("p50", "p80")}


def _total(milestones: list[dict], field: str) -> dict:
    return {which: ohestimate._sum([e[field][which] for e in milestones])
            for which in ("p50", "p80")}


def _milestone_run(camp, m, prior: ohestimate.Prior) -> dict:
    """The run estimate of one milestone's workflow, built with the arguments
    its round 1 receives."""
    workflow = validate(load_workflow(Path(camp.root) / m.workflow,
                                      ohcamp.milestone_args(camp, m)))
    return ohestimate.estimate_workflow(workflow, prior)["run"]


def estimate_campaign(camp, prior: ohestimate.Prior,
                      history: Iterable[str | Path] = (), *,
                      now: float | None = None) -> dict:
    """The forecast of a campaign: per milestone, then the total that is left.

    `history` names campaign logs or history roots; the campaign's own root is
    read besides them, and a root named twice counts once.
    """
    roots = discover_campaign_roots([*history, camp.root])
    counts = revise_rounds(roots)
    median = round(statistics.median(counts), 3) if counts else 0
    factor = round(1 + median, 3)
    states = ohcamp.replay(camp)
    milestones = []
    for m in camp.milestones:
        run = _milestone_run(camp, m, prior)
        landed = states[m.id].status == "passed"
        scale = 0.0 if landed else factor
        milestones.append({
            "id": m.id,
            "landed": landed,
            "factor": scale,
            "run": run,
            "wall_s": _pair(run["wall_s"], scale),
            "checks_s": _pair(run["checks_s"], scale),
            "tokens": _pair(run["tokens"], scale),
            "cost_usd": _times(run["cost_usd"], scale, 4),
            "confidence": run["confidence"],
        })
    left = [e for e in milestones if not e["landed"]]
    low = (any(e["confidence"] == "low" for e in left)
           or len(counts) < ohestimate.LOW_N)
    return {
        "schema": SCHEMA,
        "generated": ohestimate._stamp(now),
        "campaign": camp.name,
        "revise": {
            "median": median,
            "factor": factor,
            "milestones": len(counts),
            "counts": sorted(counts),
            "logs": [win(root / ohcamp.CAMPAIGN_LOG) for root in roots],
        },
        "history": ohestimate.history_block(prior),
        "milestones": milestones,
        "total": {
            "milestones": len(left),
            "wall_s": _total(milestones, "wall_s"),
            "checks_s": _total(milestones, "checks_s"),
            "tokens": _total(milestones, "tokens"),
            "cost_usd": ohestimate._sum([e["cost_usd"] for e in milestones]),
            "confidence": "low" if low else "ok",
        },
    }


# ---------------------------------------------------------------- rendering


def _count(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def render_text(data: dict) -> str:
    """The block the verb prints: the verdict line, then one row per milestone
    and the total row."""
    total, revise, hist = data["total"], data["revise"], data["history"]
    wall, tokens = total["wall_s"], total["tokens"]
    name = data["campaign"]
    if wall["p50"] is None:
        head = (f"CAMPAIGN ESTIMATE {name}: {ohestimate.NO_SAMPLES} matched some "
                f"step; {hist['samples']} attempts from {hist['sources']} summaries")
    else:
        head = (f"CAMPAIGN ESTIMATE {name}: ~{ohestimate._minutes(wall['p50'])} (p50) "
                f"to {ohestimate._minutes(wall['p80'])} (p80), "
                f"{ohestimate._tokens(tokens['p50'])} tokens, "
                f"{ohestimate._cost(total['cost_usd'])} for "
                f"{_count(total['milestones'], 'milestone')} left, confidence "
                f"{total['confidence']}; REVISE median {revise['median']:g} over "
                f"{_count(revise['milestones'], 'finished milestone')}, "
                f"x{revise['factor']:.2f}; {hist['samples']} attempts from "
                f"{hist['sources']} summaries")
    lines = [head, ""]
    lines.append(ohestimate._row(["milestone", "p50", "p80", "checks p50",
                                  "tokens p50", "tokens p80", "cost", "factor",
                                  "state", "confidence"]))
    lines.append("|" + "---|" * 10)
    for e in data["milestones"]:
        lines.append(ohestimate._row([
            f"`{e['id']}`", ohestimate._minutes(e["wall_s"]["p50"]),
            ohestimate._minutes(e["wall_s"]["p80"]),
            ohestimate._minutes(e["checks_s"]["p50"]),
            ohestimate._tokens(e["tokens"]["p50"]),
            ohestimate._tokens(e["tokens"]["p80"]),
            ohestimate._cost(e["cost_usd"]), f"x{e['factor']:.2f}",
            "landed" if e["landed"] else "left", e["confidence"]]))
    lines.append(ohestimate._row([
        "total", ohestimate._minutes(wall["p50"]), ohestimate._minutes(wall["p80"]),
        ohestimate._minutes(total["checks_s"]["p50"]),
        ohestimate._tokens(tokens["p50"]), ohestimate._tokens(tokens["p80"]),
        ohestimate._cost(total["cost_usd"]), "",
        f"{total['milestones']} left of {len(data['milestones'])}",
        total["confidence"]]))
    if not revise["milestones"]:
        lines.append(NO_CAMPAIGN_HISTORY)
    for problem in hist.get("problems") or []:
        lines.append(f"history: {problem}")
    return "\n".join(lines)

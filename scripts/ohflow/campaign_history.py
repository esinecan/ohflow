"""`ohflow campaign history`: every milestone round, with its decision and reason.

One call lists each judged round of a campaign: the decision, the judge's
reason, the revision commit, the acceptance-check result and the run directory.
The facts sit in three files, and this module joins them:

* the campaign log, `campaign.jsonl`: the decision, the run directory, the
  revision commit, and the escalations, grants and landings;
* the judge handover: the reason is its lead paragraph, the text between the
  `# ` title and the next heading. Not the `summary` of the `judged` event:
  the handover is what the judge wrote for the next reader;
* the round's packet: the acceptance checks the controller ran.

It reads files only. It never starts anything and never runs git.

Rules this module keeps, and why:

* **It reads both spellings of the campaign log.** Campaigns from before the
  rename write `attempt`, `verdict` and `milestone_passed` where new ones write
  `round`, `decision` and `milestone_landed`. Their campaign modules may no
  longer import, so the CLI also takes a campaign folder.
* **Every line carries its evidence**: a `campaign.jsonl` line, or the
  handover's path.
* **The output is bounded.** A reason or an escalation is cut to `REASON_CAP`
  characters before its pointer; the pointer is never cut. The whole text is
  at most `TEXT_CAP` characters, and a cut never splits a round from its
  reason line.

The spec is `docs/history/orchestrator-visibility.md`, "Utility 5".
"""

from __future__ import annotations

from pathlib import Path

from . import campaign as ohcamp
from .activity import one_line
from .paths import win

__all__ = ["REASON_CAP", "TEXT_CAP", "CUT_LINE", "history", "handover_lead",
           "packet_checks", "render"]

REASON_CAP = 300
TEXT_CAP = 8000
CUT_LINE = "(cut at 8,000 characters; narrow with --milestone or read --json)"
#: The packet section that holds the acceptance checks, new spelling first.
CHECK_SECTIONS = ("## Acceptance checks the controller ran",
                  "## Exit checks the driver ran")
#: Log events shown beside the rounds, and the name each one prints as.
EVENTS = {"escalated": "escalated", "granted": "granted",
          "milestone_landed": "landed", "milestone_passed": "landed"}


def _first(e: dict, *keys):
    """The value of the first key the event carries, new spelling first."""
    for key in keys:
        if e.get(key) is not None:
            return e[key]
    return None


def handover_lead(path) -> str | None:
    """The lead paragraph of a judge handover, whitespace collapsed.

    The lead is the text between the `# ` title line and the next line that
    starts with `#`. YAML front matter between `---` lines comes first and is
    never the lead. None when the file is unreadable or has no lead.
    """
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError):
        return None
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines) and lines[i].strip() == "---":
        close = next((k for k in range(i + 1, len(lines))
                      if lines[k].strip() == "---"), len(lines))
        i = close + 1
    title = next((k for k in range(i, len(lines))
                  if lines[k].startswith("# ")), None)
    if title is None:
        return None
    body: list[str] = []
    for line in lines[title + 1:]:
        if line.startswith("#"):
            break
        body.append(line)
    return " ".join(" ".join(body).split()) or None


def _exit_code(text: str) -> int | None:
    try:
        return int(text.split()[0])
    except (IndexError, ValueError):
        return None                    # `None`: the check never finished


def packet_checks(path) -> list[dict] | None:
    """The acceptance checks a packet records, as `{name, exit}` rows.

    An empty list when the milestone defines none. None when the packet is
    missing or has no check section. The section is the last line that reads
    exactly as a section heading: the step handovers quoted earlier in a
    packet may hold anything, a cut fence included. Inside the section, a
    fenced command tail is never read as a heading.
    """
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError):
        return None
    starts = [k for k, line in enumerate(lines)
              if line.strip() in CHECK_SECTIONS]
    if not starts:
        return None
    checks: list[dict] = []
    fenced = False
    for line in lines[starts[-1] + 1:]:
        if line.startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        if line.startswith("## "):
            break
        if line.startswith("### "):
            name, sep, code = line[4:].rpartition(": exit ")
            if sep:
                checks.append({"name": name.strip(), "exit": _exit_code(code)})
    return checks


def history(root: Path, *, name: str | None = None,
            milestone_order: list[str] | None = None,
            milestone: str | None = None) -> dict:
    """Every judged round and every escalation, grant and landing, by milestone.

    `milestone_order` is the campaign module's order; a milestone the log names
    and the module does not follows, in order of first appearance, as every
    milestone does without a module. `milestone` keeps that one only.
    """
    root = Path(root)
    entries = ohcamp.CampaignLog(root).numbered()
    commits = {(e.get("milestone"), _first(e, "round", "attempt")): e.get("commit")
               for _n, e in entries if e.get("event") == "revision_committed"}
    found: dict[str, dict] = {}
    run_dirs: dict[str, str | None] = {}
    for n, e in entries:
        mid, ev = e.get("milestone"), e.get("event")
        if not mid or (milestone and mid != milestone):
            continue
        if ev == "milestone_started":
            run_dirs[mid] = e.get("run_dir")
            continue
        if ev != "judged" and ev not in EVENTS:
            continue
        m = found.setdefault(mid, {"id": mid, "rounds": [], "events": []})
        if ev == "judged":
            m["rounds"].append(_round(e, n, run_dirs.get(mid), commits))
        elif EVENTS[ev] == "escalated":
            m["events"].append({"event": "escalated", "why": e.get("why"),
                                "log_line": n})
        elif ev == "granted":
            m["events"].append({"event": "granted",
                                "revisions": e.get("revisions"), "log_line": n})
        else:
            m["events"].append({"event": "landed", "log_line": n})
    order = [i for i in milestone_order or [] if i in found]
    order += [i for i in found if i not in order]
    return {"campaign": name or root.name,
            "milestones": [found[i] for i in order]}


def _round(e: dict, line: int, run_dir: str | None, commits: dict) -> dict:
    number = _first(e, "round", "attempt")
    handover = e.get("handover")
    if not handover or not Path(handover).is_file():
        handover = None
    return {
        "round": number,
        "decision": _first(e, "decision", "verdict"),
        "reason": handover_lead(handover) if handover else None,
        "handover": handover,
        "checks": packet_checks(e["packet"]) if e.get("packet") else None,
        "revision": commits.get((e.get("milestone"), number)),
        "run_dir": run_dir,
        "judge_dir": e.get("judge_dir"),
        "log_line": line,
    }


# ------------------------------------------------------------------ text


def _count(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _at(line: int) -> str:
    return f"{ohcamp.CAMPAIGN_LOG}:{line}"


def _checks(checks: list[dict] | None) -> str:
    if checks is None:
        return "checks unknown"
    if not checks:
        return "checks none"
    failed = [c["name"] for c in checks if c["exit"] != 0]
    tail = f" (failed: {', '.join(failed)})" if failed else ""
    return f"checks {len(checks) - len(failed)}/{len(checks)} passed{tail}"


def _round_lines(mid: str, r: dict) -> list[str]:
    parts = [f"{mid} round {r['round'] if r['round'] is not None else '?'}: "
             f"{r['decision'] or 'NO DECISION'}", _checks(r["checks"])]
    if r["revision"]:
        parts.append(f"revision {r['revision'][:10]}")
    if r["run_dir"]:
        parts.append(f"run {win(r['run_dir'])}")
    parts.append(_at(r["log_line"]))
    if r["reason"]:
        why = f"  reason: {one_line(r['reason'], REASON_CAP)} · {win(r['handover'])}"
    elif r["handover"]:
        why = f"  reason: the handover has no lead paragraph · {win(r['handover'])}"
    else:
        judge = f" · judge {win(r['judge_dir'])}" if r["judge_dir"] else ""
        why = f"  reason: no handover file{judge}"
    return [" · ".join(parts), why]


def _event_line(mid: str, ev: dict) -> str:
    if ev["event"] == "escalated":
        what = f"escalated: {one_line(ev.get('why') or '', REASON_CAP)}"
    elif ev["event"] == "granted":
        what = f"granted {_count(int(ev.get('revisions') or 0), 'revision')}"
    else:
        what = "landed"
    return f"{mid} {what} · {_at(ev['log_line'])}"


def render(data: dict) -> list[str]:
    """The text lines of one history, capped by `cap_text`.

    Each milestone's rounds and events print together, in log order.
    """
    milestones = data["milestones"]
    rounds = [r for m in milestones for r in m["rounds"]]
    decisions = [r["decision"] for r in rounds]
    head = (f"HISTORY {data['campaign']}: "
            f"{_count(len(milestones), 'milestone')}, "
            f"{_count(len(rounds), 'round')}, {decisions.count('REVISE')} REVISE, "
            f"{decisions.count('ESCALATE')} ESCALATE · {ohcamp.CAMPAIGN_LOG}")
    blocks: list[list[str]] = []
    for m in milestones:
        items = [(r["log_line"], _round_lines(m["id"], r)) for r in m["rounds"]]
        items += [(ev["log_line"], [_event_line(m["id"], ev)])
                  for ev in m["events"]]
        blocks += [lines for _line, lines in sorted(items)]
    return cap_text(head, blocks)


def cap_text(head: str, blocks: list[list[str]]) -> list[str]:
    """`head`, then whole blocks while the text fits in TEXT_CAP characters.

    A cut keeps the head and ends with CUT_LINE. A round and its reason line
    are one block, so a cut never leaves a round without its reason.
    """
    lines = [head] + [line for block in blocks for line in block]
    if len("\n".join(lines)) <= TEXT_CAP:
        return lines
    out = [head]
    size = len(head) + 1 + len(CUT_LINE)
    for block in blocks:
        cost = sum(len(line) + 1 for line in block)
        if size + cost > TEXT_CAP:
            break
        out += block
        size += cost
    return out + [CUT_LINE]

"""`ohflow watch` and `ohflow campaign watch`: report only what is new.

A watcher keeps a cursor in the run directory (or the campaign root) under a
name, `agent` by default. The cursor holds the last facts the watcher reported.
A repeated call compares the facts now with the cursor and prints the
difference, so an agent that polls never reads the same line twice.

A run watch also carries what the dashboard's attention strip and digest say,
because the orchestrating agent acts on them and the dashboard's own route
lives only while the dashboard serves. The cursor remembers the attention
items reported, by key, and the highest run-log line reported as a digest
entry. Each new entry and each new or cleared item is one line with its
run-log line, so the agent can open the evidence without the page payload.
A cursor that holds no attention keys yet has reported nothing, so the items
its first look finds were there before it: their lines say `standing`.

A run watch also prints one `phase boundary:` line for each phase that
settled since the cursor last looked. The line names the file that holds the
phase boundary check, for an orchestrator whose harness dropped the skill
body. A cursor that holds no phases yet gets the line for the newest settled
phase only.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import attention as ohattention
from . import dashboard_data as ohdata
from . import exit_report as ohexit
from . import live, proc, rundir, runstatus
from . import pilot as ohpilot
from .paths import win
from .supervisor import go_command

EXIT_ENDED_GOOD, EXIT_ENDED_BAD, EXIT_UNKNOWN, EXIT_GOING = 0, 1, 2, 10
#: A run directory that holds a workflow and no sign of a launch.
EXIT_NOT_STARTED = 3
CURSOR_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
#: Every digest and attention line is cut to this many characters. The text
#: gives way first, so the run-log pointer at the end survives.
LINE_CAP = 300
#: What an attention line keeps of its observation when a whole next command
#: leaves no room under the cap.
MIN_OBSERVED = 40
#: How long a stopped run's supervisor may take to write its own exit report.
EXIT_REPORT_WAIT_S = 10.0
#: A run with no run log and no supervisor may be a launch that has just
#: returned. After this long without a file change it is a launch that died.
NEVER_STARTED_GRACE_S = 30.0

#: Where a `phase boundary:` line sends its reader.
BOUNDARY_POINTER = (" · next: the phase boundary check in "
                    "references/monitor-a-run.md")
#: The states of a phase that has not settled.
OPEN_PHASE_STATES = frozenset({"waiting", "running"})

# Tests replace these two so a watch never sleeps for real.
_sleep = time.sleep
_clock = time.monotonic


@dataclass
class Watched:
    """What one watch call has to say. The CLI prints `lines`, or `data`."""

    code: int
    lines: list[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)


def check_cursor_name(name: str) -> str:
    if not CURSOR_NAME.match(name or ""):
        raise ValueError(f"cursor name {name!r} must use letters, digits, "
                         f"'_' and '-' only")
    return name


def _cursor_path(root: Path, name: str) -> Path:
    return Path(root) / f".watch.{check_cursor_name(name)}.json"


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _read_cursor(path: Path, root: Path) -> dict:
    stored = _read_json(path) or {}
    owner = stored.get("root")
    if owner is not None and owner != str(Path(root).resolve()):
        return {}
    return stored


def _write_cursor(path: Path, data: dict) -> None:
    try:
        path.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass


# ------------------------------------------------------------------ one run


def is_run_dir(run_dir: Path) -> bool:
    return Path(run_dir).is_dir() and any(
        (Path(run_dir) / n).exists()
        for n in ("run-log.jsonl", "workflow.json", "run.json",
                  ".ohflow-handoff.json"))


def _exit_status(run_dir: Path) -> str | None:
    return (rundir.exit_record(run_dir) or {}).get("status")


def _exit_error(run_dir: Path) -> str | None:
    """The first line of the `error` that `exit.json` records, or None."""
    error = (rundir.exit_record(run_dir) or {}).get("error")
    lines = str(error or "").strip().splitlines()
    return lines[0] if lines else None


def _exit_report(run_dir: Path, read_out: dict) -> tuple[Path | None, str | None]:
    """The exit report's path and verdict. An orphaned run gets one written."""
    written = _exit_status(run_dir)
    if written is None or written == "running":
        deadline = _clock() + EXIT_REPORT_WAIT_S
        while read_out["run"].get("supervisor_alive") and _clock() < deadline:
            _sleep(0.5)
            written = _exit_status(run_dir)
            if written not in (None, "running"):
                break
            read_out = live.read_out(run_dir)
        if written is None or written == "running":
            _info, paths, verdict = ohexit.rebuild(run_dir)
            return paths["html"], verdict
    verdict = (rundir.exit_record(run_dir) or {}).get("verdict")
    return run_dir / "exit-report.html", verdict


def _idle_seconds(run_dir: Path) -> float:
    """Seconds since the newest file in the run directory changed. A watcher's
    own cursor files do not count: each call would reset the clock."""
    newest = 0.0
    for entry in Path(run_dir).iterdir():
        if entry.is_file() and not entry.name.startswith(".watch."):
            try:
                newest = max(newest, entry.stat().st_mtime)
            except OSError:
                pass
    return time.time() - newest if newest else 0.0


def _never_launched(run_dir: Path, status: str) -> bool:
    """A `not started` run with no handoff file.

    The run reader names a run with a live engine `starting`, so `not started`
    means no engine lives. A detached launch leaves `.ohflow-handoff.json` at
    once. A directory with neither is no launch in flight, so waiting cannot
    change what it is."""
    return (status == runstatus.NOT_STARTED
            and not (run_dir / ".ohflow-handoff.json").exists())


# ------------------------------------------------- attention and the digest


def attention_key(item: dict) -> str:
    """`group|kind|coord|attempt`: what the cursor stores per item reported.

    A run-level item has no coordinate and no attempt; those parts are empty.
    The key holds no text, so a reworded item is not a new one.
    """
    return "|".join("" if item.get(k) is None else str(item[k])
                    for k in ("group", "kind", "coord", "attempt"))


def _fit(body: str, tail: str = "") -> str:
    """`body` then `tail` in at most `LINE_CAP` characters; the body gives way."""
    body = " ".join(str(body).split())
    room = LINE_CAP - len(tail)
    if len(body) > room:
        body = body[:max(0, room - 3)] + "..."
    return body + tail


def _evidence(line) -> str:
    return f" · run-log.jsonl:{line}" if isinstance(line, int) else ""


def _digest_line_no(entry: dict) -> int:
    line = (entry.get("evidence") or {}).get("line")
    return line if isinstance(line, int) else -1


def digest_line(entry: dict) -> str:
    """`digest: <text> · run-log.jsonl:<line>`."""
    return _fit(f"digest: {entry.get('text') or entry.get('kind')}",
                _evidence(_digest_line_no(entry)))


def attention_line(item: dict, standing: bool = False) -> str:
    """`attention <group>: <observed> · next: <command or text> · run-log.jsonl:<line>`.

    A `standing` item was there before the cursor first looked, so its line
    starts `attention standing <group>: `.

    The observation gives way first when the line is too long: the next
    command is what the reader acts on, and the pointer is how it checks.
    A command is never cut, because a cut command cannot be run: when the
    command alone fills the cap, the observation keeps `MIN_OBSERVED`
    characters and the line runs past `LINE_CAP`. Next text that is not a
    command gives way like any text.
    """
    nxt = item.get("next") or {}
    command = " ".join(str(nxt.get("command") or "").split())
    step = command or " ".join(str(nxt.get("text") or "").split())
    head = f"attention {'standing ' if standing else ''}{item.get('group')}: "
    observed = " ".join(str((item.get("observed") or {}).get("text")
                            or "").split())
    next_part = f" · next: {step}" if step else ""
    tail = _evidence((item.get("evidence") or {}).get("line"))
    room = LINE_CAP - len(head) - len(next_part) - len(tail)
    if room < MIN_OBSERVED:
        if not command:
            return _fit(head + observed + next_part, tail)
        room = MIN_OBSERVED
    if len(observed) > room:
        observed = observed[:room - 3] + "..."
    return head + observed + next_part + tail


def cleared_line(key: str) -> str:
    """`attention cleared: <kind> <coord, or "run">`."""
    _group, kind, coord, _attempt = (key.split("|") + ["", "", "", ""])[:4]
    return _fit(f"attention cleared: {kind} {coord or 'run'}")


def boundary_line(phase: dict) -> str:
    """`phase boundary: phase <number> <name> settled <status> · next: the
    phase boundary check in references/monitor-a-run.md`."""
    number = str(phase.get("coord") or "").split(".", 1)[0]
    return _fit(f"phase boundary: phase {number} {phase.get('name')} settled "
                f"{phase.get('state')}", BOUNDARY_POINTER)


def _settled_phases(read_out: dict) -> list[dict]:
    return [p for p in read_out.get("phases") or []
            if p.get("state") not in OPEN_PHASE_STATES]


def _rank(group: str) -> int:
    groups = ohattention.GROUPS
    return groups.index(group) if group in groups else len(groups)


def _pilot_key(run_dir: Path) -> str | None:
    record = ohpilot.read_pilot(run_dir)
    if record is None:
        return None
    return f"{record.get('state')}|{record.get('generated')}"


def watch_run(run_dir: Path, *, timeout: float = 300.0, until: str = "change",
              cursor: str = "agent", poll: float = 2.0) -> Watched:
    """Wait for news about one run, then say what is new and what the run is.

    `until`: `change` returns on any new line, `end` only when the run stops,
    and `attention` when a new `intervention` item appears or the run stops.
    Every mode returns at the timeout.
    """
    run_dir = Path(run_dir).resolve()
    if not is_run_dir(run_dir):
        return Watched(EXIT_UNKNOWN, [f"no run at {win(run_dir)}"])
    path = _cursor_path(run_dir, cursor)
    stored = _read_cursor(path, run_dir)
    previous = stored.get("facts")
    # A cursor written before the attention and digest keys existed keeps its
    # step facts and reads as a first call for the two lists.
    seen = stored.get("attention")
    standing = not isinstance(seen, list)
    seen = [] if standing else [str(k) for k in seen]
    mark = stored.get("digest_line")
    first_digest = not isinstance(mark, int)
    mark = mark if isinstance(mark, int) else 0
    pilot_seen = stored.get("pilot")
    past = stored.get("phases")
    first_phases = not isinstance(past, list)
    past = [] if first_phases else [str(c) for c in past]
    boundaries: dict[str, str] = {}
    deadline = _clock() + max(0.0, timeout)
    lines: list[str] = []
    digest: list[dict] = []
    notices: list[tuple[int, str]] = []
    items: list[dict] = []
    new_keys: list[str] = []
    alarm = False
    while True:
        read_out = live.read_out(run_dir)
        now = runstatus.facts(read_out)
        lines += runstatus.changes(previous, now, read_out)
        previous = now
        view = ohdata.agent_view(run_dir) or {"attention": [], "digest": []}
        fresh = [e for e in view["digest"] if _digest_line_no(e) > mark]
        digest += fresh
        mark = max([mark] + [_digest_line_no(e) for e in fresh])
        items = view["attention"]
        keys = [attention_key(i) for i in items]
        arrived = [i for i, k in zip(items, keys) if k not in seen]
        gone = [k for k in seen if k not in keys]
        notices += [(_rank(i["group"]), attention_line(i, standing))
                    for i in arrived]
        if not standing:
            new_keys += [attention_key(i) for i in arrived]
        standing = False
        notices += [(_rank(k.split("|")[0]), cleared_line(k)) for k in gone]
        seen = keys
        alarm = alarm or any(i["group"] == "intervention" for i in arrived)
        settled = _settled_phases(read_out)
        crossed = [p for p in settled if p["coord"] not in past]
        for phase in crossed[-1:] if first_phases else crossed:
            boundaries[phase["coord"]] = boundary_line(phase)
        first_phases = False
        past = [p["coord"] for p in settled]
        pilot_now = _pilot_key(run_dir)
        pilot_news = pilot_now != pilot_seen
        pilot_seen = pilot_now
        news = bool(lines or digest or notices or boundaries or pilot_news)
        stopped = read_out["run"]["status"] in runstatus.STOPPED_STATUSES
        unlaunched = _never_launched(run_dir, read_out["run"]["status"])
        never = (read_out["run"]["status"] == runstatus.NOT_STARTED
                 and _idle_seconds(run_dir) > NEVER_STARTED_GRACE_S)
        if stopped or never or unlaunched or (until == "change" and news) \
                or (until == "attention" and alarm) or _clock() >= deadline:
            break
        _sleep(poll)
    _write_cursor(path, {"root": str(run_dir), "facts": now,
                         "attention": seen, "digest_line": mark,
                         "pilot": pilot_seen, "phases": past})

    shown, cut = digest, []
    if first_digest and len(digest) > runstatus.FIRST_CALL_LINES:
        # The newest entries say where the run is, so they stay.
        shown = digest[-runstatus.FIRST_CALL_LINES:]
        cut = [f"... {len(digest) - len(shown)} earlier digest entries "
               f"not shown"]
    notices.sort(key=lambda notice: notice[0])
    news_lines = (cut + [digest_line(e) for e in shown]
                  + [line for _rank_no, line in notices]
                  + list(boundaries.values()))

    status = read_out["run"]["status"]
    sentence = runstatus.sentence(read_out, run_dir)
    head = sentence
    url = runstatus.dashboard_url(run_dir, read_out)
    if url and not stopped:
        head += f" · dashboard: {url}"
    out = [head] + lines + news_lines
    data = {"status": status, "sentence": sentence,
            "changes": list(lines), "dashboard": url, "facts": now,
            "attention": items, "attention_new": new_keys, "digest": shown,
            "phase_boundaries": list(boundaries)}
    if unlaunched:
        out.append("no run started here: start a run with a new --run-id, "
                   f"or delete this directory first: {win(run_dir)}")
        return Watched(EXIT_NOT_STARTED, out, data)
    if never:
        log = run_dir / "supervisor.log"
        out.append("the run never started: no supervisor and no run log; see "
                   + win(log if log.exists() else run_dir))
        return Watched(EXIT_ENDED_BAD, out, data)
    if status == rundir.HELD:
        # A held run is going, and it goes nowhere until a person releases
        # it: the watcher names the command.
        out += ohpilot.status_lines(run_dir)
        out.append(ohpilot.hold_line(run_dir)
                   or f"{live.HELD_REASON} · {go_command(run_dir)}")
        data["go"] = go_command(run_dir)
        data["pilot"] = ohpilot.read_pilot(run_dir)
        return Watched(EXIT_GOING, out, data)
    if not stopped:
        return Watched(EXIT_GOING, out, data)

    report, verdict = _exit_report(run_dir, read_out)
    read_out = live.read_out(run_dir)
    if verdict:
        out.append(verdict)
    error = _exit_error(run_dir) if status == "crashed" else None
    if error:
        out.append(error)
    if report is not None:
        out.append(f"exit report: {win(report)}")
    resume = read_out["run"].get("resume_command")
    if resume:
        out.append(f"resume: {resume}")
    n = runstatus.tally([runstatus.step_status(a) for a in read_out["agents"]])
    good = status == "finished" and n["passed"] == n["total"]
    data.update(verdict=verdict, exit_report=str(report) if report else None,
                resume=resume)
    return Watched(EXIT_ENDED_GOOD if good else EXIT_ENDED_BAD, out, data)


# ---------------------------------------------------------------- a campaign


def _short(text, limit: int = 100) -> str:
    first = " ".join(str(text or "").split())
    return first if len(first) <= limit else first[:limit - 3] + "..."


def event_line(e: dict) -> str | None:
    """One line for one campaign log event, or None for an event with no news."""
    m, ev = e.get("milestone", ""), e.get("event")
    if ev == "campaign_started":
        return f"campaign started: {len(e.get('milestones') or [])} milestones"
    if ev == "milestone_started":
        return f"{m} started"
    if ev == "judged":
        why = _short(e.get("summary"))
        return (f"{m} judged round {e.get('round')}: {e.get('decision')}"
                + (f" - {why}" if why else ""))
    if ev == "revision_committed":
        return f"{m} revision committed at {str(e.get('commit') or '')[:10]}"
    if ev == "milestone_landed":
        return f"{m} passed"
    if ev == "escalated":
        return f"{m} escalated: {_short(e.get('why'))}"
    if ev == "preflight_failed":
        return f"{m} did not start: {_short(e.get('problem'))}"
    if ev == "run_paused":
        return f"{m} paused, a provider deferred it: {_short((e.get('deferred') or [''])[0])}"
    if ev == "granted":
        return f"{m} granted {e.get('revisions')} revisions"
    if ev == "campaign_delivered":
        return "campaign delivered"
    return None


def _controller_alive(root: Path) -> bool | None:
    """Whether the detached controller lives. None when no pid file names one."""
    pid_file = Path(root) / "campaign.pid"
    try:
        pid = int(pid_file.read_text(encoding="ascii").strip())
        written = pid_file.stat().st_mtime
    except (OSError, ValueError):
        return None
    return proc.pid_alive(pid, started_before=written)


def _campaign_status(root: Path) -> dict:
    from . import campaign as ohcamp

    try:
        return ohcamp.read_status(Path(root)) or {}
    except (OSError, ValueError):
        return {}


def _held_go(root: Path, current) -> str | None:
    """The go command of the round the controller holds now, else None."""
    if current is None:
        return None
    rec = _campaign_status(root)
    if rec.get("state") == "held" and rec.get("milestone") == current.id:
        return rec.get("go") or None
    return None


def _judging_round(root: Path, current, states) -> int | None:
    """The round being judged now, from the controller's status file, else None.

    The campaign log has no judging event. A status file that names a round other
    than the next one to judge is left over from an earlier state."""
    if current is None:
        return None
    rec = _campaign_status(root)
    round_no = rec.get("round")
    if rec.get("state") == "judging" and rec.get("milestone") == current.id \
            and round_no == states[current.id].judgements + 1:
        return round_no
    return None


def watch_campaign(camp, *, timeout: float = 300.0, cursor: str = "agent",
                   poll: float = 2.0) -> Watched:
    """Wait for campaign log news, then print each new event and the status."""
    from . import campaign as ohcamp

    root = Path(camp.root)
    path = _cursor_path(root, cursor)
    seen = _read_cursor(path, root)
    seen_events = int(seen.get("events") or 0)
    seen_urls = list(seen.get("urls") or [])
    first_call = not seen
    deadline = _clock() + max(0.0, timeout)
    lines: list[str] = []
    while True:
        events = ohcamp.CampaignLog(root).events()
        for e in events[seen_events:]:
            line = event_line(e)
            if line:
                lines.append(line)
        if first_call and len(lines) > runstatus.FIRST_CALL_LINES:
            # The newest events say where the campaign is, so they stay.
            left_out = len(lines) - runstatus.FIRST_CALL_LINES
            lines = [f"... {left_out} earlier events not shown"] \
                + lines[-runstatus.FIRST_CALL_LINES:]
        first_call = False
        seen_events = len(events)
        states = ohcamp.replay(camp)
        current = next((m for m in camp.milestones
                        if states[m.id].status != "passed"), None)
        judging = _judging_round(root, current, states)
        runs: list[Path] = []
        judge_run: Path | None = None
        if current is not None:
            if states[current.id].run_dir:
                runs.append(Path(states[current.id].run_dir))
            judged = judging or states[current.id].judgements
            if judged:
                judge_run = ohcamp.judge_run_dir(root, current, judged)
                if judge_run.is_dir():
                    runs.append(judge_run)
        url = None
        for run in runs:
            found = runstatus.dashboard_url(run)
            if found:
                url = found
                if found not in seen_urls:
                    seen_urls.append(found)
                    lines.append(f"dashboard: {found}")
        passed = sum(1 for s in states.values() if s.status == "passed")
        escalated = any(s.status == "escalated" for s in states.values())
        delivered = passed == len(camp.milestones)
        dead = not delivered and _controller_alive(root) is False
        ended = delivered or escalated or dead
        if ended or lines or _clock() >= deadline:
            break
        _sleep(poll)
    _write_cursor(path, {"root": str(root.resolve()), "events": seen_events,
                         "urls": seen_urls})

    head = f"{camp.name}: {passed} of {len(camp.milestones)} milestones passed"
    if delivered:
        head += ", delivered"
    elif current is not None:
        st = states[current.id]
        if judging:
            head += f", {current.id} judging round {judging}"
            head += (f" · run {win(judge_run)}"
                     if judge_run is not None and judge_run.is_dir()
                     else " · starting")
        else:
            go = _held_go(root, current)
            head += f", {current.id} {'held' if go else st.status}"
            if st.run_dir:
                head += f" · run {win(Path(st.run_dir))}"
            if go:
                head += f" · go: {go}"
    out = [head] + lines
    data = {"campaign": camp.name, "passed": passed,
            "milestones": len(camp.milestones), "delivered": delivered,
            "escalated": escalated, "changes": list(lines), "dashboard": url}
    if delivered:
        return Watched(EXIT_ENDED_GOOD, out, data)
    if escalated or dead:
        if dead and not escalated:
            out.append("the campaign controller is not running")
        return Watched(EXIT_ENDED_BAD, out, data)
    return Watched(EXIT_GOING, out, data)

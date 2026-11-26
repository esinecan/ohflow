"""The exit report: what a run did, written on every exit path that runs code.

Three files in the run directory, all built from one `live.read_out`:

  exit.json         for tools: status, when, the error, the traceback tail,
                    the run id, the verdict sentence and the report file names
  exit-report.md    for agents, forum posts and the terminal
  exit-report.html  for a person: the dashboard page with the final read-out
                    embedded, so it opens from disk with no server

The Markdown and the HTML are two renderings of the same dictionary, so they
cannot disagree, and the page is the same template the live dashboard serves,
so the report looks like the last frame of the run a person was watching.

Exit paths. `supervisor.run_workflow` writes `finished`, `failed` and `paused` from
the engine's own verdict, and `crashed` or `interrupted` from the exception it
caught. A hard kill runs no code, so `ohflow report --run DIR` rebuilds the
files later and calls the run `orphaned`. None of these paths writes a run log
event: `run_finished` keeps its three statuses, and a crashed run stays exactly
as resumable as an orphaned one.
"""

from __future__ import annotations

import datetime as _dt
import base64
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from . import activity as act, cloud_spend, live, rundir, tool_output
from . import budget as ohbudget
from . import estimate as ohestimate

__all__ = ["EXIT_STATUSES", "exit_info", "exit_info_from_files", "build",
           "needs", "human_duration", "rebuild", "read_verdict",
           "render_md", "render_html", "render_timeline_svg",
           "write_exit_report", "TEMPLATE"]

EXIT_STATUSES = ("finished", "failed", "paused", "crashed", "interrupted",
                 "orphaned")

#: The page the live dashboard serves. The report embeds its data into it.
TEMPLATE = Path(__file__).resolve().parent / "dashboard.html"
STYLESHEET = TEMPLATE.with_name("dashboard.css")
JAVASCRIPT = TEMPLATE.with_name("dashboard.js")
RECORDS_JAVASCRIPT = TEMPLATE.with_name("dashboard_records.js")
BRAND_FONT = TEMPLATE.with_name("assets") / "lexend-variable.ttf"
DATA_SLOT = '<script id="ohflow-data" type="application/json">null</script>'
TIMELINE_SLOT = "<!--OHFLOW:TIMELINE-->"
STYLE_SLOT = ('<link rel="stylesheet" href="/dashboard.css" '
              'data-ohflow-asset="style">')
RECORDS_SLOT = ('<script src="/dashboard_records.js" '
                'data-ohflow-asset="records"></script>')
SCRIPT_SLOT = ('<script src="/dashboard.js" '
               'data-ohflow-asset="script"></script>')

#: The verdict lists the non-passing statuses in this order.
_ORDER = ("quarantined", "failed", "timeout", "deferred", "skipped",
          "interrupted", "running", "pending")
_GOOD = frozenset({"passed", "cached"})


def _utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def exit_info(status: str, error: BaseException | str | None = None,
              traceback_text: str | None = None) -> dict:
    """What `supervisor.run_workflow` knows at exit, in the shape `exit.json`
    records."""
    if isinstance(error, BaseException):
        text = f"{type(error).__name__}: {error}".rstrip(": ")
    else:
        text = error
    tail = (traceback_text or "").rstrip().splitlines()[-20:]
    return {"status": status, "error": text or None, "traceback_tail": tail}


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def exit_info_from_files(run_dir: Path) -> dict:
    """The exit status the files support, for `ohflow report`.

    `run_finished` names it when the run log has one. Without it, a crash or
    an interrupt that `run_workflow` already reported keeps its own status and its
    error, a live supervisor means the run is still going, and anything else
    is a run whose supervisor died without writing a word: `orphaned`.
    """
    run_dir = Path(run_dir)
    run = rundir.open_run(run_dir)
    if run.state.status in ("finished", "failed", "paused"):
        return exit_info(run.state.status)
    prior = run.exit_record()
    if prior and prior.get("status") in ("crashed", "interrupted"):
        return {"status": prior["status"], "error": prior.get("error"),
                "traceback_tail": list(prior.get("traceback_tail") or [])}
    if run.status == rundir.ORPHANED:
        return exit_info("orphaned",
                         "the supervisor stopped without finishing the run and "
                         "wrote no exit report: a hard kill or a machine restart")
    return exit_info("running",
                     "the supervisor is still running; this report is a "
                     "read-out of the run so far, and the run replaces it "
                     "when it stops")


# ------------------------------------------------------------ the numbers


def human_duration(seconds: float | None) -> str:
    if seconds is None:
        return "unknown time"
    s = int(round(seconds))
    if s < 60:
        return f"{s} s"
    m = int(round(s / 60))
    if m < 60:
        return f"{m} min"
    return f"{m // 60} h {m % 60} min"


def _human_tokens(n: int) -> str:
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        return f"{n / 1000:.1f} k"
    return f"{n / 1_000_000:.1f} M"


def _total(tokens: dict | None) -> int:
    """The live read-out's token total. `input` already counts the cache."""
    t = tokens or {}
    return int(t.get("input") or 0) + int(t.get("output") or 0)


def _numbers(read_out: dict, summary: dict | None) -> dict:
    """Statuses, restarts, duration and tokens: from `summary.json` when it
    exists, and from the run-log-built read-out when it does not."""
    statuses: list[str] = []
    restarts = 0
    tokens = 0
    duration = None
    if isinstance(summary, dict) and summary.get("phases"):
        for item in rundir.walk_summary(summary):
            statuses.append(str(item.step.get("status") or "pending"))
            for att in item.executions:
                if isinstance(att.get("attempt"), int) and att["attempt"] >= 2:
                    restarts += 1
                tokens += (rundir.Run.usage(att) or {}).get(
                    "total_tokens") or 0
        start = act.epoch(summary.get("started"))
        end = act.epoch(summary.get("finished"))
        if start is not None and end is not None:
            duration = end - start
    else:
        for a in read_out["agents"]:
            status = a["engine_status"]
            if a["display"]["label"] == "INTERRUPTED":
                status = "interrupted"
            statuses.append(status)
            restarts += sum(1 for r in live.agent_attempts(a) if r["n"] >= 2)
        tokens = _total(read_out["run"].get("tokens"))
    if duration is None:
        duration = read_out["run"].get("elapsed_s")
    return {"statuses": statuses, "restarts": restarts, "tokens": tokens,
            "duration": duration}


def verdict(read_out: dict, summary: dict | None) -> str:
    """One sentence, spec §11 item 1."""
    n = _numbers(read_out, summary)
    counts = Counter(n["statuses"])
    total = len(n["statuses"])
    good = sum(counts[s] for s in _GOOD)
    parts = [f"{good} of {total} agents passed"]
    for status in _ORDER:
        if counts.get(status):
            parts.append(f"{counts[status]} {status}")
    for status, count in sorted(counts.items()):
        if status not in _GOOD and status not in _ORDER:
            parts.append(f"{count} {status}")
    r = n["restarts"]
    parts.append(f"{r} restart{'' if r == 1 else 's'}")
    parts.append(human_duration(n["duration"]))
    parts.append(f"{_human_tokens(n['tokens'])} tokens")
    check = read_out.get("cloudflare")
    if isinstance(check, dict):
        billed = check.get("billed_usd")
        reported = f"${check.get('reported_usd') or 0:.4f}"
        if not isinstance(billed, (int, float)):
            parts.append(f"Cloudflare containers {reported} reported, meters unread")
        elif check.get("lag_note"):
            parts.append(f"Cloudflare containers {reported} reported, "
                         f"${billed:.4f} billed so far")
        else:
            parts.append(f"Cloudflare containers ${billed:.4f} billed")
    ledger = read_out.get("token_budget")
    if isinstance(ledger, dict):
        if ledger.get("overshoot_tokens"):
            parts.insert(0, f"token budget overshot by "
                            f"{ledger['overshoot_tokens']} tokens")
        parts.append(f"token budget {ledger.get('settled_tokens')} of "
                     f"{ledger.get('limit_tokens')} settled")
    return f"Run {read_out['run']['id']} {read_out['run']['status']}: " + \
        ", ".join(parts) + "."


def needs(read_out: dict, run_dir: Path) -> list[dict]:
    """Spec §11 item 2: what a person must act on, each with its command."""
    out: list[dict] = []
    run = read_out["run"]
    ledger = read_out.get("token_budget")
    if isinstance(ledger, dict) and ledger.get("overshoot_tokens"):
        where = ", ".join(f"`{o.get('key')}` {o.get('overshoot_tokens')}"
                          for o in ledger.get("overshoots") or [])
        out.append({"text": f"The token budget overshot by "
                            f"{ledger['overshoot_tokens']} tokens: "
                            f"{ledger.get('settled_tokens')} settled against "
                            f"a limit of {ledger.get('limit_tokens')} ({where}). "
                            f"Usage arrived after the step could be stopped."})
    if isinstance(ledger, dict) and ledger.get("refused"):
        out.append({"text": f"{len(ledger['refused'])} agent step(s) were not "
                            f"admitted because the token budget is spent; raise "
                            f"`--token-budget` and resume to run them."})
    for a in read_out["agents"]:
        status = a["engine_status"]
        where = f"`{a['coord']}`"
        if a.get("excluded"):
            out.append({"text": f"{where} is excluded from this run directory "
                                f"after repeated failures: {a['display']['reason']}"})
        elif status in ("quarantined", "failed", "timeout"):
            branch = f" on branch `{a['branch']}`" if a.get("branch") else ""
            cause = next((r["cause"] for r in reversed(live.agent_attempts(a))
                          if r.get("cause")), None) or a.get("error") or status
            out.append({"text": f"{where} {status}{branch}: {cause}"})
        elif status == "deferred":
            out.append({"text": f"{where} deferred and never judged: "
                                f"{a.get('error') or 'transient fault'}; "
                                f"`--resume` reruns it"})
        elif a["display"]["label"] == "INTERRUPTED":
            out.append({"text": f"{where} was running when the supervisor "
                                f"stopped; `--resume` starts a new attempt"})
    if run.get("resume_command") and run["status"] in (
            "paused", "crashed", "interrupted", "orphaned"):
        out.append({"text": "Resume the run with:",
                    "command": run["resume_command"]})
    revert = live.revert_command(run_dir)
    if revert:
        out.append({"text": "Tear down the worktrees when the work is kept or "
                            "dropped:", "command": revert})
    return out


def _agents_table(read_out: dict) -> list[dict]:
    rows = []
    for a in read_out["agents"]:
        gate = a.get("gate")
        if gate is None:
            gate_text = "-"
        elif gate["passed"]:
            gate_text = "passed"
        else:
            gate_text = "failed" + (f": {', '.join(gate['failed'])}"
                                    if gate["failed"] else "")
        rows.append({
            "coord": a["coord"],
            "status": a["display"]["label"],
            "lineage": a.get("lineage") or "not started",
            "wall": (human_duration(a["wall_s"]) if a.get("wall_s")
                     is not None else "-"),
            "tokens": _human_tokens(_total(a.get("tokens"))),
            "gate": gate_text,
        })
    return rows


def _evidence(read_out: dict, run_dir: Path) -> list[str]:
    paths = [str(run_dir / "run-log.jsonl")]
    if (run_dir / "summary.json").exists():
        paths.append(str(run_dir / "summary.json"))
    for a in read_out["agents"]:
        for r in live.agent_attempts(a):
            if r.get("dir"):
                paths.append(str(run_dir / Path(r["dir"])))
    return paths


def _predicted(read_out: dict, run_dir: Path) -> list[dict] | None:
    """Spec: predicted vs actual, per phase and for the run, when the run was
    estimated. None when no `estimate.json` exists, so the report never says
    "predicted" about a number nobody predicted.

    A phase's actual wall is its own clock, from `phase_started` to
    `phase_settled` in the run log; its actual tokens are the sum of its
    agents' recorded tokens, as the agents table counts them.
    """
    estimate = ohestimate.read_estimate(run_dir)
    if estimate is None:
        return None
    state = rundir.open_run(run_dir).state
    rows = []
    for phase in estimate.get("phases") or []:
        entry = state.phases.get(phase["coord"]) or {}
        start = act.epoch(entry.get("started"))
        end = act.epoch(entry.get("settled_at"))
        actual_wall = (end - start) if start is not None and end is not None else None
        agents = [a for a in read_out["agents"] if a["phase"] == phase["coord"]
                  and a["kind"] == "agent"]
        rows.append({
            "label": f"`{phase['coord']}` {phase.get('name') or ''}".rstrip(),
            "wall_p50": phase["wall_s"]["p50"], "wall_p80": phase["wall_s"]["p80"],
            "wall_actual": actual_wall,
            "tokens_p50": phase["tokens"]["p50"], "tokens_p80": phase["tokens"]["p80"],
            "tokens_actual": sum(_total(a.get("tokens")) for a in agents),
            "n": phase.get("n"), "confidence": phase.get("confidence"),
        })
    run = estimate.get("run") or {}
    rows.append({
        "label": "run", "wall_p50": (run.get("wall_s") or {}).get("p50"),
        "wall_p80": (run.get("wall_s") or {}).get("p80"),
        "wall_actual": read_out["run"].get("elapsed_s"),
        "tokens_p50": (run.get("tokens") or {}).get("p50"),
        "tokens_p80": (run.get("tokens") or {}).get("p80"),
        "tokens_actual": _total(read_out["run"].get("tokens")),
        "n": (estimate.get("history") or {}).get("samples"),
        "confidence": run.get("confidence"),
    })
    return rows


def _run_log_health(read_out: dict) -> str:
    j = read_out.get("run_log") or {}
    notes = []
    for rec in j.get("recovered") or []:
        notes.append(f"a torn final line was repaired (line "
                     f"{rec.get('line', '?')}, {rec.get('bytes', '?')} bytes)")
    if j.get("unreadable_lines"):
        notes.append(f"{j['unreadable_lines']} line(s) could not be read")
    if not notes:
        return f"healthy: {j.get('records', 0)} records, none repaired"
    return "; ".join(notes)


def build(run_dir: Path, info: dict, now: float | None = None) -> dict:
    """The final read-out, with the exit block and the report block added."""
    run_dir = Path(run_dir).resolve()
    status = info.get("status")
    final = status if status in ("crashed", "interrupted", "orphaned") \
        else None
    read_out = live.read_out(run_dir, now, final_status=final, detail=True)
    summary = _read_json(run_dir / "summary.json")
    # A resumed run that crashed still has the summary its earlier invocation
    # wrote. That summary describes a different stop, so it is used only when
    # it names this one: the same final status at the same instant.
    if not (isinstance(summary, dict)
            and summary.get("status") == read_out["run"]["status"]
            and summary.get("finished")
            and summary.get("finished") == read_out["run"].get("finished")):
        summary = None
    at = act.iso(now) if now is not None else _utcnow()
    read_out["cloudflare"] = cloud_spend.read_check(run_dir)
    read_out["token_budget"] = ohbudget.read_snapshot(run_dir)
    read_out["exit"] = live._redact_tree({
        "status": status, "at": at, "error": info.get("error"),
        "traceback_tail": list(info.get("traceback_tail") or []),
    })
    read_out["report"] = live._redact_tree({
        "verdict": verdict(read_out, summary),
        "needs": needs(read_out, run_dir),
        "agents_table": _agents_table(read_out),
        "evidence": _evidence(read_out, run_dir),
        "run_log_health": _run_log_health(read_out),
        "summary_used": isinstance(summary, dict),
        "predicted": _predicted(read_out, run_dir),
        "stopped_calls": _stopped_calls(read_out, run_dir),
        "cloudflare": (cloud_spend.report_lines(read_out["cloudflare"])
                       if read_out["cloudflare"] else None),
        "token_budget": _budget_lines(read_out["token_budget"]),
    })
    return read_out


def _budget_lines(ledger: Any) -> list[str] | None:
    if not isinstance(ledger, dict):
        return None
    lines = [
        f"- Limit: {ledger.get('limit_tokens')} tokens, "
        f"{ledger.get('reserve_tokens')} reserved per agent attempt.",
        f"- Live usage: {ledger.get('settled_tokens')} tokens settled, "
        f"{ledger.get('observed_tokens')} observed.",
        f"- Overshoot: {ledger.get('overshoot_tokens') or 0} tokens.",
    ]
    for o in ledger.get("overshoots") or []:
        lines.append(f"  - `{o.get('key')}`: {o.get('used_tokens')} used on a "
                     f"grant of {o.get('grant_tokens')}, "
                     f"{o.get('overshoot_tokens')} past the limit")
    if ledger.get("stopped"):
        lines.append("- Stopped at their grant: "
                     + ", ".join(f"`{k}`" for k in ledger["stopped"]) + ".")
    if ledger.get("refused"):
        lines.append(f"- Not admitted: {len(ledger['refused'])} agent attempt(s).")
    if ledger.get("unknown_usage"):
        lines.append("- Usage unreadable, charged at the larger of grant and "
                     "live usage: "
                     + ", ".join(f"`{k}`" for k in ledger["unknown_usage"]) + ".")
    lines.append(f"- Billing estimate: ${ledger.get('billing_estimate_usd') or 0:.4f} "
                 f"from {ledger.get('billing_priced_attempts') or 0} priced "
                 f"attempt(s); {ledger.get('billing_unpriced_attempts') or 0} "
                 f"unpriced. The budget never reads this figure.")
    return lines


def _stopped_calls(read_out: dict, run_dir: Path) -> dict[str, dict]:
    """Per failed attempt: the tool call open when it stopped, with its tail.

    Keyed `<coord>@<n>`. From `result.json` `open_tool_call` and the
    tool-output contract in the attempt directory.
    """
    out: dict[str, dict] = {}
    for a in read_out["agents"]:
        for r in live.agent_attempts(a):
            if r["status"] in _GOOD or r["status"] == "running":
                continue
            adir = rundir.attempt_dir(run_dir, a["coord"], r["n"])
            result = _read_json(adir / "result.json")
            call = result.get("open_tool_call") if isinstance(result, dict) else None
            if not isinstance(call, dict):
                continue
            path = adir / str(call.get("file") or "")
            out[f"{a['coord']}@{r['n']}"] = {
                **call, "tail": tool_output.tail(path, 10) if call.get("file") else []}
    return out


# ------------------------------------------------------------- Markdown


def _maybe_duration(seconds: Any) -> str:
    return human_duration(seconds) if isinstance(seconds, (int, float)) else "-"


def _maybe_tokens(n: Any) -> str:
    return _human_tokens(int(n)) if isinstance(n, (int, float)) else "-"


def _cell(text: Any) -> str:
    return str(text if text is not None else "-").replace("|", "\\|").replace(
        "\n", " ")


def render_md(read_out: dict) -> str:
    rep, ex, run = read_out["report"], read_out["exit"], read_out["run"]
    L = [f"# Exit report - {run['id']}", "",
         rep["verdict"], "",
         f"exit status: **{ex['status']}**   written: {ex['at']}   "
         f"workflow: `{run.get('workflow')}`   run dir: `{run.get('dir')}`"]
    if ex.get("error"):
        L += ["", f"error: {ex['error']}"]
    if ex.get("traceback_tail"):
        L += ["", "```text", *ex["traceback_tail"], "```"]

    L += ["", "## What needs a person", ""]
    if rep["needs"]:
        for n in rep["needs"]:
            L.append(f"- {n['text']}")
            if n.get("command"):
                L += ["", f"  ```", f"  {n['command']}", "  ```", ""]
    else:
        L.append("Nothing. Every agent passed.")

    L += ["", "## Phases", "", "| phase | state | good/total | auto-resume passes |",
          "|---|---|---|---|"]
    for p in read_out["phases"]:
        good = p.get("good")
        L.append(f"| `{p['coord']}` {_cell(p['name'])} | {p['state']} | "
                 f"{good if good is not None else '-'}/{p['total']} | "
                 f"{p.get('auto_resumes', 0)} |")

    if rep.get("predicted"):
        L += ["", "## Predicted vs actual", "",
              "| phase | predicted p50 | p80 | actual | tokens p50 | tokens p80 "
              "| tokens actual | n |",
              "|---|---|---|---|---|---|---|---|"]
        for r in rep["predicted"]:
            L.append(f"| {r['label']} | {_maybe_duration(r['wall_p50'])} | "
                     f"{_maybe_duration(r['wall_p80'])} | "
                     f"{_maybe_duration(r['wall_actual'])} | "
                     f"{_maybe_tokens(r['tokens_p50'])} | "
                     f"{_maybe_tokens(r['tokens_p80'])} | "
                     f"{_maybe_tokens(r['tokens_actual'])} | "
                     f"{r['n'] if r['n'] is not None else '-'} |")

    if rep.get("token_budget"):
        L += ["", "## Token budget", "", *rep["token_budget"]]

    if rep.get("cloudflare"):
        L += ["", "## Cloudflare", "", *rep["cloudflare"]]

    L += ["", "## Agents", "",
          "| agent | status | attempts | wall | tokens | gate |",
          "|---|---|---|---|---|---|"]
    for r in rep["agents_table"]:
        L.append(f"| `{r['coord']}` | {_cell(r['status'])} | "
                 f"{_cell(r['lineage'])} | {r['wall']} | {r['tokens']} | "
                 f"{_cell(r['gate'])} |")

    failed = [(a, r) for a in read_out["agents"] for r in live.agent_attempts(a)
              if r.get("activity") is not None or (
                  r["status"] not in _GOOD and r["status"] != "running")]
    L += ["", "## Failed attempts", ""]
    if not failed:
        L.append("None.")
    for a, r in failed:
        L += [f"### `{a['coord']}` attempt {r['n']} - {r['status']}", ""]
        L.append(f"- cause: {r.get('cause') or '-'}")
        if r.get("retry_decision"):
            L.append(f"- decision: {r['retry_decision']}")
        act = r.get("activity") or {}
        said = act.get("latest_reasoning")
        L.append(f"- latest reasoning: {said['text'] if said else '-'}")
        if act.get("last_error"):
            L.append(f"- last provider error: {act['last_error']}")
        stopped = (rep.get("stopped_calls") or {}).get(f"{a['coord']}@{r['n']}")
        if stopped:
            L.append(f"- open when it stopped: {_cell(stopped.get('tool'))} "
                     f"`{_cell(stopped.get('command'))}` for {stopped.get('since_s')} s "
                     f"(`{stopped.get('file')}`)")
            if stopped.get("tail"):
                L += ["", "  ```"] + [f"  {line}" for line in stopped["tail"]] + ["  ```"]
        calls = act.get("tool_calls") or []
        if calls:
            L += ["", "| time | tool | summary | s | result |",
                  "|---|---|---|---|---|"]
            for c in calls:
                mark = ("no result" if c.get("pending") else
                        "ok" if c.get("ok") else "error")
                L.append(f"| {c.get('at') or '-'} | {_cell(c.get('name'))} | "
                         f"{_cell(c.get('summary'))} | "
                         f"{c.get('duration_s') if c.get('duration_s') is not None else '-'} "
                         f"| {mark} |")
        L.append("")

    L += ["## Evidence", ""]
    L += [f"- `{p}`" for p in rep["evidence"]]
    L += ["", "## Run log health", "", rep["run_log_health"], ""]
    return "\n".join(L)


# ----------------------------------------------------------------- HTML


def _x(text: Any) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


_TL_TONE = {"passed": "tl-ok", "cached": "tl-ok", "failed": "tl-bad",
            "quarantined": "tl-bad", "timeout": "tl-bad",
            "deferred": "tl-warn", "interrupted": "tl-warn",
            "running": "tl-run"}


def render_timeline_svg(read_out: dict) -> str:
    """Spec §11 item 6: one bar per attempt on one time axis, as inline SVG.

    Colours are CSS classes, so the page's light and dark themes apply.
    """
    bars = []
    end_of_run = act.epoch(read_out["run"].get("finished")) or act.epoch(
        read_out.get("generated"))
    for a in read_out["agents"]:
        for r in live.agent_attempts(a):
            start = act.epoch(r.get("started"))
            if start is None:
                continue
            end = act.epoch(r.get("ended")) or end_of_run or start
            bars.append((a["coord"], r, start, max(end, start)))
    if not bars:
        return "<p>No attempt started, so there is nothing to draw.</p>"
    t0 = min(b[2] for b in bars)
    t1 = max(b[3] for b in bars)
    span = max(t1 - t0, 1.0)
    label_w, plot_w, row_h, top = 300, 640, 22, 26
    width = label_w + plot_w + 20
    height = top + row_h * len(bars) + 10

    def x(t: float) -> float:
        return label_w + plot_w * (t - t0) / span

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} '
           f'{height}" role="img" aria-label="timeline of every attempt">']
    for i in range(5):
        t = t0 + span * i / 4
        xi = x(t)
        out.append(f'<line class="tl-axis" x1="{xi:.1f}" y1="{top - 6}" '
                   f'x2="{xi:.1f}" y2="{height - 6}"/>')
        out.append(f'<text x="{xi:.1f}" y="{top - 10}" text-anchor="middle">'
                   f'{_x(act.hms(t))}</text>')
    for i, (coord, r, start, end) in enumerate(bars):
        y = top + i * row_h
        label = f"{coord} #{r['n']:02d}"
        tone = _TL_TONE.get(r["status"], "tl-mute")
        w = max(x(end) - x(start), 2.0)
        tip = (f"{coord} attempt {r['n']} ({r['start_kind']}): {r['status']}"
               + (f", {r['wall_s']} s" if r.get("wall_s") is not None else "")
               + (f" - {r['cause']}" if r.get("cause") else ""))
        out.append(f'<text x="{label_w - 8}" y="{y + 15}" '
                   f'text-anchor="end">{_x(label)}</text>')
        out.append(f'<rect class="{tone}" x="{x(start):.1f}" y="{y + 4}" '
                   f'width="{w:.1f}" height="{row_h - 8}" rx="3">'
                   f'<title>{_x(tip)}</title></rect>')
    out.append("</svg>")
    return "".join(out)


def _embed(payload: dict) -> str:
    """JSON that is safe inside a `<script>` element."""
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return (text.replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("&", "\\u0026").replace("\u2028", "\\u2028")
            .replace("\u2029", "\\u2029"))


def render_html(payload: dict, template: str | None = None) -> str:
    page = template if template is not None else TEMPLATE.read_text(
        encoding="utf-8")
    if DATA_SLOT not in page:
        raise ValueError("the dashboard template lost its data slot")
    page = page.replace(
        DATA_SLOT, '<script id="ohflow-data" type="application/json">'
        + _embed(payload) + "</script>", 1)
    if isinstance(payload.get("read_out"), dict):
        timeline_data = payload["read_out"]
    elif "run" in payload and "agents" in payload:
        timeline_data = payload
    else:
        workflow = payload.get("workflow") if isinstance(
            payload.get("workflow"), dict) else payload
        timeline_data = {"run": workflow.get("run", {}), "agents": [],
                         "generated": workflow.get("generated")}
    page = page.replace(TIMELINE_SLOT, render_timeline_svg(timeline_data), 1)
    # Exit reports are standalone files opened without the live server. Inline
    # the same shipping CSS and JavaScript so the offline renderer is not a
    # separate mock, and embed the measured brand face as a data URL.
    css = STYLESHEET.read_text(encoding="utf-8")
    try:
        font = base64.b64encode(BRAND_FONT.read_bytes()).decode("ascii")
        css = css.replace('url("/assets/lexend-variable.ttf")',
                          f'url("data:font/ttf;base64,{font}")')
    except OSError:
        pass
    page = page.replace(STYLE_SLOT, "<style>" + css + "</style>", 1)
    # The pure record assembler ships before the renderer, live and inline
    # alike, so an enriched offline export reconstructs oversized records with
    # the exact code the live page runs.
    page = page.replace(
        RECORDS_SLOT,
        "<script>" + RECORDS_JAVASCRIPT.read_text(encoding="utf-8") + "</script>",
        1)
    page = page.replace(
        SCRIPT_SLOT,
        "<script>" + JAVASCRIPT.read_text(encoding="utf-8") + "</script>",
        1)
    run = timeline_data.get("run") or (
        payload.get("workflow", {}).get("run") if isinstance(
            payload.get("workflow"), dict) else {})
    title = f"<title>exit report - {_x(run.get('id', 'ohflow run'))}</title>"
    return page.replace("<title>ohflow run</title>", title, 1)


# ---------------------------------------------------------------- write


def _write(path: Path, text: str) -> None:
    """Write beside, then move into place: a kill mid-write leaves the old
    report whole rather than a torn new one."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def write_exit_report(run_dir: Path, info: dict,
                      now: float | None = None) -> dict[str, Path]:
    """Write `exit.json`, `exit-report.md` and `exit-report.html`."""
    from . import dashboard_data

    run_dir = Path(run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    read_out = build(run_dir, info, now)
    plan = dashboard_data.plan_data(run_dir, now)
    if plan is not None:
        plan["run"]["status"] = read_out["run"]["status"]
    read_out["plan"] = plan
    paths = {"json": run_dir / "exit.json",
             "md": run_dir / "exit-report.md",
             "html": run_dir / "exit-report.html"}
    record = dict(read_out["exit"])
    record["run_id"] = read_out["run"]["id"]
    record["verdict"] = read_out["report"]["verdict"]
    record["reports"] = {"md": paths["md"].name, "html": paths["html"].name}
    _write(paths["md"], render_md(read_out))
    _write(paths["html"], render_html(read_out))
    # Last, so a reader that finds exit.json also finds both reports.
    _write(paths["json"], json.dumps(record, indent=2) + "\n")
    return paths


def rebuild(run_dir: Path) -> tuple[dict, dict[str, Path], str | None]:
    """Write the exit files from the run directory's own files.

    Returns `(info, paths, verdict)`. This is the one path for a run whose
    supervisor wrote no report: `ohflow report` and `ohflow watch` both take
    it. A run with a run log and no `summary.json` gets its summary first.
    """
    run_dir = Path(run_dir)
    if (run_dir / "run-log.jsonl").exists() \
            and not (run_dir / "summary.json").exists():
        rundir.open_run(run_dir).write_summary()
    info = exit_info_from_files(run_dir)
    paths = write_exit_report(run_dir, info)
    return info, paths, read_verdict(paths)


def read_verdict(paths: dict[str, Path]) -> str | None:
    """The verdict sentence in a written `exit.json`, or None."""
    try:
        return json.loads(paths["json"].read_text(encoding="utf-8")).get(
            "verdict")
    except (OSError, ValueError):
        return None

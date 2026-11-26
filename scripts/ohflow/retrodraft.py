"""Draft the mechanical half of `retro.md` when a run ends.

`runnotes.py` writes `retro.md` at the start of a run with an empty block between
two markers. When the run ends, this module fills that block from `summary.json`
and the attempt directories: the facts the engine already holds, in the order a
person reads them. The person adds the judgement, in the table below the block.

    <!-- ohflow:auto begin -->   rewritten every time the run ends
    <!-- ohflow:auto end -->     everything outside the markers is the person's

The block has three parts. **Totals** say what the run did as a whole. **Per
step** is one row each, with the same sums and cell formats as
`ohflow table --by step`, which this module reuses so the two cannot disagree.
**Pointers** are deterministic observations that point at a step worth a look:
a retry, a step that did not pass, an attempt that recorded an error and still
passed its gate, an outlier, a run of tool errors, a step that ran past the p80
of its estimate. A pointer is never a verdict.
Cost that reads `unpriced` is shown in the totals and the table, not pointed at.
The person decides whether the gate was right and what caused the trouble.

Rules, as in `runnotes.py`:

* **Replace only the block.** A resume rewrites the block and leaves every other
  byte of `retro.md` alone. A file without the markers is left untouched.
* **Never raise.** `write` returns a status and a message. The engine says the
  message and carries on.
* **Read the files, not the engine.** Everything comes from `summary.json` and
  the attempts' `gate.json`, so the draft can be rebuilt from a preserved run.
"""

from __future__ import annotations

import json
import os
import statistics
from pathlib import Path
from typing import Any, Iterator

from . import estimate as ohestimate
from . import rundir, table as ohtable

__all__ = ["BEGIN", "END", "render", "write", "WRITTEN", "ABSENT", "PROBLEM"]


BEGIN = "<!-- ohflow:auto begin -->"
END = "<!-- ohflow:auto end -->"

WRITTEN, ABSENT, PROBLEM = "written", "absent", "problem"

#: A step is an outlier when it used at least this many times the median, and at
#: least the floor, so a run of three tiny steps raises no pointer.
OUTLIER_RATIO = 2.0
OUTLIER_MIN_TOOL_CALLS = 20
OUTLIER_MIN_SECONDS = 300
#: An attempt with this many tool errors or more earns a pointer.
TOOL_ERRORS = 3

_OK = ("passed", "cached")


def _steps(summary: dict) -> Iterator[tuple[str, dict, list[dict]]]:
    for item in rundir.walk_summary(summary):
        yield item.coord, item.step, item.executions


def _num(value: Any) -> float | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) \
        else None


def _failed_checks(attempt: dict) -> str:
    """`name (expected X, observed Y)` for each check that failed, read from the
    attempt's own `gate.json`. Empty when the file is missing or all passed."""
    where = attempt.get("dir")
    if not where:
        return ""
    try:
        gate = json.loads((Path(where) / "gate.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    bad = []
    for check in gate.get("checks") or []:
        if isinstance(check, dict) and check.get("passed") is False:
            bad.append(f"{check.get('name')} (expected {check.get('expected')}, "
                       f"observed {check.get('observed')})")
    return "; ".join(bad)


def _clip(text: Any, n: int = 110) -> str:
    one = " ".join(str(text).split())
    return one if len(one) <= n else one[:n - 1] + "..."


# ----------------------------------------------------------------- the parts


def _totals(summary: dict) -> list[str]:
    everything: list[dict] = []
    agent_steps: list[tuple[dict, list[dict]]] = []
    for _c, step, attempts in _steps(summary):
        everything.extend(attempts)
        if step.get("kind", "agent") == "agent":
            agent_steps.append((step, attempts))
    folded = ohtable._fold(everything)

    by_status: dict[str, int] = {}
    for _c, step, _attempts in _steps(summary):
        by_status[str(step.get("status"))] = by_status.get(
            str(step.get("status")), 0) + 1
    spread = ", ".join(f"{n} {s}" for s, n in sorted(by_status.items())) or "none"

    first = retried = never = 0
    for step, attempts in agent_steps:
        final_ok = step.get("status") in _OK
        first_ok = bool(attempts) and attempts[0].get("status") in _OK
        if first_ok or (final_ok and len(attempts) <= 1):
            first += 1
        elif final_ok:
            retried += 1
        else:
            never += 1

    models = sorted({str((a.get("tokens") or {}).get("model"))
                     for _c, _step, attempts in _steps(summary) for a in attempts
                     if (a.get("tokens") or {}).get("model")})
    lines = [
        f"- Status: **{summary.get('status') or ohtable.MISSING}**. "
        f"Started {summary.get('started') or ohtable.MISSING}, "
        f"finished {summary.get('finished') or ohtable.MISSING}, "
        f"elapsed {ohtable._elapsed(summary)}.",
        f"- Steps: {spread}.",
        f"- Agent steps: {first} passed on the first attempt, {retried} passed "
        f"after a retry, {never} did not pass.",
        f"- Agent time {ohtable._cell(folded['agent_time'], 'agent_time')} "
        f"across {folded['agent_executions']} agent executions. "
        f"Elapsed is the run's clock; the two differ by the parallelism.",
        f"- LLM calls {ohtable._cell(folded['llm_calls'], 'llm_calls')}, "
        f"tool calls {ohtable._cell(folded['tool_calls'], 'tool_calls')}, "
        f"prompt tokens {ohtable._cell(folded['prompt_tokens'], 'prompt_tokens')}, "
        f"completion tokens "
        f"{ohtable._cell(folded['completion_tokens'], 'completion_tokens')}, "
        f"cost {ohtable._cell(folded['cost'], 'cost')}.",
    ]
    if any(folded[k] is None for k in ("agent_time", "llm_calls", "tool_calls",
                                        "prompt_tokens", "completion_tokens")):
        lines.append("- A dash means an agent execution wrote no numbers, so "
                     "that total is unknown.")
    if models:
        lines.append(f"- Model: {', '.join(models)}.")
    for branch, stat in sorted((summary.get("diff_stat") or {}).items()):
        tail = [ln.strip() for ln in str(stat).splitlines() if ln.strip()]
        if tail:
            lines.append(f"- Diff of `{branch}`: {tail[-1]}.")
    return lines


def _step_table(summary: dict) -> list[str]:
    head = ["Step", "Kind", "Status", "Attempts", "Tool calls", "LLM calls",
            "Prompt tokens", "Completion tokens", "Agent time", "Cost"]
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    for coord, step, entries in _steps(summary):
        f = ohtable._fold(entries)
        cells = [coord, str(step.get("kind", "agent")),
                 str(step.get("status") or ohtable.MISSING),
                 str(len(entries) or ohtable.MISSING),
                 ohtable._cell(f["tool_calls"], "tool_calls"),
                 ohtable._cell(f["llm_calls"], "llm_calls"),
                 ohtable._cell(f["prompt_tokens"], "prompt_tokens"),
                 ohtable._cell(f["completion_tokens"], "completion_tokens"),
                 ohtable._cell(f["agent_time"], "agent_time"),
                 ohtable._cell(f["cost"], "cost")]
        out.append("| " + " | ".join(cells) + " |")
    return out


def _pointers(summary: dict, estimate: dict | None = None) -> list[str]:
    out: list[str] = []

    for coord, step, attempts in _steps(summary):            # retries
        if len(attempts) < 2:
            continue
        parts = []
        for a in attempts:
            bit = f"attempt {a.get('attempt')} {a.get('status')}"
            if a.get("failure_class"):
                bit += f" ({a['failure_class']})"
            bad = _failed_checks(a)
            if bad:
                bit += f", failed checks: {bad}"
            parts.append(bit)
        parts[0] = parts[0][:1].upper() + parts[0][1:]
        out.append(f"- `{coord}` ran {len(attempts)} attempts. " + "; ".join(parts) + ".")

    for coord, step, attempts in _steps(summary):            # did not pass
        if step.get("status") in _OK + ("dry-run", "skipped"):
            continue
        why = step.get("retry_decision") or ""
        last = (attempts or [{}])[-1]
        err = last.get("error")
        out.append(f"- `{coord}` has status **{step.get('status')}**."
                   + (f" {_clip(why)[:1].upper()}{_clip(why)[1:]}" if why else "")
                   + (f" Error: {_clip(err)}" if err else ""))

    for item in summary.get("excluded") or []:               # excluded work
        if isinstance(item, dict):
            out.append(f"- `{item.get('coord')}` was excluded after "
                       f"{item.get('failures')} failures of unchanged work: "
                       f"{_clip(item.get('reason') or '')}")

    for coord, step, attempts in _steps(summary):            # error, yet passed
        for a in attempts:
            if a.get("error") and (a.get("status") in _OK or a.get("gate_passed")):
                out.append(f"- `{coord}` attempt {a.get('attempt')} recorded an "
                           f"error and still passed its gate: {_clip(a['error'])}")

    agent = [(c, s, at) for c, s, at in _steps(summary)
             if s.get("kind", "agent") == "agent"]
    if len(agent) >= 3:                                     # outliers
        for label, pick, floor, unit in (
                ("tool calls", lambda at: sum(_num(a.get("tool_calls")) or 0
                                          for a in at),
                 OUTLIER_MIN_TOOL_CALLS, ""),
                ("agent time", lambda at: sum(_num(a.get("wall_seconds")) or 0
                                              for a in at),
                 OUTLIER_MIN_SECONDS, " s")):
            values = {c: pick(at) for c, _s, at in agent}
            median = statistics.median(values.values())
            for c, v in sorted(values.items()):
                if v >= floor and median > 0 and v >= OUTLIER_RATIO * median:
                    out.append(f"- `{c}` used {v:g}{unit} of {label}; the median "
                               f"agent step used {median:g}{unit}.")

    for coord, _step, attempts in _steps(summary):           # tool errors
        for a in attempts:
            n = _num(a.get("observation_errors")) or 0
            if n >= TOOL_ERRORS:
                out.append(f"- `{coord}` attempt {a.get('attempt')} hit {n:g} tool "
                           f"errors in {_num(a.get('tool_calls')) or 0:g} tool calls.")

    # Past the estimate: the step's attempts together took longer than the
    # p80 the run was estimated with. Only a run with an estimate.json has one.
    expected = {s["coord"]: s for s in (estimate or {}).get("steps") or []}
    for coord, _step, attempts in _steps(summary):
        p80 = (expected.get(coord, {}).get("wall_s") or {}).get("p80")
        if not isinstance(p80, (int, float)):
            continue
        actual = sum(_num(a.get("wall_seconds")) or 0 for a in attempts)
        if actual > p80:
            n = expected[coord].get("n")
            out.append(f"- `{coord}` ran {actual:g} s; the estimate's p80 was "
                       f"{p80:g} s ({n} sample{'s' if n != 1 else ''}).")

    return out


def render(summary: dict, estimate: dict | None = None) -> str:
    """The text that goes between the markers. `estimate` is the run's
    `estimate.json`, when it has one."""
    pointers = _pointers(summary, estimate) or ["- Nothing matched the pointer rules."]
    parts = [
        "Drafted by ohflow when the run ended, and rewritten each time it ends. "
        "Write outside this block.",
        "",
        "**Totals**", "", *_totals(summary), "",
        "**Per step**", "", *_step_table(summary), "",
        "**Pointers.** Places to look, not verdicts. Rules: a retry, a step that "
        "did not pass, an error that still passed its gate, a step at "
        f"{OUTLIER_RATIO:g}x the median for tool calls or time, "
        f"{TOOL_ERRORS} or more tool errors, a step past the p80 of its estimate.", "",
        *pointers,
    ]
    return "\n".join(parts)


# ------------------------------------------------------------------- writing


def write(run_dir: Path) -> tuple[str, str]:
    """Fill the block in `retro.md`. Returns `(status, message)`; never raises.

    `absent`: there is no `retro.md` or no `summary.json`, so there is nothing
    to do and nothing is wrong (an older run, a dry run, a deleted file).
    `problem`: something exists but could not be used, and the message says what.
    """
    run_dir = Path(run_dir)
    retro = run_dir / "retro.md"
    try:
        if not retro.is_file() or not (run_dir / "summary.json").is_file():
            return ABSENT, "no retro.md or no summary.json at the run root"
        summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        text = retro.read_text(encoding="utf-8")
        start = text.find(BEGIN)
        stop = text.find(END, start + 1) if start >= 0 else -1
        if start < 0 or stop < 0:
            return PROBLEM, "retro.md has no complete ohflow:auto block; left alone"
        new = (text[:start + len(BEGIN)] + "\n"
               + render(summary, ohestimate.read_estimate(run_dir)) + "\n"
               + text[stop:])
        tmp = retro.with_name(retro.name + ".tmp")
        tmp.write_text(new, encoding="utf-8")
        os.replace(tmp, retro)
        return WRITTEN, "retro.md: the engine's half is drafted"
    except Exception as e:  # noqa: BLE001 - a draft must never stop a run
        return PROBLEM, f"{type(e).__name__}: {e}"

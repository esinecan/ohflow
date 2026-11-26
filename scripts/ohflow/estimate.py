"""Budget and duration estimates, read from the history of finished runs.

A run has always been able to say what it cost once it was over (`ohflow
table`), and the live page has always been able to extrapolate from a run's
own finished steps. Neither answers the question a person asks before firing:
how long will this take, and what will it burn. This module answers it from
the only evidence there is, every `summary.json` of every earlier run.

    prior = Prior.from_history([history_dir, ...])
    estimate = estimate_workflow(workflow, prior)
    print(render_text(estimate))

**One sample per attempt.** A failed attempt cost its tokens and its minutes
as surely as the one that passed, so every started attempt is a sample, and
the ratio of attempts to steps over the corpus is the retry multiplier the run
total is scaled by.

**Keys fall back.** A step is looked up by `(role, harness executor, model)`.
Role names differ per workflow and the corpus is small, so an exact key is
often empty; the lookup then tries `(executor, model)`, then `(executor,)`,
then the whole corpus, and the result says which key answered. A fallback is
reported as low confidence, never hidden.

**The barrier rule.** A phase of N agents at `max_parallel` M takes `ceil(N /
M)` waves of the median step, which is the rule the live ETA in `live.py`
has used since the dashboard existed. A cached step and a mechanical step add
nothing.

**The 80th percentile stays inside the samples.** `statistics.quantiles`
with its default method extrapolates past the largest sample when there are
two or three of them, and a p80 above every run ever measured is not a
percentile of anything. The inclusive method is used.

Costs. Only an attempt whose `cost_source` is a real price (pi's catalog, the
claude CLI, a `subscription` recorded as 0) is a cost sample. `unpriced` means
nobody could price it, and a step whose history is unpriced reports no dollar
figure and low confidence rather than a zero that reads as free.

This module reads `summary.json` files and the `spec.json` beside each
attempt, and writes nothing. `supervisor.run_workflow` writes the returned
dictionary as `<run-dir>/estimate.json`; the dashboard, the exit report and
the retro draft read that file back with `read_estimate`.
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import os
import statistics
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable, NamedTuple

from . import gates as ohgates
from . import rundir, settings, tiers
from . import table as ohtable
from .coords import coord as make_coord
from .paths import win

__all__ = ["SCHEMA", "ESTIMATE_FILE", "HISTORY_ENV", "HISTORY_DEPTH",
           "NO_HISTORY", "MECHANICAL", "CACHED", "NO_SAMPLES", "Sample",
           "Stat", "Hit", "Prior", "discover_history", "history_paths",
           "history_block", "estimate_workflow", "render_text", "render_json",
           "read_estimate", "write_estimate", "step_expectations"]

SCHEMA = "ohflow.estimate/1"
#: Where a run keeps the estimate made when it started.
ESTIMATE_FILE = "estimate.json"
#: `os.pathsep`-separated history directories, read when `--history` is absent.
HISTORY_ENV = "OHFLOW_HISTORY"
#: How far below a history root the search goes. A history root holds
#: experiment directories, which hold `runs/`, which hold run directories:
#: `summary.json` sits four levels down at most. Deeper trees are worktrees
#: and fixtures copied into runs, and their summaries describe other runs.
HISTORY_DEPTH = 4
#: The one line a verb prints when nothing names a history.
NO_HISTORY = "estimate: no history given (--history DIR or OHFLOW_HISTORY)"
#: Step bases that are not a history lookup.
MECHANICAL = "mechanical"
CACHED = "cached"
NO_SAMPLES = "no history"
#: Fewer samples than this on a key read as low confidence.
LOW_N = 3
#: The last key in the fallback order: every sample of the corpus.
GLOBAL = ("global",)

_RUN_LOG = "run-log.jsonl"


# ------------------------------------------------------------------ samples


@dataclass(frozen=True)
class Sample:
    """One attempt of one agent step, as the numbers a prior is built from.

    `wall_s` is None for an attempt that recorded no positive wall, `tokens`
    None for one that recorded no usage. A sample with neither is not made.
    """
    role: str | None
    executor: str | None
    model: str | None
    wall_s: float | None
    tokens: int | None
    cost: float | None
    cost_source: str | None
    status: str | None
    start_kind: str | None
    run_id: str
    coord: str
    checks_s: float | None = None

    @property
    def priced(self) -> bool:
        """A cost somebody actually computed, a `subscription`'s known zero
        included."""
        return (isinstance(self.cost, (int, float))
                and not isinstance(self.cost, bool)
                and self.cost_source not in (None, ohtable.UNPRICED))


class Stat(NamedTuple):
    """How many samples, their median and their 80th percentile."""
    n: int
    p50: float
    p80: float


class Hit(NamedTuple):
    """What a lookup found: the key that answered and its statistics."""
    key: tuple
    fallback: bool
    wall: Stat | None
    tokens: Stat | None
    cost: Stat | None
    basis: str
    checks: Stat | None = None


def _stat(values: list[float]) -> Stat | None:
    if not values:
        return None
    if len(values) == 1:
        return Stat(1, float(values[0]), float(values[0]))
    p80 = statistics.quantiles(values, n=5, method="inclusive")[3]
    return Stat(len(values), float(statistics.median(values)), float(p80))


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _spec(attempt_dir: Path | None) -> dict:
    if attempt_dir is None:
        return {}
    spec, _problem = ohtable._json_file(attempt_dir / "spec.json")
    return spec if isinstance(spec, dict) else {}


def _spec_model(spec: dict) -> str | None:
    model = spec.get("model")
    if isinstance(model, dict):
        model = model.get("model")
    return str(model) if isinstance(model, str) and model else None


def _samples_ohflow(summary: dict, path: Path) -> tuple[list[Sample], int, int]:
    """The samples of one ohflow summary, plus its attempt and step counts for
    the retry multiplier."""
    run_id = str(summary.get("run_id") or path.parent.name)
    out: list[Sample] = []
    attempts = steps = 0
    for item in rundir.walk_summary(summary):
        step = item.step
        if step.get("kind", "agent") != "agent":
            continue
        role = step.get("role") or step.get("step_id") or item.coord
        started = [e for e in item.executions
                   if isinstance(e, dict) and e.get("started") is not False]
        if started:
            steps += 1
            attempts += len(started)
        first = len(out)
        for entry in started:
            spec = _spec(ohtable._attempt_dir(entry, step, path))
            executor = ohtable._harness_executor(summary, step, entry, {}, spec)
            wall = _num(entry.get("wall_seconds"))
            usage = rundir.Run.usage(entry)
            tokens = usage["total_tokens"] if usage else None
            if (wall is None or wall <= 0) and tokens is None:
                continue
            out.append(Sample(
                role=str(role), executor=executor,
                model=_spec_model(spec) or _tokens_model(entry),
                wall_s=wall if wall is not None and wall > 0 else None,
                tokens=int(tokens) if tokens is not None else None,
                cost=_num(entry.get("cost")),
                cost_source=entry.get("cost_source"),
                status=entry.get("status"), start_kind=entry.get("start_kind"),
                run_id=run_id, coord=item.coord))
        checks = _step_checks(step, started)
        if checks is not None and len(out) > first:
            out[-1] = replace(out[-1], checks_s=checks)
    return out, attempts, steps


def _step_checks(step: dict, started: list[dict]) -> float | None:
    recorded = ohgates.check_seconds(step.get("gate"))
    if recorded is not None:
        return recorded
    total = _num(step.get("wall_seconds"))
    agent = sum(w for w in (_num(e.get("wall_seconds")) for e in started) if w)
    if total is None or not agent or total <= agent:
        return None
    return round(total - agent, 1)


def _tokens_model(entry: dict) -> str | None:
    tokens = entry.get("tokens")
    if isinstance(tokens, dict) and isinstance(tokens.get("model"), str):
        return tokens["model"]
    return None


def _samples_legacy(summary: dict, path: Path) -> list[Sample]:
    """A legacy phase block is one record with no executor and no model. It
    informs the global key only, and it is no evidence about retries."""
    out: list[Sample] = []
    run_id = ohtable._legacy_run_name(path, summary)
    for name, block in (summary.get("phases") or {}).items():
        if not isinstance(block, dict) or block.get("skipped") or block.get("resumed"):
            continue
        wall = _num(block.get("wall_seconds"))
        tokens = rundir.Run.usage(block)
        total = tokens["total_tokens"] if tokens else None
        if (wall is None or wall <= 0) and total is None:
            continue
        gate = block.get("gate") or {}
        out.append(Sample(role=str(name), executor=None, model=None,
                          wall_s=wall if wall and wall > 0 else None,
                          tokens=int(total) if total is not None else None,
                          cost=None, cost_source=None,
                          status="passed" if gate.get("passed") else "failed",
                          start_kind="initial", run_id=run_id, coord=str(name)))
    return out


# ---------------------------------------------------------------- discovery


def discover_history(paths: Iterable[str | Path]) -> list[Path]:
    """Every summary under these paths, `HISTORY_DEPTH` levels down at most.

    `table.discover` stops three levels down, which fits a runs root. A
    history root is one level higher (experiments, then their runs), so this
    walk goes one level further and no more. A run directory with a run log
    and no `summary.json` is named by its run log, as `table` does.
    """
    found: dict[Path, None] = {}
    for raw in paths:
        root = Path(raw)
        if root.is_file():
            found[root.resolve()] = None
            continue
        if not root.is_dir():
            continue
        base_depth = len(root.resolve().parts)
        for dirpath, dirnames, filenames in os.walk(root.resolve()):
            here = Path(dirpath)
            depth = len(here.parts) - base_depth
            if depth >= HISTORY_DEPTH:
                dirnames[:] = []
            dirnames.sort()
            for name in sorted(filenames):
                if name == "summary.json" or name.endswith(".summary.json"):
                    found[here / name] = None
            if _RUN_LOG in filenames and "summary.json" not in filenames:
                found[here / _RUN_LOG] = None
    return list(found)


def history_paths(flag: Iterable[str] | None) -> list[str] | None:
    """The history directories a verb uses: the flag, else `OHFLOW_HISTORY`,
    else None, which means no estimate and the `NO_HISTORY` line."""
    given = [str(p) for p in (flag or []) if str(p).strip()]
    if given:
        return given
    raw = os.environ.get(HISTORY_ENV, "")
    from_env = [p for p in raw.split(os.pathsep) if p.strip()]
    return from_env or None


# -------------------------------------------------------------------- prior


class Prior:
    """The corpus as statistics, with the fallback lookup."""

    def __init__(self, samples: Iterable[Sample], *, retry_multiplier: float = 1.0,
                 sources: Iterable[str] = (), problems: Iterable[str] = (),
                 roots: Iterable[str] = (), ignored: int = 0):
        self.samples: tuple[Sample, ...] = tuple(samples)
        self.retry_multiplier = max(1.0, float(retry_multiplier))
        self.sources = list(sources)
        self.problems = list(problems)
        self.roots = list(roots)
        #: `summary.json` files of another shape. A history root holds other
        #: tools' summaries too (a knowledge extraction writes one per repo),
        #: and they are not a fault of the history, so they are counted, not
        #: named one by one.
        self.ignored = ignored

    @property
    def sample_count(self) -> int:
        return len(self.samples)

    @property
    def source_count(self) -> int:
        return len(self.sources)

    @classmethod
    def from_history(cls, paths: Iterable[str | Path]) -> "Prior":
        """Read every summary the paths name. A file that cannot be read is
        named in `problems` and skipped; it never stops the others."""
        paths = [str(p) for p in paths]
        samples: list[Sample] = []
        sources: list[str] = []
        problems: list[str] = []
        attempts = steps = ignored = 0
        for path in discover_history(paths):
            summary, problem = ohtable._load(path)
            if problem:
                problems.append(problem)
                continue
            shape = ohtable.detect_shape(summary)
            if shape == "ohflow":
                found, a, s = _samples_ohflow(summary, path)
                attempts += a
                steps += s
            elif shape == "legacy":
                found = _samples_legacy(summary, path)
            else:
                ignored += 1
                continue
            sources.append(str(path))
            samples.extend(found)
        multiplier = (attempts / steps) if steps else 1.0
        return cls(samples, retry_multiplier=multiplier, sources=sources,
                   problems=problems, roots=paths, ignored=ignored)

    # ---- lookup

    @staticmethod
    def _matches(sample: Sample, key: tuple) -> bool:
        if key == GLOBAL:
            return True
        if len(key) == 3:
            return (sample.role, sample.executor, sample.model) == key
        if len(key) == 2:
            return (sample.executor, sample.model) == key
        return (sample.executor,) == key

    def lookup(self, role: str | None, executor: str | None,
               model: str | None) -> Hit | None:
        """The first key in the fallback order that has a wall sample, or
        None when no key has one.

        A key is answered by its walls. An attempt that recorded tokens and no
        wall (a crash, a fake, a run on a box with no clock) says nothing
        about duration, and a key made only of those would stop the fallback
        at a number that cannot be an estimate.
        """
        exact = (role, executor, model)
        order = [exact, (executor, model), (executor,), GLOBAL]
        for key in order:
            subset = [s for s in self.samples if self._matches(s, key)]
            walls = [s.wall_s for s in subset if s.wall_s is not None]
            tokens = [s.tokens for s in subset if s.tokens is not None]
            if not walls:
                continue
            costs = [s.cost for s in subset if s.priced]
            checks = [s.checks_s for s in subset if s.checks_s is not None]
            return Hit(key=key, fallback=key != exact, wall=_stat(walls),
                       tokens=_stat(tokens), cost=_stat(costs),
                       basis=self._basis(key, exact, len(subset)),
                       checks=_stat(checks))
        return None

    @staticmethod
    def _basis(key: tuple, exact: tuple, n: int) -> str:
        who = "attempt" if n == 1 else "attempts"
        role, executor, model = exact
        if key == GLOBAL:
            return (f"{n} {who} across the whole history (no timed attempt on "
                    f"{executor or 'this executor'})")
        if len(key) == 3:
            return f"{n} {who} of {role} on {executor}/{model}"
        if len(key) == 2:
            return f"{n} {who} on {executor}/{model} (none as {role})"
        return f"{n} {who} on {executor} (none with {model})"


# -------------------------------------------------------------- the rollup


def _pair(stat: Stat | None, *, scale: float = 1.0) -> dict:
    if stat is None:
        return {"p50": None, "p80": None}
    return {"p50": round(stat.p50 * scale), "p80": round(stat.p80 * scale)}


def _zero() -> dict:
    return {"p50": 0, "p80": 0}


def _sum(values: list[Any]) -> int | float | None:
    """A sum that stays unknown when one part is unknown."""
    if any(v is None for v in values):
        return None
    return sum(values)


def _stamp(now: float | None) -> str:
    return (_dt.datetime.fromtimestamp(now, _dt.timezone.utc) if now is not None
            else _dt.datetime.now(_dt.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")


def history_block(prior: Prior) -> dict:
    """What an estimate says about the corpus it was read from."""
    return {
        "sources": prior.source_count,
        "samples": prior.sample_count,
        "retry_multiplier": round(prior.retry_multiplier, 3),
        "paths": [win(Path(p)) for p in prior.roots],
        "problems": list(prior.problems),
        "ignored": prior.ignored,
    }


def _phase_limit(phase, workflow, override: int | None) -> int:
    # The CLI value is both the default and a ceiling on every phase override,
    # which is how the engine reads `--max-parallel`.
    own = phase.max_parallel if phase.max_parallel is not None else (
        override or workflow.max_parallel)
    if override is not None:
        own = min(own, override)
    return max(1, int(own or 1))


def _step_entry(coord: str, step, prior: Prior, cached: set[str]) -> dict:
    base = {"coord": coord, "kind": step.kind, "key": None, "basis": None,
            "n": 0, "fallback": False, "confidence": "ok",
            "wall_s": _zero(), "checks_s": _zero(), "tokens": _zero(),
            "cost_usd": 0.0}
    if step.kind != "agent" or step.agent is None:
        base["basis"] = MECHANICAL
        return base
    if coord in cached:
        base["basis"] = CACHED
        return base
    try:
        agent = tiers.resolve(step.agent)
    except settings.SettingsError:
        agent = step.agent
    hit = prior.lookup(agent.role, agent.harness_executor, agent.model.model)
    if hit is None or (hit.wall is None and hit.tokens is None):
        base.update({"basis": NO_SAMPLES, "confidence": "low",
                     "wall_s": {"p50": None, "p80": None},
                     "checks_s": {"p50": None, "p80": None},
                     "tokens": {"p50": None, "p80": None}, "cost_usd": None})
        return base
    n = hit.wall.n if hit.wall else hit.tokens.n
    cost = hit.cost.p50 if hit.cost and hit.cost.n else None
    low = n < LOW_N or hit.fallback or cost is None
    base.update({
        "key": list(hit.key), "basis": hit.basis, "n": n,
        "fallback": hit.fallback, "confidence": "low" if low else "ok",
        "wall_s": _pair(hit.wall), "checks_s": _pair(hit.checks),
        "tokens": _pair(hit.tokens),
        "cost_usd": round(cost, 4) if cost is not None else None,
    })
    return base


def _phase_entry(coord: str, phase, limit: int, steps: list[dict]) -> dict:
    agents = [s for s in steps if s["kind"] == "agent"
              and s["basis"] not in (MECHANICAL, CACHED)]
    entry = {"coord": coord, "name": phase.name, "max_parallel": limit,
             "agents": len(agents), "wall_s": _zero(), "checks_s": _zero(),
             "tokens": _zero(),
             "cost_usd": _sum([s["cost_usd"] for s in steps]),
             "n": 0, "basis": "no agent steps", "confidence": "ok"}
    if not agents:
        return entry
    waves = math.ceil(len(agents) / limit)
    p50s = [s["wall_s"]["p50"] for s in agents]
    p80s = [s["wall_s"]["p80"] for s in agents]
    if any(v is None for v in p50s):
        entry["wall_s"] = {"p50": None, "p80": None}
    else:
        entry["wall_s"] = {"p50": round(waves * statistics.median(p50s)),
                           "p80": round(waves * statistics.median(p80s))}
    entry["checks_s"] = {
        which: (round(waves * statistics.median(known)) if known else None)
        for which, known in (
            (w, [s["checks_s"][w] for s in agents if s["checks_s"][w] is not None])
            for w in ("p50", "p80"))}
    entry["tokens"] = {"p50": _sum([s["tokens"]["p50"] for s in agents]),
                       "p80": _sum([s["tokens"]["p80"] for s in agents])}
    entry["n"] = min(s["n"] for s in agents)
    entry["basis"] = (f"{len(agents)} agent step{'s' if len(agents) != 1 else ''}, "
                      f"{waves} wave{'s' if waves != 1 else ''} of the median "
                      f"step at max_parallel {limit}")
    entry["confidence"] = ("low" if any(s["confidence"] == "low" for s in agents)
                           else "ok")
    return entry


def estimate_workflow(workflow, prior: Prior, *, cached: Iterable[str] = (),
                      max_parallel: int | None = None,
                      now: float | None = None) -> dict:
    """The estimate of one workflow: per step, per phase, and the run.

    `cached` names the coordinates a resume will not run again; they cost
    zero. `max_parallel` is the CLI override, when there is one.
    """
    cached = set(cached)
    steps_out: list[dict] = []
    phases_out: list[dict] = []
    for pi, phase in enumerate(workflow.phases, start=1):
        pc = f"{pi:02d}.{phase.slug}"
        limit = _phase_limit(phase, workflow, max_parallel)
        here = []
        for si, step in enumerate(phase.steps, start=1):
            entry = _step_entry(make_coord(pi, phase.slug, si, step.id), step,
                                prior, cached)
            entry["phase"] = pc
            here.append(entry)
        steps_out.extend(here)
        phases_out.append(_phase_entry(pc, phase, limit, here))

    scale = prior.retry_multiplier

    def total(field: str, which: str):
        parts = [p[field][which] for p in phases_out]
        value = _sum(parts)
        return round(value * scale) if value is not None else None

    cost = _sum([p["cost_usd"] for p in phases_out])
    low = (any(p["confidence"] == "low" for p in phases_out)
           or prior.sample_count < LOW_N)
    return {
        "schema": SCHEMA,
        "generated": _stamp(now),
        "workflow": workflow.name,
        "history": history_block(prior),
        "run": {
            "wall_s": {"p50": total("wall_s", "p50"), "p80": total("wall_s", "p80")},
            "checks_s": {"p50": total("checks_s", "p50"),
                         "p80": total("checks_s", "p80")},
            "tokens": {"p50": total("tokens", "p50"), "p80": total("tokens", "p80")},
            "cost_usd": round(cost * scale, 4) if cost is not None else None,
            "confidence": "low" if low else "ok",
            "basis": (f"{prior.sample_count} attempts from {prior.source_count} "
                      f"summaries; phases added in order, times the retry "
                      f"multiplier x{scale:.2f}"),
        },
        "phases": phases_out,
        "steps": steps_out,
    }


# ---------------------------------------------------------------- rendering


def _minutes(seconds: Any) -> str:
    if seconds is None:
        return ohtable.MISSING
    s = int(round(seconds))
    if s < 60:
        return f"{s} s"
    m = int(round(s / 60))
    if m < 60:
        return f"{m} min"
    return f"{m // 60} h {m % 60} min"


def _tokens(n: Any) -> str:
    if n is None:
        return ohtable.MISSING
    n = int(n)
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        return f"{n / 1000:.1f} k"
    return f"{n / 1_000_000:.1f} M"


def _cost(value: Any) -> str:
    return ohtable.UNPRICED if value is None else f"${value:.2f}"


def _row(cells: list[str]) -> str:
    return "| " + " | ".join(str(c) for c in cells) + " |"


def render_text(estimate: dict) -> str:
    """The block a verb prints: the verdict line, then a phase table and a
    step table with n and the p50-p80 range."""
    run, hist = estimate["run"], estimate["history"]
    wall, tokens = run["wall_s"], run["tokens"]
    name = estimate["workflow"]
    if wall["p50"] is None:
        head = (f"ESTIMATE {name}: {NO_SAMPLES} matched some step; "
                f"{hist['samples']} attempts from {hist['sources']} summaries")
    else:
        head = (f"ESTIMATE {name}: ~{_minutes(wall['p50'])} (p50) to "
                f"{_minutes(wall['p80'])} (p80), checks "
                f"~{_minutes(run['checks_s']['p50'])}, {_tokens(tokens['p50'])} tokens, "
                f"{_cost(run['cost_usd'])}, confidence {run['confidence']}; "
                f"{hist['samples']} attempts from {hist['sources']} summaries, "
                f"retry x{hist['retry_multiplier']:.2f}")
    lines = [head, ""]
    lines.append(_row(["phase", "agents", "p50", "p80", "checks p50", "tokens p50",
                       "tokens p80", "cost", "n", "confidence"]))
    lines.append("|" + "---|" * 10)
    for p in estimate["phases"]:
        lines.append(_row([f"`{p['coord']}` {p['name']}", p["agents"],
                           _minutes(p["wall_s"]["p50"]), _minutes(p["wall_s"]["p80"]),
                           _minutes(p["checks_s"]["p50"]),
                           _tokens(p["tokens"]["p50"]), _tokens(p["tokens"]["p80"]),
                           _cost(p["cost_usd"]), p["n"], p["confidence"]]))
    lines.append("")
    lines.append(_row(["step", "p50", "p80", "checks p50", "tokens p50", "n",
                       "basis"]))
    lines.append("|" + "---|" * 7)
    for s in estimate["steps"]:
        lines.append(_row([f"`{s['coord']}`", _minutes(s["wall_s"]["p50"]),
                           _minutes(s["wall_s"]["p80"]),
                           _minutes(s["checks_s"]["p50"]), _tokens(s["tokens"]["p50"]),
                           s["n"], s["basis"] or ohtable.MISSING]))
    for problem in hist.get("problems") or []:
        lines.append(f"history: {problem}")
    if hist.get("ignored"):
        lines.append(f"history: {hist['ignored']} summary.json file(s) of another "
                     f"shape were ignored")
    return "\n".join(lines)


def render_json(estimate: dict) -> str:
    return json.dumps(estimate, indent=2, default=str)


# ------------------------------------------------------------ the run file


def write_estimate(run_dir: Path, estimate: dict) -> Path:
    path = Path(run_dir) / ESTIMATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_json(estimate) + "\n", encoding="utf-8")
    return path


def read_estimate(run_dir: Path) -> dict | None:
    """The run's `estimate.json`, or None when it is absent or not one."""
    try:
        data = json.loads((Path(run_dir) / ESTIMATE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return None
    return data


def step_expectations(estimate: dict | None) -> dict[str, float]:
    """`coord -> expected seconds (p50)` for every estimated agent step, for
    the live ETA before any step of the run has finished."""
    out: dict[str, float] = {}
    for step in (estimate or {}).get("steps") or []:
        p50 = (step.get("wall_s") or {}).get("p50")
        if step.get("kind") == "agent" and isinstance(p50, (int, float)) \
                and step.get("basis") not in (MECHANICAL, CACHED):
            out[str(step["coord"])] = float(p50)
    return out

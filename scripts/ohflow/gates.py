"""Mechanical exit conditions. A gate is Python and it is never an agent.

Each check is a callable that takes a `GateContext` plus its declarative
arguments, and returns a `GateResult`. A step's gate is the conjunction of its
checks, with every sub-result recorded. A failing gate names the check that
failed and points at the log that proves it.
"""

from __future__ import annotations

import fnmatch
import hashlib
import inspect
import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Mapping

from . import exec as ohexec
from . import check_passes
from .paths import win

__all__ = ["GateResult", "GateReport", "GateContext", "REGISTRY", "run_gate",
           "register", "argument_errors", "check_seconds"]


@dataclass
class GateResult:
    name: str
    passed: bool
    observed: Any = None
    expected: Any = None
    evidence_path: str | None = None
    detail: str | None = None
    duration_s: float | None = None


def _check_dict(check: GateResult) -> dict:
    out = asdict(check)
    if out["duration_s"] is None:
        del out["duration_s"]
    return out


def check_seconds(gate: Any) -> float | None:
    checks = gate.get("checks") if isinstance(gate, dict) else None
    times = [c["duration_s"] for c in checks or ()
             if isinstance(c, dict) and c.get("name") == "command_exit"
             and isinstance(c.get("duration_s"), (int, float))]
    return round(sum(times), 1) if times else None


@dataclass
class GateReport:
    coord: str = ""
    passed: bool = False
    checks: list[GateResult] = field(default_factory=list)

    def failed_names(self) -> list[str]:
        return [f"gate:{c.name}" for c in self.checks if not c.passed]

    def failure_lines(self) -> list[str]:
        out = []
        for c in self.checks:
            if c.passed:
                continue
            line = f"{c.name}: observed {c.observed!r}, expected {c.expected!r}"
            if c.evidence_path:
                line += f" (evidence: {win(c.evidence_path)})"
            if c.detail:
                line += f" - {c.detail}"
            out.append(line)
        return out

    def to_dict(self) -> dict:
        return {"coord": self.coord, "passed": self.passed,
                "checks": [_check_dict(c) for c in self.checks]}


@dataclass
class GateContext:
    """Everything a check may look at. Assembled by the engine."""
    coord: str
    repo: Path
    worktree: Path
    base_sha: str
    base_ref: str
    attempt_dir: Path
    log_dir: Path
    write_scope: tuple[str, ...] = ()
    final_text: str = ""
    structured: Any = None
    schema: dict | None = None
    agent_error: str | None = None
    timeout_s: int = 1800
    attempt: int = 1
    check_index: int = 0
    #: HEAD of the step's worktree when this attempt began. A step with no
    #: worktree has none.
    start_sha: str = ""
    run_dir: Path | None = None


REGISTRY: dict[str, Callable[..., GateResult]] = {}


def register(name: str, describe: Callable[[dict], str]):
    def deco(fn):
        fn.describe = describe
        REGISTRY[name] = fn
        return fn
    return deco


def argument_errors(name: str, args: Mapping[str, Any]) -> list[str]:
    """What is wrong with a check's arguments, read against its signature, so a
    workflow is refused before an agent runs and not by a `TypeError` after."""
    fn = REGISTRY.get(name)
    if fn is None:
        return []
    try:
        args = dict(args)
    except (TypeError, ValueError):
        return [f"check {name!r} takes its arguments as a mapping, "
                f"not {type(args).__name__}"]
    params = list(inspect.signature(fn).parameters.values())[1:]
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params):
        return []
    takes = [p.name for p in params]
    errs = [f"check {name!r} takes no argument {key!r}; it takes: "
            f"{', '.join(takes) if takes else 'no arguments'}"
            for key in args if key not in takes]
    errs.extend(f"check {name!r} needs the argument {p.name!r}"
                for p in params
                if p.default is inspect.Parameter.empty and p.name not in args)
    return errs


def _command_log_name(ctx: GateContext, check: str, cmd: str) -> str:
    digest = hashlib.sha256(cmd.encode("utf-8")).hexdigest()[:10]
    return f"gate-{ctx.check_index:02d}-{check}-{digest}"


def _attempt_env(ctx: GateContext) -> dict[str, str]:
    return {"OHFLOW_ATTEMPT": str(ctx.attempt),
            "OHFLOW_ATTEMPT_DIR": str(Path(ctx.attempt_dir).resolve())}


# ------------------------------------------------------------------- checks


@register("handover_written", lambda a: f"handover.md answers {len(a.get('headings') or [])} headings in at most {a.get('max_chars', 6000)} characters")
def handover_written(ctx: GateContext, headings=None, max_chars=6000) -> GateResult:
    from .handover import check_text, CORE
    from .workflow import HandoverSpec
    path = ctx.attempt_dir / "handover.md"
    if path.resolve() != ctx.attempt_dir.resolve() / "handover.md":
        return GateResult("handover_written", False, "redirected file", "attempt handover", str(path))
    try:
        with path.open(encoding="utf-8", newline="") as stream:
            text = stream.read(max_chars + 1)
    except (OSError, UnicodeError):
        return GateResult("handover_written", False, "missing or unreadable", "complete handover", str(path))
    # The declarative headings come from the same question contract as the brief.
    base = [h for h, _ in CORE]
    spec = HandoverSpec(extra=tuple((headings or base)[len(base):]), max_chars=max_chars)
    problem = check_text(text, spec)
    return GateResult("handover_written", problem is None, problem or "present", "complete handover", str(path))


def _git_or_fail(ctx: GateContext, args: str, *, check: str, log_name: str,
                 expected: Any):
    """Run a git command for a check, and refuse to read a failure as good news.

    Returns `(completed, None)` when git exited 0, and `(completed, GateResult)`
    when it did not.

    Measured 2026-09-18 and recorded in `thread1/oracle-before.json`: `git diff
    --name-only invalid-sha..HEAD` exits 128 and prints nothing to stdout, and
    `git status --porcelain` outside a repository does the same. Five checks used
    to read that empty stdout as "nothing strayed", "nothing is dirty", "no
    attribution" and "nothing touched", so a gate that could not see the tree
    approved it. The exit code is now the first thing each of them reads.
    """
    c = ohexec.git(args, ctx.worktree, log_dir=ctx.log_dir, name=log_name)
    if c.returncode == 0:
        return c, None
    said = (c.stderr or c.stdout or "").strip().splitlines()
    return c, GateResult(
        check, False,
        observed={"git_exit": c.returncode, "stderr": said[0][:300] if said else ""},
        expected=expected,
        evidence_path=c.stderr_path or c.stdout_path,
        detail=f"`git {args}` exited {c.returncode}; this check cannot judge a "
               f"tree it could not read")


#: The values of `since`, the argument every check that reads git history takes.
#: Any other string names a ref or a commit.
SINCE_BASE = "base"              # the worktree's creation commit: the default
SINCE_STEP_START = "step_start"  # HEAD when this attempt began
SINCE_LAST_MERGE = "last_merge"  # the newest merge commit past the base
_SINCE_WORDS = {SINCE_BASE: "base", SINCE_STEP_START: "the step's start",
                SINCE_LAST_MERGE: "the last merge"}
_REF = re.compile(r"^[A-Za-z0-9._/~^@{}-]+$")


def _since_words(args: dict) -> str:
    since = args.get("since", SINCE_BASE)
    return _SINCE_WORDS.get(since, str(since))


def _resolve_since(ctx: GateContext, since: str, *, check: str,
                   expected: Any) -> tuple[str | None, GateResult | None]:
    """The commit a check measures from: `(sha or ref, None)`, or `(None,
    failure)` when it cannot be named. A check never reads a range it could not
    resolve as an empty one."""
    def refuse(observed: Any, detail: str):
        return None, GateResult(check, False, observed=observed,
                                expected=expected, detail=detail)

    if since == SINCE_BASE:
        return ctx.base_sha, None
    if since == SINCE_STEP_START:
        if not ctx.start_sha:
            return refuse("no start commit",
                          "since=step_start needs the commit the step began at, "
                          "and this step has no worktree")
        return ctx.start_sha, None
    if since == SINCE_LAST_MERGE:
        scope = f"{ctx.base_sha}..HEAD" if ctx.base_sha else "HEAD"
        c, bad = _git_or_fail(ctx, f"log --merges -1 --format=%H {scope}",
                              check=check, log_name="gate-since",
                              expected=expected)
        if bad is not None:
            return None, bad
        # With no merge past the base the work is measured from the base.
        return c.stdout.strip() or ctx.base_sha, None
    if not isinstance(since, str) or not _REF.match(since):
        return refuse(since, "since is `base`, `step_start`, `last_merge` or a "
                             "ref name")
    return since, None


@register("commits_past_base",
          lambda a: f"commits past {_since_words(a)} >= {a.get('min', 1)}")
def commits_past_base(ctx: GateContext, min: int = 1,
                      since: str = SINCE_BASE) -> GateResult:
    # `min=0` is why this one needs the exit code as well. With `min=1` a failed
    # git call reads as zero commits and the check fails closed by accident;
    # with `min=0` that same empty stdout passes.
    start, bad = _resolve_since(ctx, since, check="commits_past_base",
                                expected=f">= {min}")
    if bad is not None:
        return bad
    c, bad = _git_or_fail(ctx, f"rev-list --count {start}..HEAD",
                          check="commits_past_base", log_name="gate-commits",
                          expected=f">= {min}")
    if bad is not None:
        return bad
    try:
        n = int(c.stdout.strip() or "0")
    except ValueError:
        n = 0
    return GateResult("commits_past_base", n >= min, observed=n,
                      expected=f">= {min}", evidence_path=c.stdout_path)


BASE = "{base}"


def with_base(cmd: str, base: str) -> str | None:
    if BASE not in cmd:
        return cmd
    return cmd.replace(BASE, base) if base else None


@register("command_exit",
          lambda a: f"`{a.get('cmd')}` exits {a.get('expect', 0)}")
def command_exit(ctx: GateContext, cmd: str = "npm test", expect: int = 0,
                 shell: str = "sh", timeout: int | None = None,
                 reuse: bool = True) -> GateResult:
    filled = with_base(cmd, ctx.base_sha)
    if filled is None:
        return GateResult("command_exit", False, observed="no base commit",
                          expected=expect,
                          detail=f"command: {cmd}; {BASE} is the step's base commit, "
                                 "and this step has no worktree")
    cmd = filled
    tree = (check_passes.clean_tree(ctx.worktree)
            if reuse and expect == 0 and ctx.run_dir is not None else None)
    prior = check_passes.find(ctx.run_dir, cmd, shell, ctx.worktree, tree)
    if prior is not None:
        return GateResult("command_exit", True, observed=expect, expected=expect,
                          evidence_path=prior.get("log"),
                          detail=f"command: {cmd}; {check_passes.reused_note(prior)}",
                          duration_s=0.0)
    c = ohexec.run(cmd, ctx.worktree, shell=shell,
                   timeout=timeout or ctx.timeout_s,
                   log_dir=ctx.log_dir,
                   name=_command_log_name(ctx, "command_exit", cmd),
                   env=_attempt_env(ctx))
    passed = c.returncode == expect
    if passed and tree is not None:
        check_passes.record(ctx.run_dir, cmd, shell, ctx.worktree, tree,
                            by=f"{ctx.coord} attempt {ctx.attempt}", log=c.stdout_path)
    return GateResult("command_exit", passed,
                      observed=c.returncode, expected=expect,
                      evidence_path=c.stdout_path,
                      detail=f"command: {cmd}",
                      duration_s=round(c.duration_s, 1))


_VITEST_TESTS = re.compile(
    r"^\s*Tests\s+(?P<body>.+?)\s*$", re.MULTILINE)
_COUNT = re.compile(r"(\d+)\s+(passed|failed|skipped|todo)")


def parse_vitest(text: str) -> dict[str, int]:
    """Read the `Tests  260 passed | 3 skipped (263)` summary line."""
    counts = {"passed": 0, "failed": 0, "skipped": 0, "todo": 0, "total": 0}
    m = None
    for m in _VITEST_TESTS.finditer(text):
        pass
    if m is None:
        return counts
    body = m.group("body")
    for num, kind in _COUNT.findall(body):
        counts[kind] = int(num)
    tot = re.search(r"\((\d+)\)\s*$", body)
    if tot:
        counts["total"] = int(tot.group(1))
    return counts


def parse_unittest(text: str) -> dict[str, int]:
    counts = {"passed": 0, "failed": 0, "skipped": 0, "todo": 0, "total": 0}
    runs = list(re.finditer(r"^Ran\s+(\d+)\s+tests?\s+in\s+", text, re.MULTILINE))
    if not runs:
        return counts
    counts["total"] = int(runs[-1].group(1))
    summary = text[runs[-1].end():]
    failed = sum(int(n) for n in re.findall(
        r"(?:failures|errors|unexpected successes)=(\d+)", summary))
    skipped = sum(int(n) for n in re.findall(
        r"(?:skipped|expected failures)=(\d+)", summary))
    counts["failed"] = failed
    counts["skipped"] = skipped
    counts["passed"] = max(0, counts["total"] - failed - skipped)
    return counts


def parse_node_test(text: str) -> dict[str, int]:
    counts = {"passed": 0, "failed": 0, "skipped": 0, "todo": 0, "total": 0}
    labels = {"tests": "total", "pass": "passed", "fail": "failed",
              "skipped": "skipped", "todo": "todo"}
    for label, value in re.findall(
            r"^\s*(?:#|\u2139)\s*(tests|pass|fail|skipped|todo)\s+(\d+)\s*$",
            text, re.MULTILINE):
        counts[labels[label]] = int(value)
    return counts


def parse_pytest(text: str) -> dict[str, int]:
    counts = {"passed": 0, "failed": 0, "skipped": 0, "todo": 0, "total": 0}
    matches = list(re.finditer(
        r"(?P<body>(?:\d+\s+(?:passed|failed|error|errors|skipped|xfailed|xpassed)"
        r"(?:,\s*)?)+)\s+in\s+[\d.]+s", text))
    if not matches:
        return counts
    for number, label in re.findall(
            r"(\d+)\s+(passed|failed|error|errors|skipped|xfailed|xpassed)",
            matches[-1].group("body")):
        value = int(number)
        if label == "passed":
            counts["passed"] += value
        elif label in ("failed", "error", "errors", "xpassed"):
            counts["failed"] += value
        else:
            counts["skipped"] += value
    counts["total"] = counts["passed"] + counts["failed"] + counts["skipped"]
    return counts


PARSERS: dict[str, Callable[[str], dict[str, int]]] = {
    "vitest": parse_vitest,
    "unittest": parse_unittest,
    "node": parse_node_test,
    "node-test": parse_node_test,
    "pytest": parse_pytest,
}


@register("test_counts",
          lambda a: (f"`{a.get('cmd', 'npm test')}` exits 0, at most "
                     f"{a.get('max_failed', 0)} failing, at least "
                     f"{a.get('min_passed', 1)} passing"))
def test_counts(ctx: GateContext, cmd: str = "npm test", min_passed: int = 1,
                max_failed: int = 0, parser: str = "vitest",
                shell: str = "sh", timeout: int | None = None) -> GateResult:
    c = ohexec.run(cmd, ctx.worktree, shell=shell,
                   timeout=timeout or ctx.timeout_s,
                   log_dir=ctx.log_dir,
                   name=_command_log_name(ctx, "test_counts", cmd),
                   env=_attempt_env(ctx))
    fn = PARSERS.get(parser)
    if fn is None:
        return GateResult("test_counts", False, observed=f"no parser {parser!r}",
                          expected=sorted(PARSERS), evidence_path=c.stdout_path)
    counts = fn(c.stdout + c.stderr)
    ok = (c.returncode == 0 and counts["passed"] >= min_passed
          and counts["failed"] <= max_failed)
    return GateResult("test_counts", ok,
                      observed={"exit": c.returncode, **counts},
                      expected={"exit": 0, "passed>=": min_passed,
                                "failed<=": max_failed},
                      evidence_path=c.stdout_path, detail=f"command: {cmd}")


@register("tree_clean", lambda a: "git status --porcelain prints nothing")
def tree_clean(ctx: GateContext) -> GateResult:
    c, bad = _git_or_fail(ctx, "status --porcelain", check="tree_clean",
                          log_name="gate-status", expected="clean")
    if bad is not None:
        return bad
    dirty = c.stdout.strip()
    return GateResult("tree_clean", dirty == "",
                      observed=dirty.splitlines()[:20] or "clean",
                      expected="clean", evidence_path=c.stdout_path)


@register("file_contains",
          lambda a: (f"the file {a.get('path', '')} in the worktree holds "
                     + ("the required token (the failure message names it)"
                        if a.get("hidden") else repr(a.get("text", "")))))
def file_contains(ctx: GateContext, path: str = "", text: str = "",
                  hidden: bool = False) -> GateResult:
    """With `hidden`, the position block does not name `text`; only a failure
    does. The retry shape uses it so that attempt 2 must read the failure."""
    where = (ctx.worktree / path) if path else None
    if (where is None or Path(path).is_absolute() or ".." in Path(path).parts
            or not text):
        return GateResult("file_contains", False, observed="bad arguments",
                          expected=text or "a non-empty text",
                          detail="path must be relative, inside the worktree, "
                                 "and text must not be empty")
    try:
        body = where.read_text(encoding="utf-8")
    except OSError:
        body = None
    if body is None:
        observed = f"{path} is absent"
    elif text in body:
        return GateResult("file_contains", True, observed="present",
                          expected=text)
    else:
        observed = f"{text!r} is absent from {path}"
    return GateResult("file_contains", False, observed=observed, expected=text)


@register("ownership",
          lambda a: (f"git diff --name-only {_since_words(a)}..HEAD is a subset "
                     f"of {list(a.get('allowed', []))}"))
def ownership(ctx: GateContext, allowed: list[str] | None = None,
              since: str = SINCE_BASE) -> GateResult:
    allowed = list(allowed if allowed is not None else ctx.write_scope)
    start, bad = _resolve_since(ctx, since, check="ownership", expected=allowed)
    if bad is not None:
        return bad
    c, bad = _git_or_fail(ctx, f"diff --name-only {start}..HEAD",
                          check="ownership", log_name="gate-ownership",
                          expected=allowed)
    if bad is not None:
        return bad
    touched = [p for p in c.stdout.split("\n") if p.strip()]
    strays = [p for p in touched
              if not any(p == a or fnmatch.fnmatch(p, a) for a in allowed)]
    return GateResult("ownership", not strays, observed=strays or "none",
                      expected=allowed, evidence_path=c.stdout_path,
                      detail="paths outside the ownership list" if strays else None)


@register("paths_untouched",
          lambda a: f"{list(a.get('globs', []))} unchanged since {_since_words(a)}")
def paths_untouched(ctx: GateContext, globs: list[str] | None = None,
                    since: str = SINCE_BASE) -> GateResult:
    globs = list(globs or [])
    start, bad = _resolve_since(ctx, since, check="paths_untouched",
                                expected=f"none of {globs}")
    if bad is not None:
        return bad
    c, bad = _git_or_fail(ctx, f"diff --name-only {start}..HEAD",
                          check="paths_untouched", log_name="gate-untouched",
                          expected=f"none of {globs}")
    if bad is not None:
        return bad
    touched = [p for p in c.stdout.split("\n") if p.strip()]
    hits = [p for p in touched if any(fnmatch.fnmatch(p, g) or p == g for g in globs)]
    return GateResult("paths_untouched", not hits, observed=hits or "none",
                      expected=f"none of {globs}", evidence_path=c.stdout_path)


AI_ATTRIBUTION = re.compile(
    r"(co-authored-by:\s*(claude|gpt|codex|copilot|gemini|openhands|anthropic|openai)"
    r"|generated with \[?claude"
    r"|generated (?:with|by) (?:claude|chatgpt|copilot|openhands|an ai)"
    r"|🤖 generated)",
    re.IGNORECASE,
)


@register("no_ai_attribution",
          lambda a: f"no AI attribution in any commit message past "
                    f"{_since_words(a)}")
def no_ai_attribution(ctx: GateContext, since: str = SINCE_BASE) -> GateResult:
    start, bad = _resolve_since(ctx, since, check="no_ai_attribution",
                                expected="none")
    if bad is not None:
        return bad
    c, bad = _git_or_fail(ctx, f"log --format=%B {start}..HEAD",
                          check="no_ai_attribution",
                          log_name="gate-attribution", expected="none")
    if bad is not None:
        return bad
    hits = [ln for ln in c.stdout.splitlines() if AI_ATTRIBUTION.search(ln)]
    return GateResult("no_ai_attribution", not hits, observed=hits or "none",
                      expected="none", evidence_path=c.stdout_path)


@register("final_message_matches",
          lambda a: f"the final message matches /{a.get('regex', '')}/")
def final_message_matches(ctx: GateContext, regex: str = "",
                          group: int | None = None) -> GateResult:
    # MULTILINE on purpose: a verdict or a DONE line sits on its own line at the
    # end of a report, so `^DONE$` must anchor to that line and not to the
    # whole message.
    hits = re.findall(regex, ctx.final_text or "", re.MULTILINE)
    observed = hits[-1] if hits else None
    ev = ctx.attempt_dir / "final.md"
    return GateResult("final_message_matches", bool(hits), observed=observed,
                      expected=f"/{regex}/",
                      evidence_path=str(ev) if ev.exists() else None)


def _validate_schema(value: Any, schema: dict, path: str = "$") -> list[str]:
    """A deliberately small JSON Schema subset.

    It supports ``type``, ``required``, ``properties``, ``items``, ``enum``
    and schema-valued ``additionalProperties``.  A type may be one string or
    a list of strings.  That is enough for dynamic maps and nullable report
    fields without adding a dependency to a package that must import on plain
    Python.
    """
    errs: list[str] = []
    declared = schema.get("type")
    types = [declared] if isinstance(declared, str) else list(declared or [])
    kinds = {"object": dict, "array": list, "string": str, "number": (int, float),
             "integer": int, "boolean": bool, "null": type(None)}
    if types:
        def matches(name: str) -> bool:
            if name not in kinds:
                return True
            if name in ("number", "integer") and isinstance(value, bool):
                return False
            return isinstance(value, kinds[name])

        if not any(matches(name) for name in types):
            expected = types[0] if len(types) == 1 else " or ".join(types)
            errs.append(f"{path}: expected {expected}, got {type(value).__name__}")
            return errs
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{path}: {value!r} not in {schema['enum']}")
    if isinstance(value, dict) and (not types or "object" in types):
        properties = schema.get("properties") or {}
        for key in schema.get("required", []):
            if key not in value:
                errs.append(f"{path}: missing required key {key!r}")
        for key, sub in properties.items():
            if key in value:
                errs.extend(_validate_schema(value[key], sub, f"{path}.{key}"))
        additional = schema.get("additionalProperties", True)
        for key in value.keys() - properties.keys():
            if additional is False:
                errs.append(f"{path}: unexpected key {key!r}")
            elif isinstance(additional, dict):
                errs.extend(_validate_schema(
                    value[key], additional, f"{path}[{key!r}]"))
    if isinstance(value, list) and (not types or "array" in types) \
            and "items" in schema:
        for i, item in enumerate(value):
            errs.extend(_validate_schema(item, schema["items"], f"{path}[{i}]"))
    return errs


@register("schema_valid",
          lambda a: (f"the file {a['path']} in the worktree holds one JSON "
                     "object that validates against the step's schema"
                     if a.get("path") else
                     "the final message carries one fenced json block that "
                     "validates against the step's schema"))
def schema_valid(ctx: GateContext, schema: dict | None = None,
                 path: str = "") -> GateResult:
    schema = schema or ctx.schema
    if not schema:
        return GateResult("schema_valid", False, observed="no schema given",
                          expected="a JSON Schema object")
    if path:
        expected = "a JSON file that validates against the step's schema"
        if Path(path).is_absolute() or ".." in Path(path).parts:
            return GateResult("schema_valid", False, observed="bad arguments",
                              expected=expected,
                              detail="path must be relative and inside the "
                                     "worktree")
        try:
            raw = (ctx.worktree / path).read_text(encoding="utf-8")
        except OSError:
            return GateResult("schema_valid", False,
                              observed=f"{path} is absent", expected=expected)
        try:
            file_value = json.loads(raw)
        except json.JSONDecodeError as e:
            return GateResult("schema_valid", False,
                              observed=f"{path} is not valid JSON: {e}",
                              expected=expected)
        errs = _validate_schema(file_value, schema)
        return GateResult("schema_valid", not errs, observed=errs or "valid",
                          expected="no validation errors",
                          evidence_path=str(ctx.worktree / path),
                          detail="; ".join(errs) if errs else None)
    value = ctx.structured
    if value is None:
        result_path = ctx.attempt_dir / "result.json"
        parse_error = None
        if result_path.exists():
            try:
                result = json.loads(result_path.read_text(encoding="utf-8"))
                parse_error = result.get("schema_error")
            except (OSError, json.JSONDecodeError):
                pass
        detail = (str(parse_error) if parse_error else
                  "the agent emitted no valid fenced json block")
        return GateResult("schema_valid", False, observed=parse_error,
                          expected="a parsed object in result.json.structured",
                          evidence_path=str(result_path) if result_path.exists()
                          else None,
                          detail=detail)
    errs = _validate_schema(value, schema)
    return GateResult("schema_valid", not errs, observed=errs or "valid",
                      expected="no validation errors",
                      detail="; ".join(errs) if errs else None)


def _tool_policy_name(name: Any) -> str:
    """One spelling per server. Codex shows `brave-search` as `brave_search`,
    and Claude shows the connector `claude.ai Gmail` as `claude_ai_Gmail`."""
    return re.sub(r"[^a-z0-9]", "_", str(name).strip().lower())


@register("rollcall_matches",
          lambda a: "every tool and MCP server the agent reports was announced "
                    "by its harness" + (" and is inside the workflow tool policy"
                                        if a.get("tool_policy") else "") +
                    (f"; the report names harness executor {a['harness_executor']}" if a.get("harness_executor") else ""))
def rollcall_matches(ctx: GateContext, tool_policy: list[str] | None = None,
                     harness_executor: str | None = None) -> GateResult:
    """The agent's report of its own tool policy against the harness's record.

    The harness executor writes what the harness announced into `result.json`: `tools`
    and `mcp_servers`. The agent reports `tools` and `mcp_servers` in its
    structured final message. A reported name the harness never announced
    fails the check, and so does one outside `tool_policy` when the workflow gives
    one (a hermetic agent). A harness executor that announces no tool list (codex) has
    its tools unchecked, and the observed record says so. When the workflow gives
    `harness_executor`, the report's own `harness_executor` field must equal it.
    """
    result_path = ctx.attempt_dir / "result.json"
    evidence = str(result_path) if result_path.exists() else None
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return GateResult("rollcall_matches", False, observed=f"no result.json: {e}",
                          expected="the harness executor's announced tool policy")
    report = ctx.structured
    if not isinstance(report, dict):
        return GateResult("rollcall_matches", False, observed="no structured report",
                          expected="a report with tools and mcp_servers",
                          evidence_path=evidence)
    announced_tools = {_tool_policy_name(t) for t in result.get("tools") or []}
    announced_servers = {_tool_policy_name(s) for s in result.get("mcp_servers") or []}
    reported_tools = [t for t in report.get("tools") or [] if isinstance(t, str)]
    # An agent may name a server by its tool prefix: Codex spells a plugin tool
    # `mcp__cua_repl.js`, and an agent then reports `mcp__cua_repl`.
    reported_servers = [re.sub(r"^mcp__", "", s) for s in report.get("mcp_servers") or []
                        if isinstance(s, str)]
    problems: list[str] = []
    if harness_executor is not None and report.get("harness_executor") != harness_executor:
        problems.append(f"report names harness executor {report.get('harness_executor')!r}, "
                        f"the step runs on harness executor {harness_executor!r}")
    if announced_tools:
        extra = [t for t in reported_tools if _tool_policy_name(t) not in announced_tools]
        if extra:
            problems.append(f"tools the harness did not announce: {extra}")
    extra = [s for s in reported_servers if _tool_policy_name(s) not in announced_servers]
    if extra:
        problems.append(f"MCP servers the harness did not announce: {extra}")
    if tool_policy is not None:
        allowed = {_tool_policy_name(t) for t in tool_policy}
        outside = [t for t in reported_tools if _tool_policy_name(t) not in allowed]
        if outside:
            problems.append(f"tools outside the workflow tool policy: {outside}")
        servers = [s for s in reported_servers if _tool_policy_name(s) not in allowed]
        if servers:
            problems.append(f"MCP servers outside the workflow tool policy: {servers}")
    observed = {"reported_tools": len(reported_tools),
                "reported_servers": len(reported_servers),
                "announced_tools": len(announced_tools) if announced_tools
                else "none announced; tools unchecked",
                "announced_servers": len(announced_servers)}
    return GateResult("rollcall_matches", not problems, observed=observed,
                      expected="reported tool policy is a subset of the announced one",
                      evidence_path=evidence,
                      detail="; ".join(problems) if problems else None)


# --------------------------------------------------------------- conjunction


def run_gate(ctx: GateContext, gate) -> GateReport:
    """Run every check in workflow order. Every sub-result is recorded, including
    the ones after the first failure, because the retry brief needs all of them."""
    report = GateReport(coord=ctx.coord, passed=True, checks=[])
    if gate is None or not gate.checks:
        report.passed = True
        return report
    for index, spec in enumerate(gate.checks, start=1):
        ctx.check_index = index
        fn = REGISTRY.get(spec.name)
        if fn is None:
            report.checks.append(GateResult(spec.name, False,
                                            observed="unknown check",
                                            expected=sorted(REGISTRY)))
            report.passed = False
            continue
        try:
            res = fn(ctx, **dict(spec.args))
        except Exception as e:                      # a check must never crash a run
            res = GateResult(spec.name, False, observed=f"{type(e).__name__}: {e}",
                             expected="the check to run")
        report.checks.append(res)
        report.passed = report.passed and res.passed
    return report


def write_report(attempt_dir: Path, report: GateReport) -> Path:
    p = Path(attempt_dir) / "gate.json"
    p.write_text(json.dumps(report.to_dict(), indent=2, default=str),
                 encoding="utf-8")
    return p

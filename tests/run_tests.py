#!/usr/bin/env python
"""The one command that runs the ohflow suite.

    python ohflow/tests/run_tests.py --changed  # the tests the changes since main reach
    python ohflow/tests/run_tests.py --changed 88beb7d # the tests the changes since a commit reach
    python ohflow/tests/run_tests.py            # deterministic tests only
    python ohflow/tests/run_tests.py --e2e      # plus the real-model run
    python ohflow/tests/run_tests.py -k failure # only matching test names
    python ohflow/tests/run_tests.py --shard 1/3 # one third of the tests
    python ohflow/tests/run_tests.py --real-process # after the shards: the real-process tests
    python ohflow/tests/run_tests.py --durations 15 # name the slowest tests
    python ohflow/tests/run_tests.py --test-timeout 60 # one test may run 60 s

Why a script and not pytest. This box's interpreter is Python 3.14 and has no
pytest.
The brief asks that a fresh clone plus one command works. `unittest` is in the
standard library, so it always does. What this script adds on top of
`python -m unittest` is the part `unittest` gets wrong for this suite: it prints
every skip with its reason, unconditionally, instead of a silent `s`.

Every path is resolved from `__file__`. The script may be run from any working
directory and it reads nothing outside this repository.

Exit code 0 when everything that ran passed, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback
import unittest
from dataclasses import dataclass, field
from pathlib import Path

os.environ["OHFLOW_SETTINGS"] = os.environ.get(
    "OHFLOW_TEST_SETTINGS",
    str(Path(__file__).resolve().with_name("operator.settings.json")))

HERE = Path(__file__).resolve().parent          # ohflow/tests
SKILL_ROOT = HERE.parent                        # ohflow
IMPORT_ROOT = SKILL_ROOT / "scripts"            # holds the `ohflow` package

for p in (str(SKILL_ROOT), str(IMPORT_ROOT), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

from ohflow import proc
from summary_schema_audit import SummarySchemaAudit
from support import is_real_process


DEFAULT_TEST_TIMEOUT_S = 300.0
E2E_TEST_TIMEOUT_S = 1800.0


def thread_stacks() -> str:
    """The stack of every thread of this process, each under its thread's name."""
    names = {t.ident: t.name for t in threading.enumerate()}
    parts = []
    for ident, frame in sys._current_frames().items():
        parts.append(f"thread {names.get(ident, ident)}:\n"
                     + "".join(traceback.format_stack(frame)))
    return "\n".join(parts)


class ReasonedResult(unittest.TextTestResult):
    """A result that remembers why things were skipped, and how long each test ran.

    It also holds the per-test time limit. A test past its limit ends the whole
    run: the limit names the test, prints every thread's stack, ends the
    children the run still manages and every other descendant of the run, and
    exits 1, also when the stream refuses the report. A child the hung test
    started would otherwise keep the run's stdout open, and a caller that
    reads the run through a pipe would wait for that child. A timer thread
    does this and no signal, because Windows has no alarm signal, and because
    a test that waits on a child or a lock would not see an exception raised
    in it either.
    """

    def __init__(self, *a, test_timeout: float = 0.0, **kw):
        super().__init__(*a, **kw)
        self.skip_reasons: list[tuple[str, str]] = []
        self.timings: list[tuple[float, str]] = []
        self.test_timeout = test_timeout
        self._started = 0.0
        self._limit: threading.Timer | None = None

    def startTest(self, test):
        self._started = time.perf_counter()
        if self.test_timeout > 0:
            self._limit = threading.Timer(self.test_timeout, self._timed_out,
                                          args=(test.id(),))
            self._limit.daemon = True
            self._limit.start()
        super().startTest(test)

    def stopTest(self, test):
        if self._limit is not None:
            self._limit.cancel()
            self._limit = None
        super().stopTest(test)
        self.timings.append((time.perf_counter() - self._started, test.id()))

    def _timed_out(self, test_id: str) -> None:
        try:
            out = self.stream
            out.write(f"\nTIMED OUT after {self.test_timeout:g}s: {test_id}\n")
            out.write("  --test-timeout sets the limit of one test; the run ends "
                      "here and the tests after this one did not run\n\n")
            out.flush()
            out.write(thread_stacks().encode("ascii", "backslashreplace").decode())
            out.write(f"\nran {self.testsRun - 1} tests before it   "
                      f"timed out: {test_id}\n")
            out.flush()
        finally:
            try:
                proc.end_owned_groups()
            finally:
                try:
                    proc.end_descendants()
                finally:
                    os._exit(1)

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.skip_reasons.append((str(test), reason))


class ReasonedRunner(unittest.TextTestRunner):
    resultclass = ReasonedResult

    def __init__(self, *a, test_timeout: float = 0.0, **kw):
        super().__init__(*a, **kw)
        self.test_timeout = test_timeout

    def _makeResult(self):
        return self.resultclass(self.stream, self.descriptions, self.verbosity,
                                test_timeout=self.test_timeout)


def checkout_state(root: Path) -> tuple[str, frozenset[str]] | None:
    """The HEAD commit and the `git status` lines of the checkout at `root`.

    None when `root` is not inside a git checkout, or git is not there.
    """
    import subprocess

    def git(*args: str) -> str | None:
        try:
            done = subprocess.run(["git", "-C", str(root), *args],
                                  capture_output=True, text=True, timeout=60,
                                  stdin=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            return None
        return done.stdout if done.returncode == 0 else None

    head = git("rev-parse", "HEAD")
    status = git("status", "--porcelain", "--untracked-files=all")
    if head is None or status is None:
        return None
    return head.strip(), frozenset(status.splitlines())


def checkout_changes(before, after) -> list[str]:
    """What a run did to the checkout: one line per fault, none when clean.

    Only what the run added counts, so a checkout that was dirty before the
    run is no fault.
    """
    if before is None or after is None:
        return []
    changes = []
    if before[0] != after[0]:
        changes.append(f"HEAD moved from {before[0][:12]} to {after[0][:12]}: "
                       "a test committed into the source checkout")
    changes += [f"new in git status: {line}"
                for line in sorted(after[1] - before[1])]
    return changes


def name_patterns(patterns) -> list[str]:
    """The loader's name patterns for every `-k` given: a test runs when its
    name holds any one of them."""
    return [f"*{p}*" for p in (patterns or [])]


BUDGET_S = 300.0
SECONDS_FILE = HERE / "file_seconds.json"
SMOKE = ("test_verb_validate.py", "test_suite_02_git_identity.py",
         "test_rundir_01_reads_a_run.py", "test_defect_10_git_gates_fail_closed.py",
         "test_stage_09_summary_schema.py")
OWN_TESTS = {
    "run_tests.py": ("test_suite_01_test_timeout.py", "test_suite_03_changed_selection.py",
                     "test_defect_63_the_suite_leaves_the_checkout_alone.py",
                     "test_defect_71_go_hint_and_repeatable_k.py"),
    "support.py": ("test_suite_02_git_identity.py",
                   "test_defect_42_tests_ignore_the_agents_environment.py"),
    "verb_support.py": ("test_verb_validate.py", "test_verb_status.py"),
    "summary_schema_audit.py": ("test_stage_09_summary_schema.py",),
    "file_seconds.json": ("test_suite_03_changed_selection.py",),
    "__init__.py": (),
    "operator.settings.json": (),
}


@dataclass
class Pick:
    reasons: list[str] = field(default_factory=list)
    direct: bool = False
    changed: bool = False


@dataclass
class Fit:
    keep: list[str]
    left: list[str]
    total_s: float
    keep_s: float


def imports(text: str, dotted: str) -> bool:
    name = re.escape(dotted)
    if re.search(rf"^\s*from\s+{name}\s+import\b", text, re.M):
        return True
    if re.search(rf"^\s*import\s+[^\n]*(?<![\w.]){name}(?![\w.])", text, re.M):
        return True
    parent, _, leaf = dotted.rpartition(".")
    if not parent:
        return False
    listed = re.finditer(rf"^\s*from\s+{re.escape(parent)}\s+import\s+"
                         r"(\([^)]*\)|[^\n]*(?:\\\n[^\n]*)*)", text, re.M)
    return any(re.search(rf"(?<!\w){re.escape(leaf)}(?!\w)", m[1]) for m in listed)


def names(text: str, word: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(word)}(?![\w-])", text) is not None


def names_doc(text: str, path: str) -> bool:
    parts = path.split("/")
    joined = r"\s*/\s*".join(f'"{re.escape(part)}"' for part in parts)
    if len(parts) == 1:
        joined = r"(?:ROOT|parents\[\d\])\s*/\s*" + joined
    elif path in text:
        return True
    return re.search(joined, text) is not None


def select(changed: list[str], sources: dict[str, str]) -> dict[str, Pick]:
    tests = sorted(n for n in sources if n.startswith("test_") and n.endswith(".py"))
    helpers = sorted(n for n in sources if n.endswith("_support.py"))
    picks: dict[str, Pick] = {}

    def add(test: str, reason: str, direct: bool = True, changed: bool = False):
        if test not in sources:
            return
        pick = picks.setdefault(test, Pick())
        if reason not in pick.reasons:
            pick.reasons.append(reason)
        pick.direct = pick.direct or direct
        pick.changed = pick.changed or changed

    def naming(word: str, own: str = "") -> bool:
        found = False
        for test in tests:
            if names(sources[test], word):
                add(test, f"names {word}")
                found = True
        for helper in helpers:
            if helper != own and names(sources[helper], word):
                for test in tests:
                    if imports(sources[test], helper[:-3]):
                        add(test, f"imports {helper[:-3]}, which names {word}", direct=False)
                        found = True
        return found

    for path in changed:
        parts = path.split("/")
        name = parts[-1]
        stem = name.rsplit(".", 1)[0]
        if parts[0] == "tests":
            if len(parts) == 2 and name.startswith("test_") and name.endswith(".py"):
                add(name, "changed test file", changed=True)
                continue
            if len(parts) == 2 and name in OWN_TESTS:
                for test in OWN_TESTS[name]:
                    add(test, f"a test of {name}")
            elif len(parts) > 3 and not name.endswith(".py"):
                naming(parts[2]) or naming(parts[1])
            else:
                naming(stem if name.endswith(".py") else name, own=name)
            for test in SMOKE:
                add(test, f"smoke test for {path}", direct=False)
        elif parts[:2] == ["scripts", "ohflow"] and name.endswith(".py"):
            if parts[2:] == ["__init__.py"]:
                for test in SMOKE:
                    add(test, f"smoke test for {path}")
                continue
            dotted = ".".join(parts[1:])[:-3].removesuffix(".__init__")
            for test in tests:
                if imports(sources[test], dotted):
                    add(test, f"imports {dotted}")
            for test in tests:
                if stem in test[len("test_"):-len(".py")]:
                    add(test, f"name holds {stem}", direct=False)
        elif name.endswith(".md") and parts[0] != "scripts":
            for test in tests:
                if names_doc(sources[test], path):
                    add(test, f"names {path}")
        else:
            naming(stem if name.endswith(".py") else name)
    return picks


def fit_budget(picks: dict[str, Pick], seconds: dict[str, float], default_s: float,
               budget_s: float = BUDGET_S) -> Fit:
    def cost(test: str) -> float:
        return float(seconds.get(test, default_s))

    total = sum(cost(t) for t in picks)
    if total <= budget_s:
        return Fit(sorted(picks), [], total, total)
    keep = [t for t, p in picks.items() if p.changed]
    used = sum(cost(t) for t in keep)
    rest = sorted((t for t, p in picks.items() if p.direct and not p.changed),
                  key=lambda t: (cost(t), t))
    for test in rest:
        if used + cost(test) > budget_s:
            break
        keep.append(test)
        used += cost(test)
    left = sorted((t for t in picks if t not in keep), key=lambda t: (-cost(t), t))
    return Fit(sorted(keep), left, total, used)


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", "core.quotepath=off", "-C", str(SKILL_ROOT), *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", stdin=subprocess.DEVNULL, timeout=60)


def git_lines(*args: str) -> list[str]:
    done = git(*args)
    if done.returncode != 0:
        raise SystemExit(f"--changed: git {' '.join(args)} failed: {done.stderr.strip()}")
    return [line for line in done.stdout.splitlines() if line.strip()]


def changed_files(base: str) -> tuple[str, str, list[str]]:
    label = base or "the merge base of HEAD and main"
    if not base:
        found = git("merge-base", "HEAD", "main")
        if found.returncode != 0:
            raise SystemExit("--changed: HEAD has no merge base with main; "
                             "name the base commit: --changed <commit>")
        base = found.stdout.strip()
    sha = git("rev-parse", "--verify", "--quiet", f"{base}^{{commit}}")
    if sha.returncode != 0:
        raise SystemExit(f"--changed: {base!r} names no commit in {SKILL_ROOT}")
    commit = sha.stdout.strip()
    files = git_lines("diff", "--name-only", "--no-renames", "--relative", commit, "--")
    files += git_lines("ls-files", "--others", "--exclude-standard")
    return commit, label, sorted(set(files))


def read_sources(tests_dir: Path = HERE) -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8", errors="replace")
            for p in sorted(tests_dir.glob("*.py"))}


def read_seconds(path: Path = SECONDS_FILE) -> tuple[dict[str, float], float]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["files"], float(data["default"])


def changed_selection(base: str) -> list[str]:
    commit, label, files = changed_files(base)
    picks = select(files, read_sources())
    seconds, default_s = read_seconds()
    fit = fit_budget(picks, seconds, default_s)
    print(f"  changed: {len(files)} files since {commit[:12]} ({label}), "
          "committed or not")
    for path in files:
        print(f"    {path}")
    print(f"  selected: {len(picks)} test files, about {fit.total_s:.0f} s by "
          f"{SECONDS_FILE.name}")
    for test in sorted(picks):
        cost = float(seconds.get(test, default_s))
        print(f"    {cost:5.0f} s  {test}: {'; '.join(picks[test].reasons)}")
    if fit.left:
        print(f"  budget: about {fit.total_s:.0f} s is past the {BUDGET_S:.0f} s budget, "
              f"so {len(fit.keep)} files run, about {fit.keep_s:.0f} s: the changed "
              "tests and the direct part, cheapest first. CI runs the full suite.")
        print(f"  left to CI ({len(fit.left)}): " + ", ".join(
            f"{t} ({float(seconds.get(t, default_s)):.0f} s)" for t in fit.left))
    if not picks:
        print("  no test file reaches these changes; check_docs.py runs alone")
    return fit.keep


def run_check_docs() -> int:
    started = time.time()
    done = subprocess.run([sys.executable, str(HERE / "check_docs.py")],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", stdin=subprocess.DEVNULL)
    lines = (done.stdout + done.stderr).strip().splitlines() or ["no output"]
    print(f"check_docs.py: {lines[-1]} ({time.time() - started:.1f}s)")
    for line in lines[:-1]:
        print(f"  {line}")
    return done.returncode


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="run_tests.py",
        description="the ohflow regression suite")
    ap.add_argument(
        "--e2e", action="store_true",
        help="also run the end-to-end test against a real model. It needs "
             "ZAI_CODING_CN_API_KEY and ready pi, claude and codex "
             "harnesses, and it costs several minutes of wall time.")
    ap.add_argument(
        "--changed", metavar="BASE", nargs="?", const="", default=None,
        help="run only the test files that the files changed since BASE reach "
             "(default: the merge base of HEAD and main), committed or not, "
             "plus check_docs.py. A changed test file runs itself; a changed "
             "ohflow module runs the test files that import it directly and the "
             "ones whose name holds its name; a changed Markdown file runs "
             "the test files that name its path from the skill root. Past about "
             f"{BUDGET_S:.0f} s it runs the "
             "changed tests and the direct part, cheapest first. CI runs the "
             "full suite.")
    ap.add_argument("-k", dest="pattern", action="append", default=None,
                    help="run only tests whose name contains this substring; "
                         "repeat it to run the tests that match any of them")
    ap.add_argument("--shard", metavar="K/N", default=None,
                    help="run shard K of N (1-based). The tests sorted by "
                         "name go to the shards in turn, so the N shards "
                         "together run every test once, except the tests marked real-process.")
    ap.add_argument("--real-process", action="store_true",
                    help="run only the tests marked real-process, in one "
                         "process. --shard leaves them out, so run this "
                         "after the parallel shards finish.")
    ap.add_argument("--durations", metavar="N", type=int, default=0,
                    help="after the run, print the N slowest tests")
    ap.add_argument("--test-timeout", metavar="SECONDS", type=test_timeout,
                    default=None,
                    help="the time one test may run (default "
                         f"{DEFAULT_TEST_TIMEOUT_S:g}, and "
                         f"{E2E_TEST_TIMEOUT_S:g} with --e2e, whose live "
                         "matrix is one test). A test past it ends "
                         "the run with exit code 1, its name and every "
                         "thread's stack. 0 turns the limit off.")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="name every test as it runs")
    ap.add_argument("-q", "--quiet", action="store_true",
                    help="dots only")
    return ap


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """The parsed flags, with the limit of one test resolved: an explicit
    `--test-timeout` wins, else `--e2e` gets the longer default."""
    ns = build_parser().parse_args(argv)
    if ns.test_timeout is None:
        ns.test_timeout = E2E_TEST_TIMEOUT_S if ns.e2e else DEFAULT_TEST_TIMEOUT_S
    return ns


def test_timeout(text: str) -> float:
    try:
        seconds = float(text)
    except ValueError:
        seconds = -1.0
    if not 0 <= seconds < float("inf"):
        raise argparse.ArgumentTypeError(
            f"takes a number of seconds, 0 or more, got {text!r}")
    return seconds


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def parse_shard(text: str) -> tuple[int, int]:
    try:
        k, n = (int(part) for part in text.split("/"))
    except ValueError:
        k = n = 0
    if not 1 <= k <= n:
        raise SystemExit(f"--shard takes K/N with 1 <= K <= N, got {text!r}")
    return k, n


def main(argv: list[str] | None = None) -> int:
    ns = parse_args(argv)
    shard = parse_shard(ns.shard) if ns.shard else None
    if shard and ns.real_process:
        raise SystemExit("--shard and --real-process are separate passes: "
                         "run the shards, then --real-process")
    if ns.changed is not None and (shard or ns.real_process):
        raise SystemExit("--changed picks its own test files; it takes no --shard "
                         "or --real-process")
    # A run without a console (run-hidden.vbs) has no stdin handle, and every
    # test that starts a child through plain `subprocess` would fail on it.
    proc.ensure_stdin()

    # The end-to-end test reads this variable and skips when it is unset. The
    # flag is the only way it is ever set by this script, so the deterministic
    # suite can never start a provider call by accident.
    if ns.e2e:
        os.environ["OHFLOW_E2E"] = "1"

    verbosity = 2 if ns.verbose else (0 if ns.quiet else 1)

    loader = unittest.TestLoader()
    if ns.pattern:
        loader.testNamePatterns = name_patterns(ns.pattern)
    if ns.changed is not None:
        changed_t0 = time.time()
        print("--changed selection")
        chosen = changed_selection(ns.changed)
        docs_exit = run_check_docs()
        if not chosen:
            print(f"--changed: no unittest, check_docs.py only, in "
                  f"{time.time() - changed_t0:.1f}s")
            return docs_exit
        suite = loader.loadTestsFromNames([f"tests.{t[:-3]}" for t in chosen])
    else:
        suite = loader.discover(start_dir=str(HERE), pattern="test_*.py",
                                top_level_dir=str(SKILL_ROOT))
    left_out = 0
    if shard or ns.real_process:
        tests = sorted(flatten(suite), key=lambda t: t.id())
        lane = [t for t in tests if is_real_process(t)]
        if ns.real_process:
            suite = unittest.TestSuite(lane)
        else:
            k, n = shard
            rest = [t for t in tests if not is_real_process(t)]
            suite = unittest.TestSuite(rest[k - 1::n])
            left_out = len(lane)

    print(f"ohflow suite   python {sys.version.split()[0]}")
    print(f"  tests:  {HERE}")
    print(f"  ohflow: {IMPORT_ROOT / 'ohflow'}")
    print(f"  e2e:    {'requested with --e2e' if ns.e2e else 'off (pass --e2e to include it)'}")
    if shard:
        print(f"  shard:  {shard[0]} of {shard[1]}; {left_out} real-process "
              f"tests left out, run --real-process after the shards")
    if ns.real_process:
        print("  lane:   real-process tests only")
    print(f"  limit:  "
          + (f"{ns.test_timeout:g} s for one test (--test-timeout)"
             if ns.test_timeout else "off (--test-timeout 0)"))
    print("")

    t0 = time.time()
    checkout_before = checkout_state(SKILL_ROOT)
    runner = ReasonedRunner(verbosity=verbosity, stream=sys.stdout,
                            test_timeout=ns.test_timeout)
    with SummarySchemaAudit() as summary_audit:
        result = runner.run(suite)
    elapsed = time.time() - t0
    # A test writes under its own temp dir and nowhere else. A commit or a new
    # path in the source checkout means one wrote outside it.
    checkout_faults = checkout_changes(checkout_before,
                                       checkout_state(SKILL_ROOT))

    # A suite that silently skips its only real test is worse than one that
    # never had it. Every skip is named here with the reason it carried.
    if result.skip_reasons:
        print("")
        print(f"SKIPPED ({len(result.skip_reasons)}) - each with its reason:")
        for name, reason in result.skip_reasons:
            print(f"  - {name}")
            print(f"      {reason}")
    if ns.durations:
        print("")
        print(f"SLOWEST {ns.durations}:")
        for seconds, name in sorted(result.timings, reverse=True)[:ns.durations]:
            print(f"  {seconds:7.1f}s  {name}")
    print("")
    print(f"summary schema checks: {summary_audit.checked}   "
          f"unexpected rejections: {summary_audit.rejected}")
    audit_ok = (summary_audit.rejected == 0
                and (summary_audit.checked > 0 or ns.pattern is not None
                     or ns.real_process or ns.changed is not None))
    if not audit_ok:
        reason = ("the unfiltered suite produced no summary audit receipts"
                  if summary_audit.checked == 0
                  else "one or more summaries failed schema validation")
        print(f"SUMMARY SCHEMA AUDIT FAILED: {reason}")
    elif summary_audit.checked == 0:
        print("summary schema audit: this filtered selection produced no "
              "Engine summary")
    if checkout_faults:
        print(f"SOURCE CHECKOUT CHANGED ({len(checkout_faults)}): a test "
              "wrote outside its temp dir")
        for fault in checkout_faults:
            print(f"  - {fault}")
    ran_nothing = result.testsRun == 0
    if ran_nothing:
        print("NO TESTS RAN: the selection matched no test, so it proves nothing")
    print(f"ran {result.testsRun} tests in {elapsed:.1f}s   "
          f"failures={len(result.failures)} errors={len(result.errors)} "
          f"skipped={len(result.skipped)}")
    docs_ok = True
    if ns.changed is not None:
        docs_ok = docs_exit == 0
        print(f"--changed: {len(chosen)} test files and check_docs.py in "
              f"{time.time() - changed_t0:.1f}s"
              + ("" if docs_ok else "   CHECK_DOCS FAILED"))
    return 0 if (result.wasSuccessful() and audit_ok and docs_ok
                 and not checkout_faults and not ran_nothing) else 1


if __name__ == "__main__":
    sys.exit(main())

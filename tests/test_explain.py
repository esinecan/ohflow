"""`ohflow explain` prints the step inspector as bounded text.

Before: an orchestrating agent triaged a failed step by reading `/api/evidence`
and `/api/agent`, routes that exist only while the dashboard serves, and by
joining the gate, the failure class, the retry decision and the attention item
itself. Now one call prints them for one attempt, each with its evidence, under
a size cap.

The spec is `docs/history/orchestrator-visibility.md`, "Utility 2".
"""

from __future__ import annotations

import json
import re

from dashboard_support import (G1_RUN, T0, RunLog, agent, copy_tree, mark_alive,
                               workflow_json)
from ohflow import explain, rundir
from ohflow.tool_output import ToolOutputWriter
from support import TempCase
from verb_support import call

FLAKY = "01.sweep/01.flaky"
A, B = "01.alpha/01.a", "01.alpha/02.b"
SPENT = "retry budget spent: 1 of 1 retries used for this work"
FAILED_CHECK = {"name": "tests_pass", "passed": False, "observed": "exit 1",
                "expected": "exit 0", "detail": "3 of 12 tests failed",
                "evidence_path": None}
OK_CHECK = {"name": "tree_clean", "passed": True, "observed": "clean",
            "expected": "clean", "detail": None, "evidence_path": None}


def quarantined_run(run) -> RunLog:
    """Step a failed its gate and spent its one retry; step b passed."""
    workflow_json(run, [("Alpha", [agent("a", retry_max=1), agent("b")], 2)])
    log = RunLog(run).phase(1, "01.alpha", "Alpha", [A, B], 2)
    mark_alive(run)
    gate = {"coord": A, "passed": False, "checks": [OK_CHECK, FAILED_CHECK]}
    (log.start(2, B).finish(12, B, 1, "passed")
        .start(2, A)
        .finish(20, A, 1, "quarantined", failure_class="structural", gate=gate)
        .add(20, "retry_decided", A, 1, retry_decision=SPENT))
    return log


class ADeferredAttemptOnARecordedRun(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.dir = copy_tree(G1_RUN, self.tmp / "runs" / "g1")

    def test_1_the_transient_attempt_names_its_class_signature_and_decision(self):
        code, lines = call("explain", "--run", self.dir, "--step", "flaky",
                           "--attempt", 1)
        self.assertEqual(code, 0, lines)
        self.assertEqual(
            lines[0],
            f"EXPLAIN {FLAKY} attempt 1: deferred, transient: 429; no retry: "
            "the step was deferred on a transient fault and reached no "
            "verdict; auto-resume owns it")
        cause = [l for l in lines if l.startswith("cause: ")]
        self.assertEqual(len(cause), 1, lines)
        self.assertIn("Rate limit reached", cause[0])
        self.assertTrue(cause[0].endswith("· run-log.jsonl:8"), cause[0])

    def test_2_without_attempt_the_newest_is_explained_and_both_are_listed(self):
        code, lines = call("explain", "--run", self.dir, "--step", FLAKY)
        self.assertEqual(code, 0, lines)
        self.assertTrue(lines[0].startswith(f"EXPLAIN {FLAKY} attempt 2: "
                                            "passed; "), lines[0])
        attempts = [l for l in lines if l.startswith("attempt ")]
        self.assertEqual([l.split(":")[0] for l in attempts],
                         ["attempt 1", "attempt 2"])
        self.assertIn("deferred", attempts[0])
        self.assertIn("next: nothing waits on a person for this step", lines)


class TheOpenTimeStopsWithTheAttempt(TempCase):
    """A call a kill left open reads its age to the stop, not to the clock."""

    def setUp(self) -> None:
        super().setUp()
        self.dir = self.run_dir("r-open-time")
        workflow_json(self.dir, [("Alpha", [agent("a")], 1)])
        mark_alive(self.dir)
        self.log = RunLog(self.dir).phase(1, "01.alpha", "Alpha", [A], 1)
        adir = rundir.attempt_dir(self.dir, A, 1)
        adir.mkdir(parents=True, exist_ok=True)
        ToolOutputWriter(adir).start("c1", "bash", "sleep 900", at=T0 + 4)

    def test_an_ended_attempt_measures_the_open_time_to_its_end(self):
        self.log.start(2, A).finish(
            20, A, 1, "timeout",
            error="the execution timeout stopped the attempt")
        call = explain.explain_data(self.dir, A, 1, now=T0 + 100_000)[
            "tool_output"]["call"]
        self.assertTrue(call["open"])
        self.assertEqual(call["since_s"], 16.0)

    def test_a_running_attempt_still_measures_the_open_time_to_now(self):
        self.log.start(2, A)
        call = explain.explain_data(self.dir, A, 1, now=T0 + 100)[
            "tool_output"]["call"]
        self.assertTrue(call["open"])
        self.assertEqual(call["since_s"], 96.0)


class AQuarantinedStepWithItsBudgetSpent(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.dir = self.run_dir("r-explain")
        self.log = quarantined_run(self.dir)

    def test_3_the_failed_check_the_gate_file_and_the_next_step(self):
        adir = rundir.attempt_dir(self.dir, A, 1)
        adir.mkdir(parents=True, exist_ok=True)
        (adir / "gate.json").write_text(json.dumps(
            {"coord": A, "passed": False, "checks": [OK_CHECK, FAILED_CHECK]}),
            encoding="utf-8")
        code, lines = call("explain", "--run", self.dir, "--step", "a")
        self.assertEqual(code, 0, lines)
        self.assertEqual(lines[0], f"EXPLAIN {A} attempt 1: quarantined, "
                                   f"structural; {SPENT}")
        failed = [l for l in lines if l.startswith("gate failed: ")]
        self.assertEqual(len(failed), 1, lines)
        self.assertIn("tests_pass (observed exit 1, expected exit 0: 3 of 12 "
                      "tests failed)", failed[0])
        self.assertIn("phases/01.alpha/01.a/attempts/01/gate.json", failed[0])
        self.assertIn("gate passed: tree_clean", lines)
        nexts = [l for l in lines if l.startswith("next: ")]
        self.assertEqual(len(nexts), 1, lines)
        self.assertRegex(nexts[0], r"^next: intervention failed_step: no "
                                   r"further start by the engine: retry "
                                   r"budget spent")

    def test_4_a_recorded_tool_call_prints_its_command_exit_and_tail(self):
        adir = rundir.attempt_dir(self.dir, A, 1)
        adir.mkdir(parents=True, exist_ok=True)
        w = ToolOutputWriter(adir)
        w.start("c1", "bash", "git status", at=3)
        w.end("c1", ok=True, exit=0, text="clean\n")
        w.start("c2", "bash", "npm test", at=5)
        w.write("c2", "".join(f"line {i}\n" for i in range(30)))
        w.end("c2", ok=False, exit=1)
        code, lines = call("explain", "--run", self.dir, "--step", A)
        self.assertEqual(code, 0, lines)
        head = [l for l in lines if l.startswith("tool output: ")]
        self.assertEqual(len(head), 1, lines)
        self.assertIn("npm test", head[0])
        self.assertIn("exit 1", head[0])
        self.assertIn("2 calls", head[0])
        tail = [l for l in lines if l.startswith("  | ")]
        self.assertEqual(tail, [f"  | line {i}" for i in range(20, 30)])

    def test_6_the_text_and_every_line_are_capped(self):
        adir = rundir.attempt_dir(self.dir, A, 1)
        adir.mkdir(parents=True, exist_ok=True)
        (adir / "final.md").write_text("x" * 5000 + "\n" + "y\n" * 4000,
                                       encoding="utf-8")
        w = ToolOutputWriter(adir)
        w.start("c1", "bash", "z" * 3000, at=3)
        w.write("c1", ("w" * 2000 + "\n") * 40)
        w.end("c1", ok=False, exit=2)
        code, lines = call("explain", "--run", self.dir, "--step", A)
        self.assertEqual(code, 0)
        text = "\n".join(lines)
        self.assertLessEqual(len(text), explain.TEXT_CAP)
        for line in lines:
            self.assertLessEqual(len(line), explain.LINE_CAP, line[:80])

    def test_6_a_next_command_is_never_cut(self):
        command = ("python -m ohflow.cli run --workflow " + "w" * 100
                   + " --out runs --resume r-1")
        item = {"group": "intervention", "kind": "paused_run", "coord": None,
                "text": "resume the run " + "x" * 200, "command": command,
                "evidence": {"path": "run-log.jsonl", "line": 9}}
        line = explain._next_line(item)
        self.assertIn(f"`{command}`", line)
        self.assertTrue(line.endswith(" · run-log.jsonl:9"), line)
        self.assertLessEqual(len(line), explain.LINE_CAP)
        item["command"] = "c" * 400
        self.assertIn("`" + "c" * 400 + "`", explain._next_line(item))

    def test_6_a_cut_keeps_the_next_lines(self):
        long = [f"line {i} " + "v" * 280 for i in range(40)]
        nexts = ["next: intervention failed_step: decide"]
        cut = explain.cap_text(long, reserve=len(nexts[0]) + 1) + nexts
        self.assertLessEqual(len("\n".join(cut)), explain.TEXT_CAP)
        self.assertEqual(cut[-2:], [explain.CUT_LINE, nexts[0]])

    def test_6_a_text_over_the_cap_ends_with_the_cut_line(self):
        long = [f"line {i} " + "v" * 280 for i in range(40)]
        cut = explain.cap_text(long)
        self.assertLessEqual(len("\n".join(cut)), explain.TEXT_CAP)
        self.assertEqual(cut[-1], f"... cut at {explain.TEXT_CAP} characters; "
                                  "--json carries every field")

    def test_7_json_carries_the_schema_and_every_key(self):
        code, lines = call("explain", "--run", self.dir, "--step", A, "--json")
        self.assertEqual(code, 0, lines)
        data = json.loads("\n".join(lines))
        self.assertEqual(data["schema"], "ohflow.explain/1")
        self.assertEqual(set(data) - {"schema", "run"},
                         {"step", "attempt", "attempts", "gate", "handover",
                          "final", "tool_output", "activity", "next"})
        self.assertEqual(data["attempt"]["failure_class"], "structural")
        self.assertEqual(data["attempt"]["retry_decision"], SPENT)
        self.assertEqual(data["attempt"]["evidence"],
                         {"path": "run-log.jsonl", "line": 6})
        self.assertEqual(data["next"][0]["group"], "intervention")


def failed_run(run, status: str, error: str | None, checks: list[dict],
               execution_status: str, final: str | None) -> RunLog:
    """Step a ended with `status`, its gate written, its runner's record kept."""
    workflow_json(run, [("Alpha", [agent("a")], 1)])
    log = RunLog(run).phase(1, "01.alpha", "Alpha", [A], 1)
    mark_alive(run)
    gate = {"coord": A, "passed": False, "checks": checks}
    (log.start(2, A)
        .finish(20, A, 1, status, error=error, failure_class="structural",
                gate=gate, result_path="result.json")
        .add(20, "retry_decided", A, 1,
             retry_decision="no retry: the step declares no retry budget"))
    adir = rundir.attempt_dir(run, A, 1)
    adir.mkdir(parents=True, exist_ok=True)
    (adir / "gate.json").write_text(json.dumps(gate), encoding="utf-8")
    (adir / "result.json").write_text(json.dumps(
        {"execution_status": execution_status, "error": error}),
        encoding="utf-8")
    if final is not None:
        (adir / "final.md").write_text(final, encoding="utf-8")
    return log


def no_commit(passed: bool = False) -> dict:
    return {"name": "commits_since_base", "passed": passed, "observed": 0,
            "expected": ">= 1", "detail": None, "evidence_path": None}


DONE_CHECK = {"name": "final_message_matches", "passed": False,
              "observed": None, "expected": "/^DONE\\s*\\Z/", "detail": None,
              "evidence_path": None}
HANDOVER_CHECK = {"name": "handover_exists", "passed": False,
                  "observed": "missing", "expected": "handover.md",
                  "detail": None, "evidence_path": None}
GATE_FILE = "phases/01.alpha/01.a/attempts/01/gate.json"


class AnExecutionErrorIsTheCause(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.dir = self.run_dir("r-error")

    def explain(self) -> list[str]:
        code, lines = call("explain", "--run", self.dir, "--step", "a")
        self.assertEqual(code, 0, lines)
        return lines

    def assert_error_leads(self, lines: list[str], error: str,
                           consequences: list[str]) -> None:
        cause = [i for i, l in enumerate(lines) if l.startswith("cause: ")]
        self.assertEqual(len(cause), 1, lines)
        self.assertEqual(lines[cause[0]],
                         f"cause: execution error: {error} · run-log.jsonl:4")
        prefix = "gate failed after the execution error: "
        failed = [i for i, l in enumerate(lines) if l.startswith(prefix)]
        self.assertEqual([lines[i][len(prefix):].split(" ")[0]
                          for i in failed], consequences, lines)
        self.assertTrue(all(i > cause[0] for i in failed), lines)
        for i in failed:
            self.assertTrue(lines[i].endswith(f" · {GATE_FILE}"), lines[i])
        self.assertFalse([l for l in lines if l.startswith("gate failed: ")])

    def test_a_stalled_attempt_names_the_stall_and_an_interrupted_message(self):
        failed_run(self.dir, "failed", "stall",
                   [no_commit(), HANDOVER_CHECK], "error",
                   "Now I will read the gate module next.\n")
        lines = self.explain()
        self.assert_error_leads(lines, "stall",
                                ["commits_since_base", "handover_exists"])
        self.assertIn("last message, interrupted: Now I will read the gate "
                      f"module next. · phases/01.alpha/01.a/attempts/01/"
                      "final.md", lines)
        self.assertFalse([l for l in lines if l.startswith("final: ")])
        self.assertIn("attempt 1: failed (stall) · no retry: the step "
                      "declares no retry budget · run-log.jsonl:4", lines)
        data = explain.explain_data(self.dir, A)
        self.assertFalse(data["final"]["completed"])
        self.assertEqual(data["attempt"]["error"], "stall")

    def test_an_attempt_killed_by_the_execution_timeout(self):
        failed_run(self.dir, "timeout", "pi-cloud runner was killed",
                   [DONE_CHECK], "error", "Still working on the sleep.\n")
        lines = self.explain()
        self.assertTrue(lines[0].startswith(
            f"EXPLAIN {A} attempt 1: timeout, structural; "), lines[0])
        self.assert_error_leads(lines, "pi-cloud runner was killed",
                                ["final_message_matches"])
        self.assertTrue(any(l.startswith("last message, interrupted: Still "
                                         "working") for l in lines), lines)

    def test_a_timeout_with_no_error_text_names_the_timeout(self):
        failed_run(self.dir, "timeout", None, [DONE_CHECK], "error", None)
        lines = self.explain()
        self.assert_error_leads(lines,
                                "the execution timeout stopped the attempt",
                                ["final_message_matches"])

    def test_a_gate_failure_with_no_execution_error_reads_as_before(self):
        failed_run(self.dir, "failed", None, [OK_CHECK, FAILED_CHECK],
                   "finished", "Tests written; three still fail.\n")
        lines = self.explain()
        self.assertIn("cause: gate tests_pass failed · run-log.jsonl:4", lines)
        self.assertIn("gate failed: tests_pass (observed exit 1, expected "
                      "exit 0: 3 of 12 tests failed) · " + GATE_FILE, lines)
        self.assertIn("final: Tests written; three still fail. · "
                      "phases/01.alpha/01.a/attempts/01/final.md", lines)
        self.assertIn("attempt 1: failed (gate tests_pass) · no retry: the "
                      "step declares no retry budget · run-log.jsonl:4", lines)
        self.assertFalse([l for l in lines if "execution error" in l
                          or "interrupted" in l], lines)
        self.assertTrue(explain.explain_data(self.dir, A)["final"]["completed"])


class TheCallRefuses(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.dir = self.run_dir("r-refuse")
        quarantined_run(self.dir)

    def test_5_a_missing_step(self):
        code, lines = call("explain", "--run", self.dir, "--step", "nope")
        self.assertEqual(code, 1)
        self.assertEqual(lines, ["step 'nope' is missing or ambiguous"])

    def test_5_an_ambiguous_step_id(self):
        run = self.run_dir("r-twice")
        workflow_json(run, [("Alpha", [agent("a")], 1),
                            ("Beta", [agent("a")], 1)])
        RunLog(run).phase(1, "01.alpha", "Alpha", [A], 1)
        code, lines = call("explain", "--run", run, "--step", "a")
        self.assertEqual(code, 1)
        self.assertEqual(lines, ["step 'a' is missing or ambiguous"])

    def test_5_a_directory_that_is_no_run(self):
        code, lines = call("explain", "--run", self.tmp / "nothing",
                           "--step", "a")
        self.assertEqual(code, 1)
        self.assertEqual(len(lines), 1)
        self.assertRegex(lines[0], r"^no ohflow run at ")

    def test_5_a_step_with_no_recorded_attempt(self):
        code, lines = call("explain", "--run", self.dir, "--step", "b",
                           "--attempt", 4)
        self.assertEqual(code, 1)
        self.assertEqual(lines, [f"step {B} has no recorded attempt 4"])


class EveryClaimCarriesItsEvidence(TempCase):

    def test_every_evidence_line_names_the_event_it_claims(self):
        run = copy_tree(G1_RUN, self.tmp / "runs" / "g1")
        data = explain.explain_data(run, FLAKY, 1)
        log = (run / "run-log.jsonl").read_text(encoding="utf-8").splitlines()
        rec = json.loads(log[data["attempt"]["evidence"]["line"] - 1])
        self.assertEqual((rec["event"], rec["coord"], rec["attempt"]),
                         ("attempt_finished", FLAKY, 1))
        for row in data["attempts"]:
            line = row["evidence"]["line"]
            rec = json.loads(log[line - 1])
            self.assertEqual(rec["attempt"], row["attempt"])
            self.assertTrue(re.match(r"attempt_finished|retry_decided",
                                     rec["event"]))

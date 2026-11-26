"""`ohflow compare` diffs two runs by fixed rules.

Before: an orchestrating agent compared two runs by printing `table --by step`
for each, pairing the rows itself, and calling `explain` on every step whose row
looked different. Now one call pairs the steps by id, names every rule that
fired, and prints what each run spent, each side with its evidence.

The spec is `docs/history/orchestrator-visibility.md`, "Utility 4".
"""

from __future__ import annotations

import json

from dashboard_support import G1_RUN, RunLog, agent, copy_tree, workflow_json
from ohflow import compare, rundir
from support import TempCase
from verb_support import call

A, B = "01.alpha/01.a", "01.alpha/02.b"
FAILED_CHECK = {"name": "tests_pass", "passed": False, "observed": "exit 1",
                "expected": "exit 0", "detail": None, "evidence_path": None}
PASSED_CHECK = {"name": "tests_pass", "passed": True, "observed": "exit 0",
                "expected": "exit 0", "detail": None, "evidence_path": None}
CLEAN = {"name": "tree_clean", "passed": True, "observed": "clean",
         "expected": "clean", "detail": None, "evidence_path": None}


def two_step_run(run, *, a_status="passed", a_gate=None, a_class=None,
                 a_steps=None, run_status="finished") -> RunLog:
    """Alpha with steps a and b; a ends as the caller says, b passes."""
    workflow_json(run, [("Alpha", a_steps or [agent("a"), agent("b")], 2)])
    log = RunLog(run).phase(1, "01.alpha", "Alpha", [A, B], 2)
    log.start(2, A).start(2, B)
    log.finish(10, A, 1, a_status, failure_class=a_class,
               gate=a_gate or {"coord": A, "passed": a_status == "passed",
                               "checks": [CLEAN, PASSED_CHECK]})
    log.add(10, "retry_decided", A, 1, retry_decision=(
        "no retry: status 'passed' is not a failure" if a_status == "passed"
        else "retry budget spent: 0 of 0 retries used for this work"))
    log.finish(12, B, 1, "passed")
    return log.run_finished(20, run_status)


def measured(run, coord: str, attempt: int, *, prompt: int, completion: int,
             tool_calls: int, wall: float) -> None:
    """Write the result.json an agent attempt leaves with its usage."""
    adir = rundir.attempt_dir(run, coord, attempt)
    adir.mkdir(parents=True, exist_ok=True)
    (adir / "result.json").write_text(json.dumps({
        "tool_calls": tool_calls, "llm_calls": 2, "wall_seconds": wall,
        "tokens": {"prompt_tokens": prompt, "completion_tokens": completion,
                   "cache_read_tokens": 0, "cache_write_tokens": 0,
                   "reasoning_tokens": 0},
        "cost": 0.0, "cost_source": "unpriced"}), encoding="utf-8")


def rule_lines(lines: list[str], step: str) -> list[str]:
    """The indented rule lines printed under one step line."""
    head = next(i for i, l in enumerate(lines) if l.startswith(f"step {step}:"))
    out = []
    for line in lines[head + 1:]:
        if not line.startswith("  "):
            break
        out.append(line.strip())
    return out


class ARunAgainstAnUnchangedCopy(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.a = copy_tree(G1_RUN, self.tmp / "a")
        self.b = copy_tree(G1_RUN, self.tmp / "b")

    def test_1_nothing_differs_and_every_step_carries_both_evidence_lines(self):
        code, lines = call("compare", "--runs", self.a, self.b)
        self.assertEqual(code, 0, lines)
        self.assertEqual(
            lines[0],
            "COMPARE r-20260929-021128-7974ff3a -> r-20260929-021128-7974ff3a: "
            "2 paired, 0 differ, 0 only in A, 0 only in B")
        steps = [l for l in lines if l.startswith("step ")]
        self.assertEqual([l.split(":")[0] for l in steps],
                         ["step flaky", "step control"])
        for line in steps:
            self.assertRegex(line, r"· A run-log\.jsonl:\d+ · B run-log\.jsonl:\d+$")
        self.assertEqual(rule_lines(lines, "flaky"), [])
        self.assertEqual(rule_lines(lines, "control"), [])

    def test_8_json_carries_the_schema_and_repeats_byte_for_byte(self):
        code, lines = call("compare", "--runs", self.a, self.b, "--json")
        self.assertEqual(code, 0, lines)
        view = json.loads("\n".join(lines))
        self.assertEqual(view["schema"], "ohflow.compare/1")
        for key in ("runs", "totals", "steps"):
            self.assertIn(key, view)
        for side in ("a", "b"):
            self.assertEqual(set(view["runs"][side]) >= {
                "dir", "run_id", "workflow", "status", "started", "finished",
                "elapsed_s", "base_sha"}, True, view["runs"][side])
        step = view["steps"][0]
        self.assertEqual(set(step), {"id", "a", "b", "changes"})
        self.assertTrue({"coord", "status", "attempts", "failure_class",
                         "transient_signature", "retry_decision", "gate",
                         "fingerprint", "sums", "evidence"} <= set(step["a"]))
        _code, again = call("compare", "--runs", self.a, self.b, "--json")
        self.assertEqual(lines, again)


class AStepThatPassedAndThenFailed(TempCase):

    def test_2_status_attempts_failure_class_and_the_gate_check_are_named(self):
        two_step_run(self.tmp / "a")
        two_step_run(self.tmp / "b", a_status="quarantined",
                     a_class="structural",
                     a_gate={"coord": A, "passed": False,
                             "checks": [CLEAN, FAILED_CHECK]},
                     run_status="failed")
        code, lines = call("compare", "--runs", self.tmp / "a", self.tmp / "b")
        self.assertEqual(code, 0, lines)
        self.assertIn("2 paired, 1 differ", lines[0])
        rules = rule_lines(lines, "a")
        self.assertEqual([r.split(":")[0] for r in rules],
                         ["status", "attempts", "failure", "gate", "retry"])
        self.assertIn("passed -> quarantined", rules[0])
        self.assertIn("- -> structural", rules[2])
        self.assertIn("tests_pass passed -> failed (observed exit 1)", rules[3])
        self.assertEqual(rule_lines(lines, "b"), [])


class Sums(TempCase):

    def test_5_sums_print_measured_tokens_and_a_dash_for_an_unmeasured_one(self):
        for name, prompt in (("a", 1000), ("b", 1500)):
            run = self.tmp / name
            two_step_run(run)
            measured(run, A, 1, prompt=prompt, completion=100, tool_calls=4,
                     wall=30.0)
        _code, lines = call("compare", "--runs", self.tmp / "a", self.tmp / "b")
        a_line = next(l for l in lines if l.startswith("step a:"))
        b_line = next(l for l in lines if l.startswith("step b:"))
        self.assertIn("passed -> passed", a_line)
        self.assertIn("attempts 1 -> 1", a_line)
        self.assertIn("tokens 1100 -> 1600", a_line)
        self.assertIn("tool calls 4 -> 4", a_line)
        self.assertIn("agent time 30.0 s -> 30.0 s", a_line)
        self.assertIn("tokens - -> -", b_line)
        totals = next(l for l in lines if l.startswith("totals:"))
        self.assertIn("tokens - -> -", totals)
        self.assertIn("executions 2 -> 2", totals)
        self.assertIn("cost unpriced -> unpriced", totals)


class AChangedDefinition(TempCase):

    def test_3_a_changed_harness_executor_and_a_changed_brief_are_named(self):
        long_brief = "Do the thing carefully. " * 10
        two_step_run(self.tmp / "a")
        two_step_run(self.tmp / "b", a_steps=[
            agent("a", harness_executor="claude", brief=long_brief),
            agent("b")])
        _code, lines = call("compare", "--runs", self.tmp / "a", self.tmp / "b")
        rules = rule_lines(lines, "a")
        self.assertEqual(len(rules), 1, rules)
        self.assertTrue(rules[0].startswith("definition: "), rules[0])
        self.assertIn("agent.harness_executor pi -> claude", rules[0])
        self.assertIn(f"agent.brief {len('Do the thing.')} -> "
                      f"{len(long_brief)} chars", rules[0])
        self.assertNotIn("carefully", rules[0])


class AMovedStepAndStepsInOneRunOnly(TempCase):

    def test_4_a_moved_step_pairs_by_id_and_unpaired_steps_come_last(self):
        two_step_run(self.tmp / "a")
        run = self.tmp / "b"
        x, moved = "01.beta/01.x", "02.alpha/01.a"
        workflow_json(run, [("Beta", [agent("x")], 1),
                            ("Alpha", [agent("a")], 1)])
        (RunLog(run).phase(1, "01.beta", "Beta", [x], 1)
            .start(2, x).finish(5, x, 1, "passed")
            .phase(6, "02.alpha", "Alpha", [moved], 1)
            .start(6, moved)
            .finish(9, moved, 1, "passed",
                    gate={"coord": moved, "passed": True,
                          "checks": [CLEAN, PASSED_CHECK]})
            .add(9, "retry_decided", moved, 1,
                 retry_decision="no retry: status 'passed' is not a failure")
            .run_finished(10, "finished"))
        code, lines = call("compare", "--runs", self.tmp / "a", run)
        self.assertEqual(code, 0, lines)
        self.assertIn("1 paired, 1 differ, 1 only in A, 1 only in B", lines[0])
        steps = [l.split(":")[0] for l in lines if l.startswith("step ")]
        self.assertEqual(steps, ["step a", "step b", "step x"])
        self.assertEqual(rule_lines(lines, "a"),
                         [f"coord: {A} -> {moved}"])
        b_line = next(l for l in lines if l.startswith("step b:"))
        self.assertIn(f"only in A ({B})", b_line)
        x_line = next(l for l in lines if l.startswith("step x:"))
        self.assertIn(f"only in B ({x})", x_line)
        self.assertRegex(x_line, r"· B run-log\.jsonl:\d+$")


class NotARun(TempCase):

    def test_6_a_directory_that_is_not_a_run_exits_1_with_one_line(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        good = copy_tree(G1_RUN, self.tmp / "g1")
        code, lines = call("compare", "--runs", good, empty)
        self.assertEqual(code, 1)
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("no ohflow run at", lines[0])


class TheTextIsBounded(TempCase):

    def test_7_six_thousand_characters_and_three_hundred_per_line(self):
        many = [agent(f"s{i:02d}-" + "x" * 40) for i in range(60)]
        coords = [f"01.alpha/{i + 1:02d}.{s['id']}" for i, s in enumerate(many)]
        for name, status in (("a", "passed"), ("b", "quarantined")):
            run = self.tmp / name
            workflow_json(run, [("Alpha", many, 2)])
            log = RunLog(run).phase(1, "01.alpha", "Alpha", coords, 2)
            for c in coords:
                log.start(2, c).finish(5, c, 1, status,
                                       error="E" * 900 if status != "passed"
                                       else None)
            log.run_finished(9, "finished")
        _code, lines = call("compare", "--runs", self.tmp / "a", self.tmp / "b")
        self.assertLessEqual(len("\n".join(lines)), compare.TEXT_CAP)
        self.assertTrue(all(len(l) <= compare.LINE_CAP for l in lines),
                        max(lines, key=len))
        self.assertEqual(lines[-1], compare.CUT_LINE)

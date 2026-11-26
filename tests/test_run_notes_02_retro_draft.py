"""Run notes: the engine drafts its half of `retro.md` when a run ends.

Why. The retro asks seven questions, and most of what answers them is already in
`summary.json`: which steps passed first time, which retried and why, where the
time and tokens went, what ended badly. Typing that out is the dull part and the
part a person skips. `retro.md` therefore carries a block between two markers,
and the engine fills it each time a run ends. The person writes the verdicts,
outside the block.

What is asserted here.

* A finished run fills the block with totals, one row per step and pointers, and
  the placeholder line is gone.
* The per-step numbers are the numbers `ohflow table --by step` prints.
* A retry is pointed at, with the gate check that failed. A step that did not
  pass is pointed at. A clean run says nothing matched.
* Each pointer rule fires on its own input: an error that still passed its gate,
  an excluded step, an outlier, a run of tool errors. Unpriced cost is shown,
  not pointed at.
* A resume rewrites the block and leaves every byte outside it alone.
* The draft never stops a run: no `retro.md`, a half-deleted block, or an
  unreadable summary each come back as a message and the run finishes.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from ohflow import retrodraft, table
from ohflow.engine import Engine
from ohflow.workflow import RetryPolicy
from support import (FakeHarnessExecutor, TempCase, AgentScript, git_repo,
                     install_fake_harness_executor, simple_workflow, stub_preflight,
                     agent_step)


def prepare(case: TempCase, steps, script: AgentScript | None = None):
    repo = git_repo(case.tmp / "repo")
    stub_preflight(case)
    install_fake_harness_executor(case, FakeHarnessExecutor(default=script or AgentScript(
        final_text="DONE\n")))
    return simple_workflow(repo, steps=steps), case.run_dir()


def block(run_dir: Path) -> str:
    text = (run_dir / "retro.md").read_text(encoding="utf-8")
    a, b = text.index(retrodraft.BEGIN), text.index(retrodraft.END)
    return text[a + len(retrodraft.BEGIN):b]


def outside(run_dir: Path) -> str:
    text = (run_dir / "retro.md").read_text(encoding="utf-8")
    a, b = text.index(retrodraft.BEGIN), text.index(retrodraft.END)
    return text[:a] + text[b:]


def table_row(markdown: str, label: str) -> dict[str, str]:
    """The cells of the table row that names `label`, keyed by column header."""
    lines = markdown.splitlines()

    def cells(line: str) -> list[str]:
        return [c.strip() for c in line.strip().strip("|").split("|")]

    for i, line in enumerate(lines):
        if not line.startswith("|---"):
            continue
        head = cells(lines[i - 1])
        for row in lines[i + 1:]:
            if not row.startswith("|"):
                break
            if label in cells(row):
                return dict(zip(head, cells(row)))
    raise AssertionError(f"no table row names {label}")


def flaky() -> object:
    return dataclasses.replace(
        agent_step("flaky"),
        retry=RetryPolicy(max=1, on=("gate:final_message_matches",)))


class ADraftAfterAFinishedRun(TempCase):

    def _run(self):
        workflow, run_dir = prepare(self, [agent_step("alpha"), agent_step("beta")])
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors).run()
        return workflow, run_dir

    def test_the_block_holds_totals_a_row_per_step_and_pointers(self):
        _workflow, run_dir = self._run()
        body = block(run_dir)
        self.assertNotIn("Filled in when the run ends.", body)
        for heading in ("**Totals**", "**Per step**", "**Pointers."):
            self.assertIn(heading, body)
        for step_id in ("alpha", "beta"):
            self.assertIn(f"| 01.only-phase/0{1 if step_id == 'alpha' else 2}."
                          f"{step_id} |", body)
        text = (run_dir / "retro.md").read_text(encoding="utf-8")
        self.assertEqual(text.count(retrodraft.BEGIN), 1)
        self.assertEqual(text.count(retrodraft.END), 1)

    def test_a_clean_run_says_nothing_matched(self):
        _workflow, run_dir = self._run()
        self.assertIn("Nothing matched the pointer rules.", block(run_dir))
        self.assertIn("2 passed on the first attempt, 0 passed after a retry, "
                      "0 did not pass", block(run_dir))

    def test_the_per_step_numbers_are_the_numbers_ohflow_table_prints(self):
        summary = summary_of({"01.p/01.a": ("passed", [
            attempt(1, "failed", tool_calls=7, llm_calls=3, wall_seconds=90.0,
                    tokens={"prompt_tokens": 1100, "completion_tokens": 220,
                            "model": "m"}, cost=0.25),
            attempt(2, tool_calls=4, llm_calls=2, wall_seconds=30.0,
                    tokens={"prompt_tokens": 900, "completion_tokens": 180,
                            "model": "m"}, cost=0.5)])})
        path = self.tmp / "summary.json"
        path.write_text(json.dumps(summary), encoding="utf-8")
        expected = {"Attempts": "2", "Tool calls": "11", "LLM calls": "5",
                    "Prompt tokens": "2000", "Completion tokens": "400",
                    "Agent time": "2.0 min", "Cost": "0.7500"}
        drafted = table_row(retrodraft.render(summary), "01.p/01.a")
        self.assertEqual({name: drafted[name] for name in expected}, expected)
        rows, problems = table.load_rows([path], by="step")
        self.assertEqual(problems, [])
        printed = table_row(table.render_markdown(rows), "01.p/01.a")
        for name in sorted(expected.keys() - {"Attempts"}):
            self.assertEqual(drafted[name], printed[name], name)

    def test_writing_twice_gives_the_same_file(self):
        _workflow, run_dir = self._run()
        first = (run_dir / "retro.md").read_bytes()
        status, _msg = retrodraft.write(run_dir)
        self.assertEqual(status, retrodraft.WRITTEN)
        self.assertEqual((run_dir / "retro.md").read_bytes(), first)


class WhatGoesWrongIsPointedAt(TempCase):

    def test_a_retry_names_each_attempt_and_the_check_that_failed(self):
        workflow, run_dir = prepare(self, [flaky()], AgentScript(
            sequence=[{"final_text": "I gave up\n"}, {"final_text": "DONE\n"}]))
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors).run()
        body = block(run_dir)
        self.assertIn("`01.only-phase/01.flaky` ran 2 attempts", body)
        self.assertIn("Attempt 1 quarantined (structural)", body)
        self.assertIn("final_message_matches", body)
        self.assertIn("attempt 2 passed", body)
        self.assertIn("0 passed on the first attempt, 1 passed after a retry, "
                      "0 did not pass", body)

    def test_a_step_that_did_not_pass_is_named_with_its_status(self):
        workflow, run_dir = prepare(self, [agent_step("alpha")],
                                    AgentScript(final_text="nope\n"))
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors).run()
        body = block(run_dir)
        self.assertIn("`01.only-phase/01.alpha` has status **quarantined**", body)
        self.assertIn("No retry: the step declares no retry budget", body)
        self.assertIn("0 passed on the first attempt, 0 passed after a retry, "
                      "1 did not pass", body)


def attempt(n, status="passed", **over):
    base = {"attempt": n, "kind": "agent", "status": status, "tool_calls": 10,
            "llm_calls": 5, "observation_errors": 0, "wall_seconds": 60.0,
            "tokens": {"prompt_tokens": 100, "completion_tokens": 20,
                       "model": "m"},
            "cost": 0.0, "cost_source": "measured", "error": None,
            "gate_passed": status == "passed"}
    base.update(over)
    return base


def summary_of(steps: dict, **top) -> dict:
    """steps: coord -> (status, [attempt, ...])."""
    built = {}
    for coord, (status, attempts) in steps.items():
        built[coord] = {"kind": "agent", "status": status, "attempts": attempts}
    out = {"run_id": "r-x", "workflow": "p", "status": "finished",
           "started": "2026-09-30T10:00:00Z", "finished": "2026-09-30T10:10:00Z",
           "phases": {"01.p": {"steps": built}}, "diff_stat": {},
           "excluded": [], "quarantined": [], "deferred": []}
    out.update(top)
    return out


class EachPointerRuleFiresOnItsOwnInput(TempCase):

    def test_an_error_that_still_passed_its_gate(self):
        s = summary_of({"01.p/01.a": ("passed", [attempt(
            1, error="429 Too Many Requests")])})
        self.assertIn("recorded an error and still passed its gate",
                      retrodraft.render(s))

    def test_an_excluded_step(self):
        s = summary_of({"01.p/01.a": ("quarantined", [attempt(1, "failed")])},
                       excluded=[{"coord": "01.p/01.a", "failures": 2,
                                  "reason": "unchanged work failed twice"}])
        body = retrodraft.render(s)
        self.assertIn("`01.p/01.a` was excluded after 2 failures", body)
        self.assertIn("`01.p/01.a` has status **quarantined**", body)

    def test_an_outlier_needs_three_agent_steps_and_a_floor(self):
        big = summary_of({
            "01.p/01.a": ("passed", [attempt(1, tool_calls=10)]),
            "01.p/02.b": ("passed", [attempt(1, tool_calls=12)]),
            "01.p/03.c": ("passed", [attempt(1, tool_calls=80)])})
        self.assertIn("`01.p/03.c` used 80 of tool calls; the median agent step "
                      "used 12", retrodraft.render(big))
        small = summary_of({
            "01.p/01.a": ("passed", [attempt(1, tool_calls=1)]),
            "01.p/02.b": ("passed", [attempt(1, tool_calls=2)]),
            "01.p/03.c": ("passed", [attempt(1, tool_calls=9)])})
        self.assertNotIn("of tool calls", retrodraft.render(small))
        two = summary_of({
            "01.p/01.a": ("passed", [attempt(1, tool_calls=10)]),
            "01.p/02.b": ("passed", [attempt(1, tool_calls=90)])})
        self.assertNotIn("of tool calls", retrodraft.render(two))

    def test_a_dash_in_the_totals_is_explained(self):
        """An agent execution that wrote no numbers makes its total unknown, as
        in `ohflow table`. The totals say so instead of leaving a bare dash."""
        s = summary_of({"01.p/01.a": ("timeout", [attempt(
            1, "timeout", tool_calls=None, llm_calls=None, wall_seconds=None,
            tokens=None)])})
        self.assertIn("A dash means an agent execution wrote no numbers",
                      retrodraft.render(s))
        clean = summary_of({"01.p/01.a": ("passed", [attempt(1)])})
        self.assertNotIn("A dash means", retrodraft.render(clean))

    def test_a_run_of_tool_errors(self):
        s = summary_of({"01.p/01.a": ("passed", [attempt(
            1, observation_errors=4, tool_calls=30)])})
        self.assertIn("hit 4 tool errors in 30 tool calls", retrodraft.render(s))

    def test_unpriced_cost_is_shown_not_pointed_at(self):
        """A host harness executor run is always unpriced, so a pointer would fire every
        time. The cost cell says `unpriced` and that is all it needs."""
        s = summary_of({"01.p/01.a": ("passed", [attempt(
            1, cost_source="unpriced", cost=None)])})
        self.assertIn("Nothing matched the pointer rules.",
                      retrodraft.render(s))

    def test_a_retry_reads_the_failed_check_from_the_attempts_gate_json(self):
        a1 = self.tmp / "attempts" / "01"
        a1.mkdir(parents=True)
        (a1 / "gate.json").write_text(json.dumps({"checks": [
            {"name": "tests_pass", "expected": "0", "observed": "1",
             "passed": False},
            {"name": "tree_clean", "expected": True, "observed": True,
             "passed": True}]}), encoding="utf-8")
        s = summary_of({"01.p/01.a": ("passed", [
            attempt(1, "failed", dir=str(a1), failure_class="gate"),
            attempt(2)])})
        body = retrodraft.render(s)
        self.assertIn("failed checks: tests_pass (expected 0, observed 1)", body)
        self.assertNotIn("tree_clean", body)


class AResumeKeepsWhatThePersonWrote(TempCase):

    def test_only_the_block_is_rewritten(self):
        workflow, run_dir = prepare(self, [agent_step("alpha"), agent_step("beta")])
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors).run()
        retro = run_dir / "retro.md"
        text = retro.read_text(encoding="utf-8")
        retro.write_text(text.replace("- Best step:", "- Best step: alpha")
                         + "\nMY LAST WORD\n", encoding="utf-8")
        before = outside(run_dir)

        Engine(workflow, run_dir, run_id=run_dir.name, resume=True,
               verbose=False,
               harness_executors=self.harness_executors).run()

        self.assertEqual(outside(run_dir), before,
                         "a resume touched text outside the block")
        self.assertIn("- Best step: alpha", outside(run_dir))
        self.assertNotIn("Filled in when the run ends.", block(run_dir))


class ADraftNeverStopsARun(TempCase):

    def _finished(self):
        workflow, run_dir = prepare(self, [agent_step("alpha")])
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors).run()
        return workflow, run_dir

    def test_a_deleted_retro_is_not_recreated_and_the_resume_finishes(self):
        workflow, run_dir = self._finished()
        (run_dir / "retro.md").unlink()
        summary = Engine(workflow, run_dir, run_id=run_dir.name, resume=True,
                         verbose=False,
                         harness_executors=self.harness_executors).run()
        self.assertEqual(summary.get("status"), "finished")
        self.assertFalse((run_dir / "retro.md").exists())
        self.assertEqual(retrodraft.write(run_dir)[0], retrodraft.ABSENT)

    def test_a_half_deleted_block_is_left_alone(self):
        workflow, run_dir = self._finished()
        retro = run_dir / "retro.md"
        retro.write_text(retro.read_text(encoding="utf-8").replace(
            retrodraft.END, ""), encoding="utf-8")
        before = retro.read_bytes()
        summary = Engine(workflow, run_dir, run_id=run_dir.name, resume=True,
                         verbose=False,
                         harness_executors=self.harness_executors).run()
        self.assertEqual(summary.get("status"), "finished")
        self.assertEqual(retro.read_bytes(), before)
        self.assertEqual(retrodraft.write(run_dir)[0], retrodraft.PROBLEM)

    def test_an_unreadable_summary_is_a_message_not_an_error(self):
        _workflow, run_dir = self._finished()
        retro = run_dir / "retro.md"
        before = retro.read_bytes()
        (run_dir / "summary.json").write_text("{ not json", encoding="utf-8")
        status, message = retrodraft.write(run_dir)
        self.assertEqual(status, retrodraft.PROBLEM)
        self.assertTrue(message)
        self.assertEqual(retro.read_bytes(), before)

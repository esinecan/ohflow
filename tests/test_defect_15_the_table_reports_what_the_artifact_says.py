"""Defect 15: the run-summary table was kept by hand and had drifted.

What went wrong. `references/implement-review.md` carries a four-row table of
measured runs, typed in by a person. Two of its rows disagree with the artifacts
they describe, and one column has no artifact behind it at all:

  * the `run-1 implement` row claims 44 tool calls, 35 LLM calls, 30k completion
    tokens and 24 minutes. `run-1.summary.json` records that phase as
    `{"resumed": "phase 1 taken from the existing worktree"}`, so that run was
    fired with `--mode review` and those numbers were never written anywhere.
  * the `run-1 review` row says the verdict was BLOCKED.
    `run-1.summary.json` records `E2a_verdict: null` with `passed: false`, which
    means the driver found no verdict line at all.
  * the "LLM calls" column: no legacy summary carries `llm_calls`. Those
    numbers came from reading transcripts by hand.

What is asserted here. The generator reports what the artifact says. The three
rows the preserved files do support are asserted number by number, the missing
ones render `-`, and the rows that disagree with the hand-kept table render what
the file holds.

And the three honesty rules: a missing measurement is never a zero, an unpriced
cost is never `0.00`, and a row sums every execution rather than the last one.
"""

from __future__ import annotations

import json
from pathlib import Path

from ohflow import table
from ohflow.cli import main as cli_main
from support import TempCase, quiet

#: The two preserved artifacts of the first implement-review run.
EXAMPLES = Path(__file__).resolve().parent / "fixtures" / "implement-review"


def _rows(*paths, by="phase"):
    rows, problems = table.load_rows(list(paths), by=by)
    return rows, problems


def _find(rows, run, label):
    for r in rows:
        if r["run"] == run and r["label"] == label:
            return r
    raise AssertionError(f"no row {run}/{label} in {[ (r['run'], r['label']) for r in rows ]}")


class ThePreservedArtifactsRenderExactly(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.rows, self.problems = _rows(EXAMPLES)

    def test_no_file_was_unreadable(self):
        self.assertEqual(self.problems, [])

    def test_four_rows_two_runs_two_phases_each(self):
        self.assertEqual([(r["run"], r["label"]) for r in self.rows],
                         [("run-1", "implement"), ("run-1", "review"),
                          ("run-2", "implement"), ("run-2", "review")])

    def test_run_2_implement_matches_its_artifact(self):
        r = _find(self.rows, "run-2", "implement")
        self.assertEqual(r["tool_calls"], 31)
        self.assertEqual(r["prompt_tokens"], 443926)
        self.assertEqual(r["completion_tokens"], 6316)
        self.assertEqual(table._cell(r["agent_time"], "agent_time"), "3.9 min")
        self.assertEqual(r["outcome"], "passed")

    def test_run_2_review_matches_its_artifact(self):
        r = _find(self.rows, "run-2", "review")
        self.assertEqual(r["tool_calls"], 26)
        self.assertEqual(r["completion_tokens"], 13327)
        self.assertEqual(table._cell(r["agent_time"], "agent_time"), "10.9 min")
        self.assertIn("MERGEABLE", r["outcome"])

    def test_run_1_implement_has_no_numbers_because_it_never_ran(self):
        """The hand-kept table gives this row 44 tool calls and 24 minutes. The
        artifact records a resumed phase and no metrics at all."""
        r = _find(self.rows, "run-1", "implement")
        self.assertEqual(r["outcome"], "resumed")
        for key in ("tool_calls", "prompt_tokens", "completion_tokens",
                    "agent_time"):
            self.assertIsNone(r[key], f"{key} was invented for a phase that "
                                      f"never ran")

    def test_run_1_review_reports_the_verdict_the_artifact_holds(self):
        """The hand-kept table says BLOCKED. The artifact says the driver found
        no verdict line: `E2a_verdict: null`, `passed: false`."""
        r = _find(self.rows, "run-1", "review")
        self.assertEqual(r["outcome"], "failed")
        self.assertEqual(r["tool_calls"], 15)
        self.assertEqual(r["completion_tokens"], 20371)

    def test_the_llm_calls_column_is_empty_for_every_legacy_row(self):
        for r in self.rows:
            self.assertIsNone(r["llm_calls"],
                              "no legacy summary carries llm_calls")


class TheThreeHonestyRules(TempCase):

    def test_a_missing_measurement_is_not_a_zero(self):
        self.assertIsNone(table._add(0, None))
        self.assertIsNone(table._add(None, 3))
        rows, _p = _rows(EXAMPLES)
        rendered = table.render_markdown(rows)
        self.assertIn("| - |", rendered)
        llm_index = next(i for i, (_label, key) in enumerate(table.COLUMNS)
                         if key == "llm_calls")
        for line in rendered.splitlines()[2:]:
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            self.assertEqual(cells[llm_index], "-",
                             "a missing LLM-call measurement printed as zero")

    def test_an_unpriced_cost_is_never_a_number(self):
        self.assertEqual(
            table._cost([{"cost": 0.0, "cost_source": "unpriced"}]),
            table.UNPRICED)
        self.assertEqual(
            table._cost([{"cost": 1.0, "cost_source": "litellm"},
                         {"cost": 0.0, "cost_source": "unpriced"}]),
            table.UNPRICED,
            "one unpriced execution makes the row's total unpriced")
        self.assertEqual(table._cost([{"cost": None, "cost_source": None}]),
                         table.MISSING)
        self.assertEqual(
            table._cost([{"cost": 1.5, "cost_source": "litellm"}]), "1.5000")

    def test_a_subscription_cost_is_a_known_zero(self):
        self.assertEqual(
            table._cost([{"cost": 0.0, "cost_source": table.SUBSCRIPTION}]), "0.0000")
        self.assertEqual(
            table._cost([{"cost": 1.5, "cost_source": "pi-catalog"},
                         {"cost": 0.0, "cost_source": table.SUBSCRIPTION}]), "1.5000")
        self.assertEqual(
            table._cost([{"cost": 0.0, "cost_source": table.SUBSCRIPTION},
                         {"cost": 0.0, "cost_source": "unpriced"}]),
            table.UNPRICED)

    def test_a_row_sums_every_execution_including_the_failed_ones(self):
        entries = [
            {"tool_calls": 10, "wall_seconds": 60.0, "llm_calls": 3,
             "tokens": {"prompt_tokens": 100, "completion_tokens": 10},
             "cost": 0.0, "cost_source": "unpriced"},
            {"tool_calls": 5, "wall_seconds": 30.0, "llm_calls": 2,
             "tokens": {"prompt_tokens": 50, "completion_tokens": 5},
             "cost": 0.0, "cost_source": "unpriced"},
        ]
        folded = table._fold(entries)
        self.assertEqual(folded["executions"], 2)
        self.assertEqual(folded["tool_calls"], 15,
                         "summing the last attempt alone loses what the "
                         "failed one cost")
        self.assertEqual(folded["agent_time"], 90.0)
        self.assertEqual(folded["completion_tokens"], 15)


class TheTwoClocksAreNamedApart(TempCase):

    def test_agent_time_and_elapsed_are_different_columns(self):
        names = [name for name, _k in table.COLUMNS]
        self.assertIn("Agent time", names)
        self.assertIn("Elapsed", names)
        self.assertNotIn("Wall", names,
                         "calling either one 'wall' invites the reader to add "
                         "them up")

    def test_elapsed_comes_from_the_run_and_not_from_a_sum(self):
        self.assertEqual(
            table._elapsed({"started": "2026-09-18T10:00:00Z",
                            "finished": "2026-09-18T10:30:00Z"}), "30.0 min")
        self.assertEqual(table._elapsed({"started": None, "finished": None}),
                         table.MISSING)


class TheInputsAreFoundAndDeduplicated(TempCase):

    def test_a_directory_finds_the_dotted_names(self):
        """`--runs <dir>` searching only for `summary.json` would find neither
        preserved artifact, because both are named `run-N.summary.json`."""
        found = table.discover([EXAMPLES])
        self.assertEqual(sorted(p.name for p in found),
                         ["run-1.summary.json", "run-2.summary.json"])

    def test_a_file_path_is_accepted_directly(self):
        found = table.discover([EXAMPLES / "run-2.summary.json"])
        self.assertEqual([p.name for p in found], ["run-2.summary.json"])

    def test_overlapping_roots_are_deduplicated(self):
        found = table.discover([EXAMPLES, EXAMPLES,
                                EXAMPLES / "run-2.summary.json"])
        self.assertEqual(len(found), 2)

    def test_a_shim_run_is_counted_once(self):
        """A shim run writes both shapes. The legacy projection names the
        ohflow run it came from, and the native summary carries every attempt,
        so the native one wins."""
        native = self.tmp / "ohflow" / "r-1"
        native.mkdir(parents=True)
        (native / "summary.json").write_text(json.dumps({
            "run_id": "r-1", "workflow": "implement-review", "status": "finished",
            "started": "2026-09-18T10:00:00Z", "finished": "2026-09-18T10:20:00Z",
            "phases": {"01.implement": {"steps": {"01.implement/01.impl": {
                "status": "passed",
                "attempts": [{"attempt": 1, "tool_calls": 7, "llm_calls": 4,
                              "wall_seconds": 120.0, "cost": 0.0,
                              "cost_source": "unpriced",
                              "tokens": {"prompt_tokens": 9,
                                         "completion_tokens": 3}}]}}}},
        }), encoding="utf-8")
        legacy = self.tmp / "summary.json"
        legacy.write_text(json.dumps({
            "repo": "r", "branch": "feat/x", "worktree": "w",
            "ohflow_run": {"run_id": "r-1", "dir": str(native)},
            "phases": {"implement": {"tool_calls": 7, "wall_seconds": 120.0,
                                     "gate": {"passed": True}}},
        }), encoding="utf-8")

        rows, problems = _rows(self.tmp, by="run")
        self.assertEqual(problems, [])
        self.assertEqual(len(rows), 1, "the shim run was counted twice")
        self.assertEqual(rows[0]["run"], "r-1")
        self.assertEqual(rows[0]["llm_calls"], 4,
                         "the native summary wins, and it has the calls")


class OlderSummariesStillRender(TempCase):
    """A native summary written before attempt records existed carries
    `result` and no `attempts` key. Reading only `attempts` rendered those runs
    as zero usage."""

    def _old_native(self, **step_extra) -> Path:
        d = self.tmp / "old"
        d.mkdir(parents=True, exist_ok=True)
        step = {"step_id": "impl", "kind": "agent", "status": "passed",
                "attempt": 1,
                "result": {"tool_calls": 44, "llm_calls": 35,
                           "wall_seconds": 1440.0, "cost": 0.0,
                           "cost_source": "unpriced",
                           "tokens": {"prompt_tokens": 900,
                                      "completion_tokens": 30000}}}
        step.update(step_extra)
        (d / "summary.json").write_text(json.dumps({
            "run_id": "r-old", "workflow": "old-workflow", "status": "finished",
            "started": "2026-09-15T09:00:00Z",
            "finished": "2026-09-15T09:30:00Z",
            "phases": {"01.build": {"steps": {"01.build/01.impl": step}}},
        }), encoding="utf-8")
        return d / "summary.json"

    def test_a_summary_without_attempts_reads_its_result(self):
        rows, problems = _rows(self._old_native(), by="run")
        self.assertEqual(problems, [])
        self.assertEqual(rows[0]["tool_calls"], 44)
        self.assertEqual(rows[0]["llm_calls"], 35)
        self.assertEqual(rows[0]["completion_tokens"], 30000)
        self.assertEqual(rows[0]["cost"], table.UNPRICED)
        self.assertEqual(table._cell(rows[0]["elapsed"], "elapsed"), "30.0 min")

    def test_an_empty_attempts_list_means_nothing_ran(self):
        """An explicit empty list is a statement, not a missing key."""
        rows, _p = _rows(self._old_native(attempts=[], result=None), by="run")
        self.assertEqual(rows[0]["executions"], 0)
        self.assertEqual(rows[0]["tool_calls"], 0)


class NonAgentStepsAreCountedButNotSummed(TempCase):
    """A command, a merge and a bare gate produce no agent metrics. Reading
    their empty numbers as a missing measurement made a whole phase's usage
    unknown although every agent in it was measured, which is the shape of the
    shim's review-only mode: one gate step and one agent."""

    def _mixed(self, *, agent_crashed=False) -> Path:
        d = self.tmp / "mixed"
        d.mkdir(parents=True, exist_ok=True)
        agent_attempt = {"attempt": 1, "kind": "agent", "status": "passed",
                         "tool_calls": 12, "llm_calls": 6, "wall_seconds": 300.0,
                         "cost": 0.0, "cost_source": "unpriced",
                         "tokens": {"prompt_tokens": 500,
                                    "completion_tokens": 40}}
        if agent_crashed:
            agent_attempt = {"attempt": 1, "kind": "agent", "status": "failed",
                             "tool_calls": None, "llm_calls": None,
                             "wall_seconds": None, "cost": None,
                             "cost_source": None, "tokens": None}
        (d / "summary.json").write_text(json.dumps({
            "run_id": "r-mixed", "workflow": "implement-review",
            "status": "finished", "started": "2026-09-18T10:00:00Z",
            "finished": "2026-09-18T10:10:00Z",
            "phases": {"01.implement": {"steps": {
                "01.implement/01.gate": {
                    "step_id": "gate", "kind": "gate", "status": "passed",
                    "attempts": [{"attempt": 1, "kind": "gate",
                                  "status": "passed", "tool_calls": None,
                                  "llm_calls": None, "wall_seconds": None,
                                  "tokens": None, "cost": None,
                                  "cost_source": None}]},
                "01.implement/02.review": {
                    "step_id": "review", "kind": "agent", "status": "passed",
                    "attempts": [agent_attempt]}}}},
        }), encoding="utf-8")
        return d / "summary.json"

    def test_a_gate_step_does_not_make_the_phase_unknown(self):
        rows, _p = _rows(self._mixed(), by="phase")
        r = rows[0]
        self.assertEqual(r["executions"], 2, "both executions are counted")
        self.assertEqual(r["agent_executions"], 1)
        self.assertEqual(r["tool_calls"], 12,
                         "the gate step made the agent's tool calls unknown")
        self.assertEqual(r["llm_calls"], 6)
        self.assertEqual(r["completion_tokens"], 40)
        self.assertEqual(r["cost"], table.UNPRICED)

    def test_a_crashed_agent_still_makes_the_row_unknown(self):
        """An agent that produced no numbers is a missing measurement, and it
        must not be confused with a step that never produces any."""
        rows, _p = _rows(self._mixed(agent_crashed=True), by="phase")
        r = rows[0]
        self.assertEqual(r["agent_executions"], 1)
        self.assertIsNone(r["tool_calls"])
        self.assertIsNone(r["completion_tokens"])
        self.assertEqual(r["cost"], table.MISSING)

    def test_the_run_row_agrees_with_the_phase_row(self):
        by_phase, _p = _rows(self._mixed(), by="phase")
        by_run, _p2 = _rows(self._mixed(), by="run")
        self.assertEqual(by_run[0]["tool_calls"], by_phase[0]["tool_calls"])
        self.assertEqual(by_run[0]["agent_executions"],
                         by_phase[0]["agent_executions"])


class AnOlderRunDirectoryStillYieldsItsMetrics(TempCase):
    """`Run.attempts` reads `attempts/NN/result.json`. A run directory
    written before attempt directories existed keeps `result.json` at the step
    root, and its successful execution would have come back empty."""

    def _run_dir(self, *, old_layout: bool) -> Path:
        from ohflow.run_log import RunLog
        run_dir = self.tmp / "runs" / "r-old"
        step_dir = run_dir / "phases" / "01.only-phase" / "01.s1"
        target = step_dir if old_layout else step_dir / "attempts" / "01"
        target.mkdir(parents=True, exist_ok=True)
        (target / "result.json").write_text(json.dumps({
            "tool_calls": 9, "llm_calls": 5, "wall_seconds": 61.0,
            "cost": 0.0, "cost_source": "unpriced",
            "tokens": {"prompt_tokens": 70, "completion_tokens": 8}}),
            encoding="utf-8")
        j = RunLog(run_dir)
        j.append("run_started", payload={"run_id": "r-old", "workflow": "p",
                                         "meta": {}})
        j.append("attempt_started", coord="01.only-phase/01.s1", attempt=1,
                 payload={"step_id": "s1", "kind": "agent",
                          "fingerprint": "f" * 64, "start_kind": "initial"})
        j.append("attempt_finished", coord="01.only-phase/01.s1", attempt=1,
                 payload={"step_id": "s1", "kind": "agent",
                          "fingerprint": "f" * 64, "status": "passed"})
        return run_dir

    def _records(self, *, old_layout: bool):
        from ohflow import rundir
        run_dir = self._run_dir(old_layout=old_layout)
        return rundir.open_run(run_dir).attempts("01.only-phase/01.s1")

    def test_the_old_layout_is_read_from_the_step_root(self):
        records = self._records(old_layout=True)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["tool_calls"], 9)
        self.assertEqual(records[0]["llm_calls"], 5)

    def test_a_crashed_new_attempt_does_not_inherit_an_older_result(self):
        """The fallback is narrow on purpose. A step that has an `attempts`
        directory reads only from it, so attempt 2 crashing before it wrote a
        result cannot pick up the root copy attempt 1 left there."""
        from ohflow import rundir
        from ohflow.run_log import RunLog
        run_dir = self._run_dir(old_layout=False)
        step_dir = run_dir / "phases" / "01.only-phase" / "01.s1"
        # The projection attempt 1 left at the root.
        (step_dir / "result.json").write_text(
            json.dumps({"tool_calls": 9, "llm_calls": 5}), encoding="utf-8")
        j = RunLog(run_dir)
        j.append("attempt_started", coord="01.only-phase/01.s1", attempt=2,
                 payload={"step_id": "s1", "kind": "agent",
                          "fingerprint": "f" * 64, "start_kind": "retry"})
        j.append("attempt_finished", coord="01.only-phase/01.s1", attempt=2,
                 payload={"step_id": "s1", "kind": "agent",
                          "fingerprint": "f" * 64, "status": "failed"})
        records = rundir.open_run(run_dir).attempts("01.only-phase/01.s1")
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["tool_calls"], 9)
        self.assertIsNone(records[1]["tool_calls"],
                          "attempt 2 inherited attempt 1's numbers")


class MalformedInputIsNamedAndSkipped(TempCase):

    def test_an_unparseable_file_names_itself_and_the_others_still_render(self):
        broken = self.tmp / "broken.summary.json"
        broken.write_text('{"event":', encoding="utf-8")
        rows, problems = _rows(EXAMPLES, broken)
        self.assertEqual(len(rows), 4, "one bad file must not lose the rest")
        self.assertEqual(len(problems), 1)
        self.assertIn("broken.summary.json", problems[0])

    def test_a_file_of_the_wrong_shape_is_named(self):
        odd = self.tmp / "odd.summary.json"
        odd.write_text('{"hello": "world"}', encoding="utf-8")
        _rows_, problems = _rows(odd)
        self.assertEqual(len(problems), 1)
        self.assertIn("not an ohflow or a legacy summary", problems[0])

    def test_the_cli_reports_a_bad_file_with_a_non_zero_exit(self):
        broken = self.tmp / "broken.summary.json"
        broken.write_text("{", encoding="utf-8")
        with quiet() as out:
            code = cli_main(["table", "--runs", str(broken)])
        self.assertEqual(code, 1)
        self.assertIn("broken.summary.json", out.out)


class TheOutputIsDeterministic(TempCase):

    def test_two_runs_of_the_generator_agree_byte_for_byte(self):
        first, _p = _rows(EXAMPLES)
        second, _p2 = _rows(EXAMPLES)
        self.assertEqual(table.render_markdown(first),
                         table.render_markdown(second))
        self.assertEqual(table.render_json(first), table.render_json(second))

    def test_the_cli_writes_the_file_it_says_it_wrote(self):
        out = self.tmp / "table.md"
        with quiet():
            code = cli_main(["table", "--runs", str(EXAMPLES),
                             "--out", str(out)])
        self.assertEqual(code, 0)
        self.assertIn("| Agent time |", out.read_text(encoding="utf-8"))

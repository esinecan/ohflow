"""m1: `rundir` is the one reader of a run directory.

It opens four kinds of run: the g1 fixture (a finished run with a deferred
first attempt), a finished run built with the fake harness executor, a dry run, and a run
that was hard-killed (a run log with no `run_finished`, no `summary.json` and a
dead supervisor PID). For each it checks status, workflow order, attempts, usage
and the computed summary, which must satisfy `summary.schema.json`.

The three defect tests are named in `DefectTokenTotal`, `DefectTableNeedsNoSummary`
and `DefectDryRunStatus`. Each one failed against the code before `rundir`.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from dashboard_support import G1_RUN, RunLog, copy_tree, workflow_json, agent
from ohflow import cli, gates, rundir, table
from ohflow.engine import Engine
from support import (FakeHarnessExecutor, TempCase, AgentScript, git_repo,
                     install_fake_harness_executor, quiet, simple_workflow, stub_preflight,
                     agent_step)

SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "references"
                     / "summary.schema.json").read_text(encoding="utf-8"))

DEAD_PID = "2147483646"


def _schema_errors(summary: dict) -> list[str]:
    return gates._validate_schema(json.loads(json.dumps(summary, default=str)),
                                  SCHEMA)


class G1Run(TempCase):
    """The g1 fixture: two steps, the first one deferred once then passed."""

    def setUp(self) -> None:
        super().setUp()
        self.dir = copy_tree(G1_RUN, self.tmp / "runs" / "g1")
        self.run = rundir.open_run(self.dir)

    def test_rundir_status_is_the_run_logs(self):
        self.assertEqual(self.run.status, "finished")
        self.assertEqual(self.run.id, "r-20260929-021128-7974ff3a")

    def test_rundir_steps_come_in_workflow_order(self):
        self.assertEqual([v.coord for v in self.run.steps()],
                         ["01.sweep/01.flaky", "01.sweep/02.control"])
        self.assertEqual([v.status for v in self.run.steps()],
                         ["passed", "passed"])

    def test_rundir_attempts_list_every_execution(self):
        attempts = self.run.attempts("01.sweep/01.flaky")
        self.assertEqual([(a["attempt"], a["status"]) for a in attempts],
                         [(1, "deferred"), (2, "passed")])
        self.assertEqual(self.run.latest_attempt("01.sweep/01.flaky")["attempt"], 2)

    def test_rundir_usage_includes_the_cache_once(self):
        usage = self.run.usage(self.run.latest_attempt("01.sweep/01.flaky"))
        self.assertEqual(usage["prompt_tokens"], 12806)
        self.assertEqual(usage["cache_read_tokens"], 7744)
        self.assertEqual(usage["total_tokens"], 12806 + 1350)
        self.assertIsNone(self.run.usage(
            self.run.attempts("01.sweep/01.flaky")[0]))

    def test_rundir_summary_satisfies_the_schema(self):
        summary = self.run.summary(git=False)
        self.assertEqual(_schema_errors(summary), [])
        self.assertEqual(summary["status"], "finished")
        self.assertEqual(summary["phases"]["01.sweep"]["steps"][
            "01.sweep/01.flaky"]["executions"], 2)


class AFinishedFakeHarnessExecutorRun(TempCase):

    def test_rundir_reads_what_the_engine_wrote(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript(final_text="DONE\n")))
        run_dir = self.run_dir("r-fake")
        Engine(simple_workflow(repo, name="fake", steps=[agent_step("only")]),
               run_dir, run_id="r-fake", verbose=False,
               harness_executors=self.harness_executors).run()

        run = rundir.open_run(run_dir)
        self.assertEqual(run.status, "finished")
        self.assertEqual([v.step_id for v in run.steps()], ["only"])
        on_disk = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(_schema_errors(on_disk), [])
        computed = run.summary(git=False)
        self.assertEqual(computed["phases"], on_disk["phases"])

    def test_rundir_leaves_no_board_json_behind(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript(final_text="DONE\n")))
        run_dir = self.run_dir("r-no-board")
        Engine(simple_workflow(repo, steps=[agent_step("only")]), run_dir,
               run_id="r-no-board", verbose=False,
               harness_executors=self.harness_executors).run()
        self.assertFalse((run_dir / "board.json").exists())
        self.assertFalse((run_dir / "heartbeat.json").exists())
        self.assertTrue((run_dir / "board.md").exists())


class ADryRun(TempCase):

    def test_rundir_a_dry_run_lists_each_step_as_dry_run(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        run_dir = self.run_dir("r-dry")
        Engine(simple_workflow(repo, name="dry", steps=[agent_step("a"), agent_step("b")]),
               run_dir, run_id="r-dry", dry_run=True, verbose=False,
               harness_executors=self.harness_executors).run()
        run = rundir.open_run(run_dir)
        self.assertEqual([(v.step_id, v.status) for v in run.steps()],
                         [("a", "dry-run"), ("b", "dry-run")])
        self.assertEqual(_schema_errors(run.summary(git=False)), [])


class AHardKilledRun(TempCase):
    """A run log that never reached `run_finished`, and a supervisor that died."""

    def setUp(self) -> None:
        super().setUp()
        self.dir = self.run_dir("r-killed")
        workflow_json(self.dir, [("Map", [agent("a"), agent("b")], 2)])
        (RunLog(self.dir).phase(1, "01.map", "Map",
                                ["01.map/01.a", "01.map/02.b"])
         .start(2, "01.map/01.a")
         .start(3, "01.map/02.b")
         .finish(40, "01.map/02.b", 1, "passed"))
        (self.dir / "supervisor.pid").write_text(DEAD_PID, encoding="utf-8")

    def test_rundir_a_dead_supervisor_makes_the_run_orphaned(self):
        run = rundir.open_run(self.dir)
        self.assertFalse(run.supervisor_alive)
        self.assertEqual(run.status, "orphaned")
        self.assertEqual([(v.step_id, v.status) for v in run.steps()],
                         [("a", "running"), ("b", "passed")])

    def test_rundir_a_live_supervisor_keeps_the_run_running(self):
        (self.dir / "supervisor.pid").write_text(
            str(__import__("os").getpid()), encoding="utf-8")
        self.assertEqual(rundir.open_run(self.dir).status, "running")

    def test_rundir_the_computed_summary_is_valid_and_written_by_report(self):
        summary = rundir.open_run(self.dir).summary(git=False)
        self.assertEqual(summary["status"], "orphaned")
        self.assertEqual(_schema_errors(summary), [])
        self.assertFalse((self.dir / "summary.json").exists())
        with quiet():
            code = cli.main(["report", "--run", str(self.dir)])
        self.assertEqual(code, cli.EXIT_OK)
        written = json.loads((self.dir / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(written["status"], "orphaned")
        self.assertTrue((self.dir / "exit.json").exists())

class TheInterfaceIsNarrow(TempCase):
    """The public names are the reader of a run, its status words, the layout
    (the hold gate's two files included), the hold readers `ohflow go` needs,
    and one walk of a saved summary. Token sums, step-id parsing and the test
    audit are not."""

    def test_rundir_exports_only_the_reader_the_layout_and_one_summary_walk(self):
        self.assertEqual(
            sorted(rundir.__all__),
            sorted(["TOKEN_KEYS", "ORPHANED", "STARTING", "HELD", "NOT_STARTED",
                    "STOPPED_STATUSES", "HOLD_FILE", "GO_FILE", "step_dir",
                    "attempt_dir", "attempt_in", "hold_record", "hold_alive",
                    "open_run", "Run", "StepView", "SummaryStep",
                    "walk_summary", "step_status"]))


class DefectTokenTotal(TempCase):
    """Defect: the exit report added the cache to `prompt_tokens`, which
    already includes it. g1 said 21.9 k tokens; the run used 14.2 k."""

    def test_rundir_defect_token_total_counts_the_cache_once(self):
        run = copy_tree(G1_RUN, self.tmp / "runs" / "g1")
        with quiet():
            code = cli.main(["report", "--run", str(run)])
        self.assertEqual(code, cli.EXIT_OK)
        record = json.loads((run / "exit.json").read_text(encoding="utf-8"))
        self.assertIn("14.2 k tokens", record["verdict"])
        self.assertNotIn("21.9 k", record["verdict"])


class DefectTableNeedsNoSummary(TempCase):
    """Defect: `ohflow table` found runs by `summary.json` only, so a run that
    was killed, or is still going, printed no row."""

    def test_rundir_defect_table_reads_a_run_with_no_summary(self):
        root = self.tmp / "runs"
        copy_tree(G1_RUN, root / "g1")
        self.assertFalse((root / "g1" / "summary.json").exists())
        rows, problems = table.load_rows([root], by="step")
        self.assertEqual(problems, [])
        self.assertEqual([r["label"] for r in rows], ["01.sweep/01.flaky", "01.sweep/02.control"])
        flaky = rows[0]
        self.assertEqual(flaky["agent_executions"], 2)


class DefectDryRunStatus(TempCase):
    """Defect: a dry run showed every step `pending`, because the run log
    carries no step record for a step that never started."""

    def test_rundir_defect_dry_run_status_is_not_pending(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        run_dir = self.run_dir("r-dry-status")
        Engine(simple_workflow(repo, steps=[agent_step("only")]), run_dir,
               run_id="r-dry-status", dry_run=True, verbose=False,
               harness_executors=self.harness_executors).run()
        statuses = [v.status for v in rundir.open_run(run_dir).steps()]
        self.assertEqual(statuses, ["dry-run"])
        with quiet() as output:
            cli.main(["status", "--run", str(run_dir)])
        first = output.out.splitlines()[0]
        self.assertIn("0 pending", first)
        self.assertIn("1 dry-run", first)
        shutil.rmtree(run_dir, ignore_errors=True)

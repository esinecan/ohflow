"""m4: `ohflow watch` reports what is new, and what the run is.

Before: an agent polled `status`, read the whole dict again each time and
compared it with its memory of the last one. Now a watcher keeps a cursor in
the run directory, so a repeated call prints only the change since its last
call. A run that ended returns at once with the exit verdict. A run whose
supervisor died gets its exit report written by the watcher.

Exit codes: 0 every step passed, 1 ended otherwise, 2 unknown run, 10 the run
is still going.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from unittest import mock

from dashboard_support import (G1_RUN, RunLog, copy_tree, mark_alive,
                               workflow_json, agent)
from ohflow import exit_report as ohexit
from ohflow import watch
from support import TempCase
from verb_support import call

STEPS = ["01.map/01.a", "01.map/02.b"]
DEAD_PID = "2147483646"


def step_lines(lines: list[str]) -> list[str]:
    """The step change lines: the digest and attention lines are left out.

    A watch also prints a digest line per new run-log verdict and a line per
    new or cleared attention item; `test_watch_attention_digest` covers them.
    """
    return [line for line in lines
            if not line.startswith(("digest: ", "attention "))]


class WatchAFinishedRun(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.dir = copy_tree(G1_RUN, self.tmp / "runs" / "g1")

    def test_watch_a_finished_run_returns_at_once_with_the_verdict(self):
        code, lines = call("watch", "--run", self.dir, "--timeout", 5)
        self.assertEqual(code, 0)
        self.assertRegex(lines[0], r"^finished: 2 of 2 steps passed, 0 running")
        self.assertTrue(any(line.startswith("exit report: ") for line in lines),
                        lines)
        # The fixture's seven digest entries come on top of the step lines.
        self.assertLessEqual(len(step_lines(lines)), 8)
        self.assertEqual(len(lines) - len(step_lines(lines)), 7)

    def test_watch_a_repeated_call_on_a_finished_run_reports_no_old_step(self):
        call("watch", "--run", self.dir, "--timeout", 0)
        code, lines = call("watch", "--run", self.dir, "--timeout", 0)
        self.assertEqual(code, 0)
        self.assertRegex(lines[0], r"^finished: ")
        self.assertFalse(any(" passed" in line and line.startswith("01.sweep")
                             for line in lines), lines)
        self.assertLessEqual(len(lines), 6)

    def test_watch_a_copied_run_directory_starts_from_a_fresh_cursor(self):
        call("watch", "--run", self.dir, "--timeout", 0)
        copy = copy_tree(self.dir, self.tmp / "runs" / "g1-copy")
        code, lines = call("watch", "--run", copy, "--timeout", 0)
        self.assertEqual(code, 0)
        self.assertTrue(any(" passed" in line and line.startswith("01.sweep")
                            for line in lines), lines)

    def test_watch_an_unknown_run_exits_2(self):
        code, lines = call("watch", "--run", self.tmp / "nowhere")
        self.assertEqual(code, 2)
        self.assertLessEqual(len(lines), 2)


class WatchARunThatChanges(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.dir = self.run_dir("r-change")
        workflow_json(self.dir, [("Map", [agent("a"), agent("b")], 2)])
        self.run_log = RunLog(self.dir).phase(1, "01.map", "Map", STEPS)
        mark_alive(self.dir)

    def test_watch_the_second_call_reports_only_the_new_change(self):
        self.run_log.start(2, STEPS[0]).start(3, STEPS[1])
        code, first = call("watch", "--run", self.dir, "--timeout", 0)
        self.assertEqual(code, watch.EXIT_GOING)
        self.assertRegex(first[0], r"^running: 0 of 2 steps passed, 2 running")
        self.assertIn(f"{STEPS[0]} started (attempt 1)", first)

        self.run_log.finish(40, STEPS[1], 1, "passed")
        code, second = call("watch", "--run", self.dir, "--timeout", 0)
        self.assertEqual(code, watch.EXIT_GOING)
        self.assertRegex(second[0], r"^running: 1 of 2 steps passed, 1 running")
        self.assertEqual(step_lines(second[1:]), [f"{STEPS[1]} passed"])
        self.assertRegex(second[2], r"^digest: role b attempt 1 passed")

    def test_watch_with_no_change_prints_only_the_status_line(self):
        self.run_log.start(2, STEPS[0])
        call("watch", "--run", self.dir, "--timeout", 0)
        code, again = call("watch", "--run", self.dir, "--timeout", 0)
        self.assertEqual(code, watch.EXIT_GOING)
        self.assertEqual(len(again), 1, again)

    def test_watch_each_cursor_name_keeps_its_own_place(self):
        self.run_log.start(2, STEPS[0])
        call("watch", "--run", self.dir, "--timeout", 0)
        _code, other = call("watch", "--run", self.dir, "--timeout", 0,
                            "--cursor", "second-reader")
        self.assertIn(f"{STEPS[0]} started (attempt 1)", other)
        self.assertTrue((self.dir / ".watch.second-reader.json").is_file())
        self.assertTrue((self.dir / ".watch.agent.json").is_file())

    def test_watch_waits_for_news_and_returns_when_a_step_changes(self):
        self.run_log.start(2, STEPS[0])
        call("watch", "--run", self.dir, "--timeout", 0)
        ticks = iter(range(1000))

        def sleep(_seconds):
            self.run_log.finish(40, STEPS[0], 1, "passed")

        with mock.patch.object(watch, "_sleep", sleep), \
                mock.patch.object(watch, "_clock", lambda: next(ticks)):
            code, lines = call("watch", "--run", self.dir, "--timeout", 60,
                               "--poll", 0)
        self.assertEqual(code, watch.EXIT_GOING)
        self.assertEqual(step_lines(lines[1:]), [f"{STEPS[0]} passed"])

    def test_watch_returns_on_the_timeout_with_exit_10(self):
        self.run_log.start(2, STEPS[0])
        ticks = iter(range(1000))
        with mock.patch.object(watch, "_sleep", lambda _s: None), \
                mock.patch.object(watch, "_clock", lambda: next(ticks)):
            code, lines = call("watch", "--run", self.dir, "--timeout", 3,
                               "--until", "end", "--poll", 0)
        self.assertEqual(code, watch.EXIT_GOING)
        self.assertRegex(lines[0], r"^running: ")

    def test_watch_json_carries_the_changes(self):
        self.run_log.start(2, STEPS[0])
        code, lines = call("watch", "--run", self.dir, "--timeout", 0,
                           "--json")
        self.assertEqual(code, watch.EXIT_GOING)
        data = json.loads("\n".join(lines))
        self.assertEqual(data["status"], "running")
        self.assertIn(f"{STEPS[0]} started (attempt 1)", data["changes"])


class WatchAnOrphanedRun(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.dir = self.run_dir("r-orphan")
        workflow_json(self.dir, [("Map", [agent("a"), agent("b")], 2)])
        (RunLog(self.dir).phase(1, "01.map", "Map", STEPS)
         .start(2, STEPS[0]).start(3, STEPS[1])
         .finish(40, STEPS[1], 1, "passed"))
        (self.dir / "supervisor.pid").write_text(DEAD_PID, encoding="utf-8")

    def test_watch_writes_the_exit_report_of_an_orphaned_run(self):
        self.assertFalse((self.dir / "exit.json").exists())
        code, lines = call("watch", "--run", self.dir, "--timeout", 0)
        self.assertEqual(code, 1)
        self.assertRegex(lines[0], r"^orphaned: 1 of 2 steps passed")
        self.assertTrue(any(line.startswith("exit report: ") for line in lines),
                        lines)
        self.assertTrue((self.dir / "exit.json").is_file())
        self.assertLessEqual(len(lines), 8)


class WatchARunThatNeverStarted(TempCase):
    """A detached launch that died before its first run log line leaves a
    directory with no run log and no supervisor. Its status, `not started`,
    never changes, so a watcher that waited for the end would answer exit 10
    ("call again") for ever."""

    def setUp(self) -> None:
        super().setUp()
        self.dir = self.run_dir("r-never")
        workflow_json(self.dir, [("Map", [agent("a")], 1)])
        (self.dir / ".ohflow-handoff.json").write_text("{}", encoding="utf-8")

    def age(self, seconds: float) -> None:
        past = time.time() - seconds
        for path in self.dir.iterdir():
            os.utime(path, (past, past))

    def watch(self, **kw):
        sleeps, ticks = [], iter(range(1000))
        with mock.patch.object(watch, "_sleep", sleeps.append), \
                mock.patch.object(watch, "_clock", lambda: next(ticks)):
            code, lines = call("watch", "--run", self.dir, "--timeout", 5,
                               "--poll", 0)
        return code, lines, sleeps

    def test_watch_a_run_that_never_started_ends_with_exit_1(self):
        self.age(60)
        code, lines, sleeps = self.watch()
        self.assertEqual(code, watch.EXIT_ENDED_BAD)
        self.assertRegex(lines[0], r"^not started: ")
        self.assertRegex(lines[1], r"^the run never started: no supervisor and "
                                   r"no run log; see ")
        self.assertEqual(sleeps, [], "it must not wait for the timeout")
        self.assertFalse((self.dir / "exit.json").exists())
        self.assertLessEqual(len(lines), 3)

    def test_watch_names_the_launch_log_when_there_is_one(self):
        (self.dir / "supervisor.log").write_text("boom", encoding="utf-8")
        self.age(60)
        _code, lines, _sleeps = self.watch()
        self.assertRegex(lines[1], r"supervisor\.log$")

    def test_watch_a_run_launched_a_moment_ago_keeps_polling(self):
        code, lines, sleeps = self.watch()
        self.assertEqual(code, watch.EXIT_GOING)
        self.assertRegex(lines[0], r"^not started: ")
        self.assertTrue(sleeps, "within the grace it polls")


class WatchARunDirectoryThatHoldsOnlyAWorkflow(TempCase):
    """A directory with `workflow.json` and nothing else is no launch in flight: a
    launch leaves `.ohflow-handoff.json` or `supervisor.pid`. Waiting cannot
    change it, so `watch` says so at once, with an exit code of its own."""

    def setUp(self) -> None:
        super().setUp()
        self.dir = self.run_dir("r-workflow-only")
        workflow_json(self.dir, [("Map", [agent("a")], 1)])

    def test_watch_reports_at_once_with_exit_3_and_names_the_next_step(self):
        sleeps = []
        with mock.patch.object(watch, "_sleep", sleeps.append):
            code, lines = call("watch", "--run", self.dir, "--timeout", 300,
                               "--poll", 0)
        self.assertEqual(code, watch.EXIT_NOT_STARTED)
        self.assertEqual(sleeps, [], "it must not wait for the timeout")
        self.assertRegex(lines[0], r"^not started: ")
        self.assertRegex(lines[1], r"^no run started here: ")
        self.assertLessEqual(len(lines), 3)

    def test_the_remedy_names_no_command_that_refuses_on_this_directory(self):
        """`run --resume` refuses a directory with no run log, and `run` with
        the same `--run-id` refuses a directory that exists. The line names a
        new run id or a delete."""
        (self.dir / "run.json").write_text(json.dumps(
            {"run_id": self.dir.name, "workflow_path": "C:/workflows/p.py"}),
            encoding="utf-8")
        code, lines = call("watch", "--run", self.dir, "--timeout", 0)
        self.assertEqual(code, watch.EXIT_NOT_STARTED)
        remedy = lines[1]
        self.assertNotIn("--resume", remedy)
        self.assertIn("new --run-id", remedy)
        self.assertRegex(remedy, r"delete .*directory")
        self.assertNotIn(f"--run-id {self.dir.name}", remedy)

    def test_watch_json_carries_the_status_and_the_code_words(self):
        code, lines = call("watch", "--run", self.dir, "--timeout", 0,
                           "--json")
        self.assertEqual(code, watch.EXIT_NOT_STARTED)
        self.assertEqual(json.loads("\n".join(lines))["status"], "not started")


class WatchARunWhoseEngineIsStillStarting(TempCase):
    """An attached run writes `workflow.json`, then runs preflight and the baseline
    command, and only the first run log line writes `supervisor.pid`. In that
    window `watch` told an agent to start a run that was alive (exit 3, or exit
    1 after the grace). `.ohflow-owner.json` names the engine from the first
    moment, so a live owner means the run is going."""

    def setUp(self) -> None:
        super().setUp()
        self.dir = self.run_dir("r-starting")
        workflow_json(self.dir, [("Map", [agent("a")], 1)])
        past = time.time() - 60
        os.utime(self.dir / "workflow.json", (past, past))
        self.owner = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.addCleanup(self.owner.wait)
        self.addCleanup(self.owner.kill)
        (self.dir / ".ohflow-owner.json").write_text(
            json.dumps({"run_id": "r-starting", "pid": self.owner.pid}),
            encoding="utf-8")

    def watch(self):
        sleeps, ticks = [], iter(range(1000))
        with mock.patch.object(watch, "_sleep", sleeps.append), \
                mock.patch.object(watch, "_clock", lambda: next(ticks)):
            code, lines = call("watch", "--run", self.dir, "--timeout", 5,
                               "--poll", 0)
        return code, lines, sleeps

    def test_watch_a_run_with_a_live_owner_keeps_polling_and_exits_10(self):
        code, lines, sleeps = self.watch()
        self.assertEqual(code, watch.EXIT_GOING, lines)
        self.assertRegex(lines[0], r"^starting: ")
        self.assertTrue(sleeps, "it polls until the timeout")
        self.assertFalse(any("no run started here" in line
                             or "never started" in line for line in lines),
                         lines)

    def test_watch_a_starting_run_idle_past_the_grace_still_exits_10(self):
        with mock.patch.object(watch, "_idle_seconds", lambda _dir: 60):
            code, lines, _sleeps = self.watch()
        self.assertEqual(code, watch.EXIT_GOING, lines)
        self.assertRegex(lines[0], r"^starting: ")

    def test_watch_a_run_whose_owner_died_is_no_launch_in_flight(self):
        self.owner.kill()
        self.owner.wait()
        code, _lines, sleeps = self.watch()
        self.assertEqual(code, watch.EXIT_NOT_STARTED)
        self.assertEqual(sleeps, [])


class WatchARunThatCrashedInPreflight(TempCase):
    """An attached run whose preflight fails (a baseline command that exits
    non-zero) leaves `workflow.json`, `.ohflow-owner.json` and an `exit.json` with
    status `crashed` and the error, and no run log. `watch` said "no run
    started here" and named a command that refuses in both forms, and the
    crash and its cause stayed in `exit.json`."""

    ERROR = ("PreflightError: baseline command 'false' exited 1 at ad03370e; "
             "see C:/runs/r-crash/logs/baseline.out.log")

    def setUp(self) -> None:
        super().setUp()
        self.dir = self.run_dir("r-crash")
        workflow_json(self.dir, [("Map", [agent("a")], 1)])
        (self.dir / ".ohflow-owner.json").write_text(
            json.dumps({"run_id": "r-crash", "pid": int(DEAD_PID)}),
            encoding="utf-8")
        (self.dir / "run.json").write_text(
            json.dumps({"run_id": "r-crash", "workflow_path": "p.py"}),
            encoding="utf-8")
        ohexit.write_exit_report(self.dir, ohexit.exit_info(
            "crashed", self.ERROR, "Traceback ...\n" + self.ERROR))

    def test_watch_reports_the_crash_and_its_cause_and_exits_1(self):
        code, lines = call("watch", "--run", self.dir, "--timeout", 5)
        self.assertEqual(code, watch.EXIT_ENDED_BAD, lines)
        self.assertRegex(lines[0], r"^crashed: 0 of 1 steps passed")
        self.assertTrue(any("baseline command 'false' exited 1" in line
                            for line in lines), lines)
        self.assertTrue(any(line.startswith("exit report: ") for line in lines),
                        lines)
        self.assertFalse(any("no run started here" in line
                             or line.startswith("resume:") for line in lines),
                         lines)

    def test_status_says_crashed_on_line_one(self):
        code, lines = call("status", "--run", self.dir)
        self.assertEqual(code, 0)
        self.assertRegex(lines[0], r"^crashed: ")


if __name__ == "__main__":
    import unittest
    unittest.main()

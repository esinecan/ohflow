"""The suite had no time limit for one test.

Shard 1 ran over 35 minutes in a cloud box and 82 s in WSL on the same commit.
Nothing named the test that hung, and only the step's execution timeout ended
the run.

`run_tests.py` now gives every test `--test-timeout` seconds, 300 by default
and 1800 under `--e2e`, whose live matrix is one test of a few minutes; an
explicit `--test-timeout` wins.
A test past the limit ends the run: the output names the test and holds the
stack of every thread, and the exit code is 1. A timer thread does it, so the
limit also works on Windows, which has no alarm signal.

The limit also ends every descendant of the run. A child the hung test
started through plain `subprocess` inherits the run's stdout, and while it
lived a caller that read the run through a pipe got no end of file: the limit
named the test and the caller still waited for the child.

The slow tests live in `fixtures/slow_case.py`, which the suite does not
discover. They run here in a child process, because the limit ends the process.
"""

from __future__ import annotations

import io
import os
import signal
import subprocess
import sys
import time
import unittest
import unittest.mock
from pathlib import Path

import run_tests
from fixtures import slow_case
from ohflow import proc
from support import TempCase

TESTS = Path(run_tests.__file__).resolve().parent

CHILD = """
import sys, unittest
sys.path.insert(0, sys.argv[1])
import run_tests
from fixtures import slow_case
suite = unittest.defaultTestLoader.loadTestsFromTestCase(
    getattr(slow_case, sys.argv[3]))
run_tests.ReasonedRunner(stream=sys.stdout, verbosity=2,
                         test_timeout=float(sys.argv[2])).run(suite)
print("the run went on")
"""


class ATestPastItsLimitEndsTheRun(TempCase):

    def run_slow_case(self, limit: str) -> tuple[subprocess.CompletedProcess, float]:
        started = time.monotonic()
        done = subprocess.run([sys.executable, "-c", CHILD, str(TESTS), limit,
                               "SlowCase"],
                              capture_output=True, text=True, timeout=120,
                              stdin=subprocess.DEVNULL, cwd=str(self.tmp))
        return done, time.monotonic() - started

    def test_the_slow_test_is_named_and_the_run_exits_1(self):
        done, elapsed = self.run_slow_case("1")
        slow = f"{slow_case.__name__}.SlowCase.test_2_sleeps_past_any_limit"
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn(f"TIMED OUT after 1s: {slow}", done.stdout)
        self.assertLess(elapsed, 60)

    def test_the_output_holds_the_stack_of_the_hung_test(self):
        done, _ = self.run_slow_case("1")
        self.assertIn("thread MainThread:", done.stdout)
        self.assertIn("time.sleep(600)", done.stdout)

    def test_the_tests_after_it_do_not_run(self):
        done, _ = self.run_slow_case("1")
        self.assertIn("test_1_ends_at_once", done.stdout)
        self.assertIn("ran 1 tests before it", done.stdout)
        self.assertNotIn("test_3_never_starts", done.stdout)
        self.assertNotIn("the run went on", done.stdout)


class AChildOfTheHungTestEndsWithTheRun(TempCase):

    def end_the_waited_on_child(self) -> None:
        try:
            pid = int((self.tmp / slow_case.CHILD_PID_FILE).read_text())
        except (OSError, ValueError):
            return
        if proc.pid_alive(pid):
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass

    def test_the_output_pipe_of_the_run_reaches_its_end(self):
        self.addCleanup(self.end_the_waited_on_child)
        started = time.monotonic()
        run = subprocess.Popen([sys.executable, "-c", CHILD, str(TESTS), "2",
                                "WaitsOnAChild"],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               stdin=subprocess.DEVNULL, text=True,
                               cwd=str(self.tmp))
        try:
            out, _ = run.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            run.kill()
            run.stdout.close()
            run.wait(timeout=30)
            self.fail("the run's output pipe was still open 30 s after the "
                      "run started: a child of the hung test holds it")
        self.assertLess(time.monotonic() - started, 30)
        self.assertEqual(run.returncode, 1, out)
        self.assertIn("TIMED OUT after 2s: ", out)
        self.assertIn("test_waits_on_a_plain_child_that_holds_stdout", out)
        pid = int((self.tmp / slow_case.CHILD_PID_FILE).read_text())
        deadline = time.monotonic() + 10
        while proc.pid_alive(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertFalse(proc.pid_alive(pid), "the child outlived the run")


class TheRunEndsEvenWhenTheReportCannotBeWritten(unittest.TestCase):

    def test_a_stream_that_refuses_the_report_still_ends_the_run(self):
        class Refusing(io.StringIO):
            def write(self, text):
                raise UnicodeEncodeError("cp1252", text, 0, 1, "no such character")

        result = run_tests.ReasonedResult(Refusing(), True, 0, test_timeout=1)
        with unittest.mock.patch.object(run_tests.os, "_exit") as leave, \
                unittest.mock.patch.object(run_tests.proc, "end_owned_groups") as end, \
                unittest.mock.patch.object(run_tests.proc, "end_descendants") as end_rest:
            with self.assertRaises(UnicodeEncodeError):
                result._timed_out("some.test")
        end.assert_called_once_with()
        end_rest.assert_called_once_with()
        leave.assert_called_once_with(1)


class ATestInsideItsLimitIsLeftAlone(unittest.TestCase):

    def test_a_quick_test_passes_and_its_timer_is_cancelled(self):
        suite = unittest.TestSuite([slow_case.SlowCase("test_1_ends_at_once")])
        result = run_tests.ReasonedRunner(stream=io.StringIO(), verbosity=0,
                                          test_timeout=30).run(suite)
        self.assertTrue(result.wasSuccessful())
        self.assertEqual(result.testsRun, 1)
        self.assertIsNone(result._limit)

    def test_no_limit_starts_no_timer(self):
        result = run_tests.ReasonedResult(io.StringIO(), True, 0)
        test = slow_case.SlowCase("test_1_ends_at_once")
        result.startTest(test)
        self.assertIsNone(result._limit)
        result.stopTest(test)


class TheLimitIsAFlagWithADefault(unittest.TestCase):

    def test_the_default_is_300_seconds(self):
        ns = run_tests.parse_args([])
        self.assertEqual(ns.test_timeout, 300.0)
        self.assertEqual(run_tests.DEFAULT_TEST_TIMEOUT_S, 300.0)

    def test_the_flag_sets_it_and_0_turns_it_off(self):
        self.assertEqual(run_tests.parse_args(["--test-timeout", "45"]).test_timeout, 45.0)
        self.assertEqual(run_tests.parse_args(["--test-timeout", "0"]).test_timeout, 0.0)

    def test_e2e_raises_the_default_to_1800_seconds(self):
        self.assertEqual(run_tests.parse_args(["--e2e"]).test_timeout, 1800.0)
        self.assertEqual(run_tests.E2E_TEST_TIMEOUT_S, 1800.0)

    def test_an_explicit_flag_wins_over_the_e2e_default(self):
        for argv in (["--e2e", "--test-timeout", "60"], ["--test-timeout", "60", "--e2e"]):
            with self.subTest(argv=argv):
                self.assertEqual(run_tests.parse_args(argv).test_timeout, 60.0)
        self.assertEqual(run_tests.parse_args(["--e2e", "--test-timeout", "0"]).test_timeout,
                         0.0)

    def test_a_value_that_is_no_limit_is_refused(self):
        parser = run_tests.build_parser()
        for bad in ("-1", "soon", "inf", "nan"):
            with self.subTest(bad=bad), self.assertRaises(SystemExit), \
                    unittest.mock.patch("sys.stderr", io.StringIO()):
                parser.parse_args(["--test-timeout", bad])


if __name__ == "__main__":
    unittest.main()

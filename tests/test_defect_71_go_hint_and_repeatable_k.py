"""Defect 71: two hints an operator could not use as printed.

1. The held-run hint was `ohflow go --run <dir>`. A source install has no
   `ohflow` command; every other hint is `<python> -m ohflow.cli ...`. The go
   hint is built the same way now.
2. `run_tests.py -k a -k b` ran only `b`: the option kept its last value. It
   is repeatable now, and a test runs when its name holds any of the patterns.
"""

from __future__ import annotations

import run_tests
from ohflow import supervisor
from ohflow.paths import python_cmd, win
from support import TempCase


class TheGoHintRunsAsPrinted(TempCase):

    def test_it_starts_with_this_interpreter_and_the_cli_module(self):
        run_dir = self.tmp / "run"
        self.assertEqual(supervisor.go_command(run_dir),
                         f"{python_cmd()} -m ohflow.cli go --run {win(run_dir)}")


class TheNameFilterIsRepeatable(TempCase):

    def test_every_k_is_kept(self):
        ns = run_tests.build_parser().parse_args(["-k", "defect_66", "-k", "defect_67"])
        self.assertEqual(ns.pattern, ["defect_66", "defect_67"])
        self.assertEqual(run_tests.name_patterns(ns.pattern),
                         ["*defect_66*", "*defect_67*"])

    def test_no_k_means_no_filter(self):
        ns = run_tests.build_parser().parse_args([])
        self.assertFalse(ns.pattern)
        self.assertEqual(run_tests.name_patterns(ns.pattern), [])


if __name__ == "__main__":
    import unittest
    unittest.main()

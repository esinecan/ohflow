"""`ohflow watch` prints a pointer line at each phase boundary.

Before: the phase boundary check lived only in the skill body, in
`references/monitor-a-run.md`. An orchestrator whose harness dropped that body
at compaction kept polling `watch` and passed each boundary without the check,
because no line of the watch output named it. Now `watch` prints one
`phase boundary:` line for each phase that settled since its cursor last
looked, and the line names the file and the check.
"""

from __future__ import annotations

import json

from dashboard_support import RunLog, agent, mark_alive, workflow_json
from ohflow import watch
from support import TempCase
from verb_support import call

ALPHA, BETA, GAMMA = "01.alpha", "02.beta", "03.gamma"
A, B, C = f"{ALPHA}/01.a", f"{BETA}/01.b", f"{GAMMA}/01.c"
POINTER = " · next: the phase boundary check in references/monitor-a-run.md"


def boundary_lines(lines: list[str]) -> list[str]:
    return [line for line in lines if line.startswith("phase boundary: ")]


def pass_phase(log: RunLog, at: float, pc: str, name: str, c: str) -> RunLog:
    return (log.phase(at, pc, name, [c], 1).start(at + 1, c)
            .finish(at + 11, c, 1, "passed").settle(at + 12, pc, "passed", 1, 1))


class APhaseBoundaryOnALiveRun(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.dir = self.run_dir("r-boundary")
        workflow_json(self.dir, [("Alpha", [agent("a")], 1),
                                 ("Beta", [agent("b")], 1),
                                 ("Gamma", [agent("c")], 1)])
        self.log = RunLog(self.dir).phase(1, ALPHA, "Alpha", [A], 1).start(2, A)
        mark_alive(self.dir)

    def test_a_phase_that_settles_gives_one_line_that_names_the_file_and_the_check(self):
        _code, before = call("watch", "--run", self.dir, "--timeout", 0)
        self.assertEqual(boundary_lines(before), [])

        self.log.finish(12, A, 1, "passed").settle(13, ALPHA, "passed", 1, 1)
        code, lines = call("watch", "--run", self.dir, "--timeout", 0)
        self.assertEqual(code, watch.EXIT_GOING)
        self.assertEqual(
            boundary_lines(lines),
            ["phase boundary: phase 01 Alpha settled passed" + POINTER])
        self.assertIn("references/monitor-a-run.md", lines[-1])
        self.assertIn("phase boundary check", lines[-1])

        _code, again = call("watch", "--run", self.dir, "--timeout", 0)
        self.assertEqual(boundary_lines(again), [])

    def test_two_phases_that_settle_between_two_calls_give_one_line_each(self):
        call("watch", "--run", self.dir, "--timeout", 0)
        self.log.finish(12, A, 1, "passed").settle(13, ALPHA, "passed", 1, 1)
        pass_phase(self.log, 20, BETA, "Beta", B)
        _code, lines = call("watch", "--run", self.dir, "--timeout", 0)
        self.assertEqual(
            boundary_lines(lines),
            ["phase boundary: phase 01 Alpha settled passed" + POINTER,
             "phase boundary: phase 02 Beta settled passed" + POINTER])

    def test_a_fresh_cursor_names_only_the_newest_settled_phase(self):
        self.log.finish(12, A, 1, "passed").settle(13, ALPHA, "passed", 1, 1)
        pass_phase(self.log, 20, BETA, "Beta", B)
        _code, lines = call("watch", "--run", self.dir, "--timeout", 0)
        self.assertEqual(
            boundary_lines(lines),
            ["phase boundary: phase 02 Beta settled passed" + POINTER])

    def test_a_cursor_in_the_old_format_names_the_newest_settled_phase_once(self):
        self.log.finish(12, A, 1, "passed").settle(13, ALPHA, "passed", 1, 1)
        call("watch", "--run", self.dir, "--timeout", 0)
        path = self.dir / ".watch.agent.json"
        stored = json.loads(path.read_text(encoding="utf-8"))
        del stored["phases"]
        path.write_text(json.dumps(stored), encoding="utf-8")
        _code, lines = call("watch", "--run", self.dir, "--timeout", 0)
        self.assertEqual(len(boundary_lines(lines)), 1, lines)
        _code, again = call("watch", "--run", self.dir, "--timeout", 0)
        self.assertEqual(boundary_lines(again), [])

    def test_a_phase_that_settles_again_after_a_restart_gives_its_line_again(self):
        self.log.finish(12, A, 1, "quarantined", error="tests red")
        self.log.settle(13, ALPHA, "failed", 0, 1)
        _code, lines = call("watch", "--run", self.dir, "--timeout", 0)
        self.assertEqual(
            boundary_lines(lines),
            ["phase boundary: phase 01 Alpha settled failed" + POINTER])

        self.log.phase(30, ALPHA, "Alpha", [A], 1).start(31, A, 2, "resume")
        _code, running = call("watch", "--run", self.dir, "--timeout", 0)
        self.assertEqual(boundary_lines(running), [])
        self.log.finish(41, A, 2, "passed").settle(42, ALPHA, "passed", 1, 1)
        _code, lines = call("watch", "--run", self.dir, "--timeout", 0)
        self.assertEqual(
            boundary_lines(lines),
            ["phase boundary: phase 01 Alpha settled passed" + POINTER])

    def test_watch_json_names_the_phases_whose_boundary_it_reports(self):
        call("watch", "--run", self.dir, "--timeout", 0)
        self.log.finish(12, A, 1, "passed").settle(13, ALPHA, "passed", 1, 1)
        _code, lines = call("watch", "--run", self.dir, "--timeout", 0,
                            "--json")
        self.assertEqual(json.loads("\n".join(lines))["phase_boundaries"],
                         [ALPHA])
        _code, lines = call("watch", "--run", self.dir, "--timeout", 0,
                            "--json")
        self.assertEqual(json.loads("\n".join(lines))["phase_boundaries"], [])

    def test_a_long_phase_name_gives_way_and_the_pointer_stays(self):
        line = watch.boundary_line({"coord": ALPHA, "name": "n" * 400,
                                    "state": "passed"})
        self.assertEqual(len(line), watch.LINE_CAP)
        self.assertTrue(line.endswith(POINTER), line)

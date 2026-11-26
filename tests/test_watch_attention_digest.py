"""`ohflow watch` carries the attention items and the digest.

Before: the attention items and the digest were built only for the dashboard
page, so an orchestrating agent read them from `/api/workflow`, a route that
exists only while the dashboard serves, at about 9,450 tokens a call on a
4-step run. Now `watch` prints each new digest entry and each new or cleared
attention item as one line with its run-log line, and its cursor remembers
what it reported, so a repeated call never prints the same entry twice.

The spec is `docs/history/orchestrator-visibility.md`, "Utility 1".
"""

from __future__ import annotations

import json
import re
from unittest import mock

from dashboard_support import (G1_RUN, RunLog, agent, copy_tree, mark_alive,
                               workflow_json)
from ohflow import dashboard_data, runstatus, watch
from support import TempCase
from verb_support import call

A, B, C = "01.alpha/01.a", "01.alpha/02.b", "01.alpha/03.c"
DIGEST = re.compile(r"^digest: .+ · run-log\.jsonl:(\d+)$")
SPENT = "retry budget spent: 1 of 1 retries used for this work"
#: The run-log lines of the g1 fixture's seven digest entries.
G1_DIGEST_LINES = [8, 9, 11, 13, 17, 19, 20]


def digest_lines(lines: list[str]) -> list[str]:
    return [line for line in lines if line.startswith("digest: ")]


def attention_lines(lines: list[str]) -> list[str]:
    return [line for line in lines if line.startswith("attention ")]


def evidence_lines(lines: list[str]) -> list[int]:
    return [int(DIGEST.match(line).group(1)) for line in digest_lines(lines)]


def three_steps(run) -> RunLog:
    workflow_json(run, [("Alpha", [agent("a", retry_max=1), agent("b"),
                                   agent("c", retry_max=1)], 3)])
    log = RunLog(run).phase(1, "01.alpha", "Alpha", [A, B, C], 3)
    mark_alive(run)
    return log


def fail_with_budget_spent(log: RunLog, at: float, coord: str) -> RunLog:
    return (log.start(at, coord)
            .finish(at + 10, coord, 1, "quarantined", error="tests red")
            .add(at + 10, "retry_decided", coord, 1, retry_decision=SPENT))


class TheDigestOnAFinishedRun(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.dir = copy_tree(G1_RUN, self.tmp / "runs" / "g1")

    def test_1_a_first_call_prints_one_digest_line_per_entry_with_its_line(self):
        code, lines = call("watch", "--run", self.dir, "--timeout", 0)
        self.assertEqual(code, 0)
        self.assertEqual(evidence_lines(lines), G1_DIGEST_LINES)
        for line in digest_lines(lines):
            self.assertRegex(line, DIGEST)
        self.assertIn("digest: control attempt 1 passed in 8 s; gate "
                      "tree_clean ok, ownership ok · run-log.jsonl:11", lines)
        # The order: head, step changes, digest, then attention.
        first_digest = lines.index(digest_lines(lines)[0])
        self.assertTrue(lines[first_digest - 1] == "run finished", lines)

    def test_every_digest_entry_comes_from_one_run_log_line(self):
        view = dashboard_data.agent_view(self.dir)
        log = (self.dir / "run-log.jsonl").read_text(
            encoding="utf-8").splitlines()
        self.assertEqual([e["evidence"]["line"] for e in view["digest"]],
                         G1_DIGEST_LINES)
        for entry in view["digest"]:
            self.assertEqual(entry["evidence"]["path"], "run-log.jsonl")
            rec = json.loads(log[entry["evidence"]["line"] - 1])
            self.assertEqual(rec["event"], entry["kind"])
        self.assertEqual(view["attention"], [])
        self.assertEqual(set(view), {"attention", "digest"})

    def test_agent_view_is_none_for_a_directory_that_is_no_run(self):
        self.assertIsNone(dashboard_data.agent_view(self.tmp / "nothing"))

    def test_2_a_second_call_prints_no_digest_line_again(self):
        call("watch", "--run", self.dir, "--timeout", 0)
        _code, lines = call("watch", "--run", self.dir, "--timeout", 0)
        self.assertEqual(digest_lines(lines), [])
        cursor = json.loads((self.dir / ".watch.agent.json").read_text(
            encoding="utf-8"))
        self.assertEqual(cursor["digest_line"], 20)
        self.assertEqual(cursor["attention"], [])

    def test_3_one_appended_digest_event_gives_exactly_one_new_line(self):
        call("watch", "--run", self.dir, "--timeout", 0)
        with (self.dir / "run-log.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"event": "run_finished",
                                 "payload": {"status": "finished"},
                                 "ts": "2026-09-29T00:12:20Z"}) + "\n")
        _code, lines = call("watch", "--run", self.dir, "--timeout", 0)
        self.assertEqual(digest_lines(lines),
                         ["digest: run finished · run-log.jsonl:21"])

    def test_6_a_cursor_in_the_old_format_prints_the_first_call_digest(self):
        call("watch", "--run", self.dir, "--timeout", 0)
        path = self.dir / ".watch.agent.json"
        cursor = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps({"facts": cursor["facts"]}),
                        encoding="utf-8")
        code, lines = call("watch", "--run", self.dir, "--timeout", 0)
        self.assertEqual(code, 0)
        self.assertEqual(evidence_lines(lines), G1_DIGEST_LINES)
        # The step facts the old cursor holds are kept: no step line again.
        self.assertNotIn("01.sweep/01.flaky passed", lines)
        self.assertNotIn("run finished", lines)

    def test_watch_json_carries_the_new_digest_entries_and_the_attention(self):
        code, lines = call("watch", "--run", self.dir, "--timeout", 0,
                           "--json")
        self.assertEqual(code, 0)
        data = json.loads("\n".join(lines))
        self.assertEqual([e["evidence"]["line"] for e in data["digest"]],
                         G1_DIGEST_LINES)
        self.assertIn("handover_first_line", data["digest"][0])
        self.assertEqual(data["attention"], [])
        _code, again = call("watch", "--run", self.dir, "--timeout", 0,
                            "--json")
        self.assertEqual(json.loads("\n".join(again))["digest"], [])


class AttentionOnALiveRun(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.dir = self.run_dir("r-attention")
        self.log = three_steps(self.dir)
        self.log.start(2, B).finish(12, B, 1, "passed")

    def test_4_a_spent_retry_budget_is_one_intervention_line_until_it_clears(self):
        fail_with_budget_spent(self.log, 2, A)
        code, lines = call("watch", "--run", self.dir, "--timeout", 0)
        self.assertEqual(code, watch.EXIT_GOING)
        found = attention_lines(lines)
        self.assertEqual(len(found), 1, lines)
        self.assertRegex(found[0], r"^attention standing intervention: "
                                   r"attempt 1 quarantined: tests red · next: "
                                   r"no further start by the engine: retry "
                                   r"budget spent")
        self.assertTrue(found[0].endswith(" · run-log.jsonl:6"), found[0])
        # The attention lines come last.
        self.assertEqual(lines[-1], found[0])

        _code, again = call("watch", "--run", self.dir, "--timeout", 0)
        self.assertEqual(attention_lines(again), [])

        self.log.start(30, A, 2, "resume").finish(40, A, 2, "passed")
        _code, cleared = call("watch", "--run", self.dir, "--timeout", 0)
        self.assertEqual(attention_lines(cleared),
                         [f"attention cleared: failed_step {A}"])

    def test_a_fresh_cursor_says_standing_and_a_later_call_does_not(self):
        fail_with_budget_spent(self.log, 2, A)
        call("watch", "--run", self.dir, "--timeout", 0)
        fail_with_budget_spent(self.log, 40, C)
        _code, later = call("watch", "--run", self.dir, "--timeout", 0)
        found = attention_lines(later)
        self.assertEqual(len(found), 1, later)
        self.assertTrue(found[0].startswith("attention intervention: "),
                        found[0])

        _code, fresh = call("watch", "--run", self.dir, "--timeout", 0,
                            "--cursor", "second-reader")
        found = attention_lines(fresh)
        self.assertEqual(len(found), 2, fresh)
        for line in found:
            self.assertTrue(
                line.startswith("attention standing intervention: "), line)

    def test_an_item_that_arrives_while_a_fresh_cursor_waits_is_not_standing(self):
        fail_with_budget_spent(self.log, 2, A)
        sleeps = []

        def sleep(_seconds):
            sleeps.append(_seconds)
            if len(sleeps) == 1:
                fail_with_budget_spent(self.log, 40, C)

        ticks = iter(range(1000))
        with mock.patch.object(watch, "_sleep", sleep), \
                mock.patch.object(watch, "_clock", lambda: next(ticks)):
            _code, lines = call("watch", "--run", self.dir, "--timeout", 3,
                                "--until", "end", "--poll", 0)
        self.assertEqual(
            sorted(line.split(": ")[0] for line in attention_lines(lines)),
            ["attention intervention", "attention standing intervention"])

    def test_watch_json_names_the_new_items_and_none_on_a_fresh_cursor(self):
        fail_with_budget_spent(self.log, 2, A)
        _code, lines = call("watch", "--run", self.dir, "--timeout", 0,
                            "--json")
        data = json.loads("\n".join(lines))
        self.assertEqual(data["attention_new"], [])
        self.assertEqual(len(data["attention"]), 1)

        fail_with_budget_spent(self.log, 40, C)
        _code, lines = call("watch", "--run", self.dir, "--timeout", 0,
                            "--json")
        data = json.loads("\n".join(lines))
        self.assertEqual(data["attention_new"],
                         [f"intervention|failed_step|{C}|1"])
        self.assertEqual(len(data["attention"]), 2)

    def test_5_until_attention_waits_past_a_digest_line_for_an_intervention(self):
        call("watch", "--run", self.dir, "--timeout", 0)
        appends = iter([
            lambda: self.log.start(20, C).finish(30, C, 1, "passed"),
            lambda: fail_with_budget_spent(self.log, 40, A),
        ])
        sleeps = []

        def sleep(_seconds):
            sleeps.append(_seconds)
            next(appends, lambda: None)()

        ticks = iter(range(1000))
        with mock.patch.object(watch, "_sleep", sleep), \
                mock.patch.object(watch, "_clock", lambda: next(ticks)):
            code, lines = call("watch", "--run", self.dir, "--timeout", 60,
                               "--until", "attention", "--poll", 0)
        self.assertEqual(code, watch.EXIT_GOING)
        self.assertEqual(len(sleeps), 2, "a digest line alone must not return")
        self.assertTrue(any(line.startswith("digest: role c attempt 1 passed")
                            for line in lines), lines)
        self.assertEqual(len([l for l in attention_lines(lines)
                              if l.startswith("attention intervention: ")]), 1)

    def test_until_change_returns_on_a_digest_line_alone(self):
        self.log.start(20, A).finish(30, A, 1, "quarantined", error="red")
        call("watch", "--run", self.dir, "--timeout", 0)
        sleeps = []

        def sleep(_seconds):
            sleeps.append(_seconds)
            self.log.add(30, "retry_decided", A, 1, retry_decision=SPENT)

        ticks = iter(range(1000))
        with mock.patch.object(watch, "_sleep", sleep), \
                mock.patch.object(watch, "_clock", lambda: next(ticks)):
            code, lines = call("watch", "--run", self.dir, "--timeout", 60,
                               "--poll", 0)
        self.assertEqual(code, watch.EXIT_GOING)
        self.assertEqual(len(sleeps), 1)
        self.assertEqual(len(digest_lines(lines)), 1, lines)
        self.assertIn(SPENT, digest_lines(lines)[0])

    def test_every_new_line_is_capped_and_keeps_its_evidence(self):
        (self.log.start(20, A)
         .finish(30, A, 1, "quarantined", error="tests red " * 100)
         .add(30, "retry_decided", A, 1, retry_decision=SPENT))
        _code, lines = call("watch", "--run", self.dir, "--timeout", 0)
        new = digest_lines(lines) + attention_lines(lines)
        self.assertTrue(new)
        for line in new:
            self.assertLessEqual(len(line), 300, line)
        self.assertRegex(attention_lines(lines)[0], r" · run-log\.jsonl:\d+$")

    def test_a_long_next_command_is_never_cut(self):
        # A resume command with long Windows paths passes the cap alone. A
        # cut command cannot be run, so the line grows past the cap instead.
        command = "python -m ohflow.cli run --workflow " + "C:\\x" * 120 \
            + " --resume r-1"
        item = {"group": "intervention", "kind": "run_stopped",
                "observed": {"text": "the run paused on a transient fault"},
                "next": {"command": command, "text": "resume"},
                "evidence": {"line": 9}}
        line = watch.attention_line(item)
        self.assertIn(f" · next: {command} · run-log.jsonl:9", line)
        self.assertTrue(line.startswith("attention intervention: the run"),
                        line)

    def test_7_status_json_carries_the_attention_items(self):
        fail_with_budget_spent(self.log, 2, A)
        code, lines = call("status", "--run", self.dir, "--json")
        self.assertEqual(code, 0)
        data = json.loads("\n".join(lines))
        self.assertEqual([i["kind"] for i in data["attention"]],
                         ["failed_step"])
        self.assertEqual(data["attention"][0]["coord"], A)
        # Text `status` is unchanged.
        _code, text = call("status", "--run", self.dir)
        self.assertFalse(any(line.startswith("attention") for line in text),
                         text)


class AFirstCallWithMoreDigestThanItPrints(TempCase):

    def test_8_a_first_call_prints_the_newest_entries_after_the_cut_line(self):
        run = self.run_dir("r-many")
        steps = [agent(f"s{i:02d}") for i in range(1, 12)]
        workflow_json(run, [("Alpha", steps, 11)])
        coords = [f"01.alpha/{i:02d}.s{i:02d}" for i in range(1, 12)]
        log = RunLog(run).phase(1, "01.alpha", "Alpha", coords, 11)
        for n, coord in enumerate(coords):
            log.start(2 + n, coord).finish(20 + n, coord, 1, "passed")
        log.settle(40, "01.alpha", "passed", 11, 11)
        mark_alive(run)
        entries = dashboard_data.agent_view(run)["digest"]
        self.assertEqual(len(entries), 12)

        code, lines = call("watch", "--run", run, "--timeout", 0)
        self.assertEqual(code, watch.EXIT_GOING)
        keep = runstatus.FIRST_CALL_LINES
        cut = f"... {len(entries) - keep} earlier digest entries not shown"
        self.assertIn(cut, lines)
        self.assertEqual(evidence_lines(lines),
                         [e["evidence"]["line"] for e in entries[-keep:]])
        self.assertEqual(lines.index(cut) + 1,
                         lines.index(digest_lines(lines)[0]))
        _code, again = call("watch", "--run", run, "--timeout", 0)
        self.assertEqual(digest_lines(again), [])


if __name__ == "__main__":
    import unittest
    unittest.main()

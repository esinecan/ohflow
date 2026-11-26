"""`ohflow transcript`, `ohflow actions` and the dashboard read a pi-cloud attempt.

What went wrong. On 22.11.2026 a killed pi-cloud attempt of run
`r-20261122-102109-10d0f2be` held `logs/pi-cloud-events.jsonl`, and still
`actions` answered "harness executor 'pi-cloud' has no transcript reader here"
and `transcript` answered "no pi-cloud transcript": the actions readers
covered pi, claude and codex only, and the transcript was only the copy the
runner makes after the Worker settled, which a killed runner never makes.

What is asserted here. A running, a finished and a killed pi-cloud attempt
each answer all three entry points from the event log, a finished one's
`transcript` prefers the Worker's own copy, and a log that holds a replay of
its own conversation counts each model call, action and record once. The
event lines are the Worker's recorded stream of 26.10.2026
(`tests/fixtures/pi_cloud`).
"""

from __future__ import annotations

import json
from pathlib import Path

from dashboard_support import RunLog, agent, mark_alive, workflow_json
from ohflow import actions, dashboard_data, pi_cloud_runner, rundir
from support import TempCase
from verb_support import call

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "pi_cloud"
S = "01.work/01.s"


def events(name: str, *, drop: tuple[str, ...] = ()) -> list[str]:
    lines = (FIXTURES / name).read_text(encoding="utf-8").splitlines()
    return [line for line in lines
            if json.loads(line).get("type") not in drop + ("pi_cloud_beat",)]


def replayed_log() -> list[str]:
    """A conversation streamed live, then replayed whole on a reconnection,
    as a client that lost its seen set would have written it."""
    return (events("single-events.ndjson", drop=("pi_cloud_end",))
            + events("replay-events.ndjson", drop=("pi_cloud_start",)))


def a_run(run: Path, lines: list[str], *, state: str,
          transcript: bool = False) -> Path:
    workflow_json(run, [("Work", [agent("s", harness_executor="pi-cloud")], 1)])
    log = RunLog(run).phase(1, "01.work", "Work", [S], 1).start(2, S)
    if state == "finished":
        log.finish(30, S, 1, "passed")
    elif state == "killed":
        log.finish(30, S, 1, "failed",
                   error="execution timeout: the engine killed the runner")
    mark_alive(run)
    adir = rundir.attempt_dir(run, S, 1)
    (adir / "logs").mkdir(parents=True, exist_ok=True)
    (adir / "result.json").write_text("{}", encoding="utf-8")
    (adir / "logs" / pi_cloud_runner.EVENT_LOG).write_text(
        "".join(line + "\n" for line in lines), encoding="utf-8")
    if transcript:
        (adir / "transcript.md").write_text(
            (FIXTURES / "transcript.md").read_text(encoding="utf-8"),
            encoding="utf-8")
    return adir


def page(run: Path) -> dict:
    return dashboard_data.transcript_data(run, S, 1, limit=400)


class EachStateReadsThroughEveryEntryPoint(TempCase):

    def test_a_finished_attempt_prefers_the_workers_copy(self):
        run = self.tmp / "finished"
        a_run(run, events("single-events.ndjson"), state="finished",
              transcript=True)
        code, lines = call("transcript", "--run", run, "--step", "s", "--html")
        self.assertEqual((code, Path(lines[0]).name), (0, "transcript.md"), lines)
        code, lines = call("actions", "--run", run, "--step", "s")
        self.assertEqual(code, 0, lines)
        self.assertTrue(lines[0].startswith(
            "ACTIONS 01.work/01.s attempt 1: 6 model calls, 6 actions, "
            "0 failed; tokens in 16717 out 390 (pi-cloud)"), lines[0])
        view = actions.actions_data(run, "s")
        self.assertEqual(view["totals"]["tokens_source"],
                         "the transcript's own total")
        self.assertEqual(view["totals"]["pending"], 0)
        self.assertEqual(view["source"]["path"],
                         "phases/01.work/01.s/attempts/01/logs/pi-cloud-events.jsonl")
        self.assertTrue(page(run)["complete"])

    def test_a_running_attempt_reads_its_event_log_so_far(self):
        run = self.tmp / "running"
        a_run(run, events("cut-first.ndjson"), state="running")
        code, lines = call("transcript", "--run", run, "--step", "s", "--html")
        self.assertEqual((code, Path(lines[0]).name),
                         (0, pi_cloud_runner.EVENT_LOG), lines)
        view = actions.actions_data(run, "s")
        self.assertEqual(view["attempt"]["status"], "running")
        self.assertEqual((view["totals"]["calls"], view["totals"]["actions"],
                          view["totals"]["pending"]), (2, 2, 1))
        self.assertEqual(view["totals"]["tokens_source"], "the sum of the calls")
        block = page(run)
        self.assertFalse(block["complete"])
        self.assertEqual([r["type"] for r in block["records"]],
                         ["pi_cloud_start", "message", "tool_started",
                          "tool_result", "message", "tool_started"])

    def test_a_killed_attempt_shows_what_its_event_log_holds(self):
        run = self.tmp / "killed"
        a_run(run, events("cut-first.ndjson"), state="killed")
        code, lines = call("transcript", "--run", run, "--step", "s", "--html")
        self.assertEqual((code, Path(lines[0]).name),
                         (0, pi_cloud_runner.EVENT_LOG), lines)
        code, lines = call("actions", "--run", run, "--step", "s")
        self.assertEqual(code, 0, lines)
        self.assertIn("2 model calls, 2 actions, 0 failed", lines[0])
        self.assertIn("-> pending", lines[-1])
        block = page(run)
        self.assertTrue(block["complete"])
        call_ids = [b["call_id"] for r in block["records"]
                    for b in r["blocks"] if b["type"] == "tool_call"]
        result_ids = [r["tool_call_id"] for r in block["records"]
                      if r["type"] == "tool_result"]
        self.assertEqual(result_ids, call_ids[:1])

    def test_an_attempt_without_an_event_log_says_why(self):
        run = self.tmp / "bare"
        adir = a_run(run, [], state="killed")
        (adir / "logs" / pi_cloud_runner.EVENT_LOG).unlink()
        code, lines = call("transcript", "--run", run, "--step", "s", "--html")
        self.assertEqual(code, 1)
        self.assertIn("no logs/pi-cloud-events.jsonl", lines[0])
        code, lines = call("actions", "--run", run, "--step", "s")
        self.assertEqual((code, len(lines)), (1, 1), lines)
        self.assertIn("no pi-cloud-events.jsonl", lines[0])


class AReplayedEventCountsOnce(TempCase):

    def test_actions_count_each_call_and_action_once(self):
        run = self.tmp / "replayed"
        a_run(run, replayed_log(), state="finished")
        once = self.tmp / "once"
        a_run(once, events("single-events.ndjson"), state="finished")
        twice, single = actions.actions_data(run, "s"), actions.actions_data(once, "s")
        self.assertEqual(twice["totals"], single["totals"])
        self.assertEqual(len(twice["calls"]), 6)
        live = len(events("single-events.ndjson", drop=("pi_cloud_end",)))
        self.assertTrue(all(c["evidence"]["line"] <= live
                            for c in twice["calls"]), twice["calls"])
        self.assertEqual([a["summary"] for c in twice["calls"]
                          for a in c["actions"]],
                         [a["summary"] for c in single["calls"]
                          for a in c["actions"]])

    def test_a_replayed_call_keeps_the_messages_clock(self):
        run = self.tmp / "replay-only"
        a_run(run, events("replay-events.ndjson"), state="finished")
        first = actions.actions_data(run, "s")["calls"][0]
        self.assertEqual(first["latency_s"], 4.7)
        self.assertIsNone(first["actions"][0]["duration_s"])
        self.assertEqual(first["at"], 1793018112.156)

    def test_the_dashboard_shows_each_record_once_on_every_page(self):
        run = self.tmp / "replayed"
        a_run(run, replayed_log(), state="finished")
        once = self.tmp / "once"
        a_run(once, events("single-events.ndjson"), state="finished")
        shape = [(r["type"], r.get("tool_call_id"))
                 for r in page(once)["records"]]
        paged, cursor = [], None
        while True:
            block = dashboard_data.transcript_data(run, S, 1, cursor=cursor,
                                                   limit=4)
            paged += [(r["type"], r.get("tool_call_id"))
                      for r in block["records"]]
            if not block["has_more"]:
                break
            cursor = block["next_cursor"]
        self.assertEqual(paged, shape)
        self.assertEqual(sum(1 for kind, _ in paged if kind == "message"), 6)

    def test_the_activity_panel_counts_each_model_call_once(self):
        run = self.tmp / "replayed"
        adir = a_run(run, replayed_log(), state="running")
        view = pi_cloud_runner.activity(adir, running=True)
        self.assertEqual(view["llm_calls"], 6)
        self.assertEqual(len(view["tool_calls"]), 6)

    def test_the_line_scan_reads_on_and_starts_over_on_a_rewrite(self):
        path = self.tmp / "events.jsonl"
        lines = replayed_log()
        half = len(events("single-events.ndjson", drop=("pi_cloud_end",)))
        path.write_text("".join(line + "\n" for line in lines[:half]),
                        encoding="utf-8")
        self.assertEqual(pi_cloud_runner.replayed_lines(path), frozenset())
        with path.open("a", encoding="utf-8") as fh:
            fh.write("".join(line + "\n" for line in lines[half:]))
        repeats = pi_cloud_runner.replayed_lines(path)
        self.assertEqual(len(repeats), half - 1)
        path.write_text("".join(line + "\n" for line in
                                events("replay-events.ndjson")),
                        encoding="utf-8")
        self.assertEqual(pi_cloud_runner.replayed_lines(path), frozenset())

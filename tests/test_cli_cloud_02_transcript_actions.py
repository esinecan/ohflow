"""`ohflow transcript`, `ohflow actions` and the dashboard read a cloud CLI attempt.

What went wrong. On 22.11.2026 the killed codex-cloud attempt of run
`r-20261122-102406-5d5f369e` and the killed claude-cloud attempt of
`r-20261122-102711-d800377e` held `logs/codex-cloud-events.jsonl` and
`logs/claude-cloud-events.jsonl`, and still `actions` answered "no actions
reader for harness executor 'codex-cloud'" and the dashboard answered
"harness executor 'claude-cloud' has no transcript reader here": the
readers covered pi, claude, codex and pi-cloud only, and `transcript`
wanted the `transcript.md` a killed runner never copies down.

What is asserted here. A running, a finished and a killed attempt of each
cloud CLI executor answers all three entry points from its event log, a
finished one's `transcript` prefers the Worker's own copy, and a log that
holds a replay of its own stream counts each model call, action and record
once. A killed attempt's dashboard record for a tool start carries the call
as a `tool_call` block, so the page names the tool and its arguments. The cloud CLI streams pi's event shapes in the CLI's own order: the
tool executions arrive as they run and the assistant messages arrive when
the session settles, so a message claims the actions its toolCall ids
already name. The event lines are slices of the runs of 15.11 and
22.11.2026 (`tests/fixtures/cli_cloud`).
"""

from __future__ import annotations

import json
from pathlib import Path

from dashboard_support import RunLog, agent, mark_alive, workflow_json
from ohflow import actions, dashboard_data, pi_cloud_runner, rundir
from support import TempCase
from verb_support import call

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "cli_cloud"
S = "01.work/01.s"
LOGS = {"codex-cloud": "codex-cloud-events.jsonl",
        "claude-cloud": "claude-cloud-events.jsonl"}
SLICES = {"codex-cloud": "codex-cloud-events.ndjson",
          "claude-cloud": "claude-cloud-events.ndjson"}
KILLED = {"codex-cloud": "codex-cloud-killed-events.ndjson",
          "claude-cloud": "claude-cloud-killed-events.ndjson"}
REPLAY_T = 1795000000000
STARTED = {
    "codex-cloud": ("item_0", "shell",
                    {"command": "/bin/sh -lc 'sleep 900'"}),
    "claude-cloud": ("toolu_01Ck8izz9xxG1Et3r9HiXJgg", "Bash",
                     {"command": "sleep 900", "timeout": 1000000}),
}


def events(name: str, *, drop: tuple[str, ...] = ()) -> list[str]:
    lines = (FIXTURES / name).read_text(encoding="utf-8").splitlines()
    return [line for line in lines
            if json.loads(line).get("type") not in drop]


def _marked_replay(name: str) -> list[str]:
    """The Worker's events as a reattached runner received them: the same
    records, marked replayed and stamped with the replay's clock."""
    again = events(name, drop=("pi_cloud_start", "pi_cloud_container",
                               "pi_cloud_end"))
    ends = {str(json.loads(line).get("toolCallId")):
            json.loads(line).get("entryId")
            for line in again
            if json.loads(line).get("type") == "tool_execution_end"}
    marked = []
    for line in again:
        rec = json.loads(line)
        rec["replayed"] = True
        rec["t"] = REPLAY_T
        if rec.get("type") == "tool_execution_start":
            rec["entryId"] = ends.get(str(rec.get("toolCallId")))
        marked.append(json.dumps(rec, separators=(",", ":")))
    return marked


def _end_line(name: str) -> list[str]:
    return [line for line in events(name)
            if json.loads(line).get("type") == "pi_cloud_end"]


def replayed_log(name: str) -> list[str]:
    """A stream written live, then written again by a runner that reattached,
    as a client that lost its seen set would have received it."""
    return (events(name, drop=("pi_cloud_end",))
            + _marked_replay(name) + _end_line(name))


def replayed_only(name: str) -> list[str]:
    """The whole conversation as a reattached runner received it, after the
    first runner died before any of the Worker's events reached it."""
    return (events(name, drop=("message_end", "tool_execution_start",
                               "tool_execution_end", "pi_cloud_end"))
            + _marked_replay(name) + _end_line(name))


def a_run(run: Path, harness: str, lines: list[str], *, state: str,
          transcript: bool = False) -> Path:
    workflow_json(run, [("Work", [agent("s", harness_executor=harness)], 1)])
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
    (adir / "logs" / LOGS[harness]).write_text(
        "".join(line + "\n" for line in lines), encoding="utf-8")
    if transcript:
        (adir / "transcript.md").write_text(
            (FIXTURES / f"{harness}-transcript.md").read_text(
                encoding="utf-8"), encoding="utf-8")
    return adir


def page(run: Path) -> dict:
    return dashboard_data.transcript_data(run, S, 1, limit=400)


class EachStateReadsThroughEveryEntryPoint(TempCase):

    def test_a_finished_attempt_prefers_the_workers_copy(self):
        for harness in LOGS:
            with self.subTest(harness_executor=harness):
                run = self.tmp / f"finished-{harness}"
                a_run(run, harness, events(SLICES[harness]), state="finished",
                      transcript=True)
                code, lines = call("transcript", "--run", run, "--step", "s",
                                   "--html")
                self.assertEqual((code, Path(lines[0]).name),
                                 (0, "transcript.md"), lines)
                code, lines = call("actions", "--run", run, "--step", "s")
                self.assertEqual(code, 0, lines)
                head, unit, calls, tokens = {
                    "codex-cloud": ("ACTIONS 01.work/01.s attempt 1: 1 turn, "
                                    "3 actions, 0 failed; tokens in 404556 "
                                    "out 3361 (codex-cloud)", "turn", 1,
                                    (404556, 3361)),
                    "claude-cloud": ("ACTIONS 01.work/01.s attempt 1: "
                                     "3 model calls, 3 actions, 0 failed; "
                                     "tokens in 273 out 6185 (claude-cloud)",
                                     "model call", 3, (273, 6185)),
                }[harness]
                self.assertTrue(lines[0].startswith(head), lines[0])
                view = actions.actions_data(run, "s")
                self.assertEqual(view["source"]["unit"], unit)
                self.assertEqual(len(view["calls"]), calls)
                self.assertEqual(view["totals"]["tokens_source"],
                                 "the transcript's own total")
                self.assertEqual((view["totals"]["tokens"]["prompt"],
                                  view["totals"]["tokens"]["output"]), tokens)
                self.assertEqual(view["totals"]["pending"], 0)
                self.assertEqual(
                    view["source"]["path"],
                    f"phases/01.work/01.s/attempts/01/logs/{LOGS[harness]}")
                self.assertTrue(page(run)["complete"])

    def test_a_running_attempt_reads_its_event_log_so_far(self):
        for harness in LOGS:
            with self.subTest(harness_executor=harness):
                run = self.tmp / f"running-{harness}"
                a_run(run, harness,
                      events(SLICES[harness],
                             drop=("message_end", "pi_cloud_end")),
                      state="running")
                code, lines = call("transcript", "--run", run, "--step", "s",
                                   "--html")
                self.assertEqual((code, Path(lines[0]).name),
                                 (0, LOGS[harness]), lines)
                code, lines = call("actions", "--run", run, "--step", "s")
                self.assertEqual(code, 0, lines)
                self.assertIn("3 actions, 0 failed", lines[0])
                view = actions.actions_data(run, "s")
                self.assertEqual(view["attempt"]["status"], "running")
                self.assertEqual((view["totals"]["calls"],
                                  view["totals"]["actions"],
                                  view["totals"]["pending"]), (1, 3, 0))
                self.assertEqual(view["totals"]["tokens"], None)
                self.assertEqual(view["totals"]["tokens_source"],
                                 "the sum of the calls")
                block = page(run)
                self.assertFalse(block["complete"])
                self.assertEqual(
                    [r["type"] for r in block["records"]],
                    ["pi_cloud_start", "pi_cloud_container",
                     "tool_started", "tool_result",
                     "tool_started", "tool_result",
                     "tool_started", "tool_result"])

    def test_a_killed_attempt_shows_what_its_event_log_holds(self):
        for harness in KILLED:
            with self.subTest(harness_executor=harness):
                run = self.tmp / f"killed-{harness}"
                a_run(run, harness, events(KILLED[harness]), state="killed")
                code, lines = call("transcript", "--run", run, "--step", "s",
                                   "--html")
                self.assertEqual((code, Path(lines[0]).name),
                                 (0, LOGS[harness]), lines)
                code, lines = call("actions", "--run", run, "--step", "s")
                self.assertEqual(code, 0, lines)
                self.assertIn("1 action", lines[0])
                self.assertIn("-> pending", lines[-1])
                view = actions.actions_data(run, "s")
                self.assertEqual((view["totals"]["calls"],
                                  view["totals"]["actions"],
                                  view["totals"]["pending"]), (1, 1, 1))
                block = page(run)
                self.assertTrue(block["complete"])
                self.assertEqual([r["type"] for r in block["records"]],
                                 ["pi_cloud_start", "pi_cloud_container",
                                  "tool_started"])
                started = next(r for r in block["records"]
                               if r["type"] == "tool_started")
                call_id, name, args = STARTED[harness]
                self.assertEqual(
                    started["blocks"],
                    [{"type": "tool_call", "call_id": call_id,
                      "name": name, "input": args}])
                self.assertEqual(started["tool_name"], name)

    def test_an_attempt_without_an_event_log_says_why(self):
        for harness in LOGS:
            with self.subTest(harness_executor=harness):
                run = self.tmp / f"bare-{harness}"
                adir = a_run(run, harness, [], state="killed")
                (adir / "logs" / LOGS[harness]).unlink()
                code, lines = call("transcript", "--run", run, "--step", "s",
                                   "--html")
                self.assertEqual(code, 1)
                self.assertIn(f"no logs/{LOGS[harness]}", lines[0])
                code, lines = call("actions", "--run", run, "--step", "s")
                self.assertEqual((code, len(lines)), (1, 1), lines)
                self.assertIn(f"no {LOGS[harness]}", lines[0])


class AReplayedEventCountsOnce(TempCase):

    def test_actions_count_each_call_and_action_once(self):
        for harness in LOGS:
            with self.subTest(harness_executor=harness):
                run = self.tmp / f"replayed-{harness}"
                a_run(run, harness, replayed_log(SLICES[harness]),
                      state="finished")
                once = self.tmp / f"once-{harness}"
                a_run(once, harness, events(SLICES[harness]), state="finished")
                twice = actions.actions_data(run, "s")
                single = actions.actions_data(once, "s")
                self.assertEqual(twice["totals"], single["totals"])
                self.assertEqual(len(twice["calls"]), len(single["calls"]))
                live = len(events(SLICES[harness], drop=("pi_cloud_end",)))
                self.assertTrue(all(c["evidence"]["line"] <= live
                                    for c in twice["calls"]), twice["calls"])
                self.assertEqual(
                    [a["summary"] for c in twice["calls"]
                     for a in c["actions"]],
                    [a["summary"] for c in single["calls"]
                     for a in c["actions"]])

    def test_the_dashboard_shows_each_record_once_on_every_page(self):
        for harness in LOGS:
            with self.subTest(harness_executor=harness):
                run = self.tmp / f"replayed-{harness}"
                a_run(run, harness, replayed_log(SLICES[harness]),
                      state="finished")
                once = self.tmp / f"once-{harness}"
                a_run(once, harness, events(SLICES[harness]), state="finished")
                shape = [(r["type"], r.get("tool_call_id"))
                         for r in page(once)["records"]]
                paged, cursor = [], None
                while True:
                    block = dashboard_data.transcript_data(
                        run, S, 1, cursor=cursor, limit=4)
                    paged += [(r["type"], r.get("tool_call_id"))
                              for r in block["records"]]
                    if not block["has_more"]:
                        break
                    cursor = block["next_cursor"]
                self.assertEqual(paged, shape)
                messages = (1 if harness == "codex-cloud" else 3)
                self.assertEqual(
                    sum(1 for kind, _ in paged if kind == "message"), messages)

    def test_a_replayed_call_keeps_the_messages_clock(self):
        for harness, first_at in (("codex-cloud", 1794762457.649),
                                  ("claude-cloud", 1794762654.514)):
            with self.subTest(harness_executor=harness):
                run = self.tmp / f"replay-only-{harness}"
                a_run(run, harness, replayed_only(SLICES[harness]),
                      state="finished")
                view = actions.actions_data(run, "s")
                first = view["calls"][0]
                self.assertEqual(first["at"], first_at)
                self.assertIsNone(first["actions"][0]["duration_s"])
                self.assertEqual(first["actions"][0]["at"], first_at)

    def test_the_line_scan_marks_the_replayed_lines(self):
        for harness in LOGS:
            with self.subTest(harness_executor=harness):
                path = self.tmp / f"{harness}-events.jsonl"
                lines = replayed_log(SLICES[harness])
                live = len(events(SLICES[harness], drop=("pi_cloud_end",)))
                path.write_text("".join(line + "\n" for line in lines[:live]),
                                encoding="utf-8")
                self.assertEqual(pi_cloud_runner.replayed_lines(path),
                                 frozenset())
                with path.open("a", encoding="utf-8") as fh:
                    fh.write("".join(line + "\n" for line in lines[live:]))
                repeats = pi_cloud_runner.replayed_lines(path)
                self.assertEqual(len(repeats),
                                 len(lines) - live - 1)
                path.write_text("".join(line + "\n" for line in
                                        events(SLICES[harness])),
                                encoding="utf-8")
                self.assertEqual(pi_cloud_runner.replayed_lines(path),
                                 frozenset())

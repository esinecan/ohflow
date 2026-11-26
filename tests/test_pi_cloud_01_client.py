"""The pi-cloud client: reconnect, dedup, beats, the lost bound and the 4xx line.

The real `pi_cloud_client.py` runs as a child process against the fake Worker
(`tests/fakes/fake_pi_cloud.py`), which replays the recordings taken from the
real one. What is proved:

- R3: a dropped stream reconnects inside the same client process, and no
  `entryId` and no tool-call start reaches stdout twice (the `cut` recording:
  six lines, a close, then the replay plus the live continuation);
- a beat never reaches stdout, on a whole step and on a settled replay;
- F1: the lost clock counts from the last contact, so beats for longer than
  the bound keep the client alive to the end line; and a stream that drops
  after them exits 3 only once the bound has passed with no line and no
  opened response (F1 and R4), then reconnects like any other drop when the
  reconnect is served (F2 and R3);
- the lost bound: no successful connection for `OHFLOW_PI_CLOUD_LOST_S`
  seconds exits 3 with a stderr reason and no stdout line;
- an HTTP 401 becomes one `pi_cloud_error` line naming the status, and exit 1;
- both headers ride every request, and the token reaches no argv, no stdout
  and no stderr (R9).
"""

from __future__ import annotations

import json
import time

from ohflow import remote_git
from pi_cloud_support import TOKEN, PiCloudCase

#: One hold's shape in these tests: beats for 3 s - longer than the 2 s lost
#: bound the tests set - close enough to each other (0.5 s) that the read
#: never times out.
HOLD = {"hold_s": 3.0, "beat_s": 0.5}
LOST = "2"
RETRY = "0.2"


def lines_of(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


class ClientCase(PiCloudCase):

    def _prepare(self, key: str, behaviours: list) -> str:
        """Push the branch a launch would push, post `step`, plan the stream."""
        branch = self.branch_for(key)
        start = remote_git.push_start(self.repo, branch)
        answer = self.post_step(key, branch, start)
        self.assertEqual(answer["accepted"], True)
        self.worker.plan(key, 1, behaviours)
        return start

    def test_a_dropped_stream_reconnects_and_prints_nothing_twice(self):
        key = "cut-1"
        self._prepare(key, ["cut-first", "cut-second"])
        done = self.run_client(key, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        events = lines_of(done.stdout)
        self.assertTrue(events, "the client printed nothing")
        self.assertEqual(events[-1]["type"], "pi_cloud_end")
        self.assertEqual(events[-1]["status"], "done")
        # R3: no entryId twice, no tool-call start twice, no beat at all.
        entry_ids = [e.get("entryId") for e in events
                     if e.get("type") in ("message_end", "tool_execution_end")
                     and e.get("entryId") is not None]
        self.assertEqual(len(entry_ids), len(set(entry_ids)), entry_ids)
        starts = [e.get("toolCallId") for e in events
                  if e.get("type") == "tool_execution_start"]
        self.assertEqual(len(starts), len(set(starts)), starts)
        self.assertNotIn("pi_cloud_beat", [e.get("type") for e in events])
        # The first connection's six lines and the second's continuation are
        # both there: the whole conversation, each part once. One start line
        # per connection is expected - the dedup rules cover entries and
        # tool-call starts, and the runner reads the last start line.
        kinds = [e.get("type") for e in events]
        self.assertEqual(kinds.count("pi_cloud_start"), 2)
        self.assertEqual(kinds.count("message_end"), 9)

    def test_beats_never_reach_stdout_on_a_whole_step(self):
        key = "beat-1"
        self._prepare(key, ["success"])
        done = self.run_client(key, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        kinds = [e.get("type") for e in lines_of(done.stdout)]
        self.assertNotIn("pi_cloud_beat", kinds)
        self.assertEqual(kinds[0], "pi_cloud_start")

    def test_a_settled_operation_replays_and_ends_at_once(self):
        key = "settled-1"
        self._prepare(key, ["settled"])
        done = self.run_client(key, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        events = lines_of(done.stdout)
        self.assertEqual(events[-1]["type"], "pi_cloud_end")
        self.assertEqual([e.get("replayed") for e in events[1:-1]],
                         [True] * (len(events) - 2))

    def test_no_worker_for_the_lost_bound_exits_three_with_no_stdout(self):
        key = "lost-1"
        self._prepare(key, ["refuse"])
        done = self.run_client(key, timeout=60, env={
            "OHFLOW_PI_CLOUD_LOST_S": "2", "OHFLOW_PI_CLOUD_RETRY_S": "0.2"})
        self.assertEqual(done.returncode, 3)
        self.assertEqual(done.stdout, "")
        self.assertIn("no line and no opened response", done.stderr)
        self.assertIn(key, done.stderr)
        # Every events connection was refused outright; none succeeded.
        refused = [r for r in self.worker.requests
                   if "/events" in r["path"]]
        self.assertGreater(len(refused), 3)

    def test_f1_beats_longer_than_the_lost_bound_keep_the_client_alive(self):
        key = "f1-alive"
        # One connection: the start line, beats for 3 s - longer than the 2 s
        # bound - then the whole recording, ended `done` on the same stream.
        self._prepare(key, [{**HOLD, "then": "single-events"}])
        started = time.time()
        done = self.run_client(key, timeout=60, env={
            "OHFLOW_PI_CLOUD_LOST_S": LOST, "OHFLOW_PI_CLOUD_RETRY_S": RETRY})
        elapsed = time.time() - started
        self.assertEqual(done.returncode, 0, done.stderr)
        events = lines_of(done.stdout)
        self.assertEqual(events[-1]["type"], "pi_cloud_end")
        self.assertEqual(events[-1]["status"], "done")
        kinds = [e.get("type") for e in events]
        self.assertNotIn("pi_cloud_beat", kinds)
        # The beats were really written for longer than the bound, and the
        # client read them all and stayed alive to the end line (F1).
        held = [b for b in self.worker.beats if b["key"] == key]
        self.assertGreater(len(held), 3)
        self.assertGreaterEqual(elapsed, HOLD["hold_s"])

    def test_f1_and_r4_lines_longer_than_the_bound_then_refused_exits_three_late(self):
        key = "f1-lost"
        self._prepare(key, [HOLD, "refuse"])
        started = time.time()
        done = self.run_client(key, timeout=60, env={
            "OHFLOW_PI_CLOUD_LOST_S": LOST, "OHFLOW_PI_CLOUD_RETRY_S": RETRY})
        finished = time.time()
        self.assertEqual(done.returncode, 3)
        kinds = [e.get("type") for e in lines_of(done.stdout)]
        self.assertEqual(kinds, ["pi_cloud_start"])
        self.assertIn("no line and no opened response", done.stderr)
        self.assertIn(key, done.stderr)
        # The hold outlived the bound, so a clock that counted from the opened
        # response would exit here at once. The exit came only after the bound
        # had passed with no line at all: at least LOST s after the last beat.
        last_beat = max(b["at"] for b in self.worker.beats
                        if b["key"] == key)
        self.assertGreaterEqual(finished - last_beat, float(LOST) - 0.4)
        refused = [r for r in self.worker.requests if "/events" in r["path"]]
        self.assertGreater(len(refused), 3)

    def test_f2_and_r3_a_healthy_stream_past_the_bound_drops_and_the_reconnect_serves_the_rest(self):
        key = "f2-cut"
        # The first connection carries the `cut-first` prefix, then beats for
        # 3 s - longer than the 2 s bound - then closes; the reconnect is the
        # ordinary `cut-second` replay-and-continuation.
        self._prepare(key, [{**HOLD, "prefix": "cut-first"}, "cut-second"])
        started = time.time()
        done = self.run_client(key, timeout=60, env={
            "OHFLOW_PI_CLOUD_LOST_S": LOST, "OHFLOW_PI_CLOUD_RETRY_S": RETRY})
        elapsed = time.time() - started
        self.assertEqual(done.returncode, 0, done.stderr)
        events = lines_of(done.stdout)
        self.assertTrue(events, "the client printed nothing")
        self.assertEqual(events[-1]["type"], "pi_cloud_end")
        self.assertEqual(events[-1]["status"], "done")
        # The stream really outlived the bound, and the drop reconnected like
        # any other: every entry once, no beat printed (F2 and R3).
        self.assertGreaterEqual(elapsed, HOLD["hold_s"])
        entry_ids = [e.get("entryId") for e in events
                     if e.get("type") in ("message_end", "tool_execution_end")
                     and e.get("entryId") is not None]
        self.assertEqual(len(entry_ids), len(set(entry_ids)), entry_ids)
        starts = [e.get("toolCallId") for e in events
                  if e.get("type") == "tool_execution_start"]
        self.assertEqual(len(starts), len(set(starts)), starts)
        kinds = [e.get("type") for e in events]
        self.assertNotIn("pi_cloud_beat", kinds)
        self.assertEqual(kinds.count("pi_cloud_start"), 2)
        self.assertEqual(kinds.count("message_end"), 9)

    def test_an_unauthorized_stream_prints_the_fourxx_line_and_exits_one(self):
        key = "auth-1"
        self._prepare(key, ["unauthorized"])
        done = self.run_client(key, timeout=60)
        self.assertEqual(done.returncode, 1, done.stderr)
        [line] = lines_of(done.stdout)
        self.assertEqual(line["type"], "pi_cloud_error")
        self.assertEqual(line["name"], "HTTPError")
        self.assertIn("HTTP 401", line["message"])
        self.assertIn("unauthorized", line["message"])

    def test_an_unset_token_exits_two_naming_the_variable(self):
        key = "token-1"
        self._prepare(key, ["success"])
        done = self.run_client(key, timeout=30, env={"PI_CLOUD_TOKEN": ""})
        self.assertEqual(done.returncode, 2)
        self.assertIn("PI_CLOUD_TOKEN", done.stderr)
        self.assertEqual(done.stdout, "")

    def test_every_request_carries_both_headers(self):
        key = "headers-1"
        self._prepare(key, ["success"])
        done = self.run_client(key, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        made = [r for r in self.worker.requests if r["path"] != "/"]
        self.assertGreaterEqual(len(made), 2)
        for request in made:
            self.assertTrue(request["auth"], request)
            self.assertEqual(request["user_agent"], "ohflow-pi-cloud/1")

    def test_the_token_reaches_no_stdout_stderr_or_request_url(self):
        runs = []
        for key, behaviours, env in (
                ("r9-cut", ["cut-first", "cut-second"], None),
                ("r9-lost", ["refuse"], {"OHFLOW_PI_CLOUD_LOST_S": "2",
                                         "OHFLOW_PI_CLOUD_RETRY_S": "0.2"}),
                ("r9-auth", ["unauthorized"], None)):
            self._prepare(key, behaviours)
            runs.append(self.run_client(key, timeout=60, env=env))
        for done in runs:
            self.assertNotIn(TOKEN, done.stdout)
            self.assertNotIn(TOKEN, done.stderr)
        for request in self.worker.requests:
            self.assertNotIn(TOKEN, request["path"])
            if isinstance(request["body"], dict):
                self.assertNotIn(TOKEN, json.dumps(request["body"]))

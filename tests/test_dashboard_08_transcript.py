"""`/api/transcript`: the full readable transcript of one attempt, paged.

The real packet proves paging and pairing at recorded scale (attempt 4 of the
implement step: 100 records, 21 tool calls, all matched with results). A
minimal packet fixture proves the cursor mechanics: appends add no duplicates,
a truncated or replaced file resets, a torn final line waits for its writer,
malformed lines are named, and secrets are redacted before anything leaves.
The current formats - pi session, claude and codex event logs, a command
step's out log - are
each read through their own adapter, and an attempt with nothing readable says
so in diagnostics instead of posing as an empty success.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from dashboard_support import RunLog, agent, command, \
    copy_tree, workflow_json
from support import TempCase

from ohflow import dashboard, dashboard_data

HERE = Path(__file__).resolve().parent
PACKET = HERE / "fixtures" / "dashboard-basis"
IMPL = "01.implement/01.implement"
REVIEW = "02.review/01.review"

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def get(url: str, **kwargs):
    req = urllib.request.Request(url, **kwargs)
    try:
        with OPENER.open(req, timeout=10) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def http_page_all(base: str, coord: str, attempt: int,
                  limit: int = 400):
    """Read and losslessly reassemble every logical record through HTTP."""
    records, pages = [], []
    cursor = None
    chunks: dict[str, list[str]] = {}
    while True:
        query = {"coord": coord, "attempt": attempt, "limit": limit}
        if cursor is not None:
            query["cursor"] = cursor
        status, body = get(base + "/api/transcript?"
                           + urllib.parse.urlencode(query))
        if status != 200:
            raise AssertionError(f"transcript HTTP status {status}: {body!r}")
        page = json.loads(body)
        pages.append(page)
        for record in page["records"]:
            part = record.get("continuation")
            if part:
                record_id = part["record_id"]
                chunks.setdefault(record_id, []).append(part["data"])
                if part["complete"]:
                    records.append(json.loads("".join(chunks.pop(record_id))))
            else:
                records.append(record)
        if not page["has_more"]:
            return records, pages
        cursor = page["next_cursor"]


def page_all(run_dir: Path, coord: str, attempt: int, limit: int = 37):
    records, cursors, pages = [], [], []
    cursor = None
    while True:
        block = dashboard_data.transcript_data(run_dir, coord, attempt,
                                               cursor=cursor, limit=limit)
        records.extend(block["records"])
        cursors.append(block["next_cursor"])
        pages.append(block)
        if not block["has_more"]:
            return records, cursors, pages
        cursor = block["next_cursor"]


def make_packet(tmp: Path, *, records=None, records_text=None) -> Path:
    """A minimal but complete `ohflow.dashboard-case/1` packet."""
    root = tmp / "packet-case"
    attempt_dir = root / "transcripts" / "worker-att01"
    attempt_dir.mkdir(parents=True)
    if records_text is not None:
        (attempt_dir / "transcript.jsonl").write_text(records_text,
                                                      encoding="utf-8")
        count = len([l for l in records_text.splitlines() if l.strip()])
    else:
        records = records if records is not None else []
        (attempt_dir / "transcript.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
        count = len(records)
    case = {
        "schema": "ohflow.dashboard-case/1",
        "generated_at": "2026-10-06T21:14:48Z",
        "canonical_run": {"id": "packet-fixture", "plan": "pkt",
                          "status": "finished",
                          "started": "2026-10-01T21:48:35Z",
                          "finished": "2026-10-02T04:32:28Z"},
        "phases": [{"id": "01.p", "name": "P", "policy": "abort",
                    "min_success": "all", "max_parallel": 1, "depends_on": [],
                    "steps": ["01.p/01.worker"], "final_status": "passed"}],
        "steps": [{"coord": "01.p/01.worker", "phase": "01.p", "id": "worker",
                   "kind": "worker", "role": "worker", "lane": "claude",
                   "model": "claude-sonnet-5-5", "depends_on": [],
                   "owns": [], "retry_policy": {"max": 0, "on": []},
                   "gate_checks": ["tree_clean"]}],
        "attempts": [{
            "coord": "01.p/01.worker", "attempt": 1, "start_kind": "initial",
            "fingerprint": "fp",
            "started": {"path": "journal.jsonl", "line": 4,
                        "type": "step_started", "ts": "2026-10-01T21:48:37Z"},
            "status": "passed",
            "finished": {"path": "journal.jsonl", "line": 6,
                         "type": "step_finished",
                         "ts": "2026-10-01T22:40:31Z"},
            "gate_passed": True, "failed_checks": [], "wall_seconds": 10.0,
            "transcript": {"jsonl": "packet:transcripts/worker-att01/"
                                    "transcript.jsonl",
                           "records": count},
        }],
        "counts": {}, "totals": {}, "known_holes": [],
    }
    (root / "case.json").write_text(json.dumps(case), encoding="utf-8")
    events = [
        {"n": 1, "ts": "2026-10-01T21:48:35Z",
         "original": {"path": "journal.jsonl", "line": 1,
                      "type": "run_started"},
         "type": "run.started", "coord": None, "attempt": None,
         "payload": {"run_id": "packet-fixture"}},
        {"n": 4, "ts": "2026-10-01T21:48:37Z",
         "original": {"path": "journal.jsonl", "line": 4,
                      "type": "step_started"},
         "type": "attempt.started", "coord": "01.p/01.worker", "attempt": 1,
         "payload": {"start_kind": "initial"}},
        {"n": 6, "ts": "2026-10-01T22:40:31Z",
         "original": {"path": "journal.jsonl", "line": 6,
                      "type": "step_finished"},
         "type": "attempt.finished", "coord": "01.p/01.worker", "attempt": 1,
         "payload": {"status": "passed"}},
    ]
    (root / "events.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    return root


def claude_records():
    """A claude event stream with a call, its result, and a null timestamp."""
    return [
        {"type": "system", "subtype": "init", "session_id": "s1",
         "cwd": str(PACKET)},
        {"type": "assistant", "timestamp": "2026-10-02T02:39:28.031Z",
         "message": {"model": "claude-sonnet-5-5", "content": [
             {"type": "tool_use", "id": "toolu_1", "name": "Read",
              "input": {"file_path": "brief.md"}}]}},
        {"type": "user", "timestamp": "2026-10-02T02:39:28.188Z",
         "message": {"content": [
             {"type": "tool_result", "tool_use_id": "toolu_1",
              "is_error": False, "content": "brief text"}]}},
        {"type": "result", "stop_reason": "end_turn",
         "result": "done"},
    ]


def current_run(tmp: Path, *, harness_executor: str = "claude") -> Path:
    """A current-format run with one finished agent attempt: the run dir."""
    run = tmp / f"run-{harness_executor}"
    workflow_json(run, [("Build", [agent("worker",
                                         harness_executor=harness_executor)],
                         1)])
    log = RunLog(run)
    log.phase(1, "01.build", "Build", ["01.build/01.worker"], 1)
    log.start(2, "01.build/01.worker", 1)
    log.finish(60, "01.build/01.worker", 1, "passed", wall=58.0)
    return run


def attempt_dir(run: Path) -> Path:
    return run / "phases" / "01.build" / "01.worker" / "attempts" / "01"


class PacketPaging(TempCase):

    def setUp(self):
        super().setUp()
        self.run = PACKET

    def test_paging_covers_every_record_exactly_once(self):
        records, cursors, pages = page_all(self.run, IMPL, 4, limit=37)
        self.assertEqual([len(p["records"]) for p in pages], [37, 37, 26])
        self.assertEqual([p["has_more"] for p in pages],
                         [True, True, False])
        self.assertEqual([p["complete"] for p in pages],
                         [False, False, True])
        ids = [r["id"] for r in records]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, sorted(ids, key=lambda x: int(x[1:])))
        self.assertEqual(len(records), 100)
        # The last page names the total; the earlier ones do not pretend to.
        self.assertEqual(pages[-1]["total"], 100)
        self.assertNotIn("total", pages[0])
        # Cursors are opaque: not the byte offset in plain text.
        self.assertNotIn(str(50148), cursors[0])

    def test_tool_calls_pair_with_results_across_page_boundaries(self):
        records, _c, _p = page_all(self.run, IMPL, 4)
        calls = {b["call_id"] for r in records for b in r.get("blocks", [])
                 if b.get("type") == "tool_call"}
        results = {b["call_id"] for r in records for b in r.get("blocks", [])
                   if b.get("type") == "tool_result"}
        self.assertEqual(len(calls), 21)
        self.assertEqual(calls, results)

    def test_pi_transcripts_pair_on_the_message_level(self):
        records, _c, _p = page_all(self.run, REVIEW, 4, limit=400)
        calls = {b["call_id"] for r in records for b in r.get("blocks", [])
                 if b.get("type") == "tool_call"}
        results = {r["tool_call_id"] for r in records
                   if r.get("type") == "tool_result"}
        self.assertTrue(calls)
        self.assertEqual(calls, results)

    def test_unknown_timestamps_stay_null(self):
        records, _c, _p = page_all(self.run, IMPL, 4)
        first = next(r for r in records if r["id"] == "L1")
        self.assertIsNone(first["ts"])
        nulls = [r for r in records if r["ts"] is None]
        self.assertGreater(len(nulls), 10)

    def test_records_carry_their_source(self):
        records, _c, _p = page_all(self.run, IMPL, 4, limit=5)
        source = records[0]["source"]
        self.assertEqual(source["path"],
                         "transcripts/implement-att04/transcript.jsonl")
        self.assertEqual(source["line"], 1)

    def test_a_cached_evaluation_has_no_transcript_and_says_so(self):
        block = dashboard_data.transcript_data(self.run, IMPL, 0)
        self.assertEqual(block["records"], [])
        self.assertFalse(block["complete"])
        self.assertTrue(any("cached" in d for d in block["diagnostics"]))

    def test_roles_and_reasoning_are_readable(self):
        records, _c, _p = page_all(self.run, IMPL, 4)
        roles = {r["role"] for r in records}
        self.assertIn("assistant", roles)
        self.assertIn("user", roles)
        thinking = [b for r in records for b in r.get("blocks", [])
                    if b.get("type") == "thinking"]
        self.assertGreater(len(thinking), 0)

    def test_real_long_record_is_preserved_without_the_old_string_cap(self):
        raw = (PACKET / "transcripts" / "implement-att04"
               / "transcript.jsonl").read_text(encoding="utf-8").splitlines()
        expected = json.loads(raw[3])["blocks"][0]["content"]
        records, _c, _p = page_all(self.run, IMPL, 4)
        actual = next(r for r in records if r["id"] == "L4")
        self.assertEqual(actual["blocks"][0]["content"], expected)
        self.assertGreater(len(expected), 15000)
        self.assertNotIn("capped at", json.dumps(actual))


class CursorMechanics(TempCase):
    """A small packet fixture the test may append to and truncate."""

    def setUp(self):
        super().setUp()
        # Four distinct records: one system, three messages.
        self.run = make_packet(self.tmp, records=[
            {"ts": None, "type": "system", "subtype": "init"},
            {"ts": "2026-10-01T21:48:38Z", "type": "message",
             "role": "assistant", "blocks": [{"type": "text", "text": "one"}]},
            {"ts": "2026-10-01T21:48:39Z", "type": "message",
             "role": "assistant", "blocks": [{"type": "text", "text": "two"}]},
            {"ts": "2026-10-01T21:48:40Z", "type": "message",
             "role": "assistant", "blocks": [{"type": "text", "text": "three"}]},
        ])
        self.path = (self.run / "transcripts" / "worker-att01"
                     / "transcript.jsonl")

    def test_an_append_is_picked_up_exactly_once(self):
        first = dashboard_data.transcript_data(self.run, "01.p/01.worker", 1,
                                               limit=2)
        self.assertEqual([r["id"] for r in first["records"]], ["L1", "L2"])
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(
                {"ts": "2026-10-01T21:48:41Z", "type": "message",
                 "role": "assistant",
                 "blocks": [{"type": "text", "text": "four"}]}) + "\n")
        second = dashboard_data.transcript_data(self.run, "01.p/01.worker", 1,
                                                cursor=first["next_cursor"],
                                                limit=10)
        # The earlier page's records are not repeated, and the appended one
        # appears exactly once.
        self.assertEqual([r["id"] for r in second["records"]],
                         ["L3", "L4", "L5"])
        self.assertFalse(second["reset"])
        self.assertFalse(second["has_more"])
        self.assertEqual(sum(1 for r in second["records"]
                             if r["id"] in ("L1", "L2")), 0)

    def test_a_torn_final_line_waits_for_its_writer(self):
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write('{"ts": null, "type": "message", "role": "assistant"')
        torn = dashboard_data.transcript_data(self.run, "01.p/01.worker", 1,
                                              limit=10)
        self.assertEqual(len(torn["records"]), 4)
        self.assertFalse(torn["has_more"])
        cursor = torn["next_cursor"]
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(', "blocks": [{"type": "text", "text": "done"}]}\n')
        done = dashboard_data.transcript_data(self.run, "01.p/01.worker", 1,
                                              cursor=cursor, limit=10)
        self.assertEqual([r["id"] for r in done["records"]], ["L5"])
        self.assertNotIn("done", json.dumps(torn["records"]))

    def test_a_truncated_file_resets_without_duplicates(self):
        first = dashboard_data.transcript_data(self.run, "01.p/01.worker", 1,
                                               limit=4)
        self.assertEqual(first["complete"], True)
        # The source is replaced by a shorter rewrite (a new attempt reading
        # its session from the top, a rotated log).
        self.path.write_text(json.dumps(
            {"ts": "2026-10-01T22:00:00Z", "type": "message",
             "role": "assistant",
             "blocks": [{"type": "text", "text": "rewritten"}]}) + "\n",
            encoding="utf-8")
        after = dashboard_data.transcript_data(self.run, "01.p/01.worker", 1,
                                               cursor=first["next_cursor"],
                                               limit=10)
        self.assertTrue(after["reset"])
        self.assertEqual([r["id"] for r in after["records"]], ["L1"])
        self.assertIn("rewritten", json.dumps(after["records"]))

    def test_equal_or_larger_replacement_resets_from_the_new_beginning(self):
        first = dashboard_data.transcript_data(self.run, "01.p/01.worker", 1,
                                               limit=2)
        replacement = [
            {"ts": None, "type": "message", "role": "assistant",
             "blocks": [{"type": "text", "text": f"new-{n}-longer"}]}
            for n in range(1, 5)
        ]
        self.path.write_text(
            "".join(json.dumps(r) + "\n" for r in replacement),
            encoding="utf-8")
        after = dashboard_data.transcript_data(
            self.run, "01.p/01.worker", 1, cursor=first["next_cursor"],
            limit=10)
        self.assertTrue(after["reset"])
        self.assertEqual([r["id"] for r in after["records"]],
                         ["L1", "L2", "L3", "L4"])
        self.assertIn("new-1-longer", json.dumps(after["records"]))
        self.assertTrue(any("prefix changed" in d
                            for d in after["diagnostics"]))

    def test_a_large_consumed_prefix_is_hashed_in_full(self):
        records = [
            {"ts": None, "type": "message", "role": "assistant",
             "blocks": [{"type": "text",
                         "text": f"marker-{n:03d}-A-" + "x" * 1200}]}
            for n in range(1, 121)
        ]
        run = make_packet(self.tmp / "large-prefix", records=records)
        path = (run / "transcripts" / "worker-att01"
                / "transcript.jsonl")
        first = dashboard_data.transcript_data(
            run, "01.p/01.worker", 1, limit=100)
        raw = path.read_bytes()
        consumed = sum(len(line) for line in raw.splitlines(keepends=True)[:100])
        self.assertGreater(consumed, 100_000)
        old = b"marker-005-A"
        new = b"marker-005-B"
        self.assertEqual(raw.count(old), 1)
        path.write_bytes(raw.replace(old, new))

        after = dashboard_data.transcript_data(
            run, "01.p/01.worker", 1, cursor=first["next_cursor"],
            limit=10)
        self.assertTrue(after["reset"])
        self.assertEqual(after["records"][0]["id"], "L1")
        self.assertIn("marker-005-B", json.dumps(after["records"]))
        self.assertTrue(any("prefix changed" in d
                            for d in after["diagnostics"]))

    def test_cursor_is_bound_to_attempt_and_tampering_is_diagnosed(self):
        first = dashboard_data.transcript_data(self.run, "01.p/01.worker", 1,
                                               limit=2)
        case_path = self.run / "case.json"
        case = json.loads(case_path.read_text(encoding="utf-8"))
        second_dir = self.run / "transcripts" / "worker-att02"
        second_dir.mkdir()
        second = {"ts": None, "type": "message", "role": "assistant",
                  "blocks": [{"type": "text", "text": "attempt two"}]}
        (second_dir / "transcript.jsonl").write_text(
            json.dumps(second) + "\n", encoding="utf-8")
        attempt = dict(case["attempts"][0])
        attempt["attempt"] = 2
        attempt["transcript"] = {
            "jsonl": "packet:transcripts/worker-att02/transcript.jsonl",
            "records": 1,
        }
        case["attempts"].append(attempt)
        case_path.write_text(json.dumps(case), encoding="utf-8")

        crossed = dashboard_data.transcript_data(
            self.run, "01.p/01.worker", 2, cursor=first["next_cursor"])
        self.assertTrue(crossed["reset"])
        self.assertIn("attempt two", json.dumps(crossed["records"]))
        self.assertTrue(any("another run, coordinate, attempt" in d
                            for d in crossed["diagnostics"]))

        token = first["next_cursor"]
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
        rejected = dashboard_data.transcript_data(
            self.run, "01.p/01.worker", 1, cursor=tampered, limit=1)
        self.assertTrue(rejected["reset"])
        self.assertEqual(rejected["records"][0]["id"], "L1")
        self.assertTrue(any("tampered" in d
                            for d in rejected["diagnostics"]))

    def test_a_malformed_line_becomes_a_named_error_record(self):
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write('{"broken json\n')
        block = dashboard_data.transcript_data(self.run, "01.p/01.worker", 1,
                                               limit=10)
        errors = [r for r in block["records"] if r["type"] == "error"]
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["id"], "L5")
        self.assertTrue(any("malformed JSON" in d
                            for d in block["diagnostics"]))

    def test_a_blank_line_is_skipped_without_losing_ids(self):
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write("\n")
            fh.write(json.dumps({"ts": None, "type": "system",
                                 "subtype": "note"}) + "\n")
        block = dashboard_data.transcript_data(self.run, "01.p/01.worker", 1,
                                               limit=10)
        self.assertEqual(block["records"][-1]["id"], "L6")

    def test_secrets_are_redacted_before_the_page_leaves(self):
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(
                {"ts": None, "type": "message", "role": "assistant",
                 "blocks": [{"type": "text",
                             "text": "key = sk-live-secret-0123456789"}]})
                + "\n")
        block = dashboard_data.transcript_data(self.run, "01.p/01.worker", 1,
                                               limit=10)
        text = json.dumps(block)
        self.assertNotIn("sk-live-secret", text)
        self.assertIn("sk-[redacted]", text)

    def test_structured_secret_fields_are_masked_but_counters_survive(self):
        secret = "ordinary-value-with-no-token-shape"
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "ts": None, "type": "message", "role": "assistant",
                "blocks": [
                    {"type": "tool_use", "id": "call-secret", "name": "x",
                     "input": {"CLIENT_SECRET": secret,
                               "PASSWORD": "plain-password",
                               "input_tokens": 17}},
                    {"type": "tool_result", "tool_use_id": "call-secret",
                     "content": {"PASSWORD": "result-password",
                                 "output_tokens": 3}},
                ],
            }) + "\n")
        block = dashboard_data.transcript_data(self.run, "01.p/01.worker", 1,
                                               limit=10)
        text = json.dumps(block)
        for leaked in (secret, "plain-password", "result-password"):
            self.assertNotIn(leaked, text)
        record = block["records"][-1]
        self.assertEqual(record["blocks"][0]["input"]["CLIENT_SECRET"],
                         "[redacted]")
        self.assertEqual(record["blocks"][0]["input"]["input_tokens"], 17)
        self.assertEqual(record["blocks"][1]["content"]["output_tokens"], 3)

    def test_oversized_record_uses_lossless_stable_continuations(self):
        wanted = "0123456789" * 9000
        run = make_packet(self.tmp / "large", records=[
            {"ts": None, "type": "message", "role": "assistant",
             "blocks": [{"type": "text", "text": wanted}]},
        ])
        cursor = None
        chunks, pages = [], []
        while True:
            page = dashboard_data.transcript_data(
                run, "01.p/01.worker", 1, cursor=cursor, limit=1)
            pages.append(page)
            self.assertLess(len(json.dumps(page)), 30000)
            record = page["records"][0]
            self.assertEqual(record["id"], "L1")
            chunks.append(record["continuation"]["data"])
            if not page["has_more"]:
                break
            cursor = page["next_cursor"]
        rebuilt = json.loads("".join(chunks))
        self.assertEqual(rebuilt["blocks"][0]["text"], wanted)
        self.assertEqual(sum(p["logical_records_started"] for p in pages), 1)
        self.assertEqual(sum(p["logical_records_completed"] for p in pages), 1)
        self.assertEqual(pages[-1]["total"], 1)
        self.assertTrue(pages[-1]["complete"])


class CurrentFormats(TempCase):

    def test_a_pi_session_is_read_from_the_top(self):
        run = copy_tree(HERE / "fixtures" / "dashboard" / "g1-run",
                        self.tmp / "g1")
        block = dashboard_data.transcript_data(run, "01.sweep/01.flaky", 2)
        self.assertTrue(block["complete"])
        self.assertEqual(block["records"][0]["type"], "session")
        types = {r["type"] for r in block["records"]}
        self.assertIn("message", types)
        calls = [b for r in block["records"] for b in r.get("blocks", [])
                 if b.get("type") == "tool_call"]
        self.assertTrue(calls)

    def test_a_claude_event_log_is_read(self):
        run = current_run(self.tmp, harness_executor="claude")
        log = attempt_dir(run) / "logs"
        log.mkdir(parents=True)
        (log / "claude-events.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in claude_records()),
            encoding="utf-8")
        block = dashboard_data.transcript_data(run, "01.build/01.worker", 1)
        self.assertTrue(block["complete"])
        calls = [b for r in block["records"] for b in r.get("blocks", [])
                 if b.get("type") == "tool_call"]
        results = [b for r in block["records"] for b in r.get("blocks", [])
                   if b.get("type") == "tool_result"]
        self.assertEqual(calls[0]["call_id"], "toolu_1")
        self.assertEqual(results[0]["call_id"], "toolu_1")
        init = next(r for r in block["records"] if r["type"] == "system")
        self.assertIsNone(init["ts"])

    def test_an_empty_attempt_is_not_a_fake_success(self):
        run = current_run(self.tmp, harness_executor="claude")
        block = dashboard_data.transcript_data(run, "01.build/01.worker", 1)
        self.assertEqual(block["records"], [])
        self.assertFalse(block["complete"])
        self.assertTrue(any("claude-events.jsonl" in d
                            for d in block["diagnostics"]))

    def test_a_codex_event_log_is_read(self):
        run = current_run(self.tmp, harness_executor="codex")
        log = attempt_dir(run) / "logs"
        log.mkdir(parents=True)
        records = [
            {"type": "thread.started", "thread_id": "th1"},
            {"type": "item.started", "item": {"id": "item_0",
                                              "type": "command_execution",
                                              "command": "git status"}},
            {"type": "item.completed", "item": {"id": "item_0",
                                                "type": "command_execution",
                                                "exit_code": 0,
                                                "aggregated_output": "clean"}},
            {"type": "item.completed", "item": {"id": "item_1",
                                                "type": "agent_message",
                                                "text": "DONE"}},
            {"type": "turn.completed", "usage": {"input_tokens": 10,
                                                 "output_tokens": 5}},
        ]
        (log / "codex-events.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
        block = dashboard_data.transcript_data(run, "01.build/01.worker", 1)
        call = next(r for r in block["records"] if r["type"] == "tool_call")
        result = next(r for r in block["records"]
                      if r["type"] == "tool_result")
        self.assertEqual(call["tool_call_id"], "item_0")
        self.assertEqual(result["tool_call_id"], "item_0")
        final = next(r for r in block["records"] if r["type"] == "result")
        self.assertEqual(final["usage"]["input_tokens"], 10)

    def test_a_command_step_serves_its_out_log(self):
        run = self.tmp / "cmd-run"
        workflow_json(run, [("Build", [command("compile", "echo hi")], 1)])
        log = RunLog(run)
        log.phase(1, "01.build", "Build", ["01.build/01.compile"], 1)
        log.start(2, "01.build/01.compile", 1)
        log.finish(3, "01.build/01.compile", 1, "passed", wall=1.0)
        attempt = run / "phases" / "01.build" / "01.compile" / "attempts" / "01"
        logs = attempt / "logs"
        logs.mkdir(parents=True)
        (logs / "compile.out.log").write_text("hi\n", encoding="utf-8")
        block = dashboard_data.transcript_data(run, "01.build/01.compile", 1)
        self.assertEqual(block["records"][0]["type"], "log")
        self.assertEqual(block["records"][0]["blocks"][0]["text"], "hi")

    def test_an_unknown_attempt_is_refused(self):
        run = PACKET
        for coord, attempt in ((IMPL, 9), (IMPL, "x"), ("../elsewhere", 1),
                               (IMPL, -1), (IMPL, 10000), (REVIEW, 99)):
            with self.subTest(coord=coord, attempt=attempt):
                self.assertIsNone(
                    dashboard_data.transcript_data(run, coord, attempt))

    def test_bad_cursors_and_limits_are_refused(self):
        for cursor in ("not-a-cursor", "%%%", "eyJvIjotMX0"):
            with self.subTest(cursor=cursor):
                block = dashboard_data.transcript_data(
                    PACKET, IMPL, 4, cursor=cursor, limit=1)
                self.assertTrue(block["reset"])
                self.assertEqual(block["records"][0]["id"], "L1")
                self.assertTrue(any("cursor" in d and "beginning" in d
                                    for d in block["diagnostics"]))
        for limit in (0, -5, 401, "huge"):
            with self.subTest(limit=limit):
                self.assertIsNone(dashboard_data.transcript_data(
                    PACKET, IMPL, 4, limit=limit))


class OverHttp(TempCase):

    def setUp(self):
        super().setUp()
        self.handle = dashboard.start(PACKET)
        self.addCleanup(self.handle.stop)
        self.base = self.handle.url.rstrip("/")

    def test_the_route_serves_pages_and_echoes_the_cursor(self):
        status, body = get(self.base + "/api/transcript?coord="
                           "01.implement/01.implement&attempt=4&limit=7")
        self.assertEqual(status, 200)
        block = json.loads(body)
        self.assertEqual(block["schema"], "ohflow.transcript/1")
        self.assertEqual(block["limit"], 7)
        self.assertEqual(len(block["records"]), 7)
        self.assertIsNone(block["cursor"])
        status, body = get(self.base + "/api/transcript?coord="
                           "01.implement/01.implement&attempt=4&limit=7"
                           f"&cursor={block['next_cursor']}")
        self.assertEqual(status, 200)
        second = json.loads(body)
        self.assertEqual(second["cursor"], block["next_cursor"])
        self.assertEqual(second["records"][0]["id"], "L8")

    def test_invalid_requests_are_404_and_leak_nothing(self):
        for path in (
            "/api/transcript?coord=../../etc&attempt=1",
            "/api/transcript?coord=01.implement/01.implement&attempt=abc",
            "/api/transcript?coord=01.implement/01.implement&attempt=99",
            "/api/transcript?attempt=4",
        ):
            with self.subTest(path=path):
                status, body = get(self.base + path)
                self.assertEqual(status, 404, path)
                self.assertNotIn(b"transcript.jsonl", body)

    def test_invalid_cursor_is_bounded_diagnosed_and_restarted(self):
        for invalid in ("@@bad@@", "x" * 5001, "x" * 50_000):
            with self.subTest(length=len(invalid)):
                query = urllib.parse.urlencode({
                    "coord": "01.implement/01.implement", "attempt": 4,
                    "limit": 1, "cursor": invalid,
                })
                status, body = get(self.base + "/api/transcript?" + query)
                self.assertEqual(status, 200)
                block = json.loads(body)
                self.assertTrue(block["reset"])
                self.assertIsNone(block["cursor"])
                self.assertEqual(block["records"][0]["id"], "L1")
                self.assertLess(len(body), 30_000)
                self.assertTrue(any("cursor" in d
                                    for d in block["diagnostics"]))

                restart = urllib.parse.urlencode({
                    "coord": "01.implement/01.implement", "attempt": 4,
                    "limit": 1, "cursor": block["next_cursor"],
                })
                status, body = get(self.base + "/api/transcript?" + restart)
                self.assertEqual(status, 200)
                continued = json.loads(body)
                self.assertFalse(continued["reset"])
                self.assertEqual(continued["records"][0]["id"], "L2")


if __name__ == "__main__":
    import unittest
    unittest.main()

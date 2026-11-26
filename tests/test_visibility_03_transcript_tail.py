"""`/api/transcript?tail=N`: the last N records of an attempt, and a cursor
that continues from the end.

The peek panel polls every running invocation for its output tail. Paging a
long transcript from the top to reach its end would cost the whole file on
every first look, so `tail` starts the page N complete records before the end
and hands back the same cursor the top-down pager would have reached there:
the next poll with that cursor adds only what the agent appended since.
"""

from __future__ import annotations

import json
import urllib.parse

from support import TempCase
from test_dashboard_08_transcript import (IMPL, PACKET, get, make_packet)

from ohflow import dashboard, dashboard_data


def ids(block) -> list[str]:
    return [r["id"] for r in block["records"]]


class TailOfAStream(TempCase):

    def setUp(self):
        super().setUp()
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

    def test_the_tail_is_the_last_n_records_with_their_real_ids(self):
        block = dashboard_data.transcript_data(self.run, "01.p/01.worker", 1,
                                               tail=2)
        self.assertEqual(ids(block), ["L3", "L4"])
        self.assertEqual(block["limit"], 2)
        self.assertEqual(block["tail"], 2)
        self.assertFalse(block["has_more"])
        self.assertTrue(block["complete"])
        self.assertEqual(block["records"][-1]["blocks"][0]["text"], "three")

    def test_the_cursor_continues_from_the_end_without_duplicates(self):
        first = dashboard_data.transcript_data(self.run, "01.p/01.worker", 1,
                                               tail=2)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(
                {"ts": "2026-10-01T21:48:41Z", "type": "message",
                 "role": "assistant",
                 "blocks": [{"type": "text", "text": "four"}]}) + "\n")
        second = dashboard_data.transcript_data(
            self.run, "01.p/01.worker", 1, cursor=first["next_cursor"],
            limit=10)
        self.assertEqual(ids(second), ["L5"])
        self.assertFalse(second["reset"])
        self.assertIn("four", json.dumps(second["records"]))

    def test_a_tail_longer_than_the_transcript_starts_at_the_top(self):
        block = dashboard_data.transcript_data(self.run, "01.p/01.worker", 1,
                                               tail=50)
        self.assertEqual(ids(block), ["L1", "L2", "L3", "L4"])
        self.assertEqual(block["total"], 4)

    def test_a_torn_final_line_is_left_for_its_writer(self):
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write('{"ts": null, "type": "message", "role": "assistant"')
        block = dashboard_data.transcript_data(self.run, "01.p/01.worker", 1,
                                               tail=2)
        self.assertEqual(ids(block), ["L3", "L4"])
        self.assertNotIn("L5", json.dumps(block["records"]))

    def test_blank_lines_before_the_tail_keep_the_line_numbers_true(self):
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write("\n\n")
            fh.write(json.dumps({"ts": None, "type": "system",
                                 "subtype": "note"}) + "\n")
        block = dashboard_data.transcript_data(self.run, "01.p/01.worker", 1,
                                               tail=2)
        self.assertEqual(ids(block), ["L4", "L7"])

    def test_tail_sets_the_page_size_and_refuses_nonsense(self):
        for bad in (0, -1, 401, "x"):
            with self.subTest(tail=bad):
                self.assertIsNone(dashboard_data.transcript_data(
                    self.run, "01.p/01.worker", 1, tail=bad))
        # `tail` wins over `limit`: the page is the tail, whole.
        block = dashboard_data.transcript_data(self.run, "01.p/01.worker", 1,
                                               tail=3, limit=1)
        self.assertEqual(ids(block), ["L2", "L3", "L4"])
        self.assertEqual(block["limit"], 3)

    def test_a_page_without_tail_says_so(self):
        block = dashboard_data.transcript_data(self.run, "01.p/01.worker", 1,
                                               limit=2)
        self.assertIsNone(block["tail"])


class TailOfTheRecordedPacket(TempCase):

    def test_the_implement_attempt_tail_is_its_last_five_records(self):
        block = dashboard_data.transcript_data(PACKET, IMPL, 4, tail=5)
        self.assertEqual(ids(block), ["L96", "L97", "L98", "L99", "L100"])
        self.assertTrue(block["complete"])
        self.assertEqual(block["total"], 100)
        again = dashboard_data.transcript_data(PACKET, IMPL, 4,
                                               cursor=block["next_cursor"])
        self.assertEqual(again["records"], [])
        self.assertFalse(again["reset"])


class TailOverHttp(TempCase):

    def setUp(self):
        super().setUp()
        self.handle = dashboard.start(PACKET)
        self.addCleanup(self.handle.stop)
        self.base = self.handle.url.rstrip("/")

    def test_the_route_takes_tail(self):
        status, body = get(self.base + "/api/transcript?coord="
                           + urllib.parse.quote(IMPL) + "&attempt=4&tail=5")
        self.assertEqual(status, 200)
        block = json.loads(body)
        self.assertEqual(ids(block), ["L96", "L97", "L98", "L99", "L100"])
        self.assertEqual(block["tail"], 5)

    def test_a_bad_tail_is_404(self):
        for bad in ("0", "abc", "999"):
            with self.subTest(tail=bad):
                status, _body = get(self.base + "/api/transcript?coord="
                                    + urllib.parse.quote(IMPL)
                                    + f"&attempt=4&tail={bad}")
                self.assertEqual(status, 404)


if __name__ == "__main__":
    import unittest
    unittest.main()

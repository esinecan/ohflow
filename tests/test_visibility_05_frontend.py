"""The shipping page draws the live-visibility fields `/api/workflow` carries.

The attention strip above the map, the phase lane line, the peek panel that
tails every running invocation through `/api/transcript?tail=`, and the digest
list under the retry story. These tests pin the page source to the names,
and serve a live fixture to check the data the page reads is there.
"""

from __future__ import annotations

import json
import urllib.request

from support import TempCase
from test_dashboard_07_data import live_run

from ohflow import dashboard

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def fetch(url: str) -> tuple[int, bytes]:
    with OPENER.open(url, timeout=10) as resp:
        return resp.status, resp.read()


class PageSource(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.html = dashboard.TEMPLATE.read_text(encoding="utf-8")
        self.js = dashboard.STATIC_ASSETS["/dashboard.js"][0].read_text(
            encoding="utf-8")
        self.css = dashboard.STATIC_ASSETS["/dashboard.css"][0].read_text(
            encoding="utf-8")

    def assertNames(self, source: str, *markers: str) -> None:
        for marker in markers:
            self.assertTrue(marker in source, f"{marker!r} is not in the source")

    def test_the_shell_reserves_the_strip_the_lanes_and_the_peek_panel(self):
        self.assertNames(self.html, 'id="attention-strip"', 'id="phase-lanes"',
                         'id="live-peek"')
        # The strip sits above the map, the peek panel inside the graph panel.
        self.assertLess(self.html.index('id="attention-strip"'),
                        self.html.index('id="overview-layout"'))
        self.assertLess(self.html.index('id="graph-canvas"'),
                        self.html.index('id="live-peek"'))

    def test_the_script_renders_each_field(self):
        self.assertNames(self.js, "function renderAttention", "w.attention",
                         "function renderLanes", "lanes.text",
                         "function renderLivePeek", "function pollPeek",
                         "&tail=", "function renderDigest", "digest-list",
                         "handover_first_line")
        # Each attention item and digest entry selects its invocation.
        self.assertNames(self.js, "item.evidence", "entry.id")


class ServedLiveFixture(TempCase):

    def test_the_live_run_answers_attention_lanes_and_digest(self):
        run = live_run(self.tmp / "live-run")
        handle = dashboard.start(run)
        self.addCleanup(handle.stop)
        status, page = fetch(handle.url)
        self.assertEqual(status, 200)
        self.assertIn(b'id="attention-strip"', page)
        self.assertIn(b'id="live-peek"', page)
        status, body = fetch(handle.url + "api/workflow")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(payload["run"]["mode"], "live")
        self.assertIn("attention", payload)
        self.assertIn("digest", payload)
        self.assertEqual(payload["phases"][0]["lanes"]["running"], 1)
        self.assertEqual(payload["phases"][0]["lanes"]["text"], "1 running")
        status, body = fetch(handle.url + "api/transcript?coord=01.build/"
                             "01.worker&attempt=1&tail=5")
        self.assertEqual(status, 200)
        block = json.loads(body)
        self.assertEqual(block["tail"], 5)
        self.assertEqual(len(block["records"]), 2)


if __name__ == "__main__":
    import unittest
    unittest.main()

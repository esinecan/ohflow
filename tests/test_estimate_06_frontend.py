"""The page renders the estimate fields `/api/workflow` now carries.

The ETA was computed for a month and never drawn: the page polled
`/api/workflow`, which did not carry it. The run header's time line is checked
on the shipping page itself, booted under node on the `/api/workflow` of a
live run and of a finished one: the ETA while it runs, the predicted-versus-
actual line when it is over. The other tests pin the page source to the
fields: the header's ETA element, the phase header's `~N min`, the running
card's `expected` beside its elapsed time, and the digest's
predicted-versus-actual block.
"""

from __future__ import annotations

from dashboard_support import T0, RunLog, boot_page
from ohflow import dashboard, dashboard_data
from support import TempCase
from test_estimate_04_run_writes_estimate_json import A, B, live_run


class PageSource(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.html = dashboard.TEMPLATE.read_text(encoding="utf-8")
        self.js = dashboard.STATIC_ASSETS["/dashboard.js"][0].read_text(encoding="utf-8")

    def assertNames(self, source: str, *markers: str) -> None:
        # The sources are large; a failure names the missing marker only.
        for marker in markers:
            self.assertTrue(marker in source, f"{marker!r} is not in the source")

    def test_the_shell_reserves_the_run_eta_element(self):
        self.assertNames(self.html, 'id="run-eta"')

    def test_the_phase_header_shows_the_phase_estimate(self):
        self.assertNames(self.js, "phase-estimate")
        self.assertNames(self.js, "phase.estimate")

    def test_the_running_card_shows_the_expected_time(self):
        self.assertNames(self.js, '"expected "')
        self.assertNames(self.js, "step.estimate")

    def test_the_digest_shows_predicted_vs_actual_tokens_and_minutes(self):
        self.assertNames(self.js, "digest-estimate")
        self.assertNames(self.js, "run.estimate")
        self.assertNames(self.js, "tokens")


class TheRunHeader(TempCase):

    def eta(self, payload: dict) -> dict:
        seen = boot_page(payload, ids=("run-eta",))
        if seen is None:
            self.skipTest("node is not installed")
        self.assertEqual(seen["errors"], [])
        return seen["ids"]["run-eta"]

    def test_the_header_reads_eta_while_live_and_predicted_vs_actual_when_final(self):
        live = dashboard_data.workflow_data(
            live_run(self.tmp / "live", finish_a=False), now=T0 + 12)
        self.assertEqual(live["run"]["eta_s"], 190)
        shown = self.eta(live)
        self.assertFalse(shown["hidden"], "a live run's header hides its ETA")
        self.assertIn("3m10s", shown["text"])
        self.assertIn(live["run"]["eta_basis"], shown["text"])

        over = live_run(self.tmp / "over", finish_a=True)
        (RunLog(over).phase(1, "01.build", "Build", [A, B], 1)
         .start(2, A, 1).finish(42, A, 1, "passed", wall=40.0)
         .start(43, B, 1).finish(83, B, 1, "passed", wall=40.0)
         .settle(84, "01.build", "passed", 2, 2).run_finished(90, "finished"))
        final = dashboard_data.workflow_data(over, now=T0 + 120)
        self.assertEqual(final["run"]["status"], "finished")
        self.assertEqual(final["run"]["estimate"]["wall_s"]["p50"], 200)
        self.assertEqual(final["run"]["elapsed_s"], 90)
        shown = self.eta(final)
        self.assertFalse(shown["hidden"],
                         "a finished run's header hides predicted versus actual")
        self.assertIn("3m20s", shown["text"])
        self.assertIn("1m30s", shown["text"])

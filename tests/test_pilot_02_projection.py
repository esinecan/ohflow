from __future__ import annotations

from dataclasses import replace

from ohflow import pilot
from ohflow.workflow import Unit
from pilot_support import two_paths
from support import TempCase


def attempt(wall, prompt, completion, cost=None, source=None, status="passed"):
    return {"attempt": 1, "status": status, "wall_seconds": wall,
            "tokens": {"prompt_tokens": prompt, "completion_tokens": completion},
            "cost": cost, "cost_source": source}


def summary_of(steps: dict) -> dict:
    return {"started": "2026-11-07T10:00:00Z", "finished": "2026-11-07T10:05:00Z",
            "phases": {"01.fix": {"steps": {
                f"01.fix/{i:02d}.{sid}": {"step_id": sid, "kind": "agent",
                                          "status": status, "attempts": attempts}
                for i, (sid, (status, attempts)) in enumerate(steps.items(), 1)}}}}


class Projection(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.full = two_paths(self.repo)
        self.small = pilot.pilot_workflow(self.full)
        self.summary = summary_of({
            "fix-s2": ("passed", [attempt(60, 900, 100, 0.10, "catalog")]),
            "fix-p2": ("passed", [attempt(100, 1500, 500, 0.20, "catalog",
                                          status="failed"),
                                  attempt(200, 2500, 500, 0.30, "catalog")]),
            "report": ("passed", [attempt(30, 400, 100, 0.05, "catalog")]),
        })

    def test_measure_sums_every_attempt_of_a_unit(self):
        measured = pilot.measure(self.small, self.summary)
        self.assertEqual(measured["units"]["s2"]["wall_s"], 60)
        self.assertEqual(measured["units"]["s2"]["tokens"], 1000)
        self.assertEqual(measured["units"]["p2"]["wall_s"], 300)
        self.assertEqual(measured["units"]["p2"]["tokens"], 5000)
        self.assertEqual(measured["units"]["p2"]["attempts"], 2)
        self.assertAlmostEqual(measured["units"]["p2"]["cost_usd"], 0.50)
        self.assertEqual(measured["shared"]["wall_s"], 30)
        self.assertEqual(measured["shared"]["steps"], 1)

    def test_the_full_run_is_units_times_the_measured_cost_plus_shared(self):
        projection = pilot.project(self.full, pilot.measure(self.small, self.summary))
        single, probe = projection["paths"]
        self.assertEqual((single["units"], single["pilot_unit"]), (3, "s2"))
        self.assertEqual(single["projected"]["wall_s"], 180)
        self.assertEqual(single["projected"]["tokens"], 3000)
        self.assertEqual((probe["units"], probe["pilot_unit"]), (2, "p2"))
        self.assertEqual(probe["projected"]["wall_s"], 600)
        self.assertEqual(probe["projected"]["tokens"], 10000)
        total = projection["total"]
        self.assertEqual(total["wall_s"], 180 + 600 + 30)
        self.assertEqual(total["tokens"], 3000 + 10000 + 500)
        self.assertAlmostEqual(total["cost_usd"], 0.30 + 1.00 + 0.05)
        self.assertEqual(total["units"], 5)
        self.assertTrue(total["complete"])

    def test_an_edited_module_is_projected_with_its_own_unit_counts(self):
        measured = pilot.measure(self.small, self.summary)
        fewer = replace(self.full, units=self.full.units[:2]
                        + (Unit("p2", "probe", 1),))
        projection = pilot.project(fewer, measured)
        self.assertEqual([p["units"] for p in projection["paths"]], [2, 1])
        self.assertEqual(projection["total"]["tokens"], 2000 + 5000 + 500)

    def test_a_path_the_pilot_did_not_measure_makes_the_projection_incomplete(self):
        measured = pilot.measure(self.small, self.summary)
        del measured["units"]["p2"]
        projection = pilot.project(self.full, measured)
        self.assertFalse(projection["total"]["complete"])
        self.assertEqual(projection["total"]["missing"], ["probe"])
        self.assertIsNone(projection["paths"][1]["projected"])
        self.assertEqual(projection["paths"][1]["status"], "not measured")

    def test_tokens_without_a_price_make_the_cost_unpriced(self):
        summary = summary_of({"fix-s2": ("passed", [attempt(60, 900, 100)]),
                              "fix-p2": ("passed", [attempt(10, 1, 1, 0.1, "catalog")])})
        measured = pilot.measure(self.small, summary)
        self.assertIsNone(measured["units"]["s2"]["cost_usd"])
        projection = pilot.project(self.full, measured)
        self.assertIsNone(projection["total"]["cost_usd"])

    def test_a_subscription_cost_is_a_known_zero(self):
        summary = summary_of({"fix-s2": ("passed", [attempt(60, 900, 100, 0.0, "subscription")]),
                              "fix-p2": ("passed", [attempt(10, 1, 1, 0.1, "catalog")])})
        measured = pilot.measure(self.small, summary)
        self.assertEqual(measured["units"]["s2"]["cost_usd"], 0.0)

    def test_a_command_step_is_timed_from_its_step_record(self):
        command = {"attempt": 1, "status": "passed", "wall_seconds": None,
                   "tokens": None, "cost": None, "cost_source": None,
                   "started": "2026-11-07T10:00:00Z", "ended": "2026-11-07T10:00:04Z"}
        summary = summary_of({"fix-s2": ("passed", [dict(command)]),
                              "fix-p2": ("passed", [dict(command)])})
        steps = summary["phases"]["01.fix"]["steps"]
        steps["01.fix/01.fix-s2"]["wall_seconds"] = 3.5
        measured = pilot.measure(self.small, summary)
        self.assertEqual(measured["units"]["s2"]["wall_s"], 3.5)
        self.assertEqual(measured["units"]["p2"]["wall_s"], 4.0)
        self.assertEqual(measured["units"]["s2"]["cost_usd"], 0.0)

    def test_a_failed_unit_is_named_by_its_status(self):
        summary = summary_of({"fix-s2": ("quarantined", [attempt(60, 900, 100,
                                                                status="failed")]),
                              "fix-p2": ("passed", [attempt(10, 1, 1)])})
        measured = pilot.measure(self.small, summary)
        self.assertEqual(measured["units"]["s2"]["status"], "quarantined")
        self.assertEqual(measured["units"]["p2"]["status"], "passed")

    def test_the_text_leads_with_the_projection_and_lists_each_path(self):
        record = pilot.finished_record(self.full, self.small,
                                       self.tmp / "run" / "pilot", "finished",
                                       self.summary)
        lines = pilot.render_text(record).splitlines()
        self.assertEqual(lines[0], "PILOT two-paths: projected 14 min, 13.5 k "
                                   "tokens, $1.35 for 5 units on 2 paths; measured "
                                   "on 2 pilot units in 5 min, pilot run finished")
        self.assertIn("| single | 3 | s2 | passed | 1 min | 1.0 k | $0.10 | 3 min "
                      "| 3.0 k | $0.30 |", lines)
        self.assertIn("| probe | 2 | p2 | passed | 5 min | 5.0 k | $0.50 | 10 min "
                      "| 10.0 k | $1.00 |", lines)
        self.assertTrue(any(line.startswith("| shared steps |") for line in lines))

    def test_a_running_pilot_says_which_units_run(self):
        record = pilot.started_record(self.full, self.small, self.tmp / "p")
        self.assertIn("running the smallest unit of each path (s2, p2)",
                      pilot.render_text(record))


if __name__ == "__main__":
    import unittest
    unittest.main()

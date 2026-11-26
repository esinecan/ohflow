"""Who waits for whom: each phase on `/api/workflow` carries its lanes.

`lanes` counts the phase's running steps and the steps waiting, by what they
wait for (a free slot, the provider cooldown, an auto-resume pass, a resume,
their phase, a dependency, the hold), and words the line the page shows:
"2 running · 1 for a free slot (2 of 2 busy) · 1 for a dependency". A step
that waits for a dependency keeps naming it in its own `reason`.
"""

from __future__ import annotations

from dashboard_support import (T0, RunLog, agent, command, mark_alive, stamp,
                               workflow_json)
from support import TempCase

from ohflow import dashboard_data, live

A, B, C, D = ("01.alpha/01.a", "01.alpha/02.b", "01.alpha/03.c",
              "01.alpha/04.d")
LATER = "02.beta/01.later"


def phases(payload) -> dict:
    return {p["coord"]: p for p in payload["phases"]}


class Lanes(TempCase):

    def test_slot_dependency_and_phase_waits_are_counted_and_worded(self):
        run = self.run_dir("r-lanes")
        a, b, c, d = agent("a"), agent("b"), agent("c"), agent("d")
        d["depends_on"] = ["c"]
        workflow_json(run, [("Alpha", [a, b, c, d], 2),
                            ("Beta", [command("later")], 1)])
        (RunLog(run).phase(1, "01.alpha", "Alpha", [A, B, C, D], 2)
         .start(2, A).start(2, B))
        mark_alive(run)
        payload = dashboard_data.workflow_data(run, now=T0 + 100)
        alpha, beta = phases(payload)["01.alpha"], phases(payload)["02.beta"]
        self.assertEqual(alpha["lanes"]["running"], 2)
        self.assertEqual(alpha["lanes"]["waiting_by"],
                         {"slot": 1, "dependency": 1})
        self.assertEqual(alpha["lanes"]["waiting_words"],
                         "1 for a free slot, 1 for a dependency")
        self.assertEqual(alpha["lanes"]["text"],
                         "2 running · 1 for a free slot (2 of 2 busy) · "
                         "1 for a dependency")
        self.assertEqual(beta["lanes"]["running"], 0)
        self.assertEqual(beta["lanes"]["waiting_by"], {"phase": 1})
        self.assertEqual(beta["lanes"]["text"], "0 running · 1 for its phase")
        steps = {s["coord"]: s for s in payload["steps"]}
        self.assertEqual(steps[D]["waiting_on"], "dependency")
        self.assertIn(C, steps[D]["reason"])

    def test_cooldown_and_auto_resume_waits_are_counted(self):
        run = self.run_dir("r-cool")
        workflow_json(run, [("Alpha", [agent("a"), agent("b")], 2)],
                      auto_resume=1)
        (RunLog(run, auto_resume=1).phase(1, "01.alpha", "Alpha", [A, B], 2)
         .start(2, A)
         .finish(5, A, 1, "deferred", error="429: rate limit",
                 failure_class="transient", cooldown_until=stamp(160)))
        mark_alive(run)
        payload = dashboard_data.workflow_data(run, now=T0 + 100)
        alpha = phases(payload)["01.alpha"]
        self.assertEqual(alpha["lanes"]["waiting_by"],
                         {"cooldown": 1, "auto_resume": 1})
        self.assertEqual(alpha["lanes"]["text"],
                         "0 running · 1 for the provider cooldown · "
                         "1 for an auto-resume pass")
        steps = {s["coord"]: s for s in payload["steps"]}
        self.assertEqual(steps[B]["waiting_on"], "cooldown")
        self.assertIn("cooldown", steps[B]["reason"])
        # Once the cooldown has passed, the same step waits for a slot.
        later = dashboard_data.workflow_data(run, now=T0 + 200)
        self.assertEqual(phases(later)["01.alpha"]["lanes"]["waiting_by"],
                         {"slot": 1, "auto_resume": 1})

    def test_a_deferred_step_past_its_budget_waits_for_nothing(self):
        run = self.run_dir("r-spent")
        workflow_json(run, [("Alpha", [agent("a"), agent("b")], 2)],
                      auto_resume=0)
        (RunLog(run, auto_resume=0).phase(1, "01.alpha", "Alpha", [A, B], 2)
         .start(2, A)
         .finish(5, A, 1, "deferred", error="429", failure_class="transient")
         .start(6, B))
        mark_alive(run)
        payload = dashboard_data.workflow_data(run, now=T0 + 100)
        self.assertEqual(phases(payload)["01.alpha"]["lanes"],
                         {"running": 1, "waiting_by": {}, "waiting_words": "",
                          "max_parallel": 2, "text": "1 running"})
        steps = {s["coord"]: s for s in payload["steps"]}
        self.assertEqual(steps[A]["display"], "done")
        self.assertIn("budget", steps[A]["reason"])

    def test_a_held_run_waits_for_go(self):
        run = self.run_dir("r-held")
        workflow_json(run, [("Alpha", [agent("a"), agent("b")], 2)])
        import json
        import os
        from ohflow import rundir
        (run / rundir.HOLD_FILE).write_text(
            json.dumps({"pid": os.getpid(), "since": stamp(0)}), encoding="utf-8")
        payload = dashboard_data.workflow_data(run, now=T0 + 10)
        self.assertEqual(payload["run"]["status"], "held")
        self.assertEqual(phases(payload)["01.alpha"]["lanes"]["text"],
                         "0 running · 2 for go")

    def test_the_words_know_dependencies(self):
        self.assertEqual(live.waiting_words({"dependency": 1}),
                         "1 for a dependency")
        self.assertEqual(live.waiting_words({"dependency": 2, "slot": 1}),
                         "1 for a free slot, 2 for their dependencies")

    def test_the_packet_phases_carry_settled_lanes(self):
        from pathlib import Path
        packet = Path(__file__).resolve().parent / "fixtures" / "dashboard-basis"
        payload = dashboard_data.workflow_data(packet, now=T0)
        for phase in payload["phases"]:
            self.assertEqual(phase["lanes"]["running"], 0)
            self.assertEqual(phase["lanes"]["waiting_by"], {})


if __name__ == "__main__":
    import unittest
    unittest.main()

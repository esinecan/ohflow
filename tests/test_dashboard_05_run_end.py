"""Dashboard S3: a watching page sees the run end, not a lost contact.

The supervisor stops its dashboard a moment after the run ends. A page that
polls every two seconds used to keep a last graph that said `running`, and
then called the stop a lost contact. `Handle.stop` now waits for a watching
page's next poll -- the page polls `/api/workflow`, so that route feeds the
same watching signal `/api/read-out` does -- serves the final state in it,
and only then closes the port. That poll ends the wait: the stop returns well
inside the linger instead of sitting it out. A poll that began after the stop
carries the exit verdict for a run whose run log cannot name it (crash,
interrupt); a run that reached `run_finished` is terminal from its own files.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request

from dashboard_support import RunLog, workflow_json, agent
from ohflow import dashboard
from support import TempCase

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def get_json(url: str) -> dict:
    with OPENER.open(url, timeout=10) as resp:
        return json.loads(resp.read())


def read_out(url: str) -> dict:
    return get_json(url + "api/read-out")


def workflow(url: str) -> dict:
    return get_json(url + "api/workflow")


class TheLastPollSeesTheEnd(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.run = self.run_dir("r-ending")
        workflow_json(self.run, [("Map", [agent("a")], 1)])
        (RunLog(self.run).phase(1, "01.map", "Map", ["01.map/01.a"])
         .start(2, "01.map/01.a"))

    def test_a_watched_stop_serves_the_exit_status_once_more(self):
        handle = dashboard.start(self.run, supervisor_pid=os.getpid())
        self.addCleanup(handle.stop)
        self.assertEqual(read_out(handle.url)["run"]["status"], "running")

        stopper = threading.Thread(
            target=handle.stop, kwargs={"final_status": "crashed"})
        stopper.start()
        deadline = time.monotonic() + 5
        while handle._server.stopping_since is None \
                and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertIsNotNone(handle._server.stopping_since,
                             "a watched stop did not linger")
        self.assertEqual(read_out(handle.url)["run"]["status"], "crashed")
        stopper.join(timeout=dashboard.LINGER_S / 2)
        self.assertFalse(stopper.is_alive(),
                         "the stop waited past the final poll")

    def test_a_workflow_only_watcher_also_lingers_for_a_final_poll(self):
        """The shipping page polls `/api/workflow` only; the stop must wait
        for its next poll and that poll must carry the exit verdict."""
        handle = dashboard.start(self.run, supervisor_pid=os.getpid())
        self.addCleanup(handle.stop)
        # No supervisor.pid in this synthetic run, so the file-derived status
        # is `orphaned`; the exit verdict must replace it exactly as the
        # read-out route replaces running/starting/orphaned.
        self.assertEqual(workflow(handle.url)["run"]["status"], "orphaned")

        stopper = threading.Thread(
            target=handle.stop, kwargs={"final_status": "crashed"})
        stopper.start()
        deadline = time.monotonic() + 5
        while handle._server.stopping_since is None \
                and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertIsNotNone(handle._server.stopping_since,
                             "a workflow-only watcher did not make the stop linger")
        final = workflow(handle.url)
        self.assertEqual(final["run"]["status"], "crashed")
        self.assertEqual(final["run"]["mode"], "final")
        stopper.join(timeout=dashboard.LINGER_S / 2)
        self.assertFalse(stopper.is_alive(),
                         "the stop waited past the final workflow poll")
        # The port is closed after the final delivery, not before.
        with self.assertRaises(urllib.error.URLError):
            workflow(handle.url)

    def test_a_finished_run_is_terminal_from_its_own_files(self):
        """The normal end path needs no injected verdict: `run_finished` makes
        the workflow feed terminal, the stop lingers for the page's poll, and
        the page receives the finished state before the port closes."""
        RunLog(self.run).finish(30, "01.map/01.a", 1, "passed").run_finished(
            60, "finished")
        handle = dashboard.start(self.run, supervisor_pid=os.getpid())
        self.addCleanup(handle.stop)
        self.assertEqual(workflow(handle.url)["run"]["status"], "finished")
        stopper = threading.Thread(target=handle.stop)
        stopper.start()
        deadline = time.monotonic() + 5
        while handle._server.stopping_since is None \
                and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertIsNotNone(handle._server.stopping_since)
        stopper.join(timeout=5)
        self.assertFalse(stopper.is_alive())

    def test_an_unwatched_stop_is_immediate(self):
        handle = dashboard.start(self.run, supervisor_pid=os.getpid())
        started = time.monotonic()
        handle.stop(final_status="finished")
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertIsNone(handle._server.stopping_since)


class TheFinalPollReachesARealRun(TempCase):
    """Over a real `supervisor.run_workflow`-shaped stop: the page's next
    two-second poll lands inside the linger window and sees the end."""

    def setUp(self) -> None:
        super().setUp()
        self.run = self.run_dir("r-live-poll")
        workflow_json(self.run, [("Map", [agent("a")], 1)])
        (RunLog(self.run).phase(1, "01.map", "Map", ["01.map/01.a"])
         .start(2, "01.map/01.a"))

    def test_the_poll_that_lands_in_the_linger_window_is_final(self):
        handle = dashboard.start(self.run, supervisor_pid=os.getpid())
        self.addCleanup(handle.stop)
        first = workflow(handle.url)
        self.assertEqual(first["run"]["status"], "orphaned")
        RunLog(self.run).finish(30, "01.map/01.a", 1, "passed").run_finished(
            60, "finished")
        stopper = threading.Thread(target=handle.stop)
        stopper.start()
        deadline = time.monotonic() + 5
        seen = None
        while time.monotonic() < deadline:
            try:
                seen = workflow(handle.url)
            except (urllib.error.URLError, OSError):
                break
            if seen["run"]["status"] == "finished":
                break
            time.sleep(0.05)
        stopper.join(timeout=5)
        self.assertIsNotNone(seen, "no workflow poll reached the page")
        self.assertEqual(seen["run"]["status"], "finished")
        self.assertFalse(stopper.is_alive())


if __name__ == "__main__":
    import unittest
    unittest.main()

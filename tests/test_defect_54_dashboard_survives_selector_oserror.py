"""A transient OSError from the dashboard's selector does not end the serve loop.

Windows can raise `WinError 10055` (no buffer space) from `select()`. The
serve thread used to die with it, and the page timed out for the rest of the
run.
"""

from __future__ import annotations

import selectors
import time
import urllib.request
from unittest import mock

from dashboard_support import RunLog, workflow_json, agent
from ohflow import dashboard
from support import TempCase


class _Flaky(selectors.SelectSelector):
    raised = False

    def select(self, timeout=None):
        if not _Flaky.raised:
            _Flaky.raised = True
            raise OSError(10055, "no buffer space")
        return super().select(timeout)


class DashboardSurvivesSelectorError(TempCase):

    def test_the_dashboard_keeps_serving_after_a_selector_oserror(self):
        run = self.run_dir("r-flaky")
        workflow_json(run, [("Map", [agent("a")], 1)])
        RunLog(run)
        _Flaky.raised = False
        with mock.patch("socketserver._ServerSelector", _Flaky):
            handle = dashboard.start(run)
            self.addCleanup(handle.stop)
            deadline = time.monotonic() + 5
            while not _Flaky.raised and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(_Flaky.raised)
            url = f"http://127.0.0.1:{handle.port}/api/read-out"
            deadline = time.monotonic() + 10
            status = None
            while time.monotonic() < deadline:
                try:
                    with urllib.request.urlopen(url, timeout=5) as r:
                        status = r.status
                    break
                except OSError:
                    time.sleep(0.2)
            self.assertEqual(status, 200)
            self.assertTrue(handle.alive)

"""`ohflow dashboard --run DIR` on a run whose own dashboard serves starts nothing.

Before: the verb kept `dashboard.json` but still started a second server, so
a person who typed the verb against a live run got two URLs for one run.
Now the verb prints the recorded URL, says the run's own dashboard serves,
and exits 0 without binding a port.
"""

from __future__ import annotations

import json

from ohflow import cli, dashboard
from support import TempCase, quiet
from verb_support import live_child


class DashboardReusesTheLiveRecord(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.run = self.run_dir("r-live")
        self.run.mkdir(parents=True)
        (self.run / "workflow.json").write_text("{}", encoding="utf-8")
        child = live_child(self)
        self.record = {"url": "http://127.0.0.1:1/", "port": 1, "pid": child.pid,
                       "started": "2026-09-30T12:00:00Z", "supervisor": True}
        self.path = self.run / dashboard.RECORD
        self.path.write_text(json.dumps(self.record), encoding="utf-8")

    def test_it_prints_the_recorded_url_and_starts_no_server(self):
        def refuse(*_a, **_kw):
            raise AssertionError("a second dashboard was started")
        original = dashboard.start
        dashboard.start = refuse
        self.addCleanup(setattr, dashboard, "start", original)
        before = self.path.stat().st_mtime_ns
        with quiet() as output:
            code = cli.main(["dashboard", "--run", str(self.run)])
        self.assertEqual(code, cli.EXIT_OK)
        lines = output.out.splitlines()
        self.assertEqual(lines[0], "dashboard: http://127.0.0.1:1/")
        self.assertIn("the run's own dashboard is serving; nothing else started",
                      lines)
        self.assertEqual(self.path.stat().st_mtime_ns, before,
                         "dashboard.json is not written again")
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")),
                         self.record)


if __name__ == "__main__":
    import unittest
    unittest.main()

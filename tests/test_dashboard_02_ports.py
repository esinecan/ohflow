"""Dashboard S3, test 6: two runs started together get two ports.

Port 0 lets the OS pick a free port, so two dashboards started at the same
instant never collide. An explicit port that is already taken is refused, not
shared: Windows lets `SO_REUSEADDR` bind one listening port twice, and the
server turns that option off for exactly that reason.
"""

from __future__ import annotations

import json
import threading

from dashboard_support import RunLog, workflow_json, agent
from ohflow import dashboard
from support import TempCase


class TwoServers(TempCase):

    def _run(self, name: str):
        run = self.run_dir(name)
        workflow_json(run, [("Map", [agent("a")], 1)])
        RunLog(run)
        return run

    def test_two_servers_started_together_get_different_ports(self):
        runs = [self._run("r-one"), self._run("r-two")]
        handles: list = [None, None]
        barrier = threading.Barrier(2)

        def go(i):
            barrier.wait(timeout=5)
            handles[i] = dashboard.start(runs[i])

        threads = [threading.Thread(target=go, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        for h in handles:
            self.assertIsNotNone(h)
            self.addCleanup(h.stop)
        self.assertNotEqual(handles[0].port, handles[1].port)
        for run, h in zip(runs, handles):
            record = json.loads((run / "dashboard.json").read_text(
                encoding="utf-8"))
            self.assertEqual(record["port"], h.port)
            self.assertEqual(record["url"], f"http://127.0.0.1:{h.port}/")
            self.assertEqual(set(record), {"url", "port", "pid", "started",
                                           "supervisor"})

    def test_a_taken_port_is_refused_not_shared(self):
        first = dashboard.start(self._run("r-first"))
        self.addCleanup(first.stop)
        with self.assertRaises(OSError):
            dashboard.start(self._run("r-second"), port=first.port)

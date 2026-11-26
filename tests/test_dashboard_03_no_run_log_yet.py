"""Dashboard S3, test 7: the page and the read-out before the run log exists.

`ohflow run` starts the dashboard right after it claims the run directory, and
preflight, the baseline command and worktree creation all run before the
engine's first run log record. The page must answer during that time, and so
must the read-out, from `workflow.json` when it exists and from nothing when it
does not.
"""

from __future__ import annotations

import json
import os
import urllib.request

from dashboard_support import workflow_json, agent
from ohflow import dashboard
from support import TempCase


OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def fetch(url: str) -> tuple[int, bytes]:
    with OPENER.open(url, timeout=10) as resp:
        return resp.status, resp.read()


class NoRunLogYet(TempCase):

    def test_with_a_workflow_but_no_run_log(self):
        run = self.run_dir("r-early")
        workflow_json(run, [("Map", [agent("a"), agent("b")], 2),
                            ("Merge", [agent("c")], 1)])
        handle = dashboard.start(run, supervisor_pid=os.getpid())
        self.addCleanup(handle.stop)
        status, page = fetch(handle.url)
        self.assertEqual(status, 200)
        self.assertIn(b"<title>ohflow run</title>", page)
        status, body = fetch(handle.url + "api/read-out")
        self.assertEqual(status, 200)
        read_out = json.loads(body)
        self.assertEqual(read_out["run"]["status"], "starting",
                         "the serving supervisor is alive before it writes "
                         "supervisor.pid")
        self.assertEqual([a["coord"] for a in read_out["agents"]],
                         ["01.map/01.a", "01.map/02.b", "02.merge/01.c"])
        self.assertTrue(all(a["display"]["state"] == "waiting"
                            for a in read_out["agents"]))
        self.assertEqual(read_out["events"], [])
        self.assertIsNone(read_out["run"]["eta_s"])

    def test_with_nothing_but_the_directory(self):
        run = self.run_dir("r-empty")
        run.mkdir(parents=True)
        handle = dashboard.start(run, supervisor_pid=os.getpid())
        self.addCleanup(handle.stop)
        status, _page = fetch(handle.url)
        self.assertEqual(status, 200)
        status, body = fetch(handle.url + "api/read-out")
        self.assertEqual(status, 200)
        read_out = json.loads(body)
        self.assertEqual(read_out["agents"], [])
        self.assertEqual(read_out["phases"], [])
        self.assertEqual(read_out["run"]["id"], "r-empty")
        self.assertEqual(read_out["run"]["status"], "starting")
        self.assertEqual(sorted(p.name for p in run.iterdir()),
                         ["dashboard.json"],
                         "the dashboard writes dashboard.json and nothing else")

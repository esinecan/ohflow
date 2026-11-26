"""Dashboard S3, test 5: the server answers three GET paths and nothing else.

The server never maps a request to a file. A pi attempt directory holds
`pi-agent/auth.json`, and this test puts one there to prove no path reaches it.
Every path outside the endpoint table of spec §10 is a 404, every method but
GET is refused, and a `Host` that is not a loopback name is refused too, which
is what stops a web page from reaching the port through DNS rebinding.
"""

from __future__ import annotations

import http.client
import json
import urllib.error
import urllib.request

from dashboard_support import G1_RUN, copy_tree
from ohflow import dashboard
from support import TempCase

SECRET = "sk-this-must-never-be-served-0123456789"
#: Loopback requests must never be routed through a proxy the box configures.
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def get(url: str, *, method: str = "GET", host: str | None = None):
    req = urllib.request.Request(url, method=method)
    if host:
        req.add_header("Host", host)
    try:
        with OPENER.open(req, timeout=10) as resp:
            return resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


class Endpoints(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.run = copy_tree(G1_RUN, self.tmp / "r-g1")
        auth = (self.run / "phases" / "01.sweep" / "01.flaky" / "attempts" /
                "02" / "pi-agent" / "auth.json")
        auth.parent.mkdir(parents=True)
        auth.write_text(json.dumps({"zai": {"key": SECRET}}), encoding="utf-8")
        (self.run / ".env").write_text(f"ZAI_KEY={SECRET}\n", encoding="utf-8")
        self.handle = dashboard.start(self.run)
        self.addCleanup(self.handle.stop)
        self.base = self.handle.url.rstrip("/")

    def test_the_three_endpoints_answer(self):
        status, headers, body = get(self.base + "/")
        self.assertEqual(status, 200)
        self.assertTrue(headers["Content-Type"].startswith("text/html"))
        self.assertIn(b'id="ohflow-data"', body)
        self.assertEqual(headers["Cache-Control"], "no-store")

        status, headers, body = get(self.base + "/api/read-out")
        self.assertEqual(status, 200)
        self.assertTrue(headers["Content-Type"].startswith("application/json"))
        read_out = json.loads(body)
        self.assertEqual(read_out["schema"], "ohflow.read-out/2")
        self.assertEqual(read_out["run"]["status"], "finished")

        status, _h, body = get(self.base + "/api/agent?coord=01.sweep/01.flaky"
                                           "&attempt=2&limit=3")
        self.assertEqual(status, 200)
        block = json.loads(body)
        self.assertEqual(block["attempt"], 2)
        self.assertEqual(len(block["activity"]["tool_calls"]), 3)
        self.assertEqual(block["activity"]["tool_calls_total"], 5)

    def test_every_other_path_is_a_404(self):
        paths = [
            "/attempts/01/pi-agent/auth.json",
            "/phases/01.sweep/01.flaky/attempts/02/pi-agent/auth.json",
            "/run-log.jsonl", "/workflow.json", "/dashboard.json", "/.env",
            "/index.html", "/dashboard.html", "/api", "/api/", "/api/read-out/",
            "/api/read-outx", "/api/agents", "/../run-log.jsonl",
            # `//api/read-out` is absent on purpose: `http.server` itself
            # collapses a leading `//` to `/`, so it is the read-out endpoint.
            "/%2e%2e/run-log.jsonl", "//run-log.jsonl", "/favicon.ico",
            "/api/agent", "/api/agent?coord=01.sweep/01.flaky",
            "/api/agent?coord=01.sweep/01.flaky&attempt=abc",
            "/api/agent?coord=01.sweep/01.flaky&attempt=9",
            "/api/agent?coord=../../pi-agent&attempt=2",
            "/api/agent?coord=01.sweep/01.flaky/../../..&attempt=2",
        ]
        for path in paths:
            with self.subTest(path=path):
                status, _h, body = get(self.base + path)
                self.assertEqual(status, 404, path)
                self.assertNotIn(SECRET.encode(), body)

    def test_the_raw_request_line_cannot_climb_out_either(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.handle.port,
                                          timeout=10)
        self.addCleanup(conn.close)
        conn.putrequest("GET", "/../../phases/01.sweep/01.flaky/attempts/02/"
                               "pi-agent/auth.json", skip_host=True)
        conn.putheader("Host", f"127.0.0.1:{self.handle.port}")
        conn.endheaders()
        resp = conn.getresponse()
        self.assertEqual(resp.status, 404)
        self.assertNotIn(SECRET.encode(), resp.read())

    def test_no_method_but_get_is_accepted(self):
        for method in ("POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"):
            with self.subTest(method=method):
                status, headers, _b = get(self.base + "/api/read-out",
                                          method=method)
                self.assertEqual(status, 405)
                self.assertEqual(headers["Allow"], "GET")

    def test_a_foreign_host_header_is_refused(self):
        status, _h, _b = get(self.base + "/api/read-out",
                             host="attacker.example:80")
        self.assertEqual(status, 403)
        status, _h, _b = get(self.base + "/api/read-out",
                             host=f"localhost:{self.handle.port}")
        self.assertEqual(status, 200)

    def test_it_binds_loopback_only(self):
        self.assertEqual(self.handle._server.server_address[0], "127.0.0.1")
        self.assertTrue(self.handle.url.startswith("http://127.0.0.1:"))

    def test_stop_closes_the_port(self):
        self.handle.stop()
        with self.assertRaises(OSError):
            OPENER.open(self.base + "/api/read-out", timeout=5)

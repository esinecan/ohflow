"""Cloudflare spend: the attempt's container price and the run-end meter check.

- a settled pi-cloud attempt carries the Worker's container seconds, its
  instance, its Durable Object id and the list price of that time;
- `container_cost` prices memory and disk of the instance per second;
- `check_run` asks the meters for the run's own objects, writes
  `cloudflare.json`, and flags an object billed well beyond its report;
- unread meters leave the reported price and name the reason;
- a run with no pi-cloud attempt is not checked at all;
- the exit verdict names the Cloudflare figure, and the table sums it.
"""

from __future__ import annotations

import json
import tempfile
import unittest
import urllib.error
from pathlib import Path

from ohflow import cloud_spend, exit_report, table
from fakes.fake_pi_cloud import END_SECONDS, object_id
from pi_cloud_support import PiCloudCase

GIB = float(1 << 30)


class SettledAttemptCase(PiCloudCase):

    def test_a_settled_attempt_carries_its_container_time_and_price(self):
        key = self.key_of(self.tmp / "c1")
        self.worker.plan(key, 1, ["success"])
        _, result = self.run_attempt("c1")
        infra = result["infra"]
        self.assertEqual(infra["durable_object_id"], object_id(key))
        self.assertEqual(infra["instance"], "standard-1")
        self.assertEqual(infra["container_seconds"], END_SECONDS)
        self.assertEqual(result["infra_cost"],
                         cloud_spend.container_cost("standard-1", END_SECONDS))
        self.assertEqual(result["pi_cloud"]["durable_object_id"], object_id(key))


def _run_dir(root: Path, *, branch: str = "ohflow/pi-cloud/k1",
             seconds: float = 60.0) -> Path:
    attempt = root / "phases" / "p1" / "s1" / "attempts" / "01"
    attempt.mkdir(parents=True)
    (attempt / "remote.json").write_text(json.dumps(
        {"key": "k1", "branch": branch}), encoding="utf-8")
    (attempt / "result.json").write_text(json.dumps({
        "coord": "p1.s1", "attempt": 1, "pi_cloud": {"key": "k1"},
        "infra": {"durable_object_id": "aa", "instance": "standard-1",
                  "container_seconds": seconds},
        "infra_cost": cloud_spend.container_cost("standard-1", seconds)}),
        encoding="utf-8")
    return root


class CheckCase(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.queries: list[str] = []

    def tearDown(self):
        self._tmp.cleanup()

    def _meters(self, billed_seconds: float):
        def fetch(method, url, headers, body):
            self.queries.append(json.loads(body)["query"])
            return {"data": {"viewer": {"accounts": [{
                "containersMetricsAdaptiveGroups": [{
                    "dimensions": {"durableObjectId": "aa"},
                    "sum": {"allocatedMemory": 4 * GIB * billed_seconds,
                            "allocatedDisk": 8e9 * billed_seconds,
                            "cpuTimeSec": 3.0}}]}]}}}
        return fetch

    def test_container_cost_prices_memory_and_disk_per_second(self):
        self.assertAlmostEqual(cloud_spend.container_cost("standard-1", 3600),
                               4 * 3600 * 0.0000025 + 8 * 3600 * 0.00000007)
        self.assertIsNone(cloud_spend.container_cost("huge", 10))

    def test_the_check_reads_the_runs_objects_and_flags_a_long_tail(self):
        run = _run_dir(self.tmp / "run")
        check = cloud_spend.check_run(run, fetch=self._meters(3600.0),
                                      token="t", account="acct")
        self.assertIn('durableObjectId_in: ["aa"]', self.queries[0])
        row = check["attempts"][0]
        self.assertEqual(row["billed_seconds"], 3600.0)
        self.assertEqual(len(check["flags"]), 1)
        self.assertIn("ran on after its step", check["flags"][0])
        self.assertGreater(check["billed_usd"], check["reported_usd"])
        written = json.loads((run / "cloudflare.json").read_text(encoding="utf-8"))
        self.assertEqual(written["billed_usd"], check["billed_usd"])

    def test_a_billed_time_close_to_the_report_raises_no_flag(self):
        run = _run_dir(self.tmp / "run")
        check = cloud_spend.check_run(run, fetch=self._meters(90.0),
                                      token="t", account="acct")
        self.assertEqual(check["flags"], [])

    def test_unread_meters_keep_the_reported_price_and_name_the_reason(self):
        def refuse(method, url, headers, body):
            raise urllib.error.URLError("offline")
        run = _run_dir(self.tmp / "run")
        check = cloud_spend.check_run(run, fetch=refuse, token="t", account="acct")
        self.assertIsNone(check["billed_usd"])
        self.assertIn("offline", check["error"])
        self.assertGreater(check["reported_usd"], 0)
        self.assertTrue(any("not read" in line
                            for line in cloud_spend.report_lines(check)))

    def test_a_run_without_pi_cloud_attempts_is_not_checked(self):
        run = _run_dir(self.tmp / "run", branch="ohflow/durable/k1")
        (run / "phases/p1/s1/attempts/01/result.json").write_text("{}", encoding="utf-8")
        self.assertIsNone(cloud_spend.check_run(run, fetch=self._meters(1.0),
                                                token="t", account="acct"))
        self.assertFalse((run / "cloudflare.json").exists())

    def test_the_verdict_names_the_cloudflare_figure(self):
        read_out = {"agents": [], "run": {"id": "r", "status": "finished",
                                          "tokens": {}, "elapsed_s": 5},
                    "cloudflare": {"billed_usd": 0.0123, "reported_usd": 0.01}}
        self.assertIn("Cloudflare containers $0.0123 billed",
                      exit_report.verdict(read_out, None))
        read_out["cloudflare"]["lag_note"] = "the bill so far"
        self.assertIn("$0.0100 reported, $0.0123 billed so far",
                      exit_report.verdict(read_out, None))

    def test_the_table_sums_infra_cost_beside_cost(self):
        folded = table._fold([
            {"kind": "agent", "cost": 0.5, "cost_source": "pi-cloud-worker",
             "infra_cost": 0.01},
            {"kind": "agent", "cost": 0.25, "cost_source": "pi-cloud-worker",
             "infra_cost": 0.02}])
        self.assertEqual(folded["infra_cost"], "0.0300")
        self.assertEqual(table._fold([{"kind": "agent", "cost": 0.0,
                                       "cost_source": "unpriced"}])["infra_cost"],
                         table.MISSING)


if __name__ == "__main__":
    unittest.main()

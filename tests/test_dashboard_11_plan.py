"""`/api/plan`: the declared plan of a run, whole, for the Plan view.

`/api/workflow` caps every string at 2,000 characters and names only the gate
check names, so a held page could not show a 3,400-character brief or say what
a check tests. `/api/plan` reads `workflow.json`, `estimate.json` and
`.ohflow-hold` once, under the artifact cap of 32,000 characters, and carries
the position block, the gate wording, the handover contract, the schema, the
command and the limits of every step. A packet is recorded evidence with no
plan and answers 404. The route keeps the server's rules: GET only, loopback
hosts only, nothing written into the run directory.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import replace
from pathlib import Path

from dashboard_support import RunLog, T0, agent, plan28, workflow_json
from ohflow import dashboard, dashboard_data, estimate, exit_report, rundir
from ohflow.workflow import (CheckSpec, GateSpec, HandoverSpec, Phase,
                             RetryPolicy, Step, Unit, UnitPath, Workflow,
                             WorktreeSpec, to_jsonable, validate)
from support import TempCase, agent_step, git_repo

HERE = Path(__file__).resolve().parent
PACKET = HERE / "fixtures" / "dashboard-basis"
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

LONG_BRIEF = "Scout the module and write what you find. " * 120
SECRET_BRIEF = ("Call the API with the key sk-abcdefghijklmnopqrstuvwxyz0123 "
                "and report the status code.")
SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}},
          "required": ["ok"]}
SCOUT, BUILD = "01.scout/01.scout", "02.build/01.build"


def get(url: str, *, method: str = "GET", host: str | None = None):
    req = urllib.request.Request(url, method=method)
    if host:
        req.add_header("Host", host)
    try:
        with OPENER.open(req, timeout=10) as resp:
            return resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def plan_workflow(repo: Path) -> Workflow:
    scout = agent_step("scout", brief=LONG_BRIEF)
    build = Step(
        id="build", kind="agent", worktree="wt", write_scope=("src/**",),
        depends_on=("scout",), consumes=("scout",),
        retry=RetryPolicy(max=2, on=("agent_error",)),
        execution_timeout_s=1200, stall_timeout_s=300,
        gate=GateSpec(checks=(
            CheckSpec("command_exit", {"cmd": "npm test", "expect": 0}),
            CheckSpec("final_message_matches", {"regex": "DONE"}))),
        handover=HandoverSpec(audience="next", max_chars=4000,
                              extra=("What broke?",)),
        schema=SCHEMA, unit="family-a",
        agent=replace(agent_step("build", brief=SECRET_BRIEF).agent,
                      command_time_cap_s=240))
    check = Step(id="check", kind="command", command="echo DONE",
                 execution_timeout_s=60)
    land = Step(id="land", kind="merge", merge_branch="plan-wt",
                merge_message="land the build", execution_timeout_s=600)
    return validate(Workflow(
        name="plan-test", repo=repo, base_branch="main", max_parallel=3,
        transient_backoff_s=0,
        paths=(UnitPath(name="plain"),),
        units=(Unit(id="family-a", path="plain"),),
        worktrees=(WorktreeSpec(name="wt", path=repo.parent / "wt",
                                branch="plan-wt", base="main"),),
        phases=(Phase(name="Scout", steps=(scout,), on_step_failure="abort",
                      min_success="all", max_parallel=1),
                Phase(name="Build", steps=(build, check, land),
                      min_success="any"))))


def estimate_file(run_dir: Path) -> None:
    (run_dir / estimate.ESTIMATE_FILE).write_text(json.dumps({
        "schema": estimate.SCHEMA, "generated": "2026-09-30T11:59:00Z",
        "workflow": "plan-test",
        "history": {"sources": 3, "samples": 4, "retry_multiplier": 1.0,
                    "paths": []},
        "run": {"wall_s": {"p50": 300, "p80": 390},
                "tokens": {"p50": 1500, "p80": 1800},
                "cost_usd": 0.25, "confidence": "low", "basis": "fixture"},
        "phases": [
            {"coord": "01.scout", "name": "Scout", "max_parallel": 1,
             "agents": 1, "wall_s": {"p50": 100, "p80": 130},
             "tokens": {"p50": 500, "p80": 600}, "cost_usd": 0.1, "n": 3,
             "basis": "fixture", "confidence": "low"},
            {"coord": "02.build", "name": "Build", "max_parallel": 3,
             "agents": 1, "wall_s": {"p50": 200, "p80": 260},
             "tokens": {"p50": 1000, "p80": 1200}, "cost_usd": 0.15, "n": 4,
             "basis": "fixture", "confidence": "low"}],
        "steps": [
            {"coord": SCOUT, "kind": "agent", "key": ["role-scout", "host", "m"],
             "basis": "fixture", "n": 3, "fallback": False, "confidence": "low",
             "wall_s": {"p50": 100, "p80": 130},
             "tokens": {"p50": 500, "p80": 600}, "cost_usd": 0.1},
            {"coord": BUILD, "kind": "agent", "key": ["role-build", "pi", "m"],
             "basis": "fixture", "n": 4, "fallback": False, "confidence": "low",
             "wall_s": {"p50": 200, "p80": 260},
             "tokens": {"p50": 1000, "p80": 1200}, "cost_usd": 0.15}],
    }), encoding="utf-8")


def null_leaves(block: dict) -> bool:
    for key in ("cost_usd", "n", "basis", "confidence"):
        if block[key] is not None:
            return False
    return all(block[k][p] is None for k in ("wall_s", "tokens")
               for p in ("p50", "p80"))


def file_list(run_dir: Path) -> set[str]:
    return {p.relative_to(run_dir).as_posix() for p in run_dir.rglob("*")}


class PlanPayload(TempCase):

    def setUp(self) -> None:
        super().setUp()
        repo = git_repo(self.tmp / "repo")
        self.workflow = plan_workflow(repo)
        self.dir = self.run_dir("r-plan")
        self.dir.mkdir(parents=True)
        (self.dir / "workflow.json").write_text(
            json.dumps(to_jsonable(self.workflow), indent=2, sort_keys=True),
            encoding="utf-8")
        (self.dir / rundir.HOLD_FILE).write_text(
            json.dumps({"pid": os.getpid(), "since": "2026-10-15T09:00:00Z"}),
            encoding="utf-8")
        self.payload = dashboard_data.plan_data(self.dir, now=T0)

    def step(self, step_id: str) -> dict:
        return next(s for p in self.payload["phases"] for s in p["steps"]
                    if s["id"] == step_id)

    def test_the_full_brief_comes_back_whole(self):
        brief = self.step("scout")["brief"]
        self.assertGreater(len(LONG_BRIEF), 5000)
        self.assertEqual(brief, LONG_BRIEF)
        self.assertNotIn("capped at", brief)

    def test_every_declared_field_of_a_step_is_carried(self):
        build = self.step("build")
        self.assertEqual([c["name"] for c in build["gate"]][:2],
                         ["command_exit", "final_message_matches"])
        self.assertEqual(build["gate"][0]["args"],
                         {"cmd": "npm test", "expect": 0})
        self.assertEqual(build["gate"][0]["text"], "`npm test` exits 0")
        self.assertEqual(build["gate"][1]["text"],
                         "the final message matches /DONE/")
        self.assertEqual(build["handover"]["audience"], "next")
        self.assertEqual(build["handover"]["max_chars"], 4000)
        self.assertEqual(build["handover"]["extra"], ["What broke?"])
        self.assertEqual(build["schema"], SCHEMA)
        self.assertEqual(build["harness_executor"], "pi")
        self.assertNotIn("executor", build)
        self.assertEqual(build["model"], "fake/deterministic")
        self.assertEqual(build["write_scope"], ["src/**"])
        self.assertEqual(build["worktree"], "wt")
        self.assertEqual(build["depends_on"], ["scout"])
        self.assertEqual(build["consumes"], ["scout"])
        self.assertEqual(build["retry"], {"max": 2, "on": ["agent_error"],
                                          "carry_context": False})
        self.assertEqual(build["execution_timeout_s"], 1200)
        self.assertEqual(build["stall_timeout_s"], 300)
        self.assertEqual(build["max_iterations"], 5)
        self.assertEqual(build["command_time_cap_s"], 240)
        self.assertEqual(build["unit"], "family-a")
        self.assertIsNone(build["box"])
        self.assertEqual(build["tools"]["preset"], "default")
        self.assertIn("## Your position in this run", build["position"])
        self.assertIn("Coordinate: 02.build/01.build", build["position"])
        self.assertIn("`npm test` exits 0", build["position"])
        check = self.step("check")
        self.assertEqual(check["kind"], "command")
        self.assertEqual(check["command"], "echo DONE")
        self.assertEqual(check["shell"], "sh")
        self.assertIsNone(check["brief"])
        self.assertEqual(check["gate"], [])
        land = self.step("land")
        self.assertEqual(land["kind"], "merge")
        self.assertEqual(land["merge_branch"], "plan-wt")
        self.assertEqual(land["merge_message"], "land the build")
        self.assertEqual(self.payload["worktrees"][0]["branch"], "plan-wt")

    def test_the_totals_count_executors_checks_and_the_timeout_bound(self):
        totals = self.payload["totals"]
        self.assertEqual(totals["phases"], 2)
        self.assertEqual(totals["steps"], 4)
        self.assertEqual(totals["kinds"],
                         {"agent": 2, "command": 1, "merge": 1, "gate": 0})
        by_model = {(m["harness_executor"], m["model"]): m["n"]
                    for m in totals["by_model"]}
        self.assertEqual(sum(by_model.values()), 2)
        self.assertEqual(by_model[("pi", "fake/deterministic")], 2)
        expected_checks = (len(self.step("scout")["gate"])
                           + len(self.step("build")["gate"]))
        self.assertGreaterEqual(expected_checks, 3)
        self.assertEqual(totals["gate_checks"], expected_checks)
        self.assertEqual(totals["gated_steps"], 2)
        self.assertEqual(totals["retry_steps"], 1)
        self.assertEqual(totals["schemas"], 1)
        self.assertEqual(totals["handovers"],
                         sum(1 for p in self.payload["phases"]
                             for s in p["steps"] if s["handover"]))
        self.assertEqual(totals["worktrees"], 1)
        scout, build = self.payload["phases"]
        self.assertEqual((scout["max_parallel"], scout["waves"],
                          scout["worst_timeout_s"], scout["timeout_bound_s"]),
                         (1, 1, 5400, 5400))
        self.assertEqual((build["max_parallel"], build["declared_max_parallel"],
                          build["waves"], build["worst_timeout_s"],
                          build["timeout_bound_s"]),
                         (3, None, 1, 1200, 1200))
        self.assertEqual(totals["timeout_bound_s"], 6600)

    def test_the_run_block_names_the_hold_and_the_go_command(self):
        run = self.payload["run"]
        self.assertEqual(run["status"], "held")
        self.assertEqual(run["held_since"], "2026-10-15T09:00:00Z")
        self.assertEqual(run["hold_pid"], os.getpid())
        self.assertIn("-m ohflow.cli go --run ", run["go_command"])
        self.assertEqual(run["max_parallel"], 3)
        self.assertEqual(run["base_branch"], "main")
        self.assertEqual(run["plan_stamp"]["size"],
                         (self.dir / "workflow.json").stat().st_size)
        self.assertEqual(self.payload["schema"], dashboard_data.PLAN_SCHEMA)

    def test_the_run_block_follows_the_run_and_the_plan_does_not(self):
        log = RunLog(self.dir, workflow="plan-test")
        log.phase(1, "01.scout", "Scout", [SCOUT], 1)
        log.start(2, SCOUT, 1)
        (self.dir / rundir.HOLD_FILE).unlink()
        after = dashboard_data.plan_data(self.dir, now=T0)
        for block in ("phases", "totals", "worktrees", "estimate"):
            self.assertEqual(after[block], self.payload[block], block)
        self.assertEqual(self.payload["run"]["status"], "held")
        self.assertNotEqual(after["run"]["status"], "held")
        self.assertIsNone(after["run"]["held_since"])
        self.assertIsNone(after["run"]["hold_pid"])
        self.assertEqual(after["run"]["plan_stamp"],
                         self.payload["run"]["plan_stamp"])

    def test_the_estimate_fills_every_block_or_none(self):
        estimate_file(self.dir)
        payload = dashboard_data.plan_data(self.dir, now=T0)
        run = payload["estimate"]
        self.assertEqual((run["wall_s"], run["tokens"], run["cost_usd"],
                          run["n"]),
                         ({"p50": 300, "p80": 390}, {"p50": 1500, "p80": 1800},
                          0.25, 4))
        scout, build = payload["phases"]
        self.assertEqual(scout["estimate"]["wall_s"], {"p50": 100, "p80": 130})
        self.assertEqual(scout["estimate"]["n"], 3)
        self.assertEqual(build["estimate"]["cost_usd"], 0.15)
        step = next(s for s in build["steps"] if s["id"] == "build")
        self.assertEqual(step["estimate"]["tokens"], {"p50": 1000, "p80": 1200})
        self.assertEqual(step["estimate"]["n"], 4)
        command = next(s for s in build["steps"] if s["id"] == "check")
        self.assertTrue(null_leaves(command["estimate"]))
        (self.dir / estimate.ESTIMATE_FILE).unlink()
        payload = dashboard_data.plan_data(self.dir, now=T0)
        self.assertTrue(null_leaves(payload["estimate"]))
        self.assertIsNone(payload["estimate"]["generated"])
        for phase in payload["phases"]:
            self.assertTrue(null_leaves(phase["estimate"]), phase["coord"])
            for step in phase["steps"]:
                self.assertTrue(null_leaves(step["estimate"]), step["coord"])

    def test_a_secret_in_a_brief_is_masked(self):
        brief = self.step("build")["brief"]
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz0123", brief)
        self.assertIn("sk-[redacted]", brief)
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz0123",
                         json.dumps(self.payload))

    def test_the_plan_stamp_follows_a_rewrite_of_workflow_json(self):
        before = dashboard_data.workflow_data(self.dir, now=T0)["run"]["plan_stamp"]
        self.assertEqual(before, self.payload["run"]["plan_stamp"])
        (self.dir / "workflow.json").write_text(
            json.dumps(to_jsonable(self.workflow), indent=4, sort_keys=True),
            encoding="utf-8")
        after = dashboard_data.workflow_data(self.dir, now=T0)["run"]["plan_stamp"]
        self.assertNotEqual(before, after)
        self.assertEqual(after, dashboard_data.plan_data(self.dir, now=T0)
                         ["run"]["plan_stamp"])

    def test_the_run_directory_is_untouched(self):
        before = file_list(self.dir)
        dashboard_data.plan_data(self.dir, now=T0)
        handle = dashboard.start(self.dir)
        self.addCleanup(handle.stop)
        status, _h, _b = get(handle.url + "api/plan")
        self.assertEqual(status, 200)
        self.assertEqual(file_list(self.dir) - before, {dashboard.RECORD})

    def test_a_run_log_without_a_workflow_json_says_the_plan_is_missing(self):
        run = self.run_dir("r-nofile")
        log = RunLog(run)
        log.phase(1, "01.map", "Map", ["01.map/01.a"], 1)
        log.start(2, "01.map/01.a", 1)
        payload = dashboard_data.plan_data(run, now=T0)
        self.assertEqual(payload["run"]["plan_stamp"], None)
        self.assertEqual([p["coord"] for p in payload["phases"]], ["01.map"])
        self.assertIsNone(payload["phases"][0]["steps"][0]["position"])
        self.assertIn("workflow.json is missing", payload["diagnostics"][0])


class PlanRoute(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.run = self.run_dir("r-route")
        plan28(self.run)
        self.handle = dashboard.start(self.run)
        self.addCleanup(self.handle.stop)
        self.base = self.handle.url.rstrip("/")

    def test_the_route_serves_the_plan_of_a_run(self):
        status, headers, body = get(self.base + "/api/plan")
        self.assertEqual(status, 200)
        self.assertTrue(headers["Content-Type"].startswith("application/json"))
        self.assertEqual(headers["Cache-Control"], "no-store")
        payload = json.loads(body)
        self.assertEqual(payload["schema"], "ohflow.plan/1")
        self.assertEqual(payload["totals"]["steps"], 28)
        self.assertEqual(payload["totals"]["phases"], 20)
        self.assertEqual(payload["totals"]["kinds"],
                         {"agent": 11, "command": 12, "merge": 5, "gate": 0})
        self.assertEqual(payload["totals"]["gate_checks"], 55)

    def test_a_packet_answers_404(self):
        handle = dashboard.start(PACKET)
        self.addCleanup(handle.stop)
        status, _h, body = get(handle.url + "api/plan")
        self.assertEqual(status, 404)
        self.assertEqual(body.strip(), b"not found")


class ExitReportEmbedsThePlan(TempCase):

    def test_the_html_report_carries_the_plan_beside_the_read_out(self):
        run = self.run_dir("r-exit")
        workflow_json(run, [("Map", [agent("a", brief="Map the module.")], 1)])
        log = RunLog(run)
        log.phase(1, "01.map", "Map", ["01.map/01.a"], 1)
        log.start(2, "01.map/01.a", 1)
        log.finish(12, "01.map/01.a", 1, "passed", wall=10.0)
        log.settle(13, "01.map", "passed", 1, 1)
        log.run_finished(14, "finished")
        paths = exit_report.write_exit_report(
            run, exit_report.exit_info("finished"), now=T0 + 20)
        html = paths["html"].read_text(encoding="utf-8")
        embedded = html.split(
            '<script id="ohflow-data" type="application/json">', 1)[1].split(
            "</script>", 1)[0]
        read_out = json.loads(embedded)
        self.assertEqual(read_out["schema"], "ohflow.read-out/2")
        self.assertEqual(read_out["plan"]["schema"], "ohflow.plan/1")
        self.assertEqual(read_out["plan"]["phases"][0]["steps"][0]["brief"],
                         "Map the module.")
        record = json.loads(paths["json"].read_text(encoding="utf-8"))
        self.assertNotIn("plan", record)

    def test_the_embedded_plan_reads_the_final_status_of_the_run(self):
        run = self.run_dir("r-interrupted")
        workflow_json(run, [("Map", [agent("a", brief="Map the module.")], 1)])
        self.assertEqual(dashboard_data.plan_data(run)["run"]["status"],
                         "not started")
        paths = exit_report.write_exit_report(
            run, exit_report.exit_info("interrupted"), now=T0 + 20)
        html = paths["html"].read_text(encoding="utf-8")
        read_out = json.loads(html.split(
            '<script id="ohflow-data" type="application/json">', 1)[1].split(
            "</script>", 1)[0])
        self.assertEqual(read_out["run"]["status"], "interrupted")
        self.assertEqual(read_out["plan"]["run"]["status"], "interrupted")


if __name__ == "__main__":
    import unittest
    unittest.main()

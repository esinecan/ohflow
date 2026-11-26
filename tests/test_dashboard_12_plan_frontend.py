"""The page's Plan view renders the whole plan, live and from disk.

The shipping `dashboard.js` is run under node with a small DOM in place of
the browser, over the real `/api/plan` payload of the 28-step fixture: twenty
phase sections, twenty-eight step rows, the strip's counts, the held banner,
phase 1 open and the rest folded, a drawer that shows a 3,000-character brief
whole, the gate tab in words, the search, and the expand-all control. The
same renderer reads the plan an exit report embeds, with no server. A gate
step reads as a gate step, a step `estimate.json` calls mechanical or cached
says so, and `Inspect the plan` stays in place where no plan can exist.
"""

from __future__ import annotations

import json
import shutil
import subprocess

from dashboard_support import PLAN28_LONG_BRIEF, RunLog, T0, plan28
from ohflow import dashboard, dashboard_data, estimate, exit_report
from ohflow.workflow import (CheckSpec, GateSpec, Phase, Step, Workflow,
                             to_jsonable, validate)
from support import TempCase, agent_step, git_repo

ASSETS = dashboard.ASSET_ROOT
CONSOLIDATE = "04.consolidate/01.consolidate"

DOM = r"""
const fs = require("node:fs");
const vm = require("node:vm");
let document;
class Element {
  constructor(tag) {
    this.nodeType = 1; this.tagName = tag; this.children = []; this.dataset = {}; this.attrs = {};
    this.className = ""; this.hidden = false; this.open = false; this.id = ""; this.text = null;
    this.parentElement = null; this.style = {setProperty() {}};
    const values = new Set();
    this.classList = {
      add: (...names) => names.forEach(name => values.add(name)),
      remove: (...names) => names.forEach(name => values.delete(name)),
      toggle: (name, on) => on ? values.add(name) : values.delete(name),
      contains: name => values.has(name)
    };
  }
  get textContent() { return this.text !== null ? this.text : this.children.map(child => child.textContent).join(""); }
  set textContent(value) {
    if (this.tagName === "#text") { this.text = String(value); return; }
    this.children = []; this.text = null;
    if (String(value) !== "") this.appendChild(textNode(String(value)));
  }
  appendChild(child) { this.children.push(child); child.parentElement = this; return child; }
  replaceChildren(...children) { this.children = []; children.forEach(child => this.appendChild(child)); }
  setAttribute(name, value) { this.attrs[name] = String(value); if (name === "id") this.id = String(value); }
  getAttribute(name) { return name in this.attrs ? this.attrs[name] : null; }
  addEventListener() {}
}
function textNode(text) { const item = new Element("#text"); item.text = text; return item; }
const ids = { "plan-view": new Element("section"), "ohflow-data": new Element("script") };
document = {
  getElementById: id => ids[id] || null,
  createElement: tag => new Element(tag),
  createElementNS: (_ns, tag) => new Element(tag),
  createTextNode: textNode,
  querySelectorAll: () => [], addEventListener() {}
};
const context = {__OHFLOW_TEST__: true, document, window: {setTimeout() {}},
  requestAnimationFrame: fn => fn(), console: {error() {}}, setTimeout() {},
  clearTimeout() {}, Intl, Date, URLSearchParams};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), context);
const api = context.__OHFLOW_TEST_API__;
function all(node, predicate, out) {
  out = out || [];
  if (predicate(node)) out.push(node);
  node.children.forEach(child => all(child, predicate, out));
  return out;
}
const hasClass = (node, name) => (" " + node.className + " ").indexOf(" " + name + " ") >= 0;
const host = () => document.getElementById("plan-view");
const phases = () => all(host(), node => node.tagName === "details" && hasClass(node, "plan-phase"));
const rows = () => all(host(), node => node.tagName === "tr" && hasClass(node, "plan-step"));
"""

LIVE = DOM + r"""
const PLAN = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
api.state.plan = PLAN;
api.state.workflow = {run: {id: PLAN.run.id, status: "held"},
  phases: PLAN.phases.map(phase => ({coord: phase.coord, state: "waiting"}))};
api.renderPlanView();
const strip = all(host(), node => hasClass(node, "plan-strip"))[0];
const banner = all(host(), node => hasClass(node, "held-banner"))[0];
const before = {
  phases: phases().length, rows: rows().length,
  open: phases().filter(phase => phase.open).map(phase => phase.dataset.planPhase),
  strip: strip.textContent, banner: banner ? banner.textContent : null,
  drawers: all(host(), node => hasClass(node, "plan-drawer")).length,
  chips: all(host(), node => node.dataset.planChip).map(node => node.textContent)
};
const long = PLAN.phases.flatMap(phase => phase.steps).find(step => step.brief && step.brief.length > 2000);
api.togglePlanDrawer(long.coord);
const brief = all(host(), node => node.tagName === "pre" && hasClass(node, "plan-brief"))[0];
const openAfterDrawer = phases().filter(phase => phase.open).map(phase => phase.dataset.planPhase);
const openButton = all(host(), node => node.dataset.planStep === long.coord)[0];
api.setPlanTab(long.coord, "gate");
const gateItems = all(host(), node => node.tagName === "li" && node.parentElement && hasClass(node.parentElement, "plan-gate"));
api.setPlanTab(long.coord, "position");
const position = all(host(), node => node.tagName === "pre" && hasClass(node, "plan-position"))[0];
api.state.search = "quokka";
api.renderPlanView();
const searched = rows().map(row => row.dataset.planRow);
api.state.search = "";
api.setPlanPhases(true);
const allOpen = phases().every(phase => phase.open);
api.setPlanPhases(false);
const noneOpen = phases().every(phase => !phase.open);
console.log(JSON.stringify({
  before, briefWhole: !!brief && brief.textContent === long.brief,
  briefLength: brief ? brief.textContent.length : null, openAfterDrawer,
  openButtonLabel: openButton ? openButton.textContent : null,
  gateItems: gateItems.length, gateFirst: gateItems.length ? gateItems[0].textContent : null,
  positionStart: position ? position.textContent.slice(0, 28) : null,
  searched, allOpen, noneOpen
}));
"""

EMBEDDED = DOM + r"""
document.getElementById("ohflow-data").textContent = fs.readFileSync(process.argv[2], "utf8");
api.parseEmbedded();
api.renderPlanView();
console.log(JSON.stringify({
  static: api.state.static, planSchema: api.state.plan ? api.state.plan.schema : null,
  phases: phases().length, rows: rows().length,
  heading: all(host(), node => node.id === "plan-view-heading")[0].textContent
}));
"""


KINDS = DOM + r"""
const PLAN = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
api.state.plan = PLAN;
api.state.workflow = {run: {id: PLAN.run.id, status: "held"}, phases: []};
api.renderPlanView();
const cells = {};
rows().forEach(row => {
  cells[row.dataset.planRow.split("/").pop()] = {
    model: row.children[3].textContent, forecast: row.children[11].textContent};
});
const gate = PLAN.phases.flatMap(phase => phase.steps).find(step => step.kind === "gate");
api.togglePlanDrawer(gate.coord);
const selected = all(host(), node => node.dataset.planTab === gate.coord
  && node.getAttribute("aria-selected") === "true").map(node => node.dataset.tab);
const body = () => all(host(), node => hasClass(node, "plan-drawer-body"))[0].textContent;
const gateBody = body();
api.setPlanTab(gate.coord, "command");
const commandBody = body();
api.setPlanTab(gate.coord, "brief");
const briefBody = body();
console.log(JSON.stringify({cells, selected, gateBody, commandBody, briefBody}));
"""

INSPECT = DOM + r"""
const listeners = {};
document.getElementById = id => ids[id] || (ids[id] = new Element("div"));
document.addEventListener = (type, fn) => { if (!listeners[type]) listeners[type] = fn; };
document.querySelector = () => null;
context.window.addEventListener = () => {};
context.requestAnimationFrame = () => {};
Element.prototype.contains = () => false;
Element.prototype.querySelector = () => null;
Element.prototype.querySelectorAll = () => [];
const COORD = "01.map/01.scout";
const button = {closest: sel => sel === "[data-select-step]" ? {dataset: {selectStep: COORD}} : null};
let fetched = 0;
context.fetch = () => { fetched += 1; return Promise.reject(new Error("404")); };
api.bindEvents();
function click(workflow, isStatic) {
  api.state.workflow = workflow; api.state.static = isStatic; api.state.plan = null;
  api.state.planError = null; api.state.view = "workflow"; api.state.selectedStep = null;
  listeners.click({target: button});
  return {view: api.state.view, selected: api.state.selectedStep,
          planView: host().textContent};
}
const workflow = source => ({source, run: {id: "r", status: "passed"}, phases: [],
  invocations: [], edges: [], events: [],
  steps: [{coord: COORD, id: "scout", role: "scout", kind: "agent", plan: {}}]});
const packet = click(workflow("packet"), false);
const report = click(workflow("run"), true);
const afterStatic = fetched;
const live = click(workflow("run"), false);
console.log(JSON.stringify({packet, report, afterStatic, liveView: live.view}));
"""


def run_node(script: str, *args: str):
    node = shutil.which("node")
    if node is None:
        return None
    return subprocess.run([node, "-e", script, *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          timeout=300)


class PlanViewSource(TempCase):

    def test_the_shell_has_the_plan_button_and_the_view(self):
        page = dashboard.TEMPLATE.read_text(encoding="utf-8")
        self.assertIn('data-view="plan"', page)
        self.assertIn('id="plan-view"', page)
        self.assertLess(page.index('data-view="workflow"'), page.index('data-view="plan"'))
        self.assertLess(page.index('data-view="plan"'), page.index('data-view="compare"'))

    def test_the_script_fetches_the_plan_once_and_opens_a_held_run_on_it(self):
        script = (ASSETS / "dashboard.js").read_text(encoding="utf-8")
        self.assertIn('requestJson("/api/plan")', script)
        self.assertEqual(script.count('requestJson("/api/plan")'), 1)
        self.assertIn("function renderPlanView", script)
        self.assertIn("plan_stamp", script)
        self.assertIn('if (heldRun()) S.view = "plan";', script)
        self.assertIn("function openPlanStep", script)


class PlanViewRenders(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.run = self.run_dir("r-plan28")
        plan28(self.run)
        self.plan = dashboard_data.plan_data(self.run, now=T0)
        self.plan_path = self.tmp / "plan.json"
        self.plan_path.write_text(json.dumps(self.plan), encoding="utf-8")

    def test_the_live_view_shows_the_whole_plan(self):
        result = run_node(LIVE, str(dashboard.STATIC_ASSETS["/dashboard.js"][0]),
                          str(self.plan_path))
        if result is None:
            self.skipTest("node is not installed")
        self.assertEqual(result.returncode, 0, result.stderr)
        seen = json.loads(result.stdout)
        totals = self.plan["totals"]
        before = seen["before"]
        self.assertEqual(before["phases"], 20)
        self.assertEqual(before["rows"], 28)
        self.assertEqual(before["open"], ["01.sweep"])
        self.assertEqual(before["drawers"], 0)
        self.assertEqual(len(before["chips"]), 20)
        self.assertEqual(set(before["chips"]), {"Waiting"})
        self.assertIn("20 phases · 28 steps", before["strip"])
        self.assertIn("11 agent · 12 command · 5 merge", before["strip"])
        self.assertIn(f"{totals['gate_checks']} gate checks on "
                      f"{totals['gated_steps']} steps", before["strip"])
        self.assertIn("6 × claude · claude-opus-5-5 · effort high", before["strip"])
        self.assertIn("5 × claude · claude-sonnet-5-5 · effort high", before["strip"])
        self.assertIn("no estimate.json for this run", before["strip"])
        self.assertIn("Held: waiting for go", before["banner"])
        self.assertIn(self.plan["run"]["go_command"], before["banner"])
        self.assertTrue(seen["briefWhole"])
        self.assertEqual(seen["briefLength"], len(PLAN28_LONG_BRIEF))
        self.assertGreater(seen["briefLength"], dashboard_data.STRING_CAP)
        self.assertEqual(seen["openAfterDrawer"], ["01.sweep", "04.consolidate"])
        self.assertEqual(seen["openButtonLabel"], "Close")
        self.assertEqual(seen["gateItems"], 5)
        self.assertTrue(seen["gateFirst"].startswith(
            "commits past the step's start >= 1"), seen["gateFirst"])
        self.assertEqual(seen["positionStart"], "## Your position in this run")
        self.assertEqual(seen["searched"], [CONSOLIDATE])
        self.assertTrue(seen["allOpen"])
        self.assertTrue(seen["noneOpen"])

    def test_the_view_renders_from_the_embedded_report_with_no_server(self):
        log = RunLog(self.run, workflow="plan28")
        log.phase(1, "01.sweep", "Sweep", ["01.sweep/01.sweep-a"], 3)
        log.start(2, "01.sweep/01.sweep-a", 1)
        log.finish(12, "01.sweep/01.sweep-a", 1, "failed", wall=10.0,
                   error="the sweep stopped")
        log.settle(13, "01.sweep", "failed", 0, 5)
        log.run_finished(14, "failed")
        paths = exit_report.write_exit_report(
            self.run, exit_report.exit_info("failed"), now=T0 + 20)
        html = paths["html"].read_text(encoding="utf-8")
        embedded = html.split(
            '<script id="ohflow-data" type="application/json">', 1)[1].split(
            "</script>", 1)[0]
        data_path = self.tmp / "embedded.json"
        data_path.write_text(embedded, encoding="utf-8")
        result = run_node(EMBEDDED, str(dashboard.STATIC_ASSETS["/dashboard.js"][0]),
                          str(data_path))
        if result is None:
            self.skipTest("node is not installed")
        self.assertEqual(result.returncode, 0, result.stderr)
        seen = json.loads(result.stdout)
        self.assertTrue(seen["static"])
        self.assertEqual(seen["planSchema"], "ohflow.plan/1")
        self.assertEqual(seen["phases"], 20)
        self.assertEqual(seen["rows"], 28)
        self.assertTrue(seen["heading"].startswith("Plan: every phase"))


class PlanViewStepKinds(TempCase):
    """The rows of a gate step, a command step and a cached agent step, over
    the `estimate.json` that `estimate.py` writes for them."""

    def setUp(self) -> None:
        super().setUp()
        repo = git_repo(self.tmp / "repo")
        gate = GateSpec(checks=(CheckSpec("command_exit",
                                          {"cmd": "npm test", "expect": 0}),))
        workflow = validate(Workflow(
            name="plan-kinds", repo=repo, base_branch="main",
            phases=(Phase(name="Work", steps=(
                agent_step("scout", brief="Scout the module."),
                agent_step("reuse", brief="Scout it again."),
                Step(id="build", kind="command", command="echo DONE"),
                Step(id="verify", kind="gate", gate=gate))),)))
        self.run = self.run_dir("r-kinds")
        self.run.mkdir(parents=True)
        (self.run / "workflow.json").write_text(
            json.dumps(to_jsonable(workflow), indent=2, sort_keys=True),
            encoding="utf-8")
        estimate.write_estimate(self.run, estimate.estimate_workflow(
            workflow, estimate.Prior([]), cached=["01.work/02.reuse"], now=T0))
        self.plan = dashboard_data.plan_data(self.run, now=T0)
        self.plan_path = self.tmp / "plan.json"
        self.plan_path.write_text(json.dumps(self.plan), encoding="utf-8")

    def seen(self) -> dict:
        result = run_node(KINDS, str(dashboard.STATIC_ASSETS["/dashboard.js"][0]),
                          str(self.plan_path))
        if result is None:
            self.skipTest("node is not installed")
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_the_estimate_file_has_the_shape_estimate_py_writes(self):
        steps = {s["id"]: s["estimate"] for p in self.plan["phases"]
                 for s in p["steps"]}
        self.assertEqual(steps["build"]["basis"], estimate.MECHANICAL)
        self.assertEqual(steps["build"]["wall_s"], {"p50": 0, "p80": 0})
        self.assertEqual(steps["verify"]["basis"], estimate.MECHANICAL)
        self.assertEqual(steps["reuse"]["basis"], estimate.CACHED)
        self.assertEqual(steps["reuse"]["wall_s"], {"p50": 0, "p80": 0})
        self.assertIsNone(steps["scout"]["wall_s"]["p50"])

    def test_a_mechanical_or_cached_step_names_its_basis_as_its_forecast(self):
        cells = self.seen()["cells"]
        self.assertEqual(cells["03.build"]["forecast"], "mechanical")
        self.assertEqual(cells["04.verify"]["forecast"], "mechanical")
        self.assertEqual(cells["02.reuse"]["forecast"], "cached")
        self.assertEqual(cells["01.scout"]["forecast"], "no sample")

    def test_a_gate_step_reads_as_a_gate_step(self):
        seen = self.seen()
        self.assertEqual(seen["cells"]["04.verify"]["model"], "gate only, no agent")
        self.assertTrue(seen["cells"]["03.build"]["model"].startswith("shell "))
        self.assertEqual(seen["selected"], ["gate"])
        self.assertIn("command_exit", seen["gateBody"])
        self.assertIn("A gate step has no command", seen["commandBody"])
        self.assertNotIn("An agent step", seen["commandBody"])
        self.assertIn("this is a gate step", seen["briefBody"])
        self.assertNotIn("Its command is under Command", seen["briefBody"])


class InspectThePlanWithoutAPlan(TempCase):

    def test_a_packet_and_a_report_without_a_plan_keep_the_inspector_in_place(self):
        result = run_node(INSPECT, str(dashboard.STATIC_ASSETS["/dashboard.js"][0]))
        if result is None:
            self.skipTest("node is not installed")
        self.assertEqual(result.returncode, 0, result.stderr)
        seen = json.loads(result.stdout)
        for page in ("packet", "report"):
            self.assertEqual(seen[page]["view"], "workflow", page)
            self.assertEqual(seen[page]["selected"], "01.map/01.scout", page)
            self.assertNotIn("could not be loaded", seen[page]["planView"], page)
        self.assertEqual(seen["afterStatic"], 0)
        self.assertEqual(seen["liveView"], "plan")


if __name__ == "__main__":
    import unittest
    unittest.main()

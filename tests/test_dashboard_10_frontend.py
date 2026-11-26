"""The approved dashboard shell uses real APIs and remains standalone offline.

The oversized-record tests here drive the real shipping page over real HTTP
and then run the real `dashboard_records.js` assembler (the exact asset the
page loads) over the responses, so a reconstruction failure fails the suite
rather than silently losing transcript content in the browser.
"""

from __future__ import annotations

import json
import hashlib
import shutil
import subprocess

from ohflow import dashboard, dashboard_data, exit_report
from support import TempCase
from test_dashboard_08_transcript import PACKET, get, make_packet

REVIEW = "02.review/01.review"


def run_node(script: str, *args: str):
    node = shutil.which("node")
    if node is None:
        return None
    return subprocess.run([node, "-e", script, *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          timeout=300)


class ShippingAssets(TempCase):

    def setUp(self):
        super().setUp()
        self.handle = dashboard.start(PACKET)
        self.addCleanup(self.handle.stop)
        self.base = self.handle.url.rstrip("/")

    def test_page_and_fixed_assets_are_served_without_a_file_mapper(self):
        status, page = get(self.base + "/")
        self.assertEqual(status, 200)
        self.assertIn(b'href="/dashboard.css"', page)
        self.assertIn(b'src="/dashboard.js"', page)
        for path, marker in (
                ("/dashboard.css", b".invocation-node"),
                ("/dashboard.js", b"function renderGraph"),
                ("/dashboard_records.js", b"function createLedger"),
                ("/assets/lexend-variable.ttf", b"\x00\x01\x00\x00")):
            status, body = get(self.base + path)
            self.assertEqual(status, 200, path)
            self.assertIn(marker, body)
        status, _body = get(self.base + "/assets/../dashboard.py")
        self.assertEqual(status, 404)

    def test_the_assembler_asset_loads_before_the_renderer(self):
        status, page = get(self.base + "/")
        self.assertEqual(status, 200)
        records = page.index(b'src="/dashboard_records.js"')
        renderer = page.index(b'src="/dashboard.js"')
        self.assertLess(records, renderer)

    def test_shell_has_real_controls_and_accessible_inspector_tabs(self):
        page = dashboard.TEMPLATE.read_text(encoding="utf-8")
        self.assertIn('data-view="order"', page)
        self.assertIn('data-view="compare"', page)
        self.assertIn('role="tablist"', page)
        self.assertIn('role="tooltip"', page)
        self.assertIn('aria-live="polite"', page)
        self.assertIn(exit_report.DATA_SLOT, page)
        self.assertIn(exit_report.TIMELINE_SLOT, page)

    def test_finished_state_and_loaded_count_share_a_reserved_status_row(self):
        page = dashboard.TEMPLATE.read_text(encoding="utf-8")
        start = page.index('<div class="transcript-status-row">')
        end = page.index("</div>", start)
        status_row = page[start:end]
        self.assertIn('id="follow-explanation"', status_row)
        self.assertIn('id="loaded-count"', status_row)

    def test_dynamic_source_uses_safe_dom_text_not_html_injection(self):
        source = dashboard.STATIC_ASSETS["/dashboard.js"][0].read_text(
            encoding="utf-8")
        self.assertIn("textContent", source)
        self.assertNotIn("innerHTML", source)
        self.assertIn("encodeURIComponent(inv.coord)", source)
        self.assertIn("block.type === \"tool_result\"", source)

    def test_renderer_retains_one_inspector_through_async_compare_rebuilds(self):
        """Exercise the shipping renderer's DOM-ownership functions, not a
        source-string proxy: an async Compare refresh and two view moves keep
        the same inspector node and its live reader state."""
        script = r"""
const fs = require("node:fs");
const vm = require("node:vm");
let document;
class Element {
  constructor(tag, id) {
    this.nodeType = 1; this.tagName = tag; this.id = id || ""; this.children = [];
    this.parentElement = null; this.dataset = {}; this.className = "";
    this.hidden = false; this.value = ""; this.scrollTop = 0;
    this.scrollLeft = 0; this.textContent = ""; this.open = false;
    const values = new Set();
    this.classList = {
      add: (...names) => names.forEach(name => values.add(name)),
      remove: (...names) => names.forEach(name => values.delete(name)),
      toggle: (name, on) => on ? values.add(name) : values.delete(name)
    };
  }
  appendChild(child) {
    if (child.parentElement) child.parentElement.children =
      child.parentElement.children.filter(item => item !== child);
    this.children.push(child); child.parentElement = this; return child;
  }
  replaceChildren(...children) {
    this.children.forEach(child => { child.parentElement = null; });
    this.children = []; children.forEach(child => this.appendChild(child));
  }
  contains(wanted) {
    return this === wanted || this.children.some(child => child.contains(wanted));
  }
  setAttribute(name, value) { this[name] = String(value); }
  focus() { document.activeElement = this; }
}
const root = new Element("body", "root");
function find(node, id) {
  if (node.id === id) return node;
  for (const child of node.children) { const hit = find(child, id); if (hit) return hit; }
  return null;
}
document = {
  activeElement: null, title: "",
  getElementById: id => find(root, id),
  createElement: tag => new Element(tag),
  createElementNS: (_ns, tag) => new Element(tag),
  createTextNode: text => { const item = new Element("text"); item.textContent = text; return item; }
};
const overview = root.appendChild(new Element("div", "overview-layout"));
const compare = root.appendChild(new Element("section", "compare-view"));
const oldSlot = compare.appendChild(new Element("div", "old-slot"));
const parking = root.appendChild(new Element("div", "inspector-parking"));
const inspector = oldSlot.appendChild(new Element("aside", "inspector"));
const search = inspector.appendChild(new Element("input", "transcript-search"));
const panel = inspector.appendChild(new Element("section", "panel-transcript"));
inspector.appendChild(new Element("section", "panel-overview"));
inspector.appendChild(new Element("section", "panel-checks"));
inspector.appendChild(new Element("section", "panel-artifacts"));
const disclosure = inspector.appendChild(new Element("details", "open-source-events"));
search.value = "failing test"; panel.scrollTop = 413; panel.scrollLeft = 17;
disclosure.open = true; search.focus();
const context = {
  __OHFLOW_TEST__: true, document, window: {setTimeout: fn => fn()},
  requestAnimationFrame: fn => fn(), console: {error() {}},
  setTimeout: fn => fn(), clearTimeout() {}, Intl, Date, URLSearchParams
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), context);
const api = context.__OHFLOW_TEST_API__;
api.state.selected = "impl@5"; api.state.search = "gate";
api.state.transcripts.set("impl@5", {follow: true});
const original = inspector;
function countInspector(node) {
  return (node.id === "inspector" ? 1 : 0)
    + node.children.reduce((sum, child) => sum + countInspector(child), 0);
}
(async () => {
  const shell1 = new Element("div", "compare-shell-1");
  const slot1 = shell1.appendChild(new Element("div", "slot-1"));
  await Promise.resolve(); // evidence arrival / poll boundary
  api.replaceCompareContents(compare, shell1, slot1);
  const first = document.getElementById("inspector");
  const snapshot = api.captureInspectorState(first);
  api.adoptInspector(overview, snapshot, false); // Start order
  const shell2 = new Element("div", "compare-shell-2");
  const slot2 = shell2.appendChild(new Element("div", "slot-2"));
  await Promise.resolve(); // later transcript arrival
  api.replaceCompareContents(compare, shell2, slot2); // Compare again
  const retained = document.getElementById("inspector");
  console.log(JSON.stringify({
    sameNode: retained === original, count: countInspector(root),
    parent: retained.parentElement.id, search: search.value,
    top: panel.scrollTop, left: panel.scrollLeft, disclosure: disclosure.open,
    focused: document.activeElement === search,
    selected: api.state.selected, globalSearch: api.state.search,
    follow: api.state.transcripts.get("impl@5").follow,
    parkedOnlyDuringReplacement: parking.children.length === 0
  }));
})().catch(error => { console.error(error); process.exit(1); });
"""
        result = run_node(script, str(dashboard.STATIC_ASSETS[
            "/dashboard.js"][0]))
        self.assertIsNotNone(result)
        self.assertEqual(result.returncode, 0, result.stderr)
        seen = json.loads(result.stdout)
        self.assertEqual(seen, {
            "sameNode": True, "count": 1, "parent": "slot-2",
            "search": "failing test", "top": 413, "left": 17,
            "disclosure": True, "focused": True,
            "selected": "impl@5", "globalSearch": "gate",
            "follow": True, "parkedOnlyDuringReplacement": True,
        })

    def test_compare_claim_is_compact_but_keeps_the_complete_recorded_text(self):
        script = r"""
const fs = require("node:fs");
const vm = require("node:vm");
class Element {
  constructor(tag) {
    this.nodeType = 1; this.tagName = tag; this.children = []; this.dataset = {};
    this.className = ""; this.textContent = ""; this.open = false;
  }
  appendChild(child) { this.children.push(child); return child; }
  setAttribute(name, value) { this[name] = String(value); }
}
const document = {
  getElementById() { return null; },
  createElement: tag => new Element(tag),
  createElementNS: (_ns, tag) => new Element(tag),
  createTextNode: text => { const item = new Element("text"); item.textContent = text; return item; }
};
const context = {__OHFLOW_TEST__: true, document, window: {setTimeout() {}},
  console: {error() {}}, Intl, Date, URLSearchParams};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), context);
const api = context.__OHFLOW_TEST_API__;
const full = "BEGIN " + "recorded claim ".repeat(20) + "END";
api.state.evidence.set("impl@5", {status: "ready", data: {final_message: full}});
function find(node, className) {
  if (node.className === className) return node;
  for (const child of node.children) { const hit = find(child, className); if (hit) return hit; }
  return null;
}
const compact = api.compareClaim({id: "impl@5"});
const preview = find(compact, "claim-preview");
const disclosure = find(compact, "compare-claim-disclosure");
const complete = find(compact, "compare-claim-full");
api.state.disclosures.add("impl@5:claim");
const expanded = find(api.compareClaim({id: "impl@5"}), "compare-claim-disclosure");
console.log(JSON.stringify({
  previewIsShort: preview.textContent.length < full.length && preview.textContent.endsWith("…"),
  initiallyClosed: !disclosure.open,
  disclosureKey: disclosure.dataset.disclosure,
  fullText: complete.textContent,
  stateReopens: expanded.open
}));
"""
        result = run_node(script, str(dashboard.STATIC_ASSETS[
            "/dashboard.js"][0]))
        self.assertIsNotNone(result)
        self.assertEqual(result.returncode, 0, result.stderr)
        seen = json.loads(result.stdout)
        self.assertTrue(seen["previewIsShort"])
        self.assertTrue(seen["initiallyClosed"])
        self.assertEqual(seen["disclosureKey"], "impl@5:claim")
        self.assertEqual(seen["fullText"],
                         "BEGIN " + "recorded claim " * 20 + "END")
        self.assertTrue(seen["stateReopens"])

    def test_compare_edit_disclosure_overrides_reader_mode_and_survives_rerenders(self):
        """The Compare edit button owns old/new visibility even while the
        transcript reader expands every ordinary long record body."""
        script = r"""
const fs = require("node:fs");
const vm = require("node:vm");
class Element {
  constructor(tag) {
    this.nodeType = 1; this.tagName = tag; this.children = []; this.dataset = {};
    this.className = ""; this.textContent = "";
  }
  appendChild(child) { this.children.push(child); return child; }
  setAttribute(name, value) { this[name] = String(value); }
}
const document = {
  getElementById() { return null; },
  createElement: tag => new Element(tag),
  createElementNS: (_ns, tag) => new Element(tag),
  createTextNode: text => { const item = new Element("text"); item.textContent = text; return item; }
};
const context = {__OHFLOW_TEST__: true, document, window: {setTimeout() {}},
  console: {error() {}}, Intl, Date, URLSearchParams};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), context);
const api = context.__OHFLOW_TEST_API__;
const editKey = "impl@5:edit";
api.state.readerAll = true;
api.state.transcripts.set("impl@5", {ledger: {records: [{id: "001", blocks: [{
  type: "tool_call", input: {file_path: "README.md",
    old_string: "old value ".repeat(90), new_string: "new value ".repeat(90)}
}]}]}});
function find(node, predicate) {
  if (predicate(node)) return node;
  for (const child of node.children) { const hit = find(child, predicate); if (hit) return hit; }
  return null;
}
function snapshot() {
  const excerpt = api.changeExcerpt({id: "impl@5"});
  const button = find(excerpt, node => node.dataset.expand === editKey);
  return {open: excerpt.className.includes(" open"),
    expanded: button["aria-expanded"], label: button.textContent};
}
(async () => {
  const initially = snapshot();
  const ordinaryBody = api.clampedBody("record:1:text", "record-block", "long text ".repeat(100));
  api.toggleExpanded(editKey);
  await Promise.resolve(); // async evidence arrival / Compare rebuild boundary
  const expandedAfterAsyncRerender = snapshot();
  api.state.view = "order";
  api.state.view = "compare";
  const expandedAfterViewSwitch = snapshot();
  api.toggleExpanded(editKey);
  const collapsedAgain = snapshot();
  console.log(JSON.stringify({
    initially, expandedAfterAsyncRerender, expandedAfterViewSwitch, collapsedAgain,
    ordinaryBodyOpen: ordinaryBody.className.includes(" open"),
    readerModeStillOn: api.state.readerAll
  }));
})().catch(error => { console.error(error); process.exit(1); });
"""
        result = run_node(script, str(dashboard.STATIC_ASSETS[
            "/dashboard.js"][0]))
        self.assertIsNotNone(result)
        self.assertEqual(result.returncode, 0, result.stderr)
        seen = json.loads(result.stdout)
        self.assertEqual(seen["initially"], {
            "open": False, "expanded": "false", "label": "Show full edit",
        })
        self.assertEqual(seen["expandedAfterAsyncRerender"], {
            "open": True, "expanded": "true", "label": "Hide full edit",
        })
        self.assertEqual(seen["expandedAfterViewSwitch"],
                         seen["expandedAfterAsyncRerender"])
        self.assertEqual(seen["collapsedAgain"], seen["initially"])
        self.assertTrue(seen["ordinaryBodyOpen"])
        self.assertTrue(seen["readerModeStillOn"])

    def test_render_exceptions_do_not_masquerade_as_server_disconnects(self):
        script = r"""
const fs = require("node:fs");
const vm = require("node:vm");
let document;
class Element {
  constructor(tag, id) { this.nodeType = 1; this.tagName = tag; this.id = id || "";
    this.children = []; this.parentElement = null; this.hidden = true;
    this.textContent = ""; this.className = ""; this.dataset = {};
    this.classList = {add() {}, remove() {}, toggle() {}}; }
  appendChild(child) { this.children.push(child); child.parentElement = this; return child; }
  replaceChildren(...children) { this.children = []; children.forEach(child => this.appendChild(child)); }
  contains(wanted) { return this === wanted || this.children.some(child => child.contains(wanted)); }
  setAttribute(name, value) { this[name] = String(value); }
}
const root = new Element("body", "root");
for (const id of ["run-title", "run-status", "run-counts", "workflow-title",
  "workflow-summary", "offline-banner", "live-status"]) root.appendChild(new Element("div", id));
function find(node, id) { if (node.id === id) return node;
  for (const child of node.children) { const hit = find(child, id); if (hit) return hit; }
  return null; }
document = {activeElement: null, title: "", getElementById: id => find(root, id),
  createElement: tag => new Element(tag), createElementNS: (_ns, tag) => new Element(tag),
  createTextNode: text => { const item = new Element("text"); item.textContent = text; return item; }};
const context = {__OHFLOW_TEST__: true, document, window: {setTimeout() {}},
  console: {error() {}}, Intl, Date, URLSearchParams};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), context);
const api = context.__OHFLOW_TEST_API__;
api.state.workflow = {run: {id: "run", status: "finished", finished: null},
  phases: [], steps: [], invocations: [], edges: [], cached: []};
api.state.connected = true;
api.reportRenderFailure(new Error("broken view"));
const renderState = {connected: api.state.connected,
  banner: document.getElementById("offline-banner").textContent,
  live: document.getElementById("live-status").textContent};
api.reportRequestFailure(new Error("connection refused"));
console.log(JSON.stringify({renderState, requestState: {
  connected: api.state.connected,
  banner: document.getElementById("offline-banner").textContent
}}));
"""
        result = run_node(script, str(dashboard.STATIC_ASSETS[
            "/dashboard.js"][0]))
        self.assertIsNotNone(result)
        self.assertEqual(result.returncode, 0, result.stderr)
        seen = json.loads(result.stdout)
        self.assertTrue(seen["renderState"]["connected"])
        self.assertIn("could not be rendered", seen["renderState"]["banner"])
        self.assertNotIn("dashboard stopped", seen["renderState"]["banner"])
        self.assertIn("broken view", seen["renderState"]["live"])
        self.assertFalse(seen["requestState"]["connected"])
        self.assertIn("dashboard stopped", seen["requestState"]["banner"])


class ContinuationAssembly(TempCase):
    """The real review-attempt transcript ships 110 logical records as 112
    rows: record L16 (34,794 canonical chars) travels as three
    `ohflow.record-json/1` fragments. The shipping client must join them."""

    def setUp(self):
        super().setUp()
        self.handle = dashboard.start(PACKET)
        self.addCleanup(self.handle.stop)
        self.base = self.handle.url.rstrip("/")
        self.module = dashboard.STATIC_ASSETS["/dashboard_records.js"][0]

    def test_review_att03_reconstructs_every_logical_record_in_order(self):
        # The server-side truth this must match, computed independently.
        cursor, expected_rows, fragments = None, 0, []
        while True:
            block = dashboard_data.transcript_data(
                PACKET, REVIEW, 3, cursor=cursor, limit=100)
            expected_rows += len(block["records"])
            fragments += [r for r in block["records"] if r.get("continuation")]
            cursor = block["next_cursor"]
            if block["complete"] and not block["has_more"]:
                break
        joined = "".join(f["continuation"]["data"] for f in fragments)
        expected = json.loads(joined)
        expected_text = expected["blocks"][0]["text"]

        script = """
const api = require(process.argv[1]);
const base = process.argv[2];
(async () => {
  const ledger = api.createLedger();
  let cursor = null, rows = 0;
  for (let i = 0; i < 40; i++) {
    const url = base + "/api/transcript?coord="
      + encodeURIComponent("02.review/01.review")
      + "&attempt=3&limit=100"
      + (cursor ? "&cursor=" + encodeURIComponent(cursor) : "");
    const response = await fetch(url);
    if (!response.ok) throw new Error("HTTP " + response.status);
    const block = await response.json();
    if (block.reset) ledger.reset();
    ledger.absorb(block.records || []);
    rows += (block.records || []).length;
    cursor = block.next_cursor;
    if (block.complete && !block.has_more) break;
  }
  const ids = ledger.records.map(r => r.id);
  const l16 = ledger.records.find(r => r.id === "L16");
  const text = l16.blocks[0].text;
  const ordered = ids.every((id, i) =>
    i === 0 || Number(id.slice(1)) > Number(ids[i - 1].slice(1)));
  console.log(JSON.stringify({
    rows, logical: ledger.loadedCount(),
    placeholders: ledger.records.filter(r => r.continuing).length,
    unique: new Set(ids).size, ordered,
    l16Len: text.length, head: text.slice(0, 60), tail: text.slice(-60),
    toolCallId: l16.tool_call_id || null
  }));
})().catch(error => { console.error(error); process.exit(1); });
"""
        result = run_node(script, str(self.module), self.base)
        self.assertIsNotNone(result, "node is required to run the real client assembler")
        self.assertEqual(result.returncode, 0, result.stderr)
        seen = json.loads(result.stdout)
        self.assertEqual(seen["rows"], expected_rows)
        self.assertEqual(seen["rows"], 112)          # 3 fragments for L16
        self.assertEqual(seen["logical"], 110)       # fragments never count
        self.assertEqual(seen["unique"], 110)
        self.assertEqual(seen["placeholders"], 0)
        self.assertTrue(seen["ordered"])
        self.assertEqual(seen["l16Len"], len(expected_text))
        self.assertGreater(seen["l16Len"], 32000)
        self.assertEqual(seen["head"], expected_text[:60])
        self.assertEqual(seen["tail"], expected_text[-60:])
        self.assertEqual(seen["toolCallId"], expected.get("tool_call_id"))

    def test_fragments_survive_out_of_order_and_duplicate_delivery(self):
        """A fresh ledger fed the whole run's rows reversed, duplicated, and
        with interleaved records still reconstructs L16 exactly once."""
        pages, cursor = [], None
        while True:
            block = dashboard_data.transcript_data(
                PACKET, REVIEW, 3, cursor=cursor, limit=100)
            pages.append(block)
            cursor = block["next_cursor"]
            if block["complete"] and not block["has_more"]:
                break
        expected = json.loads("".join(
            fragment["continuation"]["data"] for block in pages
            for fragment in block["records"] if fragment.get("continuation")))
        script = """
const api = require(process.argv[1]);
const base = process.argv[2];
(async () => {
  const rows = [];
  let cursor = null;
  for (let i = 0; i < 40; i++) {
    const url = base + "/api/transcript?coord="
      + encodeURIComponent("02.review/01.review")
      + "&attempt=3&limit=100"
      + (cursor ? "&cursor=" + encodeURIComponent(cursor) : "");
    const block = await (await fetch(url)).json();
    rows.push(...(block.records || []));
    cursor = block.next_cursor;
    if (block.complete && !block.has_more) break;
  }
  const ledger = api.createLedger();
  let scrambled = [...rows].reverse();
  const mid = Math.floor(scrambled.length / 2);
  scrambled = [...scrambled.slice(mid), ...scrambled.slice(0, mid)];
  ledger.absorb(scrambled);
  const midState = {
    placeholders: ledger.records.filter(r => r.continuing).length,
    logical: ledger.loadedCount()
  };
  ledger.absorb(scrambled);              // duplicates change nothing
  ledger.absorb(rows);                   // in-order delivery settles it
  const l16s = ledger.records.filter(r => r.id === "L16");
  const text = l16s.length === 1 && !l16s[0].continuing
      ? l16s[0].blocks[0].text : null;
  console.log(JSON.stringify({
    midState, count: l16s.length, logical: ledger.loadedCount(),
    l16Len: text === null ? null : text.length, diagnostics: ledger.diagnostics
  }));
})().catch(error => { console.error(error); process.exit(1); });
"""
        result = run_node(script, str(self.module), self.base)
        self.assertIsNotNone(result)
        self.assertEqual(result.returncode, 0, result.stderr)
        seen = json.loads(result.stdout)
        # A complete batch assembles even when its fragments arrive scrambled.
        # Re-delivering the same fragments changes neither count nor content.
        self.assertEqual(seen["midState"]["placeholders"], 0)
        self.assertEqual(seen["midState"]["logical"], 110)
        self.assertEqual(seen["count"], 1)
        self.assertEqual(seen["logical"], 110)
        self.assertEqual(seen["l16Len"],
                         len(expected["blocks"][0]["text"]))
        self.assertEqual(seen["diagnostics"], [])

    def test_continuation_metadata_rejects_incomplete_or_corrupt_chains(self):
        script = r"""
const api = require(process.argv[1]);
function row(id, offset, next, total, data, complete) {
  return {id, continuation: {
    record_id: id, offset, next_offset: next, total_chars: total,
    data, complete
  }};
}
function state(ledger) {
  return {
    loaded: ledger.loadedCount(), pending: ledger.pendingCount(),
    placeholders: ledger.records.filter(r => r.continuing).length,
    diagnostics: ledger.diagnostics
  };
}

const earlyData = JSON.stringify({id: "early", blocks: []});
const early = api.createLedger();
early.absorb([row("early", 0, [...earlyData].length,
    [...earlyData].length + 10, earlyData, true)]);

const conflictData = JSON.stringify({id: "conflict", blocks: []});
const conflictPoints = [...conflictData];
const conflictCut = 8;
const conflict = api.createLedger();
conflict.absorb([
  row("conflict", 0, conflictCut, conflictPoints.length,
      conflictPoints.slice(0, conflictCut).join(""), false),
  row("conflict", conflictCut, conflictPoints.length,
      conflictPoints.length + 1,
      conflictPoints.slice(conflictCut).join(""), false)
]);

const gapData = JSON.stringify({id: "gap", blocks: []});
const gapPoints = [...gapData];
const gapCut = 7;
const gap = api.createLedger();
gap.absorb([
  row("gap", 0, gapCut, gapPoints.length,
      gapPoints.slice(0, gapCut).join(""), false),
  row("gap", gapCut + 1, gapPoints.length, gapPoints.length,
      gapPoints.slice(gapCut + 1).join(""), true)
]);

const badSpan = api.createLedger();
badSpan.absorb([row("span", 0, 2, 2, "🦋", true)]);
const badRange = api.createLedger();
badRange.absorb([row("range", 3, 2, 4, "", false)]);

const validData = JSON.stringify({
  id: "valid", blocks: [{type: "text", text: "A🦋B"}]
});
const validPoints = [...validData];
const validCut = 11;
const first = row("valid", 0, validCut, validPoints.length,
    validPoints.slice(0, validCut).join(""), false);
const last = row("valid", validCut, validPoints.length, validPoints.length,
    validPoints.slice(validCut).join(""), true);
const valid = api.createLedger();
valid.absorb([last, first, first]);

console.log(JSON.stringify({
  early: state(early), conflict: state(conflict), gap: state(gap),
  badSpan: state(badSpan), badRange: state(badRange),
  valid: state(valid), validText: valid.records[0].blocks[0].text
}));
"""
        result = run_node(script, str(self.module))
        self.assertIsNotNone(result)
        self.assertEqual(result.returncode, 0, result.stderr)
        seen = json.loads(result.stdout)
        for name in ("early", "conflict", "gap", "badSpan", "badRange"):
            self.assertEqual(seen[name]["loaded"], 0, name)
            self.assertEqual(seen[name]["pending"], 1, name)
            self.assertEqual(seen[name]["placeholders"], 1, name)
            self.assertTrue(seen[name]["diagnostics"], name)
        self.assertIn("claims completion", " ".join(
            seen["early"]["diagnostics"]))
        self.assertIn("contradictory total_chars", " ".join(
            seen["conflict"]["diagnostics"]))
        self.assertIn("missing continuation coverage", " ".join(
            seen["gap"]["diagnostics"]))
        self.assertIn("Unicode code points", " ".join(
            seen["badSpan"]["diagnostics"]))
        self.assertIn("invalid continuation range", " ".join(
            seen["badRange"]["diagnostics"]))
        self.assertEqual(seen["valid"], {
            "loaded": 1, "pending": 0, "placeholders": 0,
            "diagnostics": [],
        })
        self.assertEqual(seen["validText"], "A\U0001f98bB")


class PublicTranscriptToolPairing(TempCase):

    def setUp(self):
        super().setUp()
        self.handle = dashboard.start(PACKET)
        self.addCleanup(self.handle.stop)
        self.base = self.handle.url.rstrip("/")
        self.module = dashboard.STATIC_ASSETS["/dashboard_records.js"][0]

    def test_all_nine_launched_transcripts_pair_both_result_shapes(self):
        script = r"""
const api = require(process.argv[1]);
const base = process.argv[2];
(async () => {
  const workflowResponse = await fetch(base + "/api/workflow");
  if (!workflowResponse.ok) throw new Error("workflow HTTP "
      + workflowResponse.status);
  const workflow = await workflowResponse.json();
  const launched = workflow.invocations.filter(inv => inv.launch === "agent");
  const cached = workflow.invocations.filter(inv => inv.launch === "cached");
  let logical = 0, calls = 0, pairs = 0;
  const shapes = {block: 0, record: 0};
  let actualReviewPair = false;

  for (const inv of launched) {
    const ledger = api.createLedger();
    let cursor = null;
    for (let page = 0; page < 100; page += 1) {
      const url = base + "/api/transcript?coord="
        + encodeURIComponent(inv.coord) + "&attempt=" + inv.attempt
        + "&limit=100" + (cursor ? "&cursor="
        + encodeURIComponent(cursor) : "");
      const response = await fetch(url);
      if (!response.ok) throw new Error(inv.id + " HTTP " + response.status);
      const block = await response.json();
      if (block.reset) ledger.reset();
      ledger.absorb(block.records || []);
      cursor = block.next_cursor;
      if (block.complete && !block.has_more) break;
    }
    logical += ledger.loadedCount();
    const results = api.collectToolResults(ledger.records);
    results.forEach(result => { shapes[result.shape] += 1; });
    ledger.records.forEach(record => {
      (record.blocks || []).forEach(block => {
        if (block.type !== "tool_call" || block.call_id == null) return;
        calls += 1;
        if (results.has(String(block.call_id))) pairs += 1;
      });
    });
    if (inv.coord === "02.review/01.review" && inv.attempt === 3) {
      const l5 = ledger.records.find(record => record.id === "L5");
      const l6 = ledger.records.find(record => record.id === "L6");
      const call = l5.blocks.find(block => block.type === "tool_call"
          && block.call_id === l6.tool_call_id);
      const result = api.collectToolResults([l5, l6]).get(l6.tool_call_id);
      const sourceText = l6.blocks.filter(block => block.type === "text")
          .map(block => block.text).join("");
      actualReviewPair = Boolean(call && result
          && result.shape === "record" && result.record.id === "L6"
          && result.block.content === sourceText
          && result.record.source.line === 6);
    }
  }
  console.log(JSON.stringify({
    invocations: workflow.invocations.length,
    launched: launched.length, cached: cached.length,
    logical, calls, pairs, shapes, actualReviewPair
  }));
})().catch(error => { console.error(error); process.exit(1); });
"""
        result = run_node(script, str(self.module), self.base)
        self.assertIsNotNone(result)
        self.assertEqual(result.returncode, 0, result.stderr)
        seen = json.loads(result.stdout)
        self.assertEqual(seen["invocations"], 11)
        self.assertEqual(seen["launched"], 9)
        self.assertEqual(seen["cached"], 2)
        self.assertEqual(seen["logical"], 1795)
        self.assertEqual(seen["calls"], 516)
        self.assertEqual(seen["pairs"], 516)
        self.assertEqual(seen["shapes"], {"block": 281, "record": 235})
        self.assertTrue(seen["actualReviewPair"])


class ToolStartRecordsRenderAsCalls(TempCase):
    """A cloud CLI's `tool_started` record carries its call as a `tool_call`
    block, so a running attempt's transcript names the tool and its
    arguments; the settled message keeps the result, so the finished view
    shows each result once."""

    def test_the_call_renders_and_the_result_lands_once(self):
        script = r"""
const fs = require("node:fs");
const vm = require("node:vm");
class Element {
  constructor(tag) {
    this.nodeType = 1; this.tagName = tag; this.children = []; this.dataset = {};
    this.className = ""; this.textContent = ""; this.open = false;
  }
  appendChild(child) { this.children.push(child); return child; }
  setAttribute(name, value) { this[name] = String(value); }
}
const document = {
  getElementById() { return null; },
  createElement: tag => new Element(tag),
  createElementNS: (_ns, tag) => new Element(tag),
  createTextNode: text => { const item = new Element("text"); item.textContent = text; return item; }
};
const context = {__OHFLOW_TEST__: true, document, window: {setTimeout() {}},
  console: {error() {}}, Intl, Date, URLSearchParams};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), context);
vm.runInContext(fs.readFileSync(process.argv[2], "utf8"), context);
const api = context.__OHFLOW_TEST_API__;
function card(root, id) {
  return root.children.reduce(function (hit, node) {
    return hit || (node.dataset && node.dataset.record === id ? node : null);
  }, null);
}
function texts(node, out) {
  out = out || [];
  if (node.tagName === "text") out.push(node.textContent);
  else if (!node.children.length && node.textContent) out.push(node.textContent);
  (node.children || []).forEach(function (child) { texts(child, out); });
  return out;
}
function count(root, needle) {
  return texts(root).filter(function (text) {
    return String(text).indexOf(needle) >= 0;
  }).length;
}
const source = {path: "logs/claude-cloud-events.jsonl", line: 3};
const toolStart = {id: "L3", source: source, ts: null, type: "tool_started",
  role: "system", tool_call_id: "toolu_1", tool_name: "Bash",
  blocks: [{type: "tool_call", call_id: "toolu_1", name: "Bash",
    input: {command: "sleep 900", timeout: 1000000}}]};
const toolEnd = {id: "L4", source: source, ts: null, type: "tool_result",
  role: "toolResult", tool_call_id: "toolu_1", is_error: false,
  blocks: [{type: "text", text: "the sleeper slept"}]};
const message = {id: "L5", source: source, ts: null, type: "message",
  role: "assistant",
  blocks: [{type: "text", text: "I will sleep."},
    {type: "tool_call", call_id: "toolu_1", name: "Bash",
     input: {command: "sleep 900", timeout: 1000000}}]};
const running = api.renderRecords([toolStart, toolEnd]);
const finished = api.renderRecords([toolStart, toolEnd, message]);
const startCard = card(running, "L3"), endCard = card(running, "L4");
const settledStart = card(finished, "L3"), settledMessage = card(finished, "L5");
console.log(JSON.stringify({
  runningNamesTool: texts(startCard).join("\n").indexOf("Bash") >= 0,
  runningShowsCommand: count(startCard, "sleep 900") >= 1,
  runningResultWithTheStart: count(startCard, "the sleeper slept") === 1,
  runningResultOnce: count(running, "the sleeper slept") === 1,
  runningEndConsumed: count(endCard, "the sleeper slept") === 0,
  finishedResultOnce: count(finished, "the sleeper slept") === 1,
  finishedResultWithTheMessage: count(settledMessage, "the sleeper slept") === 1,
  finishedStartKeepsTheCall: count(settledStart, "sleep 900") >= 1
    && count(settledStart, "the sleeper slept") === 0,
  finishedMessageKeepsItsText: texts(settledMessage).join("\n").indexOf("I will sleep.") >= 0
}));
"""
        result = run_node(script,
                          str(dashboard.STATIC_ASSETS["/dashboard_records.js"][0]),
                          str(dashboard.STATIC_ASSETS["/dashboard.js"][0]))
        self.assertIsNotNone(result)
        self.assertEqual(result.returncode, 0, result.stderr)
        seen = json.loads(result.stdout)
        self.assertEqual(seen, {
            "runningNamesTool": True,
            "runningShowsCommand": True,
            "runningResultWithTheStart": True,
            "runningResultOnce": True,
            "runningEndConsumed": True,
            "finishedResultOnce": True,
            "finishedResultWithTheMessage": True,
            "finishedStartKeepsTheCall": True,
            "finishedMessageKeepsItsText": True,
        })


class OversizedAndUnicodeRecords(TempCase):
    """A >90,000-char record with non-BMP characters reconstructs exactly:
    code-point offsets from the server are never compared with JS lengths."""

    def setUp(self):
        super().setUp()
        # Each "abc" + butterfly is 4 code points but 5 UTF-16 units, so a
        # length-based client would misassemble this record.
        unit = "abc\U0001f98b"
        self.wanted = unit * 24000
        self.marker = "marker-\U0001f4d0-tail"
        self.payload = self.wanted + self.marker
        run = make_packet(self.tmp / "large-unicode", records=[
            {"ts": None, "type": "message", "role": "assistant",
             "blocks": [{"type": "text", "text": self.payload}]},
        ])
        self.handle = dashboard.start(run)
        self.addCleanup(self.handle.stop)
        self.base = self.handle.url.rstrip("/")
        self.module = dashboard.STATIC_ASSETS["/dashboard_records.js"][0]

    def test_the_record_reassembles_losslessly_over_http(self):
        self.assertGreater(len(self.payload), 90000)
        script = """
const api = require(process.argv[1]);
const base = process.argv[2];
const crypto = require("node:crypto");
(async () => {
  const ledger = api.createLedger();
  let cursor = null, pages = 0;
  for (let i = 0; i < 30; i++) {
    const url = base + "/api/transcript?coord="
      + encodeURIComponent("01.p/01.worker")
      + "&attempt=1&limit=1"
      + (cursor ? "&cursor=" + encodeURIComponent(cursor) : "");
    const block = await (await fetch(url)).json();
    if (block.reset) ledger.reset();
    ledger.absorb(block.records || []);
    pages += 1;
    cursor = block.next_cursor;
    if (block.complete && !block.has_more) break;
  }
  const record = ledger.records[0];
  const text = record.blocks[0].text;
  console.log(JSON.stringify({
    pages, logical: ledger.loadedCount(), total: ledger.records.length,
    codePoints: [...text].length,
    sha256: crypto.createHash("sha256").update(text, "utf8").digest("hex"),
    tail: [...text].slice(-20).join("")
  }));
})().catch(error => { console.error(error); process.exit(1); });
"""
        result = run_node(script, str(self.module), self.base)
        self.assertIsNotNone(result)
        self.assertEqual(result.returncode, 0, result.stderr)
        seen = json.loads(result.stdout)
        self.assertGreater(seen["pages"], 5)
        self.assertEqual(seen["logical"], 1)
        self.assertEqual(seen["total"], 1)
        self.assertEqual(seen["codePoints"], len(self.payload))
        self.assertEqual(seen["sha256"], hashlib.sha256(
            self.payload.encode("utf-8")).hexdigest())
        self.assertEqual(seen["tail"], self.payload[-20:])

    def test_reset_clears_gathered_fragments_and_records(self):
        script = """
const api = require(process.argv[1]);
const base = process.argv[2];
(async () => {
  const url = base + "/api/transcript?coord="
    + encodeURIComponent("01.p/01.worker") + "&attempt=1&limit=1";
  const block = await (await fetch(url)).json();
  const ledger = api.createLedger();
  ledger.absorb(block.records || []);
  const before = {
    placeholders: ledger.records.filter(r => r.continuing).length,
    logical: ledger.loadedCount()
  };
  ledger.reset();
  ledger.absorb(block.records || []);   // the same page again, after reset
  const after = {
    placeholders: ledger.records.filter(r => r.continuing).length,
    logical: ledger.loadedCount()
  };
  console.log(JSON.stringify({ before, after }));
})().catch(error => { console.error(error); process.exit(1); });
"""
        result = run_node(script, str(self.module), self.base)
        self.assertIsNotNone(result)
        self.assertEqual(result.returncode, 0, result.stderr)
        seen = json.loads(result.stdout)
        self.assertEqual(seen["before"], seen["after"])
        self.assertEqual(seen["after"]["logical"], 0)   # one fragment pending
        self.assertEqual(seen["after"]["placeholders"], 1)


class StandaloneReport(TempCase):

    def test_read_out_report_inlines_the_same_shipping_renderer(self):
        read_out = {
            "generated": "2026-10-02T04:32:28Z",
            "run": {"id": "offline", "status": "finished",
                    "finished": "2026-10-02T04:32:28Z"},
            "agents": [], "phases": [], "events": [],
        }
        page = exit_report.render_html(read_out)
        self.assertIn("<style>", page)
        self.assertIn("data:font/ttf;base64,", page)
        self.assertIn("function renderGraph", page)
        self.assertIn("function createLedger", page)
        self.assertNotIn('href="/dashboard.css"', page)
        self.assertNotIn('src="/dashboard.js"', page)
        self.assertNotIn('src="/dashboard_records.js"', page)
        self.assertNotIn(exit_report.TIMELINE_SLOT, page)

    def test_optional_enriched_export_is_embedded_losslessly(self):
        workflow = dashboard_data.workflow_data(PACKET)
        evidence = dashboard_data.evidence_data(
            PACKET, "01.implement/01.implement", 5)
        transcript = dashboard_data.transcript_data(
            PACKET, "01.implement/01.implement", 5, limit=3)
        payload = {
            "workflow": workflow,
            "evidence": {"01.implement/01.implement@5": evidence},
            "transcripts": {"01.implement/01.implement@5": transcript},
        }
        page = exit_report.render_html(payload)
        embedded = page.split(exit_report.DATA_SLOT.split("null")[0], 1)[1]
        embedded = embedded.split("</script>", 1)[0]
        restored = json.loads(embedded)
        self.assertEqual(restored["workflow"]["run"]["id"],
                         "m7-smoke-fixes")
        self.assertEqual(len(restored["transcripts"][
            "01.implement/01.implement@5"]["records"]), 3)


if __name__ == "__main__":
    import unittest
    unittest.main()

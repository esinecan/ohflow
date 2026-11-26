(function () {
  "use strict";

  var byId = function (id) { return document.getElementById(id); };
  var NS = "http://www.w3.org/2000/svg";
  var TERMINAL = new Set(["finished", "failed", "paused", "crashed", "interrupted", "orphaned"]);
  var ROLE_ABBR = { implement: "Impl", review: "Rev" };
  var S = {
    workflow: null,
    readOut: null,
    static: false,
    limitedStatic: false,
    selected: null,
    /* A planned step the person opened instead of an invocation: the inspector
       then shows the plan (brief, policy, limits) because nothing has run. */
    selectedStep: null,
    view: "order",
    tab: "transcript",
    evidence: new Map(),
    transcripts: new Map(),
    artifactContent: new Map(),
    requestSerial: 0,
    pollTimer: null,
    connected: true,
    graphFit: false,
    search: "",
    expanded: new Set(),
    disclosures: new Set(),
    readerAll: false,
    compare: null,
    inspectorUi: null,
    plan: null,
    planError: null,
    planLoading: false,
    planPhases: new Map(),
    planDrawers: new Set(),
    planTabs: new Map(),
    /* The output tail of each running invocation: its transcript cursor and
       the last few lines, keyed by invocation id. Emptied as attempts end. */
    peek: new Map()
  };
  /* Lines the live peek keeps per running invocation, and the `tail=` it asks
   * `/api/transcript` for on its first look. */
  var PEEK_LINES = 5;

  function ledgerModule() {
    return (typeof ohflowRecords !== "undefined" && ohflowRecords) || null;
  }

  function node(tag, attrs) {
    var el = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (key) {
      var value = attrs[key];
      if (value === null || value === undefined || value === false) return;
      if (key === "class") el.className = value;
      else if (key === "text") el.textContent = value;
      else if (key === "dataset") Object.keys(value).forEach(function (name) { el.dataset[name] = value[name]; });
      else if (key === "checked" || key === "disabled" || key === "open") el[key] = !!value;
      else el.setAttribute(key, value === true ? "" : String(value));
    });
    for (var i = 2; i < arguments.length; i += 1) append(el, arguments[i]);
    return el;
  }

  function append(parent, child) {
    if (child === null || child === undefined || child === false) return;
    if (Array.isArray(child)) child.forEach(function (item) { append(parent, item); });
    else parent.appendChild(child.nodeType ? child : document.createTextNode(String(child)));
  }

  function icon(name) {
    var svg = document.createElementNS(NS, "svg");
    svg.setAttribute("aria-hidden", "true");
    var use = document.createElementNS(NS, "use");
    use.setAttribute("href", "#i-" + name);
    svg.appendChild(use);
    return svg;
  }

  function replace(el, children) {
    el.replaceChildren();
    append(el, children);
  }

  function jsonText(value) {
    if (typeof value === "string") return value;
    try { return JSON.stringify(value, null, 2); } catch (_error) { return String(value); }
  }

  function short(value, length) {
    value = value === null || value === undefined ? "" : String(value);
    return value.length > length ? value.slice(0, length - 1) + "…" : value;
  }

  function titleCase(value) {
    return String(value || "unknown").replace(/[_-]+/g, " ").replace(/\b\w/g, function (m) { return m.toUpperCase(); });
  }

  function statusTone(status) {
    status = String(status || "neutral").toLowerCase();
    return "tone-" + (["passed", "cached", "failed", "quarantined", "timeout", "running", "waiting", "pending", "deferred", "interrupted", "orphaned", "held"].indexOf(status) >= 0 ? status : "neutral");
  }

  function setStatusChip(el, status, label) {
    el.className = "status-chip " + statusTone(status);
    replace(el, [node("span", { class: "status-icon", "aria-hidden": "true" }), node("span", { text: label || titleCase(status) })]);
  }

  function utc(iso, includeDate) {
    if (!iso) return "Timestamp unavailable";
    var date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "Timestamp unavailable";
    var options = includeDate ? { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false, timeZone: "UTC" } : { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false, timeZone: "UTC" };
    return new Intl.DateTimeFormat("en-GB", options).format(date).replace(",", "") + " UTC";
  }

  function utcDay(iso) {
    if (!iso) return null;
    var date = new Date(iso);
    if (Number.isNaN(date.getTime())) return null;
    return new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", timeZone: "UTC" }).format(date) + " UTC";
  }

  function duration(seconds) {
    if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) return "Duration unavailable";
    seconds = Math.max(0, Math.round(Number(seconds)));
    var h = Math.floor(seconds / 3600);
    var m = Math.floor((seconds % 3600) / 60);
    var s = seconds % 60;
    if (h) return h + "h " + String(m).padStart(2, "0") + "m";
    if (m) return m + "m" + String(s).padStart(2, "0") + "s";
    return s + "s";
  }

  function stepFor(inv) {
    return S.workflow && (S.workflow.steps || []).find(function (item) { return item.coord === inv.coord; });
  }

  function fullRole(inv) {
    var step = stepFor(inv);
    return titleCase(step && (step.role || step.id) || inv.role || inv.step_id || "Invocation");
  }

  /* Compact node label: the approved composition abbreviates the fixed-width
   * node title; full names stay in the lane label, ARIA label and peek. */
  function shortRole(inv) {
    var step = stepFor(inv);
    var role = String((step && (step.role || step.id)) || inv.role || "invocation").toLowerCase();
    if (ROLE_ABBR[role]) return ROLE_ABBR[role];
    var named = titleCase(role);
    return named.length > 6 ? named.slice(0, 5) : named;
  }

  function invocationLabel(inv) {
    return shortRole(inv) + " " + inv.attempt;
  }

  function invocationTitle(inv) {
    return fullRole(inv) + " · attempt " + inv.attempt;
  }

  function retrySource(inv) {
    var edge = S.workflow && (S.workflow.edges || []).find(function (item) { return item.kind === "retry" && item.to === inv.id; });
    return edge ? invocation(edge.from) : null;
  }

  function sameRetryInputs(inv) {
    var before = retrySource(inv);
    return !!(before && before.fingerprint && inv.fingerprint && before.fingerprint === inv.fingerprint);
  }

  function launched() {
    return (S.workflow && S.workflow.invocations || []).filter(function (inv) { return inv.launch === "agent" || (inv.started && inv.launch !== "cached"); }).slice().sort(function (a, b) {
      var at = a.started ? Date.parse(a.started) : Infinity;
      var bt = b.started ? Date.parse(b.started) : Infinity;
      return at - bt || String(a.id).localeCompare(String(b.id));
    });
  }

  function invocation(id) {
    return (S.workflow && S.workflow.invocations || []).find(function (item) { return item.id === id; }) || null;
  }

  function parseEmbedded() {
    var raw = null;
    try { raw = JSON.parse(byId("ohflow-data").textContent || "null"); } catch (_error) { raw = null; }
    if (!raw) return;
    S.static = true;
    if (raw.schema === "ohflow.dashboard/1") S.workflow = raw;
    else if (raw.workflow && raw.workflow.schema === "ohflow.dashboard/1") {
      S.workflow = raw.workflow;
      S.readOut = raw.read_out || null;
    } else {
      S.readOut = raw.read_out || raw;
      S.workflow = workflowFromReadOut(S.readOut);
      S.limitedStatic = true;
    }
    if (raw.plan && raw.plan.schema === "ohflow.plan/1") S.plan = raw.plan;
    var evidence = raw.evidence || {};
    Object.keys(evidence).forEach(function (id) { S.evidence.set(id, { status: "ready", data: evidence[id] }); });
    var transcripts = raw.transcripts || {};
    Object.keys(transcripts).forEach(function (id) {
      var block = transcripts[id];
      var state = newTranscriptState();
      state.ledger.absorb(block.records || []);
      state.cursor = block.next_cursor || null;
      state.hasMore = !!block.has_more;
      state.complete = block.complete !== false && !block.has_more;
      state.total = block.total === null || block.total === undefined ? state.ledger.loadedCount() : block.total;
      S.transcripts.set(id, state);
    });
  }

  function workflowFromReadOut(readOut) {
    readOut = readOut || {};
    var phases = (readOut.phases || []).map(function (phase, index) {
      return { coord: phase.coord || String(index + 1), index: phase.index || index + 1, name: phase.name || phase.coord || "Phase", state: phase.state || phase.status || "unknown", steps: [] };
    });
    var steps = [];
    var invocations = [];
    (readOut.agents || []).forEach(function (agent, index) {
      var phaseCoord = agent.phase || (phases[0] && phases[0].coord) || "01.phase";
      var step = { coord: agent.coord, phase: phaseCoord, id: String(agent.coord || "step").split("/").pop(), role: agent.role || "agent", kind: "agent", harness_executor: agent.lane || agent.harness_executor || "unknown", status: agent.engine_status || "unknown", display: agent.display && agent.display.label || agent.engine_status || "unknown", waiting_on: agent.waiting_on || null, reason: agent.display && agent.display.reason || null };
      steps.push(step);
      var phase = phases.find(function (item) { return item.coord === phaseCoord; });
      if (phase) phase.steps.push(step.coord);
      (agent.attempts || []).forEach(function (attempt) {
        if (attempt.n === 0 || attempt.status === "cached") return;
        invocations.push({ id: agent.coord + "@" + attempt.n, coord: agent.coord, attempt: attempt.n, phase: phaseCoord, role: agent.role || "agent", harness_executor: agent.lane || agent.harness_executor || "unknown", launch: "agent", status: attempt.status || agent.engine_status || "unknown", started: attempt.started || null, finished: attempt.ended || attempt.finished || null, wall_s: attempt.wall_s, elapsed_s: attempt.elapsed_s, start_kind: attempt.start_kind || "initial", fingerprint: attempt.fingerprint || null, previous_fingerprint: attempt.previous_fingerprint || null, gate: attempt.gate || agent.gate || null, final_message: attempt.final_message || null, cause: attempt.cause || null, short_cause: attempt.short_cause || null, activity: attempt.activity || agent.activity || null, health: attempt.health || null, ordinal: index + 1 });
      });
    });
    invocations.sort(function (a, b) { return Date.parse(a.started || 0) - Date.parse(b.started || 0); });
    return { schema: "ohflow.dashboard/1", source: "embedded read-out", run: readOut.run || { id: "offline report", status: "unknown", mode: "final" }, phases: phases, steps: steps, invocations: invocations, edges: [], segments: [], cached: [], events: readOut.events || [], campaign: null, diagnostics: ["This older static report contains the legacy snapshot only; graph detail and full transcripts were not embedded."] };
  }

  function requestJson(url) {
    return fetch(url, { cache: "no-store", headers: { Accept: "application/json" } }).then(function (response) {
      if (!response.ok) throw new Error(response.status + " " + response.statusText);
      return response.json();
    });
  }

  function chooseDefault() {
    var list = launched();
    if (!list.length) return null;
    var running = list.find(function (inv) { return inv.status === "running"; });
    if (running) return running.id;
    var retry = (S.workflow.edges || []).filter(function (edge) { return edge.kind === "retry"; }).pop();
    if (retry && invocation(retry.to)) return retry.to;
    var abnormal = list.find(function (inv) { return ["failed", "quarantined", "timeout", "interrupted"].indexOf(inv.status) >= 0; });
    return (abnormal || list[list.length - 1]).id;
  }

  function announce(text) { byId("live-status").textContent = text; }

  function renderChrome() {
    var w = S.workflow;
    if (!w) return;
    var run = w.run || {};
    byId("run-title").textContent = run.id || "Unnamed run";
    var recovered = (w.edges || []).some(function (edge) { return edge.kind === "retry"; }) && launched().some(function (inv) { return inv.start_kind === "retry" && inv.status === "passed"; });
    var label = titleCase(run.status || "unknown") + (recovered ? " · recovered" : "");
    setStatusChip(byId("run-status"), run.status === "finished" && recovered ? "passed" : run.status, label);
    byId("run-counts").textContent = (w.phases || []).length + " phases  ·  " + (w.steps || []).length + " steps  ·  " + launched().length + " invocations" + ((w.cached || []).length ? "  ·  " + w.cached.length + " cached evaluations" : "");
    renderEta(run);
    var names = (w.phases || []).map(function (phase) { return phase.name; });
    byId("workflow-title").textContent = names.length ? names.join(" → ") : (run.plan || "Workflow");
    byId("workflow-summary").textContent = (w.steps || []).length + " planned steps  ·  " + Math.max(0, names.length - 1) + " phase barrier" + (names.length === 2 ? "" : "s");
    document.title = (run.id || "ohflow") + " · ohflow";
    var banner = byId("offline-banner");
    if (S.limitedStatic) {
      banner.hidden = false;
      banner.textContent = "Offline read-out report: basic run structure is available. Full graph evidence and transcripts were not embedded in this older report.";
    } else if (!S.connected && !S.static && TERMINAL.has(run.status)) {
      banner.hidden = false;
      banner.textContent = "The run ended at " + utc(run.finished, true) + " and its dashboard stopped. The exit report is exit-report.html in the run folder.";
    } else if (!S.connected && !S.static) {
      banner.hidden = false;
      banner.textContent = "Live updates are unavailable. The last complete workflow response remains visible.";
    } else banner.hidden = true;
  }

  /* The run's time line. Live: the ETA and the basis it was computed from
   * (the run's own finished steps, or the estimate before any finished).
   * Final: the minutes predicted when the run started beside the minutes it
   * took. Nothing when the run was never estimated and has no ETA yet. */
  function renderEta(run) {
    var el = byId("run-eta");
    if (!el) return;
    var estimate = run.estimate || null;
    var predicted = estimate && estimate.wall_s && estimate.wall_s.p50 !== null && estimate.wall_s.p50 !== undefined;
    if (TERMINAL.has(run.status)) {
      if (!predicted) { el.hidden = true; return; }
      el.hidden = false;
      el.textContent = "Predicted " + duration(estimate.wall_s.p50) + " · actual " + duration(run.elapsed_s);
      el.title = "p80 " + duration(estimate.wall_s.p80) + " · confidence " + (estimate.confidence || "unknown");
      return;
    }
    if (run.eta_s !== null && run.eta_s !== undefined) {
      el.hidden = false;
      el.textContent = "ETA ~" + duration(run.eta_s) + (run.eta_basis ? " (" + run.eta_basis + ")" : "");
      return;
    }
    if (predicted) {
      el.hidden = false;
      el.textContent = "Predicted " + duration(estimate.wall_s.p50) + (run.eta_basis ? " · ETA " + run.eta_basis : "");
      return;
    }
    el.hidden = true;
  }

  function estimateLine(estimate) {
    if (!estimate || !estimate.wall_s || estimate.wall_s.p50 === null || estimate.wall_s.p50 === undefined) return null;
    return "~" + duration(estimate.wall_s.p50) + " · p80 " + duration(estimate.wall_s.p80) + " · " + estimate.n + " sample" + (estimate.n === 1 ? "" : "s") + (estimate.confidence === "low" ? " · low confidence" : "");
  }

  /* ---- the attention strip: one item per condition, grouped by consequence ---- */

  var ATTENTION_GROUPS = [["intervention", "Needs a person"], ["recovering", "Recovering by itself"], ["signal", "Signals, not verdicts"]];

  function renderAttention() {
    var host = byId("attention-strip");
    if (!host) return;
    var w = S.workflow || {};
    var items = w.attention || [];
    if (!items.length) { replace(host, []); host.hidden = true; return; }
    host.hidden = false;
    replace(host, ATTENTION_GROUPS.map(function (group) {
      var mine = items.filter(function (item) { return item.group === group[0]; });
      if (!mine.length) return null;
      return node("div", { class: "attention-group " + group[0] }, node("h2", { text: group[1] + " · " + mine.length }), mine.map(attentionItem));
    }));
  }

  function attentionItem(item) {
    var who = item.step_id ? titleCase(item.role || item.step_id) : titleCase(String(item.kind || "run").replace(/_run$/, "")) + " run";
    var head = who + (item.attempt !== null && item.attempt !== undefined ? " · attempt " + item.attempt : "");
    var observed = (item.observed && item.observed.text) || "not recorded";
    if (item.observed && item.observed.ts) observed += " · " + utc(item.observed.ts, true);
    var next = item.next || {};
    var nextCell = next.command
        ? [node("code", { text: next.command }), node("button", { class: "copy-button", type: "button", title: "Copy the command", "aria-label": "Copy the command", dataset: { copy: next.command, copyLabel: "Command" } }, icon("copy")), node("span", { class: "source-ref", text: " " + (next.text || "") })]
        : (next.text || "none");
    var facts = node("dl", { class: "attention-facts" },
      node("dt", { text: "Observed" }), node("dd", { text: observed }),
      node("dt", { text: "Expected" }), node("dd", { text: item.expected || "not recorded" }),
      node("dt", { text: "Impact" }), node("dd", { text: (item.impact && item.impact.text) || "not recorded" }),
      node("dt", { text: "Next" }), node("dd", {}, nextCell));
    var evidence = item.evidence || {};
    var where = evidence.line ? "run-log.jsonl:" + evidence.line : null;
    var link = null;
    if (evidence.id && invocation(evidence.id)) link = node("button", { class: "event-link", type: "button", dataset: { select: evidence.id }, text: "Open " + invocationTitle(invocation(evidence.id)) + (where ? " · " + where : "") });
    else if (where) link = node("span", { class: "source-ref", text: where });
    return node("article", { class: "attention-item " + item.group, dataset: { kind: item.kind } },
      node("header", {}, node("strong", { text: head }), node("span", { class: "attention-kind", text: titleCase(item.kind) })),
      facts, link);
  }

  /* ---- who waits for whom: one line per phase ---- */

  function renderLanes() {
    var host = byId("phase-lanes");
    if (!host) return;
    var phases = (S.workflow && S.workflow.phases) || [];
    var rows = phases.filter(function (phase) { return phase.lanes; }).map(function (phase) {
      var lanes = phase.lanes;
      return node("div", { class: "phase-lane", dataset: { phase: phase.coord } },
        node("strong", { text: "Phase " + phase.index + " · " + phase.name }),
        node("span", { class: "status-chip " + statusTone(phase.state), text: titleCase(phase.state) }),
        node("span", { class: "lane-words", text: lanes.text }));
    });
    replace(host, rows);
    host.hidden = !rows.length;
  }

  /* ---- the live peek: the output tail of every running invocation ---- */

  function runningInvocations() {
    return launched().filter(function (inv) { return inv.status === "running"; });
  }

  function renderLivePeek() {
    var host = byId("live-peek");
    if (!host) return;
    var running = runningInvocations();
    if (!running.length) { replace(host, []); host.hidden = true; return; }
    host.hidden = false;
    replace(host, [node("h2", { text: "Running now · " + running.length }), running.map(peekRow)]);
  }

  function peekRow(inv) {
    var state = S.peek.get(inv.id) || { lines: [], error: null };
    var act = inv.activity || {};
    var tool = act.latest_tool;
    var health = inv.health || {};
    var meta = ["elapsed " + duration(inv.elapsed_s) + expectedSuffix(inv)];
    meta.push(tool ? "running " + tool.name + (tool.summary ? ": " + short(tool.summary, 60) : "") : (act.note || "no tool running"));
    if (health.idle_s !== null && health.idle_s !== undefined) meta.push("idle " + duration(health.idle_s) + (health.idle_signal && health.idle_signal !== "ok" ? " (" + health.idle_signal + ")" : ""));
    var body;
    if (state.lines.length) body = node("pre", { class: "peek-lines", text: state.lines.join("\n") });
    else body = node("p", { class: "peek-empty", text: S.static ? "The output tail is live only." : (state.error || "Output tail loading…") });
    return node("article", { class: "peek-row " + (health.idle_signal || "ok"), dataset: { peek: inv.id } },
      node("div", { class: "peek-head" }, node("strong", { text: invocationTitle(inv) }), node("span", { class: "peek-meta", text: meta.join(" · ") }), node("button", { class: "peek-open", type: "button", dataset: { peek: inv.id }, text: "Open transcript" })),
      body, commandOutputBlock(act.command_output));
  }

  /* The command an agent waits on and its output so far, from the
   * tool-output contract (logs/tool-output/ in the attempt directory). */
  function commandLabel(call) {
    var state = call.open ? "running " + duration(call.since_s) : (call.detached ? "running in the background" : (call.ok === false || (call.exit !== null && call.exit !== undefined && call.exit !== 0) ? "failed" + (call.exit !== null && call.exit !== undefined ? " (exit " + call.exit + ")" : "") : "finished"));
    return (call.tool || "tool") + " · " + short(call.command || "(no command recorded)", 90) + " · " + state;
  }

  function commandOutputBlock(call) {
    if (!call) return null;
    var lines = call.lines || call.tail || [];
    return node("div", { class: "command-output" + (call.open ? " open" : "") },
      node("p", { class: "command-output-head", text: (call.open ? "Command output so far · " : "Last command · ") + commandLabel(call) }),
      lines.length ? node("pre", { class: "peek-lines", text: lines.join(String.fromCharCode(10)) }) : node("p", { class: "peek-empty", text: call.open ? "The command has printed nothing yet." : "The command printed nothing." }));
  }

  function commandOutputDisclosure(evidence) {
    var out = evidence && evidence.tool_output;
    if (!out || !out.calls || !out.calls.length) return null;
    var stopped = evidence.open_tool_call;
    var rows = out.calls.slice().reverse().map(function (call, index) {
      var isStopped = stopped && stopped.id === call.id;
      return node("details", { class: "command-call" + (isStopped ? " stopped" : ""), open: index === 0 || isStopped },
        node("summary", { text: (isStopped ? "Open when the attempt stopped · " : "") + commandLabel(call) }),
        call.tail && call.tail.length ? node("pre", { class: "peek-lines", text: call.tail.join(String.fromCharCode(10)) }) : node("p", { class: "peek-empty", text: "No output was captured." }),
        node("p", { class: "source-ref", text: (call.file || "no file") + (call.truncated ? " · head and tail kept" : "") + (call.bytes ? " · " + call.bytes + " bytes" : "") }));
    });
    var title = "Command output · " + out.total + " call" + (out.total === 1 ? "" : "s") + (out.total > out.shown ? " (newest " + out.shown + " shown)" : "");
    return node("details", { class: "disclosure", open: !!stopped }, node("summary", { text: title }), node("div", { class: "disclosure-body" }, rows));
  }

  /* One transcript record as one tail line: the tool it called, the text it
   * wrote, or its reasoning, in that order of usefulness. */
  function oneLine(value, length) {
    var text = typeof value === "string" ? value : (function () { try { return JSON.stringify(value); } catch (_error) { return String(value); } }());
    return short(String(value === null || value === undefined ? "" : text).trim().split("\n")[0], length);
  }

  function recordLine(record) {
    if (!record || record.continuation || record.continuing) return null;
    var best = null, score = 0;
    (record.blocks || []).forEach(function (block) {
      var text = null, rank = 0;
      if (block.type === "tool_call") { text = "→ " + (block.name || "tool") + " " + oneLine(block.input, 90); rank = 3; }
      else if (block.type === "text") { text = oneLine(block.text, 110); rank = 2; }
      else if (block.type === "tool_result") { text = "← " + oneLine(block.content, 90); rank = 2; }
      else if (block.type === "thinking") { text = "(thinking) " + oneLine(block.thinking || block.text, 100); rank = 1; }
      if (text && rank >= score) { best = text; score = rank; }
    });
    if (!best) {
      if (record.type === "tool_call") best = "→ " + (record.name || "tool") + " " + oneLine(record.input, 90);
      else if (record.type === "tool_result") best = "← " + oneLine(record.content, 90);
      else if (record.error) best = "error: " + short(String(record.error), 100);
      else best = titleCase(record.subtype || record.status || record.type || "record");
    }
    var at = record.ts ? utc(record.ts, false).replace(" UTC", "") : "--:--:--";
    return at + " " + (record.role || record.type || "") + "  " + best;
  }

  function pollPeek() {
    if (S.static) return;
    var running = runningInvocations();
    var ids = new Set(running.map(function (inv) { return inv.id; }));
    Array.from(S.peek.keys()).forEach(function (id) { if (!ids.has(id)) S.peek.delete(id); });
    running.forEach(function (inv) {
      var state = S.peek.get(inv.id);
      if (!state) { state = { cursor: null, lines: [], loading: false, error: null }; S.peek.set(inv.id, state); }
      if (state.loading) return;
      state.loading = true;
      var url = "/api/transcript?coord=" + encodeURIComponent(inv.coord) + "&attempt=" + encodeURIComponent(inv.attempt)
          + (state.cursor ? "&cursor=" + encodeURIComponent(state.cursor) + "&limit=50" : "&tail=" + PEEK_LINES);
      requestJson(url).then(function (block) {
        state.loading = false;
        if (!S.peek.has(inv.id)) return;
        if (block.reset) state.lines = [];
        (block.records || []).forEach(function (record) { var line = recordLine(record); if (line) state.lines.push(line); });
        state.lines = state.lines.slice(-PEEK_LINES);
        state.cursor = block.next_cursor || state.cursor;
        state.error = (block.records || []).length || state.lines.length ? null : ((block.diagnostics || [])[0] || "No readable record yet.");
        renderLivePeek();
      }).catch(function (error) {
        state.loading = false;
        state.error = "Output tail unavailable: " + error.message;
        renderLivePeek();
      });
    });
  }

  function renderGraph() {
    var canvas = byId("graph-canvas");
    var grid = byId("graph-grid");
    hidePeek();
    var previousFocus = document.activeElement && document.activeElement.dataset && document.activeElement.dataset.invocation;
    var list = launched();
    var steps = [];
    list.forEach(function (inv) { if (steps.indexOf(inv.coord) < 0) steps.push(inv.coord); });
    if (!steps.length) (S.workflow.steps || []).forEach(function (step) { if (steps.indexOf(step.coord) < 0) steps.push(step.coord); });
    grid.style.setProperty("--columns", Math.max(1, list.length));
    grid.style.gridTemplateRows = "28px repeat(" + Math.max(1, steps.length) + ", 124px) 24px 62px";
    canvas.style.height = (28 + Math.max(1, steps.length) * 124 + 24 + 62) + "px";
    replace(grid, []);
    grid.appendChild(node("span", { class: "utc-label", text: list.length ? utc(list[0].started, true) + "  →  " + utc(list[list.length - 1].started, true) : "No observed starts" }));
    steps.forEach(function (coord, row) {
      var step = (S.workflow.steps || []).find(function (item) { return item.coord === coord; }) || {};
      var detail = step.kind === "agent" ? (step.harness_executor || "agent") + " agent" : (step.kind || "planned step");
      var planned = !list.some(function (inv) { return inv.coord === coord; });
      var label = node("div", { class: "lane-label" }, node("span", { text: titleCase(step.role || step.id || coord) }), node("small", { text: detail }),
        planned ? planButton(coord) : null);
      label.style.gridColumn = "1";
      label.style.gridRow = String(row + 2);
      grid.appendChild(label);
    });
    var query = S.search.trim().toLowerCase();
    var matches = 0;
    list.forEach(function (inv, index) {
      var text = searchableInvocation(inv);
      var match = !query || text.indexOf(query) >= 0;
      if (match) matches += 1;
      var state = String(inv.status || "unknown").toLowerCase();
      var stateIcon = state === "failed" || state === "quarantined" || state === "timeout" ? "x" : state === "running" || state === "waiting" || state === "pending" ? "dot" : "check";
      var button = node("button", {
        class: "invocation-node " + state + (match ? "" : " search-miss"),
        type: "button",
        dataset: { invocation: inv.id },
        "aria-pressed": inv.id === S.selected ? "true" : "false",
        "aria-label": invocationTitle(inv) + ", " + titleCase(state) + ", started " + utc(inv.started, false)
      },
      node("span", { class: "node-title" }, node("span", { class: "node-state", "aria-hidden": "true" }, icon(stateIcon)), node("span", { class: "node-name", text: invocationLabel(inv) })),
      node("time", { text: inv.started ? utc(inv.started, false).replace(" UTC", "") : "Unknown time" }),
      node("span", { class: "node-duration", text: inv.status === "running" ? "Running · " + duration(inv.elapsed_s) + expectedSuffix(inv) : duration(inv.wall_s) }),
      inv.start_kind === "retry" ? node("span", { class: "retry-label", text: "Retry" }) : null);
      button.style.gridColumn = String(index + 2);
      button.style.gridRow = String(steps.indexOf(inv.coord) + 2);
      button.addEventListener("click", function () { selectInvocation(inv.id, true); });
      button.addEventListener("mouseenter", function () { showPeek(inv, button); });
      button.addEventListener("mouseleave", hidePeek);
      button.addEventListener("focus", function () { showPeek(inv, button); });
      button.addEventListener("blur", hidePeek);
      grid.appendChild(button);
      var ordinal = node("span", { class: "ordinal-label", text: "Col " + (index + 1) });
      ordinal.style.gridColumn = String(index + 2);
      ordinal.style.gridRow = String(steps.length + 2);
      grid.appendChild(ordinal);
    });
    (S.workflow.segments || []).filter(function (segment) { return (segment.invocations || []).some(function (id) { return list.some(function (inv) { return inv.id === id; }); }); }).forEach(function (segment) {
      var indexes = segment.invocations.map(function (id) { return list.findIndex(function (inv) { return inv.id === id; }); }).filter(function (index) { return index >= 0; });
      if (!indexes.length) return;
      var label = node("div", { class: "segment-label" }, node("span", { text: "Segment " + segment.index }), node("small", { text: indexes.map(function (index) { return invocationLabel(list[index]); }).join(" → ") }));
      label.style.gridColumn = (Math.min.apply(Math, indexes) + 2) + " / " + (Math.max.apply(Math, indexes) + 3);
      label.style.gridRow = String(steps.length + 3);
      grid.appendChild(label);
    });
    byId("graph-empty").hidden = !query;
    if (query) {
      var inspected = Array.from(S.evidence.values()).filter(function (record) { return record.status === "ready"; }).length;
      replace(byId("graph-empty"), [
        node("strong", { text: matches ? matches + " invocation" + (matches === 1 ? "" : "s") + " match this search." : "No invocation matches this search." }),
        node("span", { text: "Search covers node text and evidence loaded so far (" + inspected + " of " + list.length + " invocations inspected). Open an invocation to include its evidence." })
      ]);
    }
    requestAnimationFrame(function () { drawEdges(); drawDateCrossings(list); });
    if (previousFocus) requestAnimationFrame(function () { var focus = grid.querySelector('[data-invocation="' + CSS.escape(previousFocus) + '"]'); if (focus) focus.focus(); });
  }

  function searchableInvocation(inv) {
    var ev = S.evidence.get(inv.id);
    return jsonText({ id: inv.id, coord: inv.coord, role: inv.role, status: inv.status, cause: inv.cause, message: inv.final_message, evidence: ev && ev.data }).toLowerCase();
  }

  function drawEdges() {
    var svg = byId("graph-edges");
    var canvas = byId("graph-canvas");
    if (!S.workflow || !canvas.clientWidth) return;
    replace(svg, []);
    svg.setAttribute("viewBox", "0 0 " + canvas.clientWidth + " " + canvas.clientHeight);
    var defs = document.createElementNS(NS, "defs");
    ["normal", "retry", "context"].forEach(function (name) {
      var marker = document.createElementNS(NS, "marker");
      marker.setAttribute("id", "arrow-" + name);
      marker.setAttribute("viewBox", "0 0 10 10"); marker.setAttribute("refX", "8"); marker.setAttribute("refY", "5"); marker.setAttribute("markerWidth", "6"); marker.setAttribute("markerHeight", "6"); marker.setAttribute("orient", "auto-start-reverse");
      var path = document.createElementNS(NS, "path"); path.setAttribute("d", "M 0 0 L 10 5 L 0 10 z"); path.setAttribute("fill", name === "retry" ? "#6ea8ff" : name === "context" ? "#8a96a5" : "#758190"); marker.appendChild(path); defs.appendChild(marker);
    });
    svg.appendChild(defs);
    var connections = new Map();
    function connect(from, to, kind, source) {
      var key = String(from) + "→" + String(to);
      var group = connections.get(key);
      if (!group) { group = { from: from, to: to, kinds: [], sources: [] }; connections.set(key, group); }
      if (group.kinds.indexOf(kind) < 0) { group.kinds.push(kind); group.sources.push(source || "recorded relation"); }
    }
    (S.workflow.edges || []).filter(function (edge) { return edge.kind === "retry"; }).forEach(function (edge) { connect(edge.from, edge.to, "retry", edge.source); });
    var abstractEdges = (S.workflow.edges || []).filter(function (edge) { return edge.kind === "depends_on" || edge.kind === "phase"; });
    (S.workflow.segments || []).forEach(function (segment) {
      var ids = new Set(segment.invocations || []);
      abstractEdges.forEach(function (edge) {
        var targets = launched().filter(function (inv) { return ids.has(inv.id) && inv.coord === edge.to; });
        targets.forEach(function (target) {
          var targetIndex = launched().indexOf(target);
          var sources = launched().filter(function (inv, index) { return ids.has(inv.id) && inv.coord === edge.from && index < targetIndex; });
          if (sources.length) connect(sources[sources.length - 1].id, target.id, edge.kind, edge.source);
        });
      });
    });
    var list = launched();
    var withStarts = (S.workflow.segments || []).filter(function (segment) { return (segment.invocations || []).some(function (id) { return invocation(id) && invocation(id).launch !== "cached"; }); });
    for (var i = 1; i < withStarts.length; i += 1) {
      var previous = withStarts[i - 1].invocations.filter(function (id) { return invocation(id) && invocation(id).launch !== "cached"; }).pop();
      var next = withStarts[i].invocations.find(function (id) { return invocation(id) && invocation(id).launch !== "cached"; });
      if (previous && next) {
        var before = invocation(previous), after = invocation(next);
        var changed = before.fingerprint && after.fingerprint && before.fingerprint !== after.fingerprint;
        connect(previous, next, changed ? "context" : "context-same", "next segment (recorded start order)");
      }
    }
    var root = canvas.getBoundingClientRect();
    connections.forEach(function (group) {
      var from = canvas.querySelector('[data-invocation="' + CSS.escape(group.from) + '"]');
      var to = canvas.querySelector('[data-invocation="' + CSS.escape(group.to) + '"]');
      if (!from || !to) return;
      var a = from.getBoundingClientRect(), b = to.getBoundingClientRect();
      var x1 = a.right - root.left, y1 = a.top + a.height / 2 - root.top;
      var x2 = b.left - root.left, y2 = b.top + b.height / 2 - root.top;
      var bend = Math.max(12, (x2 - x1) * .45);
      var d = "M " + x1 + " " + y1 + " C " + (x1 + bend) + " " + y1 + ", " + (x2 - bend) + " " + y2 + ", " + (x2 - 4) + " " + y2;
      /* One arrow per ordered node pair. When the same pair carries both the
       * recorded dependency and the phase barrier, the dotted barrier stroke
       * rides on the same geometry instead of drawing a second arrow. */
      var style = group.kinds.indexOf("retry") >= 0 ? "retry"
          : group.kinds.indexOf("depends_on") >= 0 ? "dependency"
          : group.kinds.indexOf("phase") >= 0 ? "phase" : "context";
      var path = document.createElementNS(NS, "path");
      /* The selected invocation's declared dependencies stand out: a
       * depends_on edge that touches its step is drawn stronger. */
      var selected = invocation(S.selected);
      var touches = selected && group.kinds.indexOf("depends_on") >= 0 && [group.from, group.to].some(function (id) { var other = invocation(id); return other && other.coord === selected.coord; });
      path.setAttribute("class", "edge-path " + style + (touches ? " is-selected" : ""));
      path.setAttribute("d", d);
      path.setAttribute("marker-end", "url(#arrow-" + (style === "retry" ? "retry" : style === "context" || style === "context-same" ? "context" : "normal") + ")");
      path.dataset.kinds = group.kinds.join("+");
      svg.appendChild(path);
      if (style === "dependency" && group.kinds.indexOf("phase") >= 0) {
        var overlay = document.createElementNS(NS, "path");
        overlay.setAttribute("class", "edge-path phase overlay");
        overlay.setAttribute("d", d);
        overlay.dataset.kinds = "phase";
        svg.appendChild(overlay);
      }
    });
  }

  /* Actual UTC date crossings between consecutive recorded starts, marked in
   * the ordinal grid. The marker never turns spacing into elapsed time. */
  function drawDateCrossings(list) {
    var canvas = byId("graph-canvas");
    var host = byId("graph-markers");
    if (!host) {
      host = node("div", { class: "graph-markers", id: "graph-markers", "aria-hidden": "true" });
      canvas.appendChild(host);
    }
    replace(host, []);
    var root = canvas.getBoundingClientRect();
    for (var i = 1; i < list.length; i += 1) {
      var beforeDay = utcDay(list[i - 1].started), afterDay = utcDay(list[i].started);
      if (!beforeDay || !afterDay || beforeDay === afterDay) continue;
      var a = canvas.querySelector('[data-invocation="' + CSS.escape(list[i - 1].id) + '"]');
      var b = canvas.querySelector('[data-invocation="' + CSS.escape(list[i].id) + '"]');
      if (!a || !b) continue;
      var ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
      var x = (ra.left + ra.right + rb.left + rb.right) / 4 - root.left;
      host.appendChild(node("div", { class: "date-cross" }, node("span", { class: "date-cross-label", text: afterDay }), node("span", { class: "date-cross-line" })));
      host.lastChild.style.left = x + "px";
    }
  }

  function showPeek(inv, anchor) {
    var peek = byId("node-peek");
    var rows = [];
    var evidence = evidenceData(inv.id);
    var state = String(inv.status || "unknown").toLowerCase();
    var waitLine = null;
    var gateLine = null;
    if (inv.gate && inv.gate.passed === false) {
      var detail = null;
      if (evidence && evidence.gate) {
        var bad = (evidence.gate.checks || []).find(function (check) { return !check.passed; });
        if (bad) detail = bad.name + ": expected " + jsonText(bad.expected) + ", observed " + jsonText(bad.observed);
      }
      var names = (inv.gate.failed || []).join(", ");
      gateLine = "Independent gate failed · " + (detail || names || inv.short_cause || "cause recorded");
    } else if (inv.gate && inv.gate.passed === true && evidence && evidence.gate) {
      gateLine = "Independent gate · " + (evidence.gate.checks || []).length + " checks passed";
    }
    if (inv.waiting_on) waitLine = "Waiting on " + inv.waiting_on + (stepReason(inv) ? " · " + stepReason(inv) : "");
    else if (inv.health && inv.health.note) waitLine = inv.health.note;
    var output = inv.activity && (inv.activity.latest_reasoning && inv.activity.latest_reasoning.text
        || inv.activity.latest_tool && (inv.activity.latest_tool.name + ": " + (inv.activity.latest_tool.summary || "activity observed")));
    var outputLabel = null;
    if (output) outputLabel = "Activity";
    else if (inv.final_message) { output = inv.final_message; outputLabel = "Claim (model output)"; }
    else if (inv.cause) { output = inv.cause; outputLabel = "Recorded cause"; }
    replace(peek, [
      node("strong", { class: statusTone(inv.status), text: titleCase(inv.status) }),
      node("p", { text: utc(inv.started, true) + " → " + (inv.finished ? utc(inv.finished, true) : "in progress") }),
      node("p", { text: (inv.status === "running" ? "Elapsed " + duration(inv.elapsed_s) : "Duration " + duration(inv.wall_s)) + " · " + (inv.start_kind === "retry" ? "automatic retry" : (inv.start_kind || "recorded start")) }),
      gateLine ? node("p", { class: "peek-gate", text: gateLine }) : null,
      waitLine ? node("p", { class: "peek-gate", text: waitLine }) : null,
      output ? node("p", { class: "peek-output" }, node("span", { class: "peek-output-label", text: outputLabel + ": " }), short(output, 150)) : node("p", { class: "peek-output", text: "No output peek was recorded." })
    ]);
    peek.hidden = false;
    var rect = anchor.getBoundingClientRect();
    var width = 246;
    var left = Math.min(window.innerWidth - width - 10, Math.max(10, rect.left + rect.width / 2 - width / 2));
    var top = rect.top - peek.offsetHeight - 8;
    if (top < 8) top = rect.bottom + 8;
    peek.style.left = left + "px"; peek.style.top = top + "px";
  }

  function stepReason(inv) {
    var step = stepFor(inv);
    return step && (step.reason || (step.waiting_on ? "waiting on " + step.waiting_on : null)) || null;
  }

  function hidePeek() { byId("node-peek").hidden = true; }

  function renderDigest() {
    var host = byId("digest-panel");
    var retry = (S.workflow.edges || []).find(function (edge) { return edge.kind === "retry"; });
    var failed = retry && invocation(retry.from), recovered = retry && invocation(retry.to);
    var keyEvents = retry ? keyEventLinks(retry) : [];
    var copy = node("div", { class: "digest-copy" }, icon("file"), node("div", {}, node("h2", { id: "digest-heading", text: retry ? "Recovered automatically: failed check → same-input retry → passed checks" : "Recorded workflow evidence" }), node("p", {}, retry ? ["Retry decision: ", node("button", { class: "event-link", type: "button", dataset: { select: recovered.id }, text: retry.label })] : "No automatic retry relationship is recorded for this run."), keyEvents.length ? node("p", { class: "digest-events" }, ["Recorded events: "].concat(keyEvents)) : null));
    var cache = node("div", { class: "cache-summary" }, icon("tool"), node("div", {}, node("strong", { text: (S.workflow.cached || []).length + " reused result" + ((S.workflow.cached || []).length === 1 ? "" : "s") }), node("p", { text: (S.workflow.cached || []).length ? "Cached evaluations launched no new agent; each names the evidence it reuses (Workflow view)." : "No cached evaluation is recorded." })));
    var held = (S.workflow.run || {}).status === "held";
    replace(host, held ? [renderDigestPilot(), renderDigestEstimate(), copy, cache, renderDigestList()]
      : [copy, cache, renderDigestEstimate(), renderDigestPilot(), renderDigestList()]);
    if (failed) host.dataset.failed = failed.id;
  }

  /* The between-invocation digest: one sentence per verdict, decision,
   * settlement and run end, newest first, each linked to its invocation and
   * labelled with its run-log line. */
  function renderDigestList() {
    var entries = (S.workflow.digest || []).slice().reverse();
    if (!entries.length) return null;
    var items = entries.map(function (entry) {
      var inv = entry.id ? invocation(entry.id) : null;
      var line = entry.evidence && entry.evidence.line ? (entry.evidence.path || "run-log.jsonl") + ":" + entry.evidence.line : null;
      var text = node("span", { class: "digest-text" }, entry.text,
        inv ? node("button", { class: "event-link", type: "button", dataset: { select: entry.id }, text: "open" }) : null,
        line ? node("span", { class: "source-ref", text: line }) : null);
      if (entry.handover_first_line && !inv) text.title = "handover: " + entry.handover_first_line;
      return node("li", { dataset: { kind: entry.kind } }, node("span", { class: "digest-dot " + (entry.tone || "info"), "aria-hidden": "true" }), node("time", { text: entry.ts ? utc(entry.ts, false).replace(" UTC", "") : "--:--:--" }), text);
    });
    return [node("div", { class: "digest-heading-row" }, node("h3", { text: "Digest · " + entries.length + " entr" + (entries.length === 1 ? "y" : "ies") + ", newest first" }), node("span", { class: "source-ref", text: "verdicts, retry decisions, exclusions, settlements, run end" })),
      node("ol", { class: "digest-list" }, items)];
  }

  /* Predicted vs actual, from the estimate the run started with and what
   * the run has recorded so far. Only a run with an estimate.json has one. */
  function renderDigestEstimate() {
    var run = S.workflow.run || {};
    var estimate = run.estimate;
    if (!estimate || !estimate.wall_s) return null;
    var actual = run.actual || {};
    function tokens(n) { return n === null || n === undefined ? "unknown" : n >= 1000000 ? (n / 1000000).toFixed(1) + " M" : n >= 1000 ? (n / 1000).toFixed(1) + " k" : String(n); }
    var rows = [
      ["Minutes", (estimate.wall_s.p50 === null ? "unknown" : duration(estimate.wall_s.p50) + " predicted (p80 " + duration(estimate.wall_s.p80) + ")") + " · " + duration(actual.wall_s) + " actual"],
      ["Tokens", tokens(estimate.tokens && estimate.tokens.p50) + " predicted (p80 " + tokens(estimate.tokens && estimate.tokens.p80) + ")" + " · " + tokens(actual.tokens) + " actual"],
      ["Cost", estimate.cost_usd === null || estimate.cost_usd === undefined ? "unpriced" : "$" + Number(estimate.cost_usd).toFixed(2) + " predicted"],
      ["Confidence", (estimate.confidence || "unknown") + (estimate.basis ? " · " + estimate.basis : "")]
    ];
    return node("div", { class: "cache-summary digest-estimate" }, icon("clock"), node("div", {}, node("strong", { text: TERMINAL.has(run.status) ? "Predicted vs actual" : "Predicted · actual so far" }), node("dl", {}, rows.map(function (row) { return [node("dt", { text: row[0] }), node("dd", { text: row[1] })]; }))));
  }

  function renderDigestPilot() {
    var run = S.workflow.run || {};
    var pilot = run.pilot;
    if (!pilot) return null;
    function tokens(n) { return n === null || n === undefined ? "unknown" : n >= 1000000 ? (n / 1000000).toFixed(1) + " M" : n >= 1000 ? (n / 1000).toFixed(1) + " k" : String(n); }
    function money(v) { return v === null || v === undefined ? "unpriced" : "$" + Number(v).toFixed(2); }
    function time(s) {
      if (s === null || s === undefined) return "-";
      s = Number(s);
      if (s < 60) return s.toFixed(1) + " s";
      var m = Math.round(s / 60);
      return m < 60 ? m + " min" : Math.floor(m / 60) + " h " + (m % 60) + " min";
    }
    function triple(part) { return part ? time(part.wall_s) + " · " + tokens(part.tokens) + " tokens · " + money(part.cost_usd) : "not measured"; }
    var title = node("strong", { text: pilot.state === "running" ? "Pilot running" : "Pilot projection" });
    var head = node("p", { class: "pilot-head", text: pilot.head });
    var projection = pilot.projection;
    if (!projection) return node("div", { class: "cache-summary digest-pilot" }, icon("clock"), node("div", {}, title, head));
    var rows = projection.paths.map(function (path) {
      return node("tr", {}, node("th", { scope: "row", text: path.name, title: path.description || null }), node("td", { text: String(path.units) }), node("td", { text: path.pilot_unit || "-" }), node("td", { text: path.status }), node("td", { text: triple(path.unit) }), node("td", { text: triple(path.projected) }));
    });
    if (projection.shared) rows.push(node("tr", {}, node("th", { scope: "row", text: "shared steps" }), node("td", { text: "-" }), node("td", { text: "-" }), node("td", { text: projection.shared.status }), node("td", { text: "measured once" }), node("td", { text: triple(projection.shared.projected) })));
    var table = node("table", { class: "pilot-table" }, node("thead", {}, node("tr", {}, ["Path", "Units", "Pilot unit", "Status", "Per unit", "Projected"].map(function (h) { return node("th", { scope: "col", text: h }); }))), node("tbody", {}, rows));
    var total = projection.total;
    var sum = node("p", { class: "pilot-total", text: "Projected full run: " + triple(total) + " for " + total.units + " units" + (total.complete ? "" : " · not measured: " + total.missing.join(", ")) });
    var note = node("p", { class: "campaign-note", text: "Time is the summed wall time of a unit's attempts. Pilot run: " + pilot.run_dir });
    return node("div", { class: "cache-summary digest-pilot" }, icon("clock"), node("div", {}, title, head, table, sum, note));
  }

  /* The run-log events that carry the retry story, each linked to the
   * invocation it belongs to and labelled with its recorded journal line. */
  function keyEventLinks(retry) {
    var events = S.workflow.events || [];
    function ref(inv, wanted, label) {
      var index = events.findIndex(function (event) {
        return event.coord === inv.coord && event.attempt === inv.attempt && event.event === wanted;
      });
      if (index < 0) return null;
      var event = events[index];
      var line = event.source && event.source.line ? event.source.line : index + 1;
      return node("button", { class: "event-link", type: "button", dataset: { select: inv.id }, title: event.text, text: "#" + line + " " + label });
    }
    var before = invocation(retry.from), after = invocation(retry.to);
    if (!before || !after) return [];
    return [
      ref(before, "attempt.finished", "failure"),
      ref(before, "attempt.retry_decided", "retry decision"),
      ref(after, "attempt.started", "retry started"),
      ref(after, "attempt.finished", "passed")
    ].filter(Boolean).reduce(function (out, item, index) {
      if (index) out.push(" · ");
      out.push(item);
      return out;
    }, []);
  }

  function renderCampaign() {
    var host = byId("campaign-panel");
    var campaign = S.workflow.campaign;
    if (!campaign || !(campaign.rounds || []).length) {
      replace(host, [node("h2", { id: "campaign-heading", text: "Campaign context" }), node("p", { class: "campaign-note", text: "This run has no linked campaign record. Campaign revisions are separate from engine retries." })]);
      return;
    }
    var judged = (campaign.rounds || []).filter(function (round) { return round.event === "judged"; });
    var rows = judged.map(function (round, index) {
      var pos = campaign.rounds.indexOf(round);
      var nextJudge = index + 1 < judged.length ? campaign.rounds.indexOf(judged[index + 1]) : campaign.rounds.length;
      var escalated = campaign.rounds.slice(pos + 1, nextJudge).find(function (item) { return item.event === "escalated"; });
      var landed = campaign.rounds.slice(pos + 1, nextJudge + 1).find(function (item) { return item.event === "milestone_passed"; });
      var outcome = round.verdict + (round.verdict === "PASS" && escalated ? " · refused" : landed ? " · landed" : "");
      return node("tr", {}, node("td", { text: String(index + 1) }), node("td", { class: round.verdict === "PASS" ? "verdict-pass" : "verdict-revise", text: outcome }), node("td", { class: "source-ref", text: "campaign line " + (round.campaign_jsonl_line || "unknown") }));
    });
    replace(host, [node("h2", { id: "campaign-heading" }, icon("workflow"), "Campaign decisions (separate context)"), node("table", { class: "campaign-table" }, node("thead", {}, node("tr", {}, node("th", { text: "Round" }), node("th", { text: "Decision" }), node("th", { text: "Source" }))), node("tbody", {}, rows)), node("p", { class: "campaign-note", text: "Campaign milestone revisions are context links, not execution dependencies or automatic retries." })]);
  }

  function planButton(coord) {
    return node("button", { type: "button", class: "plan-button", dataset: { selectStep: coord }, "aria-pressed": S.selectedStep === coord ? "true" : "false", text: "Inspect the plan" });
  }

  /* Open the inspector on a step that has no invocation. The step is planned
     work, so the inspector shows what will run, not evidence of what ran. */
  function selectStep(coord) {
    var step = (S.workflow && S.workflow.steps || []).find(function (item) { return item.coord === coord; });
    if (!step) return;
    S.selectedStep = coord;
    renderGraph();
    renderPlannedInspector();
    if (S.view === "workflow") renderWorkflowView();
    announce(titleCase(step.role || step.id) + " plan selected");
  }

  function setInspectorMode(mode) {
    var planned = mode === "planned";
    var meta = byId("invocation-meta-disclosure");
    if (meta) meta.hidden = planned;
    var tabs = document.querySelector("#inspector .tab-list");
    if (tabs) tabs.hidden = planned;
    var controls = byId("transcript-controls");
    if (controls) controls.hidden = planned;
    ["panel-overview", "panel-checks", "panel-transcript", "panel-artifacts"].forEach(function (id) {
      var panel = byId(id);
      if (panel && planned) panel.hidden = true;
    });
    var plan = byId("panel-planned");
    if (plan) plan.hidden = !planned;
  }

  function listOrNone(values, none) {
    return values && values.length ? values.join(", ") : none;
  }

  function renderPlannedInspector() {
    var step = (S.workflow && S.workflow.steps || []).find(function (item) { return item.coord === S.selectedStep; });
    if (!step) return;
    var plan = step.plan || {};
    var limits = plan.limits || {};
    var retry = plan.retry || {};
    var handover = plan.handover || null;
    var phase = (S.workflow.phases || []).find(function (item) { return item.coord === step.phase; }) || {};
    var policy = phase.plan || {};
    var run = S.workflow.run || {};
    var status = run.status === "held" ? "held" : (step.display || step.status || "waiting");
    var recorded = launched().filter(function (inv) { return inv.coord === step.coord; }).length;
    byId("inspector-title").textContent = titleCase(step.role || step.id);
    byId("inspector-subtitle").textContent = "Planned step · " + (step.harness_executor || step.kind || "step") + " · " + (step.reason || (recorded ? recorded + " invocation" + (recorded === 1 ? "" : "s") + " recorded; open one from the graph" : "no invocation recorded yet"));
    setStatusChip(byId("inspector-status"), status, titleCase(status));
    setInspectorMode("planned");
    var rows = [
      ["Objective", step.objective || "Not stated"],
      ["Model", plan.model || "Not an agent step"],
      ["Harness executor", plan.harness_executor || "—"],
      ["Tool policy", plan.tool_policy ? jsonText(plan.tool_policy) : "—"],
      ["Write scope", listOrNone(plan.write_scope, "Nothing declared")],
      ["Worktree", plan.worktree || "The repository itself"],
      ["Retry", "max " + (retry.max === undefined || retry.max === null ? 0 : retry.max) + (retry.on && retry.on.length ? " on " + retry.on.join(", ") : "") + (retry.carry_context ? " · carries context" : "")],
      ["Consumes", listOrNone(plan.consumes, "No handover")],
      ["Depends on", listOrNone(plan.depends_on, "No explicit step dependency")],
      ["Gate checks", listOrNone(plan.gate, "No checks")],
      ["Limits", "execution " + duration(limits.execution_timeout_s) + " · stall " + (limits.stall_timeout_s ? duration(limits.stall_timeout_s) : "none") + " · " + (limits.max_iterations === undefined || limits.max_iterations === null ? "iterations unbounded" : limits.max_iterations + " iterations")],
      ["Handover", handover ? "for " + (handover.audience || "next") + " · " + (handover.max_chars || "?") + " chars" + (handover.extra && handover.extra.length ? " · " + handover.extra.join(", ") : "") : "None"],
      ["Phase policy", "on_step_failure " + (policy.on_step_failure || "?") + " · min_success " + (policy.min_success === undefined || policy.min_success === null ? "?" : policy.min_success) + " · max_parallel " + (policy.max_parallel === undefined || policy.max_parallel === null ? "workflow default" : policy.max_parallel)]
    ];
    var meta = node("dl", { class: "planned-meta" }, rows.map(function (row) { return [node("dt", { text: row[0] }), node("dd", { text: String(row[1]) })]; }));
    replace(byId("panel-planned"), [
      node("p", { class: "planned-note", text: "Planned work, not evidence: nothing has run for this step" + (run.status === "held" ? ", and nothing will until `ohflow go` releases the run." : ".") }),
      meta,
      node("strong", { text: "Brief" }),
      node("pre", { class: "planned-brief", text: plan.brief || "No brief: this is not an agent step." })
    ]);
  }

  function selectInvocation(id, scrollOnMobile) {
    if (!invocation(id)) return;
    S.selected = id;
    S.selectedStep = null;
    renderGraph();
    renderInspector();
    ensureEvidence(id);
    ensureTranscript(id, false);
    if (S.view === "compare") renderCompare(true);
    if (scrollOnMobile && window.matchMedia("(max-width: 820px)").matches) byId("inspector").scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
    announce(invocationTitle(invocation(id)) + " selected");
  }

  function renderInspector(renderPanel) {
    if (S.selectedStep) return renderPlannedInspector();
    var inv = invocation(S.selected);
    if (!inv) return;
    setInspectorMode("invocation");
    byId("inspector-title").textContent = invocationTitle(inv);
    byId("inspector-subtitle").textContent = (inv.harness_executor || "Unknown executor") + " · " + (inv.start_kind === "retry" ? "automatic retry" : (inv.start_kind || "recorded start"));
    setStatusChip(byId("inspector-status"), inv.status, titleCase(inv.status));
    var same = sameRetryInputs(inv) ? "Same fingerprint as failed attempt" : inv.previous_fingerprint ? (inv.previous_fingerprint === inv.fingerprint ? "Same fingerprint as prior attempt" : "Changed fingerprint from prior attempt") : (inv.start_kind === "retry" ? "Retry fingerprint recorded" : "Initial fingerprint");
    var fingerprint = inv.fingerprint || "Fingerprint unavailable";
    var relations = dependencyLine(inv);
    replace(byId("invocation-meta"), [
      node("dt", {}, icon("clock")), node("dd", { text: utc(inv.started, false) + " – " + (inv.finished ? utc(inv.finished, false) : "Running now") + "  (" + duration(inv.status === "running" ? inv.elapsed_s : inv.wall_s) + (inv.status === "running" ? expectedSuffix(inv) : "") + ")" }),
      node("dt", {}, icon("tool")), node("dd", { text: toolCount(inv) }),
      node("dt", {}, icon("file")), node("dd", { text: same }),
      relations ? [node("dt", {}, icon("workflow")), node("dd", { text: relations })] : null,
      node("dt", {}, icon("copy")), node("dd", {}, node("span", { text: short(fingerprint, 24) }), node("button", { class: "copy-button", type: "button", title: "Copy full fingerprint", "aria-label": "Copy full fingerprint", dataset: { copy: fingerprint } }, icon("copy")))
    ]);
    syncInspectorMetaDisclosure();
    updateTabs();
    if (renderPanel !== false) renderActivePanel();
  }

  /* "depends on Scout · feeds Review": the declared step relations of the
   * selected invocation's step, from the recorded depends_on edges. */
  function dependencyLine(inv) {
    var steps = (S.workflow && S.workflow.steps) || [];
    var step = stepFor(inv);
    if (!step) return null;
    var name = function (coord) { var other = steps.find(function (item) { return item.coord === coord; }); return titleCase(other ? (other.role || other.id) : coord); };
    var upstream = (step.depends_on || []).map(name);
    var downstream = steps.filter(function (item) { return (item.depends_on || []).indexOf(step.coord) >= 0; }).map(function (item) { return titleCase(item.role || item.id); });
    var parts = [];
    if (upstream.length) parts.push("depends on " + upstream.join(", "));
    if (downstream.length) parts.push("feeds " + downstream.join(", "));
    if (step.waiting_on === "dependency" && step.reason) parts.push(step.reason);
    return parts.length ? parts.join(" · ") : null;
  }

  /* " · expected N" for a running invocation whose step was estimated. */
  function expectedSuffix(inv) {
    var step = stepFor(inv);
    var estimate = step && step.estimate;
    if (!estimate || !estimate.wall_s || estimate.wall_s.p50 === null || estimate.wall_s.p50 === undefined) return "";
    return " · " + "expected " + duration(estimate.wall_s.p50);
  }

  function toolCount(inv) {
    var transcript = S.transcripts.get(inv.id);
    var records = transcript ? transcript.ledger.records : [];
    var calls = records.reduce(function (n, record) { return n + (record.blocks || []).filter(function (block) { return block.type === "tool_call"; }).length; }, 0);
    if (records.length) return calls + " tool call" + (calls === 1 ? "" : "s") + " loaded";
    if (inv.actions !== null && inv.actions !== undefined) return inv.actions + " recorded actions";
    return "Tool count loads with transcript";
  }

  function updateTabs() {
    document.querySelectorAll('[role="tab"]').forEach(function (tab) {
      var selected = tab.dataset.tab === S.tab;
      tab.setAttribute("aria-selected", selected ? "true" : "false");
      tab.tabIndex = selected ? 0 : -1;
      var panel = byId("panel-" + tab.dataset.tab);
      if (panel) panel.hidden = !selected;
    });
    byId("transcript-controls").hidden = S.tab !== "transcript";
  }

  function setTab(name, focus) {
    S.tab = name;
    updateTabs();
    renderActivePanel();
    if (focus) byId("tab-" + name).focus();
  }

  function renderActivePanel() {
    if (!S.selected) return;
    if (S.tab === "overview") renderOverviewPanel();
    else if (S.tab === "checks") renderChecksPanel();
    else if (S.tab === "artifacts") renderArtifactsPanel();
    else renderTranscriptPanel();
  }

  function evidenceData(id) {
    var record = S.evidence.get(id);
    return record && record.status === "ready" ? record.data : null;
  }

  /* ---- safe readable Markdown: paragraphs, bullets, `code`, **bold** ---- */

  function inlineMd(el, text) {
    String(text).split(/(`[^`]*`|\*\*[^*]*\*\*)/g).forEach(function (token) {
      if (!token) return;
      if (token.length > 2 && token.charAt(0) === "`" && token.charAt(token.length - 1) === "`") {
        el.appendChild(node("code", { class: "inline-code", text: token.slice(1, -1) }));
      } else if (token.length > 4 && token.slice(0, 2) === "**" && token.slice(-2) === "**") {
        el.appendChild(node("strong", { text: token.slice(2, -2) }));
      } else el.appendChild(document.createTextNode(token));
    });
  }

  function mdBlock(text) {
    var host = node("div", { class: "readable-md" });
    String(text || "").replace(/\r\n/g, "\n").split(/\n{2,}/).forEach(function (para) {
      var lines = para.split("\n");
      if (lines.every(function (line) { return /^[-*] /.test(line); })) {
        var list = node("ul");
        lines.forEach(function (line) { var li = node("li"); inlineMd(li, line.replace(/^[-*] /, "")); list.appendChild(li); });
        host.appendChild(list);
        return;
      }
      var p = node("p");
      lines.forEach(function (line, index) { if (index) p.appendChild(document.createTextNode(" ")); inlineMd(p, line); });
      host.appendChild(p);
    });
    return host;
  }

  /* ---- inspector panels ---- */

  function renderOverviewPanel() {
    var inv = invocation(S.selected), evidence = evidenceData(S.selected);
    var panel = byId("panel-overview");
    var items = [node("details", { class: "disclosure", open: true }, node("summary", { text: "Recorded invocation" }), node("div", { class: "disclosure-body" }, node("p", { text: inv.cause || "No terminal cause was recorded." }), node("p", { class: "source-ref", text: sourceText(inv.source_refs) })))];
    if (inv.health) items.push(node("div", { class: "disclosure-body" }, node("strong", { text: "Observed activity signal" }), node("p", { text: inv.health.note || "An activity threshold was observed; this does not prove a stall." })));
    var message = evidence && evidence.final_message || inv.final_message;
    if (message) items.push(finalPreviewCard(S.selected, message, evidence));
    else items.push(node("p", { class: "empty-state", text: "No agent final message is recorded for this invocation." }));
    var commands = commandOutputDisclosure(evidence);
    if (commands) items.push(commands);
    var gate = gateDisclosure(S.selected, evidence);
    if (gate) items.push(gate);
    var events = eventsDisclosure(S.selected, evidence);
    if (events) items.push(events);
    var diagnostics = diagnosticsDisclosure(S.selected, evidence && evidence.diagnostics, "evidence");
    if (diagnostics) items.push(diagnostics);
    replace(panel, items);
  }

  function sourceText(refs) {
    if (!refs) return "Source reference unavailable";
    return Object.keys(refs).map(function (key) { var ref = refs[key] || {}; return key + ": line " + (ref.journal_line || ref.line || "unknown"); }).join(" · ");
  }

  function renderChecksPanel() {
    var panel = byId("panel-checks"), record = S.evidence.get(S.selected), inv = invocation(S.selected);
    if (!record || record.status === "loading") return replace(panel, node("p", { class: "loading-state", text: "Loading independent gate evidence…" }));
    if (record.status === "error") return replace(panel, node("p", { class: "error-state", text: record.error }));
    var evidence = record.data, gate = evidence && evidence.gate;
    if (!gate) return replace(panel, node("p", { class: "empty-state", text: "No independent gate is recorded for this invocation." }));
    var items = [node("div", { class: "check-list" }, checkRows(gate)), node("p", { class: "source-ref", text: evidence.gate_source || sourceText(inv.source_refs) })];
    var events = eventsDisclosure(S.selected, evidence);
    if (events) items.push(events);
    var diagnostics = diagnosticsDisclosure(S.selected, evidence.diagnostics, "evidence");
    if (diagnostics) items.push(diagnostics);
    replace(panel, items);
  }

  function checkRows(gate) {
    var checks = gate.checks || [];
    if (!checks.length) return node("p", { class: "empty-state", text: gate.passed ? "Gate passed with no named checks." : "Gate failed with no named checks." });
    return node("div", { class: "check-list" }, checks.map(function (check) {
      return node("div", { class: "check-row" + (check.passed ? "" : " failed") },
        node("span", { class: "check-mark", "aria-hidden": "true" }, icon(check.passed ? "check" : "x")),
        node("div", { class: "check-facts" },
          node("strong", { text: check.name || "Unnamed check" }),
          node("span", { class: "check-values", text: "observed " + jsonText(check.observed) + " · expected " + jsonText(check.expected) }),
          check.evidence_path ? node("span", { class: "source-ref", text: short(check.evidence_path, 72) }) : null));
    }));
  }

  function eventsDisclosure(id, evidence) {
    var events = evidence && evidence.events || [];
    if (!events.length) return null;
    var key = id + ":events";
    return node("details", { class: "disclosure", open: S.disclosures.has(key), dataset: { disclosure: key } },
      node("summary", {}, "Source events · ", node("span", { class: "source-ref", text: events.length + " recorded" })),
      node("div", { class: "disclosure-body" }, events.map(function (event) {
        return node("div", { class: "event-row" },
          node("strong", { text: (event.event || "event") }),
          node("span", { class: "source-ref", text: utc(event.ts, true) + " · " + eventSource(event) }),
          node("p", { text: event.text || "" }));
      })));
  }

  function eventSource(event) {
    var source = event.source || {};
    return (source.path ? source.path + (source.line ? ":" + source.line : "") : "source reference unavailable");
  }

  function diagnosticsDisclosure(id, list, kind) {
    if (!list || !list.length) return null;
    var key = id + ":diagnostics-" + kind;
    return node("details", { class: "disclosure", open: S.disclosures.has(key), dataset: { disclosure: key } },
      node("summary", {}, titleCase(kind) + " diagnostics · ", node("span", { class: "source-ref", text: list.length + " recorded" })),
      node("div", { class: "disclosure-body" }, list.map(function (text) { return node("p", { text: text }); })));
  }

  /* The approved primary inspector opens with a compact, readable final
   * preview; the full text, the gate facts and the paired calls stay one
   * explicit expansion away inside the same pane. */
  function finalPreviewCard(id, message, evidence) {
    var key = id + ":final";
    var open = S.readerAll || S.expanded.has(key);
    var messageTime = evidence && (evidence.final_message_ts || evidence.final_message_timestamp);
    return node("article", { class: "evidence-card final-preview" + (open ? " expanded" : "") },
      icon("tool"),
      node("header", {},
        node("strong", { text: "Agent final message" }),
        node("span", { class: "final-meta" },
          node("time", { text: utc(messageTime, true) }),
          node("span", { text: evidence ? "model claim · acceptance is separate" : "model claim · full text loads with evidence" }))),
      node("div", { class: "final-body" }, mdBlock(message)),
      node("div", { class: "card-actions" },
        node("button", { class: "text-button", type: "button", dataset: { expand: key }, "aria-expanded": String(open), text: open ? "Show preview only" : "Read full message" })));
  }

  function gateDisclosure(id, evidence) {
    var gate = evidence && evidence.gate;
    if (!gate) return null;
    var checks = gate.checks || [];
    var failed = checks.filter(function (check) { return !check.passed; });
    var key = id + ":gate";
    var label = gate.passed
        ? "Independent gate · " + checks.length + " checks passed"
        : "Independent gate failed · " + ((failed.length ? failed.map(function (check) { return check.name; }) : gate.failed || []).join(", ") || "cause recorded");
    return node("details", { class: "disclosure gate-disclosure", open: S.disclosures.has(key), dataset: { disclosure: key } },
      node("summary", {}, node("span", { class: "gate-summary " + statusTone(gate.passed ? "passed" : "failed"), text: label }), node("span", { class: "source-ref", text: evidence.gate_source || "" })),
      node("div", { class: "disclosure-body" }, checkRows(gate)));
  }

  function collectPairs(records) {
    var module = ledgerModule();
    var results = module && module.collectToolResults
        ? module.collectToolResults(records) : new Map();
    var pairs = [];
    records.forEach(function (record) {
      (record.blocks || []).forEach(function (block) {
        if (block.type === "tool_call" && block.call_id) pairs.push({ id: block.call_id, name: block.name, record: record, input: block.input, result: results.get(String(block.call_id)) || null });
      });
    });
    return pairs;
  }

  function toolsDisclosure(id, state) {
    var pairs = collectPairs(state.ledger.records);
    if (!pairs.length) return null;
    var key = id + ":tools";
    var loaded = pairs.filter(function (pair) { return pair.result; }).length;
    var missing = pairs.length - loaded;
    var summary = pairs.length + " tool call" + (pairs.length === 1 ? "" : "s")
        + " · " + loaded + " result" + (loaded === 1 ? "" : "s") + " loaded"
        + (missing ? " · " + missing + " missing" : "")
        + (state.complete ? "" : " · more may load");
    return node("details", { class: "disclosure tools-disclosure", open: S.disclosures.has(key), dataset: { disclosure: key } },
      node("summary", {}, summary),
      node("div", { class: "disclosure-body" }, pairs.map(function (pair) {
        var ok = pair.result ? (pair.result.block.is_error ? "error result" : "result loaded") : "no result loaded";
        return node("div", { class: "pair-row" },
          node("button", { class: "pair-open", type: "button", dataset: { goto: pair.record.id }, title: "Open this call in the transcript below" },
            node("strong", { text: pair.name || "Tool call" }),
            node("span", { class: "source-ref", text: short(jsonText(pair.input), 70) })),
          node("span", { class: "source-ref" + (pair.result && pair.result.block.is_error ? " unmatched" : ""), text: ok }));
      })));
  }

  /* ---- transcript state and paging ---- */

  function newTranscriptState() {
    var module = ledgerModule();
    return {
      ledger: module ? module.createLedger() : fallbackLedger(),
      cursor: null,
      hasMore: true,
      complete: false,
      diagnostics: [],
      loading: false,
      error: null,
      follow: false,
      total: null,
      lastSerial: 0
    };
  }

  function fallbackLedger() {
    /* Only used if the records asset failed to load: full records still
     * stream, but continuation fragments stay explicitly incomplete rather
     * than silently deduped away. */
    var records = [];
    var seen = new Set();
    return {
      records: records,
      absorb: function (rows) {
        (Array.isArray(rows) ? rows : []).forEach(function (row) {
          if (!row || typeof row !== "object") return;
          if (row.continuation) return;
          var id = row.id != null ? String(row.id) : null;
          if (id !== null && seen.has(id)) return;
          if (id !== null) seen.add(id);
          records.push(row);
        });
        return { added: records.length };
      },
      reset: function () { records.length = 0; seen.clear(); },
      loadedCount: function () { return records.length; },
      pendingCount: function () { return 0; },
      diagnostics: ["The record assembler asset did not load; oversized records cannot be reconstructed."]
    };
  }

  function transcriptState(id) {
    if (!S.transcripts.has(id)) S.transcripts.set(id, newTranscriptState());
    return S.transcripts.get(id);
  }

  function ensureTranscript(id, all) {
    var state = transcriptState(id);
    if (S.static) {
      if (!state.ledger.records.length && S.limitedStatic) { state.hasMore = false; state.complete = true; state.error = "Full transcripts were not embedded in this offline report."; renderActivePanel(); }
      return Promise.resolve();
    }
    var inv = invocation(id);
    if (!inv) return Promise.resolve();
    var liveFollow = state.follow && inv.status === "running";
    if (state.loading || (state.complete && !all && !liveFollow) || (!state.hasMore && state.ledger.records.length && !liveFollow)) return Promise.resolve();
    state.loading = true; state.error = null; renderActivePanel();
    var serial = ++S.requestSerial;
    var url = "/api/transcript?coord=" + encodeURIComponent(inv.coord) + "&attempt=" + encodeURIComponent(inv.attempt) + "&limit=100" + (state.cursor ? "&cursor=" + encodeURIComponent(state.cursor) : "");
    return requestJson(url).then(function (block) {
      if (!S.transcripts.has(id) || serial < (state.lastSerial || 0)) return;
      state.lastSerial = serial;
      if (block.reset) state.ledger.reset();
      state.ledger.absorb(block.records || []);
      state.cursor = block.next_cursor || null; state.hasMore = !!block.has_more; state.complete = !!block.complete; state.total = block.total === null || block.total === undefined ? state.total : block.total;
      state.diagnostics = block.diagnostics || [];
      state.loading = false;
      if (S.selected === id) {
        renderInspector();
        if (S.view === "compare") renderCompare(false);
        if (state.follow) scrollTranscriptEnd();
      }
      if (all && state.hasMore) return ensureTranscript(id, true);
    }).catch(function (error) {
      state.loading = false; state.error = "Transcript could not be loaded: " + error.message;
      if (S.selected === id) renderActivePanel();
    });
  }

  function renderTranscriptPanel() {
    var id = S.selected, inv = invocation(id), panel = byId("panel-transcript"), state = transcriptState(id);
    var ledger = state.ledger;
    var oldTop = panel.scrollTop;
    var oldHeight = panel.scrollHeight;
    var evidence = evidenceData(id);
    var query = byId("transcript-search").value.trim().toLowerCase();
    var loaded = ledger.loadedCount();
    var children = [];
    var message = evidence && evidence.final_message || inv.final_message;
    if (message) children.push(finalPreviewCard(id, message, evidence));
    else children.push(node("p", { class: "empty-state", text: "No agent final message is recorded for this invocation." }));
    var gate = gateDisclosure(id, evidence);
    if (gate) children.push(gate);
    var tools = toolsDisclosure(id, state);
    if (tools) children.push(tools);
    var filtered = ledger.records.filter(function (record) { return !query || jsonText(record).toLowerCase().indexOf(query) >= 0; });
    if (state.error && !ledger.records.length) children.push(node("p", { class: "error-state", text: state.error }));
    else if (!ledger.records.length && state.loading) children.push(node("p", { class: "loading-state", text: "Loading readable transcript…" }));
    else if (!ledger.records.length) children.push(node("p", { class: "empty-state", text: S.static ? "Transcript unavailable in this offline report." : "No readable transcript record is available." }));
    else if (!filtered.length) children.push(node("p", { class: "empty-state", text: "No loaded transcript record matches this search." }));
    else children.push(renderRecords(filtered));
    var diagnostics = (state.diagnostics || []).concat(ledger.diagnostics || []);
    var diag = diagnosticsDisclosure(id + ":stream", diagnostics, "transcript");
    if (diag) children.push(diag);
    if (!S.static && (state.hasMore || !state.complete)) children.push(node("div", { class: "pager" }, node("button", { class: "secondary-button", type: "button", dataset: { transcript: "more" }, disabled: state.loading, text: state.loading ? "Loading…" : "Load 100 more" }), node("button", { class: "secondary-button", type: "button", dataset: { transcript: "all" }, disabled: state.loading, text: "Load full transcript" })));
    replace(panel, children);
    var count = loaded + " record" + (loaded === 1 ? "" : "s") + " loaded";
    if (state.total !== null && state.total !== undefined) count = loaded + " of " + state.total + " logical records loaded";
    if (state.complete) count += " · full transcript";
    else if (state.hasMore) count += " · more available";
    if (state.total != null && state.complete && loaded !== state.total) count += " · " + (state.total - loaded) + " record(s) did not reconstruct; see transcript diagnostics";
    if (query) count += " · " + filtered.length + " matches";
    byId("loaded-count").textContent = count;
    var live = inv.status === "running" && !S.static;
    var follow = byId("follow-latest");
    follow.disabled = !live;
    follow.setAttribute("aria-pressed", state.follow && live ? "true" : "false");
    follow.querySelector("span:last-child").textContent = live && state.follow ? "Following latest" : "Follow latest";
    byId("follow-explanation").textContent = live ? (state.follow ? "Live transcript updates are following" : "Paused until enabled") : "Run finished";
    var reader = byId("reader-mode");
    reader.setAttribute("aria-pressed", S.readerAll ? "true" : "false");
    reader.setAttribute("aria-label", S.readerAll ? "Collapse long record bodies" : "Expand all long record bodies (reader mode)");
    if (state.follow) panel.scrollTop = panel.scrollHeight;
    else panel.scrollTop = Math.min(oldTop, Math.max(0, panel.scrollHeight - Math.max(0, oldHeight - oldTop)));
    if (S.gotoRecord) {
      var target = panel.querySelector('[data-record="' + CSS.escape(S.gotoRecord) + '"]');
      S.gotoRecord = null;
      if (target) { target.scrollIntoView({ block: "start" }); target.classList.add("flash"); window.setTimeout(function () { target.classList.remove("flash"); }, 1200); }
    }
  }

  function renderRecords(records) {
    var module = ledgerModule();
    var results = module && module.collectToolResults
        ? module.collectToolResults(records) : new Map();
    var calls = new Set();
    var settled = new Set();
    records.forEach(function (record) {
      (record.blocks || []).forEach(function (block) {
        if (block.type !== "tool_call" || block.call_id == null) return;
        var id = String(block.call_id);
        calls.add(id);
        if (record.type === "message") settled.add(id);
      });
    });
    var resultOwners = new Set();
    records.forEach(function (record) {
      (record.blocks || []).forEach(function (block, index) {
        if (block.type !== "tool_call" || block.call_id == null) return;
        if (record.type === "message"
            || !settled.has(String(block.call_id))) {
          resultOwners.add(record.id + ":" + index);
        }
      });
    });
    var pairedBlocks = new Map();
    results.forEach(function (item, callId) {
      if (!calls.has(String(callId))) return;
      var indexes = pairedBlocks.get(item.record);
      if (!indexes) {
        indexes = new Set();
        pairedBlocks.set(item.record, indexes);
      }
      (item.blockIndexes || []).forEach(function (index) { indexes.add(index); });
    });
    var cards = records.map(function (record) {
      if (record.continuing) {
        return node("article", { class: "record-card continuing", dataset: { record: record.id } },
          node("span", { class: "record-id", text: record.id }),
          node("div", {}, node("p", { class: "record-block continuing-note", text: "This record is arriving in continuation parts (" + (record.parts || 1) + " loaded so far). Its full content appears here when the final part loads; it is not counted as loaded yet." })));
      }
      var blocks = [];
      (record.blocks || []).forEach(function (block, index) {
        var consumed = pairedBlocks.get(record);
        if (consumed && consumed.has(index)) return;
        blocks.push(renderBlock(block, results, record.id, index, resultOwners));
      });
      if (!blocks.length) {
        var detail = record.status || record.subtype || record.rate_limit_type || record.type;
        blocks.push(node("p", { class: "record-block", text: titleCase(detail) }));
      }
      return node("article", { class: "record-card", dataset: { record: record.id } }, node("span", { class: "record-id", text: record.id }), node("div", {}, node("div", { class: "record-head" }, node("strong", { text: record.role || record.type || "record" }), node("time", { text: utc(record.ts, false) })), blocks, node("div", { class: "source-ref", text: record.source ? record.source.path + ":" + record.source.line : "Source unavailable" })));
    });
    return node("div", { class: "record-list" }, cards);
  }

  function clampable(text) {
    return typeof text === "string" && (text.length > 720 || text.split("\n").length > 10);
  }

  function clampedBody(key, className, text) {
    if (!clampable(text)) return node("pre", { class: className, text: text });
    var open = S.readerAll || S.expanded.has(key);
    return node("div", { class: "clamp-block" + (open ? " open" : "") },
      node("pre", { class: className, text: text }),
      node("button", { class: "text-button", type: "button", dataset: { expand: key }, "aria-expanded": String(open), text: open ? "Show less" : "Show full text" }));
  }

  function renderBlock(block, results, recordId, index, owners) {
    var key = recordId + ":" + index;
    if (block.type === "tool_call") {
      var carries = !owners || owners.has(key);
      var result = carries ? results.get(String(block.call_id)) : null;
      var resultSource = result && result.record && result.record.source;
      return node("section", { class: "record-block tool-pair" }, node("header", {}, icon("tool"), node("strong", { text: block.name || "Tool call" }), node("span", { class: "source-ref", text: block.call_id || "unmatched id" })), clampedBody(key + ":in", "tool-input", jsonText(block.input)), result ? [clampedBody(key + ":out", "tool-result" + (result.block.is_error ? " error" : ""), jsonText(result.block.content)), node("span", { class: "source-ref", text: resultSource ? resultSource.path + ":" + resultSource.line : "Result source unavailable" })] : (carries ? node("p", { class: "tool-result unmatched", text: "Result not present in loaded records." }) : null));
    }
    if (block.type === "text") return clampedBody(key + ":text", "record-block", block.text || "");
    if (block.type === "thinking") return node("p", { class: "record-block thinking" }, clampedBody(key + ":think", "thinking-body", block.text || block.thinking || "Reasoning recorded without readable text."));
    if (block.type === "tool_result") return node("section", { class: "record-block tool-pair" }, node("header", { class: "unmatched", text: "Unmatched tool result · " + (block.call_id || "unknown id") }), clampedBody(key + ":out", "tool-result" + (block.is_error ? " error" : ""), jsonText(block.content)));
    return node("pre", { class: "record-block", text: jsonText(block) });
  }

  function scrollTranscriptEnd() { var panel = byId("panel-transcript"); panel.scrollTop = panel.scrollHeight; }

  function renderArtifactsPanel() {
    var panel = byId("panel-artifacts"), record = S.evidence.get(S.selected);
    if (!record || record.status === "loading") return replace(panel, node("p", { class: "loading-state", text: "Loading artifact index…" }));
    if (record.status === "error") return replace(panel, node("p", { class: "error-state", text: record.error }));
    var artifacts = record.data && record.data.artifacts || [];
    if (!artifacts.length) return replace(panel, node("p", { class: "empty-state", text: "No safe, readable artifact is listed for this invocation." }));
    var list = artifacts.map(function (artifact) {
      var key = S.selected + "::" + artifact.id;
      var content = S.artifactContent.get(key);
      return node("div", {}, node("button", { class: "artifact-button", type: "button", dataset: { artifact: artifact.id } }, icon("file"), node("span", {}, node("strong", { text: artifact.name }), node("small", { text: (artifact.source && artifact.source.path || "Source unavailable") + " · " + (artifact.bytes || 0) + " bytes" })), node("span", { text: content ? "Hide" : "Open here" })), content ? node("pre", { class: "artifact-content", text: content }) : null);
    });
    replace(panel, node("div", { class: "artifact-list" }, list));
  }

  function ensureEvidence(id) {
    var existing = S.evidence.get(id);
    if (existing && (existing.status === "ready" || existing.status === "loading")) return Promise.resolve(existing.data);
    if (S.static) {
      S.evidence.set(id, { status: "error", error: "Independent evidence was not embedded in this offline report." });
      if (S.selected === id) renderActivePanel();
      return Promise.resolve(null);
    }
    var inv = invocation(id);
    if (!inv) return Promise.resolve(null);
    var token = ++S.requestSerial;
    S.evidence.set(id, { status: "loading", token: token });
    if (S.selected === id) renderActivePanel();
    return requestJson("/api/evidence?coord=" + encodeURIComponent(inv.coord) + "&attempt=" + encodeURIComponent(inv.attempt)).then(function (data) {
      var current = S.evidence.get(id);
      if (!current || current.token !== token) return null;
      S.evidence.set(id, { status: "ready", data: data });
      if (S.selected === id) {
        renderInspector();
        if (S.view === "compare") renderCompare(false);
        else renderActivePanel();
      }
      return data;
    }).catch(function (error) {
      S.evidence.set(id, { status: "error", error: "Evidence could not be loaded: " + error.message });
      if (S.selected === id) renderActivePanel();
      return null;
    });
  }

  function loadArtifact(id) {
    var inv = invocation(S.selected), key = S.selected + "::" + id;
    if (S.artifactContent.has(key)) { S.artifactContent.delete(key); renderArtifactsPanel(); return; }
    var evidence = evidenceData(S.selected);
    var item = evidence && (evidence.artifacts || []).find(function (artifact) { return artifact.id === id; });
    if (item && item.content !== undefined) { S.artifactContent.set(key, jsonText(item.content)); renderArtifactsPanel(); return; }
    if (S.static) { S.artifactContent.set(key, "Artifact content was not embedded in this offline report."); renderArtifactsPanel(); return; }
    S.artifactContent.set(key, "Loading…"); renderArtifactsPanel();
    requestJson("/api/evidence?coord=" + encodeURIComponent(inv.coord) + "&attempt=" + encodeURIComponent(inv.attempt) + "&id=" + encodeURIComponent(id)).then(function (data) {
      var artifact = data.artifacts && data.artifacts[0];
      S.artifactContent.set(key, artifact && artifact.content !== undefined ? jsonText(artifact.content) : "No readable content returned."); renderArtifactsPanel();
    }).catch(function (error) { S.artifactContent.set(key, "Artifact could not be loaded: " + error.message); renderArtifactsPanel(); });
  }

  /* ---- Compare: the approved recovery-comparison composition ---- */

  function retryPair() {
    var edges = (S.workflow.edges || []).filter(function (edge) { return edge.kind === "retry" && invocation(edge.from) && invocation(edge.to); });
    var chosen = edges.find(function (edge) { return edge.from === S.selected || edge.to === S.selected; }) || edges[0];
    if (chosen) return { before: invocation(chosen.from), after: invocation(chosen.to), edge: chosen, realRetry: true };
    var current = invocation(S.selected), same = launched().filter(function (inv) { return current && inv.coord === current.coord; });
    if (same.length >= 2) return { before: same[same.length - 2], after: same[same.length - 1], edge: null, realRetry: false };
    return null;
  }

  function comparePair() {
    if (S.compare && invocation(S.compare.before) && invocation(S.compare.after)) {
      var before = invocation(S.compare.before), after = invocation(S.compare.after);
      var edge = (S.workflow.edges || []).find(function (item) { return item.kind === "retry" && item.from === before.id && item.to === after.id; });
      return { before: before, after: after, edge: edge || null, realRetry: !!edge };
    }
    return retryPair();
  }

  function attemptsOf(coord) {
    return launched().filter(function (inv) { return inv.coord === coord; })
        .slice().sort(function (a, b) { return a.attempt - b.attempt; });
  }

  function gateSummaryFor(inv) {
    var evidence = evidenceData(inv.id);
    var gate = evidence && evidence.gate;
    if (gate) {
      var checks = gate.checks || [];
      var failed = checks.filter(function (check) { return !check.passed; });
      if (gate.passed) return { text: checks.length + " checks passed", tone: "passed" };
      var first = failed[0];
      return {
        text: (first ? first.name + ": observed " + jsonText(first.observed) + ", expected " + jsonText(first.expected) : (gate.failed || []).join(", ") || "failed"),
        tone: "failed",
        others: checks.length - failed.length + " other checks passed" + (failed.length > 1 ? "; failed: " + failed.map(function (c) { return c.name; }).join(", ") : "")
      };
    }
    if (inv.gate && inv.gate.passed === false) {
      return { text: (inv.gate.failed || []).join(", ") || inv.short_cause || "failed", tone: "failed", pending: true };
    }
    if (inv.gate && inv.gate.passed === true) return { text: "gate passed", tone: "passed", pending: true };
    return { text: "Independent gate evidence loading…", tone: "neutral", pending: true };
  }

  function recordedEdits(id) {
    var state = S.transcripts.get(id);
    if (!state) return null;
    var edits = [];
    state.ledger.records.forEach(function (record) {
      (record.blocks || []).forEach(function (block) {
        if (block.type === "tool_call" && block.input && typeof block.input.old_string === "string" && typeof block.input.new_string === "string") {
          edits.push({ record: record.id, file: block.input.file_path || "recorded file", old: block.input.old_string, New: block.input.new_string });
        }
      });
    });
    return edits;
  }

  function changeExcerpt(inv) {
    var state = S.transcripts.get(inv.id);
    var edits = recordedEdits(inv.id);
    if (edits === null || (!edits.length && state && (state.loading || (state.hasMore && !state.ledger.records.length)))) {
      return node("p", { class: "source-ref", text: "Recorded change excerpt loads with the attempt transcript…" });
    }
    if (!edits.length) return null;
    var edit = edits[edits.length - 1];
    var key = inv.id + ":edit";
    var open = S.expanded.has(key);
    return node("div", { class: "change-excerpt" + (open ? " open" : "") },
      node("header", {}, node("strong", { text: "Recorded edit · " + edit.file.split(/[\\/]/).pop() })),
      node("div", { class: "excerpt-body" },
        node("p", { class: "excerpt-old", text: "− " + edit.old }),
        node("p", { class: "excerpt-new", text: "+ " + edit.New })),
      node("div", { class: "change-excerpt-footer" },
        node("p", { class: "source-ref", text: "from the attempt's own transcript tool input" }),
        node("button", { class: "text-button", type: "button", dataset: { expand: key }, "aria-expanded": String(open), text: open ? "Hide full edit" : "Show full edit" })));
  }

  function compareClaim(inv) {
    var message = evidenceData(inv.id) && evidenceData(inv.id).final_message
        || inv.final_message || "No final message recorded.";
    var key = inv.id + ":claim";
    var open = S.readerAll || S.disclosures.has(key);
    return node("div", { class: "compare-claim" },
      node("span", { class: "claim-label", text: "Claim (model output), not acceptance:" }),
      node("p", { class: "claim-preview", text: short(message, 112), title: short(message, 240) }),
      message.length > 112 ? node("details", { class: "compare-claim-disclosure", open: open, dataset: { disclosure: key } },
        node("summary", { text: "Full agent claim" }),
        node("p", { class: "compare-claim-full", text: message })) : null);
  }

  function compareAttemptCard(inv, other, side) {
    var gate = gateSummaryFor(inv);
    var relation = "Initial start";
    if (other && other.fingerprint && inv.fingerprint) {
      relation = other.fingerprint === inv.fingerprint
          ? "Same fingerprint as attempt " + other.attempt
          : "Changed inputs from attempt " + other.attempt;
    } else if (inv.start_kind === "retry") relation = "Recorded retry";
    var facts = node("table", { class: "compare-facts" }, node("tbody", {},
      node("tr", {}, node("th", { text: "Independent gate" }), node("td", {}, node("span", { class: "gate-line " + statusTone(gate.tone), text: gate.text }), gate.others ? node("span", { class: "source-ref", text: gate.others }) : null, gate.pending && gate.tone !== "neutral" ? node("span", { class: "source-ref", text: "observed/expected load with evidence" }) : null)),
      node("tr", {}, node("th", { text: "Agent claim" }), node("td", {}, compareClaim(inv)))));
    var factsKey = inv.id + ":compare-facts";
    var supporting = node("details", { class: "compare-supporting", open: S.disclosures.has(factsKey), dataset: { disclosure: factsKey } },
      node("summary", { text: "Timing & source facts" }),
      node("dl", { class: "compare-supporting-facts" },
        node("div", {}, node("dt", { text: "Timing" }), node("dd", { text: utc(inv.started, true) + " → " + (inv.finished ? utc(inv.finished, true) : "in progress") + " · " + duration(inv.wall_s) })),
        node("div", {}, node("dt", { text: "Sources" }), node("dd", {}, node("span", { class: "source-ref", text: sourceFactText(inv) })))));
    var holder = [facts, supporting];
    var excerpt = changeExcerpt(inv);
    if (excerpt) holder.push(excerpt);
    return node("article", { class: "attempt-compare " + side },
      node("header", { class: "attempt-compare-head" },
        node("h2", { class: statusTone(inv.status), text: "Attempt " + inv.attempt + " · " + compareStatusLabel(inv) }),
        node("p", { class: "attempt-meta" },
          node("span", { text: (inv.harness_executor || "Unknown executor") + " · " + (inv.start_kind === "retry" ? "automatic retry" : (inv.start_kind || "initial start")) + " · " + duration(inv.wall_s) }),
          node("span", { class: "fingerprint-relation", text: relation }))),
      holder);
  }

  function compareStatusLabel(inv) {
    if (inv.gate && inv.gate.passed === false) return "check failed";
    if (inv.status === "running") return "Running";
    return titleCase(inv.status);
  }

  function sourceFactText(inv) {
    var refs = inv.source_refs || {};
    var started = refs.started && refs.started.journal_line, finished = refs.finished && refs.finished.journal_line;
    var text = started && finished ? "run log lines " + started + "–" + finished : sourceText(refs);
    var evidence = evidenceData(inv.id);
    if (evidence && evidence.gate_source) text += " · gate: " + evidence.gate_source;
    return text;
  }

  function renderCompareRail(pair) {
    var phases = S.workflow.phases || [];
    var rail = node("aside", { class: "compare-rail" }, node("h2", { text: "Workflow context" }));
    var diagram = node("div", { class: "rail-phases", "aria-hidden": "false" });
    phases.forEach(function (phase, index) {
      if (index) diagram.appendChild(node("div", { class: "rail-barrier" }, node("span", { class: "rail-barrier-line", "aria-hidden": "true" }), node("small", { text: "Phase barrier" })));
      diagram.appendChild(node("div", { class: "rail-phase " + statusTone(phase.state) }, node("span", { text: phase.name }), node("small", { text: titleCase(phase.state) })));
    });
    rail.appendChild(diagram);
    (S.workflow.steps || []).forEach(function (step) {
      var attempts = attemptsOf(step.coord);
      var openKey = "rail:" + step.coord;
      var section = node("details", { class: "rail-step", open: S.disclosures.has(openKey) || attempts.some(function (inv) { return inv.id === S.selected; }), dataset: { disclosure: openKey } },
        node("summary", {}, node("strong", { text: titleCase(step.role || step.id) }), node("span", { class: "source-ref", text: attempts.length + " invocation" + (attempts.length === 1 ? "" : "s") })),
        attempts.map(function (inv) {
          var gate = inv.gate && inv.gate.passed === false ? "check failed" : titleCase(inv.status);
          return node("button", { class: "rail-attempt" + (inv.id === S.selected ? " is-selected" : ""), type: "button", dataset: { select: inv.id } },
            node("span", { class: "rail-mark " + statusTone(inv.status), "aria-hidden": "true" }),
            node("span", { text: "attempt " + inv.attempt }),
            node("span", { class: "rail-status", text: gate }));
        }));
      rail.appendChild(section);
    });
    var cache = S.workflow.cached || [];
    if (cache.length) {
      var cacheKey = "rail:cache";
      rail.appendChild(node("details", { class: "rail-step", open: S.disclosures.has(cacheKey), dataset: { disclosure: cacheKey } },
        node("summary", {}, node("strong", { text: "Cache reuse" }), node("span", { class: "source-ref", text: cache.length + " evaluation" + (cache.length === 1 ? "" : "s") + " · no agent launched" })),
        cache.map(function (item) {
          var reused = invocation(item.evidence_for);
          return node("div", { class: "rail-cache-row" },
            node("span", { text: titleCase((reused && stepFor(reused).role) || item.coord) + " · cached evaluation" }),
            node("button", { class: "event-link", type: "button", dataset: { select: item.evidence_for || "" }, text: reused ? "reuses " + invocationTitle(reused) + " evidence" : "reuse target not launched" }));
        })));
    }
    var campaign = S.workflow.campaign;
    if (campaign && (campaign.rounds || []).length) {
      var judged = campaign.rounds.filter(function (round) { return round.event === "judged"; });
      var campaignKey = "rail:campaign";
      rail.appendChild(node("details", { class: "rail-step", open: S.disclosures.has(campaignKey), dataset: { disclosure: campaignKey } },
        node("summary", {}, node("strong", { text: "Linked campaign" }), node("span", { class: "source-ref", text: judged.length + " rounds" })),
        judged.map(function (round, index) {
          var pos = campaign.rounds.indexOf(round);
          var nextJudge = index + 1 < judged.length ? campaign.rounds.indexOf(judged[index + 1]) : campaign.rounds.length;
          var escalated = campaign.rounds.slice(pos + 1, nextJudge).some(function (item) { return item.event === "escalated"; });
          return node("div", { class: "rail-cache-row" },
            node("span", { text: "Round " + (index + 1) }),
            node("span", { class: round.verdict === "PASS" ? "verdict-pass" : "verdict-revise", text: round.verdict + (round.verdict === "PASS" && escalated ? " · refused" : "") }));
        })));
    }
    rail.appendChild(node("p", { class: "rail-note", text: "Step = planned work. Invocation = an observed execution. Cached evaluations reused evidence without a new agent." }));
    rail.appendChild(node("p", { class: "source-ref", text: pair.realRetry ? "Automatic retry · " + (pair.edge && pair.edge.source || "recorded retry") : "Two recorded starts of the same step; no retry relationship" }));
    return rail;
  }

  function compareSubtitle(pair) {
    if (!pair.realRetry) return "No automatic recovery is recorded; these are two real starts of the same step. Choose attempts below.";
    var before = pair.before, after = pair.after;
    var failedName = before.gate && before.gate.passed === false ? ((before.gate.failed || []).join(", ") || "its check") : "its check";
    var same = before.fingerprint && after.fingerprint && before.fingerprint === after.fingerprint;
    return "Attempt " + before.attempt + " failed the independent gate (" + failedName + "). Attempt " + after.attempt + " is the recorded automatic retry with " + (same ? "the same input fingerprint" : "a changed input fingerprint") + (after.gate && after.gate.passed === true ? "; its gate passed." : ".");
  }

  function captureInspectorState(inspector) {
    if (!inspector) return null;
    var active = document.activeElement;
    return {
      active: active && inspector.contains(active) ? active : null,
      search: byId("transcript-search") ? byId("transcript-search").value : "",
      panels: ["panel-overview", "panel-checks", "panel-transcript", "panel-artifacts"].map(function (id) {
        var panel = byId(id);
        return { id: id, top: panel ? panel.scrollTop : 0, left: panel ? panel.scrollLeft : 0 };
      })
    };
  }

  function restoreInspectorState(snapshot) {
    if (!snapshot) return;
    var search = byId("transcript-search");
    if (search) search.value = snapshot.search;
    snapshot.panels.forEach(function (saved) {
      var panel = byId(saved.id);
      if (panel) { panel.scrollTop = saved.top; panel.scrollLeft = saved.left; }
    });
    if (snapshot.active && typeof snapshot.active.focus === "function") {
      try { snapshot.active.focus({ preventScroll: true }); } catch (_error) { snapshot.active.focus(); }
    }
  }

  function pulseInspector(inspector) {
    if (!inspector || !inspector.classList || typeof requestAnimationFrame !== "function") return;
    inspector.classList.remove("inspector-arrival");
    requestAnimationFrame(function () {
      inspector.classList.add("inspector-arrival");
      window.setTimeout(function () { inspector.classList.remove("inspector-arrival"); }, 240);
    });
  }

  function adoptInspector(container, snapshot, animate) {
    var inspector = byId("inspector");
    if (!inspector || !container || typeof container.appendChild !== "function") return false;
    var moved = inspector.parentElement !== container;
    if (moved) container.appendChild(inspector);
    syncInspectorMetaDisclosure();
    restoreInspectorState(snapshot);
    if (moved && animate) pulseInspector(inspector);
    return true;
  }

  function syncInspectorMetaDisclosure() {
    var details = byId("invocation-meta-disclosure");
    var inv = invocation(S.selected);
    if (!details || !inv) return;
    var key = inv.id + ":inspector-meta";
    details.dataset.inspectorMeta = key;
    details.open = S.view !== "compare" || S.disclosures.has(key);
  }

  function toggleExpanded(key) {
    if (S.expanded.has(key)) S.expanded.delete(key); else S.expanded.add(key);
    return S.expanded.has(key);
  }

  function replaceCompareContents(host, shell, slot, suppliedSnapshot) {
    var inspector = byId("inspector");
    var parking = byId("inspector-parking");
    var snapshot = suppliedSnapshot || captureInspectorState(inspector) || S.inspectorUi;
    if (snapshot) S.inspectorUi = snapshot;
    if (inspector && parking && inspector.parentElement !== parking) parking.appendChild(inspector);
    replace(host, shell);
    adoptInspector(slot, snapshot, !!suppliedSnapshot);
  }

  function renderCompare(force, inspectorSnapshot) {
    var host = byId("compare-view");
    var active = document.activeElement;
    var inspector = byId("inspector");
    var insideInspector = !!(active && inspector && inspector.contains(active));
    if (!force && !insideInspector && host.contains(active)) return;
    var restoreSelect = active && host.contains(active) && !insideInspector
        && active.dataset && active.dataset.select ? active.dataset.select : null;
    var pair = comparePair();
    var main = node("div", { class: "compare-main" });
    var shell = node("div", { class: "compare-shell" });
    if (!pair) {
      var emptyMain = node("div", { class: "compare-main" },
        node("div", { class: "compare-head" }, node("div", {}, node("h1", { id: "compare-heading", text: "Compare attempts" }), node("p", { text: "This run has no retry pair and not enough actual attempts to compare. No recovery has been invented." }))),
        main);
      shell.appendChild(emptyMain);
      replaceCompareContents(host, shell, main, inspectorSnapshot);
      return;
    }
    ensureEvidence(pair.before.id); ensureEvidence(pair.after.id);
    ensureTranscript(pair.before.id, false);
    ensureTranscript(pair.after.id, false);
    var attempts = attemptsOf(pair.before.coord);
    var chooser = node("label", { class: "compare-chooser" },
      node("span", { text: "Choose attempts:" }),
      attemptSelect("before", pair, attempts),
      node("span", { class: "chooser-vs", text: "vs" }),
      attemptSelect("after", pair, attempts));
    var head = node("div", { class: "compare-head" },
      node("div", {},
        node("h1", { id: "compare-heading", text: pair.realRetry ? "Why the retry passed" : "Compare recorded attempts" }),
        node("p", { text: compareSubtitle(pair) })),
      chooser);
    var columns = node("div", { class: "compare-grid" },
      compareAttemptCard(pair.before, pair.after, "before"),
      node("div", { class: "compare-divider" }),
      compareAttemptCard(pair.after, pair.before, "after"));
    var engine = pair.realRetry ? node("div", { class: "compare-engine" },
      node("strong", { text: "Engine decision: " + (pair.edge.label || "automatic retry") }),
      node("span", { class: "source-ref", text: pair.edge.source || "" })) : null;
    var slot = node("div", { class: "compare-inspector-slot" });
    main.appendChild(head); main.appendChild(columns);
    if (engine) main.appendChild(engine);
    main.appendChild(slot);
    shell.appendChild(renderCompareRail(pair)); shell.appendChild(main);
    replaceCompareContents(host, shell, slot, inspectorSnapshot);
    if (restoreSelect) {
      var again = host.querySelector('[data-select="' + CSS.escape(restoreSelect) + '"]');
      if (again) again.focus();
    }
  }

  function attemptSelect(side, pair, attempts) {
    var select = node("select", { dataset: { compareSide: side }, "aria-label": "Compare " + side + " attempt" });
    attempts.forEach(function (inv) {
      var label = "attempt " + inv.attempt + " · " + compareStatusLabel(inv);
      select.appendChild(node("option", { value: inv.id, selected: inv.id === pair[side].id, text: label }));
    });
    if (!Array.from(select.options).some(function (option) { return option.selected; })) {
      select.appendChild(node("option", { value: pair[side].id, selected: true, text: invocationTitle(pair[side]) }));
    }
    return select;
  }

  function renderWorkflowView() {
    var host = byId("workflow-view");
    var phaseEdges = (S.workflow.edges || []).filter(function (edge) { return edge.kind === "phase"; });
    var stepPhase = {};
    (S.workflow.steps || []).forEach(function (step) { stepPhase[step.coord] = step.phase; });
    function barrierLine(phaseCoord) {
      var edges = phaseEdges.filter(function (edge) { return stepPhase[edge.to] === phaseCoord; });
      if (!edges.length) return null;
      var sources = [];
      edges.forEach(function (edge) { if (sources.indexOf(edge.source) < 0) sources.push(edge.source); });
      var fromPhases = [];
      edges.forEach(function (edge) {
        var phaseName = ((S.workflow.phases || []).find(function (phase) { return phase.coord === stepPhase[edge.from]; }) || {}).name;
        if (phaseName && fromPhases.indexOf(phaseName) < 0) fromPhases.push(phaseName);
      });
      return "Phase barrier: every " + fromPhases.join(" and ") + " step settles before this phase starts (" + sources.join("; ") + ").";
    }
    var phases = (S.workflow.phases || []).map(function (phase) {
      var stepEls = (S.workflow.steps || []).filter(function (step) { return step.phase === phase.coord; }).map(function (step) {
        var attempts = launched().filter(function (inv) { return inv.coord === step.coord; });
        return node("details", { class: "workflow-step", open: attempts.some(function (inv) { return inv.id === S.selected; }) || S.selectedStep === step.coord }, node("summary", {}, titleCase(step.role || step.id) + " · " + attempts.length + " observed invocation" + (attempts.length === 1 ? "" : "s") + (step.waiting_on ? " · waiting on " + step.waiting_on : "")), node("p", { class: "source-ref", text: step.reason || ((step.depends_on || []).length ? "depends_on: " + step.depends_on.join(", ") : "No explicit step dependency") }), node("div", { class: "workflow-attempts" }, attempts.length ? attempts.map(function (inv) { return node("button", { type: "button", dataset: { select: inv.id }, class: statusTone(inv.status), text: "Attempt " + inv.attempt + " · " + titleCase(inv.status) }); }) : planButton(step.coord)));
      });
      var barrier = barrierLine(phase.coord);
      var phaseEstimate = estimateLine(phase.estimate);
      var lanes = phase.lanes && phase.lanes.text ? node("small", { class: "phase-estimate", text: phase.lanes.text }) : null;
      return node("section", { class: "workflow-phase" }, node("header", {}, node("h2", {}, node("span", { text: "Phase " + phase.index + " · " + phase.name }), lanes, phaseEstimate ? node("small", { class: "phase-estimate", text: phaseEstimate, title: phase.estimate.basis || "" }) : null), node("span", { class: "status-chip " + statusTone(phase.state), text: titleCase(phase.state) })), barrier ? node("p", { class: "source-ref barrier-note", text: barrier }) : null, stepEls);
    });
    var cached = S.workflow.cached || [];
    var cacheRows = cached.map(function (item) {
      var reused = invocation(item.evidence_for);
      return node("div", { class: "cache-row" },
        node("strong", { text: titleCase((reused && stepFor(reused).role) || item.coord) + " · cached evaluation" }),
        node("span", { class: "source-ref", text: reused ? "reused the evidence of " + invocationTitle(reused) + " — zero new invocations" : "reuse target: " + (item.evidence_for || "not launched") }),
        reused ? node("button", { class: "event-link", type: "button", dataset: { select: reused.id }, text: "Open that evidence" }) : null);
    });
    replace(host, [node("h1", { id: "workflow-view-heading", text: "Planned workflow and observed attempts" }), node("p", { class: "campaign-note", text: "A step is planned work. An invocation is an observed execution. Cached evaluations are listed separately because they launched no agent." }), phases, node("div", { class: "cache-summary cache-inspect" }, icon("tool"), node("div", {}, node("strong", { text: cached.length + " cached evaluation" + (cached.length === 1 ? "" : "s") }), cached.length ? cacheRows : node("p", { text: "No cached evaluation is recorded." })) )]);
  }


  var PLAN_TABS = [["brief", "Brief"], ["position", "Position"], ["gate", "Gate"], ["handover", "Handover"], ["schema", "Schema"], ["command", "Command"], ["limits", "Limits"]];
  var PLAN_OPEN_ALL_STEPS = 8;

  function heldRun() {
    return !!(S.workflow && S.workflow.run && S.workflow.run.status === "held");
  }

  function stampKey(run) {
    var stamp = run && run.plan_stamp;
    return stamp ? stamp.mtime_ns + ":" + stamp.size : null;
  }

  function ensurePlan(force) {
    if (S.static || S.planLoading) return;
    if (S.plan && !force) return;
    S.planLoading = true;
    requestJson("/api/plan").then(function (plan) {
      S.planLoading = false; S.plan = plan; S.planError = null;
      if (S.view === "plan") renderPlanView();
    }, function (error) {
      S.planLoading = false; S.planError = error && error.message ? error.message : String(error);
      if (S.view === "plan") renderPlanView();
    });
  }

  function planTokens(n) { return n === null || n === undefined ? "unknown" : n >= 1000000 ? (n / 1000000).toFixed(1) + " M" : n >= 1000 ? (n / 1000).toFixed(1) + " k" : String(n); }
  function planUsd(c) { return c === null || c === undefined ? "unpriced" : "$" + Number(c).toFixed(2); }
  function planP50(e) { return e && e.wall_s && e.wall_s.p50 !== null && e.wall_s.p50 !== undefined ? e.wall_s.p50 : null; }
  function planText(value, none) { return value === null || value === undefined || value === "" ? none : String(value); }

  function planKind(step) { return node("span", { class: "plan-kind plan-kind-" + step.kind, text: step.kind }); }

  function planModelCell(step) {
    if (step.kind === "gate") return node("span", { class: "plan-none", text: "gate only, no agent" });
    if (!step.harness_executor) return node("span", { class: "plan-none", text: step.kind === "merge" ? "git merge by the orchestrator" : "shell " + (step.shell || "sh") });
    return node("span", {}, step.harness_executor + " · ", node("code", { text: step.model || "model not named" }), step.effort ? node("span", { class: "plan-muted", text: " · effort " + step.effort }) : null);
  }

  function planToolsText(step) {
    var t = step.tools;
    if (!t) return null;
    var parts = [];
    if (t.only && t.only.length) parts.push("only " + t.only.join(", ")); else parts.push("preset " + (t.preset || "default"));
    if (t.allow && t.allow.length) parts.push("allow " + t.allow.join(", "));
    if (t.block && t.block.length) parts.push("block " + t.block.join(", "));
    if (t.enable_browser) parts.push("browser");
    if (t.enable_sub_agents) parts.push("sub-agents");
    return parts.join(" · ");
  }

  function planToolsCell(step) {
    var text = planToolsText(step);
    return text ? node("span", { text: text }) : node("span", { class: "plan-none", text: "—" });
  }

  function planScopeCell(step) {
    if (!(step.write_scope || []).length) return node("span", { class: "plan-none", text: "none reserved" });
    return node("span", { class: "plan-scope" }, step.write_scope.map(function (path) { return node("code", { text: path }); }));
  }

  function planDepsText(step) {
    return (step.depends_on || []).concat((step.consumes || []).map(function (c) { return c + " (handover)"; }));
  }

  function planDepsCell(step) {
    var all = planDepsText(step);
    if (!all.length) return node("span", { class: "plan-none", text: "phase barrier only" });
    return node("span", { class: "plan-deps" }, all.map(function (d, i) { return [i ? " " : null, node("code", { text: d })]; }));
  }

  function planLimitsText(step) {
    return duration(step.execution_timeout_s) + (step.stall_timeout_s ? " · stall " + duration(step.stall_timeout_s) : "") + (step.max_iterations ? " · " + step.max_iterations + " iterations" : "");
  }

  function planRetryText(step) {
    var r = step.retry || {};
    if (!r.max) return "none";
    return "max " + r.max + (r.on && r.on.length ? " on " + r.on.join(", ") : "") + (r.carry_context ? " · carries context" : "");
  }

  function planStepEstimateText(e) {
    if (e && (e.basis === "mechanical" || e.basis === "cached")) return e.basis;
    if (planP50(e) === null) return "no sample";
    return "~" + duration(e.wall_s.p50) + (e.cost_usd ? " · " + planUsd(e.cost_usd) : "");
  }

  function planPhaseEstimateText(phase) {
    var e = phase.estimate;
    if (planP50(e) === null) return "no forecast";
    if (e.wall_s.p50 === 0) return "mechanical, adds nothing to the forecast";
    return "~" + duration(e.wall_s.p50) + " · p80 " + duration(e.wall_s.p80) + " · " + planTokens(e.tokens && e.tokens.p50) + " tokens · " + planUsd(e.cost_usd) + " · " + e.n + " sample" + (e.n === 1 ? "" : "s");
  }

  function planPhaseSummaryText(phase) {
    var counts = {};
    phase.steps.forEach(function (s) { counts[s.kind] = (counts[s.kind] || 0) + 1; });
    var kinds = Object.keys(counts).map(function (k) { return counts[k] + " " + k + (counts[k] === 1 ? "" : k === "merge" ? "s" : " steps"); }).join(", ");
    var atOnce = Math.min(phase.max_parallel, phase.steps.length);
    var parallel = phase.steps.length > 1 ? " · " + atOnce + " in parallel" + (phase.waves > 1 ? " · " + phase.waves + " waves" : "") : "";
    return kinds + parallel;
  }

  function planPolicyText(phase) {
    var declared = phase.declared_max_parallel;
    return "on failure: " + planText(phase.on_step_failure, "quarantine") + " · min success: " + planText(phase.min_success, "all") + " · max parallel: " + (declared === null || declared === undefined ? phase.max_parallel + " (workflow default)" : declared);
  }

  function planGateList(step) {
    if (!(step.gate || []).length) return node("p", { class: "plan-none", text: "none: this step has no mechanical gate. The engine records the step passed when its process exits 0." });
    return node("ol", { class: "plan-gate" }, step.gate.map(function (c) { return node("li", {}, c.text, node("code", { text: c.name + " " + JSON.stringify(c.args || {}) })); }));
  }

  function planHandoverBlock(step) {
    var h = step.handover;
    if (!h) return node("p", { class: "plan-none", text: "none declared. A handover contract names its audience, its character cap and its extra questions, and the consuming steps read it as claims to verify." });
    return node("dl", { class: "plan-meta" }, node("dt", { text: "Audience" }), node("dd", { text: h.audience || "next" }), node("dt", { text: "Max chars" }), node("dd", { text: String(h.max_chars || 6000) }), node("dt", { text: "Extra questions" }), node("dd", { text: (h.extra || []).join("; ") || "none" }));
  }

  function planSchemaBlock(step) {
    if (!step.schema) return node("p", { class: "plan-none", text: "none declared. A step with a schema ends on one JSON block, and the schema_valid gate check reads it." });
    return node("pre", { class: "plan-block", text: jsonText(step.schema) });
  }

  function planCommandBlock(step) {
    var where = step.worktree || "the repository itself";
    if (step.kind === "merge") return node("pre", { class: "plan-block", text: "git merge --no-ff " + step.merge_branch + "\n# message: " + (step.merge_message || "") + "\n# in worktree " + where });
    if (step.command) return node("pre", { class: "plan-block", text: "# shell: " + (step.shell || "sh") + "   worktree: " + where + "\n" + step.command });
    if (step.kind === "gate") return node("p", { class: "plan-none", text: "A gate step has no command. It runs only its gate and starts no agent; its checks are under Gate." });
    return node("p", { class: "plan-none", text: "An agent step has no command. The harness executor starts the agent with the brief." });
  }

  function planLimitsBlock(step) {
    var wt = ((S.plan && S.plan.worktrees) || []).find(function (w) { return w.name === step.worktree; });
    var deps = planDepsText(step);
    var rows = [
      ["Execution timeout", duration(step.execution_timeout_s)],
      ["Stall timeout", step.stall_timeout_s ? duration(step.stall_timeout_s) : "none (idle signal at 300 s amber, 900 s red)"],
      ["Model calls", step.max_iterations ? step.max_iterations + " iterations at most" : "not an agent step"],
      ["Retry", planRetryText(step)],
      ["Command time cap", step.command_time_cap_s ? duration(step.command_time_cap_s) : "none"],
      ["Agent profile", step.profile || "—"],
      ["Box", step.box || "—"],
      ["Unit", step.unit || "a shared step"],
      ["Tool policy", planToolsText(step) || "—"],
      ["Worktree", wt ? wt.name + " · " + wt.path + " · branch " + wt.branch + " from " + wt.base : (step.worktree || "the repository itself")],
      ["Write scope", (step.write_scope || []).length ? step.write_scope.join(", ") : "none reserved"],
      ["Depends on", deps.length ? deps.join(", ") : "phase barrier only"],
      ["Objective", step.objective || step.note || "not stated"]
    ];
    return node("dl", { class: "plan-meta" }, rows.map(function (row) { return [node("dt", { text: row[0] }), node("dd", { text: row[1] })]; }));
  }

  function planBriefBlock(step) {
    if (step.brief) return node("pre", { class: "plan-block plan-brief", text: step.brief });
    if (step.kind === "gate") return node("p", { class: "plan-none", text: "No brief: this is a gate step. It starts no agent; its checks are under Gate." });
    return node("p", { class: "plan-none", text: "No brief: this is a " + step.kind + " step. Its command is under Command." });
  }

  function planPositionBlock(step) {
    if (step.position) return node("pre", { class: "plan-block plan-position", text: step.position });
    return node("p", { class: "plan-none", text: "The position block is not available for this step." });
  }

  function planTab(step) {
    return S.planTabs.get(step.coord) || (step.brief ? "brief" : step.kind === "gate" ? "gate" : "command");
  }

  function planDrawer(step) {
    var active = planTab(step);
    var tabs = node("div", { class: "plan-tabs", role: "tablist" }, PLAN_TABS.map(function (tab) {
      var label = tab[0] === "gate" ? "Gate (" + (step.gate || []).length + ")" : tab[1];
      return node("button", { type: "button", role: "tab", "aria-selected": active === tab[0] ? "true" : "false", dataset: { planTab: step.coord, tab: tab[0] }, text: label });
    }));
    var body;
    if (active === "brief") body = planBriefBlock(step);
    else if (active === "position") body = planPositionBlock(step);
    else if (active === "gate") body = planGateList(step);
    else if (active === "handover") body = planHandoverBlock(step);
    else if (active === "schema") body = planSchemaBlock(step);
    else if (active === "command") body = planCommandBlock(step);
    else body = planLimitsBlock(step);
    return node("div", { class: "plan-drawer" }, tabs, node("div", { class: "plan-drawer-body" }, body));
  }

  function planSearchText(step) {
    return [step.id, step.role, step.objective, step.note, step.model, step.harness_executor, step.worktree, (step.write_scope || []).join(" "), step.command, step.merge_branch, step.brief].join(" ").toLowerCase();
  }

  function planStepRow(step, index) {
    var open = S.planDrawers.has(step.coord);
    var checks = (step.gate || []).length;
    var row = node("tr", { class: "plan-step", dataset: { planRow: step.coord } },
      node("td", { class: "plan-num", text: String(index + 1) }),
      node("td", {}, planKind(step)),
      node("td", {}, node("span", { class: "plan-role", text: step.role || step.id }), node("small", { class: "plan-objective", text: step.objective || step.note || step.coord })),
      node("td", {}, planModelCell(step)),
      node("td", {}, planToolsCell(step)),
      node("td", {}, planScopeCell(step)),
      node("td", {}, node("code", { text: step.worktree || "repo" })),
      node("td", {}, planDepsCell(step)),
      node("td", { class: "plan-muted", text: planLimitsText(step) }),
      node("td", { class: "plan-muted", text: planRetryText(step) }),
      node("td", { class: "plan-muted", text: checks ? checks + (checks === 1 ? " check" : " checks") : "none" }),
      node("td", { class: "plan-muted", text: planStepEstimateText(step.estimate) }),
      node("td", {}, node("button", { type: "button", class: "plan-open-button", "aria-expanded": open ? "true" : "false", dataset: { planStep: step.coord }, text: open ? "Close" : "Open" })));
    var drawer = open ? node("tr", { class: "plan-drawer-row" }, node("td", { colspan: "13" }, planDrawer(step))) : null;
    return [row, drawer];
  }

  function planPhaseOpen(phase, query, openAll) {
    if (query) return true;
    if (S.planPhases.has(phase.coord)) return S.planPhases.get(phase.coord);
    if (openAll || phase.index === 1) return true;
    return phase.steps.some(function (s) { return S.planDrawers.has(s.coord); });
  }

  function planPhaseSection(phase, query, openAll) {
    var steps = phase.steps.filter(function (s) { return !query || planSearchText(s).indexOf(query) >= 0; });
    if (query && !steps.length) return null;
    var recorded = ((S.workflow && S.workflow.phases) || []).find(function (p) { return p.coord === phase.coord; });
    var phaseState = recorded ? recorded.state : "waiting";
    var details = node("details", { class: "plan-phase", open: planPhaseOpen(phase, query, openAll), dataset: { planPhase: phase.coord } });
    details.addEventListener("toggle", function () { S.planPhases.set(phase.coord, details.open); });
    var chip = node("span", { class: "status-chip " + statusTone(phaseState), dataset: { planChip: phase.coord }, text: titleCase(phaseState) });
    var summary = node("summary", {}, node("span", { class: "plan-phase-name", text: "Phase " + phase.index + " · " + phase.name }), chip, node("small", { text: planPhaseSummaryText(phase) }), node("small", { text: planPolicyText(phase) }), node("small", { text: planPhaseEstimateText(phase) }));
    var atOnce = Math.min(phase.max_parallel, phase.steps.length);
    var running = atOnce + " step" + (atOnce === 1 ? " runs" : "s run") + " at once; " + phase.waves + " wave" + (phase.waves === 1 ? "" : "s") + " of " + duration(phase.worst_timeout_s) + " at most.";
    var barrier = phase.index > 1 ? "Phase barrier: every step of phase " + (phase.index - 1) + " settles before this phase starts. Inside the phase, " + running : "First phase: starts at go. " + running;
    var head = node("thead", {}, node("tr", {}, ["#", "Kind", "Step", "Harness executor · model", "Tools", "Write scope", "Worktree", "Depends on", "Limits", "Retry", "Gate", "Forecast", ""].map(function (t) { return node("th", { text: t }); })));
    var rows = steps.map(function (step) { return planStepRow(step, phase.steps.indexOf(step)); });
    append(details, [summary, node("div", { class: "plan-phase-body" }, node("p", { class: "plan-barrier", text: barrier }), node("table", { class: "plan-steps" }, head, node("tbody", {}, rows)))]);
    return details;
  }

  function planTile(title, big, small) {
    return node("div", { class: "plan-tile" }, node("h3", { text: title }), node("strong", { text: big }), node("p", { text: small }));
  }

  function planStrip(plan) {
    var t = plan.totals || {}, k = t.kinds || {}, e = plan.estimate || {}, run = plan.run || {};
    var history = e.history || {};
    var unknown = planP50(e) === null;
    return node("section", { class: "plan-strip" },
      planTile("Plan", t.phases + " phases · " + t.steps + " steps", (k.agent || 0) + " agent · " + (k.command || 0) + " command · " + (k.merge || 0) + " merge" + (k.gate ? " · " + k.gate + " gate" : "") + " · phases run in order, steps of a phase in parallel"),
      node("div", { class: "plan-tile" }, node("h3", { text: "Agents" }), node("strong", { text: (k.agent || 0) + " agent steps" }), node("ul", {}, (t.by_model || []).map(function (m) { return node("li", { text: m.n + " × " + (m.harness_executor || "harness executor not named") + " · " + (m.model || "model not named") + (m.effort ? " · effort " + m.effort : "") }); }))),
      planTile("Forecast", unknown ? "unknown" : "~" + duration(e.wall_s.p50) + " · p80 " + duration(e.wall_s.p80), unknown ? (e.generated ? "the estimate has no sample for these steps" : "no estimate.json for this run") : planTokens(e.tokens && e.tokens.p50) + " tokens · " + planUsd(e.cost_usd) + " · " + e.confidence + " confidence · " + (history.samples || 0) + " samples from " + (history.sources || 0) + " summaries"),
      planTile("Timeouts", "at most " + duration(t.timeout_bound_s), "waves × longest execution timeout, phases added in order · stall timeouts per step below"),
      planTile("Parallelism and worktrees", "max " + planText(run.max_parallel, "?") + " at once · " + t.worktrees + " worktrees", "base branch " + planText(run.base_branch, "?") + " · auto-resume " + planText(run.auto_resume, "0") + " passes · transient backoff " + planText(run.transient_backoff_s, "0") + " s"),
      planTile("Checks and contracts", t.gate_checks + " gate checks on " + t.gated_steps + " steps", "retry declared on " + t.retry_steps + " steps · handover contracts " + t.handovers + " · schemas " + t.schemas));
  }

  function planHeldBanner(plan, run) {
    if (run.status !== "held") return null;
    var planRun = plan.run || {};
    return node("section", { class: "held-banner", dataset: { planBanner: "held" } }, node("strong", { text: "Held: waiting for go" }), node("span", { text: "since " + utc(planRun.held_since, true) + " · nothing has run" }), planRun.go_command ? node("code", { text: planRun.go_command }) : null, node("small", { text: "An edit to the workflow module while held is what runs; the plan is read again after go." }));
  }

  function renderPlanView() {
    var host = byId("plan-view");
    if (!host) return;
    var run = (S.workflow && S.workflow.run) || (S.plan && S.plan.run) || {};
    var plan = S.plan;
    if (!plan) {
      var text = S.planError ? "The plan could not be loaded: " + S.planError : S.static ? "This report embeds no plan payload." : "Reading the plan…";
      replace(host, [node("h1", { id: "plan-view-heading", text: "Plan" }), node("p", { class: "plan-lead", text: text })]);
      return;
    }
    var query = S.search.trim().toLowerCase();
    var openAll = ((plan.totals || {}).steps || 0) <= PLAN_OPEN_ALL_STEPS;
    var sections = (plan.phases || []).map(function (phase) { return planPhaseSection(phase, query, openAll); }).filter(Boolean);
    var heading = node("div", { class: "plan-heading" },
      node("div", {}, node("h1", { id: "plan-view-heading", text: "Plan: every phase, its steps and what each step may do" }), node("p", { class: "plan-lead", text: "Planned work, not evidence. A phase opens to its steps; a step opens to its brief, its position block, its gate checks, its handover contract, its schema, its command and its limits. Search filters the step rows." })),
      node("div", { class: "plan-controls" }, node("button", { type: "button", class: "text-button", dataset: { planPhases: "open" }, text: "Expand all phases" }), node("button", { type: "button", class: "text-button", dataset: { planPhases: "close" }, text: "Collapse all" })));
    var empty = query && !sections.length ? node("p", { class: "plan-empty", role: "status", text: "No step matches this search." }) : null;
    var diagnostics = (plan.diagnostics || []).length ? node("p", { class: "plan-lead", text: plan.diagnostics.join(" ") }) : null;
    replace(host, [planHeldBanner(plan, run), planStrip(plan), node("section", { class: "plan-tree" }, heading, diagnostics, empty, sections)]);
  }

  function refreshPlanChrome() {
    var host = byId("plan-view");
    if (!host || !S.plan || !host.querySelectorAll) return;
    var run = (S.workflow && S.workflow.run) || {};
    var banner = host.querySelector("[data-plan-banner]");
    if (banner && run.status !== "held") banner.hidden = true;
    host.querySelectorAll("[data-plan-chip]").forEach(function (chip) {
      var phase = (S.workflow.phases || []).find(function (p) { return p.coord === chip.dataset.planChip; });
      if (!phase) return;
      chip.className = "status-chip " + statusTone(phase.state);
      chip.textContent = titleCase(phase.state);
    });
  }

  function togglePlanDrawer(coord) {
    if (S.planDrawers.has(coord)) S.planDrawers.delete(coord); else S.planDrawers.add(coord);
    renderPlanView();
  }

  function setPlanTab(coord, tab) {
    S.planTabs.set(coord, tab);
    renderPlanView();
  }

  function setPlanPhases(open) {
    ((S.plan && S.plan.phases) || []).forEach(function (phase) { S.planPhases.set(phase.coord, open); });
    renderPlanView();
  }

  function planPhaseOf(coord) {
    return ((S.plan && S.plan.phases) || []).find(function (phase) { return phase.steps.some(function (s) { return s.coord === coord; }); }) || null;
  }

  /* A packet has no plan and a report can lack one: `/api/plan` answers 404
     for the first and a page from disk cannot ask for the second. */
  function planAvailable() {
    if (S.plan) return true;
    if (S.static) return false;
    return !(S.workflow && S.workflow.source && S.workflow.source !== "run");
  }

  function inspectPlannedStep(coord) {
    return planAvailable() ? openPlanStep(coord) : selectStep(coord);
  }

  function openPlanStep(coord) {
    selectStep(coord);
    S.planDrawers.add(coord);
    var phase = planPhaseOf(coord);
    if (phase) S.planPhases.set(phase.coord, true);
    setView("plan");
    var host = byId("plan-view");
    var row = host && host.querySelector ? host.querySelector('[data-plan-row="' + coord + '"]') : null;
    if (row && row.scrollIntoView) row.scrollIntoView({ block: "start" });
  }

  function setView(view) {
    var inspectorSnapshot = (S.view === "workflow" || S.view === "plan") && S.inspectorUi
        ? S.inspectorUi : captureInspectorState(byId("inspector"));
    if (inspectorSnapshot) S.inspectorUi = inspectorSnapshot;
    S.view = view;
    document.querySelectorAll("[data-view]").forEach(function (button) { var active = button.dataset.view === view; button.classList.toggle("is-active", active); button.setAttribute("aria-pressed", active ? "true" : "false"); });
    byId("overview-layout").hidden = view !== "order";
    byId("compare-view").hidden = view !== "compare";
    byId("workflow-view").hidden = view !== "workflow";
    byId("plan-view").hidden = view !== "plan";
    byId("fit-graph").hidden = view !== "order";
    if (view === "compare") renderCompare(false, inspectorSnapshot);
    else adoptInspector(byId("overview-layout"), inspectorSnapshot, true);
    if (view === "compare") return;
    byId("overview-layout").classList.remove("solo");
    if (view === "workflow") renderWorkflowView();
    if (view === "plan") { renderPlanView(); ensurePlan(); }
  }

  function renderAll() {
    if (!S.workflow) return;
    if (!S.selected || !invocation(S.selected)) S.selected = chooseDefault();
    renderChrome(); renderAttention(); renderLanes(); renderGraph(); renderLivePeek(); renderDigest(); renderCampaign();
    if (S.selectedStep) renderPlannedInspector();
    else if (S.selected) renderInspector();
    setView(S.view);
    pollPeek();
  }

  function reportRenderFailure(error) {
    var banner = byId("offline-banner");
    if (banner) {
      banner.hidden = false;
      banner.textContent = "Dashboard data loaded, but this update could not be rendered. The last rendered view remains available.";
    }
    announce("Dashboard update could not be rendered" + (error && error.message ? ": " + error.message : "."));
    if (typeof console !== "undefined" && console.error) console.error(error);
  }

  function reportRequestFailure() {
    S.connected = false;
    renderChrome();
  }

  function applyPolledWorkflow(workflow) {
    S.connected = true;
    var stampBefore = stampKey(S.workflow && S.workflow.run);
    S.workflow = workflow;
    try {
      renderChrome(); renderAttention(); renderLanes(); renderGraph(); renderLivePeek(); renderDigest(); renderCampaign();
      pollPeek();
      if (S.plan && stampKey(workflow.run) !== stampBefore) ensurePlan(true);
      else if (S.view === "plan") refreshPlanChrome();
      var inv = invocation(S.selected);
      if (S.selectedStep) renderPlannedInspector();
      else if (!inv) selectInvocation(chooseDefault(), false);
      else {
        var inspector = byId("inspector");
        if (!inspector || !inspector.contains(document.activeElement)) renderInspector(false);
        var state = transcriptState(inv.id);
        if (state.follow && inv.status === "running") ensureTranscript(inv.id, false);
      }
      if (S.view === "compare") renderCompare(false);
      if (S.view === "workflow") renderWorkflowView();
      return true;
    } catch (error) {
      reportRenderFailure(error);
      return false;
    }
  }

  function poll() {
    if (S.static) return;
    requestJson("/api/workflow").then(applyPolledWorkflow, reportRequestFailure).finally(function () {
      var status = S.workflow && S.workflow.run && S.workflow.run.status;
      if (!S.connected && TERMINAL.has(status)) { announce("The run ended and its dashboard stopped; live polling stopped."); return; }
      S.pollTimer = window.setTimeout(poll, 2000);
    });
  }

  function bindEvents() {
    document.addEventListener("click", function (event) {
      var view = event.target.closest("[data-view]");
      if (view) return setView(view.dataset.view);
      var select = event.target.closest("[data-select]");
      if (select) return selectInvocation(select.dataset.select, true);
      var plannedStep = event.target.closest("[data-select-step]");
      if (plannedStep) return inspectPlannedStep(plannedStep.dataset.selectStep);
      var planStep = event.target.closest("[data-plan-step]");
      if (planStep) return togglePlanDrawer(planStep.dataset.planStep);
      var planTabButton = event.target.closest("[data-plan-tab]");
      if (planTabButton) return setPlanTab(planTabButton.dataset.planTab, planTabButton.dataset.tab);
      var planPhases = event.target.closest("[data-plan-phases]");
      if (planPhases) return setPlanPhases(planPhases.dataset.planPhases === "open");
      var peek = event.target.closest("[data-peek]");
      if (peek) {
        selectInvocation(peek.dataset.peek, true);
        if (S.tab !== "transcript") setTab("transcript", false);
        return;
      }
      var copy = event.target.closest("[data-copy]");
      if (copy) {
        var text = copy.dataset.copy;
        var label = copy.dataset.copyLabel || "Fingerprint";
        var idle = label === "Fingerprint" ? "Copy full fingerprint" : "Copy the command";
        var done = function () { copy.setAttribute("aria-label", "Copied"); copy.title = "Copied"; announce(label + " copied"); window.setTimeout(function () { copy.setAttribute("aria-label", idle); copy.title = idle; }, 1500); };
        if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done).catch(function () {});
        return;
      }
      var transcript = event.target.closest("[data-transcript]");
      if (transcript) return ensureTranscript(S.selected, transcript.dataset.transcript === "all");
      var artifact = event.target.closest("[data-artifact]");
      if (artifact) return loadArtifact(artifact.dataset.artifact);
      var expand = event.target.closest("[data-expand]");
      if (expand) {
        var key = expand.dataset.expand;
        toggleExpanded(key);
        if (S.selected && byId("inspector").contains(expand)) renderActivePanel();
        else if (S.view === "compare") renderCompare(true);
        return;
      }
      var goto = event.target.closest("[data-goto]");
      if (goto) {
        S.gotoRecord = goto.dataset.goto;
        if (S.tab !== "transcript") setTab("transcript", false);
        else renderTranscriptPanel();
        return;
      }
    });
    document.addEventListener("change", function (event) {
      var side = event.target.closest("[data-compare-side]");
      if (!side) return;
      var value = side.value;
      if (!S.compare) { var pair = retryPair(); if (pair) S.compare = { before: pair.before.id, after: pair.after.id }; else return; }
      var other = side.dataset.compareSide === "before" ? "after" : "before";
      if (S.compare[other] === value) return;
      S.compare[side.dataset.compareSide] = value;
      renderCompare(true);
    });
    document.addEventListener("toggle", function (event) {
      var target = event.target;
      if (target && target.dataset && target.dataset.inspectorMeta) {
        if (S.view === "compare") {
          if (target.open) S.disclosures.add(target.dataset.inspectorMeta);
          else S.disclosures.delete(target.dataset.inspectorMeta);
        }
        return;
      }
      if (!target || !target.dataset || !target.dataset.disclosure) return;
      var key = target.dataset.disclosure;
      if (target.open) S.disclosures.add(key); else S.disclosures.delete(key);
    }, true);
    document.querySelectorAll('[role="tab"]').forEach(function (tab) {
      tab.addEventListener("click", function () { setTab(tab.dataset.tab, false); });
      tab.addEventListener("keydown", function (event) {
        if (["ArrowLeft", "ArrowRight", "Home", "End"].indexOf(event.key) < 0) return;
        event.preventDefault();
        var tabs = Array.from(document.querySelectorAll('[role="tab"]'));
        var index = tabs.indexOf(tab);
        if (event.key === "ArrowRight") index = (index + 1) % tabs.length;
        if (event.key === "ArrowLeft") index = (index - 1 + tabs.length) % tabs.length;
        if (event.key === "Home") index = 0;
        if (event.key === "End") index = tabs.length - 1;
        setTab(tabs[index].dataset.tab, true);
      });
    });
    byId("transcript-search").addEventListener("input", renderTranscriptPanel);
    byId("reader-mode").addEventListener("click", function () {
      S.readerAll = !S.readerAll;
      renderTranscriptPanel();
      announce(S.readerAll ? "Reader mode on: every loaded record body is fully expanded" : "Reader mode off: long record bodies collapse");
    });
    byId("global-search").addEventListener("input", function (event) { S.search = event.target.value; renderGraph(); if (S.view === "plan") renderPlanView(); });
    byId("fit-graph").addEventListener("click", function () {
      var scroll = byId("graph-scroll"), selected = byId("graph-grid").querySelector('[data-invocation="' + CSS.escape(S.selected || "") + '"]');
      if (selected) selected.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", inline: "center", block: "nearest" });
      else scroll.scrollLeft = 0;
      announce("Graph fitted around the selected invocation. Node spacing remains ordinal.");
    });
    byId("follow-latest").addEventListener("click", function () {
      var state = transcriptState(S.selected), inv = invocation(S.selected);
      if (!inv || inv.status !== "running" || S.static) return;
      state.follow = !state.follow;
      renderTranscriptPanel();
      if (state.follow) { ensureTranscript(S.selected, false); scrollTranscriptEnd(); announce("Following the latest transcript record"); }
      else announce("Follow latest paused");
    });
    byId("panel-transcript").addEventListener("scroll", function () {
      var state = S.selected && transcriptState(S.selected);
      var panel = byId("panel-transcript");
      if (state && state.follow && panel.scrollHeight - panel.scrollTop - panel.clientHeight > 80) { state.follow = false; renderTranscriptPanel(); announce("Follow latest paused while you inspect older records"); }
    }, { passive: true });
    byId("appearance-button").addEventListener("click", function () {
      var high = document.documentElement.dataset.contrast !== "high";
      document.documentElement.dataset.contrast = high ? "high" : "normal";
      this.setAttribute("aria-pressed", high ? "true" : "false");
      try { localStorage.setItem("ohflow-contrast", high ? "high" : "normal"); } catch (_error) {}
    });
    byId("density-button").addEventListener("click", function () {
      var comfortable = !document.body.classList.contains("comfortable");
      document.body.classList.toggle("comfortable", comfortable);
      this.setAttribute("aria-pressed", comfortable ? "true" : "false");
      this.setAttribute("aria-label", comfortable ? "Use compact spacing" : "Use comfortable spacing");
      try { localStorage.setItem("ohflow-density", comfortable ? "comfortable" : "compact"); } catch (_error) {}
      requestAnimationFrame(drawEdges);
    });
    document.addEventListener("keydown", function (event) { if (event.key === "Escape") hidePeek(); });
    window.addEventListener("resize", function () { requestAnimationFrame(function () { drawEdges(); drawDateCrossings(launched()); }); });
  }

  function restorePreferences() {
    try {
      var contrast = localStorage.getItem("ohflow-contrast");
      if (contrast === "high") { document.documentElement.dataset.contrast = "high"; byId("appearance-button").setAttribute("aria-pressed", "true"); }
      var density = localStorage.getItem("ohflow-density");
      if (density === "comfortable") { document.body.classList.add("comfortable"); byId("density-button").setAttribute("aria-pressed", "true"); }
    } catch (_error) {}
  }

  function boot() {
    restorePreferences(); bindEvents(); parseEmbedded();
    if (S.workflow) {
      if (heldRun()) S.view = "plan";
      try { renderAll(); } catch (error) { reportRenderFailure(error); }
      if (S.selected) { ensureEvidence(S.selected); ensureTranscript(S.selected, false); }
    } else {
      requestJson("/api/workflow").then(function (workflow) {
        S.workflow = workflow; S.connected = true;
        if (heldRun()) S.view = "plan";
        try { renderAll(); } catch (error) { reportRenderFailure(error); }
        if (S.selected) { ensureEvidence(S.selected); ensureTranscript(S.selected, false); }
        poll();
      }, function (error) {
        S.connected = false;
        byId("offline-banner").hidden = false;
        byId("offline-banner").textContent = "Workflow data could not be loaded: " + error.message;
      });
    }
  }

  if (typeof globalThis !== "undefined" && globalThis.__OHFLOW_TEST__) {
    globalThis.__OHFLOW_TEST_API__ = {
      state: S,
      adoptInspector: adoptInspector,
      captureInspectorState: captureInspectorState,
      changeExcerpt: changeExcerpt,
      clampedBody: clampedBody,
      compareClaim: compareClaim,
      replaceCompareContents: replaceCompareContents,
      reportRenderFailure: reportRenderFailure,
      reportRequestFailure: reportRequestFailure,
      toggleExpanded: toggleExpanded,
      parseEmbedded: parseEmbedded,
      renderPlanView: renderPlanView,
      renderRecords: renderRecords,
      togglePlanDrawer: togglePlanDrawer,
      setPlanTab: setPlanTab,
      setPlanPhases: setPlanPhases,
      bindEvents: bindEvents
    };
  } else boot();
}());

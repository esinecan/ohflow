"""Synthetic run directories for the dashboard and exit-report tests.

The dashboard reads files only, so a test can describe any moment of a run by
writing the files that moment leaves behind: a `workflow.json`, a hand-written
`run-log.jsonl` with fixed timestamps, and a `supervisor.pid`. No engine runs
and no clock is waited on; every test passes `now` explicitly. `boot_page`
then shows what the shipping page draws from that moment's `/api/workflow`.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures" / "dashboard"
G1_RUN = FIXTURES / "g1-run"
G1_ATTEMPT = G1_RUN / "phases" / "01.sweep" / "01.flaky" / "attempts" / "02"

#: 2026-09-30T12:00:00Z. Every synthetic run log is stamped relative to it.
T0 = _dt.datetime(2026, 9, 30, 12, 0, 0, tzinfo=_dt.timezone.utc).timestamp()

__all__ = ["FIXTURES", "G1_RUN", "G1_ATTEMPT", "T0", "stamp",
           "agent", "command", "merge", "workflow_json", "plan28", "RunLog",
           "mark_alive", "copy_tree", "boot_page"]


def stamp(offset_s: float) -> str:
    """The run log's own timestamp shape, `offset_s` after T0."""
    return _dt.datetime.fromtimestamp(T0 + offset_s, _dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def agent(step_id: str, *, harness_executor: str = "pi", brief: str = "Do the thing.",
          objective: str | None = None, note: str | None = None,
          execution_timeout_s: int = 900, stall_timeout_s: int | None = None,
          max_iterations: int = 60, retry_max: int = 0) -> dict:
    return {
        "id": step_id, "kind": "agent", "note": note, "objective": objective,
        "execution_timeout_s": execution_timeout_s, "stall_timeout_s": stall_timeout_s,
        "retry": {"max": retry_max, "on": [], "carry_context": False},
        "command": None, "merge_branch": None,
        "agent": {"role": f"role {step_id}", "brief": brief, "harness_executor": harness_executor,
                  "model": {"model": "zai/glm-5.3-flash"},
                  "max_iterations": max_iterations},
    }


def command(step_id: str, cmd: str = "echo DONE") -> dict:
    return {"id": step_id, "kind": "command", "command": cmd, "note": None,
            "objective": None, "execution_timeout_s": 60, "stall_timeout_s": None,
            "retry": {"max": 0, "on": [], "carry_context": False},
            "agent": None, "merge_branch": None}


def merge(step_id: str, branch: str, *, worktree: str = "loop",
          depends_on: tuple[str, ...] = ()) -> dict:
    return {"id": step_id, "kind": "merge", "command": None, "note": None,
            "objective": None, "execution_timeout_s": 5400,
            "stall_timeout_s": None, "worktree": worktree,
            "depends_on": list(depends_on),
            "retry": {"max": 0, "on": [], "carry_context": False},
            "agent": None, "merge_branch": branch,
            "merge_message": f"merge {branch}"}


def workflow_json(run_dir: Path, phases: list[tuple[str, list[dict], int]], *,
                  name: str = "synthetic", auto_resume: int = 0) -> dict:
    """Write `workflow.json` in the shape `to_jsonable(Workflow)` produces."""
    workflow = {
        "name": name, "max_parallel": 2, "auto_resume": auto_resume,
        "phases": [{"name": pname, "slug_override": None,
                    "max_parallel": mp, "on_step_failure": "quarantine",
                    "min_success": "all", "steps": steps}
                   for pname, steps, mp in phases],
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "workflow.json").write_text(json.dumps(workflow, indent=2),
                                           encoding="utf-8")
    return workflow


#: The brief the one long step of `plan28` carries: longer than the graph cap
#: of 2,000 characters, so a Plan view that shows it whole proves the cap is
#: the artifact cap. It holds a word no other field holds, for the search.
PLAN28_LONG_BRIEF = ("# Task: consolidate the five sweeps\n\n"
                     + "Read every sweep file and write what they agree on. "
                     * 60 + "\n\nThe needle word is quokka.\n")

_SWEEP_GATE = {"checks": [
    {"name": "commits_past_base", "args": {"min": 1, "since": "step_start"}},
    {"name": "tree_clean", "args": {}},
    {"name": "ownership", "args": {"allowed": ["sweep/*.md"],
                                   "since": "step_start"}},
    {"name": "no_ai_attribution", "args": {"since": "step_start"}},
    {"name": "final_message_matches", "args": {"regex": "DONE:"}},
]}


def _claude_agent(step_id: str, role: str, *, model: str, brief: str,
                  worktree: str, write_scope: list[str], objective: str,
                  execution_timeout_s: int = 3000) -> dict:
    return {
        "id": step_id, "kind": "agent", "note": None, "objective": objective,
        "execution_timeout_s": execution_timeout_s, "stall_timeout_s": 900,
        "worktree": worktree, "write_scope": write_scope,
        "depends_on": [], "consumes": [], "gate": _SWEEP_GATE,
        "retry": {"max": 0, "on": [], "carry_context": False},
        "command": None, "shell": "sh", "merge_branch": None,
        "merge_message": None, "schema": None, "handover": None, "pool": None,
        "agent": {"role": role, "brief": brief, "harness_executor": "claude",
                  "model": {"model": model, "base_url": "", "api_key_env": "",
                            "params": {"effort": "high"}, "extra_body": {}},
                  "tools": {"preset": "default", "enable_browser": False,
                            "enable_sub_agents": False,
                            "only": ["terminal", "file_editor"], "allow": [],
                            "block": []},
                  "skills": [], "skills_dir": None, "mcp_config": None,
                  "max_iterations": 120, "fork_session": None,
                  "command_time_cap_s": None, "agent_profile": "hermetic",
                  "box": None},
    }


def _shell(step_id: str, cmd: str, note: str, timeout_s: int = 300) -> dict:
    step = command(step_id, cmd)
    step.update({"note": note, "execution_timeout_s": timeout_s,
                 "worktree": "loop", "shell": "sh"})
    return step


def plan28(run_dir: Path) -> dict:
    """A 28-step, 20-phase `workflow.json` in the shape of the loop-1 run:
    11 agent steps, 12 command steps and 5 merge steps over six worktrees.

    Phase 1 sweeps in five worktrees, phase 2 merges them, phase 3 audits,
    phase 4 consolidates, phases 5 to 19 are five rounds of prepare, improve
    and judge, and phase 20 reports. Every agent step has five gate checks.
    """
    letters = ["a", "b", "c", "d", "e"]
    phases = [
        {"name": "Sweep", "slug_override": None, "max_parallel": 3,
         "on_step_failure": "continue", "min_success": 3,
         "steps": [_claude_agent(
             f"sweep-{x}", f"sweep-{x}", model="claude-sonnet-5-5",
             brief=f"Read three conversations and write sweep/{x}.md.",
             worktree=f"sweep-{x}", write_scope=[f"sweep/{x}.md"],
             objective=f"Sonnet reads three conversations and writes sweep/{x}.md")
             for x in letters]},
        {"name": "Merge sweep", "slug_override": None, "max_parallel": None,
         "on_step_failure": "quarantine", "min_success": "all",
         "steps": [merge(f"merge-sweep-{x}", f"plan28-sweep-{x}",
                         depends_on=(f"sweep-{x}",)) for x in letters]},
        {"name": "Audit sweep reads", "slug_override": None,
         "max_parallel": None, "on_step_failure": "abort",
         "min_success": "all",
         "steps": [_shell("audit-sweep", "python -I audit_reads.py",
                          "which dialogs each reader opened")]},
        {"name": "Consolidate", "slug_override": None, "max_parallel": None,
         "on_step_failure": "abort", "min_success": "all",
         "steps": [_claude_agent(
             "consolidate", "consolidate", model="claude-opus-5-5",
             brief=PLAN28_LONG_BRIEF, worktree="loop",
             write_scope=["sweep/consolidated.md"],
             objective="Opus merges the five sweeps into one file",
             execution_timeout_s=3600)]},
    ]
    for n in range(1, 6):
        phases.append({"name": f"Round {n} prepare", "slug_override": None,
                       "max_parallel": None, "on_step_failure": "abort",
                       "min_success": "all",
                       "steps": [_shell(f"prepare-{n}", f"python -I prepare.py --round {n}",
                                        f"packet for round {n}")]})
        phases.append({"name": f"Round {n} improve", "slug_override": None,
                       "max_parallel": None, "on_step_failure": "abort",
                       "min_success": "all",
                       "steps": [_claude_agent(
                           f"improve-{n}", f"improve-{n}",
                           model="claude-opus-5-5",
                           brief=f"Round {n}: improve the judge from the packet.",
                           worktree="loop", write_scope=["judge/**"],
                           objective=f"Opus improves the judge in round {n}",
                           execution_timeout_s=3600)]})
        phases.append({"name": f"Round {n} judge", "slug_override": None,
                       "max_parallel": None, "on_step_failure": "abort",
                       "min_success": "all",
                       "steps": [_shell(f"judge-{n}", f"python -I judge.py --round {n}",
                                        f"score after round {n}", 1800)]})
    phases.append({"name": "Report", "slug_override": None, "max_parallel": None,
                   "on_step_failure": "abort", "min_success": "all",
                   "steps": [_shell("report", "python -I report.py",
                                    "the final table")]})
    root = run_dir.parent / "plan28-wt"
    worktrees = [{"name": name, "path": str(root / name),
                  "branch": f"plan28-{name}", "base": "main",
                  "node_modules_mode": "none", "node_modules_source": None,
                  "node_modules_sentinel": "node_modules/.package-lock.json",
                  "install_cmd": None, "reuse_existing": False,
                  "base_sha_mode": "head"}
                 for name in ["loop"] + [f"sweep-{x}" for x in letters]]
    workflow = {
        "name": "plan28", "repo": str(run_dir.parent / "plan28-repo"),
        "args": {}, "max_parallel": 3, "auto_resume": 0, "base_branch": "main",
        "baseline_cmd": None, "transient_backoff_s": 60,
        "worktrees": worktrees, "phases": phases,
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "workflow.json").write_text(json.dumps(workflow, indent=2),
                                           encoding="utf-8")
    return workflow


class RunLog:
    """A hand-written run log with timestamps chosen by the test."""

    def __init__(self, run_dir: Path, *, run_id: str | None = None,
                 workflow: str = "synthetic", auto_resume: int = 0):
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.run_dir / "run-log.jsonl"
        self.path.write_text("", encoding="utf-8")
        self.add(0, "run_started", payload={
            "run_id": run_id or self.run_dir.name, "workflow": workflow,
            "meta": {"auto_resume": auto_resume, "max_parallel": 2}})

    def add(self, at: float, event: str, coord: str | None = None,
            attempt: int | None = None, **payload: Any) -> "RunLog":
        body = payload.pop("payload", None) or payload
        rec: dict[str, Any] = {"ts": stamp(at), "event": event,
                               "payload": body}
        if coord is not None:
            rec["coord"] = coord
        if attempt is not None:
            rec["attempt"] = attempt
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
        return self

    # ---- the transitions the engine writes, in its payload shapes

    def phase(self, at: float, pc: str, name: str, steps: list[str],
              max_parallel: int = 2) -> "RunLog":
        return self.add(at, "phase_started", pc, payload={
            "name": name, "policy": "quarantine", "min_success": "all",
            "max_parallel": max_parallel, "steps": steps})

    def start(self, at: float, c: str, attempt: int = 1,
              kind: str = "initial", fingerprint: str = "fp") -> "RunLog":
        return self.add(at, "attempt_started", c, attempt, payload={
            "step_id": c.rsplit(".", 1)[-1], "kind": "agent",
            "fingerprint": fingerprint, "start_kind": kind})

    def finish(self, at: float, c: str, attempt: int, status: str, *,
               wall: float = 10.0, error: str | None = None,
               failure_class: str | None = None, fingerprint: str = "fp",
               **extra: Any) -> "RunLog":
        payload = {"status": status, "step_id": c.rsplit(".", 1)[-1],
                   "kind": "agent", "fingerprint": fingerprint,
                   "wall_seconds": wall, "error": error,
                   "failure_class": failure_class, "abort_victim": False,
                   "gate": {"passed": status == "passed", "checks": []}}
        payload.update(extra)
        return self.add(at, "attempt_finished", c, attempt, payload=payload)

    def settle(self, at: float, pc: str, status: str, good: int,
               total: int) -> "RunLog":
        return self.add(at, "phase_settled", pc, payload={
            "status": status, "good": good, "total": total,
            "min_success": "all", "steps": {}})

    def run_finished(self, at: float, status: str) -> "RunLog":
        return self.add(at, "run_finished", payload={"status": status})


def mark_alive(run_dir: Path) -> None:
    """Name this test process as the run's supervisor.

    The process was created before the file is written, which is exactly what
    `proc.pid_alive(pid, started_before=mtime)` requires of a real supervisor.
    """
    (Path(run_dir) / "supervisor.pid").write_text(str(os.getpid()),
                                                  encoding="utf-8")


def copy_tree(src: Path, dst: Path) -> Path:
    shutil.copytree(src, dst)
    return dst


PAGE_BOOT = r"""
const fs = require("node:fs");
const vm = require("node:vm");
class Element {
  constructor(tag) {
    this.nodeType = 1; this.tagName = tag; this.children = []; this.dataset = {};
    this.attrs = {}; this.className = ""; this.hidden = false; this.id = "";
    this.value = ""; this.text = null; this.parentElement = null;
    this.style = {setProperty() {}};
    const values = new Set();
    this.classList = {
      add: (...names) => names.forEach(name => values.add(name)),
      remove: (...names) => names.forEach(name => values.delete(name)),
      toggle: (name, on) => on ? values.add(name) : values.delete(name),
      contains: name => values.has(name)
    };
  }
  get textContent() {
    return this.text !== null ? this.text : this.children.map(child => child.textContent).join("");
  }
  set textContent(value) {
    if (this.tagName === "#text") { this.text = String(value); return; }
    this.children = []; this.text = null;
    if (String(value) !== "") this.appendChild(textNode(String(value)));
  }
  appendChild(child) {
    if (child.parentElement) child.parentElement.children =
      child.parentElement.children.filter(item => item !== child);
    this.children.push(child); child.parentElement = this; return child;
  }
  replaceChildren(...children) { this.children = []; children.forEach(child => this.appendChild(child)); }
  setAttribute(name, value) { this.attrs[name] = String(value); if (name === "id") this.id = String(value); }
  getAttribute(name) { return name in this.attrs ? this.attrs[name] : null; }
  addEventListener() {}
  contains(wanted) { return this === wanted || this.children.some(child => child.contains(wanted)); }
  querySelector() { return new Element("span"); }
  querySelectorAll() { return []; }
}
function textNode(text) { const item = new Element("#text"); item.text = text; return item; }
const ids = {"ohflow-data": new Element("script")};
const document = {
  getElementById: id => ids[id] || (ids[id] = new Element("div")),
  createElement: tag => new Element(tag),
  createElementNS: (_ns, tag) => new Element(tag),
  createTextNode: textNode,
  querySelector: () => null, querySelectorAll: () => [], addEventListener() {},
  documentElement: new Element("html"), body: new Element("body"), title: ""
};
const workflow = JSON.parse(fs.readFileSync(0, "utf8"));
const errors = [];
const context = {document, window: {setTimeout() {}, addEventListener() {}},
  requestAnimationFrame() {}, setTimeout() {}, clearTimeout() {},
  console: {error: error => errors.push(String(error && error.stack || error))},
  Intl, Date, URLSearchParams,
  fetch: url => Promise.resolve(String(url).startsWith("/api/workflow")
    ? {ok: true, json: () => Promise.resolve(workflow)}
    : {ok: false, status: 404, statusText: "Not Found"})};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), context);
const ask = JSON.parse(process.argv[2]);
function all(node, predicate, out) {
  if (predicate(node)) out.add(node);
  node.children.forEach(child => all(child, predicate, out));
  return out;
}
function view(node) {
  return {hidden: node.hidden, text: node.textContent,
    children: node.children.map(child => child.className),
    rows: [...all(node, item => item.tagName === "tr", new Set())]
      .map(row => row.children.map(cell => cell.textContent))};
}
setImmediate(() => {
  const classes = {};
  ask.classes.forEach(name => {
    const found = new Set();
    const carries = node => (" " + node.className + " ").indexOf(" " + name + " ") >= 0;
    Object.values(ids).forEach(root => all(root, carries, found));
    classes[name] = [...found].map(view);
  });
  const shown = {};
  ask.ids.forEach(id => { shown[id] = ids[id] ? view(ids[id]) : null; });
  console.log(JSON.stringify({errors, ids: shown, classes}));
});
"""


def boot_page(payload: dict, *, ids: tuple[str, ...] = (),
              classes: tuple[str, ...] = ()) -> dict | None:
    """What the shipping page shows once it has booted on `payload`.

    The real `dashboard.js` boots under node as a browser boots it, with no
    test hook, in a small DOM where every element the page asks for by id
    exists. `/api/workflow` answers with `payload`, every other route with
    404, and no animation frame is painted. For each id and each class the
    result holds the element's hidden flag, its text, its children's classes
    and its table rows, beside every render failure the page reported. None
    when node is not installed.
    """
    from ohflow import dashboard
    node = shutil.which("node")
    if node is None:
        return None
    result = subprocess.run(
        [node, "-e", PAGE_BOOT, str(dashboard.STATIC_ASSETS["/dashboard.js"][0]),
         json.dumps({"ids": list(ids), "classes": list(classes)})],
        input=json.dumps(payload), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=300)
    if result.returncode != 0:
        raise AssertionError(f"the page did not boot: {result.stderr}")
    return json.loads(result.stdout)

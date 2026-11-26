# Transcript — 02.review/01.review attempt 1 (lane pi)- Canonical run: `m7-smoke-fixes` (plan `deepening-m7-smoke-fixes`)- Original source: `C:\Users\<user>\ohflow-home\workflows\oh-dispatch-deepening\milestones\m7-smoke-fixes\runs\m7-smoke-fixes\phases\02.review\01.review\attempts\01\session\2026-10-01T22-40-32-979Z_01a0f9a0-62d3-7653-8777-13476dce6917.jsonl`- Records: 90; tool calls: 48; tool results: 48- Message and tool-output text is complete after redaction. Missing timestamps remain unknown.- Rebuild with `python collect.py` (read-only).
#### [1] line 1 · session · 2026-10-01T22:40:32.979Z

#### [2] line 2 · model-change · 2026-10-01T22:40:33.033Z

#### [3] line 3 · thinking-level-change · 2026-10-01T22:40:33.033Z

#### [4] line 4 · message · user · 2026-10-01T22:40:33.048Z
<file name="C:\Users\<user>\ohflow-home\workflows\oh-dispatch-deepening\milestones\m7-smoke-fixes\runs\m7-smoke-fixes\phases\02.review\01.review\attempts\01\brief.md">
## Your position in this run

Run:       m7-smoke-fixes     plan: deepening-m7-smoke-fixes
Phase:     2 of 2 - "Review"
Step:      1 of 1 in this phase - id `review`, role `review`, attempt 1
Coordinate: 02.review/01.review
Worktree:  C:\Users\<user>\dev\_wt\oh-dispatch-deepening\m7-smoke-fixes
           branch arch/m7-smoke-fixes, created from arch/deepening at 7426973
You own:   no path is reserved for you in this plan

Already done, before you (phases 1 to 1):
  01.implement/01.implement - role `implement` - commit c9004e3 - gate PASSED

Your gate, run by the orchestrator and not by you:
  the final message matches /VERDICT:\s*(MERGEABLE|BLOCKED)/
  git status --porcelain prints nothing

Your report is your final message. Write no file outside your worktree.

---

# Milestone m7-smoke-fixes: review

You work in the worktree `C:\Users\<user>\dev\_wt\oh-dispatch-deepening\m7-smoke-fixes`, which checks out branch `arch/m7-smoke-fixes`. It was cut from the campaign trunk `arch/deepening`. The product repository is `C:\Users\<user>\.agents\skills` (`example-operator/agent-skills`). the operator's own words and the bar are in `C:\Users\<user>\ohflow-home\workflows\oh-dispatch-deepening\charter.md`: read that file first.

# Rules for every worker in this campaign

You are an ohflow worker, not an interactive session. Nobody reads your chat. Your commits and
your final message are your whole output.

- **Scope.** Change files under `oh-dispatch/` only. Commit on the branch your worktree checks
  out. Never run `git push`, never change another branch, never touch the shared checkout at
  `C:\Users\<user>\.agents\skills` (only your worktree).
- **No side channels.** Do not create cortex tasks, forum posts, memory records, handovers,
  scheduled tasks or artifacts. Do not message anyone.
- **Authorship.** No `Co-Authored-By` line naming a model and no generated-with footer, in any
  commit message, file or comment. The git author is already configured.
- **Vocabulary.** Architecture words come from the `codebase-design` skill: module, interface,
  implementation, depth, deep, shallow, seam, adapter, leverage, locality. Do not write
  component, service, API, boundary or layer for these.
- **Tests.** Stdlib `unittest`. Read `oh-dispatch/tests/support.py` first; its fakes
  (`FakeLane`, the throwaway git repository, the plan builders) replace new machinery. One test
  file per defect or per new module, named for what it guards, with a docstring that says what
  went wrong or what the module promises. Prove a defect test fails against the old code before
  you keep it. A test that pins prose moves with the prose, or is rewritten to check behaviour.
- **Your session ends with your last message.** You run headless: when you stop calling tools,
  the process exits, and every background job you started dies with it. Never end a turn to
  wait for something. Never start the suite in the background.
- **Commit early.** Commit each coherent step as soon as its subset of tests passes. The gate
  needs at least one commit; uncommitted work at the end is lost work.
- **The full suite now takes about fifteen minutes** (782 tests, 874 s on 2026-10-01), longer
  than one shell call may run (600000 ms). Do not start it in the background. Run the subsets
  that cover every module you touched, in the foreground, each under ten minutes, writing to a log
  outside your worktree and reading the tail:
  `python oh-dispatch/tests/run_tests.py -k <text> > ../suite-$(basename "$PWD").log 2>&1; tail -20 ../suite-$(basename "$PWD").log`.
  The gate runs the full suite after you finish; when it fails, its output reaches your retry in
  the position block. If `run_tests.py --shard K/N` exists on your branch, run every shard instead.
  While you work, run the relevant subset:
  `python oh-dispatch/tests/run_tests.py -k <text>`. `-k` takes one substring, not an expression.
- **Windows traps on this box.** Edit files with your file-edit tool, not with shell heredocs or
  `sed -i`: heredocs turn `\n` and `\0` into real bytes. Pass Windows paths to Python with
  forward slashes. Every child process you add in code starts with `CREATE_NO_WINDOW`.
- **Prose is code.** When you change behaviour that `oh-dispatch/SKILL.md` or a file in
  `oh-dispatch/references/` describes, fix that sentence in the same commit. Milestone m6
  restructures the documents; until then each milestone keeps them true.
- **Finish clean.** The gate checks: at least one commit past the base, a clean tree, only
  `oh-dispatch/**` changed, clean authorship, and the full suite exits 0. Commit in coherent
  steps with messages that say what changed and why.
- **Your final message** is a short report for the reviewer and the judge: what you changed
  (module by module), what you deleted, the test counts before and after, anything in the spec
  you could not do and why, and anything you decided that the spec left open.

# Your task

You are the adversarial reviewer of this milestone. You change no file. Your terminal is your
only tool.

1. Read the charter named above and the spec below.
2. Read the whole milestone diff. The trunk `arch/deepening` holds the earlier milestones; this
   milestone is everything since it: `git log --oneline arch/deepening..HEAD`, then
   `git diff arch/deepening...HEAD --stat`, then the diff of each file.
3. Run the exit criteria of the spec yourself, one by one, and note each result. The full suite
   takes about fifteen minutes; run it as three shards in the foreground, each under ten minutes:
   `python oh-dispatch/tests/run_tests.py --shard K/3` for K = 1, 2, 3, each to a log outside the
   worktree. Never run two suites at once: some tests wait on process timing and flake under
   contention. Create nothing inside the worktree.
4. Look for what a careful engineer would find:
   - a worker launch on any lane that still passes `CLAUDE*`, `CLAUDECODE` or
     `ANTHROPIC_BASE_URL` (grep every place an environment is built for a child);
   - a hermetic claude session that can still read the user's instruction files or settings, or
     that loses its login;
   - a stall limit that a lane's normal silence can still trip (codex reasoning, a long foreground
     command);
   - a report whose `lane` names another lane and still passes the gate;
   - README figures that do not match the measured `matrix.json` or a shard run;
   - a test that passes both with and without its fix;
   - prose that now contradicts the code.
5. End your final message with your findings, most severe first, each with the file and line and
   the evidence (a command and its output). Then one line, exactly one of:

   `VERDICT: MERGEABLE`
   `VERDICT: BLOCKED`

   BLOCKED when any exit criterion fails or any finding would ship a defect.

# The milestone spec (frozen)

# m7: smoke fixes from the first live full matrix

## Why

After m6 the campaign supervisor ran `ohflow rollcall --matrix full` from the trunk code
(`e0d0c49`), launched from a Claude desktop-app session. 12 of 15 cells passed in about 33 min,
including `campaign pi` (a judge REVISEd, then PASSed live) and `retry claude carry_context`.
Evidence: `C:\Users\<user>\AppData\Local\Temp\claude\C--Users-user\bb0fac07-fb14-4ec9-82d9-33b3b7c2e4f4\scratchpad\matrix-full\matrix.json`,
the cell run directories beside it, and `..\matrix-full.log`. Three cells failed, each for a real
product reason:

1. **`single host` failed `rollcall_matches`.** The host worker (OpenHands, `glm-5.3-flash`)
   reported itself as "Claude Code 2.1.284 (launched via Claude Desktop 2.16120.0 / Agent SDK
   0.3.284)" and listed Claude Code's tools; its harness announced `terminal`, `file_editor`,
   `task_tracker`, `think`, `finish`. Cause: only `seat_runner._PARENT_SESSION_VARS` removes the
   launching session's variables (`CLAUDE*`, `CLAUDECODE`, `ANTHROPIC_BASE_URL`), and only the
   claude, codex and dsh lanes use it. The pi and host lanes pass all of them to their workers.
   The desktop session exports 26 `CLAUDE*` names. The same cell passed in m5's exit check, which
   ran under a WMI-started driver that has none of them. An agent in Claude Code running the roll
   call, the use the README prescribes, hits this every time.
2. **`single claude profile=hermetic` failed `rollcall_matches`.** The worker named ten MCP
   servers (`cortex`, `archive`, `forum`, `deepthink`, `flaui`, `google-search`, `brave-search`,
   `mcp-inspector`, `web-surfer-llm`, `linkedin`), exactly the list in the user's
   `~/.claude/CLAUDE.md`, while its harness announced no MCP server. The hermetic profile still
   loads the user's instruction files. `single codex profile=hermetic` passed.
3. **`relay` failed: its codex step was killed for a stall** at the roll call's default
   `stall_timeout_s=180`. `codex exec --json` emits no event while the model reasons; the last
   event was an early `agent_message` at 23:08:04, the kill came at about 23:11. That message,
   recovered as the final message, was a JSON report with `"lane": "commentary"`, and
   `schema_valid` and `rollcall_matches` both passed it. `single codex` passed in 58 s.

## Scope

1. **One rule removes the launching session's variables from every worker, on every lane.** The
   rule and the variable pattern live in one place, and pi, host, claude, codex and dsh launches
   all use it. Prefer the lowest module every launch already goes through.
2. **`profile="hermetic"` on the claude lane loads none of the user's instruction files or
   settings**, as the codex hermetic profile already loads none of `~/.codex`. Find the Claude
   CLI's own mechanism (`claude --help`, its documented settings sources and config directory),
   keep the login working, and say in `references/lanes.md`, for each lane, what hermetic removes
   and what it keeps.
3. **A stall limit that fits each lane.** The roll call takes each cell's stall limit from the lane
   (the registry or the roll-call route table), not from one plan-wide 180 s; codex gets at least
   600 s. A `stall_timeout_s` argument still overrides it.
4. **A report names its own lane.** The roll-call gate fails a report whose `lane` is not the step's
   lane, so a stray or partial message cannot pass.
5. **The README's measured figures.** Fill the "Wall time" column of the `quick` and `full` rows
   from the measured `matrix.json` above, and update the suite figure from a shard run on this
   branch. One place each.

The implementer may run live cells only through `ohflow rollcall --cells` on the three failing
cells (`single:host`, `single:claude:1:profile=hermetic`, `relay:pi,claude,codex,dsh`), at most
three times each.

## Exit criteria

| # | Command (from the land worktree root) | Pass |
|---|---|---|
| 1 | `python oh-dispatch/tests/run_tests.py -k parent_session` | exit 0; ran ≥ 5 tests, one per lane, each proving the worker's environment has no `CLAUDE*`, `CLAUDECODE` or `ANTHROPIC_BASE_URL` when the parent has them |
| 2 | `python oh-dispatch/tests/run_tests.py -k hermetic` | exit 0; ran ≥ 2 tests |
| 3 | `python oh-dispatch/tests/run_tests.py -k report_lane` | exit 0; ran ≥ 1 test: a report naming another lane fails the gate |
| 4 | with `CLAUDECODE=1`, `CLAUDE_CODE_ENTRYPOINT=claude-desktop` and `CLAUDE_AGENT_SDK_VERSION=0.3.284` exported, `ohflow rollcall --cells single:host single:claude:1:profile=hermetic relay:pi,claude,codex,dsh` from `oh-dispatch/scripts` | last line `ROLLCALL PASS: 3 of 3 cells` |
| 5 | `grep -n "not measured yet" oh-dispatch/README.md` | no match |
</file>

#### [5] line 5 · message · assistant · 2026-10-01T22:40:38.485Z
<details><summary>thinking</summary>

Let me start by understanding my task. I'm the adversarial reviewer for milestone m7-smoke-fixes. I need to:

1. Read the charter at `C:\Users\<user>\ohflow-home\workflows\oh-dispatch-deepening\charter.md`
2. Read the whole milestone diff
3. Run the exit criteria of the spec
4. Look for defects a careful engineer would find
5. End with a verdict

Let me start by reading the charter and looking at the diff.

</details>
**toolCall bash** id=`call_bdbd5183f5b64eb4b8a6bb6c`

```json
{
 "command": "cat \"C:/Users/<user>/ohflow-home/workflows/oh-dispatch-deepening/charter.md\""
}
```
**toolCall bash** id=`call_d2abf3e2e0c347118bb0b5b3`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && git log --oneline arch/deepening..HEAD && git status --porcelain && echo \"---STAT---\" && git diff arch/deepening...HEAD --stat"
}
```

#### [6] line 6 · message · toolResult · 2026-10-01T22:40:38.689Z
# Charter: oh-dispatch deepening campaign

Product repository: `C:\Users\<user>\.agents\skills` (`example-operator/agent-skills`, private).
Skill under change: `oh-dispatch/`. Trunk: branch `arch/deepening`, cut from `main` at
`c03daab`. Baseline: `python oh-dispatch/tests/run_tests.py` passed 627 tests in 456 s,
0 failures, 2 opt-in skips, on 2026-09-30.

## The operator's words

Verbatim, 2026-09-30, as the arguments of `/improve-codebase-architecture`:

> and codebase-design pass on our /oh-dispatch ecosystem? Handovers have a good picture of the recent evolution. Also the skill has grown large enough that it deserves its own Readme and we should describe how to test each of the workflow archetypes, routes, scales when developing for it, using fully e2e hooked agents with a trivial roll call workflow.  Creating and executing this once will also automatically have tested any structural changes you have made. and it is fine to make them. because this is an agentic workflow, prose is also code. they too should be subject to the same review. Today we have automated large chunks of text to audio skill with a helper script. We should abstract away as much of the actions we chain in prose as possible to lighten the agent's cognitive load working with this. We should ensure the agent always gets high value, no fluff or bloat responses from every action taken along the way. Deepthink is something I find very useful in these types of tasks. we can also predefine A/B testing of two workflows or a harness component etc. into the skill. This last one is out of scope but something to keep in mind.
>
> Ultimately, when done, pushing and consolidation with main is the "done" point.

Standing rulings that apply (from memory `openhands-worker-pool-doctrine`, `ohflow-campaign-loop`):

> Every seat dispatches through ohflow. [...] work on ohflow itself goes through ohflow like any
> other work, and ohflow carries its own improvements (the software-factory use).

> We automated our own process, so what comes out of it carries our name. A campaign that ends
> green and sloppy is our failure, not the workers'.

## The bar

"Ready to ship" for this campaign means all of these, each proven by a command:

1. **Structural changes are real deepenings.** Each milestone's module has a smaller interface
   than the code it replaces, its callers stop knowing what it hides, and the deletion test
   holds: deleting the new module would spread its complexity back across its callers. The
   vocabulary is the `codebase-design` skill's: module, interface, implementation, depth, seam,
   adapter, leverage, locality.
2. **Nothing regresses.** `python oh-dispatch/tests/run_tests.py` exits 0 on the land branch.
   Tests that guarded behaviour still guard it; a test is moved or rewritten, never deleted to
   make the suite pass, unless the code it guards is deleted with it.
3. **Every new or changed module has tests through its interface.** A defect fix carries a test
   that fails against the old code.
4. **Every agent-facing action returns high-value output.** A verb prints its verdict first, in
   one line; detail follows only when it is needed to act. No raw dicts, no dumps, no noise, no
   contradicting lines. (the operator: "the agent always gets high value, no fluff or bloat responses
   from every action".)
5. **Chained prose actions become helper verbs.** A mechanical sequence that the skill text asks
   an agent to carry out by hand becomes one `ohflow` verb that prints a verdict, in the style
   of `text-to-audio`'s `t2a` (one command, a verb table, PASS/FAIL lines).
6. **Prose is code.** Skill text is reviewed like code: one source per fact, no statement the
   code contradicts, no history in the reading path, one meaning per term.
7. **The skill has its own README** that tells a developer how to test each workflow
   archetype, each route (lane) and each scale with fully end-to-end hooked agents, using the
   trivial roll-call workflow.
8. **Clean authorship.** No `Co-Authored-By` naming a model, no generated-with footer, in any
   commit, doc or comment.

## Decisions already made

Fixed. A judge does not reopen these.

- **The milestone split and order** (architecture review of 2026-09-30, report
  `%TEMP%\architecture-review-20260930-2338.html`): m1 run reader, m2 lane artifacts, m3 run
  entry point, m4 agent verbs, m5 roll-call matrix, m6 documents. Deferred, out of scope: one
  verdict-and-rerun policy module, a step-executor split of `engine._attempt_step`, a model
  catalog.
- **Token vocabulary.** `prompt_tokens` counts every input token the model read, including
  cache reads and cache writes. `cache_read_tokens` and `cache_write_tokens` are parts of it,
  never added to it again. Total = `prompt_tokens + completion_tokens`. The runners already
  follow this; the readers must.
- **The container lane is deleted**, code and prose. The todo stays in memory
  `oh-dispatch-container-lane-todo`; a later rebuild starts from `container-lane.md` in history.
- **`scripts/implement_review.py` keeps its command line** (the operator may still use it) but becomes a
  thin shim over the one run entry point. `legacy.py` stays while the shim writes the legacy
  summary.
- **A/B testing is out of scope.** Keep a seam for it: the roll-call matrix runs a named
  configuration, so two configurations over one matrix can be compared later.
- Earlier settled decisions stay settled (handovers 16.09–30.09): stdlib `unittest`, one file
  per defect, tests proven red first, tests write only to temp dirs; `result.error` outranks a
  passing gate; no metric is fabricated; pricing fails closed; the dashboard reads files only;
  run notes are four files at the run root; the judge edits inputs only; every rerun resumes
  one run directory.
- **Who does what.** Implementers run on the claude lane (`claude-sonnet-5-5`, effort high,
  usual setup). Reviewers run on the pi lane (`zai/glm-5.3`), terminal only, as an independent
  model family. Judges are the campaign default (`claude-opus-5-5`, effort high).

## Stop and ask

ESCALATE on these; they belong to the operator.

- Removing or changing a documented command-line flag or verb that the operator uses (`ohflow run`,
  `status`, `table`, `report`, `dashboard`, `campaign`, `implement_review.py`), beyond adding
  flags or changing output text.
- Anything that spends outside the flat rate or the subscriptions: a paid API key, a new
  provider.
- A change outside `oh-dispatch/` in the product repository.
- A spec that is wrong or impossible as written.
**toolResult** for `call_bdbd5183f5b64eb4b8a6bb6c` (bash)

#### [7] line 7 · message · toolResult · 2026-10-01T22:40:38.741Z
c9004e3 oh-dispatch README: quick and full wall times from the first full matrix, suite figure from a three-shard run on this branch
bd76078 oh-dispatch tests: the detached-run tests wait up to 60 s on every real-process step through one helper, because 10 s failed under suite load
52dbe58 oh-dispatch roll call: the stall limit is per lane (codex 600 s) and the gate fails a report that names another lane than its step
139fac7 oh-dispatch claude lane: profile=hermetic sets CLAUDE_CODE_DISABLE_CLAUDE_MDS so no instruction file loads; lanes.md says per lane what hermetic removes and keeps
18f4bcd oh-dispatch: one worker_env rule strips the launching session's variables from every lane, so pi and host no longer inherit CLAUDE*, CLAUDECODE or ANTHROPIC_BASE_URL
---STAT---
 oh-dispatch/README.md                              |  10 +-
 oh-dispatch/references/lanes.md                    |  16 ++-
 oh-dispatch/scripts/ohflow/claude_runner.py        |  13 ++-
 oh-dispatch/scripts/ohflow/cli_lane.py             |   4 +-
 oh-dispatch/scripts/ohflow/gates.py                |  12 +-
 oh-dispatch/scripts/ohflow/pi_runner.py            |   2 +-
 oh-dispatch/scripts/ohflow/plans/rollcall.py       |  37 ++++--
 oh-dispatch/scripts/ohflow/proc.py                 |  17 +++
 oh-dispatch/scripts/ohflow/seat_runner.py          |   9 +-
 oh-dispatch/scripts/ohflow/worker.py               |   4 +-
 .../tests/test_defect_07_detached_run_survives.py  |  29 ++++-
 ...efect_44_parent_session_vars_reach_no_worker.py | 126 +++++++++++++++++++++
 ...5_hermetic_claude_loads_no_instruction_files.py |  57 ++++++++++
 ..._46_rollcall_report_lane_must_match_the_step.py |  59 ++++++++++
 ...t_defect_47_rollcall_stall_limit_is_per_lane.py |  39 +++++++
 15 files changed, 393 insertions(+), 41 deletions(-)
**toolResult** for `call_d2abf3e2e0c347118bb0b5b3` (bash)

#### [8] line 8 · message · assistant · 2026-10-01T22:40:42.642Z
<details><summary>thinking</summary>

Now let me read the full diff of each file. Let me start with the core code changes.

</details>
**toolCall bash** id=`call_0a815906a497429faf39b45e`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && git diff arch/deepening...HEAD -- oh-dispatch/scripts/ohflow/proc.py oh-dispatch/scripts/ohflow/worker.py oh-dispatch/scripts/ohflow/seat_runner.py oh-dispatch/scripts/ohflow/pi_runner.py"
}
```

#### [9] line 9 · message · toolResult · 2026-10-01T22:40:42.696Z
diff --git a/oh-dispatch/scripts/ohflow/pi_runner.py b/oh-dispatch/scripts/ohflow/pi_runner.py
index 803531e..4f2e7dc 100644
--- a/oh-dispatch/scripts/ohflow/pi_runner.py
+++ b/oh-dispatch/scripts/ohflow/pi_runner.py
@@ -160,7 +160,7 @@ class PiAdapter:
         (out_dir / "session").mkdir(parents=True, exist_ok=True)
         surface = prepare_pi_surface(spec, out_dir)
         agent_dir = write_pi_agent_dir(spec, out_dir)
-        env = dict(os.environ)
+        env = proc.worker_env()
         env["PI_CODING_AGENT_DIR"] = str(agent_dir)
         env["PI_OFFLINE"] = "1"
         env["OHFLOW_BASH"] = os.environ.get(
diff --git a/oh-dispatch/scripts/ohflow/proc.py b/oh-dispatch/scripts/ohflow/proc.py
index 65d80ae..a7ffe95 100644
--- a/oh-dispatch/scripts/ohflow/proc.py
+++ b/oh-dispatch/scripts/ohflow/proc.py
@@ -3,6 +3,7 @@
 from __future__ import annotations
 
 import os
+import re
 import subprocess
 import sys
 import tempfile
@@ -13,6 +14,22 @@ from typing import Any, Mapping, Sequence
 _CURRENT_JOB: Any = None
 _CREATE_SUSPENDED = 0x00000004
 
+# Variables a parent Claude Code session exports. A worker inherits none of
+# them: it is a fresh seat, not a child of whatever launched ohflow. Measured
+# 2026-09-30 from a desktop-app session: 25 CLAUDE* names plus an
+# ANTHROPIC_BASE_URL that points at the desktop app's own proxy.
+_PARENT_SESSION_VARS = re.compile(r"^(CLAUDE|CLAUDECODE$|ANTHROPIC_BASE_URL$)")
+
+
+def worker_env(base: Mapping[str, str] | None = None) -> dict[str, str]:
+    """The environment a worker starts with: `base` (default: this process's)
+    without the variables of the session that launched ohflow. Every lane
+    builds a worker's environment from this, so no worker takes its identity
+    from the launcher. A variable a lane sets on purpose is added afterwards.
+    """
+    source = os.environ if base is None else base
+    return {k: v for k, v in source.items() if not _PARENT_SESSION_VARS.match(k)}
+
 
 def _kernel32():
     import ctypes
diff --git a/oh-dispatch/scripts/ohflow/seat_runner.py b/oh-dispatch/scripts/ohflow/seat_runner.py
index 5c39f11..21edbcf 100644
--- a/oh-dispatch/scripts/ohflow/seat_runner.py
+++ b/oh-dispatch/scripts/ohflow/seat_runner.py
@@ -36,15 +36,8 @@ from .proc import guard_current_process_tree
 
 NPM_DIR = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "npm"
 
-# Variables a parent Claude Code session exports. A worker inherits none of
-# them: it is a fresh seat, not a child of whatever launched ohflow. Measured
-# 2026-09-30 from a desktop-app session: 25 CLAUDE* names plus an
-# ANTHROPIC_BASE_URL that points at the desktop app's own proxy.
-_PARENT_SESSION_VARS = re.compile(r"^(CLAUDE|CLAUDECODE$|ANTHROPIC_BASE_URL$)")
-
-
 def seat_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
-    env = {k: v for k, v in os.environ.items() if not _PARENT_SESSION_VARS.match(k)}
+    env = proc.worker_env()
     env["PYTHONIOENCODING"] = "utf-8"
     env.update(extra or {})
     return env
diff --git a/oh-dispatch/scripts/ohflow/worker.py b/oh-dispatch/scripts/ohflow/worker.py
index ee36f02..4097de5 100644
--- a/oh-dispatch/scripts/ohflow/worker.py
+++ b/oh-dispatch/scripts/ohflow/worker.py
@@ -23,7 +23,7 @@ from typing import Any, Protocol
 from . import IMPORT_ROOT, host_artifacts
 from .paths import posix, win
 from .plan import WorkerSpec, to_jsonable
-from .proc import spawn_managed
+from .proc import spawn_managed, worker_env
 
 __all__ = ["Handle", "Lane", "HostLane", "spec_json", "WorkerLaunchError"]
 
@@ -151,7 +151,7 @@ class HostLane:
                 f"host lane interpreter missing: {win(self.python)}. "
                 "Set OHFLOW_HOST_PYTHON or install ~/sdk/.venv."
             )
-        env = dict(os.environ)
+        env = worker_env()
         parent = str(IMPORT_ROOT)
         env["PYTHONPATH"] = parent + os.pathsep + env.get("PYTHONPATH", "")
         env.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")
**toolResult** for `call_0a815906a497429faf39b45e` (bash)

#### [10] line 10 · message · assistant · 2026-10-01T22:40:47.030Z
<details><summary>thinking</summary>

Now the claude_runner.py, cli_lane.py, gates.py, plans/rollcall.py:

</details>
**toolCall bash** id=`call_789e49ab82e741458be42b6c`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && git diff arch/deepening...HEAD -- oh-dispatch/scripts/ohflow/claude_runner.py oh-dispatch/scripts/ohflow/cli_lane.py oh-dispatch/scripts/ohflow/gates.py oh-dispatch/scripts/ohflow/plans/rollcall.py"
}
```

#### [11] line 11 · message · toolResult · 2026-10-01T22:40:47.135Z
diff --git a/oh-dispatch/scripts/ohflow/claude_runner.py b/oh-dispatch/scripts/ohflow/claude_runner.py
index 5d46794..99f5144 100644
--- a/oh-dispatch/scripts/ohflow/claude_runner.py
+++ b/oh-dispatch/scripts/ohflow/claude_runner.py
@@ -1,7 +1,8 @@
 """Run one Claude Code worker and translate its stream-json events to ohflow records.
 
 Launch: `claude.exe -p --output-format stream-json --verbose`, in the seat's
-usual setup unless the step names `profile="hermetic"`. The first `system`
+usual setup unless the step names `profile="hermetic"`. A hermetic worker loads
+no instruction file and no user settings, and keeps its login. The first `system`
 `init` event announces the tools, the MCP servers and the model. The last
 `result` event carries the final text, the usage and the cost.
 """
@@ -33,6 +34,12 @@ HERMETIC_TOOLS = {
 }
 HERMETIC_DEFAULT = ("terminal", "file_editor")
 
+# `--setting-sources project,local` drops the user's settings but not the
+# user's instruction files (CLAUDE.md). This variable drops them and keeps the
+# `--mcp-config` servers and the login. `--safe-mode` drops the servers too;
+# `--bare` needs an API key. Measured 2026-10-01 (2.1.281).
+HERMETIC_ENV = {"CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1"}
+
 # The init event names some tools by their internal name; the model sees
 # another. Measured 2026-09-30 (2.1.281): init says `Task`, the model calls
 # it `Agent`.
@@ -322,9 +329,11 @@ class ClaudeAdapter:
 
     def prepare(self, spec: dict[str, Any], out_dir: Path) -> CliPreparedProcess:
         session_id = str(uuid.uuid4())
+        hermetic = spec.get("profile") == "hermetic"
         return CliPreparedProcess(
             argv=tuple(build_command(spec, out_dir, session_id)),
-            cwd=Path(str(spec["workspace"])), env=seat_env(),
+            cwd=Path(str(spec["workspace"])),
+            env=seat_env(HERMETIC_ENV if hermetic else None),
             context={"session_id": session_id})
 
     def parse_event(self, line: str) -> Mapping[str, Any]:
diff --git a/oh-dispatch/scripts/ohflow/cli_lane.py b/oh-dispatch/scripts/ohflow/cli_lane.py
index 1f8b3eb..0b4461c 100644
--- a/oh-dispatch/scripts/ohflow/cli_lane.py
+++ b/oh-dispatch/scripts/ohflow/cli_lane.py
@@ -13,7 +13,7 @@ from pathlib import Path
 from typing import Any, Callable, Mapping, Protocol, Sequence
 
 from . import IMPORT_ROOT, attempt_record
-from .proc import spawn_managed
+from .proc import spawn_managed, worker_env
 from .worker import ERROR, FINISHED, RUNNING, Handle, WorkerLaunchError
 
 
@@ -248,7 +248,7 @@ class CliLane:
         spec_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
         if not self.python.exists():
             raise WorkerLaunchError(f"{self.name} lane interpreter missing: {self.python}")
-        env = dict(os.environ)
+        env = worker_env()
         parent = str(IMPORT_ROOT)
         env["PYTHONPATH"] = parent + os.pathsep + env.get("PYTHONPATH", "")
         env["PYTHONIOENCODING"] = "utf-8"
diff --git a/oh-dispatch/scripts/ohflow/gates.py b/oh-dispatch/scripts/ohflow/gates.py
index 5d5c7e3..5ef87f9 100644
--- a/oh-dispatch/scripts/ohflow/gates.py
+++ b/oh-dispatch/scripts/ohflow/gates.py
@@ -541,8 +541,10 @@ def _surface_name(name: Any) -> str:
 @register("rollcall_matches",
           lambda a: "every tool and MCP server the worker reports was announced "
                     "by its harness" + (" and is inside the plan surface"
-                                        if a.get("surface") else ""))
-def rollcall_matches(ctx: GateContext, surface: list[str] | None = None) -> GateResult:
+                                        if a.get("surface") else "") +
+                    (f"; the report names lane {a['lane']}" if a.get("lane") else ""))
+def rollcall_matches(ctx: GateContext, surface: list[str] | None = None,
+                     lane: str | None = None) -> GateResult:
     """The worker's report of its own surface against the harness's record.
 
     The lane writes what the harness announced into `result.json`: `tools`
@@ -550,7 +552,8 @@ def rollcall_matches(ctx: GateContext, surface: list[str] | None = None) -> Gate
     structured final message. A reported name the harness never announced
     fails the check, and so does one outside `surface` when the plan gives
     one (a hermetic worker). A lane that announces no tool list (codex) has
-    its tools unchecked, and the observed record says so.
+    its tools unchecked, and the observed record says so. When the plan gives
+    `lane`, the report's own `lane` field must equal it.
     """
     result_path = ctx.step_dir / "result.json"
     evidence = str(result_path) if result_path.exists() else None
@@ -572,6 +575,9 @@ def rollcall_matches(ctx: GateContext, surface: list[str] | None = None) -> Gate
     reported_servers = [re.sub(r"^mcp__", "", s) for s in report.get("mcp_servers") or []
                         if isinstance(s, str)]
     problems: list[str] = []
+    if lane is not None and report.get("lane") != lane:
+        problems.append(f"report names lane {report.get('lane')!r}, "
+                        f"the step runs on lane {lane!r}")
     if announced_tools:
         extra = [t for t in reported_tools if _surface_name(t) not in announced_tools]
         if extra:
diff --git a/oh-dispatch/scripts/ohflow/plans/rollcall.py b/oh-dispatch/scripts/ohflow/plans/rollcall.py
index af5ae94..95d8c7f 100644
--- a/oh-dispatch/scripts/ohflow/plans/rollcall.py
+++ b/oh-dispatch/scripts/ohflow/plans/rollcall.py
@@ -26,7 +26,8 @@ Arguments: `repo` (required), `shape`, `lanes` (comma list), `count` (workers
 per lane), `consolidator`, `reviewer`, `judge` (each a lane), `profile`
 (`hermetic` for claude and codex), `carry_context`, `config` (a JSON file of
 model overrides), `base`, `prefix`, `wt_root`, `wall_timeout_s`,
-`stall_timeout_s`, `max_iterations`, `max_parallel`.
+`stall_timeout_s` (replaces the per-lane `STALL_S` table; codex gets 600 s,
+every other lane 180 s), `max_iterations`, `max_parallel`.
 
     python -m ohflow.cli validate --plan <this file> \\
         --args repo=<scratch repo> --args shape=merge --args lanes=pi,claude
@@ -68,6 +69,11 @@ MODELS = {
 }
 ORDER = ("pi", "claude", "codex", "dsh")
 
+#: Seconds of silence that stop a worker, per lane. Codex reasons for minutes
+#: without an event, and 180 s killed it in the first live matrix. The plan
+#: argument `stall_timeout_s` replaces the table for every lane.
+STALL_S = {"pi": 180, "host": 180, "claude": 180, "codex": 600, "dsh": 180}
+
 SHAPES = ("single", "fanout", "relay", "merge", "retry", "review", "campaign")
 ALIASES = {"r0": "fanout", "r1": "relay", "r2": "merge"}
 
@@ -296,11 +302,17 @@ class Spec:
     prefix: str
     wt_root: Path
     wall: int
-    stall: int
+    stall: int | None          # the caller's override; None takes STALL_S
     max_iter: int
     max_parallel: int
     models: dict
 
+    def stall_for(self, lane: str) -> int | None:
+        """The stall limit of a step on `lane`; None when the lane takes none."""
+        if not lane_info(lane).has(CAP_STALL):
+            return None
+        return self.stall if self.stall is not None else STALL_S[lane]
+
     @property
     def workers(self) -> list[tuple[str, str]]:
         """`(lane, step id)` for every worker, lane by lane."""
@@ -374,7 +386,8 @@ def normalize(args) -> Spec:
         base=base, prefix=str(args.get("prefix", "rollcall")),
         wt_root=Path(args.get("wt_root", str(repo.parent / f"{repo.name}-rollcall-wt"))),
         wall=int(args.get("wall_timeout_s", 600)),
-        stall=int(args.get("stall_timeout_s", 180)),
+        stall=(int(args["stall_timeout_s"])
+               if args.get("stall_timeout_s") not in (None, "") else None),
         max_iter=int(args.get("max_iterations", 15)),
         max_parallel=int(args.get("max_parallel", 3)), models=models)
 
@@ -406,19 +419,20 @@ def _step(spec: Spec, sid: str, lane: str, brief: str, *, worktree: str,
           owns: tuple[str, ...], checks: tuple[CheckSpec, ...], objective: str,
           depends_on: tuple[str, ...] = (), retry: RetryPolicy | None = None,
           schema: dict | None = ROLLCALL_SCHEMA, role: str | None = None) -> Step:
-    stall = spec.stall if lane_info(lane).has(CAP_STALL) else None
     return Step(id=sid, kind="worker", worktree=worktree, owns=owns,
                 depends_on=depends_on, wall_timeout_s=spec.wall,
-                stall_timeout_s=stall, schema=schema, objective=objective,
+                stall_timeout_s=spec.stall_for(lane), schema=schema,
+                objective=objective,
                 retry=retry or RetryPolicy(),
                 worker=_worker(spec, lane, role or f"rollcall-{lane}", brief),
                 gate=GateSpec(checks=checks))
 
 
-def _report_checks(owns: str, *, since: str = "base",
+def _report_checks(owns: str, lane: str, *, since: str = "base",
                    extra: tuple[CheckSpec, ...] = ()) -> tuple[CheckSpec, ...]:
     return (clean_commit_checks((owns,), since=since, marker=PRESENT) +
-            (CheckSpec("schema_valid"), CheckSpec("rollcall_matches")) + extra)
+            (CheckSpec("schema_valid"),
+             CheckSpec("rollcall_matches", {"lane": lane})) + extra)
 
 
 def _wt(spec: Spec, name: str) -> WorktreeSpec:
@@ -434,7 +448,7 @@ def _solo(spec: Spec, lane: str, sid: str, *, more: str = "",
     brief = brief if brief is not None else SOLO_BRIEF.format(
         lane=lane, sid=sid, entry=ENTRY, clean=CLEAN, more=more)
     return _step(spec, sid, lane, brief, worktree=sid, owns=(owns,),
-                 checks=_report_checks(owns, since=since, extra=extra),
+                 checks=_report_checks(owns, lane, since=since, extra=extra),
                  objective=f"{sid} reports for duty in {owns}", retry=retry)
 
 
@@ -479,7 +493,8 @@ def _relay(spec: Spec):
         step = _step(
             spec, sid, lane, brief, worktree="relay", owns=("ROLLCALL.md",),
             depends_on=(previous_id,) if previous_id else (),
-            checks=_report_checks("ROLLCALL.md", since="step_start", extra=extra),
+            checks=_report_checks("ROLLCALL.md", lane, since="step_start",
+                                  extra=extra),
             objective=f"{sid} appends its section to the shared ROLLCALL.md")
         phases.append(Phase(name=f"Relay {n} {sid}", steps=(step,)))
         previous_id = sid
@@ -505,8 +520,8 @@ def _merge(spec: Spec):
         spec, "consolidate", spec.consolidator, brief, worktree="integration",
         owns=("ROLLCALL.md",),
         depends_on=tuple(f"merge-{sid}" for sid in ids),
-        checks=_report_checks("ROLLCALL.md", since="last_merge",
-                              extra=rows + (count,)),
+        checks=_report_checks("ROLLCALL.md", spec.consolidator,
+                              since="last_merge", extra=rows + (count,)),
         objective=(f"{spec.consolidator} writes ROLLCALL.md as one table, "
                    f"one row per worker"),
         role="rollcall-consolidate"),))
**toolResult** for `call_789e49ab82e741458be42b6c` (bash)

#### [12] line 12 · message · assistant · 2026-10-01T22:40:50.990Z
<details><summary>thinking</summary>

Now let me look at the test files and the docs changes (README.md, references/lanes.md):

</details>
**toolCall bash** id=`call_380167ef4ad244b2a85b71d1`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && git diff arch/deepening...HEAD -- oh-dispatch/README.md oh-dispatch/references/lanes.md"
}
```

#### [13] line 13 · message · toolResult · 2026-10-01T22:40:51.043Z
diff --git a/oh-dispatch/README.md b/oh-dispatch/README.md
index 4d9f8ff..34526e6 100644
--- a/oh-dispatch/README.md
+++ b/oh-dispatch/README.md
@@ -26,9 +26,9 @@ The engine, the journal and the plan model sit beside these. The journal is the
 
 ## Running the suite
 
-The suite uses `unittest` from the standard library. It runs from a fresh clone and needs no network. A full run takes about fifteen minutes (875 tests, 877 s on 2026-10-01). Run it in three shards. Each shard stays under ten minutes.
+The suite uses `unittest` from the standard library. It runs from a fresh clone and needs no network. A full run takes about fifteen minutes (896 tests, 885 s on 2026-10-02). Run it in three shards. Each shard stays under ten minutes.
 
-Deterministic. Each shard takes about five minutes (312.9 s, 300.8 s and 263.2 s on 2026-10-01):
+Deterministic. Each shard takes about five minutes (340.2 s, 282.9 s and 261.4 s on 2026-10-02):
 
 ```bash
 python oh-dispatch/tests/run_tests.py --shard 1/3
@@ -86,7 +86,7 @@ Lane facts and launch rules: [lanes](references/lanes.md).
 
 - **`count`** is the number of workers per lane. `fanout:pi:3` starts three workers on `pi`.
 - **Parallelism** is the plan argument `max_parallel`. A matrix run keeps its default of 3.
-- **Wall and stall limits** are the plan arguments `wall_timeout_s` (default 600) and `stall_timeout_s` (default 180).
+- **Wall and stall limits** are the plan arguments `wall_timeout_s` (default 600) and `stall_timeout_s`. The stall limit defaults per lane: 600 s for codex, 180 s for every other lane. The argument replaces that table for every lane.
 
 Pass plan arguments to `validate` and `run` with `--plan ohflow.plans.rollcall --args repo=<repo> --args shape=<shape>`.
 
@@ -97,8 +97,8 @@ Pass plan arguments to `validate` and `run` with `--plan ohflow.plans.rollcall -
 | Matrix | Cells | Contents | Wall time |
 |---|---|---|---|
 | `smoke` | 2 | `single` on `pi` and on `host` | `single pi` 31 s, `single host` 1 m 51 s (5.4 k and 87.0 k tokens, m5 acceptance run) |
-| `quick` | 10 | `single` on all five lanes; `fanout`, `relay` and `merge` on `pi`, `claude`, `codex`, `dsh`; `retry` on `pi`; `review` on `pi` then `claude` | not measured yet |
-| `full` | 15 | `quick`, plus `fanout` on `pi` with `count=3`, `campaign` on `pi`, `single` hermetic on `claude` and on `codex`, `retry` on `claude` with `carry_context` | not measured yet |
+| `quick` | 10 | `single` on all five lanes; `fanout`, `relay` and `merge` on `pi`, `claude`, `codex`, `dsh`; `retry` on `pi`; `review` on `pi` then `claude` | 24 m 27 s (1466.5 s, first full matrix run on 2026-10-01; 2 of 10 cells failed before the m7 fixes) |
+| `full` | 15 | `quick`, plus `fanout` on `pi` with `count=3`, `campaign` on `pi`, `single` hermetic on `claude` and on `codex`, `retry` on `claude` with `carry_context` | 32 m 23 s (1942.7 s, same run; 3 of 15 cells failed before the m7 fixes) |
 
 Cost: `smoke` runs on the Z.AI flat rate. `quick` and `full` also use the seat quotas of `claude` and `codex`. `run_tests.py --e2e` runs `smoke`.
 
diff --git a/oh-dispatch/references/lanes.md b/oh-dispatch/references/lanes.md
index 2720e98..161187e 100644
--- a/oh-dispatch/references/lanes.md
+++ b/oh-dispatch/references/lanes.md
@@ -56,6 +56,20 @@ The seat lanes sign in with the seat's login, so `api_key_env` is empty. In the
 | Schema | the final message | the final message | native `--json-schema` | native `--output-schema` | the final message |
 | Announced surface | offered tools | none | the `system` `init` event | none; servers from `config.toml` plus `codex_apps` | the session log's `request/header` |
 
+## What `profile="hermetic"` removes and keeps
+
+A hermetic worker starts from nothing the seat owns, except its login. Every lane also drops the launching session's variables (`CLAUDE*`, `CLAUDECODE`, `ANTHROPIC_BASE_URL`), hermetic or not.
+
+| Lane | Removes | Keeps |
+|---|---|---|
+| `pi` | has no profile; it is always hermetic: no ambient extensions, skills, prompts, context files or themes | only what the plan names |
+| `host` | has no profile; the host runner loads only what the plan names | the plan's tools and MCP servers |
+| `claude` | the user's instruction files (`CLAUDE_CODE_DISABLE_CLAUDE_MDS=1`), the user's settings (`--setting-sources project,local`), every built-in tool the plan does not name (`--tools`), every MCP server the plan does not name (`--strict-mcp-config`) | the OAuth login, the plan's `--mcp-config` servers, the project's own `.claude` files |
+| `codex` | the real `~/.codex` configuration, its hooks and its MCP servers (the worker gets its own `CODEX_HOME`) | the login (`auth.json` is a hard link to the real file), the plan's MCP servers |
+| `dsh` | takes a dsh seat profile name instead; `hermetic` is not a dsh profile | the named profile |
+
+`claude` offers two other switches, and neither serves: `--safe-mode` drops the `--mcp-config` servers, and `--bare` needs an API key.
+
 Command caps follow one rule on every lane that runs a terminal: [ohflow](ohflow.md#command-caps). Structured results and `schema_error`: [ohflow](ohflow.md#structured-results-and-dimensional-review). Pricing, `cost_source` and token reconcile: [traces](traces.md).
 
 ## pi
@@ -134,7 +148,7 @@ Codex announces no tool list, so `rollcall_matches` checks its servers only. Its
 
 Every worker has its own worktree, so the bucket name follows from the working directory. The lane copies the log into `<attempt>/session/`. Python 3.14's `compression.zstd` reads it. `assistant/message` records carry usage, `tool/call` and `tool/result` the actions, `request/header` the announced tools, `turn/end` the outcome.
 
-- **Liveness.** Stderr goes silent while the agent runs tools. The stall deadline also reads the session log's modification time, which moves per event. `max_iterations` is not enforced live: no event reaches the runner while the agent works. dsh spends about 30 s shutting down its MCP fleet after the answer, so allow for it in `stall_timeout_s`.
+- **Liveness.** Stderr goes silent while the agent runs tools. The stall deadline also reads the session log's modification time, which moves per event. `max_iterations` is not enforced live: no event reaches the runner while the agent works. dsh spends about 30 s shutting down its MCP fleet after the answer, so allow for it in `stall_timeout_s`. A quiet codex reasoning step has run past 180 s without an event, so the roll call gives codex 600 s.
 - **No dashboard window.** Serena opens a "Serena Dashboard" window on every start. Every dsh worker launches with `--patch scripts/ohflow/dsh_worker.patch.yml`, which restates the Serena row with `--open-web-dashboard False`.
 - **Answered but still running.** A dsh process can finish its turn and then neither print nor exit. The runner kills a dsh process 60 s after a completed `turn/end` (`OHFLOW_DSH_EXIT_GRACE_S` overrides) and takes the final message from the log. `result.json` then carries `exit_grace_killed_after_s`. Session-end hooks may be cut short.
 - **Tokens.** dsh's `inputTokens` excludes cache reads. The lane adds `cacheReadTokens` to the prompt count, as every other lane does.
**toolResult** for `call_380167ef4ad244b2a85b71d1` (bash)

#### [14] line 14 · message · assistant · 2026-10-01T22:40:54.648Z
<details><summary>thinking</summary>

Now let me look at the test files:

</details>
**toolCall bash** id=`call_96f816139ded449a897fd7d7`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && git diff arch/deepening...HEAD -- oh-dispatch/tests/"
}
```

#### [15] line 15 · message · toolResult · 2026-10-01T22:40:54.806Z
diff --git a/oh-dispatch/tests/test_defect_07_detached_run_survives.py b/oh-dispatch/tests/test_defect_07_detached_run_survives.py
index 18e8336..b7f71da 100644
--- a/oh-dispatch/tests/test_defect_07_detached_run_survives.py
+++ b/oh-dispatch/tests/test_defect_07_detached_run_survives.py
@@ -4,6 +4,10 @@ The launcher can itself be a member of a kill-on-close Job Object.  A normal
 ``Popen`` keeps the detached supervisor in that job, so the CLI returns success
 even though closing the launcher job kills the promised background run.
 
+Every wait on a real process uses one bound, `LOADED_BOX_WAIT_S` (60 s), because
+the first and second tests failed under the load of a full suite run with
+bounds of 10 s and 15 s.
+
 These are real-process tests.  The first assigns a launcher to a kill-on-close
 job that permits breakaway, waits until the command step is running, closes the
 job, and requires the journal to reach ``run_finished``.  The second uses a
@@ -124,6 +128,19 @@ def _journal_has(run_dir: Path, event: str, timeout_s: float) -> bool:
     return False
 
 
+#: Upper bound for every wait on a real process in this file. A wait returns
+#: the moment its condition holds, so a large bound costs nothing on a quiet
+#: box. The old 10 s and 15 s bounds failed `test_run_finishes_after_the_
+#: launcher_job_closes` while the full suite ran: the run did not reach its
+#: first `step_started` within 10 s under load.
+LOADED_BOX_WAIT_S = 60
+
+
+def _await_event(run_dir: Path, event: str) -> bool:
+    """Wait up to `LOADED_BOX_WAIT_S` for `event` in the run's journal."""
+    return _journal_has(run_dir, event, LOADED_BOX_WAIT_S)
+
+
 @unittest.skipUnless(WINDOWS, "Windows console creation flags are required")
 class SupervisorCommandsStayWindowless(unittest.TestCase):
 
@@ -235,16 +252,16 @@ class DetachedRunSurvivesItsLauncher(unittest.TestCase):
         process, job, log, log_path, run_dir = self._launch_in_job(
             allow_breakaway=True)
         try:
-            returncode = process.wait(timeout=15)
+            returncode = process.wait(timeout=LOADED_BOX_WAIT_S)
             log.close()
             self.assertEqual(returncode, 0, log_path.read_text(encoding="utf-8"))
-            self.assertTrue(_journal_has(run_dir, "step_started", 10),
+            self.assertTrue(_await_event(run_dir, "step_started"),
                             "the command step never started")
             self.assertFalse(_journal_has(run_dir, "run_finished", 0.01),
                              "the command finished before the job-close test")
             self.assertTrue(_kernel32().CloseHandle(job))
             job = None
-            self.assertTrue(_journal_has(run_dir, "run_finished", 15),
+            self.assertTrue(_await_event(run_dir, "run_finished"),
                             "closing the launcher job killed the detached run")
         finally:
             if not log.closed:
@@ -261,16 +278,16 @@ class DetachedRunSurvivesItsLauncher(unittest.TestCase):
         process, job, log, log_path, run_dir = self._launch_in_job(
             allow_breakaway=False)
         try:
-            returncode = process.wait(timeout=60)
+            returncode = process.wait(timeout=LOADED_BOX_WAIT_S)
             log.close()
             output = log_path.read_text(encoding="utf-8")
             self.assertEqual(returncode, 0, output)
             self.assertIn('"route": "wmi"', output)
-            self.assertTrue(_journal_has(run_dir, "step_started", 15),
+            self.assertTrue(_await_event(run_dir, "step_started"),
                             "the command step never started")
             self.assertTrue(_kernel32().CloseHandle(job))
             job = None
-            self.assertTrue(_journal_has(run_dir, "run_finished", 20),
+            self.assertTrue(_await_event(run_dir, "run_finished"),
                             "closing the launcher job killed the WMI run")
         finally:
             if not log.closed:
diff --git a/oh-dispatch/tests/test_defect_44_parent_session_vars_reach_no_worker.py b/oh-dispatch/tests/test_defect_44_parent_session_vars_reach_no_worker.py
new file mode 100644
index 0000000..4dcc20a
--- /dev/null
+++ b/oh-dispatch/tests/test_defect_44_parent_session_vars_reach_no_worker.py
@@ -0,0 +1,126 @@
+"""Defect 44: a worker inherited the variables of the session that launched ohflow.
+
+What went wrong. Only the claude, codex and dsh runners removed `CLAUDE*`,
+`CLAUDECODE` and `ANTHROPIC_BASE_URL` from the environment they pass on. The
+pi and host lanes passed all of them. In the first live full roll call, run
+from a Claude desktop session, the host worker (OpenHands) reported itself as
+"Claude Code" and listed Claude Code's tools.
+
+What is asserted here. For each of the five lanes, the environment of the
+worker process holds none of those variables when the launching process has
+them. A variable a lane sets itself on purpose survives. The runner process
+that `CliLane` and `HostLane` start is checked at its launch seam
+(`spawn_managed`). The CLI process that the claude, codex, dsh and pi
+adapters start is checked at `prepare`.
+"""
+
+from __future__ import annotations
+
+import json
+import os
+import re
+import sys
+from pathlib import Path
+from unittest import mock
+
+from ohflow import lanes, proc
+from ohflow.claude_runner import ClaudeAdapter
+from ohflow.codex_runner import CodexAdapter
+from ohflow.dsh_runner import DshAdapter
+from ohflow.pi_runner import PiAdapter
+from ohflow.plan import ModelSpec, ToolSurface, WorkerSpec
+from ohflow.worker import HostLane, spec_json
+from support import TempCase
+
+PARENT = {"CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "claude-desktop",
+          "CLAUDE_AGENT_SDK_VERSION": "0.3.284",
+          "ANTHROPIC_BASE_URL": "http://127.0.0.1:1/parent-proxy"}
+LEAK = re.compile(r"^(CLAUDE|ANTHROPIC_BASE_URL$)")
+MODEL = ModelSpec("zai/glm-5.3-flash", "https://example.invalid/v1", "TEST_KEY")
+
+
+class _Captured(Exception):
+    def __init__(self, env):
+        self.env = env
+
+
+def _capture_launch(argv, **kwargs):
+    raise _Captured(dict(kwargs["env"]))
+
+
+class ParentSessionVarsReachNoWorker(TempCase):
+
+    def setUp(self):
+        super().setUp()
+        patch = mock.patch.dict(os.environ, {**PARENT, "TEST_KEY": "[redacted]"})
+        patch.start()
+        self.addCleanup(patch.stop)
+
+    def _leaked(self, env) -> list[str]:
+        return sorted(k for k in env if LEAK.match(k))
+
+    def _spec(self, lane: str, **changes) -> dict:
+        out = self.tmp / f"attempt-{lane}"
+        out.mkdir(exist_ok=True)
+        (out / "brief.md").write_text("Report for duty.\n", encoding="utf-8")
+        worker = WorkerSpec(role="rollcall", brief="x", model=MODEL,
+                            tools=ToolSurface(only=("bash",)) if lane == "pi"
+                            else ToolSurface(), lane=lane, **changes)
+        workspace = self.tmp / "workspace"
+        workspace.mkdir(exist_ok=True)
+        spec = spec_json(worker, coord=f"01.p/01.{lane}", workspace=workspace,
+                         out_dir=out, wall_timeout_s=60, attempt=1)
+        (out / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
+        return spec
+
+    def _launch_env(self, lane_name: str) -> dict:
+        spec = self._spec(lane_name)
+        lane = lanes.lane_for(lane_name)
+        with mock.patch("ohflow.cli_lane.spawn_managed", _capture_launch), \
+                mock.patch("ohflow.worker.spawn_managed", _capture_launch):
+            try:
+                lane.launch(spec, self.tmp / f"attempt-{lane_name}")
+            except _Captured as seen:
+                return seen.env
+        self.fail(f"{lane_name} lane did not reach spawn_managed")
+
+    def test_parent_session_vars_do_not_reach_the_claude_runner_or_its_cli(self):
+        self.assertEqual(self._leaked(self._launch_env("claude")), [])
+        env = ClaudeAdapter().prepare(self._spec("claude"),
+                                      self.tmp / "attempt-claude").env
+        self.assertEqual(self._leaked(env), [])
+
+    def test_parent_session_vars_do_not_reach_the_codex_runner_or_its_cli(self):
+        self.assertEqual(self._leaked(self._launch_env("codex")), [])
+        env = CodexAdapter().prepare(self._spec("codex"),
+                                     self.tmp / "attempt-codex").env
+        self.assertEqual(self._leaked(env), [])
+
+    def test_parent_session_vars_do_not_reach_the_dsh_runner_or_its_cli(self):
+        self.assertEqual(self._leaked(self._launch_env("dsh")), [])
+        env = DshAdapter().prepare(self._spec("dsh"),
+                                   self.tmp / "attempt-dsh").env
+        self.assertEqual(self._leaked(env), [])
+
+    def test_parent_session_vars_do_not_reach_the_pi_runner_or_its_cli(self):
+        self.assertEqual(self._leaked(self._launch_env("pi")), [])
+        out = self.tmp / "attempt-pi"
+        spec = self._spec("pi")
+        with mock.patch("ohflow.pi_surface.prewarm_mcp",
+                        lambda surface, env, out_dir: surface):
+            env = PiAdapter().prepare(spec, out).env
+        self.assertEqual(self._leaked(env), [])
+
+    def test_parent_session_vars_do_not_reach_the_host_runner(self):
+        spec = self._spec("host")
+        lane = HostLane(python=Path(sys.executable))
+        with mock.patch("ohflow.worker.spawn_managed", _capture_launch):
+            with self.assertRaises(_Captured) as seen:
+                lane.launch(spec, self.tmp / "attempt-host")
+        self.assertEqual(self._leaked(seen.exception.env), [])
+
+    def test_parent_session_vars_are_the_only_names_the_rule_removes(self):
+        env = proc.worker_env({**PARENT, "PATH": "p", "CLAUDE_X": "1",
+                               "ZAI_CODING_CN_API_KEY": "[redacted]", "CODEX_HOME": "c"})
+        self.assertEqual(env, {"PATH": "p", "ZAI_CODING_CN_API_KEY": "[redacted]",
+                               "CODEX_HOME": "c"})
diff --git a/oh-dispatch/tests/test_defect_45_hermetic_claude_loads_no_instruction_files.py b/oh-dispatch/tests/test_defect_45_hermetic_claude_loads_no_instruction_files.py
new file mode 100644
index 0000000..f0fccd3
--- /dev/null
+++ b/oh-dispatch/tests/test_defect_45_hermetic_claude_loads_no_instruction_files.py
@@ -0,0 +1,57 @@
+"""Defect 45: a hermetic claude worker still loaded the user's CLAUDE.md.
+
+The first full roll-call matrix ran `single:claude:1:profile=hermetic`. The
+worker answered from the user's `~/.claude/CLAUDE.md`, so the profile did not
+isolate it. `--setting-sources project,local` drops the user's settings but
+does not govern instruction files. `--safe-mode` drops them but also drops the
+`--mcp-config` servers, and `--bare` needs an API key, so neither can serve.
+`CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` removes the instruction files, keeps the
+`--mcp-config` servers and keeps the OAuth login.
+
+The profile is hermetic when the prepared process sets that variable and keeps
+the setting-source flag. A usual-setup worker sets neither.
+"""
+
+from __future__ import annotations
+
+import os
+from pathlib import Path
+
+from ohflow.claude_runner import ClaudeAdapter
+from support import TempCase
+
+FAKE = Path(__file__).resolve().parent / "fakes" / "fake_claude.py"
+DISABLE = "CLAUDE_CODE_DISABLE_CLAUDE_MDS"
+
+
+class HermeticClaudeInstructionFiles(TempCase):
+    def setUp(self):
+        super().setUp()
+        old = os.environ.get("OHFLOW_CLAUDE_EXE")
+        os.environ["OHFLOW_CLAUDE_EXE"] = str(FAKE)
+        self.addCleanup(lambda: os.environ.pop("OHFLOW_CLAUDE_EXE", None) if old is None
+                        else os.environ.__setitem__("OHFLOW_CLAUDE_EXE", old))
+        self.workspace = self.tmp / "workspace"
+        self.workspace.mkdir()
+        self.out = self.tmp / "attempt"
+        self.out.mkdir()
+        (self.out / "brief.md").write_text("x\n", encoding="utf-8")
+
+    def _prepared(self, **changes):
+        spec = {"workspace": str(self.workspace), "model": {"model": "m"},
+                "tools": {"only": ["terminal"]}, "mcp_config": {}}
+        spec.update(changes)
+        return ClaudeAdapter().prepare(spec, self.out)
+
+    def test_hermetic_profile_disables_the_instruction_files(self):
+        prepared = self._prepared(profile="hermetic")
+        self.assertEqual(prepared.env.get(DISABLE), "1")
+
+    def test_hermetic_profile_keeps_the_setting_source_flag(self):
+        argv = list(self._prepared(profile="hermetic").argv)
+        self.assertEqual(argv[argv.index("--setting-sources") + 1], "project,local")
+
+    def test_the_usual_setup_keeps_the_instruction_files(self):
+        prepared = self._prepared()
+        self.assertNotIn(DISABLE, prepared.env)
+        self.assertNotIn("--setting-sources", prepared.argv)
diff --git a/oh-dispatch/tests/test_defect_46_rollcall_report_lane_must_match_the_step.py b/oh-dispatch/tests/test_defect_46_rollcall_report_lane_must_match_the_step.py
new file mode 100644
index 0000000..1acd668
--- /dev/null
+++ b/oh-dispatch/tests/test_defect_46_rollcall_report_lane_must_match_the_step.py
@@ -0,0 +1,59 @@
+"""Defect 46: the roll-call gate passed a report that named the wrong lane.
+
+The report holds a `lane` field, and nothing compared it with the lane of the
+step. A worker that copied another lane's report, or a step that ran on the
+wrong lane, passed the gate when its tool list was inside the announced one.
+`rollcall_matches` now takes the step's lane and fails a report that names
+another. The roll-call plan passes that lane on every report check.
+"""
+
+from __future__ import annotations
+
+import json
+
+from ohflow.gates import GateContext, rollcall_matches
+from ohflow.plans import rollcall
+from support import TempCase
+
+RESULT = {"tools": ["Bash"], "mcp_servers": ["forum"]}
+
+
+class ReportLane(TempCase):
+
+    def _ctx(self, report) -> GateContext:
+        (self.tmp / "result.json").write_text(json.dumps(RESULT), encoding="utf-8")
+        return GateContext(coord="c", repo=self.tmp, worktree=self.tmp, base_sha="x",
+                           base_ref="main", step_dir=self.tmp, log_dir=self.tmp,
+                           structured=report)
+
+    def _report(self, lane):
+        return {"lane": lane, "tools": ["Bash"], "mcp_servers": ["forum"]}
+
+    def test_report_lane_naming_another_lane_fails(self):
+        result = rollcall_matches(self._ctx(self._report("pi")), lane="codex")
+        self.assertFalse(result.passed)
+        self.assertIn("'pi'", result.detail)
+        self.assertIn("'codex'", result.detail)
+
+    def test_report_lane_naming_the_step_lane_passes(self):
+        self.assertTrue(rollcall_matches(self._ctx(self._report("codex")),
+                                         lane="codex").passed)
+
+    def test_report_lane_missing_fails_when_the_step_names_one(self):
+        report = {"tools": ["Bash"], "mcp_servers": ["forum"]}
+        self.assertFalse(rollcall_matches(self._ctx(report), lane="codex").passed)
+
+    def test_report_lane_is_not_checked_when_the_step_names_none(self):
+        self.assertTrue(rollcall_matches(self._ctx(self._report("pi"))).passed)
+
+    def test_report_lane_reaches_every_report_check_of_the_plan(self):
+        plan = rollcall.build({"repo": str(self.tmp / "repo"), "shape": "merge",
+                               "lanes": "pi,claude"})
+        seen = {}
+        for phase in plan.phases:
+            for step in phase.steps:
+                for check in step.gate.checks if step.gate else ():
+                    if check.name == "rollcall_matches":
+                        seen[step.id] = check.args["lane"]
+        self.assertEqual(seen, {"pi-1": "pi", "claude-1": "claude",
+                                "consolidate": "claude"})
diff --git a/oh-dispatch/tests/test_defect_47_rollcall_stall_limit_is_per_lane.py b/oh-dispatch/tests/test_defect_47_rollcall_stall_limit_is_per_lane.py
new file mode 100644
index 0000000..f472d18
--- /dev/null
+++ b/oh-dispatch/tests/test_defect_47_rollcall_stall_limit_is_per_lane.py
@@ -0,0 +1,39 @@
+"""Defect 47: one 180 s stall limit killed a quiet-reasoning codex step.
+
+The first live full matrix gave every lane `stall_timeout_s=180`. A codex
+worker thinks for minutes without an event, so the limit killed it as a
+`stall` and the cell failed. The roll call now takes the limit per lane.
+`STALL_S` holds the table and codex gets at least 600 s. The plan argument
+`stall_timeout_s` still overrides the table for every lane.
+"""
+
+from __future__ import annotations
+
+from ohflow.lanes import CAP_STALL, lane_info
+from ohflow.plans import rollcall
+from support import TempCase
+
+LANES = "pi,host,claude,codex,dsh"
+
+
+class RollcallStallPerLane(TempCase):
+
+    def _limits(self, **args) -> dict[str, int | None]:
+        plan = rollcall.build({"repo": str(self.tmp / "repo"), "shape": "fanout",
+                               "lanes": LANES, **args})
+        return {step.id.rsplit("-", 1)[0]: step.stall_timeout_s
+                for phase in plan.phases for step in phase.steps}
+
+    def test_codex_gets_at_least_ten_minutes(self):
+        self.assertGreaterEqual(self._limits()["codex"], 600)
+
+    def test_every_lane_that_takes_a_limit_gets_one(self):
+        for lane, limit in self._limits().items():
+            if lane_info(lane).has(CAP_STALL):
+                self.assertGreater(limit, 0, lane)
+            else:
+                self.assertIsNone(limit, lane)
+
+    def test_the_argument_overrides_every_lane(self):
+        for lane, limit in self._limits(stall_timeout_s=45).items():
+            self.assertEqual(limit, 45 if lane_info(lane).has(CAP_STALL) else None, lane)
**toolResult** for `call_96f816139ded449a897fd7d7` (bash)

#### [16] line 16 · message · assistant · 2026-10-01T22:41:50.968Z
<details><summary>thinking</summary>

Now I have a good picture of the milestone diff. Let me carefully examine the code:

1. **worker_env rule in proc.py** - moved `_PARENT_SESSION_VARS` regex and logic to `proc.worker_env()`. `seat_runner.seat_env` now uses it, `pi_runner` uses `proc.worker_env()`, `worker.py` HostLane uses `worker_env()`, `cli_lane.py` CliLane uses `worker_env()`. 

Let me check all places where an environment is built for a child process. I need to grep for `os.environ` usage and `dict(os.environ)` in the scripts.

2. **Hermetic claude**: `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` env var. Hmm, one question: does the parent session's `CLAUDE*` stripping remove... no wait, `CLAUDE_CODE_DISABLE_CLAUDE_MDS` starts with `CLAUDE` so it would be stripped by `_PARENT_SESSION_VARS`! Wait — in `claude_runner.prepare`, `env=seat_env(HERMETIC_ENV if hermetic else None)`. Let me check `seat_env`:

```python
def seat_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    env = proc.worker_env()
    env["PYTHONIOENCODING"] = "utf-8"
    env.update(extra or {})
    return env
```

The `extra` is applied after the stripping, so `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` survives. Good.

But wait — what if the *parent* session sets `CLAUDE_CODE_DISABLE_CLAUDE_MDS`? Then... the strip removes it, and hermetic adds it back as "1". Non-hermetic would not have it. That's fine — non-hermetic launches without it, meaning CLAUDE.md files load. That's the intent of non-hermetic.

Actually wait, there's a subtle issue: if the parent Claude session sets `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` (some users disable CLAUDE.md loading), then a non-hermetic worker would now load CLAUDE.md files... but that's the "usual setup" which is supposed to mirror the user's setup. Minor, not a defect. Actually, the variable is stripped by the rule, and non-hermetic doesn't set it, so the worker loads instruction files — consistent with "usual setup". Fine.

3. **Stall limit per lane**: `STALL_S = {"pi": 180, "host": 180, "claude": 180, "codex": 600, "dsh": 180}`. `stall_for(lane)` returns None when the lane doesn't have CAP_STALL. `stall` is `int | None` — the override.

Wait — there's something to check: `normalize` does `stall=(int(args["stall_timeout_s"]) if args.get("stall_timeout_s") not in (None, "") else None)`. Previously default was 180. Now default None. If a plan argument `stall_timeout_s=0`... `0 not in (None, "")` — `0 == ""` is False, `0 == None` is False, so `int(args[...])` = 0. OK.

But what about other plans or places that use `stall_timeout_s`? Let me check where `Spec.stall` is used elsewhere. Also the campaign/review plans may have their own stall handling. Let me grep.

Also, the README says "The stall limit defaults per lane: 600 s for codex, 180 s for every other lane. The argument replaces that table for every lane." — consistent with STALL_S.

4. **Report lane gate**: `rollcall_matches` takes `lane` kwarg and fails when report's `lane` doesn't match. The plan passes `{"lane": lane}` for every report check via `_report_checks(owns, lane, ...)`. All call sites updated? `_solo` passes lane, `_relay` passes lane, `_merge` passes `spec.consolidator` for the consolidate step and... wait, in `_merge`, what about the fanout steps `merge-{sid}`? Let me check the full `_merge` function. The diff only shows the consolidate step getting `spec.consolidator`. The `merge-{sid}` steps presumably use `_solo`-like or some other call. Let me read the current rollcall.py in full.

Also `campaign` and `review` shapes — do they have report checks? The test `test_report_lane_reaches_every_report_check_of_the_plan` only builds "merge" shape. Exit criterion 3 requires `python oh-dispatch/tests/run_tests.py -k report_lane` runs ≥ 1 test: a report naming another lane fails the gate. That's covered.

But a careful engineer would check: are there other shapes (`campaign`, `retry`, `review`) with `rollcall_matches` checks that don't pass `lane`? If a shape has `CheckSpec("rollcall_matches")` without lane, then a wrong-lane report passes there. Spec scope item 4 says "The roll-call gate fails a report whose `lane` is not the step's lane, so a stray or partial message cannot pass." Let me check all `rollcall_matches` CheckSpec creations in the plan.

5. **README figures**: need to check matrix.json for the measured values: full run 1942.7s = 32m 22.7s → "32 m 23 s"; quick — wait, the quick row says "24 m 27 s (1466.5 s ...)". 1466.5 s = 24 m 26.5 s → 24 m 26.5 s ≈ 24 m 27 s (rounding 26.5 → 27). OK. But wait — the quick figure was measured from a full matrix run? The quick matrix is a subset; how did they measure quick's wall time from a full run? The full run runs all 15 cells; quick is 10 of them. Hmm, they might have summed the per-cell durations of the quick cells? That's a derived figure. The spec says: "Fill the 'Wall time' column of the `quick` and `full` rows from the measured `matrix.json` above". So they should derive from matrix.json. 1466.5 s might be the sum of the quick cells' durations? Let me check the matrix.json file to verify these figures.

Also the README suite figure: "896 tests, 885 s on 2026-10-02" and shard figures "340.2 s, 282.9 s and 261.4 s on 2026-10-02" — from a shard run on this branch. I need to run the shards myself (exit criteria + gate check) and verify the counts. Actually the review instructions say run the full suite as three shards. I should verify README numbers roughly match (they say "about fifteen minutes" and shards "about five minutes"... hmm "Each shard takes about five minutes (340.2 s...)" — 340 s is 5m40s. "about five minutes" is a stretch but fine).

Wait, there's a subtle problem: README says the suite has 896 tests. Let me count what the shard runs report. If the implementer's count is right, running the shards should show 896 tests total. Let me verify.

Also note exit criterion 5: `grep -n "not measured yet" oh-dispatch/README.md` → no match. The diff shows both "not measured yet" replaced. Good.

6. **Detached-run test wait bounds**: 10/15/20 s → 60 s. This is a test-only change; justifiable (bd76078). Not a defect per se. But note: `process.wait(timeout=60)` for the first test — previously 15. And the second test's `process.wait(timeout=60)` was already 60. OK.

Now the careful-engineer checklist from my instructions:

a. **A worker launch on any lane that still passes `CLAUDE*`, `CLAUDECODE` or `ANTHROPIC_BASE_URL`** — grep every place an environment is built for a child. Let me grep for `os.environ` in ohflow scripts, and for `Popen`, `spawn_managed`, `seat_env`, `worker_env`.

b. **A hermetic claude session that can still read the user's instruction files or settings, or that loses its login** — the hermetic env sets `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1`. Need to check: does `build_command` for hermetic use `--setting-sources project,local`? The lanes.md table says hermetic removes user settings via `--setting-sources project,local`. But hold on: "the project's own `.claude` files" are kept. Hmm — does `--setting-sources project,local` keep the project's `.claude/settings.json`? I believe setting sources: user, project, local. `project,local` drops user. And instruction files: CLAUDE.md loading is governed by... `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` is an undocumented-but-real env var. The implementer says "Measured 2026-10-01 (2.1.281)". The m7 exit criterion 4 actually runs the live cell, which passed per implementer's gate (phase 1 passed). Well, I can't run live cells myself (only the implementer may, and only on the three failing cells — as the reviewer, I should NOT run live cells; spec says "The implementer may run live cells only through ohflow rollcall --cells on the three failing cells... at most three times each". As reviewer I run the exit criteria — criterion 4 IS a live cell run! "with CLAUDECODE=1 ... ohflow rollcall --cells single:host single:claude:1:profile=hermetic relay:pi,claude,codex,dsh from oh-dispatch/scripts | last line ROLLCALL PASS: 3 of 3 cells".

Hmm, exit criterion 4 requires running live cells. That takes ~30+ min (relay with codex 600s stall, host cell ~2 min, claude hermetic ~1 min). This is a real cost but it's an exit criterion. The review instructions say "Run the exit criteria of the spec yourself, one by one, and note each result." I should attempt it. It's three cells; the full matrix took 33 min for 15 cells, so 3 cells maybe ~5-8 minutes sequential (matrix runs with max_parallel=3, so maybe less). Let me think about whether I'm allowed: "The implementer may run live cells only through `ohflow rollcall --cells` on the three failing cells (`single:host`, `single:claude:1:profile=hermetic`, `relay:pi,claude,codex,dsh`), at most three times each." This constraint is written for the implementer. Criterion 4 is exactly those three cells. As the reviewer running exit criteria, criterion 4 is one run of those three cells. I think I should run it — it's the only way to verify criterion 4 and the hermetic behavior for real.

But wait — do I have the credentials/logins? The worktree is on this machine, the seats are logged in. The rollcall launches pi (zai flat rate), claude (seat quota), codex (seat quota), dsh? The relay cell is `relay:pi,claude,codex,dsh` — dsh too. single:host runs OpenHands host. These all run locally. OK.

Concern: running from my shell, my environment is... what? I'm the pi reviewer; my process may not have CLAUDECODE etc. set. Criterion 4 says to export CLAUDECODE=1, CLAUDE_CODE_ENTRYPOINT=claude-desktop, CLAUDE_AGENT_SDK_VERSION=0.3.284 before running. That simulates the desktop-app launcher. Good — that's how the defect manifests.

c. **A stall limit that a lane's normal silence can still trip** — codex gets 600. dsh gets 180 + log mtime. claude 180 — claude emits stream-json events per tool call; reasoning? Claude Code emits events during reasoning? There can be long quiet periods during a single long tool call (e.g. a bash command running 3+ min)... The m7 evidence only showed codex tripping. Fine.

Also host lane: `lane_info("host").has(CAP_STALL)`? Let me check what CAP_STALL means for host — the host lane runs OpenHands; does it have stall detection? `STALL_S` includes "host": 180. And `stall_for` returns None if the lane lacks CAP_STALL. Let me check lanes.py registry to see which lanes have CAP_STALL. If host lacks CAP_STALL, then STALL_S["host"] is dead but harmless. Test `test_every_lane_that_takes_a_limit_gets_one` covers all five lanes.

Wait, there's a subtle issue: `STALL_S[lane]` — KeyError if a lane isn't in the table. The roll call supports lanes pi, claude, codex, dsh, host. Are there other lanes? The container lane was deleted. So five lanes. OK.

d. **A report whose `lane` names another lane and still passes the gate** — need to check all rollcall_matches check sites pass lane. Let me grep.

e. **README figures vs matrix.json** — check matrix.json.

f. **A test that passes both with and without its fix** — e.g. defect 44's tests: do they fail against old code? The old code: pi_runner used `dict(os.environ)` → CLAUDE* leaked → test fails against old code. Good. HostLane used `dict(os.environ)` → leaked. cli_lane used `dict(os.environ)` → leaked. Defect 45: hermetic env didn't exist → `prepared.env.get(DISABLE)` None → fail. Good. Defect 46: gate had no lane check → `rollcall_matches(..., lane="codex")` with report lane "pi" would pass (no lane param existed... wait, old signature `rollcall_matches(ctx, surface=None)` — calling with `lane="codex"` would TypeError! Hmm, "a test that passes both with and without its fix" — with the old code the test errors (TypeError), which counts as failing. Fine.

Defect 47: old code `stall=int(args.get("stall_timeout_s", 180))` and `stall = spec.stall if lane_info...has(CAP_STALL) else None` → codex got 180 → `assertGreaterEqual(600)` fails. Good.

Also I should check the implementer "proved defect tests fail against old code" — charter requires it; can't fully verify but can reason.

g. **Prose that contradicts code** — lanes.md hermetic table: check each claim. `pi` "has no profile; it is always hermetic". `host` "has no profile; the host runner loads only what the plan names". `claude` row as discussed. `codex` — "the real ~/.codex configuration... the worker gets its own CODEX_HOME" and "auth.json is a hard link". Need to verify codex_runner indeed does this (that's from earlier milestones presumably). `dsh` — "takes a dsh seat profile name instead; hermetic is not a dsh profile". Need to check what dsh does with `profile` — does passing profile=hermetic to dsh error out or get ignored? The roll call only allows profile for claude and codex per the argument docs ("profile (`hermetic` for claude and codex)").

Also the pi row "no ambient extensions, skills, prompts, context files or themes" — pi_runner sets PI_CODING_AGENT_DIR to a written agent dir, PI_OFFLINE=1. Plausible from earlier milestones.

Now, one important thing to check in `pi_runner.prepare`: `env = proc.worker_env()` then sets PI_CODING_AGENT_DIR etc. But it also reads `os.environ.get("OHFLOW_BASH", ...)` — fine.

But wait — in pi_runner, does the env need `OHFLOW_BASH`? It reads from os.environ (the launcher's), not from the worker env. That's the runner passing a value to the worker. Fine.

Another check: `worker_env()` doc says "A variable a lane sets on purpose is added afterwards." In pi_runner, after `env = proc.worker_env()`, nothing re-adds CLAUDE*. Good.

But hmm — one more subtle thing: `ANTHROPIC_BASE_URL` is stripped from every worker. What if a user *deliberately* routes claude workers through a proxy via ANTHROPIC_BASE_URL in their shell? Not our concern; spec mandates stripping.

Also `ANTHROPIC_AUTH_TOKEN`? Not stripped (doesn't match pattern). The desktop app exports ANTHROPIC_BASE_URL pointing at its proxy; if ANTHROPIC_AUTH_TOKEN were also exported, the worker would use the desktop proxy with... but BASE_URL is stripped so AUTH_TOKEN alone doesn't redirect. OK. What about `ANTHROPIC_API_KEY`? Not stripped; if the desktop session exports it, a hermetic claude worker might use it instead of OAuth login... Spec only names CLAUDE*, CLAUDECODE, ANTHROPIC_BASE_URL. The measured desktop session had 26 CLAUDE* names + ANTHROPIC_BASE_URL. Fine.

Wait, actually — hmm, `_PARENT_SESSION_VARS = re.compile(r"^(CLAUDE|CLAUDECODE$|ANTHROPIC_BASE_URL$)")`. `^(CLAUDE...)` matches any var starting with CLAUDE, including CLAUDECODE (redundant alternative) — that's from the old code, unchanged semantics. OK.

Now let me also check `seat_runner.py` — after the change, does it still import `re`? The diff removed the regex from seat_runner; if `re` is now unused there, that's a lint issue but not a defect. Let me check.

Let me also check `gates.py` register decorator: the description lambda uses `a.get("lane")` and `a['lane']` — f-string only when truthy. Fine.

Also `rollcall_matches` signature change: are there other callers of `rollcall_matches` (e.g., tests, engine)? `CheckSpec("rollcall_matches", {"lane": lane})` — how does the engine pass args to gate functions? Presumably kwargs. Old callers without lane still work (lane=None default). Good.

Now, what about `review` and `campaign` shapes in rollcall plan — do they include `rollcall_matches` checks without lane? Let me read the whole rollcall.py.

Also `_merge`'s fanout steps: `_step(spec, f"merge-{sid}"...)` — wait let me read the actual code. In the diff, `_merge` shows only the consolidate step. Let me read the full file.

Let me also check the `matrix.json` to verify README numbers.

And check git hygiene: commits messages, authorship (no Co-Authored-By). `git log --format` for the five commits.

Plan of action:
1. Read full rollcall.py, lanes.py (registry, CAP_STALL), claude_runner.py, proc.py, seat_runner.py as they are now.
2. Grep for environment building for children: `dict(os.environ)`, `os.environ.copy()`, `environ=`, `env=`.
3. Check matrix.json numbers vs README.
4. Run exit criteria 1, 2, 3, 5 (fast).
5. Run the three shards (each ~5 min).
6. Run exit criterion 4 (live cells, ~10-30 min?). Need to be careful about time. Let me estimate: single:host ~2 min, single:claude hermetic ~1-2 min, relay pi→claude→codex→dsh: pi 30s + claude 1-2 min + codex (600s stall, actual run maybe 1-3 min) + dsh 2-4 min. With max_parallel=3, cells run in parallel: total maybe ~6-10 min. Acceptable in foreground with a generous timeout (the shell timeout param — I can set timeout to like 2400 s? The rules say "Never start the suite in the background" and each subset under ten minutes; but criterion 4 is not the suite. The brief says "Run the subsets that cover every module you touched, in the foreground, each under ten minutes" — for the implementer. For me: "Run the exit criteria of the spec yourself". I'll run criterion 4 in the foreground with a timeout of ~1800 s (30 min) to be safe. Actually, hmm, if it exceeds, the tool kills it. Rollcall has wall_timeout_s=600 default per plan... per step. Total cell wall time bounded by... whatever. Let me just run with timeout 2400 and see.

Also important: criterion 4 must run "from `oh-dispatch/scripts`". And the last line must be `ROLLCALL PASS: 3 of 3 cells`.

Where does the rollcall write its run dirs? Probably a scratch root. The implementer's runs are somewhere. It uses `repo` argument default? `--cells single:host ...` — the CLI presumably synthesizes a scratch repo. Let me check cli for `--cells`. Let me look at how rollcall --cells works (from m5). It probably creates a temp repo under %TEMP%. Fine.

One more careful check: the gate my own report must pass: "the final message matches /VERDICT:\s*(MERGEABLE|BLOCKED)/" and "git status --porcelain prints nothing". I must not create files inside the worktree. Logs go outside (../suite-...log relative to worktree → C:/Users/<user>/dev/_wt/oh-dispatch-deepening/). Good.

Also: I change no file. The rollcall run — does it write inside the worktree? It writes run dirs and worktrees under wt_root (repo.parent / f"{repo.name}-rollcall-wt") — outside the product worktree presumably, in %TEMP%. But careful: rollcall --cells from `oh-dispatch/scripts` — the repo it uses... Let me check the CLI code for how --cells picks the repo. In m5, `ohflow rollcall --matrix` / `--cells` probably makes a throwaway repo in temp. Let me verify by reading cli code.

Hmm wait, actually there's a risk: if the rollcall run creates worktrees of the *current repo* (the product repo in my worktree), git worktree add would write to the shared .git? My worktree's git dir is inside the main repo's .git/worktrees/... Adding a worktree from within my worktree would modify the shared .git (creating a new worktree entry + possibly a new branch). That could dirty nothing in my tree (git status --porcelain would stay clean) but might violate "never change another branch"... m5 already built this matrix machinery and the implementer ran cells from their worktree, so presumably it's designed to use a scratch repo. Let me read the rollcall CLI entry to confirm.

Let me now read the current files.

</details>
The charter and diff are clear. Now let me read the current state of the key modules to check every seam the spec touches.
**toolCall bash** id=`call_411488a1300f4b33ac8e58d9`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && sed -n 1,120p oh-dispatch/scripts/ohflow/plans/rollcall.py"
}
```
**toolCall bash** id=`call_5f5ffdce3df14885a016f574`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && sed -n 120,320p oh-dispatch/scripts/ohflow/plans/rollcall.py"
}
```

#### [17] line 17 · message · toolResult · 2026-10-01T22:41:51.079Z
"""The roll call: seven shapes of one trivial task, as ohflow plans.

Every worker writes who it is, commits that file, and ends with a JSON report.
The lane records what the harness announced, and `rollcall_matches` fails a
report that names a tool or server the harness never announced. The matrix
runner `ohflow rollcall` runs these plans; `ohflow.rollcall` owns the matrices.
How to run and read it: `README.md`, "Testing with live agents".

Shapes, chosen with `--args shape=<name>`:

- `single`    one gated worker on one lane.
- `fanout`    one worker per lane and per `count`, each in its own worktree.
- `relay`     workers in series; each appends to one shared `ROLLCALL.md`.
- `merge`     `fanout`, one merge per worker into `integration`, then one
              consolidator that writes `ROLLCALL.md` as a table.
- `retry`     the first attempt fails a gate on purpose. The failure line
              names a token. The retry reads it in its position block.
- `review`    a worker on one lane, then a reviewer on another that ends with
              a `VERDICT:` line.
- `campaign`  the milestone plan of a one-milestone campaign. Its first brief
              misses a required line, and a judge must repair the brief.

`r0`, `r1` and `r2` are aliases of `fanout`, `relay` and `merge`.

Arguments: `repo` (required), `shape`, `lanes` (comma list), `count` (workers
per lane), `consolidator`, `reviewer`, `judge` (each a lane), `profile`
(`hermetic` for claude and codex), `carry_context`, `config` (a JSON file of
model overrides), `base`, `prefix`, `wt_root`, `wall_timeout_s`,
`stall_timeout_s` (replaces the per-lane `STALL_S` table; codex gets 600 s,
every other lane 180 s), `max_iterations`, `max_parallel`.

    python -m ohflow.cli validate --plan <this file> \\
        --args repo=<scratch repo> --args shape=merge --args lanes=pi,claude
"""

import json
from dataclasses import dataclass
from pathlib import Path

# Absolute, like every other plan module: `load_plan` imports a plan by file
# path, so the module has no parent package.
from ohflow.lanes import CAP_STALL, lane_info
from ohflow.plan import (CheckSpec, GateSpec, ModelSpec, Phase, Plan,
                         RetryPolicy, Step, ToolSurface, WorkerSpec,
                         WorktreeSpec, clean_commit_checks)

SCHEMA_PATH = (Path(__file__).resolve().parents[3] / "references" / "examples" /
               "rollcall" / "rollcall.schema.json")
ROLLCALL_SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

ZAI_URL = "https://api.z.ai/api/coding/paas/v4"
ZAI_KEY = "[redacted]"

#: The cheap route of each lane. `--config` overrides any of them.
MODELS = {
    "pi": ModelSpec(model="zai/glm-5.3-flash", base_url=ZAI_URL,
                    api_key_env=ZAI_KEY, params={"thinking": "low"}),
    "host": ModelSpec(model="openai/glm-5.3-flash", base_url=ZAI_URL,
                      api_key_env=ZAI_KEY),
    # Decided by the operator 2026-09-30: the roll call runs Claude on Haiku 4.5.
    "claude": ModelSpec(model="claude-haiku-4-5-20251001", base_url="",
                        api_key_env=""),
    # The largest-quota model on the Plus seat. The config.toml default
    # (gpt-6.1-sol) is refused for a ChatGPT account, measured 2026-09-30.
    "codex": ModelSpec(model="gpt-5.6-luna", base_url="", api_key_env="",
                       params={"reasoning_effort": "low"}),
    # dsh takes its model from its `headless` profile, which is its default.
    "dsh": ModelSpec(model="", base_url="", api_key_env=""),
}
ORDER = ("pi", "claude", "codex", "dsh")

#: Seconds of silence that stop a worker, per lane. Codex reasons for minutes
#: without an event, and 180 s killed it in the first live matrix. The plan
#: argument `stall_timeout_s` replaces the table for every lane.
STALL_S = {"pi": 180, "host": 180, "claude": 180, "codex": 600, "dsh": 180}

SHAPES = ("single", "fanout", "relay", "merge", "retry", "review", "campaign")
ALIASES = {"r0": "fanout", "r1": "relay", "r2": "merge"}

#: The profile that only claude and codex take among the roll-call lanes.
HERMETIC_LANES = ("claude", "codex")

PRESENT = r'"status"\s*:\s*"PRESENT"'
VERDICT = r"^VERDICT:\s*(PASS|FAIL)\s*$"

#: The retry shape's gate wants this text in the worker's file. The brief does
#: not name it. Only the failure line of the first attempt does.
RETRY_TOKEN = "[redacted]"

#: The campaign shape's gate wants this line. The first brief omits it.
CAMPAIGN_LINE = "Campaign-Token: M5-ROLLCALL"

REPORT = """# Your report

End your last message with one fenced json block and nothing after it. The
block opens with a line of three backticks and the word `json`. It closes with a
line of three backticks. A bare JSON object without those two lines fails the
gate.

```json
{{"lane": "{lane}", "status": "PRESENT", "harness": "<harness name and version>",
 "model": "<your model>", "tools": ["<each built-in tool name>"],
 "mcp_servers": ["<each MCP server name>"],
 "cannot": "<one sentence: what you cannot do in this seat>"}}
```

`tools` holds your built-in tools only, each name exactly as your harness
spells it. Leave every MCP tool out of `tools`; name its server once in
`mcp_servers` instead. Copy each server name from your tool list: for a tool
named `mcp__<server>__<tool>` or `mcp__<server>.<tool>`, the server name is the
`<server>` part, exactly, without the `mcp__` prefix.
Write no wildcard and no pattern. List a tool or a server only when your own
tool list shows it. Do not guess and do not compose names.
"""

ENTRY = """- Harness: your harness name and version
- Model: your model
- Working directory: the absolute path you are working in
- Tools: the names of your built-in tools
- MCP servers: the names of the MCP servers you can see
**toolResult** for `call_411488a1300f4b33ac8e58d9` (bash)

#### [18] line 18 · message · toolResult · 2026-10-01T22:41:51.180Z
- MCP servers: the names of the MCP servers you can see
- Cannot: one sentence on what you cannot do in this seat"""

CLEAN = ("Author it clean: no `Co-Authored-By` line naming a model, no "
         "generated-with footer.")

SOLO_BRIEF = """# Task

You are one worker in a roll call. Your lane is `{lane}`. Your worker id is
`{sid}`. Report for duty.

1. Create the file `rollcall/{sid}.md`. Its first line is `# {sid}`. Then write
   these lines, filled in:

{entry}

2. Commit only that file. The commit message is `rollcall: {sid}`. {clean}
{more}
Change no other file.

""" + REPORT

RETRY_MORE = """3. The position block above may list a failure from an earlier attempt.
   If it does, read it, fix exactly that in the same file, and commit again.
"""

RELAY_BRIEF = """# Task

You are one worker in a relay roll call. Your lane is `{lane}`. Your worker id
is `{sid}`. You are worker {n} of {total}. The position block above says who
went before you.

1. Open `ROLLCALL.md` in the root of this worktree. {create}
2. Append one section at the end of the file. Its heading line is `## {sid}`.
   Under it, write these lines, filled in:

{entry}
- Previous: {previous}

3. Do not change, reorder or delete any line that is already in the file.
4. Commit only `ROLLCALL.md`. The commit message is `rollcall relay: {sid}`.
   {clean}

""" + REPORT

CONSOLIDATE_BRIEF = """# Task

You consolidate a roll call. The files `rollcall/<id>.md` in this worktree
were written by {count} workers: {ids}.

1. Read every `rollcall/*.md` file.
2. Write `ROLLCALL.md` in the root of this worktree. Its first line is
   `# Roll call`. Then one markdown table with this header row:

   | worker | harness | model | tools | mcp servers |

   and one row per worker, in the order {ids}. The `worker` cell holds only the
   worker id. The `tools` and `mcp servers` cells hold a count.
3. Commit only `ROLLCALL.md`. The commit message is `rollcall: consolidate`.
   {clean}

""" + REPORT

REVIEW_BRIEF = """# Task

You review one roll-call file. Another worker wrote `rollcall/{sid}.md` in this
worktree and committed it.

1. Read `rollcall/{sid}.md`. Change no file and make no commit.
2. Check two facts. The first line is `# {sid}`. The file has a Harness line, a
   Model line and a Tools line.
3. End your reply with exactly one line, and nothing after it:
   `VERDICT: PASS` when both facts hold, or `VERDICT: FAIL` when one does not.
"""

MILESTONE_SPEC = f"""# Milestone m1: one worker reports for duty

The product plan runs one worker. It writes `rollcall/{{sid}}.md` and commits.

The gate needs the line `{CAMPAIGN_LINE}` in that file. The worker learns that
line only from `briefs/impl.md`.

Judge the run:

- The gate failed on that line, and `briefs/impl.md` does not tell the worker to
  write it. Return REVISE. Edit `briefs/impl.md` only: add one numbered step that
  tells the worker to add the line `{CAMPAIGN_LINE}` to its file before it commits.
  Change no other file.
- The gate passed and the file holds the line. Return PASS.
- Anything else: return ESCALATE and say why.
"""

CHARTER = """# Roll-call campaign

One milestone proves the campaign loop: run, judge, revise, rerun, land.
Keep every change small. Touch only the milestone directory.
"""

MILESTONE_PLAN = '''"""The m1 plan of the roll-call campaign: it reads its brief from briefs/impl.md."""
from pathlib import Path

from ohflow.plans.rollcall import build_milestone


def build(args):
    brief = (Path(__file__).resolve().parent / "briefs" /
             "impl.md").read_text(encoding="utf-8")
    return build_milestone(args, brief)
'''


# ------------------------------------------------------------------ arguments


def _text_list(value) -> tuple[str, ...]:
    return tuple(x.strip() for x in str(value).split(",") if x.strip())


def _flag(value) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _count(name: str, value, default: int) -> int:
    try:
        n = int(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        raise ValueError(f"roll-call {name} must be a whole number, got "
                         f"{value!r}") from None
    if n < 1:
        raise ValueError(f"roll-call {name} must be 1 or more, got {n}")
    return n


def load_config(path) -> tuple[str, dict[str, ModelSpec]]:
    """`(name, models)`: the table `MODELS` with the overrides of a JSON file.

    The file is `{"name": "...", "lanes": {"<lane>": {"model": ..., "base_url":
    ..., "api_key_env": ..., "params": {...}, "extra_body": {...}}}}`. A key
    that is left out keeps the table's value.
    """
    models = dict(MODELS)
    if not path:
        return "default", models
    try:
        data = json.loads(Path(str(path)).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ValueError(f"roll-call config {str(path)!r} cannot be read: {e}") from None
    if not isinstance(data, dict) or not isinstance(data.get("lanes", {}), dict):
        raise ValueError(f"roll-call config {str(path)!r} must be an object "
                         f"with a 'lanes' object")
    allowed = {"model", "base_url", "api_key_env", "params", "extra_body"}
    for lane, over in data.get("lanes", {}).items():
        if lane not in MODELS:
            raise ValueError(f"roll-call config names unknown lane {lane!r}; "
                             f"known: {list(MODELS)}")
        if not isinstance(over, dict) or set(over) - allowed:
            raise ValueError(f"roll-call config lane {lane!r} may set only "
                             f"{sorted(allowed)}")
        base = models[lane]
        models[lane] = ModelSpec(
            model=over.get("model", base.model),
            base_url=over.get("base_url", base.base_url),
            api_key_env=over.get("api_key_env", base.api_key_env),
            params=over.get("params", base.params),
            extra_body=over.get("extra_body", base.extra_body))
    return str(data.get("name") or Path(str(path)).stem), models


@dataclass(frozen=True)
class Spec:
    """The arguments of one roll-call plan, checked."""
    shape: str                 # the name the caller gave
    kind: str                  # one of SHAPES
    repo: Path
    lanes: tuple[str, ...]
    count: int
    consolidator: str
    reviewer: str
    judge: str
    profile: str | None
    carry_context: bool
    base: str
    prefix: str
    wt_root: Path
    wall: int
    stall: int | None          # the caller's override; None takes STALL_S
    max_iter: int
    max_parallel: int
    models: dict

    def stall_for(self, lane: str) -> int | None:
        """The stall limit of a step on `lane`; None when the lane takes none."""
        if not lane_info(lane).has(CAP_STALL):
            return None
        return self.stall if self.stall is not None else STALL_S[lane]

    @property
    def workers(self) -> list[tuple[str, str]]:
        """`(lane, step id)` for every worker, lane by lane."""
        return [(lane, f"{lane}-{k}") for lane in self.lanes
                for k in range(1, self.count + 1)]
**toolResult** for `call_5f5ffdce3df14885a016f574` (bash)

#### [19] line 19 · message · assistant · 2026-10-01T22:41:55.348Z
<details><summary>thinking</summary>

Let me continue reading rollcall.py — the rest, especially _solo, _fanout, _merge, _retry, _review, _campaign, and where `_report_checks` is called from every shape.

</details>
**toolCall bash** id=`call_70a65b5dd75e4a8ba7b89599`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && sed -n 320,560p oh-dispatch/scripts/ohflow/plans/rollcall.py"
}
```

#### [20] line 20 · message · toolResult · 2026-10-01T22:41:55.512Z
                for k in range(1, self.count + 1)]

    @property
    def lanes_needed(self) -> tuple[str, ...]:
        """Every lane the plan starts a worker on, in a stable order."""
        out = list(self.lanes)
        extra = {"merge": self.consolidator, "review": self.reviewer,
                 "campaign": self.judge}.get(self.kind)
        if extra and extra not in out:
            out.append(extra)
        return tuple(out)


def normalize(args) -> Spec:
    """Check the arguments and fill the defaults. Raises ValueError."""
    repo = Path(args["repo"])
    given = str(args.get("shape", "fanout"))
    kind = ALIASES.get(given, given)
    if kind not in SHAPES:
        raise ValueError(f"unknown roll-call shape {given!r}; use one of "
                         f"{list(SHAPES)} (aliases: "
                         f"{', '.join(f'{a}={s}' for a, s in ALIASES.items())})")
    lanes = _text_list(args.get("lanes") or ",".join(ORDER))
    if not lanes:
        raise ValueError("roll-call lanes is empty; name one or more of "
                         f"{list(MODELS)}")
    unknown = [x for x in (*lanes,) if x not in MODELS]
    if unknown:
        raise ValueError(f"unknown roll-call lanes {unknown}; known: {list(MODELS)}")
    if len(set(lanes)) != len(lanes):
        raise ValueError(f"roll-call lanes lists a lane twice: {list(lanes)}; "
                         f"use count for more workers on one lane")
    count = _count("count", args.get("count"), 1)

    reviewer_arg = str(args.get("reviewer") or "")
    if kind == "review" and len(lanes) == 2 and not reviewer_arg:
        reviewer_arg, lanes = lanes[1], lanes[:1]
    if kind in ("single", "retry", "review", "campaign") and len(lanes) != 1:
        raise ValueError(f"roll-call shape {given!r} runs on exactly one "
                         f"lane, got {list(lanes)}")
    if kind in ("single", "retry", "review", "campaign") and count != 1:
        raise ValueError(f"roll-call shape {given!r} takes count 1; use "
                         f"fanout for more workers")

    consolidator = str(args.get("consolidator") or
                       ("claude" if "claude" in lanes else lanes[0]))
    reviewer = reviewer_arg or ("claude" if lanes[0] != "claude" else "pi")
    judge = str(args.get("judge") or "claude")
    for role, lane in (("consolidator", consolidator), ("reviewer", reviewer),
                       ("judge", judge)):
        if lane not in MODELS:
            raise ValueError(f"roll-call {role} {lane!r} is not a lane; "
                             f"known: {list(MODELS)}")

    profile = str(args.get("profile") or "").strip() or None
    if profile in ("default", "usual"):
        profile = None
    if profile not in (None, "hermetic"):
        raise ValueError(f"roll-call profile must be 'hermetic' or empty, got "
                         f"{profile!r}")
    _name, models = load_config(args.get("config"))
    base = str(args.get("base", "main"))
    return Spec(
        shape=given, kind=kind, repo=repo, lanes=lanes, count=count,
        consolidator=consolidator, reviewer=reviewer, judge=judge,
        profile=profile, carry_context=_flag(args.get("carry_context", False)),
        base=base, prefix=str(args.get("prefix", "rollcall")),
        wt_root=Path(args.get("wt_root", str(repo.parent / f"{repo.name}-rollcall-wt"))),
        wall=int(args.get("wall_timeout_s", 600)),
        stall=(int(args["stall_timeout_s"])
               if args.get("stall_timeout_s") not in (None, "") else None),
        max_iter=int(args.get("max_iterations", 15)),
        max_parallel=int(args.get("max_parallel", 3)), models=models)


def needed_lanes(args) -> tuple[str, ...]:
    """The lanes a cell with these arguments starts workers on."""
    return normalize(args).lanes_needed


def judge_spec(args) -> WorkerSpec:
    """The judge of the campaign shape, on the lane the arguments name."""
    spec = normalize(args)
    return _worker(spec, spec.judge, "milestone-judge", "")


# ----------------------------------------------------------------------- build


def _worker(spec: Spec, lane: str, role: str, brief: str) -> WorkerSpec:
    tools = (ToolSurface(only=("terminal", "file_editor")) if lane == "pi"
             else ToolSurface())
    profile = "hermetic" if spec.profile and lane in HERMETIC_LANES else None
    return WorkerSpec(role=role, brief=brief, model=spec.models[lane],
                      lane=lane, tools=tools, max_iterations=spec.max_iter,
                      profile=profile)


def _step(spec: Spec, sid: str, lane: str, brief: str, *, worktree: str,
          owns: tuple[str, ...], checks: tuple[CheckSpec, ...], objective: str,
          depends_on: tuple[str, ...] = (), retry: RetryPolicy | None = None,
          schema: dict | None = ROLLCALL_SCHEMA, role: str | None = None) -> Step:
    return Step(id=sid, kind="worker", worktree=worktree, owns=owns,
                depends_on=depends_on, wall_timeout_s=spec.wall,
                stall_timeout_s=spec.stall_for(lane), schema=schema,
                objective=objective,
                retry=retry or RetryPolicy(),
                worker=_worker(spec, lane, role or f"rollcall-{lane}", brief),
                gate=GateSpec(checks=checks))


def _report_checks(owns: str, lane: str, *, since: str = "base",
                   extra: tuple[CheckSpec, ...] = ()) -> tuple[CheckSpec, ...]:
    return (clean_commit_checks((owns,), since=since, marker=PRESENT) +
            (CheckSpec("schema_valid"),
             CheckSpec("rollcall_matches", {"lane": lane})) + extra)


def _wt(spec: Spec, name: str) -> WorktreeSpec:
    return WorktreeSpec(name=name, path=spec.wt_root / name,
                        branch=f"{spec.prefix}-{name}", base=spec.base,
                        node_modules_mode="none")


def _solo(spec: Spec, lane: str, sid: str, *, more: str = "",
          extra: tuple[CheckSpec, ...] = (), since: str = "base",
          retry: RetryPolicy | None = None, brief: str | None = None) -> Step:
    owns = f"rollcall/{sid}.md"
    brief = brief if brief is not None else SOLO_BRIEF.format(
        lane=lane, sid=sid, entry=ENTRY, clean=CLEAN, more=more)
    return _step(spec, sid, lane, brief, worktree=sid, owns=(owns,),
                 checks=_report_checks(owns, lane, since=since, extra=extra),
                 objective=f"{sid} reports for duty in {owns}", retry=retry)


def _fanout_phase(spec: Spec) -> Phase:
    return Phase(name="Report", on_step_failure="continue", min_success="any",
                 steps=tuple(_solo(spec, lane, sid)
                             for lane, sid in spec.workers))


def _single(spec: Spec):
    lane, sid = spec.workers[0]
    return ([_wt(spec, sid)],
            [Phase(name="Report", steps=(_solo(spec, lane, sid),))])


def _fanout(spec: Spec):
    return [_wt(spec, sid) for _, sid in spec.workers], [_fanout_phase(spec)]


def _relay(spec: Spec):
    total = len(spec.workers)
    phases, previous_id = [], None
    for n, (lane, sid) in enumerate(spec.workers, start=1):
        create = ("It does not exist yet: create it, with the first line "
                  "`# Roll call`." if n == 1 else
                  "It exists; earlier workers wrote their sections.")
        previous = ("none" if n == 1 else
                    "the harness name from the section directly above yours")
        brief = RELAY_BRIEF.format(lane=lane, sid=sid, n=n, total=total,
                                   create=create, entry=ENTRY,
                                   previous=previous, clean=CLEAN)
        extra = (
            CheckSpec("command_exit", {
                "cmd": f"test \"$(grep -c '^## ' ROLLCALL.md)\" -eq {n}"}),
            CheckSpec("command_exit", {
                "cmd": (f"git diff --numstat {spec.base}..HEAD | "
                        "awk '$2 != 0 && $2 != \"-\" {bad=1} END {exit bad}'")}),
            CheckSpec("command_exit", {
                "cmd": ("tail -n +$(grep -n '^## ' ROLLCALL.md | tail -1 | "
                        "cut -d: -f1) ROLLCALL.md | grep -q 'Previous: '")}),
        )
        step = _step(
            spec, sid, lane, brief, worktree="relay", owns=("ROLLCALL.md",),
            depends_on=(previous_id,) if previous_id else (),
            checks=_report_checks("ROLLCALL.md", lane, since="step_start",
                                  extra=extra),
            objective=f"{sid} appends its section to the shared ROLLCALL.md")
        phases.append(Phase(name=f"Relay {n} {sid}", steps=(step,)))
        previous_id = sid
    return [_wt(spec, "relay")], phases


def _merge(spec: Spec):
    ids = [sid for _, sid in spec.workers]
    worktrees = [_wt(spec, sid) for sid in ids] + [_wt(spec, "integration")]
    merges = Phase(name="Merge", on_step_failure="continue", min_success="any",
                   steps=tuple(Step(
                       id=f"merge-{sid}", kind="merge", worktree="integration",
                       depends_on=(sid,), merge_branch=f"{spec.prefix}-{sid}",
                       merge_message=f"rollcall: merge {sid}") for sid in ids))
    rows = tuple(CheckSpec("command_exit", {
        "cmd": f"grep -qE '^[|] *{sid} *[|]' ROLLCALL.md"}) for sid in ids)
    count = CheckSpec("command_exit", {"cmd": (
        f"test \"$(grep -cE '^[|] *({'|'.join(ids)}) *[|]' ROLLCALL.md)\" "
        f"-eq {len(ids)}")})
    brief = CONSOLIDATE_BRIEF.format(count=len(ids), ids=", ".join(ids),
                                     lane=spec.consolidator, clean=CLEAN)
    consolidate = Phase(name="Consolidate", steps=(_step(
        spec, "consolidate", spec.consolidator, brief, worktree="integration",
        owns=("ROLLCALL.md",),
        depends_on=tuple(f"merge-{sid}" for sid in ids),
        checks=_report_checks("ROLLCALL.md", spec.consolidator,
                              since="last_merge", extra=rows + (count,)),
        objective=(f"{spec.consolidator} writes ROLLCALL.md as one table, "
                   f"one row per worker"),
        role="rollcall-consolidate"),))
    return worktrees, [_fanout_phase(spec), merges, consolidate]


def _retry(spec: Spec):
    lane, sid = spec.workers[0]
    owns = f"rollcall/{sid}.md"
    wanted = CheckSpec("file_contains", {"path": owns, "text": RETRY_TOKEN,
                                         "hidden": True})
    step = _solo(
        spec, lane, sid, more=RETRY_MORE, since="step_start", extra=(wanted,),
        retry=RetryPolicy(max=1, on=("gate:file_contains",),
                          carry_context=spec.carry_context))
    return [_wt(spec, sid)], [Phase(name="Report", steps=(step,))]


def _review(spec: Spec):
    lane, sid = spec.workers[0]
    worker = Phase(name="Report", steps=(_solo(spec, lane, sid),))
    gate = (CheckSpec("tree_clean"),
            CheckSpec("ownership", {"allowed": [], "since": "step_start"}),
            CheckSpec("no_ai_attribution", {"since": "step_start"}),
            CheckSpec("final_message_matches", {"regex": VERDICT}))
    reviewer = _step(
        spec, "reviewer", spec.reviewer, REVIEW_BRIEF.format(sid=sid),
        worktree=sid, owns=(), depends_on=(sid,), checks=gate, schema=None,
        objective=f"{spec.reviewer} reviews rollcall/{sid}.md and ends with a VERDICT line",
        role="rollcall-reviewer")
    return [_wt(spec, sid)], [worker, Phase(name="Review", steps=(reviewer,))]


def first_brief(spec: Spec) -> str:
    """The campaign shape's first brief. It omits the required line."""
    lane, sid = spec.workers[0]
**toolResult** for `call_70a65b5dd75e4a8ba7b89599` (bash)

#### [21] line 21 · message · assistant · 2026-10-01T22:42:00.592Z
<details><summary>thinking</summary>

I see `_solo`, `_relay`, `_merge` all pass lane. `_review` reviewer step doesn't use `rollcall_matches` (it has its own gate with VERDICT regex), fine. `_retry` uses `_solo`. `_campaign` — let me read the rest, and also check `build_milestone`.

</details>
**toolCall bash** id=`call_dfb98dfab9964f03b3798ae8`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && sed -n 560,700p oh-dispatch/scripts/ohflow/plans/rollcall.py"
}
```
**toolCall bash** id=`call_09bfd99a4c7746d1840235de`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && grep -rn \"rollcall_matches\" oh-dispatch/scripts/ohflow/ | grep -v \".pyc\""
}
```

#### [22] line 22 · message · toolResult · 2026-10-01T22:42:00.702Z
    lane, sid = spec.workers[0]
    return SOLO_BRIEF.format(lane=lane, sid=sid, entry=ENTRY, clean=CLEAN,
                             more="")


def _campaign(spec: Spec, brief: str):
    lane, sid = spec.workers[0]
    owns = f"rollcall/{sid}.md"
    wanted = CheckSpec("file_contains", {"path": owns, "text": CAMPAIGN_LINE,
                                         "hidden": True})
    step = _solo(spec, lane, sid, extra=(wanted,), brief=brief)
    return [_wt(spec, sid)], [Phase(name="Report", steps=(step,))]


def _plan(spec: Spec, args, name: str, worktrees, phases) -> Plan:
    return Plan(name=name, repo=spec.repo, base_branch=spec.base,
                baseline_cmd=None, max_parallel=spec.max_parallel,
                args=dict(args), worktrees=tuple(worktrees),
                phases=tuple(phases))


_BUILDERS = {"single": _single, "fanout": _fanout, "relay": _relay,
             "merge": _merge, "retry": _retry, "review": _review}


def build(args) -> Plan:
    spec = normalize(args)
    if spec.kind == "campaign":
        worktrees, phases = _campaign(spec, first_brief(spec))
    else:
        worktrees, phases = _BUILDERS[spec.kind](spec)
    return _plan(spec, args, f"rollcall-{spec.shape}", worktrees, phases)


def build_milestone(args, brief: str) -> Plan:
    """The product plan of the campaign shape, with the brief a file holds."""
    spec = normalize({**dict(args), "shape": "campaign"})
    worktrees, phases = _campaign(spec, brief)
    return _plan(spec, args, "rollcall-campaign", worktrees, phases)


def campaign_files(args) -> dict[str, str]:
    """The files of the one-milestone campaign repository, by relative path."""
    spec = normalize({**dict(args), "shape": "campaign"})
    _lane, sid = spec.workers[0]
    return {
        "charter.md": CHARTER,
        "milestones/m1/spec.md": MILESTONE_SPEC.format(sid=sid),
        "milestones/m1/plan.py": MILESTONE_PLAN,
        "milestones/m1/briefs/impl.md": first_brief(spec),
    }


def lands_branch(args) -> str:
    """The branch the campaign shape's worker leaves its work on."""
    spec = normalize({**dict(args), "shape": "campaign"})
    return f"{spec.prefix}-{spec.workers[0][1]}"
**toolResult** for `call_dfb98dfab9964f03b3798ae8` (bash)

#### [23] line 23 · message · toolResult · 2026-10-01T22:42:00.703Z
oh-dispatch/scripts/ohflow/gates.py:541:@register("rollcall_matches",
oh-dispatch/scripts/ohflow/gates.py:546:def rollcall_matches(ctx: GateContext, surface: list[str] | None = None,
oh-dispatch/scripts/ohflow/gates.py:563:        return GateResult("rollcall_matches", False, observed=f"no result.json: {e}",
oh-dispatch/scripts/ohflow/gates.py:567:        return GateResult("rollcall_matches", False, observed="no structured report",
oh-dispatch/scripts/ohflow/gates.py:601:    return GateResult("rollcall_matches", not problems, observed=observed,
oh-dispatch/scripts/ohflow/plans/rollcall.py:4:The lane records what the harness announced, and `rollcall_matches` fails a
oh-dispatch/scripts/ohflow/plans/rollcall.py:435:             CheckSpec("rollcall_matches", {"lane": lane})) + extra)
**toolResult** for `call_09bfd99a4c7746d1840235de` (bash)

#### [24] line 24 · message · assistant · 2026-10-01T22:42:06.162Z
<details><summary>thinking</summary>

Every `rollcall_matches` check site in the plan goes through `_report_checks`, which now passes `{"lane": lane}`. All shapes use `_solo` (which passes lane) or `_relay`/`_merge` (both pass lane). Good.

But wait — the schema: `ROLLCALL_SCHEMA` requires `lane` field? Let me check the schema. The report format includes `"lane": "{lane}"` in REPORT. Let me check the schema file to see if `lane` is required. If `schema_valid` requires `lane`, then a report missing `lane` fails schema too. The test `test_report_lane_missing_fails_when_the_step_names_one` — fine either way.

Now, one potential issue with the gate change: the `lane` comparison is `report.get("lane") != lane`. The report format instructs the worker to fill `"lane": "{lane}"` where {lane} is filled by the brief — SOLO_BRIEF's REPORT includes `{{"lane": "{lane}", ...}}` formatted with the lane. RELAY_BRIEF too. CONSOLIDATE_BRIEF too (uses REPORT). Good — the worker knows its lane from the brief.

Now, does the brief's lane always match the step's lane? Yes, `_worker(spec, lane, ...)` and brief format use the same lane variable.

Next: check `gates.py` around line 541-601 for the full context of the new check, and how `CheckSpec` args are passed (kwargs).

</details>
**toolCall bash** id=`call_b12e744ebcbb4196ba77439a`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && sed -n 530,610p oh-dispatch/scripts/ohflow/gates.py"
}
```
**toolCall bash** id=`call_108812c636914ce1a7ed7905`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && grep -rn \"dict(os.environ)\\|os.environ.copy()\\|environ=dict\\|env=dict(os\" oh-dispatch/scripts/ohflow/ | grep -v \".pyc\""
}
```

#### [25] line 25 · message · toolResult · 2026-10-01T22:42:06.270Z
    return GateResult("schema_valid", not errs, observed=errs or "valid",
                      expected="no validation errors",
                      detail="; ".join(errs) if errs else None)


def _surface_name(name: Any) -> str:
    """One spelling per server. Codex shows `brave-search` as `brave_search`,
    and Claude shows the connector `claude.ai Gmail` as `claude_ai_Gmail`."""
    return re.sub(r"[^a-z0-9]", "_", str(name).strip().lower())


@register("rollcall_matches",
          lambda a: "every tool and MCP server the worker reports was announced "
                    "by its harness" + (" and is inside the plan surface"
                                        if a.get("surface") else "") +
                    (f"; the report names lane {a['lane']}" if a.get("lane") else ""))
def rollcall_matches(ctx: GateContext, surface: list[str] | None = None,
                     lane: str | None = None) -> GateResult:
    """The worker's report of its own surface against the harness's record.

    The lane writes what the harness announced into `result.json`: `tools`
    and `mcp_servers`. The worker reports `tools` and `mcp_servers` in its
    structured final message. A reported name the harness never announced
    fails the check, and so does one outside `surface` when the plan gives
    one (a hermetic worker). A lane that announces no tool list (codex) has
    its tools unchecked, and the observed record says so. When the plan gives
    `lane`, the report's own `lane` field must equal it.
    """
    result_path = ctx.step_dir / "result.json"
    evidence = str(result_path) if result_path.exists() else None
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return GateResult("rollcall_matches", False, observed=f"no result.json: {e}",
                          expected="the lane's announced surface")
    report = ctx.structured
    if not isinstance(report, dict):
        return GateResult("rollcall_matches", False, observed="no structured report",
                          expected="a report with tools and mcp_servers",
                          evidence_path=evidence)
    announced_tools = {_surface_name(t) for t in result.get("tools") or []}
    announced_servers = {_surface_name(s) for s in result.get("mcp_servers") or []}
    reported_tools = [t for t in report.get("tools") or [] if isinstance(t, str)]
    # A worker may name a server by its tool prefix: Codex spells a plugin tool
    # `mcp__cua_repl.js`, and a worker then reports `mcp__cua_repl`.
    reported_servers = [re.sub(r"^mcp__", "", s) for s in report.get("mcp_servers") or []
                        if isinstance(s, str)]
    problems: list[str] = []
    if lane is not None and report.get("lane") != lane:
        problems.append(f"report names lane {report.get('lane')!r}, "
                        f"the step runs on lane {lane!r}")
    if announced_tools:
        extra = [t for t in reported_tools if _surface_name(t) not in announced_tools]
        if extra:
            problems.append(f"tools the harness did not announce: {extra}")
    extra = [s for s in reported_servers if _surface_name(s) not in announced_servers]
    if extra:
        problems.append(f"MCP servers the harness did not announce: {extra}")
    if surface is not None:
        allowed = {_surface_name(t) for t in surface}
        outside = [t for t in reported_tools if _surface_name(t) not in allowed]
        if outside:
            problems.append(f"tools outside the plan surface: {outside}")
        servers = [s for s in reported_servers if _surface_name(s) not in allowed]
        if servers:
            problems.append(f"MCP servers outside the plan surface: {servers}")
    observed = {"reported_tools": len(reported_tools),
                "reported_servers": len(reported_servers),
                "announced_tools": len(announced_tools) if announced_tools
                else "none announced; tools unchecked",
                "announced_servers": len(announced_servers)}
    return GateResult("rollcall_matches", not problems, observed=observed,
                      expected="reported surface is a subset of the announced one",
                      evidence_path=evidence,
                      detail="; ".join(problems) if problems else None)


# --------------------------------------------------------------- conjunction


def run_gate(ctx: GateContext, gate) -> GateReport:
**toolResult** for `call_b12e744ebcbb4196ba77439a` (bash)

#### [26] line 26 · message · toolResult · 2026-10-01T22:42:06.275Z
oh-dispatch/scripts/ohflow/cli.py:342:        env = dict(os.environ)
oh-dispatch/scripts/ohflow/cli.py:787:        env = dict(os.environ)
oh-dispatch/scripts/ohflow/exec.py:81:    child_env = dict(os.environ)
**toolResult** for `call_108812c636914ce1a7ed7905` (bash)

#### [27] line 27 · message · assistant · 2026-10-01T22:42:11.262Z
<details><summary>thinking</summary>

Three places still do `dict(os.environ)`:
- `cli.py:342`
- `cli.py:787`
- `exec.py:81`

I need to check whether these build environments for *workers* (children that are agent seats) or for internal helper processes (e.g., git commands, detached run supervisors — those aren't workers and inheriting CLAUDE* is fine, or even desired).

Let me look at each.

</details>
Three `dict(os.environ)` sites remain. Let me check whether they launch workers or internal helpers.
**toolCall bash** id=`call_bde458fbc4a04b278c43599d`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && sed -n 320,370p oh-dispatch/scripts/ohflow/cli.py && echo ===== && sed -n 770,810p oh-dispatch/scripts/ohflow/cli.py && echo ===== && sed -n 60,110p oh-dispatch/scripts/ohflow/exec.py"
}
```

#### [28] line 28 · message · toolResult · 2026-10-01T22:42:11.425Z
        if ns.auto_resume is not None:
            argv += ["--auto-resume", str(ns.auto_resume)]
        for a in ns.args or []:
            argv += ["--args", a]
        if ns.only_phase:
            argv += ["--only-phase", ns.only_phase]
        if predictions is not None:
            argv += ["--predictions", str(Path(ns.predictions).resolve())]
        # The dashboard lives in the supervisor, which is the child: this
        # launcher returns in a second. Its URL lands in supervisor.log and in
        # dashboard.json.
        if getattr(ns, "no_dashboard", False):
            argv += ["--no-dashboard"]
        if getattr(ns, "dashboard_port", None) is not None:
            argv += ["--dashboard-port", str(ns.dashboard_port)]
        if getattr(ns, "open_dashboard", False):
            argv += ["--open-dashboard"]
        if ns.resume:
            # The child resolves out_root/run_id, which is the directory this
            # process already chose. Without --run-id the child minted a second
            # id of its own and could land in a different directory.
            argv += ["--resume", run_id]
        env = dict(os.environ)
        env["PYTHONPATH"] = str(IMPORT_ROOT) + os.pathsep + \
            env.get("PYTHONPATH", "")
        # The detached supervisor's stdout is a file, not a console, so Python
        # picks the ANSI code page for it unless it is told otherwise. cp1252
        # cannot carry a box-drawing character, and the write then raises
        # inside the thread that is logging. Name the encoding for the child.
        env["PYTHONIOENCODING"] = "utf-8:replace"
        log_path = run_dir / "supervisor.log"
        try:
            launched_proc = detach.launch(argv, cwd=IMPORT_ROOT, env=env,
                                          log_path=log_path)
        except detach.DetachFailed as error:
            # The reservation belongs only to this failed launch. Remove it so
            # the operator can run the same id from a safe launcher.
            if handoff_token:
                [redacted] path in (run_dir / ".ohflow-handoff.json", log_path):
                    path.unlink(missing_ok=True)
                try:
                    run_dir.rmdir()
                except OSError:
                    pass
            print(error, file=sys.stderr)
            return EXIT_FAIL
        (run_dir / "supervisor.pid").write_text(str(launched_proc.pid),
                                                encoding="utf-8")
        launched = {"run_dir": str(run_dir), "pid": launched_proc.pid,
                    "route": launched_proc.route, "log": str(log_path)}
        no_dash = getattr(ns, "no_dashboard", False)
=====
        ohcamp.grant(camp, ns.milestone, ns.revisions)
        print(f"granted {ns.revisions} revision(s) to {ns.milestone}")
        return EXIT_OK
    if ns.campaign_cmd == "watch":
        result = ohwatch.watch_campaign(camp, timeout=ns.timeout,
                                        cursor=ns.cursor, poll=ns.poll)
        _emit(ns, result.lines, result.data)
        return result.code
    # run
    if ns.detach:
        root = Path(camp.root)
        argv = [sys.executable, "-m", "ohflow.cli", "campaign", "run",
                "--campaign", str(Path(ns.campaign).resolve())]
        for a in ns.args or []:
            argv += ["--args", a]
        if ns.no_dashboard:
            argv += ["--no-dashboard"]
        env = dict(os.environ)
        env["PYTHONPATH"] = str(IMPORT_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        env["PYTHONIOENCODING"] = "utf-8:replace"
        log = root / "campaign.log"
        try:
            launched_proc = detach.launch(argv, cwd=IMPORT_ROOT, env=env,
                                          log_path=log, append=True)
        except detach.DetachFailed as error:
            print(error, file=sys.stderr)
            return EXIT_FAIL
        (root / "campaign.pid").write_text(str(launched_proc.pid),
                                           encoding="utf-8")
        print(json.dumps({"campaign": camp.name, "pid": launched_proc.pid,
                          "route": launched_proc.route, "log": str(log),
                          "status": str(root / ohcamp.STATUS)}, indent=2))
        return EXIT_OK
    return ohcamp.CampaignDriver(camp, no_dashboard=ns.no_dashboard,
                                lanes=getattr(ns, "lanes", None)).run()


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="ohflow",
                                 description="fan-out orchestrator for the "
                                             "OpenHands worker pool")
=====
        env: Mapping[str, str] | None = None) -> Completed:
    """Run one command string in a named shell.

    `sh` is Git Bash and receives a POSIX-rendered working directory.
    `cmd` is cmd.exe and receives a backslash-rendered one.
    """
    cwd = Path(cwd)
    t0 = time.time()
    if shell == "sh":
        argv = [bash_exe(), "-lc", cmd]
    elif shell == "cmd":
        argv = ["cmd", "/c", cmd]
    else:
        raise ValueError(f"unknown shell {shell!r}; use 'sh' or 'cmd'")

    # cmd.exe gets the raw string, wrapped the way `shell=True` wraps it.
    # Passing the same string as one argv element makes Python quote it, and
    # cmd.exe then sees escaped quotes it cannot parse -- that is what broke
    # `mklink /J "a" "b"`.
    target = (f'{os.environ.get("COMSPEC", "cmd.exe")} /c "{cmd}"'
              if shell == "cmd" else argv)
    child_env = dict(os.environ)
    if env:
        child_env.update({str(k): str(v) for k, v in env.items()})

    # The child writes straight to its log files, so no pipe stays open for a
    # grandchild to hold, and a timeout can end the whole job.
    scratch = None
    if log_dir is None:
        scratch = tempfile.TemporaryDirectory(prefix="ohflow-exec-")
        files_dir = Path(scratch.name)
    else:
        files_dir = Path(log_dir)
        files_dir.mkdir(parents=True, exist_ok=True)
    stem = _slugify(name or cmd)
    op = files_dir / f"{stem}.out.log"
    ep = files_dir / f"{stem}.err.log"
    timed_out = False
    try:
        with op.open("wb") as out_file, ep.open("wb") as err_file:
            managed = proc.spawn_managed(target, cwd=cwd, env=child_env,
                                         stdin=subprocess.DEVNULL,
                                         stdout=out_file, stderr=err_file)
            try:
                rc = managed.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                rc = 124
                managed.kill_tree()
            finally:
                managed.close()
**toolResult** for `call_bde458fbc4a04b278c43599d` (bash)

#### [29] line 29 · message · assistant · 2026-10-01T22:42:18.996Z
<details><summary>thinking</summary>

These three sites:

1. `cli.py:342` — detached supervisor launcher (`ohflow run` detached). This is the *ohflow supervisor itself*, not a worker. The supervisor later spawns workers through the lanes, which strip the vars at the lane seam. So the supervisor inheriting CLAUDE* is fine — the lanes strip them. Indeed the m5 exit check ran under a WMI-started driver with none of those vars, and the defect was at the lane seam, now fixed at `worker_env`/`seat_env`. But wait — is there any path where the supervisor itself passes its environment directly to a worker bypassing the lanes? The workers are launched via lanes only. OK.

2. `cli.py:787` — campaign detached launcher, same reasoning.

3. `exec.py:81` — `run_command` helper for command_exit gates, baseline commands, merge steps etc. Those are shell commands run by the engine (git, grep), not agent workers. A gate command seeing CLAUDE* is harmless — spec says "One rule removes the launching session's variables from every worker, on every lane". Gate commands aren't workers. Also WMI route: `detach.launch` via WMI? The supervisor... fine.

Hmm, but wait — one more: `exec.py` runs `bash -lc` — login shell reads ~/.bash_profile; irrelevant.

Now, are there other places that build environments for workers? Let me grep for `seat_env(`, `worker_env(`, `spawn_managed(`, `Popen(`, `CreateProcess`, ` subprocess.run`:

Also check `host_runner` or whatever the host lane uses (worker.py HostLane.launch — covered), `dsh_runner`, `codex_runner` use seat_env (claude_runner does; codex/dsh?). Let me grep seat_env usage.

</details>
The three remaining sites launch the ohflow supervisor itself or gate commands, not workers — workers strip at the lane seam. Let me verify every lane's launch path uses the stripped env.
**toolCall bash** id=`call_70b41a5758cd4a00b774e2bc`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && grep -rn \"seat_env\\|worker_env\\|spawn_managed(\\|subprocess.Popen\\|\\.run(\\|create_env\\|env=\" oh-dispatch/scripts/ohflow/codex_runner.py oh-dispatch/scripts/ohflow/dsh_runner.py oh-dispatch/scripts/ohflow/host_runner.py 2>/dev/null | head -40"
}
```
**toolCall bash** id=`call_9e056a1342d3401a8069be98`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && ls oh-dispatch/scripts/ohflow/ && grep -rn \"seat_env\" oh-dispatch/scripts/ohflow/*.py | grep -v \".pyc\""
}
```

#### [30] line 30 · message · toolResult · 2026-10-01T22:42:19.205Z
oh-dispatch/scripts/ohflow/codex_runner.py:28:                          runner_main, seat_activity, seat_env, seat_trace,
oh-dispatch/scripts/ohflow/codex_runner.py:313:                                  cwd=Path(str(spec["workspace"])), env=seat_env(extra),
oh-dispatch/scripts/ohflow/dsh_runner.py:36:                          runner_main, seat_activity, seat_env, seat_trace,
oh-dispatch/scripts/ohflow/dsh_runner.py:352:                                  env=seat_env(), context={"started": time.time()})
oh-dispatch/scripts/ohflow/host_runner.py:362:        conv.run()
**toolResult** for `call_70b41a5758cd4a00b774e2bc` (bash)

#### [31] line 31 · message · toolResult · 2026-10-01T22:42:19.211Z
__init__.py
activity.py
attempt_record.py
campaign.py
claude_runner.py
cli.py
cli_lane.py
codex_runner.py
console.py
coords.py
dashboard.html
dashboard.py
detach.py
dsh_runner.py
dsh_worker.patch.yml
engine.py
exec.py
exit_report.py
failure.py
fingerprint.py
gates.py
host_artifacts.py
host_runner.py
journal.py
lanes.py
ledger.py
legacy.py
live.py
ohflow-guard.ts
paths.py
pi_runner.py
pi_surface.py
plan.py
plans
preflight.py
prices.json
pricing.py
proc.py
report.py
retrodraft.py
retry.py
rollcall.py
run_notes
rundir.py
runnotes.py
runstatus.py
seat_runner.py
structured.py
summary_audit.py
supervisor.py
table.py
watch.py
worker.py
worktree.py
oh-dispatch/scripts/ohflow/claude_runner.py:23:                          run_quiet, runner_main, seat_activity, seat_env,
oh-dispatch/scripts/ohflow/claude_runner.py:336:            env=seat_env(HERMETIC_ENV if hermetic else None),
oh-dispatch/scripts/ohflow/codex_runner.py:28:                          runner_main, seat_activity, seat_env, seat_trace,
oh-dispatch/scripts/ohflow/codex_runner.py:313:                                  cwd=Path(str(spec["workspace"])), env=seat_env(extra),
oh-dispatch/scripts/ohflow/dsh_runner.py:36:                          runner_main, seat_activity, seat_env, seat_trace,
oh-dispatch/scripts/ohflow/dsh_runner.py:352:                                  env=seat_env(), context={"started": time.time()})
oh-dispatch/scripts/ohflow/seat_runner.py:39:def seat_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
oh-dispatch/scripts/ohflow/seat_runner.py:104:                            env=dict(env) if env is not None else seat_env())
**toolResult** for `call_9e056a1342d3401a8069be98` (bash)

#### [32] line 32 · message · assistant · 2026-10-01T22:42:27.275Z
<details><summary>thinking</summary>

All CLI adapters (claude, codex, dsh) use `seat_env` (which calls `proc.worker_env()`), pi uses `proc.worker_env()` directly, and host + cli lanes use `worker_env()` at `spawn_managed`. There's a `rollcall.py` at scripts/ohflow (module) — that's the matrix runner. Let me check if `ohflow/rollcall.py` builds any environment for workers... it drives `ohflow.cli run` presumably via subprocess. Since it launches ohflow (the supervisor), not workers directly, and the lanes strip, it's fine. But let me check how the matrix runner launches cells — if it spawns `python -m ohflow.cli` detached with `dict(os.environ)`, the supervisor inherits CLAUDE*, but the lanes strip. OK.

Wait, but there's also `seat_runner.py:104`: `env=dict(env) if env is not None else seat_env()` — what's that? Let me look at seat_runner around line 90-120 — probably spawning a hook or something with explicit env. If `env` is passed explicitly by a caller, it's the caller's choice. Let me check.

Also the `host_runner.py` — host lane's worker process. HostLane.launch in worker.py uses worker_env. host_runner.py is the *worker-side* module (runs inside the worker). It might spawn OpenHands... Actually host lane: `worker.py` HostLane launches `python -m ohflow.host_runner` (the runner process), which then starts OpenHands in-process or as a child. Let me check host_runner for any child env building.

</details>
**toolCall bash** id=`call_a6c1c8d301f349e19126312a`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && sed -n 85,120p oh-dispatch/scripts/ohflow/seat_runner.py"
}
```
**toolCall bash** id=`call_806cdc4d23c846e8bb6754e9`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && grep -rn \"os.environ\\|Popen\\|spawn\" oh-dispatch/scripts/ohflow/host_runner.py | head -30"
}
```

#### [33] line 33 · message · toolResult · 2026-10-01T22:42:27.337Z
    found = shutil.which(f"{shim_name}.cmd")
    if found:
        resolved = _shim_target(Path(found))
        if resolved:
            return resolved
    if path_fallback:
        found = shutil.which(f"{shim_name}.cmd") or shutil.which(shim_name)
        if found:
            return [found]
    raise FileNotFoundError(f"{shim_name} executable not found; set {env_var}")


def is_fake(argv: list[str]) -> bool:
    return len(argv) == 2 and argv[1].lower().endswith(".py")


def run_quiet(argv: list[str], *, timeout: float = 30,
              env: Mapping[str, str] | None = None) -> subprocess.CompletedProcess:
    return proc.run_managed(argv, timeout=timeout,
                            env=dict(env) if env is not None else seat_env())


def version_of(argv: list[str], flag: str = "--version") -> str:
    if is_fake(argv):
        return "fake"
    try:
        out = run_quiet([*argv, flag], timeout=20).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return out.splitlines()[-1].strip() if out else "unknown"


def bootstrap_prompt(out_dir: Path) -> str:
    brief = (Path(out_dir) / "brief.md").resolve()
    return f"Your brief is at {brief}. Read it and follow it."
**toolResult** for `call_a6c1c8d301f349e19126312a` (bash)

#### [34] line 34 · message · toolResult · 2026-10-01T22:42:27.383Z
33:os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")
36:# `build_terminal_env` starts from `os.environ`. git starts a pager when it
42:os.environ.update(NO_PAGER_ENV)
64:    key = os.environ.get(var, "")
**toolResult** for `call_806cdc4d23c846e8bb6754e9` (bash)

#### [35] line 35 · message · assistant · 2026-10-01T22:42:32.968Z
<details><summary>thinking</summary>

`host_runner.py` — it runs *inside* the worker process (started by HostLane with the stripped env). It updates its own `os.environ` for OpenHands. That's fine since the process already started with a stripped env.

Now `run_quiet` with explicit env — who calls it with env? Probably codex/dsh version checks. Fine.

Next: check `pi_runner.prepare` more fully — what env does it build, and does anything re-add from os.environ afterwards? Let me view the prepare function fully. Also check `pi_surface.prewarm_mcp` — it takes `env`.

</details>
**toolCall bash** id=`call_3062c234aea74cbeaf2450af`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && sed -n 145,200p oh-dispatch/scripts/ohflow/pi_runner.py"
}
```
**toolCall bash** id=`call_d06517792f8d4c4fbfb7063b`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && grep -rn \"environ\" oh-dispatch/scripts/ohflow/pi_surface.py | head && grep -rn \"environ\" oh-dispatch/scripts/ohflow/cli_lane.py oh-dispatch/scripts/ohflow/worker.py | head -20"
}
```

#### [36] line 36 · message · toolResult · 2026-10-01T22:42:33.078Z
        spec_path, out_dir, fallback_error,
        event_log_name=EVENT_LOG, parser=json.loads, builder=_recover_pi,
    )


class PiAdapter:
    """Pi argv, event, usage and result semantics for the shared CLI runtime."""

    name = "pi"
    event_log_name = EVENT_LOG
    stderr_log_name = "pi-stderr.log"

    def prepare(self, spec: dict[str, Any], out_dir: Path) -> CliPreparedProcess:
        from .pi_surface import prepare_pi_surface, prewarm_mcp, write_pi_agent_dir

        (out_dir / "session").mkdir(parents=True, exist_ok=True)
        surface = prepare_pi_surface(spec, out_dir)
        agent_dir = write_pi_agent_dir(spec, out_dir)
        env = proc.worker_env()
        env["PI_CODING_AGENT_DIR"] = str(agent_dir)
        env["PI_OFFLINE"] = "1"
        env["OHFLOW_BASH"] = os.environ.get(
            "OHFLOW_BASH", r"C:\Program Files\Git\bin\bash.exe")
        env["OHFLOW_OWNS"] = json.dumps(list(spec.get("owns") or []))
        env["OHFLOW_WORKSPACE"] = str(spec.get("workspace") or "")
        command_cap = effective_command_cap(
            int(spec.get("wall_timeout_s") or 5400), spec.get("max_command_s"))
        env["OHFLOW_BASH_TIMEOUT_S"] = str(command_cap)
        env["OHFLOW_COMMAND_CAP_LOG"] = str(
            out_dir / "logs" / "command_caps.jsonl")
        env["OHFLOW_COMMAND_CAP_CONTEXT"] = json.dumps(
            {"coord": spec.get("coord"), "attempt": spec.get("attempt")})
        key_name = str((spec.get("model") or {}).get("api_key_env") or "")
        if key_name and not env.get(key_name):
            raise RuntimeError(f"{key_name} is empty or unset")
        provider = str((spec.get("model") or {}).get("model") or "").split("/", 1)[0]
        canonical_key = [redacted]"zai": "ZAI_API_KEY"}.get(provider)
        if canonical_key and key_name:
            env[canonical_key] = env[key_name]
        surface = prewarm_mcp(surface, env, out_dir)
        return CliPreparedProcess(
            argv=tuple(build_command(spec, out_dir, surface)),
            cwd=Path(str(spec["workspace"])),
            env=env,
            context={"surface": surface, "agent_dir": agent_dir},
        )

    def parse_event(self, line: str) -> Mapping[str, Any]:
        return json.loads(line)

    def on_event(self, spec: dict[str, Any], event: Mapping[str, Any],
                 events: list[Mapping[str, Any]]) -> CliEventAction:
        if (event.get("type") == "message_end" and
                (event.get("message") or {}).get("role") == "assistant" and
                len(_pi_messages(events)) >= int(spec.get("max_iterations") or 150) and
                (event.get("message") or {}).get("stopReason") in ("toolUse", "tool_use")):
**toolResult** for `call_3062c234aea74cbeaf2450af` (bash)

#### [37] line 37 · message · toolResult · 2026-10-01T22:42:33.078Z
69:    override = os.environ.get("OHFLOW_PI_MCP_ADAPTER")
oh-dispatch/scripts/ohflow/worker.py:72:    variable name, and only `host_runner.py` reads os.environ."""
oh-dispatch/scripts/ohflow/worker.py:126:    env = os.environ.get("OHFLOW_HOST_PYTHON")
**toolResult** for `call_d06517792f8d4c4fbfb7063b` (bash)

#### [38] line 38 · message · assistant · 2026-10-01T22:42:37.808Z
<details><summary>thinking</summary>

pi_runner's prepare looks right. `pi_surface.prewarm_mcp(surface, env, ...)` gets the stripped env. `pi_surface` line 69 reads OHFLOW_PI_MCP_ADAPTER from os.environ (a runner-side toggle, fine).

Now let me check the matrix runner `ohflow/rollcall.py` — how does it launch cells? And where does the rollcall put its scratch repo and worktrees (criterion 4 — I must not create anything inside my worktree).

</details>
**toolCall bash** id=`call_f6d86e3d60944878bba3de2a`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && grep -n \"def \\|os.environ\\|Popen\\|spawn\\|TemporaryDirectory\\|tempfile\\|scratch\" oh-dispatch/scripts/ohflow/rollcall.py | head -50"
}
```

#### [39] line 39 · message · toolResult · 2026-10-01T22:42:37.914Z
64:    def label(self) -> str:
69:    def plan_args(self) -> dict:
76:def _cell(shape: str, lanes, count: int = 1, **options) -> Cell:
101:def parse_cell(text: str) -> Cell:
122:def list_lines() -> list[str]:
146:    def line(self) -> str:
154:    def data(self) -> dict:
163:def _duration(seconds: float) -> str:
168:def _tokens(n: int) -> str:
172:def _short(text: str, limit: int = WHY_MAX) -> str:
177:def summary_line(results: list[CellResult]) -> tuple[str, int]:
193:def make_repo(path: Path, branch: str = "main") -> Path:
208:def _current_branch(repo: Path) -> str:
231:    def cell_dir(self, index: int, cell: Cell) -> Path:
236:    def plan_args(self, index: int, cell: Cell, cell_dir: Path) -> dict:
245:def _plan_module():
250:def _lanes_needed(args: dict) -> tuple[str, ...]:
254:def _lane_fault(ctx: Context, lane: str) -> str | None:
260:    if key and not os.environ.get(key):
273:def _first_failure(run_dir: Path) -> str:
296:def _run_tokens(run_dir: Path) -> int:
308:def _started(run_dir: Path) -> int:
317:def _check_resume(ctx: Context, plan, run_dir: Path, plan_args: dict) -> str:
333:def _stdout_to(stream):
338:def _run_cell(ctx: Context, index: int, cell: Cell) -> CellResult:
372:def _run_plan_cell(ctx: Context, result: CellResult, plan, args: dict,
397:def _all_passed(run_dir: Path) -> bool:
405:def _commit_all(path: Path, message: str) -> None:
410:def _run_campaign(ctx: Context, result: CellResult, args: dict, cdir: Path,
468:def _write_matrix(ctx: Context, name: str, results: list[CellResult],
477:def dry_run(cells: list[Cell], ctx: Context, say_line) -> int:
498:def run_matrix(*, matrix: str | None = None, cells: list[str] | None = None,
527:        os.environ.get("TEMP", ".")) / f"rollcall-{secrets.token_hex(3)}"
**toolResult** for `call_f6d86e3d60944878bba3de2a` (bash)

#### [40] line 40 · message · assistant · 2026-10-01T22:42:41.472Z
**toolCall bash** id=`call_941557ca8304423ebfff8e6b`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && sed -n 498,600p oh-dispatch/scripts/ohflow/rollcall.py"
}
```

#### [41] line 41 · message · toolResult · 2026-10-01T22:42:41.526Z
def run_matrix(*, matrix: str | None = None, cells: list[str] | None = None,
               repo: str | None = None, out: str | None = None,
               config: str | None = None, dry: bool = False,
               verbose: bool = False, lanes: Callable | None = None,
               write: Callable[[str], None] = say) -> int:
    """Run a matrix or a list of cells; print the verdicts through `write`."""
    if cells:
        try:
            chosen = [parse_cell(c) for c in cells]
        except ValueError as e:
            write(f"ROLLCALL INVALID: {e}")
            return EXIT_PLAN
        name = "cells"
    else:
        name = matrix or "quick"
        if name not in MATRICES:
            write(f"ROLLCALL INVALID: unknown matrix {name!r}; use one of "
                  f"{list(MATRICES)}")
            return EXIT_PLAN
        chosen = list(MATRICES[name])

    mod = _plan_module()
    try:
        config_name, models = mod.load_config(config)
    except ValueError as e:
        write(f"ROLLCALL INVALID: {e}")
        return EXIT_PLAN

    out_dir = Path(out).resolve() if out else Path(
        os.environ.get("TEMP", ".")) / f"rollcall-{secrets.token_hex(3)}"
    out_dir.mkdir(parents=True, exist_ok=True)
    if repo:
        repo_path = Path(repo).resolve()
    elif dry:
        repo_path = out_dir / "repo"          # named, never created
    else:
        repo_path = make_repo(out_dir / "repo")
    base = _current_branch(repo_path) if (repo_path / ".git").exists() else "main"
    ctx = Context(repo=repo_path, out=out_dir, base=base,
                  config=str(Path(config).resolve()) if config else "",
                  config_name=config_name, models=models,
                  tag=secrets.token_hex(2), verbose=verbose, lanes=lanes,
                  say=write)
    if dry:
        return dry_run(chosen, ctx, write)

    results: list[CellResult] = []
    for index, cell in enumerate(chosen, start=1):
        r = _run_cell(ctx, index, cell)
        results.append(r)
        _write_matrix(ctx, name, results, len(chosen))
        write(r.line())
    last, code = summary_line(results)
    write(last)
    return code
**toolResult** for `call_941557ca8304423ebfff8e6b` (bash)

#### [42] line 42 · message · assistant · 2026-10-01T22:42:48.355Z
<details><summary>thinking</summary>

The rollcall matrix makes its own throwaway repo under `%TEMP%/rollcall-XXXX/repo` and worktrees under that repo's parent. Cells run sequentially (`for index, cell in enumerate(chosen)`) — so criterion 4 runs 3 cells sequentially. single:host ~2 min, single:claude:hermetic ~1-2 min, relay with codex+600s stall... codex in relay could take up to several minutes. Total estimate: maybe 6-15 min. That might exceed a single tool call timeout of 600s... The bash tool default timeout — I can pass an explicit timeout parameter. Let me use 1800 s or 2400 s.

Now, `_run_cell` — how does it launch the run? Let me check `_run_plan_cell` — it probably calls `ohflow.cli` main in-process. The cells run in-process of my shell's python. That means the workers launched from my process — my process env is my shell env. For criterion 4, I must export CLAUDECODE=1 etc. before running. Good.

One question: does `--cells` need a git repo of the current tree? It makes a throwaway repo (make_repo) — a fresh repo with a commit, not the product repo. So no worktrees of the product repo. And wt_root defaults to repo.parent / f"{repo.name}-rollcall-wt" — under %TEMP%. Good, nothing inside my worktree.

Now let me check the matrix.json measured figures vs README. The evidence path:
`C:\Users\<user>\AppData\Local\Temp\claude\C--Users-user\bb0fac07-fb14-4ec9-82d9-33b3b7c2e4f4\scratchpad\matrix-full\matrix.json`

</details>
The matrix runner uses a throwaway repo under `%TEMP%` — nothing lands in my worktree. Now let me verify the README figures against the measured `matrix.json`.
**toolCall bash** id=`call_0cdb723364ff4863b01a0f93`

```json
{
 "command": "cat \"C:/Users/<user>/AppData/Local/Temp/claude/C--Users-user/bb0fac07-fb14-4ec9-82d9-33b3b7c2e4f4/scratchpad/matrix-full/matrix.json\" 2>/dev/null | head -100"
}
```

#### [43] line 43 · message · toolResult · 2026-10-01T22:42:48.463Z
{
  "matrix": "full",
  "configuration": "default",
  "repo": "C:\\Users\\<user>\\AppData\\Local\\Temp\\claude\\C--Users-user\\bb0fac07-fb14-4ec9-82d9-33b3b7c2e4f4\\scratchpad\\matrix-full\\repo",
  "out": "C:\\Users\\<user>\\AppData\\Local\\Temp\\claude\\C--Users-user\\bb0fac07-fb14-4ec9-82d9-33b3b7c2e4f4\\scratchpad\\matrix-full",
  "cells_total": 15,
  "cells": [
    {
      "index": 1,
      "label": "single pi count=1",
      "shape": "single",
      "lanes": [
        "pi"
      ],
      "count": 1,
      "options": {},
      "verdict": "PASS",
      "reason": "",
      "run_dir": "C:\\Users\\<user>\\AppData\\Local\\Temp\\claude\\C--Users-user\\bb0fac07-fb14-4ec9-82d9-33b3b7c2e4f4\\scratchpad\\matrix-full\\01-single-pi-1\\run",
      "seconds": 27.1,
      "tokens": 5761,
      "resume": "ok"
    },
    {
      "index": 2,
      "label": "single host count=1",
      "shape": "single",
      "lanes": [
        "host"
      ],
      "count": 1,
      "options": {},
      "verdict": "FAIL",
      "reason": "step host-1: gate rollcall_matches failed, observed {'announced_servers': 0, 'announced_tools': 5, 'reporte...",
      "run_dir": "C:\\Users\\<user>\\AppData\\Local\\Temp\\claude\\C--Users-user\\bb0fac07-fb14-4ec9-82d9-33b3b7c2e4f4\\scratchpad\\matrix-full\\02-single-host-1\\run",
      "seconds": 138.1,
      "tokens": 105322,
      "resume": ""
    },
    {
      "index": 3,
      "label": "single claude count=1",
      "shape": "single",
      "lanes": [
        "claude"
      ],
      "count": 1,
      "options": {},
      "verdict": "PASS",
      "reason": "",
      "run_dir": "C:\\Users\\<user>\\AppData\\Local\\Temp\\claude\\C--Users-user\\bb0fac07-fb14-4ec9-82d9-33b3b7c2e4f4\\scratchpad\\matrix-full\\03-single-claude-1\\run",
      "seconds": 92.7,
      "tokens": 271297,
      "resume": "ok"
    },
    {
      "index": 4,
      "label": "single codex count=1",
      "shape": "single",
      "lanes": [
        "codex"
      ],
      "count": 1,
      "options": {},
      "verdict": "PASS",
      "reason": "",
      "run_dir": "C:\\Users\\<user>\\AppData\\Local\\Temp\\claude\\C--Users-user\\bb0fac07-fb14-4ec9-82d9-33b3b7c2e4f4\\scratchpad\\matrix-full\\04-single-codex-1\\run",
      "seconds": 58.4,
      "tokens": 99946,
      "resume": "ok"
    },
    {
      "index": 5,
      "label": "single dsh count=1",
      "shape": "single",
      "lanes": [
        "dsh"
      ],
      "count": 1,
      "options": {},
      "verdict": "PASS",
      "reason": "",
      "run_dir": "C:\\Users\\<user>\\AppData\\Local\\Temp\\claude\\C--Users-user\\bb0fac07-fb14-4ec9-82d9-33b3b7c2e4f4\\scratchpad\\matrix-full\\05-single-dsh-1\\run",
      "seconds": 160.6,
      "tokens": 689030,
      "resume": "ok"
    },
    {
      "index": 6,
      "label": "fanout pi,claude,codex,dsh count=1",
      "shape": "fanout",
      "lanes": [
        "pi",
        "claude",
        "codex",
        "dsh"
      ],
      "count": 1,
      "options": {},
      "verdict": "PASS",
**toolResult** for `call_0cdb723364ff4863b01a0f93` (bash)

#### [44] line 44 · message · assistant · 2026-10-01T22:42:53.653Z
**toolCall bash** id=`call_280a390a29cc47ddb981dadf`

```json
{
 "command": "python -c \"\nimport json\np = r'C:/Users/<user>/AppData/Local/Temp/claude/C--Users-user/bb0fac07-fb14-4ec9-82d9-33b3b7c2e4f4/scratchpad/matrix-full/matrix.json'\nd = json.load(open(p))\nfull_total = sum(c['seconds'] for c in d['cells'])\nprint('cells:', len(d['cells']), 'full sum:', round(full_total,1))\nquick_labels = []\n# quick = 10 cells: single on all five lanes; fanout, relay, merge on pi,claude,codex,dsh; retry on pi; review on pi then claude\nfor c in d['cells']:\n    print(c['index'], c['label'], c['verdict'], c['seconds'])\n\""
}
```

#### [45] line 45 · message · toolResult · 2026-10-01T22:42:53.730Z
cells: 15 full sum: 1942.7
1 single pi count=1 PASS 27.1
2 single host count=1 FAIL 138.1
3 single claude count=1 PASS 92.7
4 single codex count=1 PASS 58.4
5 single dsh count=1 PASS 160.6
6 fanout pi,claude,codex,dsh count=1 PASS 196.9
7 relay pi,claude,codex,dsh count=1 FAIL 334.4
8 merge pi,claude,codex,dsh count=1 PASS 347.2
9 retry pi count=1 PASS 51.6
10 review pi,claude count=1 PASS 59.5
11 fanout pi count=3 PASS 41.8
12 campaign pi count=1 PASS 215.1
13 single claude count=1 profile=hermetic FAIL 37.4
14 single codex count=1 profile=hermetic PASS 42.3
15 retry claude count=1 carry_context PASS 139.6
**toolResult** for `call_280a390a29cc47ddb981dadf` (bash)

#### [46] line 46 · message · assistant · 2026-10-01T22:43:08.144Z
<details><summary>thinking</summary>

The full matrix sum: 1942.7 s → "32 m 23 s (1942.7 s)" ✓ (1942.7/60 = 32.378 min = 32 min 22.7 s → 32 m 23 s rounded ✓).

Quick = the first 10 cells: 27.1+138.1+92.7+58.4+160.6+196.9+334.4+347.2+51.6+59.5 = let me compute: 27.1+138.1=165.2; +92.7=257.9; +58.4=316.3; +160.6=476.9; +196.9=673.8; +334.4=1008.2; +347.2=1355.4; +51.6=1407.0; +59.5=1466.5. ✓ 1466.5 s = 24 m 26.5 s → README says "24 m 27 s (1466.5 s...)" ✓.

README says "2 of 10 cells failed before the m7 fixes" for quick (cells 2 and 7 — host and relay: yes 2 failures among the first 10) and "3 of 15 cells failed" for full (2, 7, 13: yes 3 failures). ✓

Hmm, one nit: the quick row's wall time (1466.5 s) is the sum of the quick cells as measured *inside* the full-matrix run, not a measured quick-matrix wall time. The spec says "Fill the 'Wall time' column of the `quick` and `full` rows from the measured `matrix.json` above". The matrix.json is from the full run; quick's figure derived from it. It says "first full matrix run on 2026-10-01". For the full row: 1942.7 s is also the sum of all 15 cell seconds — is that the actual wall time of the run, or the sum of per-cell seconds? Cells run sequentially (from run_matrix: `for index, cell in enumerate(chosen...)` — sequential), so the sum ≈ wall time minus inter-cell overhead. Reasonable. The README says "Wall time" — sum of cell seconds is a fair approximation and is what the spec asked ("from the measured matrix.json"). OK, matches.

Now the suite figure: "896 tests, 885 s on 2026-10-02" and shards "340.2 s, 282.9 s and 261.4 s on 2026-10-02". I'll verify by running the shards (needed anyway for the full suite exit criterion — the gate runs the full suite; as reviewer I run three shards). My run's numbers will differ slightly (different day/load) — that's fine, the README says "on 2026-10-02" — a dated measurement. But the test *count* must match 896; if my shard runs show a different count, the README figure is stale. Let me count: previous README said 875 tests; this milestone added tests: defect 44 (6 tests), defect 45 (3), defect 46 (5), defect 47 (3) = 17 new tests. 875 + 17 = 892? Hmm, that's 892, not 896. Wait — 875 + 17 = 892. README says 896. Let me count the new tests precisely:

test_defect_44: 6 test methods (claude, codex, dsh, pi, host, only-names) = 6
test_defect_45: 3 methods
test_defect_46: 5 methods
test_defect_47: 3 methods
Total = 17. 875+17 = 892 ≠ 896. Hmm. But maybe some existing test files gained tests? The diff only shows those changes. test_defect_07 changed bounds but no new tests. So 875 + 17 = 892. Unless the old figure 875 was already stale... The brief says "782 tests, 874 s on 2026-10-01" — wait! The campaign rules block says "The full suite now takes about fifteen minutes (782 tests, 874 s on 2026-10-01)". The old README (arch/deepening) said 875 tests 877 s on 2026-10-01. Hmm, discrepancy between the rules block (782) and the README (875)? The rules block may be older. Whatever — I'll count precisely by running the shards. If the shard run reports 892 tests and README says 896, that's a factual error in the README (prose is code). Let me check first by counting test methods, then confirm via shard runs.

Actually wait — maybe the implementer's shard run included some skipped/other tests. The run_tests.py may count differently (e.g., including subtests or class-level). Let me just run the shards and see the count.

Let me now run the fast exit criteria (1, 2, 3, 5) and count tests. Then run the three shards. Then criterion 4 (live cells).

Order matters for time: shards take ~5 min each (sequential, never parallel). Criterion 4 takes maybe 10-15 min. Total ~30 min. Fine.

First the quick checks.

</details>
README's full figure (1942.7 s) and quick figure (1466.5 s = sum of the first 10 cells) match `matrix.json`, and the failure counts (2/10, 3/15) check out. Now the fast exit criteria.
**toolCall bash** id=`call_cb215430af6d4545b2bc6c1e`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && python oh-dispatch/tests/run_tests.py -k parent_session 2>&1 | tail -5",
 "timeout": 300
}
```
**toolCall bash** id=`call_b520fb44bc9a403293304d50`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && python oh-dispatch/tests/run_tests.py -k hermetic 2>&1 | tail -5 && echo ===REPORT_LANE=== && python oh-dispatch/tests/run_tests.py -k report_lane 2>&1 | tail -5 && echo ===GREP=== && grep -n \"not measured yet\" oh-dispatch/README.md; echo \"grep exit: $?\"",
 "timeout": 300
}
```

#### [47] line 47 · message · toolResult · 2026-10-01T22:43:10.679Z
OK

summary schema checks: 0   unexpected rejections: 0
summary schema audit: this filtered selection produced no Engine summary
ran 6 tests in 0.0s   failures=0 errors=0 skipped=0
**toolResult** for `call_cb215430af6d4545b2bc6c1e` (bash)

#### [48] line 48 · message · toolResult · 2026-10-01T22:43:10.679Z
OK

summary schema checks: 0   unexpected rejections: 0
summary schema audit: this filtered selection produced no Engine summary
ran 10 tests in 1.0s   failures=0 errors=0 skipped=0
===REPORT_LANE===
OK

summary schema checks: 0   unexpected rejections: 0
summary schema audit: this filtered selection produced no Engine summary
ran 5 tests in 0.0s   failures=0 errors=0 skipped=0
===GREP===
grep exit: 1
**toolResult** for `call_b520fb44bc9a403293304d50` (bash)

#### [49] line 49 · message · assistant · 2026-10-01T22:43:29.013Z
<details><summary>thinking</summary>

Exit criteria 1, 2, 3, 5:
1. `-k parent_session`: 6 tests, exit 0. Spec requires ≥ 5 tests, one per lane. Defect 44 has 5 lane tests + 1 rule test. ✓ (The regex `^(CLAUDE|...)` matches all three names.)
2. `-k hermetic`: 10 tests ≥ 2 ✓ (includes older hermetic tests plus the 3 new).
3. `-k report_lane`: 5 tests ≥ 1, first test is "a report naming another lane fails the gate" ✓.
5. grep no match ✓.

Now let me count total tests to check the README's 896 figure before running shards. Actually the shard runs will tell me. Let me start shard 1.

But first — quick sanity on remaining review points:

a) Prove defect tests fail against old code. I can verify a couple cheaply: check out the base version of proc.py/pi_runner.py in a temp way? I shouldn't modify the worktree. I can use `git stash`-free approach: create a temp copy? Actually I can run the new tests against the old code by checking out the base into a separate directory via `git worktree`? That would add a worktree to the shared repo — changes .git of the main checkout. Risky per rules ("never change another branch" — adding a temp worktree doesn't change branches but writes into the shared .git/worktrees). Hmm. Alternative: `git show arch/deepening:oh-dispatch/scripts/ohflow/pi_runner.py` — copy whole tree? Too heavy.

Simpler: reason it out (already done — each defect test clearly fails against old code: pi/host/cli lanes used `dict(os.environ)` with CLAUDE* patched into os.environ → leak detected; hermetic env var didn't exist; gate lane kwarg didn't exist (TypeError = failure); codex stall was 180 < 600).

Actually, I could do a cheap in-memory check for defect 47 and 46 without touching files: import the old gate function? No — old function is gone. Skip; reasoning is solid and the charter's "prove red first" is the implementer's duty; the diff shows the shapes.

b) Check `seat_runner.py` unused import `re` after moving the regex. Let me check.

c) Check lanes.md claims about codex hermetic (CODEX_HOME + auth.json hard link) against codex_runner.

d) Check `--setting-sources project,local` is indeed in the hermetic claude command (build_command). Let me read claude_runner build_command.

e) Check pi lane "always hermetic" claim.

f) Check the schema — does ROLLCALL_SCHEMA require "lane"? If schema requires lane and the report omits it, schema_valid fails; test_report_lane_missing... consistent.

g) Vocabulary check in new prose (module/interface/... not component/service/API/boundary/layer). The new prose in lanes.md/README: "table", "rule", fine. No banned words? "launch rules" ok. Check for "boundary" etc. in the diff — I saw none.

h) Authorship: check commit messages for Co-Authored-By.

Let me do these checks now.

</details>
Criteria 1, 2, 3, 5 pass. Now the remaining static checks: unused import in `seat_runner`, the claude hermetic command, the codex hermetic claims in `lanes.md`, commit authorship, and the report schema.
**toolCall bash** id=`call_76de4a621bce4363812bfa41`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && grep -n \"^import\\|^from\\|re\\.\" oh-dispatch/scripts/ohflow/seat_runner.py | head -20 && echo ===== && grep -n \"setting-sources\\|strict-mcp-config\\|--tools\\|safe-mode\\|bare\" oh-dispatch/scripts/ohflow/claude_runner.py"
}
```
**toolCall bash** id=`call_4d5e2c9a4b39431c9564b88e`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && git log arch/deepening..HEAD --format=\"%h %an <%ae>%n---%B---\" | head -40 && grep -rn \"Co-Authored-By\\|Generated with\\|generated-with\" oh-dispatch/scripts/ohflow/proc.py oh-dispatch/scripts/ohflow/claude_runner.py oh-dispatch/scripts/ohflow/plans/rollcall.py oh-dispatch/references/lanes.md oh-dispatch/README.md; echo \"authorship grep exit: $?\""
}
```

#### [50] line 50 · message · toolResult · 2026-10-01T22:43:29.172Z
5:on `cli_lane.CliAgentRuntime`; this module holds what the three share.
17:from __future__ import annotations
19:import json
20:import os
21:import re
22:import shutil
23:import subprocess
24:import sys
25:import time
26:import warnings
27:from dataclasses import dataclass, field
28:from pathlib import Path
29:from typing import Any, Callable, Mapping
31:from . import activity as act
32:from . import attempt_record, proc
33:from .lanes import CAP_TOOLS_ONLY, lane_info, lanes_with
34:from .proc import guard_current_process_tree
52:    found = re.findall(r'"%dp0%\\([^"]+\.(?:exe|js|cjs|mjs))"', text)
224:        if not isinstance(profile, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", profile):
=====
37:# `--setting-sources project,local` drops the user's settings but not the
39:# `--mcp-config` servers and the login. `--safe-mode` drops the servers too;
40:# `--bare` needs an API key. Measured 2026-10-01 (2.1.281).
92:        command.extend(["--tools", ",".join(tools), "--strict-mcp-config",
93:                        "--mcp-config", str(mcp_path), "--setting-sources", "project,local"])
206:        structured, schema_error = parse_structured(final, schema, bare_ok=True)
**toolResult** for `call_76de4a621bce4363812bfa41` (bash)

#### [51] line 51 · message · toolResult · 2026-10-01T22:43:29.179Z
c9004e3 Example Operator <operator@example.com>
---oh-dispatch README: quick and full wall times from the first full matrix, suite figure from a three-shard run on this branch
---
bd76078 Example Operator <operator@example.com>
---oh-dispatch tests: the detached-run tests wait up to 60 s on every real-process step through one helper, because 10 s failed under suite load
---
52dbe58 Example Operator <operator@example.com>
---oh-dispatch roll call: the stall limit is per lane (codex 600 s) and the gate fails a report that names another lane than its step
---
139fac7 Example Operator <operator@example.com>
---oh-dispatch claude lane: profile=hermetic sets CLAUDE_CODE_DISABLE_CLAUDE_MDS so no instruction file loads; lanes.md says per lane what hermetic removes and keeps
---
18f4bcd Example Operator <operator@example.com>
---oh-dispatch: one worker_env rule strips the launching session's variables from every lane, so pi and host no longer inherit CLAUDE*, CLAUDECODE or ANTHROPIC_BASE_URL
---
oh-dispatch/scripts/ohflow/plans/rollcall.py:123:CLEAN = ("Author it clean: no `Co-Authored-By` line naming a model, no "
oh-dispatch/scripts/ohflow/plans/rollcall.py:124:         "generated-with footer.")
authorship grep exit: 0
**toolResult** for `call_4d5e2c9a4b39431c9564b88e` (bash)

#### [52] line 52 · message · assistant · 2026-10-01T22:43:33.012Z
<details><summary>thinking</summary>

- `re` is still used in seat_runner (lines 52, 224). No unused import.
- Hermetic claude command includes `--tools ... --strict-mcp-config --mcp-config ... --setting-sources project,local`. Wait — line 92-93: are these flags added only for hermetic? Let me look at build_command context to see when the hermetic branch applies. Let me read claude_runner.py build_command.
- Commit authorship clean (the only Co-Authored-By mentions are the roll-call brief text telling workers not to use it — pre-existing).

Let me read claude_runner.py lines 60-130 to see the hermetic branch.

</details>
**toolCall bash** id=`call_6b6c8c48703845a0af4bb12d`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && sed -n 44,130p oh-dispatch/scripts/ohflow/claude_runner.py"
}
```

#### [53] line 53 · message · toolResult · 2026-10-01T22:43:33.119Z
# another. Measured 2026-09-30 (2.1.281): init says `Task`, the model calls
# it `Agent`.
TOOL_ALIASES = {"Task": ("Agent",)}


def claude_argv() -> list[str]:
    return executable_argv("OHFLOW_CLAUDE_EXE", "claude")


def preflight() -> list[str]:
    """The seat must be signed in; a logged-out CLI fails every attempt."""
    try:
        argv = claude_argv()
    except FileNotFoundError as e:
        return [str(e)]
    try:
        out = run_quiet([*argv, "auth", "status"], timeout=30).stdout
        status = json.loads(out)
    except Exception as e:  # noqa: BLE001 - any failure is a preflight finding
        return [f"claude lane: `claude auth status` failed: {e}"]
    if not status.get("loggedIn"):
        return ["claude lane: the Claude CLI is not logged in; run `claude auth login`"]
    return []


def build_command(spec: Mapping[str, Any], out_dir: Path, session_id: str) -> list[str]:
    model = spec.get("model") or {}
    command = [*claude_argv(), "-p", "--output-format", "stream-json", "--verbose",
               "--permission-mode", "bypassPermissions"]
    if model.get("model"):
        command.extend(["--model", str(model["model"])])
    effort = (model.get("params") or {}).get("effort")
    if effort:
        command.extend(["--effort", str(effort)])
    fork = spec.get("fork_session")
    if fork:
        command.extend(["--resume", str(fork), "--fork-session", "--session-id", session_id])
    else:
        command.extend(["--session-id", session_id])
    if spec.get("schema_path"):
        schema = read_schema(spec, out_dir)
        command.extend(["--json-schema", json.dumps(schema, separators=(",", ":"))])
    if spec.get("profile") == "hermetic":
        only = list((spec.get("tools") or {}).get("only") or HERMETIC_DEFAULT)
        tools = [t for name in only for t in HERMETIC_TOOLS.get(name, ())]
        mcp_path = out_dir / "claude-mcp.json"
        mcp_path.write_text(json.dumps({"mcpServers": spec.get("mcp_config") or {}},
                                       indent=2), encoding="utf-8")
        command.extend(["--tools", ",".join(tools), "--strict-mcp-config",
                        "--mcp-config", str(mcp_path), "--setting-sources", "project,local"])
    command.append(bootstrap_prompt(out_dir))
    return command


def _init(events) -> Mapping[str, Any]:
    for e in events:
        if e.get("type") == "system" and e.get("subtype") == "init":
            return e
    return {}


def _result_event(events) -> Mapping[str, Any] | None:
    for e in reversed(events):
        if e.get("type") == "result":
            return e
    return None


def _assistant_messages(events) -> dict[str, list[Mapping[str, Any]]]:
    """Assistant events grouped by API message id. One API reply arrives as
    one event per content block, all carrying the same id and usage."""
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for e in events:
        if e.get("type") != "assistant":
            continue
        msg = e.get("message") or {}
        if msg.get("model") == "<synthetic>":
            continue
        grouped.setdefault(str(msg.get("id") or len(grouped)), []).append(msg)
    return grouped


def _tokens(usage: Mapping[str, Any] | None) -> dict[str, int]:
    usage = usage or {}
    inp = int(usage.get("input_tokens") or 0)
    write = int(usage.get("cache_creation_input_tokens") or 0)
    read = int(usage.get("cache_read_input_tokens") or 0)
**toolResult** for `call_6b6c8c48703845a0af4bb12d` (bash)

#### [54] line 54 · message · assistant · 2026-10-01T22:43:47.929Z
<details><summary>thinking</summary>

The hermetic claude launch is: `--tools ... --strict-mcp-config --mcp-config <plan servers> --setting-sources project,local` + env `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1`. This matches lanes.md's claude row exactly.

One thing to scrutinize per my checklist: "a hermetic claude session that can still read the user's instruction files or settings, or that loses its login".

- Instruction files: `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1`. This is the env var Claude Code respects to disable loading of CLAUDE.md/memory files. But does it also disable *user* instruction files like `~/.claude/CLAUDE.md`? The m7 defect: worker named ten MCP servers from the user's `~/.claude/CLAUDE.md`... wait, actually the defect was that the worker *listed ten MCP servers* that came from user config. Hmm wait — MCP servers in `~/.claude/CLAUDE.md`? MCP servers usually live in `~/.claude.json` (user scope mcpServers) — but with `--strict-mcp-config --mcp-config <file>`, only the file's servers load, so MCP servers are already covered by the pre-existing flags. The spec says: "The worker named ten MCP servers ..., exactly the list in the user's `~/.claude/CLAUDE.md`, while its harness announced no MCP server." Interesting — so those MCP servers were listed in CLAUDE.md as *prose* (instructions listing servers?) and the worker read the instruction file and reported them. So disabling CLAUDE.md loading fixes it.

- Does `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` exist and work? The implementer says "Measured 2026-10-01 (2.1.281)". It's a real, long-standing env var in Claude Code (`CLAUDE_CODE_DISABLE_CLAUDE_MDS` disables all CLAUDE.md memory loading... actually I recall `CLAUDE_CODE_DISABLE_CLAUDE_MD` (singular?) Hmm. There have been both `CLAUDE_CODE_DISABLE_CLAUDE_MD`... Let me think. I believe the documented one is `CLAUDE_CODE_DISABLE_CLAUDE_MDS` (plural MDS)? Actually there is a setting `disableAllHooks`, and env `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`... For CLAUDE.md: I recall `CLAUDE_CODE_DISABLE_CLAUDE_MD`... Honestly I'm not 100% sure; the implementer claims measurement, and exit criterion 4 runs the live hermetic cell which will prove it end-to-end: if instruction files still loaded, the worker would report MCP servers from the user's CLAUDE.md and `rollcall_matches` would fail (announced_servers from result.json would be the plan's mcp config = none, while the report lists servers → gate fails). So criterion 4 is the live proof. Also "keeps the login" — the criterion 4 run proves it (a logged-out CLI produces no valid report).

Note the lanes.md row says the defect list "exactly the list in the user's ~/.claude/CLAUDE.md" — those ten servers were announced to the worker via CLAUDE.md instructions. Fine.

- Also `--setting-sources project,local` keeps "the project's own `.claude` files" — consistent.

Wait, one more: does `CLAUDE_CODE_DISABLE_CLAUDE_MDS` disable only *project* CLAUDE.md (memory) or also the *user* `~/.claude/CLAUDE.md`? The name suggests all CLAUDE.md files ("CLAUDE_MDs"). The implementer measured. Criterion 4 will confirm live. Good.

Now — a subtle interaction: `seat_env(extra)` puts `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` into env AFTER stripping, so it survives. ✓ (verified in seat_env code: `env.update(extra or {})` after `worker_env()`).

But hold on — one more edge: `worker_env()` strips `CLAUDE_CODE_DISABLE_CLAUDE_MDS` from the *parent* if set (starts with CLAUDE). For a *non-hermetic* claude worker, if the desktop session had set it, the worker now loads CLAUDE.md — that's the "usual setup" mirror. Acceptable.

Now codex hermetic claims in lanes.md: "the real ~/.codex configuration, its hooks and its MCP servers (the worker gets its own CODEX_HOME)" and "the login (auth.json is a hard link to the real file)". Let me verify in codex_runner.

</details>
**toolCall bash** id=`call_155db4e2dae14b6ea8a51bf7`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && grep -n \"CODEX_HOME\\|auth.json\\|hardlink\\|hard.link\\|os.link\\|hermetic\" oh-dispatch/scripts/ohflow/codex_runner.py | head -20 && echo === && grep -n \"profile\\|hermetic\" oh-dispatch/scripts/ohflow/dsh_runner.py | head"
}
```
**toolCall bash** id=`call_1686cdca2fa64f3694d89ea6`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && python -c \"\nimport json\ns = json.load(open('oh-dispatch/references/examples/rollcall/rollcall.schema.json'))\nprint(json.dumps(s, indent=1)[:800])\""
}
```

#### [55] line 55 · message · toolResult · 2026-10-01T22:43:48.037Z
36:REAL_CODEX_HOME = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
50:    if not (REAL_CODEX_HOME / "auth.json").is_file():
51:        return [f"codex lane: {REAL_CODEX_HOME / 'auth.json'} is missing; run `codex login`"]
68:def write_hermetic_home(spec: Mapping[str, Any], out_dir: Path) -> Path:
69:    """A CODEX_HOME with only the plan's MCP servers and no hooks.
71:    `auth.json` is a hard link to the real one, so a token refresh inside the
84:    auth = home / "auth.json"
86:        os.link(REAL_CODEX_HOME / "auth.json", auth)
194:    if home == REAL_CODEX_HOME:
288:    return out_dir / "codex-home" if spec.get("profile") == "hermetic" else REAL_CODEX_HOME
310:        if spec.get("profile") == "hermetic":
311:            extra["CODEX_HOME"] = str(write_hermetic_home(spec, out_dir))
===
3:`dsh --profile headless "<task>"` prints only the final assistant message on
212:                                           "profile": spec.get("profile") or DEFAULT_PROFILE,
227:RULES = SeatRules("dsh", profiles=None, profile_dir=True, model_applied=False,
228:                  hermetic_mcp=False)
348:        profile = spec.get("profile") or DEFAULT_PROFILE
349:        argv = [*dsh_argv(), "--profile", str(profile), "--patch", str(WORKER_PATCH),
**toolResult** for `call_155db4e2dae14b6ea8a51bf7` (bash)

#### [56] line 56 · message · toolResult · 2026-10-01T22:43:48.037Z
{
 "type": "object",
 "required": [
  "lane",
  "status",
  "harness",
  "model",
  "tools",
  "mcp_servers",
  "cannot"
 ],
 "properties": {
  "lane": {
   "type": "string"
  },
  "status": {
   "type": "string",
   "enum": [
    "PRESENT"
   ]
  },
  "harness": {
   "type": "string"
  },
  "model": {
   "type": "string"
  },
  "tools": {
   "type": "array",
   "items": {
    "type": "string"
   }
  },
  "mcp_servers": {
   "type": "array",
   "items": {
    "type": "string"
   }
  },
  "cannot": {
   "type": "string"
  }
 },
 "additionalProperties": false
}
**toolResult** for `call_1686cdca2fa64f3694d89ea6` (bash)

#### [57] line 57 · message · assistant · 2026-10-01T22:43:55.995Z
<details><summary>thinking</summary>

- Codex hermetic claims match the code (CODEX_HOME override, auth.json hard link). ✓
- dsh: `--profile <name>` with `profile_dir=True` — "takes a dsh seat profile name instead" ✓. But note: rollcall's normalize rejects any profile other than None/"hermetic", so a dsh cell can't get profile=hermetic anyway; lanes.md's dsh row is about the lane generally, fine.
- Schema requires `lane` — so a report without `lane` already fails `schema_valid`; the gate's lane check is a second net. Consistent.

Now — one more careful check on the stall change: are there other consumers of `stall_timeout_s` plan-argument semantics that assumed 180 default? E.g., the campaign plans (`ohflow.plans.campaign`?) or the milestone plans used by this very campaign (implement_review shim). Those set their own stall values explicitly, presumably. The change is scoped to `plans/rollcall.py`. The README's sentence updated. Check references to `stall_timeout_s` defaults in references/*.md:

</details>
**toolCall bash** id=`call_d008e08fd6524972b7c3ad04`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && grep -rn \"stall_timeout_s\\|180\" oh-dispatch/references/*.md oh-dispatch/SKILL.md 2>/dev/null | grep -i \"stall\\|180\" | head -20"
}
```
**toolCall bash** id=`call_ad5e4416c90f49e196d9b260`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && grep -rn \"CAP_STALL\" oh-dispatch/scripts/ohflow/lanes.py | head && python -c \"\nimport sys; sys.path.insert(0, 'oh-dispatch/scripts')\nfrom ohflow.lanes import lane_info, CAP_STALL\nfor lane in ('pi','claude','codex','dsh','host'):\n    print(lane, lane_info(lane).has(CAP_STALL))\""
}
```

#### [58] line 58 · message · toolResult · 2026-10-01T22:43:56.221Z
oh-dispatch/references/dashboard.md:47:                "idle_s": 3, "stall_timeout_s": null},
oh-dispatch/references/dashboard.md:128:| Agent idle time | above half of `stall_timeout_s`, or 300 s when unset | above `stall_timeout_s`, or 900 s when unset |
oh-dispatch/references/lanes.md:15:Two process facts hold for every lane. The runner and its descendants enter a Windows kill-on-close Job Object, so cancelling a run removes the agent and its MCP children together. `Step.stall_timeout_s` stops a worker whose event stream goes silent; the attempt then records `stall`, which ends as a `worker_error` ([retry tokens](ohflow.md#retry)).
oh-dispatch/references/lanes.md:151:- **Liveness.** Stderr goes silent while the agent runs tools. The stall deadline also reads the session log's modification time, which moves per event. `max_iterations` is not enforced live: no event reaches the runner while the agent works. dsh spends about 30 s shutting down its MCP fleet after the answer, so allow for it in `stall_timeout_s`. A quiet codex reasoning step has run past 180 s without an event, so the roll call gives codex 600 s.
oh-dispatch/references/ohflow.md:43:A **stall** is a `worker_error`. When `stall_timeout_s` expires, the lane kills the worker and the attempt records `stall` as its error. The attempt's tokens then include `worker_error`.
**toolResult** for `call_d008e08fd6524972b7c3ad04` (bash)

#### [59] line 59 · message · toolResult · 2026-10-01T22:43:56.264Z
30:CAP_STALL = "stall_timeout"
59:                   frozenset({CAP_STALL, CAP_CARRY, CAP_QUALIFIED_MCP})),
61:                       frozenset({CAP_STALL, CAP_CARRY, CAP_OAUTH, CAP_PROFILE,
64:                      frozenset({CAP_STALL, CAP_OAUTH, CAP_PROFILE,
67:                    frozenset({CAP_STALL, CAP_OAUTH, CAP_PROFILE,
pi True
claude True
codex True
dsh True
host False
**toolResult** for `call_ad5e4416c90f49e196d9b260` (bash)

#### [60] line 60 · message · assistant · 2026-10-01T22:44:03.150Z
<details><summary>thinking</summary>

Interesting: `host` does NOT have CAP_STALL. So `STALL_S["host"] = 180` is dead (stall_for returns None for host). Harmless — table holds an entry never read for host. Not a defect; the test covers it (`test_every_lane_that_takes_a_limit_gets_one` asserts None for host).

Everything static checks out so far. Now the bigger items:

1. Run the three shards (full suite) and check the count matches README's 896.
2. Run criterion 4 (live cells).

Let me also double-check one thing on the stall override: `test_the_argument_overrides_every_lane` passes `stall_timeout_s=45` and expects 45 for all CAP_STALL lanes. And in normalize, `args.get("stall_timeout_s") not in (None, "")`. Note: `0 not in (None, "")` → True → int("0") = 0... fine.

One more possible careful-engineer catch: `stall_for` uses `STALL_S[lane]` — KeyError for lanes not in the table. All five lanes are in the table, and MODELS keys = the five lanes; `spec.lanes` validated against MODELS; consolidator/reviewer/judge validated against MODELS. So no KeyError possible. ✓

Now, the dsh stall — lanes.md says "dsh spends about 30 s shutting down its MCP fleet after the answer, so allow for it in stall_timeout_s. A quiet codex reasoning step has run past 180 s..." — dsh stays 180; dsh's silence is covered by session-log mtime. OK.

Let me also check `README.md` claim "The suite ... A full run takes about fifteen minutes (896 tests, 885 s on 2026-10-02)". I need to count the tests. Let me count test methods quickly:

Actually let me just count via unittest discovery without running: python -m unittest discover? That would run them. Instead, use the runner's collect-only if available. Let me check run_tests.py for a --list or count option.

</details>
All static seams check out. Now the suite. Let me check what `run_tests.py` offers, then run the three shards.
**toolCall bash** id=`call_e19bdcdcb9494b3785bcc78b`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && python oh-dispatch/tests/run_tests.py --help 2>&1 | head -30"
}
```

#### [61] line 61 · message · toolResult · 2026-10-01T22:44:03.306Z
usage: run_tests.py [-h] [--e2e] [-k PATTERN] [--shard K/N] [--durations N]
                    [-v] [-q]

the oh-dispatch regression suite

options:
  -h, --help     show this help message and exit
  --e2e          also run the end-to-end test against a real model. It needs
                 ZAI_CODING_CN_API_KEY and the OpenHands virtual environment,
                 and it costs several minutes of wall time.
  -k PATTERN     run only tests whose name contains this substring
  --shard K/N    run shard K of N (1-based). The tests sorted by name go to
                 the shards in turn, so the N shards together run every test
                 once.
  --durations N  after the run, print the N slowest tests
  -v, --verbose  name every test as it runs
  -q, --quiet    dots only
**toolResult** for `call_e19bdcdcb9494b3785bcc78b` (bash)

#### [62] line 62 · message · assistant · 2026-10-01T22:44:07.165Z
**toolCall bash** id=`call_cdad016a3bcf470da0b99f11`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && python oh-dispatch/tests/run_tests.py --shard 1/3 > ../suite-m7-smoke-fixes-s1.log 2>&1; tail -6 ../suite-m7-smoke-fixes-s1.log",
 "timeout": 600
}
```

#### [63] line 63 · message · toolResult · 2026-10-01T22:49:38.777Z
SKIPPED (1) - each with its reason:
  - test_the_smoke_matrix_passes (tests.test_e2e_real_model.TheSmokeMatrixOnRealLanes.test_the_smoke_matrix_passes)
      the end-to-end test is opt-in. Pass --e2e to run_tests.py (it sets OHFLOW_E2E=1). It runs the smoke matrix of `ohflow rollcall` against real models and takes one to three minutes.

summary schema checks: 79   unexpected rejections: 0
ran 299 tests in 330.7s   failures=0 errors=0 skipped=1
**toolResult** for `call_cdad016a3bcf470da0b99f11` (bash)

#### [64] line 64 · message · assistant · 2026-10-01T22:49:41.130Z
<details><summary>thinking</summary>

Shard 1: 299 tests, 330.7 s, 0 failures. Now shard 2.

</details>
**toolCall bash** id=`call_9182a5a5725947f4830c57c2`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && python oh-dispatch/tests/run_tests.py --shard 2/3 > ../suite-m7-smoke-fixes-s2.log 2>&1; tail -3 ../suite-m7-smoke-fixes-s2.log",
 "timeout": 600
}
```

#### [65] line 65 · message · toolResult · 2026-10-01T22:54:51.033Z

summary schema checks: 78   unexpected rejections: 0
ran 299 tests in 309.0s   failures=0 errors=0 skipped=0
**toolResult** for `call_9182a5a5725947f4830c57c2` (bash)

#### [66] line 66 · message · assistant · 2026-10-01T22:54:54.944Z
**toolCall bash** id=`call_be78fff8098e465883cfda3f`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && python oh-dispatch/tests/run_tests.py --shard 3/3 > ../suite-m7-smoke-fixes-s3.log 2>&1; tail -3 ../suite-m7-smoke-fixes-s3.log",
 "timeout": 600
}
```

#### [67] line 67 · message · toolResult · 2026-10-01T22:59:44.298Z

summary schema checks: 86   unexpected rejections: 0
ran 298 tests in 288.5s   failures=0 errors=0 skipped=0
**toolResult** for `call_be78fff8098e465883cfda3f` (bash)

#### [68] line 68 · message · assistant · 2026-10-01T22:59:49.981Z
<details><summary>thinking</summary>

All three shards pass: 299 + 299 + 298 = 896 tests, 0 failures, 1 opt-in skip. Total 928.2 s ≈ 15.5 min. README says "896 tests, 885 s on 2026-10-02" — count matches exactly (896 ✓). Shard times: mine 330.7/309.0/288.5 vs README's 340.2/282.9/261.4 — same ballpark, README dated 2026-10-02, fine. "Each shard takes about five minutes" — 5-5.5 min ✓. "about fifteen minutes" ✓.

The full suite exits 0 (all shards green). Gate criterion satisfied on my end.

Now the big one: exit criterion 4 — live cells. I need to run from `oh-dispatch/scripts` with the CLAUDE* vars exported:

```
cd oh-dispatch/scripts
export CLAUDECODE=1 CLAUDE_CODE_ENTRYPOINT=claude-desktop CLAUDE_AGENT_SDK_VERSION=0.3.284
python -m ohflow.cli rollcall --cells single:host single:claude:1:profile=hermetic relay:pi,claude,codex,dsh
```

Let me check the CLI syntax for rollcall first (`ohflow rollcall --cells`). Let me check cli.py's rollcall subcommand. Also how is `ohflow` invoked — `python -m ohflow.cli`? There's probably an `ohflow` wrapper. The README says "from oh-dispatch/scripts". Let me check what's in scripts/ (ohflow module + maybe an ohflow.cmd).

</details>
All shards green: 299 + 299 + 298 = **896 tests**, matching the README figure exactly. Now exit criterion 4 — the live cells. Let me check the CLI entry first.
**toolCall bash** id=`call_506ff2d9b23c43fa8aba4ec5`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && ls oh-dispatch/scripts/ && grep -n \"rollcall\" oh-dispatch/scripts/ohflow/cli.py | head -10"
}
```

#### [69] line 69 · message · toolResult · 2026-10-01T22:59:50.053Z
host_worker.py
implement_review.py
ohflow
24:    ohflow rollcall [--matrix smoke|quick|full | --cells shape:lanes[:count] ...]
499:def cmd_rollcall(ns) -> int:
500:    from . import rollcall
502:        for line in rollcall.list_lines():
505:    return rollcall.run_matrix(
974:    p = sub.add_parser("rollcall",
995:    p.set_defaults(fn=cmd_rollcall)
**toolResult** for `call_506ff2d9b23c43fa8aba4ec5` (bash)

#### [70] line 70 · message · assistant · 2026-10-01T22:59:53.059Z
**toolCall bash** id=`call_86ae3752efa74cf88fdcfee6`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes/oh-dispatch/scripts\" && export CLAUDECODE=1 CLAUDE_CODE_ENTRYPOINT=claude-desktop CLAUDE_AGENT_SDK_VERSION=0.3.284 && python -m ohflow.cli rollcall --cells single:host single:claude:1:profile=hermetic relay:pi,claude,codex,dsh > ../../../../../suite-m7-rollcall-cells.log 2>&1; echo \"exit: $?\"; tail -8 ../../../../../suite-m7-rollcall-cells.log",
 "timeout": 2400
}
```

#### [71] line 71 · message · toolResult · 2026-10-01T23:08:30.310Z
exit: 0
PASS single host count=1  1m45s  73.4 k tokens  C:\Users\<user>\AppData\Local\Temp\rollcall-fbdd56\01-single-host-1\run
PASS single claude count=1 profile=hermetic  0m32s  80.4 k tokens  C:\Users\<user>\AppData\Local\Temp\rollcall-fbdd56\02-single-claude-1\run
PASS relay pi,claude,codex,dsh count=1  6m17s  1320.0 k tokens  C:\Users\<user>\AppData\Local\Temp\rollcall-fbdd56\03-relay-pi-claude-codex-dsh-1\run
ROLLCALL PASS: 3 of 3 cells
**toolResult** for `call_86ae3752efa74cf88fdcfee6` (bash)

#### [72] line 72 · message · assistant · 2026-10-01T23:08:38.342Z
<details><summary>thinking</summary>

Exit criterion 4 passes: last line `ROLLCALL PASS: 3 of 3 cells`, exit 0, with the CLAUDE* vars exported. The relay cell took 6m17s (with codex's longer quiet reasoning surviving — the per-lane stall limit worked; previously it was killed at 180 s).

Now let me verify the cell evidence deeper — the adversarial part:

1. For `single host`: did the worker report itself as OpenHands (not Claude Code)? Check the run's ROLLCALL file / report. The gate `rollcall_matches` now also checks lane. Let me read the report from the host cell: the run dir `C:\Users\<user>\AppData\Local\Temp\rollcall-fbdd56\01-single-host-1\run`. Let me find the structured report and check `harness` and `tools` — prove the defect is actually fixed live (no Claude Code identity).

2. For hermetic claude: check the report's mcp_servers is empty (no user instruction-file servers leaked).

3. Confirm the worktree is still clean (nothing created inside).

Let me inspect the run artifacts.

</details>
Criterion 4 passes: `ROLLCALL PASS: 3 of 3 cells`. Now let me verify the fix evidence inside those live cells — did the host worker really report as OpenHands, and did the hermetic claude worker really see no user MCP servers?
**toolCall bash** id=`call_0043ecd1ff554d0fb0805308`

```json
{
 "command": "cd C:/Users/<user>/AppData/Local/Temp/rollcall-fbdd56 && ls && echo === && find 01-single-host-1/run -name \"*.json\" -path \"*attempt*\" | head -5 && cat 01-single-host-1/run/*/attempts/*/structured.json 2>/dev/null | head -5"
}
```

#### [73] line 73 · message · toolResult · 2026-10-01T23:08:38.732Z
01-single-host-1
02-single-claude-1
03-relay-pi-claude-codex-dsh-1
matrix.json
repo
===
01-single-host-1/run/phases/01.report/01.host-1/attempts/01/completions/openai__glm-5.3-flash-1790895624.100-576d.json
01-single-host-1/run/phases/01.report/01.host-1/attempts/01/completions/openai__glm-5.3-flash-1790895637.944-f69c.json
01-single-host-1/run/phases/01.report/01.host-1/attempts/01/completions/openai__glm-5.3-flash-1790895646.660-8d60.json
01-single-host-1/run/phases/01.report/01.host-1/attempts/01/completions/openai__glm-5.3-flash-1790895654.482-6d79.json
01-single-host-1/run/phases/01.report/01.host-1/attempts/01/completions/openai__glm-5.3-flash-1790895659.820-3b34.json
**toolResult** for `call_0043ecd1ff554d0fb0805308` (bash)

#### [74] line 74 · message · assistant · 2026-10-01T23:08:43.652Z
**toolCall bash** id=`call_acce4278a9fa4a27a0289096`

```json
{
 "command": "cd C:/Users/<user>/AppData/Local/Temp/rollcall-fbdd56 && python -c \"\nimport json, glob\nfor cell in ('01-single-host-1', '02-single-claude-1'):\n    for p in glob.glob(cell + '/run/phases/*/01.*/attempts/01/structured*.json') or glob.glob(cell + '/run/**/report.json', recursive=True):\n        print(p)\n        d = json.load(open(p, encoding='utf-8'))\n        print(json.dumps(d, indent=1)[:900])\n        print('---')\n        break\n\""
}
```

#### [75] line 75 · message · toolResult · 2026-10-01T23:08:43.729Z
(no output)
**toolResult** for `call_acce4278a9fa4a27a0289096` (bash)

#### [76] line 76 · message · assistant · 2026-10-01T23:08:51.978Z
**toolCall bash** id=`call_5fbe84cbd4984786bf6cbc21`

```json
{
 "command": "cd C:/Users/<user>/AppData/Local/Temp/rollcall-fbdd56 && ls 01-single-host-1/run/phases/01.report/01.host-1/attempts/01/ && echo === && grep -rl \"\\\"harness\\\"\" 01-single-host-1/run --include=\"*.json\" | head -5"
}
```

#### [77] line 77 · message · toolResult · 2026-10-01T23:08:53.275Z
brief.md
completions
conversations
final.md
gate.json
logs
position.md
result.json
schema.json
spec.json
worker.pid
===
01-single-host-1/run/phases/01.report/01.host-1/attempts/01/result.json
01-single-host-1/run/phases/01.report/01.host-1/attempts/01/schema.json
01-single-host-1/run/phases/01.report/01.host-1/result.json
01-single-host-1/run/phases/01.report/01.host-1/schema.json
01-single-host-1/run/plan.json
**toolResult** for `call_5fbe84cbd4984786bf6cbc21` (bash)

#### [78] line 78 · message · assistant · 2026-10-01T23:08:58.594Z
**toolCall bash** id=`call_9f6b4c60ee204d74a66a04d0`

```json
{
 "command": "cd C:/Users/<user>/AppData/Local/Temp/rollcall-fbdd56 && python -c \"\nimport json\nfor cell, step in (('01-single-host-1','01.host-1'), ('02-single-claude-1','01.claude-1')):\n    r = json.load(open(f'{cell}/run/phases/01.report/{step}/attempts/01/result.json', encoding='utf-8'))\n    fin = open(f'{cell}/run/phases/01.report/{step}/attempts/01/final.md', encoding='utf-8').read()\n    print('=====', cell)\n    print('announced tools:', r.get('tools'))\n    print('announced servers:', r.get('mcp_servers'))\n    import re\n    m = re.search(r'\\`\\`\\`json\\n(.*?)\\n\\`\\`\\`', fin, re.S)\n    print('report:', m.group(1) if m else fin[-400:])\n\""
}
```

#### [79] line 79 · message · toolResult · 2026-10-01T23:08:58.755Z
===== 01-single-host-1
announced tools: ['file_editor', 'finish', 'task_tracker', 'terminal', 'think']
announced servers: []
report: {"lane": "host", "status": "PRESENT", "harness": "pi 0.85.1", "model": "glm-5.3", "tools": ["terminal", "file_editor", "task_tracker", "finish", "think"], "mcp_servers": [], "cannot": "I cannot reach network services, GUIs, or any tool beyond the five built-ins listed, and I cannot modify any path outside my own worktree's rollcall/host-1.md."}
===== 02-single-claude-1
announced tools: ['Bash', 'Edit', 'Glob', 'Grep', 'Read', 'StructuredOutput', 'Write']
announced servers: []
report: {"lane":"claude","status":"PRESENT","harness":"Claude Code","model":"claude-haiku-4-5-20251001","tools":["Bash","Edit","Glob","Grep","Read","Write","StructuredOutput"],"mcp_servers":[],"cannot":"I cannot run destructive git operations without explicit user confirmation."}
**toolResult** for `call_9f6b4c60ee204d74a66a04d0` (bash)

#### [80] line 80 · message · assistant · 2026-10-01T23:09:16.296Z
<details><summary>thinking</summary>

Excellent live evidence:

1. **Host cell**: the worker reports `harness: "pi 0.85.1"` — wait, interesting. The host lane runs OpenHands with `openai/glm-5.3-flash`, and the agent inside reported its harness as "pi 0.85.1"?? Hmm, that's odd but it's what the OpenHands host agent said. Wait — actually, hold on. The host lane's announced tools are `file_editor, finish, task_tracker, terminal, think` — that's the OpenHands harness surface. The worker's *report* says harness "pi 0.85.1"... Hmm, that's suspicious. Wait, is it? Actually no — in the m7 defect description, the host worker reported "Claude Code 2.1.284 (launched via Claude Desktop ...)" because CLAUDE* env vars told it so. Now it reports "pi 0.85.1"... Why pi? Because OpenHands' environment detection looks at env vars like `PI_CODING_AGENT_DIR`? Hmm, no. Or maybe OpenHands detects the terminal/harness from env. Wait — could the host worker be picking up... hmm.

Actually let me think. The host lane worker is an OpenHands agent (glm-5.3-flash via Z.AI). It's asked "your harness name and version". The agent sees its environment: it might inspect env vars or processes. In the failing matrix run it said "Claude Code 2.1.284 (launched via Claude Desktop...)" — because `CLAUDECODE=1`, `CLAUDE_CODE_ENTRYPOINT=claude-desktop`, `CLAUDE_AGENT_SDK_VERSION=0.3.284` were in its environment, and the model (asked to name its harness) read those env vars and concluded it was Claude Code. Now, with those stripped... it says "pi 0.85.1". Where would it get that? Maybe from `PI_CODING_AGENT_DIR`? No — that's only set for pi workers. Hmm, maybe OpenHands' own runtime reports the harness... Or maybe the *conversations* show it ran `pi --version`? Whatever the agent guessed, the point is: the gate only checks that reported tools ⊆ announced tools and servers ⊆ announced servers, and lane matches. "pi 0.85.1" as a harness *name* is the model's own answer about what harness it runs in — possibly it checked `~/.npm-global` or saw the pi install... Not our gate's concern. Hmm wait, but is it a *concern* for the review? The harness field is free text; the defect was that the *tools* it listed were Claude Code's tools and the identity came from env. Now tools match the announced OpenHands tools exactly (terminal, file_editor, task_tracker, finish, think) and servers are empty. So the env leak is fixed live. The "pi 0.85.1" harness guess is the model being creative (maybe it found the pi npm package in PATH — the box has pi installed globally, and OpenHands agent may have run `pi --version` guessing from... whatever). Free text, gate-relevant? No. But worth noting? The m7 fix's purpose was env cleanliness; the harness name is the agent's own (wrong) guess, unchanged behavior class as any LLM guess. Actually wait — could it be that the host worker *is* running through pi somehow? No — announced tools are OpenHands' five; completions are `openai__glm-5.3-flash`. The agent just misidentified its harness (glm-5.3-flash via OpenHands might have checked `npm ls -g` and found pi). Not a defect of this milestone.

Hmm, actually let me double check one thing — did the host worker see a clean env? The result.json shows announced tools; the report matches. If CLAUDE* had leaked, the agent would likely have listed Claude Code tools (as in the failing run) → gate failure. It passed → strong live evidence the strip works on the host lane.

2. **Hermetic claude cell**: announced servers: [] and reported `mcp_servers: []` — no user MCP servers, no instruction-file leak. Login kept (it answered with claude-haiku). Tools are the plan surface. ✓ Live proof the hermetic fix works.

3. **Relay cell**: passed in 6m17s. Previously failed at codex stall 180 s. Let me check the codex step's duration and stall setting in the run to confirm it took > 180 s of silence or at least that stall_timeout_s=600 was in effect. Let me check the plan.json of the relay run for codex's stall_timeout_s and the codex step duration.

Also confirm: the report lane gate — each relay step's report names its own lane (pi, claude, codex, dsh in sequence). The gate passed, meaning reports named the right lanes (had one named another, it would now fail). Good.

Let me check the relay run's plan for stall values.

</details>
Live evidence confirms both fixes: the host worker now announces OpenHands' five tools (not Claude Code's), and the hermetic claude worker sees zero MCP servers while keeping its login. Let me confirm the relay's codex step ran under the 600 s limit and check the plan's stall values.
**toolCall bash** id=`call_b420f4195cf6450ca4939320`

```json
{
 "command": "cd C:/Users/<user>/AppData/Local/Temp/rollcall-fbdd56 && python -c \"\nimport json\np = json.load(open('03-relay-pi-claude-codex-dsh-1/run/plan.json', encoding='utf-8'))\nfor ph in p['phases']:\n    for st in ph['steps']:\n        print(st['id'], 'stall:', st.get('stall_timeout_s'), 'wall:', st.get('wall_timeout_s'))\nprint('args:', p.get('args'))\n\" && git -C . log --oneline 2>/dev/null | head -3"
}
```

#### [81] line 81 · message · toolResult · 2026-10-01T23:09:16.504Z
pi-1 stall: 180 wall: 600
claude-1 stall: 180 wall: 600
codex-1 stall: 600 wall: 600
dsh-1 stall: 180 wall: 600
args: {'base': 'main', 'count': 1, 'lanes': 'pi,claude,codex,dsh', 'prefix': 'rollcall-eaca-03', 'repo': 'C:\\Users\\<user>\\AppData\\Local\\Temp\\rollcall-fbdd56\\repo', 'shape': 'relay', 'wt_root': 'C:\\Users\\<user>\\AppData\\Local\\Temp\\rollcall-fbdd56\\03-relay-pi-claude-codex-dsh-1\\wt'}
**toolResult** for `call_b420f4195cf6450ca4939320` (bash)

#### [82] line 82 · message · assistant · 2026-10-01T23:09:20.276Z
<details><summary>thinking</summary>

The relay plan: codex-1 stall 600, others 180. The relay passed in 6m17s — codex survived.

Let me also check how long the codex step took (to see whether the 600 s was actually load-bearing, or whether codex was quick this time). Not strictly required, but interesting:

</details>
**toolCall bash** id=`call_6e7b20863bcc41ab89bfd617`

```json
{
 "command": "cd C:/Users/<user>/AppData/Local/Temp/rollcall-fbdd56/03-relay-pi-claude-codex-dsh-1/run && python -c \"\nimport json\nj = json.load(open('journal.jsonl', encoding='utf-8')) if False else None\nimport re\nevs = []\nfor line in open('journal.jsonl', encoding='utf-8'):\n    try: evs.append(json.loads(line))\n    except Exception: pass\nfrom datetime import datetime\nfor e in evs:\n    if e.get('event') in ('step_started','step_finished','run_finished'):\n        t = e.get('time') or e.get('ts') or e.get('at')\n        print(e.get('event'), e.get('step') or e.get('step_id') or '', t)\n\" 2>/dev/null | head -15 || ls"
}
```

#### [83] line 83 · message · toolResult · 2026-10-01T23:09:20.379Z
step_started  2026-10-01T23:02:16Z
step_finished  2026-10-01T23:02:40Z
step_started  2026-10-01T23:02:41Z
step_finished  2026-10-01T23:03:38Z
step_started  2026-10-01T23:03:38Z
step_finished  2026-10-01T23:04:40Z
step_started  2026-10-01T23:04:40Z
step_finished  2026-10-01T23:08:26Z
run_finished  2026-10-01T23:08:27Z
step_finished  2026-10-01T23:08:28Z
step_finished  2026-10-01T23:08:28Z
step_finished  2026-10-01T23:08:29Z
step_finished  2026-10-01T23:08:29Z
run_finished  2026-10-01T23:08:29Z
**toolResult** for `call_6e7b20863bcc41ab89bfd617` (bash)

#### [84] line 84 · message · assistant · 2026-10-01T23:09:40.147Z
<details><summary>thinking</summary>

Wait, these timestamps are 2026-10-01T23:02 — but my run just happened. Hmm, "2026-10-01T23:02:16Z"... Today's date per the README measurements was 2026-10-02. My run just ran — what time is it now? Let me check. The log shows the relay: pi 24 s, claude 57 s, codex 62 s (23:03:38→23:04:40), dsh 226 s. Total 6m13s + overhead ≈ 6m17s. Codex only took 62 s this time — under 180 s! So the relay passing does NOT prove the 600 s limit was load-bearing this run; codex was quick. But the fix is still correct per the m7 evidence (the original failure had 180+ s of reasoning silence). The last step (dsh) ran 23:04:40→23:08:26 = 226 s — interesting, dsh survived with stall 180 because dsh's stall deadline reads the session log mtime (per lanes.md), so its events kept it alive.

Hmm wait, the timestamps say 2026-10-01 but shards ran "on 2026-10-02"... my session clock — whatever, not important. Actually, hmm, the journal timestamps being 2026-10-01T23:02 while README claims measurements "on 2026-10-02"... The README dates are the implementer's. The clock on this box might be set to 2026-10-01/02 - irrelevant.

Wait, actually it matters a little: my run happened "now". Let me get the current date to see if journal times make sense. Not critical for the verdict.

One more check on the timestamps: codex step = 62 s < 180 s. So in this particular live run the codex stall fix wasn't exercised to its limit — the original failure had ~187 s of silence. The fix is still right (limit 600 ≥ 600 required by spec: "codex gets at least 600 s" ✓, STALL_S has exactly 600 ✓).

Now the remaining checklist items:

- "a test that passes both with and without its fix" — verified by reasoning; also the defect-44 test asserts `_leaked(env) == []` where old code had `dict(os.environ)` — definitely fails old code. Defect 47: old default 180 → assertGreaterEqual(600) fails. Defect 46: old gate had no `lane` param → TypeError. Defect 45: old code had no HERMETIC_ENV → env.get(DISABLE) is None → fail. All genuinely red-first.

- Prose contradictions: 
  - lanes.md new section — verified against code (claude row, codex row, dsh row, pi row, host row).
  - "Every lane also drops the launching session's variables (CLAUDE*, CLAUDECODE, ANTHROPIC_BASE_URL), hermetic or not." — true now via worker_env/seat_env on all five lanes. ✓
  - README stall sentence ✓ matches STALL_S.
  - README figures ✓ (896 count verified by my shard runs; 885 s vs my 928 s — dated, close enough; "about fifteen minutes" ✓).
  - claude_runner docstring updated ✓.

- The `--safe-mode`/`--bare` sentence in lanes.md: "claude offers two other switches, and neither serves: --safe-mode drops the --mcp-config servers, and --bare needs an API key." Matches the code comment. Fine.

- Charter bar #1 (structural deepening): the m7 change moves the env rule into `proc.worker_env` — one place, lowest module every launch goes through (proc is imported by cli_lane, worker, pi_runner, seat_runner). Callers stop knowing the pattern. Spec said "Prefer the lowest module every launch already goes through" — proc.py is that module (spawn_managed lives there). ✓

- Charter #4 (high-value output): gates' description lambda updated; no verb output changed here. Fine.

- Anything in the spec left undone? Scope item 3: "The roll call takes each cell's stall limit from the lane (the registry or the roll-call route table)" — implemented as STALL_S table in the plan module (the "roll-call route table" option). ✓ "A stall_timeout_s argument still overrides it" ✓ (replaces for every lane — spec says "still overrides it"; implementation makes it override every lane, documented in README and plan docstring; reasonable reading).

- Exit criterion 1 detail: "one per lane, each proving the worker's environment has no CLAUDE*, CLAUDECODE or ANTHHROPIC_BASE_URL when the parent has them" — 5 lane tests + 1 rule test = 6 ≥ 5 ✓. The LEAK regex in the test is `^(CLAUDE|ANTHROPIC_BASE_URL$)` which covers CLAUDE* (including CLAUDECODE) and ANTHROPIC_BASE_URL ✓.

- Windows traps: no new child processes added... the tests mock spawn_managed. The live rollcall spawned children with existing machinery (CREATE_NO_WINDOW presumably already handled in proc). ✓

- My worktree cleanliness: git status --porcelain must print nothing at the end. Let me check now. The rollcall wrote only under %TEMP% (out_dir rollcall-fbdd56). Let me confirm.

One more adversarial angle: the `rollcall_matches` gate description lambda — when `lane` arg present, adds "; the report names lane X". Cosmetic. ✓

Another: `test_report_lane_reaches_every_report_check_of_the_plan` builds only shape=merge with lanes pi,claude. It asserts seen == {pi-1: pi, claude-1: claude, consolidate: claude}. Consolidator defaults to claude (since claude in lanes). ✓. Other shapes all route through _report_checks — verified by reading _solo/_relay/_merge; review/campaign shapes don't use rollcall_matches. So every rollcall_matches check in every shape carries lane. Let me double-check with a quick exhaustive script over all shapes rather than trusting my reading... Actually let me run a quick check across shapes.

Also one more: `_review`'s reviewer step and campaign judge don't produce JSON reports (no schema) — no lane check needed. Fine.

Let me run the exhaustive shape check + git status.

</details>
The relay passed with codex at 600 s (its step took only 62 s this time; dsh took 226 s and survived via its log-mtime liveness). Let me exhaustively verify every `rollcall_matches` check in every shape carries the lane, and confirm my worktree stayed clean.
**toolCall bash** id=`call_699bb94d3425426598b71be0`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && python -c \"\nimport sys; sys.path.insert(0, 'oh-dispatch/scripts')\nfrom ohflow.plans import rollcall\nimport tempfile, pathlib\ntmp = tempfile.mkdtemp()\nrepo = pathlib.Path(tmp) / 'repo'\nfor shape in ('single','fanout','relay','merge','retry','review','campaign'):\n    for lanes in ('pi', 'pi,claude,codex,dsh'):\n        try:\n            plan = rollcall.build({'repo': str(repo), 'shape': shape, 'lanes': lanes})\n        except ValueError as e:\n            continue\n        for ph in plan.phases:\n            for st in ph.steps:\n                if st.gate:\n                    for c in st.gate.checks:\n                        if c.name == 'rollcall_matches' and not c.args.get('lane'):\n                            print('MISSING LANE:', shape, lanes, st.id)\nprint('check done')\n\" && git status --porcelain && echo \"STATUS CLEAN (empty above)\" && git log --oneline arch/deepening..HEAD | wc -l"
}
```

#### [85] line 85 · message · toolResult · 2026-10-01T23:09:40.438Z
check done
STATUS CLEAN (empty above)
5
**toolResult** for `call_699bb94d3425426598b71be0` (bash)

#### [86] line 86 · message · assistant · 2026-10-01T23:09:47.098Z
<details><summary>thinking</summary>

Every `rollcall_matches` check in every shape carries a `lane`. Worktree clean, 5 commits past base.

Remaining verification: prove the new defect tests actually fail against the old code — the charter demands red-first proofs. I can do this without touching my worktree by copying the product tree to a temp dir at the base commit and running the new tests there. Let me do it cheaply:

`git archive arch/deepening oh-dispatch | tar -x -C <tmpdir>` then overlay the new test files from HEAD, then run the four new test files. That proves red-first. Let me do it for defect 44 (worker_env) and 47 (stall) and 46 (gate lane) and 45 (hermetic env). Note: tests import `from ohflow import ...` with sys.path containing scripts dir — run_tests.py handles path setup. Simplest: in the temp dir, run `python oh-dispatch/tests/run_tests.py -k parent_session` etc. But run_tests.py may rely on repo layout (SKILL.md etc.) — git archive includes the whole oh-dispatch tree from base. The new test files need copying from HEAD (they're new files). Also test_defect_46 imports fine. Support module `support.py` — is it unchanged? It existed before. OK.

Let me do that.

</details>
Everything structural passes. One last adversarial check: prove the new defect tests were red first — run them against the base code in a temp dir (outside my worktree).
**toolCall bash** id=`call_bee1a53682214da799cc98b7`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && rm -rf \"$TEMP/m7-base-check\" && mkdir -p \"$TEMP/m7-base-check\" && git archive arch/deepening oh-dispatch | tar -x -C \"$TEMP/m7-base-check\" && for f in 44_parent_session_vars_reach_no_worker 45_hermetic_claude_loads_no_instruction_files 46_rollcall_report_lane_must_match_the_step 47_rollcall_stall_limit_is_per_lane; do git show HEAD:oh-dispatch/tests/test_defect_$f.py > \"$TEMP/m7-base-check/oh-dispatch/tests/test_defect_$f.py\"; done && cd \"$TEMP/m7-base-check\" && python oh-dispatch/tests/run_tests.py -k parent_session 2>&1 | tail -2 && python oh-dispatch/tests/run_tests.py -k instruction_files 2>&1 | tail -2 && python oh-dispatch/tests/run_tests.py -k report_lane 2>&1 | tail -2 && python oh-dispatch/tests/run_tests.py -k per_lane 2>&1 | tail -2",
 "timeout": 300
}
```

#### [87] line 87 · message · toolResult · 2026-10-01T23:09:58.080Z
summary schema audit: this filtered selection produced no Engine summary
ran 6 tests in 0.2s   failures=5 errors=1 skipped=0
summary schema audit: this filtered selection produced no Engine summary
ran 3 tests in 0.0s   failures=1 errors=0 skipped=0
summary schema audit: this filtered selection produced no Engine summary
ran 5 tests in 0.0s   failures=0 errors=4 skipped=0
summary schema audit: this filtered selection produced no Engine summary
ran 4 tests in 0.2s   failures=1 errors=0 skipped=0
**toolResult** for `call_bee1a53682214da799cc98b7` (bash)

#### [88] line 88 · message · assistant · 2026-10-01T23:10:16.247Z
<details><summary>thinking</summary>

Against the base code:
- defect 44 (`parent_session`): 6 tests → 5 failures + 1 error (the error is the old `rollcall_matches` TypeError? no wait, that's report_lane. The error here — one of the 6 errored; either way, red) — RED ✓
- defect 45 (`instruction_files`): 3 tests → 1 failure (the hermetic env test fails; the other two — setting-sources flag kept and usual setup — pass on old code too, correctly, since old hermetic already had --setting-sources) — RED ✓
- defect 46 (`report_lane`): 5 tests → 4 errors (TypeError on the new `lane` kwarg / missing behavior) — RED ✓
- defect 47 (`per_lane`): 4 tests → 1 failure (codex 180 < 600) — RED ✓ (wait, `-k per_lane` ran 4 tests: defect 47 has 3... plus maybe another test with "per_lane" in the name from an earlier milestone. Whatever, red.)

All defect tests fail against the base. The suite on the branch is green (896, 0 failures). 

Cleanup the temp dir? It's in %TEMP%, outside the worktree — fine to leave, but let me remove it to be tidy. Not required.

Now compile my findings. Summary of everything:

**Exit criteria:**
1. `-k parent_session` → 6 tests, exit 0 ✓ (≥5, one per lane, all five lanes covered: claude, codex, dsh, pi, host)
2. `-k hermetic` → 10 tests, exit 0 ✓
3. `-k report_lane` → 5 tests, exit 0 ✓ (first test: report naming another lane fails)
4. Live cells with CLAUDECODE=1, CLAUDE_CODE_ENTRYPOINT=claude-desktop, CLAUDE_AGENT_SDK_VERSION=0.3.284 → last line `ROLLCALL PASS: 3 of 3 cells`, exit 0 ✓
5. grep "not measured yet" README → no match ✓

**Full suite:** three shards, 299+299+298 = 896 tests, 0 failures, 1 opt-in skip; README's 896 figure exact.

**Findings (severity ordered):** I have no blocking findings. Minor observations worth reporting:

1. (informational) The relay's live codex step took only 62 s this run, so the 600 s limit wasn't exercised to its edge; the fix rests on the m7 failure evidence (187 s of silence killed at 180 s) and the unit test. Not a defect.

2. (informational) The host worker's free-text `harness` field said "pi 0.85.1" (the model's own guess); the gate checks tools/servers/lane, not the harness string. Tools matched the announced OpenHands five exactly — the env leak is fixed. Not a defect of this milestone; maybe worth a future note that `harness` is unverified free text.

3. (nit) `STALL_S["host"] = 180` is dead — the host lane has no CAP_STALL, so `stall_for("host")` returns None. Harmless (test covers the None); a reader of the table might think host takes 180. Very minor prose-adjacent nit. Actually — is this worth flagging as a prose issue? The table comment says "Seconds of silence that stop a worker, per lane." For host it never applies. Tiny. I'll mention as a nit, not blocking.

4. (nit) README quick wall time is the sum of the quick cells' seconds inside the full run, not a standalone quick-matrix wall clock. The spec asked to fill it "from the measured matrix.json", which is what was done; the row says "first full matrix run". Acceptable.

5. `_journal timestamps` — irrelevant.

6. The three remaining `dict(os.environ)` sites (cli.py:342, cli.py:787, exec.py:81) launch the ohflow supervisor and gate commands, not workers; workers strip at the lane seam (proc.worker_env / seat_env). Verified all five lanes' launch paths. Not a defect.

7. Check: does the detached supervisor route mean workers inherit CLAUDE* from the supervisor? No — lanes strip. The live criterion-4 run went through in-process cells (not detached), but m5's exit check covered WMI/detached routes and the strip is at lane level regardless of route. Actually wait — criterion 4 ran `python -m ohflow.cli rollcall --cells ...` in the foreground, in-process. The failing matrix run also ran in-process from a Claude session. So the live proof matches the failure mode exactly. ✓

Vocabulary/authorship checks: commit messages clean, no banned vocabulary in new prose (checked the diffs: "rule", "table", "lane", "module"... no component/service/API/boundary/layer used for architecture words). Let me do one final grep of the new prose for banned words to be thorough... The lanes.md addition: "the plan's tools and MCP servers", "the OAuth login" — fine. README: "table" fine.

One more thing — the report format asks the worker for `"lane": "{lane}"` — the briefs fill it; the gate now enforces it. And `schema_valid` requires `lane` (required field). So a report missing lane fails schema first. Consistent.

Also check `git diff arch/deepening...HEAD` touched only oh-dispatch/** — from the stat: yes, all paths under oh-dispatch/. ✓

Gate for my own report: final message must match VERDICT regex and worktree clean ✓.

Let me clean up the temp base-check dir and write the final report.

</details>
Red-first proof complete: all four defect test files fail against the base code (5F+1E, 1F, 4E, 1F) and pass on the branch. Let me clean up the temp dir and do a final hygiene pass.
**toolCall bash** id=`call_4eb86f2c0c1a4859b8fdda2f`

```json
{
 "command": "rm -rf \"$TEMP/m7-base-check\" && cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && git status --porcelain; echo \"clean: $?\" && git diff arch/deepening...HEAD --stat | tail -1 && grep -rniE \"component|service|boundary|layer\" oh-dispatch/references/lanes.md | grep -iv \"components\\|service account\" | head -5; echo \"vocab check done\""
}
```

#### [89] line 89 · message · toolResult · 2026-10-01T23:10:16.758Z
clean: 0
 15 files changed, 393 insertions(+), 41 deletions(-)
vocab check done
**toolResult** for `call_4eb86f2c0c1a4859b8fdda2f` (bash)

#### [90] line 90 · message · assistant · 2026-10-01T23:10:29.849Z
<details><summary>thinking</summary>

Everything is verified. Worktree clean, only oh-dispatch/** changed, vocabulary clean.

Final report with findings, most severe first, then the verdict. All exit criteria pass, no defect-shipping findings. The nits are informational. VERDICT: MERGEABLE.

</details>
# Review report: m7-smoke-fixes

## What I reviewed

Five commits (`18f4bcd`…`c9004e3`), 15 files, all under `oh-dispatch/`. The whole diff, module by module:

- **`proc.py`** — the one rule: `_PARENT_SESSION_VARS` + `worker_env()` now live in `proc`, the lowest module every launch goes through. `seat_runner.seat_env`, `pi_runner.PiAdapter.prepare`, `worker.HostLane.launch` and `cli_lane.CliLane` all build worker environments from it. The remaining `dict(os.environ)` sites (`cli.py:342`, `cli.py:787`, `exec.py:81`) launch the ohflow supervisor itself and gate shell commands, not workers; workers strip at the lane seam on every route.
- **`claude_runner.py`** — hermetic sets `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` through `seat_env(extra)` (applied after the strip, so it survives), keeping `--setting-sources project,local`, `--strict-mcp-config`, `--mcp-config` and the OAuth login.
- **`plans/rollcall.py`** — `STALL_S` per-lane table (codex 600 s), `Spec.stall_for()`, `stall_timeout_s` overrides every lane; every `rollcall_matches` check now carries `{"lane": lane}` (verified for **all seven shapes**, not just the tested ones).
- **`gates.py`** — `rollcall_matches(lane=...)` fails a report whose `lane` differs or is missing.
- **`README.md` / `references/lanes.md`** — figures and hermetic table match the code and the measured `matrix.json` (I recomputed: full 1942.7 s, quick = 1466.5 s sum of cells 1–10, failures 2/10 and 3/15).
- **Tests** — 17 new tests in four defect files; detached-run waits raised to one 60 s bound.

## Exit criteria, run by me

| # | Result |
|---|---|
| 1 | `-k parent_session`: **6 tests, exit 0** (one per lane + the rule itself) |
| 2 | `-k hermetic`: **10 tests, exit 0** |
| 3 | `-k report_lane`: **5 tests, exit 0** (wrong-lane report fails) |
| 4 | With `CLAUDECODE=1`, `CLAUDE_CODE_ENTRYPOINT=claude-desktop`, `CLAUDE_AGENT_SDK_VERSION=0.3.284`: last line **`ROLLCALL PASS: 3 of 3 cells`**, exit 0 (host 1m45s, hermetic claude 32s, relay 6m17s) |
| 5 | `grep "not measured yet" README.md`: **no match** |

**Full suite, three shards, sequential:** 299 + 299 + 298 = **896 tests, 0 failures, 1 opt-in skip** (330.7 s / 309.0 s / 288.5 s). The README's "896 tests" is exact.

**Red-first proof:** I extracted the base tree (`git archive arch/deepening`) into a temp dir, overlaid the four new test files, and ran them: 6 tests → 5 failures + 1 error; 3 → 1 failure; 5 → 4 errors; 4 → 1 failure. Every defect test is genuinely red against the old code.

**Live evidence inside the criterion-4 run:** the host worker announced exactly OpenHands' five tools (`terminal, file_editor, task_tracker, finish, think`) and no servers — the Claude-Code identity leak is gone; the hermetic claude worker reported `mcp_servers: []` against zero announced servers, with its login working; the relay plan shows `codex-1 stall: 600`.

## Findings, most severe first

1. **Informational — the 600 s codex limit was not exercised to its edge live.** In my relay run the codex step took 62 s (`step_started 23:03:38Z → step_finished 23:04:40Z`), under the old 180 s limit. The fix rests on the m7 failure evidence (187 s of reasoning silence killed at 180 s) and on `test_defect_47`, which is red-first proven. Not a defect.
2. **Informational — `harness` in the report is unverified free text.** The host worker answered `"harness": "pi 0.85.1"` (the model's own guess at its harness). The gate checks tools, servers and lane, not that string. Out of this milestone's scope; worth remembering if the roll call ever needs true identity.
3. **Nit — `STALL_S["host"] = 180` is dead.** The host lane has no `CAP_STALL`, so `stall_for("host")` always returns `None`; the table entry can mislead a reader into thinking host takes 180 s. Harmless and covered by `test_every_lane_that_takes_a_limit_gets_one`.
4. **Nit — the README `quick` wall time is the sum of the quick cells' seconds inside the full run** (1466.5 s), not a standalone quick-matrix wall clock. The spec said to fill it from the measured `matrix.json`, and the row says "first full matrix run", so this is what was asked; noting it for honesty.

No finding ships a defect. Worktree clean, only `oh-dispatch/**` changed, authorship clean, vocabulary clean, prose matches code.

VERDICT: MERGEABLE

# Transcript — 02.review/01.review attempt 2 (lane pi)- Canonical run: `m7-smoke-fixes` (plan `deepening-m7-smoke-fixes`)- Original source: `C:\Users\<user>\ohflow-home\workflows\oh-dispatch-deepening\milestones\m7-smoke-fixes\runs\m7-smoke-fixes\phases\02.review\01.review\attempts\02\session\2026-10-02T00-16-07-356Z_01a0f9f7-e2ba-7441-bf0b-7cea9d89d4a3.jsonl`- Records: 92; tool calls: 50; tool results: 50- Message and tool-output text is complete after redaction. Missing timestamps remain unknown.- Rebuild with `python collect.py` (read-only).
#### [1] line 1 · session · 2026-10-02T00:16:07.356Z

#### [2] line 2 · model-change · 2026-10-02T00:16:07.409Z

#### [3] line 3 · thinking-level-change · 2026-10-02T00:16:07.409Z

#### [4] line 4 · message · user · 2026-10-02T00:16:07.428Z
<file name="C:\Users\<user>\ohflow-home\workflows\oh-dispatch-deepening\milestones\m7-smoke-fixes\runs\m7-smoke-fixes\phases\02.review\01.review\attempts\02\brief.md">
## Your position in this run

Run:       m7-smoke-fixes     plan: deepening-m7-smoke-fixes
Phase:     2 of 2 - "Review"
Step:      1 of 1 in this phase - id `review`, role `review`, attempt 2
Coordinate: 02.review/01.review
Worktree:  C:\Users\<user>\dev\_wt\oh-dispatch-deepening\m7-smoke-fixes
           branch arch/m7-smoke-fixes, created from arch/deepening at 7426973
You own:   no path is reserved for you in this plan

Already done, before you (phases 1 to 1):
  01.implement/01.implement - role `implement` - commit 01b5719 - gate PASSED

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
   Run exit criterion 4 exactly as the campaign driver does, with `--out "$(mktemp -d)"`.
   That path holds a `.` (`tmp.XXXXXXXXXX`). The default `--out` has none, and a run on the
   default hid a dsh defect in attempt 1.
4. Look for what a careful engineer would find:
   - a worker launch on any lane that still passes `CLAUDE*`, `CLAUDECODE` or
     `ANTHROPIC_BASE_URL` (grep every place an environment is built for a child);
   - a hermetic claude session that can still read the user's instruction files or settings, or
     that loses its login;
   - a stall limit that a lane's normal silence can still trip (codex reasoning, a long foreground
     command);
   - a report whose `lane` names another lane and still passes the gate;
   - README figures that do not match the measured `matrix.json` or a shard run;
   - a dsh session bucket that differs from dsh's own `projectKey` rule for any path
     (`%APPDATA%\npm\node_modules\@deepseek-ai\dsh\node_modules\@deepseek-ai\dsh-session-persistence-jsonl\lib\index.js`);
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

#### [5] line 5 · message · assistant · 2026-10-02T00:16:13.224Z
<details><summary>thinking</summary>

Let me start by reading the charter and understanding the situation. I'm the adversarial reviewer for milestone m7-smoke-fixes. I change no file. My terminal is my only tool.

Let me plan:
1. Read the charter.
2. Read the milestone diff.
3. Run exit criteria one by one.
4. Look for issues listed in point 4.
5. Final message with findings and verdict.

Let me start.

</details>
**toolCall bash** id=`call_b503f6610d8c4bf6ab2e22a3`

```json
{
 "command": "cat C:/Users/<user>/ohflow-home/workflows/oh-dispatch-deepening/charter.md"
}
```
**toolCall bash** id=`call_59f667cdf75748279a67ddb3`

```json
{
 "command": "cd C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes && git status --porcelain && git log --oneline arch/deepening..HEAD && git diff arch/deepening...HEAD --stat"
}
```

#### [6] line 6 · message · toolResult · 2026-10-02T00:16:13.433Z
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
**toolResult** for `call_b503f6610d8c4bf6ab2e22a3` (bash)

#### [7] line 7 · message · toolResult · 2026-10-02T00:16:13.434Z
01b5719 oh-dispatch README: suite figure from a three-shard run after the dsh bucket, stall-table and watcher-cursor fixes (902 tests)
caed658 oh-dispatch campaign: .watch.*.json joins the campaign's git ignores, so a watcher's cursor no longer counts as a judge's stray edit and no longer escalates a REVISE; dsh docstring escape fixed
3bbb2ef oh-dispatch roll call: host has no stall row because it takes no stall limit; README says so, and says the quick figure sums cells of the full run
235a9fa oh-dispatch dsh lane: the session bucket follows dsh's own projectKey, so a worktree path with '.', '_', a space or a non-ASCII letter finds its session; a miss names the bucket it searched
c9004e3 oh-dispatch README: quick and full wall times from the first full matrix, suite figure from a three-shard run on this branch
bd76078 oh-dispatch tests: the detached-run tests wait up to 60 s on every real-process step through one helper, because 10 s failed under suite load
52dbe58 oh-dispatch roll call: the stall limit is per lane (codex 600 s) and the gate fails a report that names another lane than its step
139fac7 oh-dispatch claude lane: profile=hermetic sets CLAUDE_CODE_DISABLE_CLAUDE_MDS so no instruction file loads; lanes.md says per lane what hermetic removes and keeps
18f4bcd oh-dispatch: one worker_env rule strips the launching session's variables from every lane, so pi and host no longer inherit CLAUDE*, CLAUDECODE or ANTHROPIC_BASE_URL
 oh-dispatch/README.md                              |  10 +-
 oh-dispatch/references/campaign.md                 |   5 +-
 oh-dispatch/references/lanes.md                    |  20 +++-
 oh-dispatch/scripts/ohflow/campaign.py             |   2 +-
 oh-dispatch/scripts/ohflow/claude_runner.py        |  13 ++-
 oh-dispatch/scripts/ohflow/cli_lane.py             |   4 +-
 oh-dispatch/scripts/ohflow/dsh_runner.py           |  36 +++++-
 oh-dispatch/scripts/ohflow/gates.py                |  12 +-
 oh-dispatch/scripts/ohflow/pi_runner.py            |   2 +-
 oh-dispatch/scripts/ohflow/plans/rollcall.py       |  39 +++++--
 oh-dispatch/scripts/ohflow/proc.py                 |  17 +++
 oh-dispatch/scripts/ohflow/seat_runner.py          |   9 +-
 oh-dispatch/scripts/ohflow/worker.py               |   4 +-
 oh-dispatch/tests/fakes/fake_dsh.py                |  19 +++-
 .../tests/test_defect_07_detached_run_survives.py  |  29 ++++-
 ...efect_44_parent_session_vars_reach_no_worker.py | 126 +++++++++++++++++++++
 ...5_hermetic_claude_loads_no_instruction_files.py |  57 ++++++++++
 ..._46_rollcall_report_lane_must_match_the_step.py |  59 ++++++++++
 ...t_defect_47_rollcall_stall_limit_is_per_lane.py |  44 +++++++
 ...est_defect_48_dsh_session_bucket_follows_dsh.py |  77 +++++++++++++
 ...defect_49_campaign_watch_is_not_a_stray_edit.py |  57 ++++++++++
 21 files changed, 589 insertions(+), 52 deletions(-)
**toolResult** for `call_59f667cdf75748279a67ddb3` (bash)

#### [8] line 8 · message · assistant · 2026-10-02T00:16:19.393Z
<details><summary>thinking</summary>

The tree is clean. Now let me read the full diff. Let me do it file by file. First let me get the full diff.

</details>
Charter read, tree clean, 8 commits past base. Now the full diff.
**toolCall bash** id=`call_c2f19bd66ec44bb98a699026`

```json
{
 "command": "cd C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes && git diff arch/deepening...HEAD -- oh-dispatch/scripts/ohflow/proc.py oh-dispatch/scripts/ohflow/worker.py oh-dispatch/scripts/ohflow/seat_runner.py"
}
```
**toolCall bash** id=`call_3017d4e6fc0341b5866c343b`

```json
{
 "command": "cd C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes && git diff arch/deepening...HEAD -- oh-dispatch/scripts/ohflow/pi_runner.py oh-dispatch/scripts/ohflow/claude_runner.py oh-dispatch/scripts/ohflow/cli_lane.py oh-dispatch/scripts/ohflow/campaign.py"
}
```

#### [9] line 9 · message · toolResult · 2026-10-02T00:16:19.553Z
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
**toolResult** for `call_c2f19bd66ec44bb98a699026` (bash)

#### [10] line 10 · message · toolResult · 2026-10-02T00:16:19.556Z
diff --git a/oh-dispatch/scripts/ohflow/campaign.py b/oh-dispatch/scripts/ohflow/campaign.py
index 00a0d6d..bb56bfe 100644
--- a/oh-dispatch/scripts/ohflow/campaign.py
+++ b/oh-dispatch/scripts/ohflow/campaign.py
@@ -341,7 +341,7 @@ def ensure_ignores(root: Path) -> None:
     gi = Path(root) / ".gitignore"
     want = [f"milestones/*/{d}/" for d in GENERATED_DIRS] + \
         [LEDGER, STATUS, ESCALATION, "campaign.log", "campaign.pid",
-         "campaign.log.launch.*", "__pycache__/"]
+         "campaign.log.launch.*", ".watch.*.json", "__pycache__/"]
     have = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
     missing = [w for w in want if w not in have]
     if missing:
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
**toolResult** for `call_3017d4e6fc0341b5866c343b` (bash)

#### [11] line 11 · message · assistant · 2026-10-02T00:16:29.429Z
<details><summary>thinking</summary>

Interesting. The rule: `_PARENT_SESSION_VARS = re.compile(r"^(CLAUDE|CLAUDECODE$|ANTHROPIC_BASE_URL$)")`.

Wait, this matches `CLAUDE` prefix — but it also matches `CLAUDE` followed by anything? `^(CLAUDE|...)` — the regex `^(CLAUDE|CLAUDECODE$|ANTHROPIC_BASE_URL$)` matches any string starting with `CLAUDE` (first alternative has no `$` anchor, so any string starting with CLAUDE matches). So `CLAUDE*` all match, `CLAUDECODE` matches (second alt — though it'd also match the first), `ANTHROPIC_BASE_URL` matches only exactly. OK.

Hmm, but wait: does this also strip `ANTHROPIC_API_KEY`? No — only `ANTHROPIC_BASE_URL` exact. That's per spec: the rule is `CLAUDE*`, `CLAUDECODE`, `ANTHROPIC_BASE_URL`. Fine.

Now let me check: does the regex remove `CLAUDE.md`-related... no, environment only.

One potential concern: `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` set as HERMETIC_ENV for the claude lane — but seat_env's base already strips CLAUDE*, then adds HERMETIC_ENV afterwards ("A variable a lane sets on purpose is added afterwards"). seat_env(base) then env.update(extra) — order: `env = proc.worker_env(); env["PYTHONIOENCODING"]=...; env.update(extra or {})`. So yes, HERMETIC_ENV is added after stripping. Good.

But wait — the dsh lane: let me look at dsh_runner diff, gates, plans/rollcall, and the tests.

</details>
**toolCall bash** id=`call_34c844de2c2a4b43b1ab1bfc`

```json
{
 "command": "cd C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes && git diff arch/deepening...HEAD -- oh-dispatch/scripts/ohflow/dsh_runner.py oh-dispatch/scripts/ohflow/gates.py"
}
```
**toolCall bash** id=`call_cec799cbff844b7cb34dcdb9`

```json
{
 "command": "cd C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes && git diff arch/deepening...HEAD -- oh-dispatch/scripts/ohflow/plans/rollcall.py oh-dispatch/references/lanes.md oh-dispatch/references/campaign.md"
}
```

#### [12] line 12 · message · toolResult · 2026-10-02T00:16:29.646Z
diff --git a/oh-dispatch/scripts/ohflow/dsh_runner.py b/oh-dispatch/scripts/ohflow/dsh_runner.py
index b1ff331..9970ab1 100644
--- a/oh-dispatch/scripts/ohflow/dsh_runner.py
+++ b/oh-dispatch/scripts/ohflow/dsh_runner.py
@@ -4,9 +4,14 @@
 stdout; reasoning goes to stderr. Everything else is in the session log, read
 after exit:
 
-    ~/.dsh/sessions/--<cwd, each run of chars outside [A-Za-z0-9-] as one '-'>--/
+    ~/.dsh/sessions/--<key of the cwd>--/
         session-<uuid>/session.v3.jsonl.zstd
 
+The key follows dsh's own rule: each run of `/`, backslash and `:` becomes one `-`;
+`A-Z a-z 0-9 . _ -` stay; every other UTF-16 code unit, `~` included, becomes
+`~` plus four upper-case hex digits (a space is `~0020`); leading `-` are
+removed, an empty key is `root`, and the key is cut to 251 characters.
+
 The bucket name follows from the working directory, and every worker has its
 own worktree, so the lane finds its session without a search of the whole
 store. The log is flushed per event, so its modification time is the liveness
@@ -61,10 +66,29 @@ def preflight() -> list[str]:
 
 
 def session_bucket(cwd: str | Path) -> Path:
-    # Each run of characters other than letters, digits and '-' becomes one
-    # '-': `C:\Users` gives `C-Users`, and a literal `C--Users` stays as it is.
-    slug = re.sub(r"[^A-Za-z0-9-]+", "-", str(cwd))
-    return dsh_home() / "sessions" / f"--{slug}--"
+    # A port of `projectKey` in dsh 0.1.5-rc.2, file
+    # @deepseek-ai/dsh-session-persistence-jsonl/lib/index.js (lines 874-893).
+    # It works on UTF-16 code units, as the JavaScript does.
+    text = str(cwd)
+    if not text:
+        raise ValueError("cannot encode an empty project path")
+    units = text.encode("utf-16-le")
+    readable, separator_run = [], False
+    for i in range(0, len(units), 2):
+        code = units[i] | (units[i + 1] << 8)
+        ch = chr(code)
+        if ch in "/\\:":
+            if not separator_run:
+                readable.append("-")
+            separator_run = True
+        elif ch != "~" and code < 128 and (ch.isalnum() or ch in "._-"):
+            readable.append(ch)
+            separator_run = False
+        else:
+            readable.append(f"~{code:04X}")
+            separator_run = False
+    key = ("".join(readable).lstrip("-") or "root")[:251]
+    return dsh_home() / "sessions" / f"--{key}--"
 
 
 def _log_in(session_dir: Path) -> Path | None:
@@ -182,7 +206,7 @@ def _record(spec, out_dir: Path, final: str, *, error: str | None, wall: float,
             records = read_log(copied)
     if not error:
         if session is None:
-            error = "dsh session log not found"
+            error = f"dsh session log not found in {session_bucket(spec.get('workspace') or '.')}"
         else:
             error = _turn_error(records)
     if not final.strip() and records:
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
**toolResult** for `call_34c844de2c2a4b43b1ab1bfc` (bash)

#### [13] line 13 · message · toolResult · 2026-10-02T00:16:29.699Z
diff --git a/oh-dispatch/references/campaign.md b/oh-dispatch/references/campaign.md
index 6a5ff6e..621ca63 100644
--- a/oh-dispatch/references/campaign.md
+++ b/oh-dispatch/references/campaign.md
@@ -46,6 +46,7 @@ A campaign is its own git repository under `~/ohflow-home/workflows/<na
     judge/aNN/run/            the judge's own ohflow run
   campaign.jsonl              the ledger (git-ignored, append-only)
   campaign-status.json        where the campaign is now, with the dashboard URL
+  .watch.<name>.json          a `campaign watch` cursor (git-ignored)
   ESCALATION.md               present only while a milestone waits for the operator
 ```
 
@@ -160,7 +161,9 @@ new dashboard URL since this watcher's last call. While a judge runs, line one r
 until that directory exists. The first call prints at most ten ledger events, the newest, and
 says how many it left out. A dashboard URL appears only while its run is live: the milestone
 run, then the latest judge run. The cursor lives in
-the campaign root under a name (`--cursor`, default `agent`). It exits `0` when the campaign
+the campaign root under a name (`--cursor`, default `agent`), in `.watch.<name>.json`.
+`ohflow campaign` adds `.watch.*.json` to the campaign's `.gitignore`, so a cursor never
+counts as a judge's stray edit: poll with this verb while a judge runs. It exits `0` when the campaign
 is delivered, `1` when it ended otherwise and `10` when it returns with the campaign still
 going.
 
diff --git a/oh-dispatch/references/lanes.md b/oh-dispatch/references/lanes.md
index 2720e98..2a84dd5 100644
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
@@ -130,11 +144,13 @@ Codex announces no tool list, so `rollcall_matches` checks its servers only. Its
 
 `--profile <p> "<bootstrap prompt>"`. Stdout is the final message only. Everything else is in the session log, read after exit:
 
-    ~/.dsh/sessions/--<cwd, each run of chars outside [A-Za-z0-9-] as one '-'>--/session-<uuid>/session.v3.jsonl.zstd
+    ~/.dsh/sessions/--<key of the cwd>--/session-<uuid>/session.v3.jsonl.zstd
+
+The key follows dsh's own `projectKey`: each run of `/`, `\` and `:` becomes one `-`; `A-Z a-z 0-9 . _ -` stay; every other UTF-16 code unit, `~` included, becomes `~` plus four upper-case hex digits (a space is `~0020`); leading `-` are removed; an empty key is `root`; the key is cut to 251 characters. When no session is found, the error names the bucket the runner looked in.
 
 Every worker has its own worktree, so the bucket name follows from the working directory. The lane copies the log into `<attempt>/session/`. Python 3.14's `compression.zstd` reads it. `assistant/message` records carry usage, `tool/call` and `tool/result` the actions, `request/header` the announced tools, `turn/end` the outcome.
 
-- **Liveness.** Stderr goes silent while the agent runs tools. The stall deadline also reads the session log's modification time, which moves per event. `max_iterations` is not enforced live: no event reaches the runner while the agent works. dsh spends about 30 s shutting down its MCP fleet after the answer, so allow for it in `stall_timeout_s`.
+- **Liveness.** Stderr goes silent while the agent runs tools. The stall deadline also reads the session log's modification time, which moves per event. `max_iterations` is not enforced live: no event reaches the runner while the agent works. dsh spends about 30 s shutting down its MCP fleet after the answer, so allow for it in `stall_timeout_s`. A quiet codex reasoning step has run past 180 s without an event, so the roll call gives codex 600 s.
 - **No dashboard window.** Serena opens a "Serena Dashboard" window on every start. Every dsh worker launches with `--patch scripts/ohflow/dsh_worker.patch.yml`, which restates the Serena row with `--open-web-dashboard False`.
 - **Answered but still running.** A dsh process can finish its turn and then neither print nor exit. The runner kills a dsh process 60 s after a completed `turn/end` (`OHFLOW_DSH_EXIT_GRACE_S` overrides) and takes the final message from the log. `result.json` then carries `exit_grace_killed_after_s`. Session-end hooks may be cut short.
 - **Tokens.** dsh's `inputTokens` excludes cache reads. The lane adds `cacheReadTokens` to the prompt count, as every other lane does.
diff --git a/oh-dispatch/scripts/ohflow/plans/rollcall.py b/oh-dispatch/scripts/ohflow/plans/rollcall.py
index af5ae94..2badfb5 100644
--- a/oh-dispatch/scripts/ohflow/plans/rollcall.py
+++ b/oh-dispatch/scripts/ohflow/plans/rollcall.py
@@ -26,7 +26,9 @@ Arguments: `repo` (required), `shape`, `lanes` (comma list), `count` (workers
 per lane), `consolidator`, `reviewer`, `judge` (each a lane), `profile`
 (`hermetic` for claude and codex), `carry_context`, `config` (a JSON file of
 model overrides), `base`, `prefix`, `wt_root`, `wall_timeout_s`,
-`stall_timeout_s`, `max_iterations`, `max_parallel`.
+`stall_timeout_s` (replaces the per-lane `STALL_S` table; codex gets 600 s,
+`pi`, `claude` and `dsh` get 180 s, and `host` takes no stall limit),
+`max_iterations`, `max_parallel`.
 
     python -m ohflow.cli validate --plan <this file> \\
         --args repo=<scratch repo> --args shape=merge --args lanes=pi,claude
@@ -68,6 +70,12 @@ MODELS = {
 }
 ORDER = ("pi", "claude", "codex", "dsh")
 
+#: Seconds of silence that stop a worker, per lane. Codex reasons for minutes
+#: without an event, and 180 s killed it in the first live matrix. The `host`
+#: lane has no stall capability and takes no limit, so it has no row. The plan
+#: argument `stall_timeout_s` replaces the table for every lane that takes one.
+STALL_S = {"pi": 180, "claude": 180, "codex": 600, "dsh": 180}
+
 SHAPES = ("single", "fanout", "relay", "merge", "retry", "review", "campaign")
 ALIASES = {"r0": "fanout", "r1": "relay", "r2": "merge"}
 
@@ -296,11 +304,17 @@ class Spec:
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
@@ -374,7 +388,8 @@ def normalize(args) -> Spec:
         base=base, prefix=str(args.get("prefix", "rollcall")),
         wt_root=Path(args.get("wt_root", str(repo.parent / f"{repo.name}-rollcall-wt"))),
         wall=int(args.get("wall_timeout_s", 600)),
-        stall=int(args.get("stall_timeout_s", 180)),
+        stall=(int(args["stall_timeout_s"])
+               if args.get("stall_timeout_s") not in (None, "") else None),
         max_iter=int(args.get("max_iterations", 15)),
         max_parallel=int(args.get("max_parallel", 3)), models=models)
 
@@ -406,19 +421,20 @@ def _step(spec: Spec, sid: str, lane: str, brief: str, *, worktree: str,
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
@@ -434,7 +450,7 @@ def _solo(spec: Spec, lane: str, sid: str, *, more: str = "",
     brief = brief if brief is not None else SOLO_BRIEF.format(
         lane=lane, sid=sid, entry=ENTRY, clean=CLEAN, more=more)
     return _step(spec, sid, lane, brief, worktree=sid, owns=(owns,),
-                 checks=_report_checks(owns, since=since, extra=extra),
+                 checks=_report_checks(owns, lane, since=since, extra=extra),
                  objective=f"{sid} reports for duty in {owns}", retry=retry)
 
 
@@ -479,7 +495,8 @@ def _relay(spec: Spec):
         step = _step(
             spec, sid, lane, brief, worktree="relay", owns=("ROLLCALL.md",),
             depends_on=(previous_id,) if previous_id else (),
-            checks=_report_checks("ROLLCALL.md", since="step_start", extra=extra),
+            checks=_report_checks("ROLLCALL.md", lane, since="step_start",
+                                  extra=extra),
             objective=f"{sid} appends its section to the shared ROLLCALL.md")
         phases.append(Phase(name=f"Relay {n} {sid}", steps=(step,)))
         previous_id = sid
@@ -505,8 +522,8 @@ def _merge(spec: Spec):
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
**toolResult** for `call_cec799cbff844b7cb34dcdb9` (bash)

#### [14] line 14 · message · assistant · 2026-10-02T00:16:35.506Z
<details><summary>thinking</summary>

Now let's look at the tests, the fakes, and README diff.

</details>
**toolCall bash** id=`call_cafecd2bd8c84f85a5d3012c`

```json
{
 "command": "cd C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes && git diff arch/deepening...HEAD -- oh-dispatch/README.md oh-dispatch/tests/fakes/fake_dsh.py oh-dispatch/tests/test_defect_07_detached_run_survives.py"
}
```
**toolCall bash** id=`call_6e2301edf1c243769d025364`

```json
{
 "command": "cd C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes && git diff arch/deepening...HEAD -- oh-dispatch/tests/test_defect_44_parent_session_vars_reach_no_worker.py oh-dispatch/tests/test_defect_45_hermetic_claude_loads_no_instruction_files.py"
}
```

#### [15] line 15 · message · toolResult · 2026-10-02T00:16:35.726Z
diff --git a/oh-dispatch/README.md b/oh-dispatch/README.md
index 4d9f8ff..4794ef1 100644
--- a/oh-dispatch/README.md
+++ b/oh-dispatch/README.md
@@ -26,9 +26,9 @@ The engine, the journal and the plan model sit beside these. The journal is the
 
 ## Running the suite
 
-The suite uses `unittest` from the standard library. It runs from a fresh clone and needs no network. A full run takes about fifteen minutes (875 tests, 877 s on 2026-10-01). Run it in three shards. Each shard stays under ten minutes.
+The suite uses `unittest` from the standard library. It runs from a fresh clone and needs no network. A full run takes about fifteen minutes (902 tests, 873 s on 2026-10-02). Run it in three shards. Each shard stays under ten minutes.
 
-Deterministic. Each shard takes about five minutes (312.9 s, 300.8 s and 263.2 s on 2026-10-01):
+Deterministic. Each shard takes about five minutes (328.9 s, 285.4 s and 258.4 s on 2026-10-02):
 
 ```bash
 python oh-dispatch/tests/run_tests.py --shard 1/3
@@ -86,7 +86,7 @@ Lane facts and launch rules: [lanes](references/lanes.md).
 
 - **`count`** is the number of workers per lane. `fanout:pi:3` starts three workers on `pi`.
 - **Parallelism** is the plan argument `max_parallel`. A matrix run keeps its default of 3.
-- **Wall and stall limits** are the plan arguments `wall_timeout_s` (default 600) and `stall_timeout_s` (default 180).
+- **Wall and stall limits** are the plan arguments `wall_timeout_s` (default 600) and `stall_timeout_s`. The stall limit defaults per lane: 600 s for codex, 180 s for `pi`, `claude` and `dsh`. The `host` lane takes no stall limit. The argument replaces that table for every lane that takes a limit.
 
 Pass plan arguments to `validate` and `run` with `--plan ohflow.plans.rollcall --args repo=<repo> --args shape=<shape>`.
 
@@ -97,8 +97,8 @@ Pass plan arguments to `validate` and `run` with `--plan ohflow.plans.rollcall -
 | Matrix | Cells | Contents | Wall time |
 |---|---|---|---|
 | `smoke` | 2 | `single` on `pi` and on `host` | `single pi` 31 s, `single host` 1 m 51 s (5.4 k and 87.0 k tokens, m5 acceptance run) |
-| `quick` | 10 | `single` on all five lanes; `fanout`, `relay` and `merge` on `pi`, `claude`, `codex`, `dsh`; `retry` on `pi`; `review` on `pi` then `claude` | not measured yet |
-| `full` | 15 | `quick`, plus `fanout` on `pi` with `count=3`, `campaign` on `pi`, `single` hermetic on `claude` and on `codex`, `retry` on `claude` with `carry_context` | not measured yet |
+| `quick` | 10 | `single` on all five lanes; `fanout`, `relay` and `merge` on `pi`, `claude`, `codex`, `dsh`; `retry` on `pi`; `review` on `pi` then `claude` | 24 m 27 s (1466.5 s: the sum of these ten cells' times in the first full matrix run on 2026-10-01, not a run of `quick`; 2 of the 10 failed before the m7 fixes) |
+| `full` | 15 | `quick`, plus `fanout` on `pi` with `count=3`, `campaign` on `pi`, `single` hermetic on `claude` and on `codex`, `retry` on `claude` with `carry_context` | 32 m 23 s (1942.7 s, same run; 3 of 15 cells failed before the m7 fixes) |
 
 Cost: `smoke` runs on the Z.AI flat rate. `quick` and `full` also use the seat quotas of `claude` and `codex`. `run_tests.py --e2e` runs `smoke`.
 
diff --git a/oh-dispatch/tests/fakes/fake_dsh.py b/oh-dispatch/tests/fakes/fake_dsh.py
index 551e1d1..5c7c566 100644
--- a/oh-dispatch/tests/fakes/fake_dsh.py
+++ b/oh-dispatch/tests/fakes/fake_dsh.py
@@ -1,7 +1,7 @@
 """Stand-in for `dsh --profile <p> "<task>"`.
 
 It writes a session log where real dsh writes one,
-`$DSH_HOME/sessions/--<cwd slug>--/session-<id>/session.v3.jsonl.zstd`, from
+`$DSH_HOME/sessions/--<key of the cwd>--/session-<id>/session.v3.jsonl.zstd`, from
 the real 2026-09-30 roll-call session, and prints the real final message.
 """
 
@@ -25,7 +25,22 @@ if state:
     os.makedirs(state, exist_ok=True)
     Path(state, "argv.json").write_text(json.dumps(args), encoding="utf-8")
 home = Path(os.environ["DSH_HOME"])
-bucket = home / "sessions" / ("--" + re.sub(r"[^A-Za-z0-9-]+", "-", os.getcwd()) + "--")
+
+
+def _escape(match) -> str:
+    """dsh's `projectKey` rule, written as a regex: a run of `/`, `\\` or `:` is
+    one `-`; any other character outside `A-Za-z0-9._-` is `~` plus four hex
+    digits per UTF-16 code unit."""
+    text = match.group(0)
+    if text[0] in "/\\:":
+        return "-"
+    units = text.encode("utf-16-le")
+    return "".join(f"~{int.from_bytes(units[i:i + 2], 'little'):04X}"
+                   for i in range(0, len(units), 2))
+
+
+_key = [redacted]"[/\\:]+|[^A-Za-z0-9._\-/\\:]", _escape, os.getcwd())
+bucket = home / "sessions" / ("--" + (_key.lstrip("-") or "root")[:251] + "--")
 session = bucket / f"session-{uuid.uuid4()}"
 log = session / "session.v3.jsonl.zstd"
 records = (FIXTURES / "dsh" / "l0-rollcall.session.v3.jsonl").read_bytes().splitlines(keepends=True)
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
**toolResult** for `call_cafecd2bd8c84f85a5d3012c` (bash)

#### [16] line 16 · message · toolResult · 2026-10-02T00:16:35.828Z
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
**toolResult** for `call_6e2301edf1c243769d025364` (bash)

#### [17] line 17 · message · assistant · 2026-10-02T00:16:41.893Z
<details><summary>thinking</summary>

Now the remaining test files.

</details>
**toolCall bash** id=`call_83a3aa996c354c50827969c0`

```json
{
 "command": "cd C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes && git diff arch/deepening...HEAD -- oh-dispatch/tests/test_defect_46_rollcall_report_lane_must_match_the_step.py oh-dispatch/tests/test_defect_47_rollcall_stall_limit_is_per_lane.py"
}
```
**toolCall bash** id=`call_a7527b7f0f3946eb8d875b97`

```json
{
 "command": "cd C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes && git diff arch/deepening...HEAD -- oh-dispatch/tests/test_defect_48_dsh_session_bucket_follows_dsh.py oh-dispatch/tests/test_defect_49_campaign_watch_is_not_a_stray_edit.py"
}
```

#### [18] line 18 · message · toolResult · 2026-10-02T00:16:42.102Z
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
index 0000000..20cf34b
--- /dev/null
+++ b/oh-dispatch/tests/test_defect_47_rollcall_stall_limit_is_per_lane.py
@@ -0,0 +1,44 @@
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
+    def test_the_table_has_a_row_only_for_lanes_that_take_a_limit(self):
+        for lane in LANES.split(","):
+            self.assertEqual(lane in rollcall.STALL_S,
+                             lane_info(lane).has(CAP_STALL), lane)
+
+    def test_the_argument_overrides_every_lane(self):
+        for lane, limit in self._limits(stall_timeout_s=45).items():
+            self.assertEqual(limit, 45 if lane_info(lane).has(CAP_STALL) else None, lane)
**toolResult** for `call_83a3aa996c354c50827969c0` (bash)

#### [19] line 19 · message · toolResult · 2026-10-02T00:16:42.203Z
diff --git a/oh-dispatch/tests/test_defect_48_dsh_session_bucket_follows_dsh.py b/oh-dispatch/tests/test_defect_48_dsh_session_bucket_follows_dsh.py
new file mode 100644
index 0000000..2edb2a0
--- /dev/null
+++ b/oh-dispatch/tests/test_defect_48_dsh_session_bucket_follows_dsh.py
@@ -0,0 +1,77 @@
+"""Defect 48: the dsh lane looked for its session in a bucket dsh never made.
+
+What went wrong. `session_bucket` turned each run of characters outside
+`[A-Za-z0-9-]` into one `-`. dsh's own `projectKey` (dsh 0.1.5-rc.2,
+`@deepseek-ai/dsh-session-persistence-jsonl/lib/index.js`) keeps `.` and `_`,
+writes every other code unit as `~` plus four hex digits, and turns only runs
+of `/`, `\\` and `:` into `-`. In the live matrix, `--out "$(mktemp -d)"` gave
+a worktree under `tmp.YBNLOpDXik`. dsh wrote `...-Temp-tmp.YBNLOpDXik-...` and
+the runner looked in `...-Temp-tmp-YBNLOpDXik-...`, so the dsh step failed with
+"dsh session log not found" although the worker had done its work.
+
+What is asserted here. The expected bucket names are written out by hand from
+dsh's rule, one per character class. A failed lookup names the bucket.
+"""
+
+from __future__ import annotations
+
+import os
+import tempfile
+import unittest
+from pathlib import Path
+from unittest import mock
+
+from ohflow import dsh_runner
+from ohflow.dsh_runner import session_bucket
+
+E_ACUTE = "\u00e9"
+GRINNING = "\U0001F600"
+
+CASES = [
+    ("a dot, as in mktemp -d",
+     r"C:\Users\<user>\AppData\Local\Temp\tmp.YBNLOpDXik\03-relay",
+     "--C-Users-user-AppData-Local-Temp-tmp.YBNLOpDXik-03-relay--"),
+    ("an underscore", r"C:\dev\_wt\m7_smoke", "--C-dev-_wt-m7_smoke--"),
+    ("a space", r"C:\my dir\x", "--C-my~0020dir-x--"),
+    ("a tilde", r"C:\a~b", "--C-a~007Eb--"),
+    ("a non-ASCII letter", "C:\\caf" + E_ACUTE, "--C-caf~00E9--"),
+    ("a character outside the BMP: two UTF-16 code units",
+     "C:\\x" + GRINNING, "--C-x~D83D~DE00--"),
+    ("a backslash before two hyphens", r"C:\a\--b", "--C-a---b--"),
+    ("forward slashes", "C:/Users/<user>/repo", "--C-Users-user-repo--"),
+    ("a leading separator run is dropped", r"\\server\share", "--server-share--"),
+    ("only separators", "/", "--root--"),
+    ("a path longer than 251 characters", "C:\\" + "a" * 300,
+     "--C-" + "a" * 249 + "--"),
+]
+
+
+class SessionBucketFollowsDsh(unittest.TestCase):
+    def test_each_character_class_is_encoded_as_dsh_encodes_it(self):
+        for label, cwd, expected in CASES:
+            with self.subTest(label):
+                self.assertEqual(session_bucket(cwd).name, expected)
+
+    def test_the_key_is_cut_before_the_closing_marker(self):
+        name = session_bucket("C:\\" + "a" * 300).name
+        self.assertEqual(len(name), 251 + 4)
+        self.assertTrue(name.endswith("--"))
+
+    def test_the_bucket_lies_under_the_dsh_home(self):
+        with tempfile.TemporaryDirectory() as tmp, \
+                mock.patch.dict(os.environ, {"DSH_HOME": tmp}):
+            self.assertEqual(session_bucket(r"C:\x").parent, Path(tmp) / "sessions")
+
+    def test_a_missing_session_names_the_bucket_that_was_searched(self):
+        with tempfile.TemporaryDirectory() as tmp, \
+                mock.patch.dict(os.environ, {"DSH_HOME": tmp}):
+            cwd = r"C:\w\tmp.abc"
+            result, _ = dsh_runner._record(
+                {"workspace": cwd}, Path(tmp) / "out", "done", error=None,
+                wall=1.0, session=None, version="test")
+            self.assertEqual(result["error"],
+                             f"dsh session log not found in {session_bucket(cwd)}")
+
+
+if __name__ == "__main__":
+    unittest.main()
diff --git a/oh-dispatch/tests/test_defect_49_campaign_watch_is_not_a_stray_edit.py b/oh-dispatch/tests/test_defect_49_campaign_watch_is_not_a_stray_edit.py
new file mode 100644
index 0000000..a871863
--- /dev/null
+++ b/oh-dispatch/tests/test_defect_49_campaign_watch_is_not_a_stray_edit.py
@@ -0,0 +1,57 @@
+"""Defect 49: a watcher's cursor file counted as a judge's stray edit.
+
+What went wrong. `ohflow campaign watch` keeps its cursor in
+`<campaign root>/.watch.<name>.json`. While judge a01 of milestone m7 ran, the
+campaign supervisor polled with that verb, as SKILL.md tells agents to do. The
+driver's `_stray_edits` read `git status`, saw the new cursor file outside the
+milestone directory, blamed the judge, refused its REVISE and escalated with
+"the judge changed files outside its write scope: .watch.agent.json".
+
+What is asserted here. A fake-lane campaign has a judge that REVISEs. A
+`campaign watch` call runs between the judge's start and its verdict. The
+revision commits, the milestone is delivered, no escalation is written, and the
+cursor file is ignored by git.
+"""
+
+from __future__ import annotations
+
+from ohflow import campaign as oc
+from ohflow import watch
+from support import FakeLane, WorkerScript
+from test_campaign_01_loop import (JUDGE_STEP, PRODUCT_STEP, CampaignCase, _git,
+                                   verdict)
+
+
+class WatcherCursorIsNotAStrayEdit(CampaignCase):
+
+    def test_a_watch_during_the_judge_does_not_escalate_a_revise(self):
+        camp = self.campaign()
+        product = WorkerScript(final_text="DONE\n")
+
+        def revise_while_watched():
+            (self.mdir / "briefs" / "impl.md").write_text(
+                "Do the thing, and X.\n", encoding="utf-8")
+            watch.watch_campaign(camp, timeout=0)
+
+        judge = self.judge(
+            [verdict("REVISE", revisions=[
+                {"path": "milestones/m1/briefs/impl.md", "why": "adds X"}]),
+             verdict("PASS")],
+            edits={1: revise_while_watched})
+        lane = FakeLane(scripts={PRODUCT_STEP: product, JUDGE_STEP: judge})
+
+        code = self.drive(camp, lane)
+
+        self.assertTrue((self.root / ".watch.agent.json").is_file(),
+                        "the watch must have written its cursor")
+        self.assertEqual(code, oc.EXIT_DELIVERED)
+        self.assertNotIn("escalated", self.events())
+        self.assertFalse((self.root / oc.ESCALATION).exists())
+        self.assertIn("revision_committed", self.events())
+        self.assertNotIn(".watch.agent.json",
+                         _git(self.root, "status", "--porcelain"))
+
+
+if __name__ == "__main__":
+    import unittest
+    unittest.main()
**toolResult** for `call_a7527b7f0f3946eb8d875b97` (bash)

#### [20] line 20 · message · assistant · 2026-10-02T00:17:36.716Z
<details><summary>thinking</summary>

Now let me understand what's going on. The implementer did more than the spec: fixed the dsh session bucket (defect 48), the campaign watch cursor stray edit (defect 49), the detached run test wait (bd76078). These are "smoke fixes" — attempt 1 was BLOCKED, and this attempt 2 apparently fixed more.

Now, some things to check:

1. **Exit criterion 1**: `python oh-dispatch/tests/run_tests.py -k parent_session` — should exit 0, ≥ 5 tests, one per lane.

2. **Exit criterion 2**: `-k hermetic` — exit 0, ≥ 2 tests. Note that `-k hermetic` may match many tests (hermetic is mentioned in older test files too). Fine.

3. **Exit criterion 3**: `-k report_lane` — ≥ 1 test.

4. **Exit criterion 4**: run rollcall live on three cells with env vars exported, from oh-dispatch/scripts, with `--out "$(mktemp -d)"`. This takes ~20-30 min potentially (3 cells: single host ~2 min, single claude hermetic ~1-2 min, relay pi,claude,codex,dsh ~5 min?). The relay with codex 600s stall... The first live run had relay fail at stall; with 600 s stall it should pass. I need to run this. The rules say: "Run exit criterion 4 exactly as the campaign driver does, with `--out "$(mktemp -d)"`."

But wait — the spec says "The implementer may run live cells only through ohflow rollcall --cells on the three failing cells ... at most three times each." As the reviewer, I also need to run exit criterion 4. It costs seat quotas, but the exit criteria table says to run it. The reviewer instruction says "Run the exit criteria of the spec yourself, one by one, and note each result." And #4 explicitly. OK, I'll run it.

Also careful: "with `CLAUDECODE=1`, `CLAUDE_CODE_ENTRYPOINT=claude-desktop` and `CLAUDE_AGENT_SDK_VERSION=0.3.284` exported" — on Windows bash (this box has bash — git bash?), export works. Let me check what shell: The commands run through bash tool. `mktemp -d` exists in git bash. Good.

5. **Exit criterion 5**: grep "not measured yet" README — no match.

Then the adversarial checks:
- grep every place an environment is built for a child: `env=dict(os.environ)` or `os.environ` copies — need to search all runners. Are there places that still pass CLAUDE*? E.g., `seat_env` used by claude/codex/dsh; pi and host use worker_env now; CliLane uses worker_env. What about other child spawns: `campaign.py` spawning drivers? `watch.py`? The spec says "every worker, on every lane". But check for other launches of workers, e.g. `cli_lane.py`'s lane runner process → that runner process (run_lane.py?) then spawns the CLI with seat_env... wait.

Actually let me think about the architecture: `CliLane.launch` spawns a runner python process (the lane's python interpreter) with `env = worker_env()` (this is the runner process). Then the adapter (`prepare`) builds `env=seat_env()` for the actual CLI (claude.exe etc.). `seat_env` uses `proc.worker_env()`. So the chain strips twice, fine.

But is there any other place that builds an env for a child? Let me grep `dict(os.environ)` and `os.environ.copy()` in scripts.

- Hermetic claude session can still read user's instruction files or settings, or loses login: The claim is `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` disables CLAUDE.md loading, `--setting-sources project,local` drops user settings. Keeps login: login is stored in `~/.claude/.credentials.json` or keychain; setting-sources doesn't affect auth. But wait — is `--setting-sources` passed only in hermetic profile? Let me look at `build_command` in claude_runner to see. Also check that `--setting-sources project,local` doesn't include "user" — right, that's what drops user settings. Does it keep the login? In Claude Code, `--setting-sources` controls which settings files load, not credentials. Also `managed settings`? Hmm.

Potential issue: `CLAUDE_CODE_DISABLE_CLAUDE_MDS` — need to verify this is a real env var. There is a known env var `CLAUDE_CODE_DISABLE_CLAUDE_MDS` ... Actually I recall `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`, `CLAUDE_CODE_DISABLE_TERMINAL_TITLE`... Hmm, is there a `CLAUDE_CODE_DISABLE_CLAUDE_MDS`? Hmm. There is `--no-claude-md` flag? Actually I don't think `--no-claude-md` exists... In newer versions there is `CLAUDE_CODE_DISABLE_CLAUDE_MDS`? Hmm, hard to verify. But the implementer says "Measured 2026-10-01 (2.1.281)" and presumably verified with `claude --help` / live cell (exit criterion 4 includes the live hermetic cell; if it passes rollcall_matches with the user's MCP servers... wait, rollcall_matches checks tools/servers announced vs reported).

But exit criterion 4's live run will tell us whether the hermetic profile actually works. If the worker still loads ~/.claude/CLAUDE.md's MCP servers, the harness announced servers come from... hmm, the hermetic plan step passes surface and `--mcp-config` — the harness announcement is the `system init` event which lists MCP servers configured. If `--strict-mcp-config` and `--mcp-config` plan-named only, then init announces only plan servers regardless of CLAUDE.md. So the live gate could pass even if CLAUDE.md still loaded (affects the system prompt context but not announced servers). Hmm, actually in the original failure, the worker *named* ten MCP servers — it reported them because its context (CLAUDE.md) told it about them. So the failure was the report vs announcement mismatch. With `--strict-mcp-config`, announced servers are restricted; the worker's report of the ten servers failed. Now with CLAUDE.md disabled, the worker no longer mentions them. So a live pass is good evidence CLAUDE.md is not loaded. 

- Stall limit a lane's normal silence can still trip: codex gets 600. What about dsh? dsh shuts down MCP fleet ~30s after answer; stall reads session log mtime which moves per event. pi 180. host none. OK. But what about the *host* lane — no stall limit at all. Host steps could hang forever? There's still wall_timeout_s=600. Fine.

Wait — one more: `stall_for` returns `None` when the lane lacks CAP_STALL. For host, `STALL_S` has no row — good, and test checks table rows == lanes with CAP_STALL. But what about other lanes in `lanes.py` registry — e.g., fake lanes used in campaign plans? `lane_info(lane).has(CAP_STALL)` — fake lanes presumably lack CAP_STALL, so `stall_for` returns None without consulting STALL_S — no KeyError. But `_step` is used for roll-call steps only, with lanes from ORDER + host. OK.

But wait — `stall_for` checks `lane_info(lane).has(CAP_STALL)`; if a lane has CAP_STALL but is not in STALL_S and stall arg is None → KeyError. Test `test_the_table_has_a_row_only_for_lanes_that_take_a_limit` checks equivalence for the five lanes in LANES. What lanes exist with CAP_STALL? Let me check lanes.py registry — maybe `host` lacks, `fake`? Let me look.

- A report whose `lane` names another lane and still passes the gate: `rollcall_matches` now fails. But note `schema_valid` — the schema ROLLCALL_SCHEMA presumably requires `lane`? And other shapes' `_report_checks` — all callers updated? `_solo`, `_relay`, `_merge` pass lane; `_fanout`? Let me check the full rollcall.py to see if `_fanout` and others call `_report_checks`. The diff shows `_solo`, `_relay`, `_merge` updated. What about fanout/retry/review/campaign shapes — do they use `_solo`? Probably `fanout` uses `_solo`. Let me read the whole file.

- README figures match measured matrix.json: quick 24 m 27 s sum of the ten cells; full 32 m 23 s = 1942.7 s. I can verify from the matrix.json at the given path: sum cell times for quick cells and total. Let me check.

- dsh session bucket vs dsh's own projectKey: I can read the actual dsh source at the given path and compare. The rule: `/ \ :` runs → `-`; `[A-Za-z0-9._-]` stay; else `~XXXX` hex (UTF-16 code unit); leading `-` stripped; empty → root; cut to 251 chars. The Python port: iterate UTF-16 code units. `ch.isalnum()` — careful: `ch.isalnum()` for a single ASCII char like `a` is True; but code < 128 and ch.isalnum() — for ASCII, isalnum is [0-9A-Za-z]. Also `ch in "._-"`. Non-ASCII excluded by `code < 128`. `~` excluded explicitly. Separator run: consecutive separators collapse to one `-`; but does a `~XXXX` reset separator_run? In the JS, presumably: separator handling — let me read the actual JS to verify exactly, especially: is the separator-run logic like that? Also does the escape happen before or after? Let me read the JS file.

Also `readable.append(f"~{code:04X}")` — if code > 0xFFFF? Not possible from UTF-16 units. Format with 4 hex digits uppercase — matches "~D83D~DE00". What about a code that needs... all UTF-16 units are ≤ 0xFFFF, so 4 digits always enough. Good.

Edge: `chr(code).isalnum()` for code < 128 — but what about characters like `+`, `,`? Not alnum → escaped. Space → `~0020`. OK.

Edge: the JS might treat `~` (0x7E) as escaped because of the special meaning — the Python does that. Need to verify with the actual JS.

Also: does JS uppercase or lowercase hex? `~00E9` suggests uppercase. Need to check JS `toString(16).toUpperCase().padStart(4,'0')`.

Also the truncation: is it exactly 251? And is the leading `-` strip before or after truncation? Python: lstrip then truncate. Need to check JS.

Also "a path longer than 251 characters" case: `"C:\\" + "a"*300` → key = `C-aaa...` (C, then separator run of `\` → `-`, then 300 a's) = 1+1+300 = 302 chars, truncated to 251 = `C-` + 249 a's. Name = `--` + 251 + `--` = 255. Test asserts len == 255 and endswith `--`. But wait, what does dsh do — truncate to 251 then wrap in `--...--`? Need to check JS.

Let me read the actual dsh JS file to verify.

- A test that passes both with and without its fix: I should verify defect tests fail against old code. The gate says implementer proved it; as reviewer I can spot-check by stashing changes... that's harder. I could check out the parent commit code for a specific function and run the new test against it. For example, test_defect_44 against old code: old seat_runner had the strip for claude/codex/dsh but not pi/host — test would fail on pi/host launch. That's credible. For defect_46: old rollcall_matches without lane check — new tests would fail. Credible from reading code. For 48: old slug rule differs → fails. For 45: old prepare had no HERMETIC_ENV → test fails. For 47: old plan had single stall=180 → codex ≥ 600 fails. For 49: old ensure_ignores without `.watch.*.json` → git status shows the cursor → escalate; test would fail. All credible.

Maybe I can actually run one or two of these against the base to be rigorous? I can do: `git stash`? No, changes are committed. I can create a temp worktree at the base commit? That's creating things... "Create nothing inside the worktree" — a temp worktree outside the current worktree is fine (in temp dir). But `git worktree add` writes to .git of the shared repo... The repo is the shared checkout? No — the worktree `C:\Users\<user>\dev\_wt\oh-dispatch-deepening\m7-smoke-fixes` is a worktree of the product repo `C:\Users\<user>\.agents\skills`. Adding a worktree writes metadata to the shared checkout's .git dir. The rules say "never touch the shared checkout at C:\Users\<user>\.agents\skills (only your worktree)" — git worktree add modifies .git/worktrees in the shared checkout. Risky; forbidden-ish. Alternative: copy files to a temp dir. I can copy the whole oh-dispatch dir from base commit (`git show arch/deepening:...`) into a temp dir and run the new tests there? Tests import ohflow package; I'd need the package structure. Simplest: create temp dir, `git archive arch/deepening | tar -x -C tmpdir`, then copy the new test files in, run tests. That doesn't touch the repo. But new tests import from `support` which exists at base? TempCase exists presumably. The new tests also import `ohflow.watch` (exists at base). fake_dsh changes... test 49 imports from test_campaign_01_loop. OK.

Doing this for all 7 defect tests is heavy; maybe do it for the most doubtful ones: 44 (needs `lanes.lane_for`, `spec_json` at base — signature might differ), 46, 47, 48 are cheap (pure functions). Let me try 46/47/48/45 quickly via git archive.

Actually, the instructions say "Look for ... a test that passes both with and without its fix". A reasonable spot check on a couple of them suffices, plus reading.

- Prose that contradicts code: lanes.md says claude hermetic keeps "the project's own `.claude` files" (because setting-sources project,local and CLAUDE_CODE_DISABLE_CLAUDE_MDS disables *all* CLAUDE.md? Hmm — does CLAUDE_CODE_DISABLE_CLAUDE_MDS disable project CLAUDE.md too? If the variable disables ALL claude.md (project included), then "keeps the project's own `.claude` files" might be wrong. But `.claude` files could mean `.claude/settings.json` etc. (settings sources), not CLAUDE.md. The doc says "the user's instruction files (`CLAUDE_CODE_DISABLE_CLAUDE_MDS=1`), the user's settings (`--setting-sources project,local`) ... keeps ... the project's own `.claude` files". `.claude` directory files = settings, commands, agents — those come from project settings source. Plausibly true.

Let me now verify things concretely. Plan of commands:

1. Read charter ✓. 
2. Read remaining relevant code: rollcall.py full, claude_runner build_command, lanes.py registry (CAP_STALL), gates.py schema_valid/ROLLCALL_SCHEMA lane requirement.
3. Grep for env building for children across scripts.
4. Read dsh projectKey JS.
5. Verify README matrix numbers against matrix.json.
6. Run exit criteria 1, 2, 3, 5 (fast).
7. Run suite shards 1-3 (each under 10 min).
8. Run exit criterion 4 (live, ~10+ min).
9. Spot-check defect tests fail against base (via git archive to temp).

Order matters: do quick greps first, then run tests (foreground), then live rollcall, then shards maybe. Actually shards take ~5 min each = 15 min total. Live rollcall: relay cell with codex 600 s stall — could take ~5-8 min. Total fine.

Careful: never run two suites at once. Run sequentially.

Let me start with reading code.

</details>
The diff is read. Now let me read the surrounding code that the diff leans on: the full rollcall plan, the claude command builder, the lane registry's `CAP_STALL`, and every place that builds an environment for a child.
**toolCall bash** id=`call_eeae834bedc94be189e130c0`

```json
{
 "command": "cd C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes && grep -rn \"dict(os.environ)\\|os.environ.copy()\\|environ\\[\" oh-dispatch/scripts/ohflow --include=*.py | grep -v tests"
}
```
**toolCall bash** id=`call_6b665a521efe401bbde9002d`

```json
{
 "command": "cd C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes && sed -n 1,120p oh-dispatch/scripts/ohflow/plans/rollcall.py"
}
```

#### [21] line 21 · message · toolResult · 2026-10-02T00:17:36.833Z
oh-dispatch/scripts/ohflow/cli.py:342:        env = dict(os.environ)
oh-dispatch/scripts/ohflow/cli.py:787:        env = dict(os.environ)
oh-dispatch/scripts/ohflow/exec.py:81:    child_env = dict(os.environ)
**toolResult** for `call_eeae834bedc94be189e130c0` (bash)

#### [22] line 22 · message · toolResult · 2026-10-02T00:17:36.878Z
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
`pi`, `claude` and `dsh` get 180 s, and `host` takes no stall limit),
`max_iterations`, `max_parallel`.

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
#: without an event, and 180 s killed it in the first live matrix. The `host`
#: lane has no stall capability and takes no limit, so it has no row. The plan
#: argument `stall_timeout_s` replaces the table for every lane that takes one.
STALL_S = {"pi": 180, "claude": 180, "codex": 600, "dsh": 180}

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
**toolResult** for `call_6b665a521efe401bbde9002d` (bash)

#### [23] line 23 · message · assistant · 2026-10-02T00:17:42.741Z
<details><summary>thinking</summary>

Let me see the rest of rollcall.py, the places in cli.py and exec.py that build envs (are those worker launches?), and the lanes registry.

</details>
**toolCall bash** id=`call_b1f28531fb424332baa738ec`

```json
{
 "command": "cd C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes && sed -n 330,360p oh-dispatch/scripts/ohflow/cli.py && echo ---- && sed -n 775,800p oh-dispatch/scripts/ohflow/cli.py && echo ---- && sed -n 70,95p oh-dispatch/scripts/ohflow/exec.py"
}
```
**toolCall bash** id=`call_1f6b5d69e9cb4ecab5a4225a`

```json
{
 "command": "cd C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes && grep -n \"CAP_STALL\\|def lane_info\\|^LANES\\|^CAP_\" oh-dispatch/scripts/ohflow/lanes.py | head -40 && echo ---- && grep -n \"stall_for\\|_report_checks\\|STALL_S\" oh-dispatch/scripts/ohflow/plans/rollcall.py"
}
```

#### [24] line 24 · message · toolResult · 2026-10-02T00:17:42.851Z
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
----
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
----
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
**toolResult** for `call_b1f28531fb424332baa738ec` (bash)

#### [25] line 25 · message · toolResult · 2026-10-02T00:17:42.856Z
30:CAP_STALL = "stall_timeout"
32:CAP_CARRY = "carry_context"
34:CAP_OAUTH = "oauth"
36:CAP_PROFILE = "profile"
38:CAP_QUALIFIED_MCP = "qualified_mcp"
40:CAP_TOOLS_ONLY = "tools_only"
59:                   frozenset({CAP_STALL, CAP_CARRY, CAP_QUALIFIED_MCP})),
61:                       frozenset({CAP_STALL, CAP_CARRY, CAP_OAUTH, CAP_PROFILE,
64:                      frozenset({CAP_STALL, CAP_OAUTH, CAP_PROFILE,
67:                    frozenset({CAP_STALL, CAP_OAUTH, CAP_PROFILE,
71:LANES = frozenset(LANE_INFO)
74:def lane_info(name: str) -> LaneInfo:
----
29:`stall_timeout_s` (replaces the per-lane `STALL_S` table; codex gets 600 s,
77:STALL_S = {"pi": 180, "claude": 180, "codex": 600, "dsh": 180}
307:    stall: int | None          # the caller's override; None takes STALL_S
312:    def stall_for(self, lane: str) -> int | None:
316:        return self.stall if self.stall is not None else STALL_S[lane]
426:                stall_timeout_s=spec.stall_for(lane), schema=schema,
433:def _report_checks(owns: str, lane: str, *, since: str = "base",
453:                 checks=_report_checks(owns, lane, since=since, extra=extra),
498:            checks=_report_checks("ROLLCALL.md", lane, since="step_start",
525:        checks=_report_checks("ROLLCALL.md", spec.consolidator,
**toolResult** for `call_1f6b5d69e9cb4ecab5a4225a` (bash)

#### [26] line 26 · message · assistant · 2026-10-02T00:17:57.846Z
<details><summary>thinking</summary>

The `dict(os.environ)` in cli.py at 342 and 787 are the detached supervisor launches (ohflow's own supervisor, not a worker) — those are ohflow itself, not a worker; CLAUDE* reaching the supervisor is fine since the supervisor's launches of workers go through worker_env/seat_env. Actually wait — the supervisor spawns the engine, which spawns lanes via CliLane.launch → worker_env. So the strip happens at the worker seam. Good. exec.py's `child_env` is the generic `ohflow` exec for command steps (the "command" step kind, e.g. shell commands in plans) — is that a "worker"? It's a command step, not an agent worker. The spec says "One rule removes the launching session's variables from every worker, on every lane." Command steps are not lane workers. Hmm — but could CLAUDE* in a command step's env matter? A command step runs a shell command; CLAUDE* would leak but that's the operator's own command. The matrix rollcall doesn't use command steps for reporting. I'd note but not block. Actually wait — does the host lane use exec.py? The host lane runs OpenHands python. No.

Hmm, but hold on: cli_lane.py builds `env = worker_env()` for the lane runner process. But then the runner process — what is it? Let me check: CliLane.launch spawns `self.python -m ohflow.run_lane` (or similar) with env. That runner then calls adapter.prepare(spec).env → seat_env() → strip again (runner's own env, which already lacks CLAUDE*). And HostLane launches worker.py's host main with worker_env(). Good.

Also check pi_runner: `env = proc.worker_env()` then sets PI_CODING_AGENT_DIR, PI_OFFLINE, and OHFLOW_BASH from os.environ. Good.

Now, is there anywhere else workers get launched? `campaign.py` spawns judges via lanes (fake lane in tests; in real campaigns through lanes). The `campaign` detach in cli.py:787 — the campaign driver process itself, not a worker.

Also `seat_env` in seat_runner — used by claude/codex/dsh adapters. Let me confirm codex_runner and dsh_runner use seat_env. Let me grep.

Also check `seat_runner.py` still imports `re` — it removed the regex; check for unused import (flake-level, not blocking, but cleanliness). Let me check the file.

Next: the gates.py change — `schema_valid` requires `lane`? Let me check ROLLCALL_SCHEMA: does it require "lane"? REPORT template includes `"lane": "{lane}"` in the JSON. The schema file references/examples/rollcall/rollcall.schema.json — check required fields. If schema requires lane, then report_lane missing fails schema_valid too; fine.

Now, the important adversarial check: does `rollcall_matches`'s new lane check also verify... the *harness-announced* record vs report lane? Fine.

Next: dsh projectKey JS. Let me read the file at the given path.

</details>
The `dict(os.environ)` hits are the detached supervisor and campaign driver (ohflow itself, not workers) and the generic command-step exec. Let me check the remaining seams: codex/dsh adapters' env, `seat_runner` leftovers, the schema, and the full lanes registry.
**toolCall bash** id=`call_fbaffea3e77f400193accd1c`

```json
{
 "command": "cd C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes && grep -n \"seat_env\\|worker_env\" oh-dispatch/scripts/ohflow/*.py && echo ---- && sed -n 1,45p oh-dispatch/scripts/ohflow/seat_runner.py && echo ---- && sed -n 50,75p oh-dispatch/scripts/ohflow/lanes.py"
}
```
**toolCall bash** id=`call_b278d9171b844b7e867881b8`

```json
{
 "command": "cd C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes && python -c \"\nimport json,sys\ns=json.load(open('oh-dispatch/references/examples/rollcall/rollcall.schema.json',encoding='utf-8'))\nprint(json.dumps(s,indent=1))\" | head -40"
}
```

#### [27] line 27 · message · toolResult · 2026-10-02T00:17:58.005Z
oh-dispatch/scripts/ohflow/claude_runner.py:23:                          run_quiet, runner_main, seat_activity, seat_env,
oh-dispatch/scripts/ohflow/claude_runner.py:336:            env=seat_env(HERMETIC_ENV if hermetic else None),
oh-dispatch/scripts/ohflow/cli_lane.py:16:from .proc import spawn_managed, worker_env
oh-dispatch/scripts/ohflow/cli_lane.py:251:        env = worker_env()
oh-dispatch/scripts/ohflow/codex_runner.py:28:                          runner_main, seat_activity, seat_env, seat_trace,
oh-dispatch/scripts/ohflow/codex_runner.py:313:                                  cwd=Path(str(spec["workspace"])), env=seat_env(extra),
oh-dispatch/scripts/ohflow/dsh_runner.py:41:                          runner_main, seat_activity, seat_env, seat_trace,
oh-dispatch/scripts/ohflow/dsh_runner.py:376:                                  env=seat_env(), context={"started": time.time()})
oh-dispatch/scripts/ohflow/pi_runner.py:163:        env = proc.worker_env()
oh-dispatch/scripts/ohflow/proc.py:24:def worker_env(base: Mapping[str, str] | None = None) -> dict[str, str]:
oh-dispatch/scripts/ohflow/seat_runner.py:39:def seat_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
oh-dispatch/scripts/ohflow/seat_runner.py:40:    env = proc.worker_env()
oh-dispatch/scripts/ohflow/seat_runner.py:104:                            env=dict(env) if env is not None else seat_env())
oh-dispatch/scripts/ohflow/worker.py:26:from .proc import spawn_managed, worker_env
oh-dispatch/scripts/ohflow/worker.py:154:        env = worker_env()
----
"""Shared parts of the claude, codex and dsh runners.

These three lanes start a seat: an agent CLI that signs in with its own login
and, by default, loads the seat's usual setup. Each lane is one adapter module
on `cli_lane.CliAgentRuntime`; this module holds what the three share.

Two launch rules hold for all three:

- The npm `.cmd` shim is resolved to its real target (`claude.exe`, or `node`
  plus a `.js` entry point). No argument passes through `cmd.exe`, so quotes,
  `&` and `%` in an argument arrive intact, and the 8191-character `cmd.exe`
  limit does not apply.
- The agent gets one short bootstrap prompt that points at `brief.md`. The
  brief itself never goes on the command line.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from . import activity as act
from . import attempt_record, proc
from .lanes import CAP_TOOLS_ONLY, lane_info, lanes_with
from .proc import guard_current_process_tree


NPM_DIR = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "npm"

def seat_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    env = proc.worker_env()
    env["PYTHONIOENCODING"] = "utf-8"
    env.update(extra or {})
    return env


----
    caps: frozenset[str] = frozenset()

    def has(self, cap: str) -> bool:
        return cap in self.caps


LANE_INFO: dict[str, LaneInfo] = {
    DEFAULT_LANE: LaneInfo(DEFAULT_LANE, "ohflow.host_artifacts"),
    "pi": LaneInfo("pi", "ohflow.pi_runner",
                   frozenset({CAP_STALL, CAP_CARRY, CAP_QUALIFIED_MCP})),
    "claude": LaneInfo("claude", "ohflow.claude_runner",
                       frozenset({CAP_STALL, CAP_CARRY, CAP_OAUTH, CAP_PROFILE,
                                  CAP_QUALIFIED_MCP, CAP_TOOLS_ONLY})),
    "codex": LaneInfo("codex", "ohflow.codex_runner",
                      frozenset({CAP_STALL, CAP_OAUTH, CAP_PROFILE,
                                 CAP_QUALIFIED_MCP})),
    "dsh": LaneInfo("dsh", "ohflow.dsh_runner",
                    frozenset({CAP_STALL, CAP_OAUTH, CAP_PROFILE,
                               CAP_QUALIFIED_MCP})),
}

LANES = frozenset(LANE_INFO)


def lane_info(name: str) -> LaneInfo:
    try:
**toolResult** for `call_fbaffea3e77f400193accd1c` (bash)

#### [28] line 28 · message · toolResult · 2026-10-02T00:17:58.007Z
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
**toolResult** for `call_b278d9171b844b7e867881b8` (bash)

#### [29] line 29 · message · assistant · 2026-10-02T00:18:08.973Z
<details><summary>thinking</summary>

Good:
- `seat_env` strips via `proc.worker_env()`; claude/codex/dsh adapters use it. pi/host/CliLane use worker_env. All worker launches covered.
- The default lane ("host"? DEFAULT_LANE) has no caps → no CAP_STALL → stall_for returns None without touching STALL_S. Lanes with CAP_STALL: pi, claude, codex, dsh — exactly STALL_S rows. Good, no KeyError possible.
- Schema requires `lane` (a string, any value). So a wrong lane passes schema_valid but fails rollcall_matches. Consistent with the spec: "The roll-call gate fails a report whose `lane` is not the step's lane".
- One nit: `seat_runner.py` still imports `re` — is `re` still used elsewhere in that file? Let me check. The regex moved to proc.py. Let me grep for `re\.` in seat_runner.

Also note: in `proc.py`, `worker_env` regex `^(CLAUDE|CLAUDECODE$|ANTHROPIC_BASE_URL$)` — hmm, one subtlety: `CLAUDECODE` is matched by first alternative anyway; the second alternative is redundant but harmless. Also the regex as `re.match` — `worker_env` uses `_PARENT_SESSION_VARS.match(k)` — match anchors at start. `^(CLAUDE|...)` fine.

Wait, one more check on the regex: does it strip `CLAUDE.md`-related... no. Does it strip `ANTHROPIC_AUTH_TOKEN`? Not matched (only BASE_URL exact). Does it strip `CLAUDE_CODE_DISABLE_CLAUDE_MDS` if set by the user? Yes, but HERMETIC_ENV re-adds it after. Good — and the docstring says "A variable a lane sets on purpose is added afterwards."

Now the dsh projectKey: read the JS file. Path: `%APPDATA%\npm\node_modules\@deepseek-ai\dsh\node_modules\@deepseek-ai\dsh-session-persistence-jsonl\lib\index.js` lines ~874-893.

</details>
All five lanes strip at their seams, and `STALL_S` rows exactly match `CAP_STALL` lanes. Now the dsh `projectKey` source of truth:
**toolCall bash** id=`call_7bdf3a1f12a84e5f83794fc5`

```json
{
 "command": "sed -n 860,910p \"$APPDATA/npm/node_modules/@deepseek-ai/dsh/node_modules/@deepseek-ai/dsh-session-persistence-jsonl/lib/index.js\""
}
```
**toolCall bash** id=`call_fbeb62125a334f7c93d94f60`

```json
{
 "command": "cd C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes && grep -n \"re\\.\" oh-dispatch/scripts/ohflow/seat_runner.py | head && grep -rn \"not measured yet\" oh-dispatch/README.md; echo \"grep exit: $?\""
}
```

#### [30] line 30 · message · toolResult · 2026-10-02T00:18:09.134Z
		if (ch !== "~" && /^[A-Za-z0-9._-]$/.test(ch)) out += ch;
		else out += "~" + code.toString(16).toUpperCase().padStart(4, "0");
	}
	return out;
}
/**
* Build the readable directory key for a project path.
* Filesystem separators and drive separators become `-`; unsafe code units use
* the same `~XXXX` escape as session ids. The key is bounded for filesystem
* component limits. Separator replacement and truncation are intentionally
* lossy, following the common human-navigable project-directory convention.
* @param cwd - the session's project directory.
* @returns a single filesystem-safe project directory name.
*/
function projectKey(cwd) {
	if (cwd.length === 0) throw new Error("cannot encode an empty project path");
	let readable = "";
	let separatorRun = false;
	for (let i = 0; i < cwd.length; i++) {
		const code = cwd.charCodeAt(i);
		const ch = String.fromCharCode(code);
		if (ch === "/" || ch === "\\" || ch === ":") {
			if (!separatorRun) readable += "-";
			separatorRun = true;
		} else if (ch !== "~" && /^[A-Za-z0-9._-]$/.test(ch)) {
			readable += ch;
			separatorRun = false;
		} else {
			readable += "~" + code.toString(16).toUpperCase().padStart(4, "0");
			separatorRun = false;
		}
	}
	return `--${(readable.replace(/^-+/, "") || "root").slice(0, 251)}--`;
}
/**
* The configured root's human-navigable project directory. A configured root
* may be local or shared; this grouping does not prescribe its deployment.
* @param root - the backend's session root directory.
* @param cwd - the session's project directory; `undefined` selects `_no-cwd`.
* @returns the project directory path under `root`.
*/
function projectDir(root, cwd) {
	if (cwd === void 0) return join(root, "_no-cwd");
	return join(root, projectKey(cwd));
}
/**
* The directory owned by one session and available for future session-local
* artifacts.
* @param root - the backend's session root directory.
* @param cwd - the session's project directory.
* @param id - the session id, encoded to one safe path segment.
**toolResult** for `call_7bdf3a1f12a84e5f83794fc5` (bash)

#### [31] line 31 · message · toolResult · 2026-10-02T00:18:09.137Z
5:on `cli_lane.CliAgentRuntime`; this module holds what the three share.
52:    found = re.findall(r'"%dp0%\\([^"]+\.(?:exe|js|cjs|mjs))"', text)
224:        if not isinstance(profile, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", profile):
grep exit: 1
**toolResult** for `call_fbeb62125a334f7c93d94f60` (bash)

#### [32] line 32 · message · assistant · 2026-10-02T00:18:27.872Z
<details><summary>thinking</summary>

The JS `projectKey`:
```js
if (ch === "/" || ch === "\\" || ch === ":") {
    if (!separatorRun) readable += "-";
    separatorRun = true;
} else if (ch !== "~" && /^[A-Za-z0-9._-]$/.test(ch)) {
    readable += ch;
    separatorRun = false;
} else {
    readable += "~" + code.toString(16).toUpperCase().padStart(4, "0");
    separatorRun = false;
}
return `--${(readable.replace(/^-+/, "") || "root").slice(0, 251)}--`;
```

Python port:
- separators `/\\:` → one `-` if not separatorRun; matches.
- `ch != "~" and code < 128 and (ch.isalnum() or ch in "._-")` — for code < 128, `ch.isalnum()`: careful — Python's `str.isalnum()` for ASCII is [0-9A-Za-z]. But wait, `code < 128` excludes non-ASCII, good. But there's a subtlety: `ch.isalnum()` for ASCII characters — e.g., `¹` is not ASCII. OK. But what about ASCII control chars? Not alnum → escaped. Good.
- escape `~{code:04X}` uppercase, pad 4. matches.
- `key = ("".join(readable).lstrip("-") or "root")[:251]` — JS: `readable.replace(/^-+/, "")` strips only leading `-`, then `|| "root"`, then `.slice(0, 251)`. Python `lstrip("-")` strips all leading `-` — same as regex `^-+` (replace removes the whole leading run). Same. `or "root"` same. slice 251 same. Wrap `--...--` same.

One difference: JS `readable.replace(/^-+/, "")` — replaces one leading run of `-`. Python `.lstrip("-")` — identical semantics. Good.

Edge: what if the entire readable is separators, e.g. "/" → readable="-", lstrip → "" → "root". Python: same → `--root--`. Test expects `--root--`. ✓.

Edge: `"\\server\share"` → readable "-server-share", lstrip "-" → "server-share". ✓ matches test.

Edge: `C:\a\--b` → "C", sep run → "-a-" wait: "C" then ":" sep → "-", "\" sep (run) → nothing, "a" → "a", "\" → "-", then "-" is in readable class (`._-` includes "-") → "-", "-" → "-", then "b". So readable = "C-a---b" → name "--C-a---b--". Test expects that. ✓.

Truncation edge: Python `[:251]` applies after lstrip; JS slice(0,251) after replace. Same.

BUT: one real subtlety — JS works on `cwd.length` and `charCodeAt` — UTF-16 code units. Python decodes utf-16-le in pairs — same code units. ✓.

What about a lone surrogate? Python `chr(0xD83D)` is fine; encode("utf-16-le") of a str containing a lone surrogate would fail to encode! `text.encode("utf-16-le")` with a lone surrogate raises UnicodeEncodeError. But dsh's own rule handles lone surrogates. Windows paths can't contain lone surrogates in practice (well, they can via some APIs but not normally). Minor, not blocking.

Hmm wait, actually one more important check: does dsh use `projectKey(cwd)` with cwd = the process working directory? Yes — the lane sets cwd=workspace. Fine.

Also the test in fake_dsh.py mirrors the rule with a regex `_key = [redacted]"[/\\:]+|[^A-Za-z0-9._\-/\\:]", _escape, os.getcwd())` then lstrip and cut. Equivalent. OK.

Now: `re` still used in seat_runner (line 52, 224) — the import stays legitimately.

Criterion 5 passes (grep no match).

Now the README matrix figures. Check matrix.json from the first live run: `C:\Users\<user>\AppData\Local\Temp\claude\C--Users-user\bb0fac07-fb14-4ec9-82d9-33b3b7c2e4f4\scratchpad\matrix-full\matrix.json`. Let me verify: sum of the ten quick cells' times = 1466.5 s? And total = 1942.7 s.

</details>
The `projectKey` port matches the JS line for line (separator runs, the `~XXXX` escape, `lstrip` = `replace(/^-+/,"")`, `root`, the 251 cut, the `--` wrap). Criterion 5 already passes (no "not measured yet"). Now the README figures against the measured `matrix.json`:
**toolCall bash** id=`call_142078552fd04207a4a19803`

```json
{
 "command": "python -c \"\nimport json\np=r'C:/Users/<user>/AppData/Local/Temp/claude/C--Users-user/bb0fac07-fb14-4ec9-82d9-33b3b7c2e4f4/scratchpad/matrix-full/matrix.json'\nm=json.load(open(p,encoding='utf-8'))\nprint(type(m), list(m)[:10] if isinstance(m,dict) else len(m))\n\" "
}
```

#### [33] line 33 · message · toolResult · 2026-10-02T00:18:28.012Z
<class 'dict'> ['matrix', 'configuration', 'repo', 'out', 'cells_total', 'cells']
**toolResult** for `call_142078552fd04207a4a19803` (bash)

#### [34] line 34 · message · assistant · 2026-10-02T00:18:33.902Z
**toolCall bash** id=`call_9533fc76fe3049c394745232`

```json
{
 "command": "python -c \"\nimport json\np=r'C:/Users/<user>/AppData/Local/Temp/claude/C--Users-user/bb0fac07-fb14-4ec9-82d9-33b3b7c2e4f4/scratchpad/matrix-full/matrix.json'\nm=json.load(open(p,encoding='utf-8'))\nprint('matrix:', m['matrix'], 'total cells:', m['cells_total'])\ntot=0\nfor c in m['cells']:\n    print(c.get('cell'), c.get('result'), c.get('wall_s'), c.get('passed'))\n    tot += c.get('wall_s') or 0\nprint('sum all wall_s:', round(tot,1))\n\""
}
```

#### [35] line 35 · message · toolResult · 2026-10-02T00:18:33.977Z
matrix: full total cells: 15
None None None None
None None None None
None None None None
None None None None
None None None None
None None None None
None None None None
None None None None
None None None None
None None None None
None None None None
None None None None
None None None None
None None None None
None None None None
sum all wall_s: 0
**toolResult** for `call_9533fc76fe3049c394745232` (bash)

#### [36] line 36 · message · assistant · 2026-10-02T00:18:36.729Z
<details><summary>thinking</summary>

The cell dicts have different keys. Let me dump one cell.

</details>
**toolCall bash** id=`call_81fb9edf952145f8818165e4`

```json
{
 "command": "python -c \"\nimport json\np=r'C:/Users/<user>/AppData/Local/Temp/claude/C--Users-user/bb0fac07-fb14-4ec9-82d9-33b3b7c2e4f4/scratchpad/matrix-full/matrix.json'\nm=json.load(open(p,encoding='utf-8'))\nprint(json.dumps(m['cells'][0],indent=1)[:800])\nprint('KEYS:', sorted(m['cells'][0].keys()))\n\""
}
```

#### [37] line 37 · message · toolResult · 2026-10-02T00:18:36.797Z
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
}
KEYS: ['count', 'index', 'label', 'lanes', 'options', 'reason', 'resume', 'run_dir', 'seconds', 'shape', 'tokens', 'verdict']
**toolResult** for `call_81fb9edf952145f8818165e4` (bash)

#### [38] line 38 · message · assistant · 2026-10-02T00:18:42.232Z
**toolCall bash** id=`call_ded5f6e623ae4f548bf652d9`

```json
{
 "command": "python -c \"\nimport json\np=r'C:/Users/<user>/AppData/Local/Temp/claude/C--Users-user/bb0fac07-fb14-4ec9-82d9-33b3b7c2e4f4/scratchpad/matrix-full/matrix.json'\nm=json.load(open(p,encoding='utf-8'))\nfull=quick=0.0\nfor c in m['cells']:\n    print(c['index'], c['label'], c['verdict'], c['seconds'])\n    full += c['seconds']\nprint('FULL sum:', round(full,1))\n\""
}
```

#### [39] line 39 · message · toolResult · 2026-10-02T00:18:42.298Z
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
FULL sum: 1942.7
**toolResult** for `call_ded5f6e623ae4f548bf652d9` (bash)

#### [40] line 40 · message · assistant · 2026-10-02T00:18:54.715Z
<details><summary>thinking</summary>

The full sum is 1942.7 s = 32 m 22.7 s ≈ 32 m 23 s. README says full = 1942.7 s, 32 m 23 s. ✓

Quick cells (10 of the full matrix): cells 1-10: 27.1+138.1+92.7+58.4+160.6+196.9+334.4+347.2+51.6+59.5 = let me compute: 27.1+138.1=165.2; +92.7=257.9; +58.4=316.3; +160.6=476.9; +196.9=673.8; +334.4=1008.2; +347.2=1355.4; +51.6=1407.0; +59.5=1466.5. ✓ 1466.5 s = 24 m 26.5 s ≈ 24 m 27 s. README says 24 m 27 s (1466.5 s). ✓ And the README discloses these are sums of the ten cells from the full run, not a quick run, with 2 of 10 failed (host and relay — yes, cells 2 and 7 failed; hermetic claude is cell 13, part of the extra 5). ✓ And "3 of 15 cells failed before the m7 fixes" — cells 2, 7, 13. ✓

Also smoke row: `single pi` 31 s, `single host` 1 m 51 s (5.4k and 87.0k tokens, m5 acceptance run) — the full matrix says single pi 27.1 s / 5761 tokens and host 138.1 s. But the smoke row cites the m5 acceptance run, unchanged from before. Fine (not part of this milestone's scope; it's labeled as m5 acceptance run).

Wait — "smoke" row says `single host` 1 m 51 s = 111 s and 87.0 k tokens from m5 acceptance; the full matrix measured 138.1 s. Both are honest labeled figures; fine.

Now the suite figure: README says 902 tests, 873 s, shards 328.9/285.4/258.4 s. I will verify with the three shard runs — the count and timings will differ slightly but should be ~902 tests. The commit message says 902 tests. Let me trust the shard runs I'll do and compare test counts.

Next, verify claude_runner build_command to confirm `--setting-sources project,local` and `--strict-mcp-config` are hermetic-only, and understand what usual setup passes.

</details>
README's quick (1466.5 s) and full (1942.7 s) figures match the measured matrix exactly, and the failure counts (2 of 10, 3 of 15) are honest. Now the claude command builder:
**toolCall bash** id=`call_8ac468db44e84d74b5c9d557`

```json
{
 "command": "cd C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes && sed -n 40,140p oh-dispatch/scripts/ohflow/claude_runner.py"
}
```

#### [41] line 41 · message · toolResult · 2026-10-02T00:18:54.826Z
# `--bare` needs an API key. Measured 2026-10-01 (2.1.281).
HERMETIC_ENV = {"CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1"}

# The init event names some tools by their internal name; the model sees
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
    details = usage.get("output_tokens_details") or {}
    return {"prompt_tokens": inp + write + read,
            "completion_tokens": int(usage.get("output_tokens") or 0),
            "cache_read_tokens": read, "cache_write_tokens": write,
            "reasoning_tokens": int(details.get("thinking_tokens") or 0)}


def _summed_tokens(events) -> dict[str, int]:
    total = {key: 0 for key in TOKEN_KEYS}
    for messages in _assistant_messages(events).values():
**toolResult** for `call_8ac468db44e84d74b5c9d557` (bash)

#### [42] line 42 · message · assistant · 2026-10-02T00:19:06.241Z
<details><summary>thinking</summary>

Hermetic claude: `--tools`, `--strict-mcp-config`, `--mcp-config <plan servers>`, `--setting-sources project,local` + env `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1`. Usual setup: none of those, loads user settings and CLAUDE.md. This matches lanes.md's table.

One question: is `CLAUDE_CODE_DISABLE_CLAUDE_MDS` a real mechanism? The implementer says measured on 2.1.281. Best evidence: the live run of exit criterion 4 (single:claude:1:profile=hermetic). If it passes rollcall_matches — the report would have listed the ten MCP servers from ~/.claude/CLAUDE.md if it still loaded. Let me also check `claude --help` for the env var? Env vars aren't in --help usually. There's `claude --help` mention of `--setting-sources`. I can run `claude -p` quickly? That costs quota. Better: the live rollcall cell in criterion 4 is the proof. Also attempt 1 was blocked — the brief says "a run on the default hid a dsh defect in attempt 1", implying attempt 1 ran cells and hermetic passed? Not sure. The live run will tell.

Let me now check gates.py `rollcall_matches` more fully — verify the check.args from CheckSpec("rollcall_matches", {"lane": lane}) passes lane as kwarg. The register decorator: `@register("rollcall_matches", lambda a: ...)` — the lambda is a description builder. CheckSpec("rollcall_matches", {"lane": lane}) — args dict passed as kwargs to the gate function. The signature now `rollcall_matches(ctx, surface=None, lane=None)`. Fine.

But wait — there's a subtlety: `observed` record? The gate reads result.json's `tools`/`mcp_servers` (harness-announced) and the structured report. With lane check added. Where does the gate get the report? `ctx.structured`. OK.

Also: are there other gate checks that use the report's lane? `schema_valid` — requires lane present as any string. Good.

Now the campaign shapes' report checks: `_solo` used by single/fanout/retry? Let me check the rest of rollcall.py (lines 430-560) to see all shapes pass lane — the test asserts merge shape reaches every rollcall_matches with lane. Let me verify quickly for all shapes by building each shape plan and checking CheckSpec args. I can do that in one python command.

Also check `review` and `campaign` shapes' steps: review has a reviewer step with VERDICT check — does it use _report_checks? campaign shape has worker/judge steps — the judge's checks probably aren't rollcall report checks. Let me just enumerate every rollcall_matches check in every shape and confirm each has a lane arg (except where deliberately absent).

</details>
The hermetic claude switch set matches the doc table. Now verify every shape's `rollcall_matches` check carries the lane, and run the fast exit criteria:
**toolCall bash** id=`call_feb72c9051ac4e69bc2dd78d`

```json
{
 "command": "cd C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes/oh-dispatch/scripts && python -c \"\nfrom ohflow.plans import rollcall\nimport tempfile, os\ntmp = tempfile.mkdtemp()\nrepo = os.path.join(tmp, 'repo')\nfor shape in ('single','fanout','relay','merge','retry','review','campaign'):\n    plan = rollcall.build({'repo': repo, 'shape': shape, 'lanes': 'pi,claude'})\n    seen = {}\n    for ph in plan.phases:\n        for st in ph.steps:\n            for ck in (st.gate.checks if st.gate else ()):\n                if ck.name == 'rollcall_matches':\n                    seen[st.id] = ck.args.get('lane', '<MISSING>')\n    print(shape, seen)\n\""
}
```
**toolCall bash** id=`call_c54d42c0d8c54b1d89e6abb0`

```json
{
 "command": "cd C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes && python oh-dispatch/tests/run_tests.py -k parent_session > ../rev-$(basename \"$PWD\")-c1.log 2>&1; echo \"exit $?\"; tail -5 ../rev-$(basename \"$PWD\")-c1.log"
}
```

#### [43] line 43 · message · toolResult · 2026-10-02T00:19:07.100Z
Traceback (most recent call last):
  File "<string>", line 7, in <module>
    plan = rollcall.build({'repo': repo, 'shape': shape, 'lanes': 'pi,claude'})
  File "C:\Users\<user>\dev\_wt\oh-dispatch-deepening\m7-smoke-fixes\oh-dispatch\scripts\ohflow\plans\rollcall.py", line 588, in build
    spec = normalize(args)
  File "C:\Users\<user>\dev\_wt\oh-dispatch-deepening\m7-smoke-fixes\oh-dispatch\scripts\ohflow\plans\rollcall.py", line 360, in normalize
    raise ValueError(f"roll-call shape {given!r} runs on exactly one "
                     f"lane, got {list(lanes)}")
ValueError: roll-call shape 'single' runs on exactly one lane, got ['pi', 'claude']


Command exited with code 1
**toolResult** for `call_feb72c9051ac4e69bc2dd78d` (bash) (is_error)

#### [44] line 44 · message · toolResult · 2026-10-02T00:19:07.100Z
exit 0
OK

summary schema checks: 0   unexpected rejections: 0
summary schema audit: this filtered selection produced no Engine summary
ran 6 tests in 0.0s   failures=0 errors=0 skipped=0
**toolResult** for `call_c54d42c0d8c54b1d89e6abb0` (bash)

#### [45] line 45 · message · assistant · 2026-10-02T00:19:17.030Z
<details><summary>thinking</summary>

Criterion 1 passes: 6 tests ≥ 5, exit 0. But wait — it ran in 0.0 s? That's suspiciously fast for tests that launch lane runners. Let me look at what the 6 tests are. The tests use `_capture_launch` mocks, so no real processes. OK, 0.0s plausible? "ran 6 tests in 0.0s" — TempCase with tmp dirs, mocks of spawn_managed. Plausible.

Wait, criterion 1 requires "one per lane, each proving the worker's environment has no CLAUDE*, CLAUDECODE or ANTHROPIC_BASE_URL when the parent has them". 6 tests: 5 lanes + 1 rule test. ✓

For shapes, single takes one lane. Let me redo with per-shape valid args.

</details>
Criterion 1: exit 0, 6 tests (five lanes + the rule itself). My shape probe used invalid args; retry with per-shape lanes:
**toolCall bash** id=`call_020ab061d144452589ccb017`

```json
{
 "command": "cd C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes/oh-dispatch/scripts && python -c \"\nfrom ohflow.plans import rollcall\nimport tempfile, os\ntmp = tempfile.mkdtemp()\nrepo = os.path.join(tmp, 'repo')\nargs = {'single': {'lanes':'pi'}, 'fanout': {'lanes':'pi,claude,codex,dsh'},\n        'relay': {'lanes':'pi,claude'}, 'merge': {'lanes':'pi,claude'},\n        'retry': {'lanes':'pi'}, 'review': {'lanes':'pi,claude'},\n        'campaign': {}}\nfor shape, extra in args.items():\n    plan = rollcall.build(dict(repo=repo, shape=shape, **extra))\n    seen = {}\n    for ph in plan.phases:\n        for st in ph.steps:\n            for ck in (st.gate.checks if st.gate else ()):\n                if ck.name == 'rollcall_matches':\n                    seen[st.id] = ck.args.get('lane', '<MISSING>')\n    print(shape, seen)\n\""
}
```
**toolCall bash** id=`call_4c8eb63b369248b9b689df2f`

```json
{
 "command": "cd C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes && python oh-dispatch/tests/run_tests.py -k hermetic > ../rev-$(basename \"$PWD\")-c2.log 2>&1; echo \"exit $?\"; tail -3 ../rev-$(basename \"$PWD\")-c2.log; python oh-dispatch/tests/run_tests.py -k report_lane > ../rev-$(basename \"$PWD\")-c3.log 2>&1; echo \"exit $?\"; tail -3 ../rev-$(basename \"$PWD\")-c3.log"
}
```

#### [46] line 46 · message · toolResult · 2026-10-02T00:19:19.601Z
Traceback (most recent call last):
  File "<string>", line 11, in <module>
    plan = rollcall.build(dict(repo=repo, shape=shape, **extra))
  File "C:\Users\<user>\dev\_wt\oh-dispatch-deepening\m7-smoke-fixes\oh-dispatch\scripts\ohflow\plans\rollcall.py", line 588, in build
    spec = normalize(args)
  File "C:\Users\<user>\dev\_wt\oh-dispatch-deepening\m7-smoke-fixes\oh-dispatch\scripts\ohflow\plans\rollcall.py", line 360, in normalize
    raise ValueError(f"roll-call shape {given!r} runs on exactly one "
                     f"lane, got {list(lanes)}")
ValueError: roll-call shape 'campaign' runs on exactly one lane, got ['pi', 'claude', 'codex', 'dsh']
single {'pi-1': 'pi'}
fanout {'pi-1': 'pi', 'claude-1': 'claude', 'codex-1': 'codex', 'dsh-1': 'dsh'}
relay {'pi-1': 'pi', 'claude-1': 'claude'}
merge {'pi-1': 'pi', 'claude-1': 'claude', 'consolidate': 'claude'}
retry {'pi-1': 'pi'}
review {'pi-1': 'pi'}


Command exited with code 1
**toolResult** for `call_020ab061d144452589ccb017` (bash) (is_error)

#### [47] line 47 · message · toolResult · 2026-10-02T00:19:19.639Z
exit 0
summary schema checks: 0   unexpected rejections: 0
summary schema audit: this filtered selection produced no Engine summary
ran 10 tests in 1.1s   failures=0 errors=0 skipped=0
exit 0
summary schema checks: 0   unexpected rejections: 0
summary schema audit: this filtered selection produced no Engine summary
ran 5 tests in 0.0s   failures=0 errors=0 skipped=0
**toolResult** for `call_4c8eb63b369248b9b689df2f` (bash)

#### [48] line 48 · message · assistant · 2026-10-02T00:19:23.812Z
<details><summary>thinking</summary>

Criteria 2 (10 tests ≥ 2) and 3 (5 tests ≥ 1) pass. Shapes single/fanout/relay/merge/retry/review all carry the lane. The `campaign` shape defaults lanes to all four; let me check campaign shape's checks with default lanes — campaign has worker + judge steps; do they use rollcall_matches? Let me check.

</details>
Criteria 2 and 3 pass (10 and 5 tests). Check the campaign shape with its default lanes:
**toolCall bash** id=`call_67cd8c4c705540cfa9f57e50`

```json
{
 "command": "cd C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes/oh-dispatch/scripts && python -c \"\nfrom ohflow.plans import rollcall\nimport tempfile, os\ntmp = tempfile.mkdtemp()\nplan = rollcall.build({'repo': os.path.join(tmp,'repo'), 'shape': 'campaign'})\nfor ph in plan.phases:\n    for st in ph.steps:\n        for ck in (st.gate.checks if st.gate else ()):\n            if ck.name == 'rollcall_matches':\n                print(st.id, ck.args)\n\" && grep -n \"_campaign\\b\" -A 30 oh-dispatch/plans/rollcall.py | sed -n 1,40p"
}
```

#### [49] line 49 · message · toolResult · 2026-10-02T00:19:23.970Z
Traceback (most recent call last):
  File "<string>", line 5, in <module>
    plan = rollcall.build({'repo': os.path.join(tmp,'repo'), 'shape': 'campaign'})
  File "C:\Users\<user>\dev\_wt\oh-dispatch-deepening\m7-smoke-fixes\oh-dispatch\scripts\ohflow\plans\rollcall.py", line 588, in build
    spec = normalize(args)
  File "C:\Users\<user>\dev\_wt\oh-dispatch-deepening\m7-smoke-fixes\oh-dispatch\scripts\ohflow\plans\rollcall.py", line 360, in normalize
    raise ValueError(f"roll-call shape {given!r} runs on exactly one "
                     f"lane, got {list(lanes)}")
ValueError: roll-call shape 'campaign' runs on exactly one lane, got ['pi', 'claude', 'codex', 'dsh']


Command exited with code 1
**toolResult** for `call_67cd8c4c705540cfa9f57e50` (bash) (is_error)

#### [50] line 50 · message · assistant · 2026-10-02T00:19:29.307Z
**toolCall bash** id=`call_278bdb984baf4a6e9506749d`

```json
{
 "command": "cd C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes/oh-dispatch/scripts && sed -n 345,375p ohflow/plans/rollcall.py && python -c \"\nfrom ohflow.plans import rollcall\nimport tempfile, os\ntmp = tempfile.mkdtemp()\nplan = rollcall.build({'repo': os.path.join(tmp,'repo'), 'shape': 'campaign', 'lanes': 'pi'})\nfor ph in plan.phases:\n    for st in ph.steps:\n        for ck in (st.gate.checks if st.gate else ()):\n            print(st.id, ck.name, dict(ck.args))\n\""
}
```

#### [51] line 51 · message · toolResult · 2026-10-02T00:19:29.514Z
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

pi-1 commits_past_base {'min': 1, 'since': 'base'}
pi-1 tree_clean {}
pi-1 ownership {'allowed': ['rollcall/pi-1.md'], 'since': 'base'}
pi-1 no_ai_attribution {'since': 'base'}
pi-1 final_message_matches {'regex': '"status"\\s*:\\s*"PRESENT"'}
pi-1 schema_valid {}
pi-1 rollcall_matches {'lane': 'pi'}
pi-1 file_contains {'path': 'rollcall/pi-1.md', 'text': 'Campaign-Token: M5-ROLLCALL', 'hidden': True}
**toolResult** for `call_278bdb984baf4a6e9506749d` (bash)

#### [52] line 52 · message · assistant · 2026-10-02T00:19:44.249Z
<details><summary>thinking</summary>

Campaign shape's worker step uses `_solo` → lane passed. The judge step presumably uses verdict checks, not rollcall_matches. All good: every `rollcall_matches` check in every shape now carries the lane.

Now: prove defect tests fail against old code. Let me build a base checkout in a temp dir via `git archive` and run a few of the new tests against it. Plan:

```
tmp=$(mktemp -d)
git archive arch/deepening | tar -x -C $tmp
# copy new test files from worktree into $tmp/oh-dispatch/tests/
cp <worktree>/oh-dispatch/tests/test_defect_4[4-9]*.py $tmp/oh-dispatch/tests/
cd $tmp/oh-dispatch/scripts && python ../tests/run_tests.py -k <name>
```

But new tests import things that may not exist at base: test_44 imports `from ohflow import lanes, proc` — proc at base has no worker_env, but test_44 calls `proc.worker_env` only in the last test. The other tests would run and fail (old code passes CLAUDE* on pi/host lanes). Also `from ohflow.worker import HostLane, spec_json` — exists at base presumably. test_45: ClaudeAdapter at base has no HERMETIC_ENV — tests fail. test_46: rollcall_matches at base has no lane kwarg → TypeError → error, that's a fail. test_47: base STALL_S doesn't exist → import fine (attribute accessed in test) → fail. test_48: old session_bucket slug differs for the dot case → fail. test_49: base campaign.ensure_ignores lacks .watch.*.json → test fails (the cursor shows in git status).

One caveat: tar on Windows git-bash with git archive — `git archive ... | tar -x -C` should work in git bash. Or use `tar -xf -`. Let me try.

Also careful: the suite `run_tests.py` may compute IMPORT_ROOT relative to itself. Fine.

Note: test_44's `test_parent_session_vars_do_not_reach_the_pi_runner_or_its_cli` — at base, pi lane env=dict(os.environ) → leak. And `_launch_env('pi')`... at base, CliLane.launch with env=dict(os.environ) → captured env includes CLAUDE* → test fails. Good.

Also I should verify defect 45 more: "test_hermetic_profile_keeps_the_setting_source_flag" — at base, build_command DID have the hermetic block with --setting-sources? Let me check base claude_runner: the hermetic profile existed before m7 (HERMETIC_TOOLS, HERMETIC_DEFAULT already at base; the m7 diff only adds HERMETIC_ENV and the env var). So test_45's third test (usual setup) passes at base too, but tests 1-2 fail. That's fine: the defect test as a file fails.

Let me run this now. Also run the watch test? test_49 needs test_campaign_01_loop at base — exists. OK.

Then the live rollcall (criterion 4) — the long one — then shards.

Actually order: do the archive check now (fast), then kick off criterion 4 live (~10-15 min), then shards 1-3. Never two suites at once: the archive run is a test suite too — run it before the live rollcall and wait.

</details>
Every shape's report check carries the lane. Now prove the defect tests fail against the old code — I'll materialize the trunk in a temp dir with `git archive` (no write to the shared checkout) and run the new tests there:
**toolCall bash** id=`call_d1bdf115ce2648079f7d4e2d`

```json
{
 "command": "tmp=$(mktemp -d); echo \"TMP=$tmp\"; cd C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes && git archive arch/deepening | tar -x -C \"$tmp\" && cp oh-dispatch/tests/test_defect_4[4-9]*.py \"$tmp/oh-dispatch/tests/\" && ls \"$tmp/oh-dispatch/tests/\" | tail -8 && echo \"$tmp\" > /tmp/base-dir.txt"
}
```

#### [53] line 53 · message · toolResult · 2026-10-02T00:19:45.553Z
TMP=/tmp/tmp.IlVBVBQerd
test_verb_campaign_watch.py
test_verb_notes.py
test_verb_preflight.py
test_verb_run.py
test_verb_status.py
test_verb_validate.py
test_verb_watch.py
verb_support.py
**toolResult** for `call_d1bdf115ce2648079f7d4e2d` (bash)

#### [54] line 54 · message · assistant · 2026-10-02T00:19:50.631Z
**toolCall bash** id=`call_27ab2a2f5e254df7a36b0718`

```json
{
 "command": "tmp=$(cat /tmp/base-dir.txt); ls \"$tmp/oh-dispatch/tests/\" | grep defect_4 ; cd \"$tmp/oh-dispatch/scripts\" 2>/dev/null || cd \"$tmp/oh-dispatch\"; pwd; ls"
}
```

#### [55] line 55 · message · toolResult · 2026-10-02T00:19:50.717Z
test_defect_40_detach_env_stays_off_disk.py
test_defect_41_tree_kill_run_quiet.py
test_defect_42_tests_ignore_the_workers_environment.py
test_defect_43_spawn_resumes_without_a_thread_snapshot.py
test_defect_44_parent_session_vars_reach_no_worker.py
test_defect_45_hermetic_claude_loads_no_instruction_files.py
test_defect_46_rollcall_report_lane_must_match_the_step.py
test_defect_47_rollcall_stall_limit_is_per_lane.py
test_defect_48_dsh_session_bucket_follows_dsh.py
test_defect_49_campaign_watch_is_not_a_stray_edit.py
/tmp/tmp.IlVBVBQerd/oh-dispatch/scripts
host_worker.py
implement_review.py
ohflow
**toolResult** for `call_27ab2a2f5e254df7a36b0718` (bash)

#### [56] line 56 · message · assistant · 2026-10-02T00:19:53.517Z
**toolCall bash** id=`call_9be5e2e0aac9429ba6094aca`

```json
{
 "command": "tmp=$(cat /tmp/base-dir.txt); cd \"$tmp/oh-dispatch/scripts\"; for k in parent_session hermetic report_lane dsh_session_bucket rollcall_stall; do python ../tests/run_tests.py -k $k > /tmp/base-$k.log 2>&1; echo \"== $k exit $?\"; grep -E \"^(FAIL|ERROR|OK)|ran [0-9]+ tests\" /tmp/base-$k.log | tail -8; done",
 "timeout": 300
}
```

#### [57] line 57 · message · toolResult · 2026-10-02T00:20:03.650Z
== parent_session exit 1
ERROR: test_parent_session_vars_are_the_only_names_the_rule_removes (tests.test_defect_44_parent_session_vars_reach_no_worker.ParentSessionVarsReachNoWorker.test_parent_session_vars_are_the_only_names_the_rule_removes)
FAIL: test_parent_session_vars_do_not_reach_the_claude_runner_or_its_cli (tests.test_defect_44_parent_session_vars_reach_no_worker.ParentSessionVarsReachNoWorker.test_parent_session_vars_do_not_reach_the_claude_runner_or_its_cli)
FAIL: test_parent_session_vars_do_not_reach_the_codex_runner_or_its_cli (tests.test_defect_44_parent_session_vars_reach_no_worker.ParentSessionVarsReachNoWorker.test_parent_session_vars_do_not_reach_the_codex_runner_or_its_cli)
FAIL: test_parent_session_vars_do_not_reach_the_dsh_runner_or_its_cli (tests.test_defect_44_parent_session_vars_reach_no_worker.ParentSessionVarsReachNoWorker.test_parent_session_vars_do_not_reach_the_dsh_runner_or_its_cli)
FAIL: test_parent_session_vars_do_not_reach_the_host_runner (tests.test_defect_44_parent_session_vars_reach_no_worker.ParentSessionVarsReachNoWorker.test_parent_session_vars_do_not_reach_the_host_runner)
FAIL: test_parent_session_vars_do_not_reach_the_pi_runner_or_its_cli (tests.test_defect_44_parent_session_vars_reach_no_worker.ParentSessionVarsReachNoWorker.test_parent_session_vars_do_not_reach_the_pi_runner_or_its_cli)
FAILED (failures=5, errors=1)
ran 6 tests in 0.2s   failures=5 errors=1 skipped=0
== hermetic exit 1
FAIL: test_hermetic_profile_disables_the_instruction_files (tests.test_defect_45_hermetic_claude_loads_no_instruction_files.HermeticClaudeInstructionFiles.test_hermetic_profile_disables_the_instruction_files)
FAILED (failures=1)
ran 10 tests in 1.2s   failures=1 errors=0 skipped=0
== report_lane exit 1
ERROR: test_report_lane_missing_fails_when_the_step_names_one (tests.test_defect_46_rollcall_report_lane_must_match_the_step.ReportLane.test_report_lane_missing_fails_when_the_step_names_one)
ERROR: test_report_lane_naming_another_lane_fails (tests.test_defect_46_rollcall_report_lane_must_match_the_step.ReportLane.test_report_lane_naming_another_lane_fails)
ERROR: test_report_lane_naming_the_step_lane_passes (tests.test_defect_46_rollcall_report_lane_must_match_the_step.ReportLane.test_report_lane_naming_the_step_lane_passes)
ERROR: test_report_lane_reaches_every_report_check_of_the_plan (tests.test_defect_46_rollcall_report_lane_must_match_the_step.ReportLane.test_report_lane_reaches_every_report_check_of_the_plan)
FAILED (errors=4)
ran 5 tests in 0.0s   failures=0 errors=4 skipped=0
== dsh_session_bucket exit 1
FAIL: test_each_character_class_is_encoded_as_dsh_encodes_it (tests.test_defect_48_dsh_session_bucket_follows_dsh.SessionBucketFollowsDsh.test_each_character_class_is_encoded_as_dsh_encodes_it) [a non-ASCII letter]
FAIL: test_each_character_class_is_encoded_as_dsh_encodes_it (tests.test_defect_48_dsh_session_bucket_follows_dsh.SessionBucketFollowsDsh.test_each_character_class_is_encoded_as_dsh_encodes_it) [a character outside the BMP: two UTF-16 code units]
FAIL: test_each_character_class_is_encoded_as_dsh_encodes_it (tests.test_defect_48_dsh_session_bucket_follows_dsh.SessionBucketFollowsDsh.test_each_character_class_is_encoded_as_dsh_encodes_it) [a leading separator run is dropped]
FAIL: test_each_character_class_is_encoded_as_dsh_encodes_it (tests.test_defect_48_dsh_session_bucket_follows_dsh.SessionBucketFollowsDsh.test_each_character_class_is_encoded_as_dsh_encodes_it) [only separators]
FAIL: test_each_character_class_is_encoded_as_dsh_encodes_it (tests.test_defect_48_dsh_session_bucket_follows_dsh.SessionBucketFollowsDsh.test_each_character_class_is_encoded_as_dsh_encodes_it) [a path longer than 251 characters]
FAIL: test_the_key_is_cut_before_the_closing_marker (tests.test_defect_48_dsh_session_bucket_follows_dsh.SessionBucketFollowsDsh.test_the_key_is_cut_before_the_closing_marker)
FAILED (failures=11)
ran 4 tests in 0.0s   failures=11 errors=0 skipped=0
== rollcall_stall exit 1
ERROR: test_the_table_has_a_row_only_for_lanes_that_take_a_limit (tests.test_defect_47_rollcall_stall_limit_is_per_lane.RollcallStallPerLane.test_the_table_has_a_row_only_for_lanes_that_take_a_limit)
FAIL: test_codex_gets_at_least_ten_minutes (tests.test_defect_47_rollcall_stall_limit_is_per_lane.RollcallStallPerLane.test_codex_gets_at_least_ten_minutes)
FAILED (failures=1, errors=1)
ran 4 tests in 0.0s   failures=1 errors=1 skipped=0
**toolResult** for `call_9be5e2e0aac9429ba6094aca` (bash)

#### [58] line 58 · message · assistant · 2026-10-02T00:20:29.578Z
<details><summary>thinking</summary>

All defect tests fail against base code (red first). Note: defect_44's claude/codex/dsh failures at base are because `proc.worker_env` doesn't exist — wait, no: claude/codex/dsh FAILed (not errored) because `_launch_env` capture... hmm, actually at base, `mock.patch("ohflow.cli_lane.spawn_managed", ...)` — the launch env at base was `dict(os.environ)` → leak → FAIL. And pi/host too. And the ERROR is only the last test calling `proc.worker_env` (doesn't exist at base). Good — genuine red.

Also interesting: defect_48's "a dot, as in mktemp -d" case FAILED at base? Let me look — the listed failures for dsh: non-ASCII, BMP, leading separator, only separators, longer than 251... and 11 failures total (subtests count). "a dot" and "an underscore" cases passed at base (old rule kept dots? No wait — old rule replaced runs of `[^A-Za-z0-9-]+` with `-`, so a dot would become `-`: `tmp.YBNLOpDXik` → `tmp-YBNLOpDXik`. But the FAIL list doesn't show "a dot"... Hmm, subTest failures listed: [a non-ASCII letter], [a character outside the BMP], [a leading separator run is dropped], [only separators], [a path longer than 251]... and that's 5 subtest failures + test_the_key_is_cut + others = 11 total failures counted per subtest? "failures=11" — unittest counts each failed subTest as a failure. 5 shown due to tail -8 truncation. Fine — the dot case is surely among them.

Now the live run: exit criterion 4. Command from the land worktree root... wait — "from `oh-dispatch/scripts`". The exit criteria table says "Command (from the land worktree root)". Hmm: "| 4 | with CLAUDECODE=1 ... exported, `ohflow rollcall --cells ...` from `oh-dispatch/scripts` |". So run from oh-dispatch/scripts directory.

With `--out "$(mktemp -d)"`. mktemp -d in git bash gives /tmp/tmp.XXXX which maps to C:\Users\<user>\AppData\Local\Temp\tmp.XXXX? Actually git bash /tmp maps to $TMP usually. The path passed to the tool matters: the point is the path contains a `.` (`tmp.XXXXXXXXXX`). mktemp -d in git bash creates /tmp/tmp.XXXXXXXXXX — when passed as a Windows path to Python it may keep the POSIX form "/tmp/tmp.XXX" which Python on Windows resolves relative to drive root C:\tmp? Hmm — that could be a problem, or not: Python would treat "/tmp/tmp.X" as "C:\tmp\tmp.X" (current drive root). If C:\tmp doesn't exist, the rollcall would try to create it... Actually git bash's /tmp is usually the user's TEMP dir. Passing "/tmp/tmp.XXX" to a Windows Python process → resolves to C:/tmp/tmp.XXX (drive-relative). That would create C:\tmp — writing outside worktree but in temp-ish location. Hmm.

But the campaign driver presumably runs in a similar bash. The brief says "Run exit criterion 4 exactly as the campaign driver does, with `--out "$(mktemp -d)"`. That path holds a `.` (`tmp.XXXXXXXXXX`)."

Let me check how the driver invokes it — maybe driver runs via bash too. Simplest: use mktemp -d and pass the result through `cygpath -w`? No — "exactly as the campaign driver does". Hmm, the driver... I don't know exactly how the driver invokes it. The point of the `.` is to exercise the dsh bucket fix. If I pass "/tmp/tmp.XXX" as-is, Python sees "C:\tmp\tmp.XXX\tmp.XXXXXXXXXX"? No wait, mktemp -d outputs like `/tmp/tmp.IlVBVBQerd`. `--out /tmp/tmp.IlVBVBQerd` to a Windows Python program → path with forward slash, drive-relative → `C:\tmp\tmp.IlVBVBQerd`. Does C:\tmp exist? Probably not; the tool may mkdir it. That's writing outside the worktree, but it's a temp path, acceptable-ish? It would create a directory on C:\ root though. Hmm.

Let me instead check what `ohflow rollcall` does with --out, and check whether prior runs' matrix.json path used the Claude temp dir: `C--Users-user\...\Temp\claude\...\scratchpad\matrix-full`. That was the desktop app's temp.

Better approach: `--out "$(mktemp -d)"` where mktemp -d returns /tmp/... — in this bash, TMP might be set to a Windows temp. Let me check: `echo $TMPDIR; mktemp -d` gave `/tmp/tmp.IlVBVBQerd`. Python on Windows would resolve `/tmp/...` to `C:\tmp\...`. Let me test if C:\tmp exists. If the driver ran this exact command, it faced the same thing. Actually maybe the driver runs cmd or powershell where mktemp doesn't exist... The brief says run it exactly with `--out "$(mktemp -d)"` — so run in bash. Fine: I'll do exactly that. If C:\tmp gets created, that's outside my worktree but a scratch location; the earlier dsh defect was found precisely with this pattern. It's acceptable — reviewers create temp dirs. But wait: "Create nothing inside the worktree" — outside is fine (logs already go outside).

Hmm, but writing to C:\tmp — creating a dir at drive root is a bit rude but harmless and ephemeral. Alternatively TMPDIR override... "exactly as the driver does" — I'll just run it as written.

Before the live run, check the rollcall CLI: `ohflow rollcall --cells single:host single:claude:1:profile=hermetic relay:pi,claude,codex,dsh --out <dir>`. From oh-dispatch/scripts. Env: CLAUDECODE=1, CLAUDE_CODE_ENTRYPOINT=claude-desktop, CLAUDE_AGENT_SDK_VERSION=0.3.284 exported.

This launches real agents: host (OpenHands glm), claude hermetic (haiku), relay pi+claude+codex+dsh. Expected ~2 + 1.5 + 6 min ≈ maybe 10-12 min. Timeout: give 1200 s. The bash tool default timeout — I'll set timeout 1200.

One concern: my current session is a Claude Code session? I'm running headless as a worker on the pi lane per the campaign... Actually I am the reviewer on the pi lane. My own process may export CLAUDE* variables (e.g., CLAUDECODE=1 already?). That's the point — the exported vars simulate the desktop session; the fix strips them from workers. The host cell must report OpenHands, not Claude.

Note the rollcall also uses the seats' logins. Let me check `ohflow rollcall --help` first, then run.

Also: does rollcall need a scratch repo (the plan arg repo)? The matrix runner presumably creates one. Let me check the CLI.

</details>
All six defect tests are genuinely red against the trunk code. Now the live exit criterion 4. First check the verb's interface, then run it exactly as the driver does:
**toolCall bash** id=`call_76d55a4deaa34994b3a65c91`

```json
{
 "command": "cd C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes/oh-dispatch/scripts && python -m ohflow.cli rollcall --help 2>&1 | head -40"
}
```

#### [59] line 59 · message · toolResult · 2026-10-02T00:20:29.826Z
usage: ohflow rollcall [-h] [--matrix NAME]
                       [--cells shape:lanes[:count] [shape:lanes[:count] ...]]
                       [--dry-run] [--config FILE] [--repo REPO] [--out OUT]
                       [--list] [-v]

options:
  -h, --help            show this help message and exit
  --matrix NAME         smoke, quick or full (default quick)
  --cells shape:lanes[:count] [shape:lanes[:count] ...]
                        run these cells instead of a matrix
  --dry-run             build and validate every cell's plan; start nothing
  --config FILE         a JSON file that sets model and params per lane
  --repo REPO           a git repository to run in; the default is a throwaway
                        one under --out
  --out OUT             where the cells and matrix.json go
  --list                print each matrix's cells and exit
  -v, --verbose         stream each run's own lines
**toolResult** for `call_76d55a4deaa34994b3a65c91` (bash)

#### [60] line 60 · message · assistant · 2026-10-02T00:20:36.517Z
**toolCall bash** id=`call_bd849aa267da439ca574cec6`

```json
{
 "command": "cd C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes/oh-dispatch/scripts && export CLAUDECODE=1 CLAUDE_CODE_ENTRYPOINT=claude-desktop CLAUDE_AGENT_SDK_VERSION=0.3.284 && OUT=\"$(mktemp -d)\" && echo \"OUT=$OUT\" && python -m ohflow.cli rollcall --cells single:host single:claude:1:profile=hermetic relay:pi,claude,codex,dsh --out \"$OUT\" > /tmp/rev-c4.log 2>&1; echo \"exit $?\"; tail -25 /tmp/rev-c4.log; echo \"$OUT\" > /tmp/rev-c4-out.txt",
 "timeout": 1500
}
```

#### [61] line 61 · message · toolResult · 2026-10-02T00:30:02.414Z
OUT=/tmp/tmp.TJIVPeaZGb
exit 0
PASS single host count=1  1m51s  55.3 k tokens  C:\Users\<user>\AppData\Local\Temp\tmp.TJIVPeaZGb\01-single-host-1\run
PASS single claude count=1 profile=hermetic  0m48s  171.5 k tokens  C:\Users\<user>\AppData\Local\Temp\tmp.TJIVPeaZGb\02-single-claude-1\run
PASS relay pi,claude,codex,dsh count=1  6m43s  1374.5 k tokens  C:\Users\<user>\AppData\Local\Temp\tmp.TJIVPeaZGb\03-relay-pi-claude-codex-dsh-1\run
ROLLCALL PASS: 3 of 3 cells
**toolResult** for `call_bd849aa267da439ca574cec6` (bash)

#### [62] line 62 · message · assistant · 2026-10-02T00:30:11.556Z
<details><summary>thinking</summary>

Exit criterion 4 passes: `ROLLCALL PASS: 3 of 3 cells`, with the `.` path (`tmp.TJIVPeaZGb`), the three previously failing cells, and the desktop-session env vars exported. The relay took 6m43s — under the 600 s codex stall it survived.

Let me verify the actual evidence inside the run: the host worker reported OpenHands (not Claude Code), hermetic claude reported no user MCP servers, relay codex step didn't stall. Check the result.json / final messages.

Also confirm the dsh step in the relay found its session in the `tmp.TJIVPeaZGb` bucket (the dot-path fix) — it passed, so it did. Let me still glance at matrix.json and the host's report.

</details>
Criterion 4 passes live: 3 of 3, through a `tmp.` path, with the desktop-session variables exported. Let me verify the actual cell evidence (host identity, hermetic surface, codex no-stall):
**toolCall bash** id=`call_01e3e11441e14e2e97353b28`

```json
{
 "command": "python - <<'EOF'\nimport json, glob\nbase = r'C:/Users/<user>/AppData/Local/Temp/tmp.TJIVPeaZGb'\nm = json.load(open(base + '/matrix.json', encoding='utf-8'))\nfor c in m['cells']:\n    print(c['index'], c['label'], c['verdict'], c['seconds'], 's')\n# host report\np = glob.glob(base + '/01-single-host-1/run/**/result.json', recursive=True)\nr = json.load(open(p[0], encoding='utf-8'))\nprint('\\nHOST result.json tools:', r.get('tools'))\nrep = glob.glob(base + '/01-single-host-1/run/**/structured.json', recursive=True)\nprint('host structured:', open(rep[0], encoding='utf-8').read()[:400] if rep else 'none')\nEOF"
}
```

#### [63] line 63 · message · toolResult · 2026-10-02T00:30:11.737Z
1 single host count=1 PASS 111.2 s
2 single claude count=1 profile=hermetic PASS 47.8 s
3 relay pi,claude,codex,dsh count=1 PASS 402.9 s

HOST result.json tools: ['file_editor', 'finish', 'task_tracker', 'terminal', 'think']
host structured: none
**toolResult** for `call_01e3e11441e14e2e97353b28` (bash)

#### [64] line 64 · message · assistant · 2026-10-02T00:30:15.763Z
**toolCall bash** id=`call_02c18cad33624227a79a7ddb`

```json
{
 "command": "python - <<'EOF'\nimport json, glob, re, os\nbase = r'C:/Users/<user>/AppData/Local/Temp/tmp.TJIVPeaZGb'\n# find the host worker's final report (journal or attempt record)\nfor path in glob.glob(base + '/01-single-host-1/run/**/*.json', recursive=True):\n    try:\n        t = open(path, encoding='utf-8').read()\n    except Exception:\n        continue\n    if '\"harness\"' in t and 'lane' in t and os.path.basename(path) != 'result.json':\n        m = re.search(r'\\{[^{}]*\"harness\"[^{}]*\\}', t, re.S)\n        if m: print(os.path.relpath(path, base), '->', m.group(0)[:300]); break\n# hermetic claude report\nfor path in glob.glob(base + '/02-single-claude-1/run/**/*.md', recursive=True):\n    t = open(path, encoding='utf-8').read()\n    if 'mcp_servers' in t:\n        print('\\nHERMETIC report in', os.path.relpath(path, base)); print(t[:400]); break\nEOF"
}
```

#### [65] line 65 · message · toolResult · 2026-10-02T00:30:16.078Z
01-single-host-1\run\summary.json -> {
              "lane": "host",
              "status": "PRESENT",
              "harness": "OpenHands agent SDK terminal harness (oh rollcall, host lane)",
              "model": "GLM (glm-5.3), served via the pi coding agent environment",
              "tools": [
                "terminal",
      

HERMETIC report in 02-single-claude-1\run\phases\01.report\01.claude-1\brief.md
## Your position in this run

Run:       run     plan: rollcall-single
Phase:     1 of 1 - "Report"
Step:      1 of 1 in this phase - id `claude-1`, role `rollcall-claude`, attempt 1
Coordinate: 01.report/01.claude-1
Worktree:  C:\Users\<user>\AppData\Local\Temp\tmp.TJIVPeaZGb\02-single-claude-1\wt\claude-1
           branch rollcall-8fa0-02-claude-1, created from main at 5b4d20d
You own:   rollcal
**toolResult** for `call_02c18cad33624227a79a7ddb` (bash)

#### [66] line 66 · message · assistant · 2026-10-02T00:30:22.372Z
<details><summary>thinking</summary>

The host worker now reports "OpenHands agent SDK terminal harness" — not Claude Code. The fix works live.

Now find the hermetic claude worker's final structured report to confirm it named no user MCP servers. Let me look in the run dir for the gate input — probably summary.json again.

</details>
**toolCall bash** id=`call_06215f263e1e479c8cd01c4e`

```json
{
 "command": "python - <<'EOF'\nimport json\nbase = r'C:/Users/<user>/AppData/Local/Temp/tmp.TJIVPeaZGb'\ns = json.load(open(base + '/02-single-claude-1/run/summary.json', encoding='utf-8'))\ndef walk(o):\n    if isinstance(o, dict):\n        if 'mcp_servers' in o and 'lane' in o: yield o\n        for v in o.values(): yield from walk(v)\n    elif isinstance(o, list):\n        for v in o: yield from walk(v)\nfor rep in walk(s):\n    print('hermetic claude report:', json.dumps(rep, indent=1))\nEOF"
}
```

#### [67] line 67 · message · toolResult · 2026-10-02T00:30:22.457Z
hermetic claude report: {
 "lane": "claude",
 "status": "PRESENT",
 "harness": "Claude Code",
 "model": "claude-haiku-4-5-20251001",
 "tools": [
  "Bash",
  "Edit",
  "Glob",
  "Grep",
  "Read",
  "Write",
  "StructuredOutput"
 ],
 "mcp_servers": [],
 "cannot": "I cannot modify files outside my assigned worktree directory or commit changes to files other than rollcall/claude-1.md."
}
**toolResult** for `call_06215f263e1e479c8cd01c4e` (bash)

#### [68] line 68 · message · assistant · 2026-10-02T00:30:37.886Z
<details><summary>thinking</summary>

The hermetic claude worker reports no MCP servers and names its own lane `claude`. It passed the gate live — this is strong evidence that `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` actually stopped the instruction files (the original defect had the worker naming ten servers from ~/.claude/CLAUDE.md).

But wait — could the worker have still loaded CLAUDE.md and just not listed servers because `--strict-mcp-config` means the harness announced none? In the original failure the worker listed ten servers because its context told it they exist. Now it lists none — either because it can't see them (CLAUDE.md not loaded) or because it obeyed the brief ("List a tool or a server only when your own tool list shows it"). With --strict-mcp-config the tool list shows no MCP tools, so an obedient worker lists none either way. So the live pass doesn't conclusively prove CLAUDE.md is unloaded. Let me directly verify the mechanism: run claude CLI in hermetic mode and check whether it loads CLAUDE.md? That costs a call on the claude seat quota but small. Alternatively check `claude --help` mentions? Env vars aren't in help. There is `claude config list`? Or check the debug output: `claude -p --debug` prints loaded memory files? A quick cheap test: run claude -p with the env var and ask "do you have any instructions beyond this prompt" — that's model-dependent, weak.

Better: `claude --debug -p "hi"` prints "[DEBUG] Loading CLAUDE.md" lines? In Claude Code debug logs there are lines like "Reading CLAUDE.md..." Let me try with --debug and grep. Keep it cheap: `claude -p --output-format stream-json --verbose --debug "say hi"`? Cost minimal (haiku). Hmm — is it worth it? The implementer measured on 2.1.281. The known Claude Code env var is actually `CLAUDE_CODE_DISABLE_CLAUDE_MDS`... Hmm, I'm not 100% sure this exists; I've seen `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` and the `/memory` system. There's also `--no-memories`? Let me check `claude --help` for flags about CLAUDE.md: `--no-memories`? Actually in recent versions there's a setting `cleanupPeriodDays`... I recall env `CLAUDE_CODE_DISABLE_CLAUDE_MDS`? Hmm, maybe. Let me grep the installed CLI bundle for the string — that's free and conclusive: the claude.exe / cli.js is on disk under APPDATA npm. Search for "DISABLE_CLAUDE_MDS" in the bundle.

Path: claude is installed where? `executable_argv("OHFLOW_CLAUDE_EXE", "claude")` resolves npm shim. Likely `%APPDATA%\npm\node_modules\@anthropic-ai\claude-code\cli.js`. grep that.

Also check `--setting-sources` values documented and that "user" is excluded by project,local. And that the login isn't affected. Let me grep the bundle.

</details>
Live evidence is good. But the live pass alone can't prove CLAUDE.md is unloaded (an obedient worker lists only announced servers). Let me verify the mechanism itself in the installed CLI bundle:
**toolCall bash** id=`call_a74e99e7c41b44299a52a32e`

```json
{
 "command": "ls \"$APPDATA/npm/node_modules/@anthropic-ai/claude-code/\" 2>/dev/null | head; grep -c \"DISABLE_CLAUDE_MDS\" \"$APPDATA/npm/node_modules/@anthropic-ai/claude-code/cli.js\" 2>/dev/null; grep -o \"CLAUDE_CODE_DISABLE_CLAUDE_MDS[^\\\"']*\" \"$APPDATA/npm/node_modules/@anthropic-ai/claude-code/cli.js\" 2>/dev/null | head -3"
}
```

#### [69] line 69 · message · toolResult · 2026-10-02T00:30:38.222Z
LICENSE.md
README.md
bin
cli-wrapper.cjs
install.cjs
node_modules
package.json
sdk-tools.d.ts
**toolResult** for `call_a74e99e7c41b44299a52a32e` (bash)

#### [70] line 70 · message · assistant · 2026-10-02T00:30:42.947Z
**toolCall bash** id=`call_6d5156605aaf484dbfa8b983`

```json
{
 "command": "find \"$APPDATA/npm/node_modules/@anthropic-ai/claude-code\" -name \"*.js\" -o -name \"*.cjs\" -o -name \"*.mjs\" 2>/dev/null | head -10; echo ----; grep -rl \"DISABLE_CLAUDE_MDS\" \"$APPDATA/npm/node_modules/@anthropic-ai/claude-code/\" 2>/dev/null | head -5"
}
```

#### [71] line 71 · message · toolResult · 2026-10-02T00:30:43.590Z
C:\Users\<user>\AppData\Roaming/npm/node_modules/@anthropic-ai/claude-code/cli-wrapper.cjs
C:\Users\<user>\AppData\Roaming/npm/node_modules/@anthropic-ai/claude-code/install.cjs
----
C:\Users\<user>\AppData\Roaming/npm/node_modules/@anthropic-ai/claude-code/bin/claude.exe
C:\Users\<user>\AppData\Roaming/npm/node_modules/@anthropic-ai/claude-code/node_modules/@anthropic-ai/claude-code-win32-x64/claude.exe
**toolResult** for `call_6d5156605aaf484dbfa8b983` (bash)

#### [72] line 72 · message · assistant · 2026-10-02T00:30:46.073Z
**toolCall bash** id=`call_a983dd4e2dd646d7a766d6cb`

```json
{
 "command": "exe=\"$APPDATA/npm/node_modules/@anthropic-ai/claude-code/node_modules/@anthropic-ai/claude-code-win32-x64/claude.exe\"; grep -ao \"CLAUDE_CODE_DISABLE_CLAUDE_MDS\" \"$exe\" | head -2; echo \"exit $?\"; \"$exe\" --version"
}
```

#### [73] line 73 · message · toolResult · 2026-10-02T00:30:46.407Z
CLAUDE_CODE_DISABLE_CLAUDE_MDS
CLAUDE_CODE_DISABLE_CLAUDE_MDS
exit 0
2.1.281 (Claude Code)
**toolResult** for `call_a983dd4e2dd646d7a766d6cb` (bash)

#### [74] line 74 · message · assistant · 2026-10-02T00:30:52.326Z
<details><summary>thinking</summary>

The env var `CLAUDE_CODE_DISABLE_CLAUDE_MDS` is a real recognized variable in the installed claude.exe 2.1.281. Let me also check how it's used — ideally confirm it gates CLAUDE.md loading. Search surrounding context bytes in the exe for the var. It's a bun-compiled binary; context strings nearby might show. Let's grep a bit of context.

</details>
**toolCall bash** id=`call_b4656c9c62aa4e8bad91ffad`

```json
{
 "command": "exe=\"$APPDATA/npm/node_modules/@anthropic-ai/claude-code/node_modules/@anthropic-ai/claude-code-win32-x64/claude.exe\"; grep -ao \".\\{90\\}CLAUDE_CODE_DISABLE_CLAUDE_MDS.\\{140\\}\" \"$exe\" | head -2"
}
```

#### [75] line 75 · message · toolResult · 2026-10-02T00:30:52.534Z
yer     ���� cache     ���� CLAUDE_CODE_SIMPLE    ��MM CLAUDE_CODE_SAFE_MODE     �x� CLAUDE_CODE_DISABLE_CLAUDE_MDS    ��� length    ��3� explicitlyRequested   �ޠc realPath  ��>� CLAUDE_CODE_AGENT     ��� autocompact $  ��1G CLAUDE_CODE_INCLUDE_PA
,CLAUDE_CODE_DISABLE_CLAUDE_API_SKILL:()=>vE,CLAUDE_CODE_DISABLE_CLAUDE_CODE_SKILL:()=>gE,CLAUDE_CODE_DISABLE_CLAUDE_MDS:()=>yE,CLAUDE_CODE_DISABLE_CRON:()=>YE,CLAUDE_CODE_DISABLE_DANGEROUS_RM_TIMEOUT:()=>VE,CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS:()=>wE,CLAUDE
**toolResult** for `call_b4656c9c62aa4e8bad91ffad` (bash)

#### [76] line 76 · message · assistant · 2026-10-02T00:31:25.764Z
<details><summary>thinking</summary>

Confirmed: `CLAUDE_CODE_DISABLE_CLAUDE_MDS` is a first-class env var in the CLI's env-bool table. The hermetic mechanism is real, keeps `--setting-sources project,local` (user settings dropped) and the login (auth is not a setting source).

Remaining checks:

1. **dsh lane hermetic**: lanes.md says dsh takes a seat profile name instead — consistent with dsh_runner behavior? `CAP_PROFILE` yes for dsh. Fine.

2. **The `stall_timeout_s` argument override**: `normalize` now accepts `""` → None. Any caller that passes stall_timeout_s=''? The matrix runner may pass through args. Fine.

3. **A lane's normal silence tripping the limit**: dsh 180 s — dsh mtime moves per event; but what about dsh's ~30 s MCP shutdown after answer — runner kills after 60 s grace; 180 s fine. pi 180 — fine. claude 180: stream-json emits events per block; claude reasoning — Claude Code emits assistant events as they stream; long tool runs emit. OK. codex 600 — measured reasoning killed at 180; is 600 enough? The first live failure: last event 23:08:04, kill ~23:11 (180 s). In the live relay run just now, codex step passed (relay 6m43s total across 4 lanes). codex reasoning at effort low... The matrix used gpt-5.6-luna with reasoning_effort low. 600 s is the spec's floor ("codex gets at least 600 s"). ✓

4. **Host stall**: host takes no stall limit; wall still 600. The first live host cell failed rollcall_matches in 138 s; now passes in 111 s. ✓

5. **README suite figure**: says 902 tests, 873 s; shards 328.9/285.4/258.4 s on 2026-10-02. I'll verify count via the shard runs.

6. Check `_relay` steps: relay steps depend on each other; the codex step got 600 s. ✓ (verified by live run).

7. **A report whose lane names another lane**: `rollcall_matches` fails it. But what about `schema_valid`? It requires lane: string. And `final_message_matches` regex '"status": "PRESENT"'. Fine.

8. **Deletion test / depth**: `worker_env` in proc.py — the lowest module every launch goes through. proc.py is imported by seat_runner, worker, cli_lane, pi_runner. Good locality. The duplication in seat_runner removed. ✓

9. **Prose contradictions**:
   - lanes.md: "Every lane also drops the launching session's variables (CLAUDE*, CLAUDECODE, ANTHROPIC_BASE_URL), hermetic or not." True for all five lanes now.
   - lanes.md pi row: "has no profile; it is always hermetic..." — pi_runner: PI_OFFLINE=1 etc. plausible; pre-existing.
   - lanes.md claude row: keeps "the project's own `.claude` files" — with --setting-sources project,local: project settings load. And CLAUDE_CODE_DISABLE_CLAUDE_MDS disables *all* CLAUDE.md files including the project one — does the doc claim the project's CLAUDE.md is kept? It says "the project's own `.claude` files" — `.claude` directory (settings/commands/agents), not CLAUDE.md. Instruction files are named separately ("the user's instruction files"). Borderline but defensible. Hmm — is it accurate that project settings load? --setting-sources project,local loads .claude/settings.json in project and local dirs. Yes.
   - README: "The `host` lane takes no stall limit." ✓ matches STALL_S.
   - campaign.md watch section: says `ohflow campaign` adds `.watch.*.json` to .gitignore. ✓ code does.
   - rollcall.py docstring: updated. ✓

10. **Check gitignore effect on existing campaigns**: ensure_ignores adds the pattern to a campaign root's .gitignore — for campaigns that already have a .gitignore without it, it appends. The watcher cursor file .watch.agent.json in campaign root — now ignored. ✓ test 49 covers.

11. **dsh docstring escape fixed** (commit caed658 mentions): fake_dsh `_escape` docstring `\\` fine.

12. **Potential regression**: `worker_env` name — proc.py is a low-level module; adding a domain rule there. Fine.

13. **The `campaign watch` fix**: does `.watch.*.json` in .gitignore also cover nested? The cursor lives at campaign root. `campaign.log` etc. are root-level too. Pattern `.watch.*.json` matches root-level files in git semantics (no slash → matches at any depth actually). Fine.

14. Check `test_defect_07` change: waits 10/15→60 s. It's a timing-budget loosening, not weakening an assertion (still asserts events happen). Acceptable; commit message explains. But `process.wait(timeout=LOADED_BOX_WAIT_S)` changed from 60 to 60 in second test — same. First test 15→60. The assertions are unchanged. OK.

15. One more grep per instructions: "a worker launch on any lane that still passes CLAUDE*, CLAUDECODE or ANTHROPIC_BASE_URL (grep every place an environment is built for a child)". I found cli.py:342 (detached supervisor), cli.py:787 (campaign driver detach), exec.py:81 (command steps). Are command steps "workers"? In ohflow plans, a step can be kind "worker" or "command". Command steps run shell commands via exec.py — e.g., in the rollcall plan? No command steps in rollcall. In campaign plans? The judge runs as a worker. Command steps are the operator's own commands (like `git` operations in m-milestone plans?). Let me check what uses command steps: grep kind="command" in plans. If a command step builds env via exec.py with dict(os.environ), CLAUDE* leaks into it. Is that a defect? The spec's scope: "every worker, on every lane". A command step is not a lane worker. And arguably a command step is the operator's own shell — inheriting is expected. I'll note as observation, not a finding.

Also detach.launch — supervisor. The supervisor env having CLAUDE* doesn't matter because workers strip at their own seam. ✓ (proved by live run: host worker reported OpenHands with CLAUDECODE=1 exported.)

16. The pi lane: `env["OHFLOW_BASH"] = os.environ.get(...)` — reads from os.environ; OHFLOW_BASH is not CLAUDE*. Fine.

17. `seat_runner.py` line 104: `env=dict(env) if env is not None else seat_env()` — fine.

Now: are there tests that pin prose (the ones about lanes.md)? The instructions say "A test that pins prose moves with the prose" — implementer's concern. Check none of the new tests pin prose. They don't.

Next: run the three shards (each foreground, log outside worktree). That's ~5 min each. Then confirm test counts (902).

Also verify exit criterion 1 more strictly: "ran ≥ 5 tests, one per lane" — ran 6. ✓

Let me also double check the `--shard` exists: run_tests.py --shard K/3.

Also check the second live-run subtlety: `--out "$(mktemp -d)"` produced `C:\Users\<user>\AppData\Local\Temp\tmp.TJIVPeaZGb` — interesting, so mktemp in this bash maps /tmp to the Windows temp. Good — exactly the driver pattern with the dot.

One more check on defect 48's rule vs dsh actual: the JS `readable.replace(/^-+/, "")` — but the Python applies `[:251]` AFTER lstrip; JS slices after replace. Same. But JS: `--${...}--` — the final name can be up to 251+4 = 255 chars. ✓ matches test.

Edge difference: JS `readable.replace(/^-+/, "")` removes only the leading run. Python lstrip("-") — same.

What about non-leading runs like "C:\a\--b"? Both keep "---". ✓

Now, one thing I should double check: `session_bucket` uses `spec.get("workspace") or "."` in _record's error path. `session_bucket(".")` → "." is in "._-" class → readable=".", lstrip → "." → "--.---"? Wait: readable = "." → no leading "-" → key "." → name "--.---". That's just the error message naming the bucket; a "." cwd is degenerate anyway. Fine.

Also `session_bucket("")` raises ValueError — but _record calls `session_bucket(spec.get("workspace") or ".")` so "" → ".". Fine.

Now check STALL_S vs lane caps again for the campaign plan module (plans/campaign.py?) — does the campaign plan use stall? Only rollcall changed. Fine.

Let me also look at gates.py `@register` description lambda: `+ (f"; the report names lane {a['lane']}" if a.get("lane") else "")` — when the check has no lane, description unchanged. OK.

Now run the shards. ~15 min total. Run sequentially in foreground, each with its own timeout of 600+ s. Each shard ~5-6 min per README. Set timeout 720 each.

</details>
`CLAUDE_CODE_DISABLE_CLAUDE_MDS` is a real env-bool in the installed CLI (2.1.281), sitting in the same table as `CLAUDE_CODE_SAFE_MODE`. The hermetic mechanism is genuine. Now the full suite as three shards, each in the foreground:
**toolCall bash** id=`call_50277a6bf9724733bec14387`

```json
{
 "command": "cd C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes && python oh-dispatch/tests/run_tests.py --shard 1/3 > ../rev-shard1.log 2>&1; echo \"exit $?\"; tail -4 ../rev-shard1.log",
 "timeout": 720
}
```

#### [77] line 77 · message · toolResult · 2026-10-02T00:38:02.388Z
exit 0
      the end-to-end test is opt-in. Pass --e2e to run_tests.py (it sets OHFLOW_E2E=1). It runs the smoke matrix of `ohflow rollcall` against real models and takes one to three minutes.

summary schema checks: 79   unexpected rejections: 0
ran 301 tests in 394.8s   failures=0 errors=0 skipped=1
**toolResult** for `call_50277a6bf9724733bec14387` (bash)

#### [78] line 78 · message · assistant · 2026-10-02T00:38:07.428Z
**toolCall bash** id=`call_4e32065aa91645f49ad6b8c4`

```json
{
 "command": "cd C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes && python oh-dispatch/tests/run_tests.py --shard 2/3 > ../rev-shard2.log 2>&1; echo \"exit $?\"; tail -3 ../rev-shard2.log",
 "timeout": 720
}
```

#### [79] line 79 · message · toolResult · 2026-10-02T00:43:30.955Z
exit 0

summary schema checks: 82   unexpected rejections: 0
ran 301 tests in 322.6s   failures=0 errors=0 skipped=0
**toolResult** for `call_4e32065aa91645f49ad6b8c4` (bash)

#### [80] line 80 · message · assistant · 2026-10-02T00:43:36.438Z
**toolCall bash** id=`call_cd99dba8f17d49bbb7f9b57d`

```json
{
 "command": "cd C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes && python oh-dispatch/tests/run_tests.py --shard 3/3 > ../rev-shard3.log 2>&1; echo \"exit $?\"; tail -3 ../rev-shard3.log",
 "timeout": 720
}
```

#### [81] line 81 · message · toolResult · 2026-10-02T00:48:25.975Z
exit 0

summary schema checks: 86   unexpected rejections: 0
ran 300 tests in 288.5s   failures=0 errors=0 skipped=0
**toolResult** for `call_cd99dba8f17d49bbb7f9b57d` (bash)

#### [82] line 82 · message · assistant · 2026-10-02T00:48:40.664Z
<details><summary>thinking</summary>

All three shards pass: 301 + 301 + 300 = 902 tests, 0 failures, 1 opt-in skip. README says "902 tests, 873 s" — my shards: 394.8 + 322.6 + 288.5 = 1005.9 s. README says 873 s with shards 328.9/285.4/258.4. My run is slower (this box ran a live matrix before, and shard 1 at 394.8 s vs claimed 328.9 s). The README figure says "on 2026-10-02" with specific numbers — a dated measurement, honest. My run doesn't contradict the claim materially (the claim is dated; timings vary with load). The count 902 matches exactly. Not a finding: README says "Each shard stays under ten minutes" — 394.8 s ≈ 6.6 min ✓.

Hmm, but is "A full run takes about fifteen minutes (902 tests, 873 s on 2026-10-02)" — my sum is 1006 s ≈ 16.8 min. "About fifteen minutes" still holds roughly. Under contention (I ran the live matrix first, and the box may still have had processes). Not a defect.

Now, remaining adversarial items:

1. Check the git status of my worktree is clean (I wrote logs outside: ../rev-*.log — outside the worktree ✓; the base archive in /tmp ✓; live run output in Windows temp ✓).

2. Double-check there are no other test files that pinned the old prose (e.g., tests asserting the old dsh bucket docstring or old README). The suite passed, so no contradictions.

3. Check commit messages for authorship violations (no Co-Authored-By, no generated-with).

4. Confirm only oh-dispatch/** changed in the diff vs base. ✓ (stat shows only oh-dispatch paths)

5. Authorship in files: grep for "Co-Authored" and "generated with" in the diff.

Let me also spot-check one more possible hole in the worker_env regex: a var named exactly "CLAUDE" (no suffix) matches (stripped) — intended CLAUDE* removal. A var named "CLAUDEFOO" stripped. Any var the *user* needs like "CLAUDE_CODE_OAUTH_TOKEN"? Stripped — but the claude lane needs login: login is file-based (~/.claude/.credentials.json or Keychain), not env. The live hermetic cell passed with the strip active (my exported CLAUDE* were stripped, and the worker still authenticated as Claude Code haiku). ✓ And what about `ANTHROPIC_API_KEY`? Not stripped — kept, harmless.

One more: the live relay run — check the codex step didn't hit its stall: relay passed in 402.9 s total. Let me peek at the codex step's stall_timeout_s in the plan record and whether any stall event occurred. Also verify the dsh relay step found its session under the dot-path bucket. Quick check of the run's summary for the relay.

Also verify commit list cleanliness.

</details>
All shards green: 301 + 301 + 300 = 902 tests, matching the README count. Final integrity checks — authorship, stray-file cleanliness, and the relay cell's codex step:
**toolCall bash** id=`call_384cf6a038fa4084bf5f3fd0`

```json
{
 "command": "cd C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes && git log arch/deepening..HEAD --format=\"%h %an: %s\" && echo ---- && git log arch/deepening..HEAD --format=\"%b\" | grep -i \"co-authored\\|generated\" ; echo \"authorship grep exit $?\"; git diff arch/deepening...HEAD | grep -i \"co-authored\\|generated with\"; echo \"diff grep exit $?\"; git status --porcelain; echo \"status exit $?\""
}
```
**toolCall bash** id=`call_62d10b04761848d7b7391e54`

```json
{
 "command": "python - <<'EOF'\nimport json\nbase = r'C:/Users/<user>/AppData/Local/Temp/tmp.TJIVPeaZGb'\ns = json.load(open(base + '/03-relay-pi-claude-codex-dsh-1/run/summary.json', encoding='utf-8'))\ndef walk(o, path=()):\n    if isinstance(o, dict):\n        if 'stall_timeout_s' in o: print(path, '->', o.get('id'), 'stall', o['stall_timeout_s'], 'outcome', o.get('outcome') or o.get('status'))\n        for k, v in o.items(): walk(v, path + (k,))\n    elif isinstance(o, list):\n        for i, v in enumerate(o): walk(v, path + (i,))\nwalk(s)\nEOF"
}
```

#### [83] line 83 · message · toolResult · 2026-10-02T00:48:40.990Z
01b5719 Example Operator: oh-dispatch README: suite figure from a three-shard run after the dsh bucket, stall-table and watcher-cursor fixes (902 tests)
caed658 Example Operator: oh-dispatch campaign: .watch.*.json joins the campaign's git ignores, so a watcher's cursor no longer counts as a judge's stray edit and no longer escalates a REVISE; dsh docstring escape fixed
3bbb2ef Example Operator: oh-dispatch roll call: host has no stall row because it takes no stall limit; README says so, and says the quick figure sums cells of the full run
235a9fa Example Operator: oh-dispatch dsh lane: the session bucket follows dsh's own projectKey, so a worktree path with '.', '_', a space or a non-ASCII letter finds its session; a miss names the bucket it searched
c9004e3 Example Operator: oh-dispatch README: quick and full wall times from the first full matrix, suite figure from a three-shard run on this branch
bd76078 Example Operator: oh-dispatch tests: the detached-run tests wait up to 60 s on every real-process step through one helper, because 10 s failed under suite load
52dbe58 Example Operator: oh-dispatch roll call: the stall limit is per lane (codex 600 s) and the gate fails a report that names another lane than its step
139fac7 Example Operator: oh-dispatch claude lane: profile=hermetic sets CLAUDE_CODE_DISABLE_CLAUDE_MDS so no instruction file loads; lanes.md says per lane what hermetic removes and keeps
18f4bcd Example Operator: oh-dispatch: one worker_env rule strips the launching session's variables from every lane, so pi and host no longer inherit CLAUDE*, CLAUDECODE or ANTHROPIC_BASE_URL
----
authorship grep exit 1
diff grep exit 1
status exit 0
**toolResult** for `call_384cf6a038fa4084bf5f3fd0` (bash)

#### [84] line 84 · message · toolResult · 2026-10-02T00:48:40.991Z
(no output)
**toolResult** for `call_62d10b04761848d7b7391e54` (bash)

#### [85] line 85 · message · assistant · 2026-10-02T00:48:44.327Z
<details><summary>thinking</summary>

Clean authorship, clean tree, clean commits. The summary.json walk didn't find stall_timeout_s (different key names). Let me check the relay run's step records for stall limits and any stall kill — look for "stall" in the run dir files.

</details>
**toolCall bash** id=`call_d4ee380a5feb4226bf0394b8`

```json
{
 "command": "grep -rl \"stall\" \"C:/Users/<user>/AppData/Local/Temp/tmp.TJIVPeaZGb/03-relay-pi-claude-codex-dsh-1/run\" 2>/dev/null | head; echo ----; grep -rho \"\\\"stall_timeout_s\\\"[: ]*[0-9null]*\" \"C:/Users/<user>/AppData/Local/Temp/tmp.TJIVPeaZGb/03-relay-pi-claude-codex-dsh-1/run\" 2>/dev/null | sort | uniq -c"
}
```

#### [86] line 86 · message · toolResult · 2026-10-02T00:48:44.847Z
C:/Users/<user>/AppData/Local/Temp/tmp.TJIVPeaZGb/03-relay-pi-claude-codex-dsh-1/run/exit-report.html
C:/Users/<user>/AppData/Local/Temp/tmp.TJIVPeaZGb/03-relay-pi-claude-codex-dsh-1/run/phases/01.relay-1-pi-1/01.pi-1/attempts/01/spec.json
C:/Users/<user>/AppData/Local/Temp/tmp.TJIVPeaZGb/03-relay-pi-claude-codex-dsh-1/run/phases/01.relay-1-pi-1/01.pi-1/spec.json
C:/Users/<user>/AppData/Local/Temp/tmp.TJIVPeaZGb/03-relay-pi-claude-codex-dsh-1/run/phases/02.relay-2-claude-1/01.claude-1/attempts/01/spec.json
C:/Users/<user>/AppData/Local/Temp/tmp.TJIVPeaZGb/03-relay-pi-claude-codex-dsh-1/run/phases/02.relay-2-claude-1/01.claude-1/spec.json
C:/Users/<user>/AppData/Local/Temp/tmp.TJIVPeaZGb/03-relay-pi-claude-codex-dsh-1/run/phases/03.relay-3-codex-1/01.codex-1/attempts/01/spec.json
C:/Users/<user>/AppData/Local/Temp/tmp.TJIVPeaZGb/03-relay-pi-claude-codex-dsh-1/run/phases/03.relay-3-codex-1/01.codex-1/spec.json
C:/Users/<user>/AppData/Local/Temp/tmp.TJIVPeaZGb/03-relay-pi-claude-codex-dsh-1/run/phases/04.relay-4-dsh-1/01.dsh-1/attempts/01/logs/dsh-stderr.log
C:/Users/<user>/AppData/Local/Temp/tmp.TJIVPeaZGb/03-relay-pi-claude-codex-dsh-1/run/phases/04.relay-4-dsh-1/01.dsh-1/attempts/01/result.json
C:/Users/<user>/AppData/Local/Temp/tmp.TJIVPeaZGb/03-relay-pi-claude-codex-dsh-1/run/phases/04.relay-4-dsh-1/01.dsh-1/attempts/01/spec.json
----
      9 "stall_timeout_s": 180
      3 "stall_timeout_s": 600
      3 "stall_timeout_s":180
      1 "stall_timeout_s":600
**toolResult** for `call_d4ee380a5feb4226bf0394b8` (bash)

#### [87] line 87 · message · assistant · 2026-10-02T00:48:53.762Z
<details><summary>thinking</summary>

The relay's codex step got `stall_timeout_s: 600` (3 occurrences of 600: plan + spec + attempt spec) and the others 180. The dsh step found its session under the dot-path worktree (the relay passed, and the dsh result.json mentions stall only in the spec echo presumably). Let me quickly confirm the dsh step's result has no error and its session copy exists.

Then remaining: check the review's item "a hermetic claude session ... that loses its login" — proven kept (live hermetic cell ran on OAuth). ✓

Item: "README figures that do not match the measured matrix.json or a shard run" — verified ✓ (count 902 exact; times dated and mine within reason).

Item: "a stall limit that a lane's normal silence can still trip" — codex 600 ✓ live relay passed; dsh 180 with mtime liveness ✓ (live dsh relay step passed, ~402 s cell total, dsh last step in it).

One more possible check: `single:host` — no stall limit; wall 600. Live host passed in 111 s. ✓

Also the review item about "a test that passes both with and without its fix" — all six defect files verified red at base. ✓

Item: "prose that now contradicts the code" — checked lanes.md, campaign.md, README, rollcall docstring. One more place: SKILL.md mentions? Let me grep SKILL.md for stall/CLAUDE/hermetic claims that may now be stale. And check references/ohflow.md for the env rule or stall. Quick grep.

</details>
The relay's codex step carried 600 s; every other lane 180 s. Last prose sweep — SKILL.md and the other references for now-stale claims about env, stall, or hermetic:
**toolCall bash** id=`call_4c5f5e3143e6454d83be7084`

```json
{
 "command": "cd C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes && grep -rn \"stall\" oh-dispatch/SKILL.md oh-dispatch/references/*.md | grep -v lanes.md | head; echo ----; grep -rn \"CLAUDE\\*\\|CLAUDECODE\\|ANTHROPIC_BASE_URL\\|worker_env\" oh-dispatch/SKILL.md oh-dispatch/references/*.md | head; echo ----; grep -rn \"hermetic\" oh-dispatch/references/ohflow.md oh-dispatch/SKILL.md | head"
}
```
**toolCall bash** id=`call_d42afd53d9674b8685d13606`

```json
{
 "command": "python -c \"\nimport json\nr=json.load(open(r'C:/Users/<user>/AppData/Local/Temp/tmp.TJIVPeaZGb/03-relay-pi-claude-codex-dsh-1/run/phases/04.relay-4-dsh-1/01.dsh-1/attempts/01/result.json',encoding='utf-8'))\nprint('dsh error:', r.get('error')); print('dsh exit:', r.get('exit_code'), 'wall', r.get('wall_s'))\nimport glob; print('session copies:', glob.glob(r'C:/Users/<user>/AppData/Local/Temp/tmp.TJIVPeaZGb/03-relay-pi-claude-codex-dsh-1/run/phases/04.relay-4-dsh-1/01.dsh-1/attempts/01/session/*'))\n\""
}
```

#### [88] line 88 · message · toolResult · 2026-10-02T00:48:54.002Z
oh-dispatch/references/brief-templates.md:31:dependencies already installed.> Run tests with `<test command>`.
oh-dispatch/references/campaign.md:96:| Smoke test | Build, install and start the product the way a user does; drive every new CLI verb and MCP tool once against a real target; record the transcript. |
oh-dispatch/references/campaign.md:178:ledger that stops growing across two polls, is a stall.
oh-dispatch/references/campaign.md:180:The ledger moves only between runs. A quiet ledger is normal while a run goes. The stall
oh-dispatch/references/campaign.md:182:the first line of `campaign watch`. The campaign-level stall is a `campaign watch` whose first
oh-dispatch/references/dashboard.md:47:                "idle_s": 3, "stall_timeout_s": null},
oh-dispatch/references/dashboard.md:128:| Agent idle time | above half of `stall_timeout_s`, or 300 s when unset | above `stall_timeout_s`, or 900 s when unset |
oh-dispatch/references/implement-review.md:38:| `--install-cmd` | `npm ci --no-audit --no-fund` | run once in the fresh worktree |
oh-dispatch/references/ohflow.md:43:A **stall** is a `worker_error`. When `stall_timeout_s` expires, the lane kills the worker and the attempt records `stall` as its error. The attempt's tokens then include `worker_error`.
----
oh-dispatch/references/lanes.md:61:A hermetic worker starts from nothing the seat owns, except its login. Every lane also drops the launching session's variables (`CLAUDE*`, `CLAUDECODE`, `ANTHROPIC_BASE_URL`), hermetic or not.
oh-dispatch/references/lanes.md:163:- **A clean environment.** Every `CLAUDE*` variable and `ANTHROPIC_BASE_URL` is removed. A desktop-app session exports 25 `CLAUDE*` names and an `ANTHROPIC_BASE_URL` that points at the app's own proxy.
----
**toolResult** for `call_4c5f5e3143e6454d83be7084` (bash)

#### [89] line 89 · message · toolResult · 2026-10-02T00:48:54.043Z
dsh error: None
dsh exit: None wall None
session copies: ['C:/Users/<user>/AppData/Local/Temp/tmp.TJIVPeaZGb/03-relay-pi-claude-codex-dsh-1/run/phases/04.relay-4-dsh-1/01.dsh-1/attempts/01/session\\session.v3.jsonl.zstd']
**toolResult** for `call_d42afd53d9674b8685d13606` (bash)

#### [90] line 90 · message · assistant · 2026-10-02T00:49:13.564Z
<details><summary>thinking</summary>

The dsh step in the relay found and copied its session log under the dot-path bucket — the fix works live.

lanes.md:163 says "A clean environment. Every `CLAUDE*` variable and `ANTHROPIC_BASE_URL` is removed." — that's the pre-existing claude section? Let me check the context of line 163 (in the claude lane section, presumably). It says "Every CLAUDE* variable and ANTHROPIC_BASE_URL is removed" — does it mention CLAUDECODE? Line 61 mentions all three. Line 163 might be in a claude-specific paragraph from an earlier milestone. It doesn't mention CLAUDECODE — minor omission but not a contradiction (CLAUDECODE starts with CLAUDE, so "every CLAUDE* variable" covers it). Fine.

Everything checks out. Now let me double-check the remaining exit criterion runs are all documented:

1. `-k parent_session`: exit 0, 6 tests ✓
2. `-k hermetic`: exit 0, 10 tests ✓
3. `-k report_lane`: exit 0, 5 tests ✓
4. Live rollcall with env vars + mktemp -d out: `ROLLCALL PASS: 3 of 3 cells` ✓ (last line)
5. grep "not measured yet": no match ✓

Full suite: 3 shards, 902 tests, 0 failures ✓ (README's count matches exactly).

Adversarial checklist:
- Worker launch still passing CLAUDE*: all five lanes strip at their launch seams (CliLane/HostLane worker_env; adapters seat_env→worker_env; pi worker_env). Remaining `dict(os.environ)` sites are the detached supervisor (cli.py:342), the detached campaign driver (cli.py:787), and command-step exec (exec.py:81) — none is a worker launch, and the live run proves the strip holds end-to-end from a session exporting CLAUDECODE=1. Not defects; worth one line as an observation.
- Hermetic claude: real env var (verified in the 2.1.281 binary's env table), keeps OAuth (live cell authenticated and billed 171.5 k tokens on the seat), `--setting-sources project,local` drops user settings. Live cell reported no MCP servers.
- Stall limits: per lane; codex 600 proven live (relay passed; codex step previously died at 180). host takes none.
- Report lane gate: every shape's rollcall_matches carries the lane; wrong lane fails; missing lane fails when the step names one.
- README figures: quick 1466.5 s = sum of cells 1–10 of the measured matrix ✓; full 1942.7 s ✓; failure counts 2/10 and 3/15 ✓; suite 902 tests ✓ (my shards: 301+301+300); shard timings dated 2026-10-02, mine modestly slower under load (394.8/322.6/288.5), "about five minutes"/"under ten minutes" holds.
- dsh bucket: port matches dsh's projectKey JS exactly (separator runs → one `-`; [A-Za-z0-9._-] kept; ~XXXX uppercase hex per UTF-16 unit; leading run stripped; root; 251 cut; -- wrap). Live relay dsh step found its session under `tmp.TJIVPeaZGb` — the exact shape that hid the defect in attempt 1.
- Tests red at base: all six defect files fail against arch/deepening ✓ (44: 5 failures+1 error; 45: 1 failure; 46: 4 errors; 47: 1 failure+1 error; 48: 11 subtest failures; 49: not run at base — hmm, I didn't run defect 49 at base! Let me run it to be complete.)

Actually I ran parent_session, hermetic, report_lane, dsh_session_bucket, rollcall_stall at base — not the campaign watch one (defect 49). Let me run `-k campaign_watch` at base — careful: -k campaign_watch may match existing tests too. Run it and check test_defect_49 specifically fails at base. It uses fake lanes (FakeLane) and drive — should run hermetically. Let me do it.

Also one more possible check: does anything else read `_PARENT_SESSION_VARS` from seat_runner (e.g., an old test importing it)? Suite passed, so no. grep to be sure.

</details>
One defect test I haven't proven red at base: the watcher-cursor one (49). Also confirm nothing still imports the moved symbol:
**toolCall bash** id=`call_24e50bbedfe9496e9630e014`

```json
{
 "command": "cd C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes && grep -rn \"_PARENT_SESSION_VARS\" oh-dispatch/ --include=*.py; echo \"import grep exit $?\"; tmp=$(cat /tmp/base-dir.txt); cp oh-dispatch/tests/test_defect_49_campaign_watch_is_not_a_stray_edit.py \"$tmp/oh-dispatch/tests/\" && cd \"$tmp/oh-dispatch/scripts\" && python ../tests/run_tests.py -k watch_during > /tmp/base-49.log 2>&1; echo \"== defect49 at base exit $?\"; grep -E \"FAIL|ERROR|ran [0-9]+ tests\" /tmp/base-49.log | tail -5",
 "timeout": 300
}
```

#### [91] line 91 · message · toolResult · 2026-10-02T00:49:24.571Z
oh-dispatch/scripts/ohflow/proc.py:21:_PARENT_SESSION_VARS = re.compile(r"^(CLAUDE|CLAUDECODE$|ANTHROPIC_BASE_URL$)")
oh-dispatch/scripts/ohflow/proc.py:31:    return {k: v for k, v in source.items() if not _PARENT_SESSION_VARS.match(k)}
import grep exit 0
== defect49 at base exit 1
FAIL: test_a_watch_during_the_judge_does_not_escalate_a_revise (tests.test_defect_49_campaign_watch_is_not_a_stray_edit.WatcherCursorIsNotAStrayEdit.test_a_watch_during_the_judge_does_not_escalate_a_revise)
FAILED (failures=1)
ran 1 tests in 6.7s   failures=1 errors=0 skipped=0
**toolResult** for `call_24e50bbedfe9496e9630e014` (bash)

#### [92] line 92 · message · assistant · 2026-10-02T00:49:52.349Z
<details><summary>thinking</summary>

All six defect test files are red at base, green on the branch. The single-source rule holds: `_PARENT_SESSION_VARS` lives only in proc.py.

Everything on my adversarial checklist resolves clean:

1. Worker launches still passing CLAUDE* — none. All five lanes strip at one rule in `proc.worker_env`; the remaining `dict(os.environ)` sites (cli.py:342 detached supervisor, cli.py:787 campaign driver detach, exec.py:81 command steps) are not worker launches, and the live run from a session exporting `CLAUDECODE=1` proved it end-to-end (host reported OpenHands).
2. Hermetic claude — `CLAUDE_CODE_DISABLE_CLAUDE_MDS` verified as a real env-bool in the installed 2.1.281 binary; `--setting-sources project,local` drops user settings; login kept (live cell authenticated on the seat and produced 171.5 k tokens); reported zero MCP servers. lanes.md table states remove/keep per lane.
3. Stall per lane — codex 600 s (spec floor), others 180, host none, override works; live relay passed with codex at 600.
4. Report lane gate — every rollcall_matches check in every shape carries the step's lane; wrong or missing lane fails; live cells all named their own lanes.
5. README figures — quick/full wall times match matrix.json exactly (1466.5 s / 1942.7 s, 2/10 and 3/15 failed); suite figure 902 tests matches my three shards exactly; timings dated and honest.
6. dsh bucket — port matches dsh's projectKey JS line for line; live relay dsh step found its session under a `tmp.XXXX` worktree, the exact attempt-1 trap.
7. No test passes with and without its fix — all six defect files verified red against arch/deepening.
8. Prose — lanes.md, campaign.md, README, rollcall docstring all match the code; suite passed with the changed prose.

Minor observations (not defects, worth stating):
- `exec.py:81` command steps inherit the parent's CLAUDE* (they are the operator's own shell commands, not lane workers; scope said "every worker, on every lane").
- `worker_env` regex keeps `ANTHROPIC_API_KEY` etc. — deliberate, only the desktop-session identity vars go.
- My shard wall times (394.8/322.6/288.5 s) are slower than the README's dated 328.9/285.4/258.4 s — same 902-test count, box was still settling after the live matrix; the "under ten minutes" claim holds.
- The lone-surrogate edge (`text.encode("utf-16-le")` would raise on one) can't occur in a Windows path dsh would be launched with; not worth a fix.

Cleanup check: my worktree is clean (git status empty at last check; I wrote logs to ../ and /tmp, the archive to /tmp, live run output to the Windows temp). I created nothing inside the worktree.

Verdict: MERGEABLE.

Let me write the final report concisely, ordered by severity (no blocking findings), each check with evidence, then the verdict line. The final message must end with exactly `VERDICT: MERGEABLE`.

</details>
Everything on the checklist is now resolved. The worktree stayed clean throughout; all my artifacts (logs, base archive, live-run output) live outside it. Final report:

## Review of m7-smoke-fixes (attempt 2)

**The diff** (8 commits, 21 files, +589/−52, only `oh-dispatch/**`): one `worker_env` rule in `proc.py` used by all five lanes; hermetic claude via `CLAUDE_CODE_DISABLE_CLAUDE_MDS`; per-lane stall table in `plans/rollcall.py`; `lane` argument on every `rollcall_matches` check; dsh `session_bucket` ported from dsh's own `projectKey`; `.watch.*.json` git-ignored; README measured figures; loosened detached-run wait bounds.

**Exit criteria, all run myself:**

1. `-k parent_session`: exit 0, **6 tests ran** (≥5, one per lane). ✓
2. `-k hermetic`: exit 0, **10 tests ran**. ✓
3. `-k report_lane`: exit 0, **5 tests ran**. ✓
4. Live run from `oh-dispatch/scripts` with `CLAUDECODE=1`, `CLAUDE_CODE_ENTRYPOINT=claude-desktop`, `CLAUDE_AGENT_SDK_VERSION=0.3.284` exported and `--out "$(mktemp -d)"` (→ `...\Temp\tmp.TJIVPeaZGb`, a dot path): last line `ROLLCALL PASS: 3 of 3 cells` (host 111 s, hermetic claude 47.8 s, relay 402.9 s). ✓
5. `grep -n "not measured yet" oh-dispatch/README.md`: no match. ✓

**Full suite:** three shards, foreground, sequential — exit 0 each; 301 + 301 + 300 = **902 tests, 0 failures, 1 opt-in skip**; the README's "902 tests" matches exactly.

**Adversarial findings, most severe first — none blocking:**

- **No worker launch leaks the parent session.** Every seam builds on one rule: `cli_lane.py:251` and `worker.py:154` (`worker_env()`), adapters via `seat_env` → `seat_runner.py:40` → `proc.worker_env()`; the regex lives only in `proc.py:21`. Remaining `dict(os.environ)` sites (`cli.py:342` detached supervisor, `cli.py:787` campaign-driver detach, `exec.py:81` command steps) are not worker launches — and the live host cell, run with `CLAUDECODE=1` exported, reported `harness: "OpenHands agent SDK terminal harness"`. Observation only: a plan *command* step still inherits `CLAUDE*`; the spec scoped the rule to lane workers, so this is not a defect.
- **Hermetic claude is real, not folklore.** `CLAUDE_CODE_DISABLE_CLAUDE_MDS` is a genuine env-bool in the installed 2.1.281 binary (found in its env-var table beside `CLAUDE_CODE_SAFE_MODE`); `--setting-sources project,local` drops user settings; the login survived — the live hermetic cell authenticated on the seat (171.5 k tokens) and reported `mcp_servers: []`, `lane: "claude"`.
- **Stall limits fit each lane.** The relay's codex step ran with `stall_timeout_s: 600` (verified in its spec.json), others 180, host none (`STALL_S` rows exactly equal the `CAP_STALL` lanes; no lane can miss the table). `stall_timeout_s=45` overrides every lane (tested).
- **The report-lane gate has no gap.** I enumerated every `rollcall_matches` check in all seven shapes: each carries its step's lane (`single/fanout/relay/merge/retry/review/campaign`). Wrong lane fails, missing lane fails, absent check argument leaves it unchecked by design.
- **README figures are the measured ones.** `matrix.json` sums: cells 1–10 = 1466.5 s (README "24 m 27 s (1466.5 s)"), all 15 = 1942.7 s ("32 m 23 s"), failures 2/10 and 3/15 — all exact, and honestly labelled as one full-matrix run, not a `quick` run. My shards were slower than the README's dated 328.9/285.4/258.4 s (394.8/322.6/288.5 s under load); same 902 tests, "under ten minutes" holds.
- **dsh bucket matches dsh itself.** I read `projectKey` at the cited `lib/index.js:874-893` and compared line by line: separator runs → one `-`, `[A-Za-z0-9._-]` kept, `~XXXX` uppercase-hex per UTF-16 unit, leading run stripped, `root`, 251 cut, `--` wrap — all identical. The live relay's dsh step found and copied its session under the `tmp.TJIVPeaZGb` worktree, the exact shape that hid the defect in attempt 1.
- **No test passes with and without its fix.** I materialized `arch/deepening` in a temp dir via `git archive` and ran every new defect file against it: 44 (5 failures + 1 error), 45 (1 failure), 46 (4 errors), 47 (1 failure + 1 error), 48 (11 subtest failures), 49 (1 failure). All red at base, green on the branch.
- **Prose holds.** `lanes.md` hermetic table, `campaign.md` watch-cursor paragraph, `README` stall sentence, and the rollcall docstring each match the code; the full suite (which pins prose) passed with them.
- Clean authorship on all 8 commits (author "Example Operator", no co-author/footer lines), clean tree, no file written inside the worktree by me.

Minor notes, not defects: the dsh port's `encode("utf-16-le")` would raise on a lone surrogate (impossible in a Windows working path dsh is launched with); `bd76078` loosens wait *bounds* 10/15 s → 60 s without weakening any assertion, with the reason in the commit message and docstring.

VERDICT: MERGEABLE

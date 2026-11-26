# Transcript — 02.review/01.review attempt 3 (lane pi)- Canonical run: `m7-smoke-fixes` (plan `deepening-m7-smoke-fixes`)- Original source: `C:\Users\<user>\ohflow-home\workflows\oh-dispatch-deepening\milestones\m7-smoke-fixes\runs\m7-smoke-fixes\phases\02.review\01.review\attempts\03\session\2026-10-02T01-50-58-129Z_01a0fa4e-b84f-7599-859e-9f853b8b9d2b.jsonl`- Records: 110; tool calls: 61; tool results: 61- Message and tool-output text is complete after redaction. Missing timestamps remain unknown.- Rebuild with `python collect.py` (read-only).
#### [1] line 1 · session · 2026-10-02T01:50:58.129Z

#### [2] line 2 · model-change · 2026-10-02T01:50:58.182Z

#### [3] line 3 · thinking-level-change · 2026-10-02T01:50:58.182Z

#### [4] line 4 · message · user · 2026-10-02T01:50:58.202Z
<file name="C:\Users\<user>\ohflow-home\workflows\oh-dispatch-deepening\milestones\m7-smoke-fixes\runs\m7-smoke-fixes\phases\02.review\01.review\attempts\03\brief.md">
## Your position in this run

Run:       m7-smoke-fixes     plan: deepening-m7-smoke-fixes
Phase:     2 of 2 - "Review"
Step:      1 of 1 in this phase - id `review`, role `review`, attempt 3
Coordinate: 02.review/01.review
Worktree:  C:\Users\<user>\dev\_wt\oh-dispatch-deepening\m7-smoke-fixes
           branch arch/m7-smoke-fixes, created from arch/deepening at 7426973
You own:   no path is reserved for you in this plan

Already done, before you (phases 1 to 1):
  01.implement/01.implement - role `implement` - commit f4a6063 - gate PASSED

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
   - a resumed run (journal events after its last `run_finished`, a live supervisor, an older
     `exit.json`) that `ohflow status`, `ohflow watch` or the dashboard snapshot still calls
     finished; build one in a temp dir and run both verbs on it;
   - a roll-call worker whose iteration budget a normal run can use up: in your criterion-4 run,
     read each step's `llm_calls` (or turn count) in `result.json` against `max_iterations` in its
     `spec.json`, and report the host cell's two numbers;
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

#### [5] line 5 · message · assistant · 2026-10-02T01:51:09.961Z
<details><summary>thinking</summary>

Let me start by understanding the situation. I'm a reviewer for milestone m7-smoke-fixes. I need to:

1. Read the charter
2. Read the spec (given above)
3. Read the whole milestone diff
4. Run the exit criteria
5. Look for defects
6. Give a verdict

Let me start by reading the charter and looking at the repository.

</details>
**toolCall bash** id=`call_f4684d0ec6574b4a93914e97`

```json
{
 "command": "cat \"C:\\Users\\<user>\\ohflow-home\\workflows\\oh-dispatch-deepening\\charter.md\""
}
```
**toolCall bash** id=`call_d262f29a2afb45e8b91165b7`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && git log --oneline arch/deepening..HEAD && git status --porcelain && git diff arch/deepening...HEAD --stat"
}
```

#### [6] line 6 · message · toolResult · 2026-10-02T01:51:10.169Z
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
**toolResult** for `call_f4684d0ec6574b4a93914e97` (bash)

#### [7] line 7 · message · toolResult · 2026-10-02T01:51:10.220Z
f4a6063 oh-dispatch roll call: workers get 30 iterations by default and are told to fill the harness facts from their own prompt, tool list and directory, or write unknown, so a host worker that searched for its own version no longer ends on its budget (test_defect_51)
470cf16 oh-dispatch journal: work after a run_finished reopens the run, and an exit.json older than the journal is not the verdict, so status, watch and the dashboard no longer call a resumed run finished (test_defect_50)
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
 oh-dispatch/references/ohflow.md                   |   2 +-
 oh-dispatch/scripts/ohflow/campaign.py             |   2 +-
 oh-dispatch/scripts/ohflow/claude_runner.py        |  13 ++-
 oh-dispatch/scripts/ohflow/cli_lane.py             |   4 +-
 oh-dispatch/scripts/ohflow/dsh_runner.py           |  36 +++++-
 oh-dispatch/scripts/ohflow/exit_report.py          |   5 +-
 oh-dispatch/scripts/ohflow/gates.py                |  12 +-
 oh-dispatch/scripts/ohflow/journal.py              |   9 ++
 oh-dispatch/scripts/ohflow/pi_runner.py            |   2 +-
 oh-dispatch/scripts/ohflow/plans/rollcall.py       |  47 ++++++--
 oh-dispatch/scripts/ohflow/proc.py                 |  17 +++
 oh-dispatch/scripts/ohflow/rundir.py               |  30 ++++-
 oh-dispatch/scripts/ohflow/seat_runner.py          |   9 +-
 oh-dispatch/scripts/ohflow/watch.py                |  20 +---
 oh-dispatch/scripts/ohflow/worker.py               |   4 +-
 oh-dispatch/tests/fakes/fake_dsh.py                |  19 +++-
 .../tests/test_defect_07_detached_run_survives.py  |  29 ++++-
 ...efect_44_parent_session_vars_reach_no_worker.py | 126 +++++++++++++++++++++
 ...5_hermetic_claude_loads_no_instruction_files.py |  57 ++++++++++
 ..._46_rollcall_report_lane_must_match_the_step.py |  59 ++++++++++
 ...t_defect_47_rollcall_stall_limit_is_per_lane.py |  44 +++++++
 ...est_defect_48_dsh_session_bucket_follows_dsh.py |  77 +++++++++++++
 ...defect_49_campaign_watch_is_not_a_stray_edit.py |  57 ++++++++++
 ...test_defect_50_a_resumed_run_is_not_finished.py |  87 ++++++++++++++
 .../tests/test_defect_51_rollcall_worker_budget.py |  68 +++++++++++
 28 files changed, 795 insertions(+), 75 deletions(-)
**toolResult** for `call_d262f29a2afb45e8b91165b7` (bash)

#### [8] line 8 · message · assistant · 2026-10-02T01:51:15.819Z
<details><summary>thinking</summary>

The worktree is clean (git status --porcelain printed nothing) and there are commits. Let me now look at the full diff of each file. Let me start with the core code changes.

</details>
Charter read. Now the full diff, file by file.
**toolCall bash** id=`call_91d601d86b124d1eabef785b`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && git diff arch/deepening...HEAD -- oh-dispatch/scripts/ohflow/proc.py oh-dispatch/scripts/ohflow/worker.py oh-dispatch/scripts/ohflow/pi_runner.py oh-dispatch/scripts/ohflow/claude_runner.py oh-dispatch/scripts/ohflow/seat_runner.py"
}
```
**toolCall bash** id=`call_51d3c39351444f3b9be2a0c8`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && git diff arch/deepening...HEAD -- oh-dispatch/scripts/ohflow/dsh_runner.py oh-dispatch/scripts/ohflow/cli_lane.py"
}
```

#### [9] line 9 · message · toolResult · 2026-10-02T01:51:16.088Z
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
**toolResult** for `call_91d601d86b124d1eabef785b` (bash)

#### [10] line 10 · message · toolResult · 2026-10-02T01:51:16.191Z
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
**toolResult** for `call_51d3c39351444f3b9be2a0c8` (bash)

#### [11] line 11 · message · assistant · 2026-10-02T01:51:21.918Z
<details><summary>thinking</summary>

Let me look at the remaining diff files: gates.py, plans/rollcall.py, journal.py, rundir.py, watch.py, exit_report.py, campaign.py, and the docs.

</details>
**toolCall bash** id=`call_10fa4934c25d4cd090274cf4`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && git diff arch/deepening...HEAD -- oh-dispatch/scripts/ohflow/gates.py oh-dispatch/scripts/ohflow/plans/rollcall.py"
}
```
**toolCall bash** id=`call_b921dc062b67448dbc18461a`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && git diff arch/deepening...HEAD -- oh-dispatch/scripts/ohflow/journal.py oh-dispatch/scripts/ohflow/rundir.py oh-dispatch/scripts/ohflow/watch.py oh-dispatch/scripts/ohflow/exit_report.py oh-dispatch/scripts/ohflow/campaign.py"
}
```

#### [12] line 12 · message · toolResult · 2026-10-02T01:51:22.132Z
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
index af5ae94..503e699 100644
--- a/oh-dispatch/scripts/ohflow/plans/rollcall.py
+++ b/oh-dispatch/scripts/ohflow/plans/rollcall.py
@@ -26,7 +26,11 @@ Arguments: `repo` (required), `shape`, `lanes` (comma list), `count` (workers
 per lane), `consolidator`, `reviewer`, `judge` (each a lane), `profile`
 (`hermetic` for claude and codex), `carry_context`, `config` (a JSON file of
 model overrides), `base`, `prefix`, `wt_root`, `wall_timeout_s`,
-`stall_timeout_s`, `max_iterations`, `max_parallel`.
+`stall_timeout_s` (replaces the per-lane `STALL_S` table; codex gets 600 s,
+`pi`, `claude` and `dsh` get 180 s, and `host` takes no stall limit),
+`max_iterations` (default 30: a worker that looks up its own facts needs more
+than the 5 to 9 calls of a worker that is told where they come from),
+`max_parallel`.
 
     python -m ohflow.cli validate --plan <this file> \\
         --args repo=<scratch repo> --args shape=merge --args lanes=pi,claude
@@ -68,6 +72,12 @@ MODELS = {
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
 
@@ -86,6 +96,10 @@ CAMPAIGN_LINE = "Campaign-Token: M5-ROLLCALL"
 
 REPORT = """# Your report
 
+Fill each value from your own system prompt, your tool list and your working
+directory. Write `unknown` for a value they do not show. Do not search the disk,
+the environment or the run directory for it.
+
 End your last message with one fenced json block and nothing after it. The
 block opens with a line of three backticks and the word `json`. It closes with a
 line of three backticks. A bare JSON object without those two lines fails the
@@ -296,11 +310,17 @@ class Spec:
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
@@ -374,8 +394,9 @@ def normalize(args) -> Spec:
         base=base, prefix=str(args.get("prefix", "rollcall")),
         wt_root=Path(args.get("wt_root", str(repo.parent / f"{repo.name}-rollcall-wt"))),
         wall=int(args.get("wall_timeout_s", 600)),
-        stall=int(args.get("stall_timeout_s", 180)),
-        max_iter=int(args.get("max_iterations", 15)),
+        stall=(int(args["stall_timeout_s"])
+               if args.get("stall_timeout_s") not in (None, "") else None),
+        max_iter=int(args.get("max_iterations", 30)),
         max_parallel=int(args.get("max_parallel", 3)), models=models)
 
 
@@ -406,19 +427,20 @@ def _step(spec: Spec, sid: str, lane: str, brief: str, *, worktree: str,
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
@@ -434,7 +456,7 @@ def _solo(spec: Spec, lane: str, sid: str, *, more: str = "",
     brief = brief if brief is not None else SOLO_BRIEF.format(
         lane=lane, sid=sid, entry=ENTRY, clean=CLEAN, more=more)
     return _step(spec, sid, lane, brief, worktree=sid, owns=(owns,),
-                 checks=_report_checks(owns, since=since, extra=extra),
+                 checks=_report_checks(owns, lane, since=since, extra=extra),
                  objective=f"{sid} reports for duty in {owns}", retry=retry)
 
 
@@ -479,7 +501,8 @@ def _relay(spec: Spec):
         step = _step(
             spec, sid, lane, brief, worktree="relay", owns=("ROLLCALL.md",),
             depends_on=(previous_id,) if previous_id else (),
-            checks=_report_checks("ROLLCALL.md", since="step_start", extra=extra),
+            checks=_report_checks("ROLLCALL.md", lane, since="step_start",
+                                  extra=extra),
             objective=f"{sid} appends its section to the shared ROLLCALL.md")
         phases.append(Phase(name=f"Relay {n} {sid}", steps=(step,)))
         previous_id = sid
@@ -505,8 +528,8 @@ def _merge(spec: Spec):
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
**toolResult** for `call_10fa4934c25d4cd090274cf4` (bash)

#### [13] line 13 · message · toolResult · 2026-10-02T01:51:22.184Z
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
diff --git a/oh-dispatch/scripts/ohflow/exit_report.py b/oh-dispatch/scripts/ohflow/exit_report.py
index a5c2cd8..de00bb2 100644
--- a/oh-dispatch/scripts/ohflow/exit_report.py
+++ b/oh-dispatch/scripts/ohflow/exit_report.py
@@ -83,9 +83,8 @@ def exit_info_from_files(run_dir: Path) -> dict:
     run = rundir.open_run(run_dir)
     if run.state.status in ("finished", "failed", "paused"):
         return exit_info(run.state.status)
-    prior = _read_json(run_dir / "exit.json")
-    if isinstance(prior, dict) and prior.get("status") in ("crashed",
-                                                           "interrupted"):
+    prior = run.exit_record()
+    if prior and prior.get("status") in ("crashed", "interrupted"):
         return {"status": prior["status"], "error": prior.get("error"),
                 "traceback_tail": list(prior.get("traceback_tail") or [])}
     if run.status == rundir.ORPHANED:
diff --git a/oh-dispatch/scripts/ohflow/journal.py b/oh-dispatch/scripts/ohflow/journal.py
index ec0c11d..0baaae3 100644
--- a/oh-dispatch/scripts/ohflow/journal.py
+++ b/oh-dispatch/scripts/ohflow/journal.py
@@ -28,6 +28,10 @@ __all__ = ["Journal", "RunState", "StepRecord", "utcnow", "TERMINAL",
 #: overwrite the record of an execution that genuinely ran.
 SYNTHETIC_ATTEMPT = 0
 
+#: Events that say nothing about the run going again after a `run_finished`.
+_NOT_WORK_EVENTS = frozenset({"run_started", "run_finished",
+                              "journal_recovered"})
+
 STATUSES = (
     "pending", "running", "passed", "failed",
     "timeout", "quarantined", "skipped", "cached", "deferred",
@@ -271,6 +275,11 @@ class Journal:
             ev = rec.get("event")
             payload = rec.get("payload") or {}
             coord = rec.get("coord")
+            if state.finished and ev not in _NOT_WORK_EVENTS:
+                # A resume appends no run-level event. Work after a
+                # `run_finished` is the run going again.
+                state.status = "running"
+                state.finished = None
             if ev == "run_started":
                 state.run_id = payload.get("run_id", state.run_id)
                 state.plan_name = payload.get("plan", state.plan_name)
diff --git a/oh-dispatch/scripts/ohflow/rundir.py b/oh-dispatch/scripts/ohflow/rundir.py
index 3e07979..48bf11d 100644
--- a/oh-dispatch/scripts/ohflow/rundir.py
+++ b/oh-dispatch/scripts/ohflow/rundir.py
@@ -141,6 +141,24 @@ def _read_json(path: Path) -> Any:
         return {"error": f"{path.name} unreadable"}
 
 
+def exit_record(run_dir: Path) -> dict | None:
+    """The `exit.json` of the run's latest stop, or None.
+
+    The file counts only when it is at least as new as the journal."""
+    run_dir = Path(run_dir)
+    try:
+        written = (run_dir / "exit.json").stat().st_mtime
+    except OSError:
+        return None
+    try:
+        if (run_dir / "journal.jsonl").stat().st_mtime > written:
+            return None
+    except OSError:
+        pass
+    record = _read_json(run_dir / "exit.json")
+    return record if isinstance(record, dict) else None
+
+
 # --------------------------------------------------------------------- run
 
 
@@ -221,6 +239,14 @@ class Run:
             self._alive = pid_alive(pid, started_before=written)
         return self._alive
 
+    def exit_record(self) -> dict | None:
+        """`exit.json`, or None when it is absent, unreadable or older than the
+        journal.
+
+        A resume appends to the journal after the earlier stop wrote its exit
+        record. That record then describes a stop the run has since left."""
+        return exit_record(self.run_dir)
+
     @property
     def status_without_journal(self) -> str:
         """The name of a run that has no journal line, from its files.
@@ -231,8 +257,8 @@ class Run:
         """
         if self.supervisor_alive:
             return STARTING
-        recorded = _read_json(self.run_dir / "exit.json")
-        status = recorded.get("status") if isinstance(recorded, dict) else None
+        recorded = self.exit_record()
+        status = recorded.get("status") if recorded else None
         return status if status in STOPPED_STATUSES else NOT_STARTED
 
     @property
diff --git a/oh-dispatch/scripts/ohflow/watch.py b/oh-dispatch/scripts/ohflow/watch.py
index 280bdb2..15778e9 100644
--- a/oh-dispatch/scripts/ohflow/watch.py
+++ b/oh-dispatch/scripts/ohflow/watch.py
@@ -15,7 +15,7 @@ from dataclasses import dataclass, field
 from pathlib import Path
 
 from . import exit_report as ohexit
-from . import live, proc, runstatus
+from . import live, proc, rundir, runstatus
 from .paths import win
 
 EXIT_ENDED_GOOD, EXIT_ENDED_BAD, EXIT_UNKNOWN, EXIT_GOING = 0, 1, 2, 10
@@ -79,20 +79,12 @@ def is_run_dir(run_dir: Path) -> bool:
 
 
 def _exit_status(run_dir: Path) -> str | None:
-    try:
-        return json.loads((run_dir / "exit.json").read_text(
-            encoding="utf-8")).get("status")
-    except (OSError, ValueError, AttributeError):
-        return None
+    return (rundir.exit_record(run_dir) or {}).get("status")
 
 
 def _exit_error(run_dir: Path) -> str | None:
     """The first line of the `error` that `exit.json` records, or None."""
-    try:
-        error = json.loads((run_dir / "exit.json").read_text(
-            encoding="utf-8")).get("error")
-    except (OSError, ValueError, AttributeError):
-        return None
+    error = (rundir.exit_record(run_dir) or {}).get("error")
     lines = str(error or "").strip().splitlines()
     return lines[0] if lines else None
 
@@ -111,11 +103,7 @@ def _exit_report(run_dir: Path, snap: dict) -> tuple[Path | None, str | None]:
         if written is None or written == "running":
             _info, paths, verdict = ohexit.rebuild(run_dir)
             return paths["html"], verdict
-    try:
-        verdict = json.loads((run_dir / "exit.json").read_text(
-            encoding="utf-8")).get("verdict")
-    except (OSError, ValueError):
-        verdict = None
+    verdict = (rundir.exit_record(run_dir) or {}).get("verdict")
     return run_dir / "exit-report.html", verdict
**toolResult** for `call_b921dc062b67448dbc18461a` (bash)

#### [14] line 14 · message · assistant · 2026-10-02T01:51:24.633Z
<details><summary>thinking</summary>

Now the docs and tests.

</details>
**toolCall bash** id=`call_f73bc6122ff64302b308185b`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && git diff arch/deepening...HEAD -- oh-dispatch/README.md oh-dispatch/references/lanes.md oh-dispatch/references/campaign.md oh-dispatch/references/ohflow.md"
}
```
**toolCall bash** id=`call_667e24891c774b60a8c5d836`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && git diff arch/deepening...HEAD -- oh-dispatch/tests/"
}
```

#### [15] line 15 · message · toolResult · 2026-10-02T01:51:24.799Z
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
diff --git a/oh-dispatch/references/ohflow.md b/oh-dispatch/references/ohflow.md
index 5356c9d..fb437af 100644
--- a/oh-dispatch/references/ohflow.md
+++ b/oh-dispatch/references/ohflow.md
@@ -231,7 +231,7 @@ What each verb prints is in the [SKILL](../SKILL.md#verbs) verb table. The roll
 
 **`run` flags.** `--plan`, `--args k=v`, `--out`, `--run-id`, `--max-parallel N`, `--dry-run`, `--detach`, `--only-phase`, `--resume RUN_ID`, `--auto-resume N`, `--no-dashboard`, `--dashboard-port N`, `--open-dashboard`, `--predictions FILE`. `--json` works only with `--detach`; an attached run refuses it and exits 2.
 
-**Resume.** `--resume <RUN_ID>` takes the run id. The run id is the run directory's name under `--out`. `--resume` refuses a run without a journal.
+**Resume.** `--resume <RUN_ID>` takes the run id. The run id is the run directory's name under `--out`. `--resume` refuses a run without a journal. A resume writes no run-level journal event. The run reader decides from the journal alone: a run that has any work event (`phase_started`, `step_started` and the rest) after its last `run_finished` is `running` again, and its finish time is cleared. A resumed run whose supervisor died reads `orphaned`. An `exit.json` older than the journal's last write belongs to an earlier stop, so `status`, `watch` and the exit report ignore it. The resume leaves the old exit files in place, and the next stop replaces them.
 
 **Exit codes.** 0 is success. 2 means the plan or its arguments are wrong: a missing `--args` key prints `plan argument missing: <name> (pass --args <name>=...)`, and an invalid plan prints `PLAN INVALID` and the reasons. Any other exception prints the last lines of its traceback and exits 1. A plan reads optional arguments with `args.get(name, default)`.
**toolResult** for `call_f73bc6122ff64302b308185b` (bash)

#### [16] line 16 · message · toolResult · 2026-10-02T01:51:24.800Z
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
diff --git a/oh-dispatch/tests/test_defect_50_a_resumed_run_is_not_finished.py b/oh-dispatch/tests/test_defect_50_a_resumed_run_is_not_finished.py
new file mode 100644
index 0000000..b339c64
--- /dev/null
+++ b/oh-dispatch/tests/test_defect_50_a_resumed_run_is_not_finished.py
@@ -0,0 +1,87 @@
+"""m7: a resumed run is running, not finished.
+
+A resume appends no run-level event. The journal reads `run_started`,
+`run_finished`, then `phase_started` and `step_started`. The replay set the
+status only on `run_finished`, so `status`, `watch` and the dashboard snapshot
+kept the old verdict while a worker ran. `watch` also read the `exit.json` of
+the earlier finish as the end of the current run, and printed the old verdict
+with exit code 1.
+
+The journal now says what a run is: any work event after a `run_finished`
+reopens the run, and an `exit.json` older than the journal is not a verdict.
+"""
+
+from __future__ import annotations
+
+import os
+import json
+import time
+
+from dashboard_support import Journal, mark_alive, plan_json, worker
+from ohflow import live, watch
+from support import TempCase
+from verb_support import call
+
+STEPS = ["01.map/01.a"]
+DEAD_PID = "2147483646"
+OLD_VERDICT = "Run r-resumed finished: 1 of 1 agents passed"
+
+
+class AResumedRun(TempCase):
+
+    def setUp(self) -> None:
+        super().setUp()
+        self.dir = self.run_dir("r-resumed")
+        plan_json(self.dir, [("Map", [worker("a")], 1)])
+        self.journal = (Journal(self.dir)
+                        .phase(1, "01.map", "Map", STEPS)
+                        .start(2, STEPS[0])
+                        .finish(30, STEPS[0], 1, "failed")
+                        .settle(31, "01.map", "failed", 0, 1)
+                        .run_finished(32, "failed"))
+        self.exit_json = self.dir / "exit.json"
+        self.exit_json.write_text(json.dumps({
+            "status": "failed", "verdict": OLD_VERDICT, "error": None,
+            "traceback_tail": []}), encoding="utf-8")
+        self.resume()
+
+    def resume(self) -> None:
+        """The engine's resume: a second phase_started and a new attempt."""
+        (self.journal.phase(100, "01.map", "Map", STEPS)
+         .start(101, STEPS[0], attempt=2, kind="retry"))
+        past = time.time() - 100
+        os.utime(self.exit_json, (past, past))
+
+    def test_status_names_a_resumed_run_running(self):
+        mark_alive(self.dir)
+        code, lines = call("status", "--run", self.dir)
+        self.assertRegex(lines[0], r"^running: ", lines)
+
+    def test_snapshot_names_a_resumed_run_running(self):
+        mark_alive(self.dir)
+        snap = live.snapshot(self.dir)
+        self.assertEqual(snap["run"]["status"], "running")
+        self.assertIsNone(snap["run"].get("finished"),
+                          "a running run has no finish time")
+
+    def test_watch_keeps_a_resumed_run_going_and_prints_no_old_verdict(self):
+        mark_alive(self.dir)
+        code, lines = call("watch", "--run", self.dir, "--timeout", 0)
+        self.assertEqual(code, watch.EXIT_GOING, lines)
+        self.assertRegex(lines[0], r"^running: ")
+        self.assertNotIn(OLD_VERDICT, "\n".join(lines))
+
+    def test_watch_does_not_read_an_older_exit_json_as_the_verdict(self):
+        (self.dir / "supervisor.pid").write_text(DEAD_PID, encoding="utf-8")
+        code, lines = call("watch", "--run", self.dir, "--timeout", 0)
+        self.assertEqual(code, watch.EXIT_ENDED_BAD, lines)
+        self.assertRegex(lines[0], r"^orphaned: ")
+        self.assertNotIn(OLD_VERDICT, "\n".join(lines))
+
+    def test_a_resumed_run_that_finishes_again_is_finished(self):
+        mark_alive(self.dir)
+        (self.journal.finish(130, STEPS[0], 2, "passed")
+         .settle(131, "01.map", "passed", 1, 1)
+         .run_finished(132, "finished"))
+        code, lines = call("status", "--run", self.dir)
+        self.assertRegex(lines[0], r"^finished: ", lines)
diff --git a/oh-dispatch/tests/test_defect_51_rollcall_worker_budget.py b/oh-dispatch/tests/test_defect_51_rollcall_worker_budget.py
new file mode 100644
index 0000000..4aa9ba5
--- /dev/null
+++ b/oh-dispatch/tests/test_defect_51_rollcall_worker_budget.py
@@ -0,0 +1,68 @@
+"""Defect 51: a roll-call worker could end on its iteration budget.
+
+The roll call gave each worker `max_iterations` 15. The host worker, with the
+launching session's variables stripped, found no false identity in its
+environment and went looking for its own harness version and model: it listed
+the environment, ran `pip show`, listed its run directory and read its own
+completions. It reached the limit of 15 before its final message, and its cell
+failed on `schema_valid`. Earlier cells used 5 to 9 calls.
+
+The default is now 30 for every worker step of every shape, and every brief
+that asks for the harness line tells the worker where its facts come from:
+its own system prompt, tool list and working directory, and `unknown` for a
+value they do not show.
+"""
+
+from __future__ import annotations
+
+from ohflow.plans import rollcall
+from support import TempCase
+
+SHAPES = {
+    "single": "pi",
+    "fanout": "pi,host,claude,codex,dsh",
+    "relay": "pi,host,claude",
+    "merge": "pi,host,claude",
+    "retry": "pi",
+    "review": "pi",
+    "campaign": "pi",
+}
+SENTENCE = "Write `unknown` for a value they do not show"
+
+
+class RollcallWorkerBudget(TempCase):
+
+    def _workers(self, **args) -> list[tuple[str, object]]:
+        found = []
+        for shape, lanes in SHAPES.items():
+            plan = rollcall.build({"repo": str(self.tmp / "repo"),
+                                   "shape": shape, "lanes": lanes, **args})
+            for phase in plan.phases:
+                for step in phase.steps:
+                    if step.kind == "worker":
+                        found.append((f"{shape}/{step.id}", step.worker))
+        return found
+
+    def test_every_worker_step_of_every_shape_gets_at_least_30_iterations(self):
+        workers = self._workers()
+        self.assertGreaterEqual(len(workers), len(SHAPES))
+        for name, worker in workers:
+            self.assertGreaterEqual(worker.max_iterations, 30, name)
+
+    def test_the_judge_gets_the_default_too(self):
+        judge = rollcall.judge_spec({"repo": str(self.tmp / "repo")})
+        self.assertGreaterEqual(judge.max_iterations, 30)
+
+    def test_the_argument_still_overrides_the_default(self):
+        for name, worker in self._workers(max_iterations=7):
+            self.assertEqual(worker.max_iterations, 7, name)
+
+    def test_every_brief_that_asks_for_the_harness_line_says_where_facts_come_from(self):
+        asking = 0
+        for name, worker in self._workers():
+            if "- Harness:" not in worker.brief and '"harness"' not in worker.brief:
+                continue
+            asking += 1
+            self.assertIn(SENTENCE, worker.brief, name)
+            self.assertIn("Do not search", worker.brief, name)
+        self.assertGreater(asking, 0)
**toolResult** for `call_667e24891c774b60a8c5d836` (bash)

#### [17] line 17 · message · assistant · 2026-10-02T01:52:45.715Z
<details><summary>thinking</summary>

Now let me understand the changes well. Let me check some potential issues:

1. **The `worker_env` regex**: `_PARENT_SESSION_VARS = re.compile(r"^(CLAUDE|CLAUDECODE$|ANTHROPIC_BASE_URL$)")` - this matches anything starting with `CLAUDE`. Note `CLAUDECODE` starts with `CLAUDE` so it's already covered. But wait — does this over-strip? E.g., `CLAUDE_CODE_DISABLE_CLAUDE_MDS` — that's intentionally set afterwards by the claude runner (HERMETIC_ENV is applied to seat_env's result, which already ran worker_env, so the hermetic env var survives). Good.

   But wait — what about variables the *claude lane* sets on purpose? Let me check where the claude runner sets `CLAUDE_CODE_DISABLE_CLAUDE_MDS`: `seat_env(HERMETIC_ENV if hermetic else None)` — seat_env calls `proc.worker_env()` first then applies extra. Good.

   What about `pi_runner`: `env = proc.worker_env()` then sets `PI_CODING_AGENT_DIR` etc. Good. Does pi runner need any CLAUDE* vars? No.

   `HostLane`: `env = worker_env()` then PYTHONPATH etc. Does OpenHands need `ANTHROPIC_BASE_URL`? Hmm — the spec says the desktop session exports an ANTHROPIC_BASE_URL pointing at the desktop app's own proxy. Stripping it is the intent. But could the host lane legitimately use ANTHROPIC_BASE_URL for its own model config? The host lane is OpenHands with `glm-5.3-flash` via zai — probably uses `ZAI_*` or a custom env. Let me check how the host runner's model env is configured. Actually, if a user set ANTHROPIC_BASE_URL deliberately for their own proxy (not the desktop app), this would strip it. But that's the pre-existing rule from seat_runner; m7 just extends it. Fine.

2. **Where else is an environment built for a child?** The review instructions say: "a worker launch on any lane that still passes `CLAUDE*`, `CLAUDECODE` or `ANTHROPIC_BASE_URL` (grep every place an environment is built for a child)". Let me grep for `os.environ` copies and `env=` in the scripts.

3. **The codex lane** — seat_runner's `seat_env` is used by claude, codex, dsh lanes. Let me verify codex runner uses seat_env.

4. **The hermetic claude**: `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1`. Need to check: does this keep the login? The lanes.md says it keeps OAuth login. Can't verify live, but the criterion 4 runs `single:claude:1:profile=hermetic` live, which will verify.

   One concern: `CLAUDE_CODE_DISABLE_CLAUDE_MDS` disables CLAUDE.md loading — including *project* CLAUDE.md? The lanes.md table says hermetic claude "Keeps: ... the project's own `.claude` files". Hmm, that might contradict: `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` disables all CLAUDE.md files including project ones? Let me check the docs. Actually in Claude Code, `CLAUDE_CODE_DISABLE_CLAUDE_MDS`... I'm not sure this is a documented env var. There's `--setting-sources` which controls which setting files load. Actually I recall Claude Code env var `CLAUDE_CODE_DISABLE_TERMINAL_TITLE`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`... `CLAUDE_CODE_DISABLE_CLAUDE_MDS`? Hmm, maybe. There is a `--no-user-memory`? Not sure. The implementer says "Measured 2026-10-01 (2.1.281)". I can't easily verify without running claude. The live criterion 4 will test it though.

   The lanes.md claim "Keeps ... the project's own `.claude` files" — if `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` disables CLAUDE.md memory loading entirely, then project CLAUDE.md would also be dropped, contradicting lanes.md. Let me check the actual claude CLI docs on this box: `claude --help` and see if the env var is documented. Also check the claude.exe version installed. Since I'm running in some environment... Actually let me check what `claude --help` says. But careful: running claude CLI may be heavy. `claude --help` is fine.

5. **The journal reopen logic**: In `Journal._replay` (or wherever), `if state.finished and ev not in _NOT_WORK_EVENTS: state.status = "running"; state.finished = None`. Note the order of checks: this happens *before* checking `ev == "run_started"`. For `run_finished` event itself, since `ev in _NOT_WORK_EVENTS`, skip. Good.

   But subtle: after reopening (status="running", finished=None), what happens when a later `run_finished` arrives — sets status again. Fine.

   What about `state.finished` used elsewhere — `RunState.finished` is a timestamp presumably set by run_finished handler. OK.

   Edge: a run that is finished, and then a `journal_recovered` event... covered by _NOT_WORK_EVENTS.

   Edge: what about paused? `exit_info_from_files`: `if run.state.status in ("finished", "failed", "paused"): return exit_info(...)`. So a paused run still returns paused even if work events came after? Wait, the replay sets status to "running" for any work event after run_finished, so status wouldn't be "paused"... unless the last run-level status was paused. Hmm, can a run be paused without run_finished? Pause writes... let me look at the journal module more fully to understand.

6. **`rundir.exit_record`**: compares mtimes. `if (run_dir / "journal.jsonl").stat().st_mtime > written: return None`. So exit.json counts only when journal is not newer. Note: on a resumed run, the journal gets appended (mtime newer), so old exit.json is ignored. Good. But there's a subtlety: what if the resumed run's supervisor *dies* without writing a new exit.json? Then `status_without_journal` → supervisor dead, exit_record None → NOT_STARTED? Let me check: `status_without_journal` returns NOT_STARTED. Then... `Run.status` presumably prefers journal-derived status (running, since work events after run_finished) and only falls back to status_without_journal when no journal. Let me read rundir.py and journal.py fully to be sure.

   The test `test_watch_does_not_read_an_older_exit_json_as_the_verdict` expects "orphaned" for a resumed run with a dead supervisor. So journal replay says "running", then since supervisor dead... something marks it orphaned. Let me read the code.

7. **The `dsh` projectKey port**: Compare with the real dsh implementation at `%APPDATA%\npm\node_modules\@deepseek-ai\dsh\node_modules\@deepseek-ai\dsh-session-persistence-jsonl\lib\index.js` lines ~874-893. The review instructions explicitly say to check this. Let me read the JS.

   The Python port: separators `/ \ :` runs → one `-`; `~` excluded explicitly; code < 128 and alnum or `._-` → as-is; else `~XXXX`. Leading `-` stripped, empty → root, cut to 251.

   The JS probably: 
   ```js
   function projectKey(cwd) {
     let key = '';
     let lastSep = false;
     for (const ch of cwd) { // or code units?
       if ('/\\:'.includes(ch)) { if (!lastSep) key += '-'; lastSep = true; }
       else if (ch !== '~' && /[A-Za-z0-9._-]/.test(ch)) { key += ch; lastSep = false; }
       else { key += '~' + ch.charCodeAt(0).toString(16).toUpperCase().padStart(4,'0'); lastSep = false; }
     }
     key = key.replace(/^-+/, '') || 'root';
     return key.slice(0, 251);
   }
   ```
   I need to read the actual file. Let me do that.

8. **gates.py rollcall_matches**: when `lane` given and report's lane mismatches → problem. But note: `schema_valid` gate — does the schema require `lane`? The report schema ROLLCALL_SCHEMA — does it have a `lane` field with enum? If the schema doesn't require lane, then a report missing lane passes schema_valid but fails rollcall_matches (test covers that). Fine.

   Edge: gate description lambda: `(f"; the report names lane {a['lane']}" if a.get("lane") else "")`. Fine.

   One thing: `_report_checks(owns, lane, ...)` is now required for every caller. Are there other callers not updated — e.g., review shape or campaign shape steps that use `rollcall_matches` without lane? The test covers merge (pi-1, claude-1, consolidate). What about `retry`, `review`, `campaign` shapes? In those, do worker steps use `_report_checks`? `_solo` covers single/retry; review uses...? Let me read rollcall.py fully. If some steps use `rollcall_matches` without lane, that's OK per design (lane=None → unchecked), but spec item 4 says "The roll-call gate fails a report whose `lane` is not the step's lane" — for all roll-call steps. Let me check every step.

9. **README figures**: quick = 24 m 27 s (1466.5 s) "the sum of these ten cells' times in the first full matrix run"; full = 32 m 23 s (1942.7 s). I should verify against the measured matrix.json at the given path. The spec says fill from the measured matrix.json above. Let me check the file exists and sums match. 1466.5/60 = 24.44 min → 24 m 27 s (0.44*60=26.5≈27). 1942.7/60 = 32.38 → 32 m 23 s (0.379*60 = 22.7 ≈ 23). Need to compute actual sums from matrix.json.

   Also suite figure: "902 tests, 873 s on 2026-10-02", shards 328.9+285.4+258.4 = 872.7 ≈ 873. I'll verify by running shards — the shard run also verifies test count.

   But wait: the README says "875 tests" before → "902 tests" now. The diff stat shows new tests: defect 44 (6 tests), 45 (3), 46 (5), 47 (4), 48 (4), 49 (1), 50 (5), 51 (4) = 32 new. 875+32 = 907? Hmm, but some tests may have been removed or the count differs. Let me count precisely from the actual test run. Actually the previous README said 875; adding 32 gives 907, not 902. Unless previously it was 870? Let me count tests in the new files:
   - 44: test_parent_session_vars_do_not_reach_the_claude_runner_or_its_cli, _codex, _dsh, _pi, _host, test_parent_session_vars_are_the_only_names_the_rule_removes = 6
   - 45: 3
   - 46: 5
   - 47: 4
   - 48: 4
   - 49: 1
   - 50: 5
   - 51: 4
   Total = 32. Hmm. So either the trunk README figure of 875 was wrong, or the shard count will show. The charter says baseline 627; m5/m6 README said 875. Let me just run the shards and count. If the actual count is 902, fine — maybe some tests were removed or skipped. Actually, wait: run_tests.py may count differently (e.g., skipping e2e opt-in). The full suite gate runs and the README claims 902. I'll verify with my shard runs.

   Actually hold on, let me check whether the implementer's earlier commit caed658 said "902 tests" from a three-shard run "after the dsh bucket, stall-table and watcher-cursor fixes". Then commit 01b5719 says "README: suite figure from a three-shard run after ... (902 tests)". And f4a6063 and 470cf16 added defect 50 (5 tests) and defect 51 (4 tests) after that. So the README says 902 but 9 more tests were added after? Unless the 902 figure was updated after. Let me check the README commit history: 01b5719 is the README commit, and it comes after caed658 but before 470cf16 and f4a6063. Wait the log order (newest first):
   - f4a6063 (defect 51, 4 tests)
   - 470cf16 (defect 50, 5 tests)
   - 01b5719 (README: suite figure 902 tests)
   - caed658 (campaign ignores + dsh docstring)
   - 3bbb2ef (README: host has no stall row; quick figure)
   - 235a9fa (dsh bucket)
   - c9004e3 (README: quick/full wall times, suite figure from three-shard run)
   - bd76078 (test_defect_07 waits 60s)
   - 52dbe58 (stall per lane + gate lane)
   - 139fac7 (hermetic claude)
   - 18f4bcd (worker_env)

   So the README figure 902 was measured at commit 01b5719, i.e., before defect 50 and 51 tests (9 more tests) were added. So the current branch has 902 + 9 = 911 tests? The README would then be stale by 9 tests. Hmm, unless run_tests counts only... let me actually run the shards and count. That's a required exit check anyway (the gate runs the full suite; I need to run 3 shards).

   Wait — but the shard runs take ~5 min each. I need to run all three shards in the foreground. Plus criterion 4 (live rollcall with 3 cells, ~10+ min?). That's fine.

   Actually wait, criterion 4 requires live claude/codex/dsh/pi seats — that runs real workers. That's the big one. And the brief says run it exactly as the campaign driver does with `--out "$(mktemp -d)"`. OK.

10. **Exit criterion 5**: grep "not measured yet" README → no match. From the diff, both rows are filled. ✓ (verify).

11. **Criterion 1**: `run_tests.py -k parent_session` — ≥ 5 tests, one per lane. The test file has 5 lane tests + 1 more = 6, all matched by "parent_session"? The file name contains "parent_session_vars_reach_no_worker" → `-k parent_session` matches module path? Depends on run_tests.py's -k implementation. Let me check run_tests.py.

12. **Criterion 2**: `-k hermetic` → test_defect_45_hermetic... ≥ 2 tests. But also maybe other hermetic tests exist (codex hermetic?). Fine.

13. **Criterion 3**: `-k report_lane` → test_defect_46... ≥ 1 test.

14. **Criterion 4**: the big live one.

Also review instructions mention:
- "a hermetic claude session that can still read the user's instruction files or settings, or that loses its login" — need to check `--setting-sources project,local` is in the hermetic build_command already (pre-existing?) and that HERMETIC_ENV works. Live run will tell.
- "a stall limit that a lane's normal silence can still trip (codex reasoning, a long foreground command)" — codex 600 now. What about host? Host takes no stall limit (CAP_STALL not set). pi/claude/dsh 180. dsh: MCP fleet shutdown ~30s after answer, plus the session log mtime moves per event, so fine.
- "a report whose lane names another lane and still passes the gate" — covered; but check `schema_valid` gate: does ROLLCALL_SCHEMA constrain `lane`? Also check the "review" and "campaign" shapes' steps.
- "README figures that do not match the measured matrix.json or a shard run" — check.
- "a dsh session bucket that differs from dsh's own projectKey rule for any path" — read the JS and compare, including edge cases (e.g., the `~` exclusion, the charAt code units vs code points, the 251 cut, the lstrip of leading `-`).
- "a resumed run ... that ohflow status, watch or the dashboard snapshot still calls finished; build one in a temp dir and run both verbs on it" — the tests cover this, but I should verify the tests actually exercise it and maybe run my own.
- "a roll-call worker whose iteration budget a normal run can use up: in your criterion-4 run, read each step's llm_calls (or turn count) in result.json against max_iterations in its spec.json, and report the host cell's two numbers" — do this after criterion 4.
- "a test that passes both with and without its fix" — check defect tests are red-first. E.g., defect 44's `_launch_env` uses `lanes.lane_for(lane_name)` and CliLane. Would the test fail on old code? On old code pi/host passed os.environ → leak detected. Yes. But I could verify by stashing... Actually a cleaner way: `git stash` isn't applicable since committed. I can check out the base into a temp worktree and run the new test files against the old code? The new test files exist only on the branch. I can copy the test files to the old worktree... but the rule says create nothing inside the worktree; a temp dir outside is fine. Let me do a few key red-first proofs: defect 44 (pi lane env), 45, 46, 47, 48, 50. That's a lot; maybe do the cheap ones with targeted runs.

Actually, a simpler approach for red-first: create a worktree at arch/deepening in temp dir, copy the new test files in, run them, expect failures. The tests import `ohflow` — from the scripts dir. run_tests.py sets up paths. The copied tests reference `ohflow.proc.worker_env` which doesn't exist in old code → ImportError → test errors → "fails against the old code". That's a weak proof (import error counts as fail). For a stronger proof on e.g. defect 46 (gate), the old gate lacks `lane` param → TypeError. Also weak. The strongest meaningful red-first proofs: defect 44 (env leak on pi/host), defect 48 (bucket names), defect 50 (status of resumed run), defect 47 (stall per lane), defect 51 (max_iterations 15 vs 30). Import-time failures in 46/45 are less meaningful but the behavior assertions exist.

Hmm, but "prove a defect test fails against the old code before you keep it" — the implementer's job. As reviewer I should sanity check at least a couple. Given time constraints, I'll do a combined temp-worktree check with the test files copied, running each defect test file with unittest directly against old code. But note `support.py` and fakes must be importable — copy the whole tests dir? The old worktree has its own tests dir; I can copy just the new test files + check whether they depend on new fakes (fake_dsh.py changed!). fake_dsh is in the diff — the new test_defect_48 doesn't use fake_dsh though. test_defect_49 imports from test_campaign_01_loop (existing). OK.

Plan for red-first check: 
```
git worktree add <temp> arch/deepening  (wait — "Never change another branch" — creating a worktree doesn't change branches; but it does write to .git of the shared checkout? No — this worktree's repo is the worktree at _wt/...m7-smoke-fixes? Hmm.
```
Wait, is the worktree itself a full clone or a linked worktree? "Worktree: ... branch arch/m7-smoke-fixes, created from arch/deepening at 7426973". The product repository is C:\Users\<user>\.agents\skills. The rule: "never touch the shared checkout at C:\Users\<user>\.agents\skills (only your worktree)". Creating a `git worktree add` from my worktree would add metadata to the repo's .git... which is the shared repo's .git (worktrees share the main .git dir). That modifies the shared repo's metadata (adds a worktree entry). Risky but harmless? "Never change another branch" — a worktree add doesn't change branches. But it does write .git/worktrees/... in the main repo. Hmm. Safer: `git archive arch/deepening | tar -x -C tempdir` — a plain export, no repo metadata touched. Then copy new test files in and run with PYTHONPATH pointing at tempdir/scripts. run_tests.py might need repo context? Let me check how tests locate ohflow. They probably run from the skill root with `python oh-dispatch/tests/run_tests.py`. The tests import ohflow from scripts dir via run_tests adding sys.path. Let me check run_tests.py.

Actually simpler: the tests dir's support.py etc. — I'll export the whole tree at arch/deepening to a temp dir, then copy the *new/changed test files* from my branch into it, then run `python oh-dispatch/tests/run_tests.py -k <name>` from the temp root with old code. The new test files may import things that don't exist in old code (worker_env) — for defect 44 that's an import error, making the "red" trivially true but not proving the behavioral defect. Hmm. But for defect 44, the test's core assertion is behavioral (env leak); import error at `from ohflow import lanes, proc` — wait, `proc` exists in old code; `worker_env` is accessed inside the last test only, so import succeeds! `from ohflow import lanes, proc` — both exist in old code. The `_launch_env` tests would run and detect leaks on pi/host lanes. 

For defect 45: imports `ClaudeAdapter` only — fine; old code: hermetic prepare didn't set the env var → test fails red. 
For defect 46: `rollcall_matches(..., lane=...)` → TypeError (unexpected kwarg) → red (error). Also `rollcall.build` produces checks with lane arg — but calling gate directly raises first. OK red.
For defect 47: old plan: stall=180 for all → codex 180 < 600 → red. Also `rollcall.STALL_S` missing → AttributeError in test 3, but test 1 fails first.
For defect 48: old bucket slug → mismatched names → red.
For defect 50: old journal replay → status finished → red.
For defect 51: old max_iter 15 → red.
For defect 49: old campaign doesn't ignore .watch → escalation → red.

Good, these are genuinely red on old code. I can verify a few quickly by running against the exported base. That's cheap for 45-48 (unit tests, fast). Let me do it.

15. **`fake_dsh.py` change**: it now computes the bucket with dsh's rule via regex `_escape`. Check the regex: `re.sub(r"[/\\:]+|[^A-Za-z0-9._\-/\\:]", _escape, ...)`. The alternation: first matches runs of separators; else a single char outside the readable set (excluding separators already matched). In `_escape`, `if text[0] in "/\\:"` → "-". Else per UTF-16 unit escape. Then `.lstrip("-")` and cut 251, or root. This mirrors the runner. But wait: in the fake, non-BMP chars in Python regex: `re.sub` iterates code points; `_escape` encodes to utf-16-le giving two units → correct surrogate pair output. Good.

    One difference: the runner's readable-set check `code < 128 and (ch.isalnum() or ch in "._-")`. `ch.isalnum()` for ASCII: [0-9A-Za-z] → yes, and no other ASCII char is alnum. So equivalent to [A-Za-z0-9._-]. Good. But careful: `ch != "~"` and code < 128 — "~" is code 126, and `~` is not alnum and not in "._-", so the `ch != "~"` is redundant in the runner. In JS the regex `[A-Za-z0-9._-]` wouldn't match `~` anyway. Fine.

    Edge: what about uppercase hex with code > 0xFFFF? Can't happen for UTF-16 units.

    Now compare with the actual JS. Must read the file.

16. **`journal.py`**: need to see where `state.finished` is set/cleared and confirm no other path breaks (e.g., `RunState.finished` cleared on reopen — the dashboard uses it).

17. **`watch.py`**: `_exit_status` now uses `rundir.exit_record` — returns None if exit.json older than journal. In `_exit_report`: `written` variable — it used to read status from exit.json; now presumably calls _exit_status. Let me read the full watch.py context around those lines to ensure no leftover json import unused... `json` import may now be unused in watch.py? The diff removed three json.loads usages. If `json` is still imported but unused, that's a lint nit, not a defect. Let me check.

18. **exit_report.py**: `prior = run.exit_record()` — note `run.exit_record()` is a method on Run taking no args, but rundir.exit_record takes run_dir. In Run class: `def exit_record(self) -> dict | None: return exit_record(self.run_dir)`. OK.

19. **campaign.py**: adds `.watch.*.json` to ignores. Note: `ensure_ignores` only adds missing entries to .gitignore. Fine.

20. **gates.py**: the check `if lane is not None and report.get("lane") != lane`. What if report's lane is a non-string, e.g. missing → None != "codex" → problem "report names lane None". Good.

21. **rollcall.py REPORT prompt change**: added instructions. And `max_iter` default 30. Also `judge_spec`? test says judge gets ≥30. Where's judge_spec defined — presumably `_worker` with default. OK.

22. Check that nothing else calls `_report_checks` with old signature — compile check via tests.

23. **`seat_runner.py`**: removed `re` import? The diff removed the regex from seat_runner but does seat_runner still use `re` elsewhere? If `import re` remains unused → nit. Let me check. The diff didn't remove an `import re` line. Let me grep seat_runner for `re.` usage.

Let me now start running things. Plan:

A. Read supporting files: run_tests.py -k behavior; seat_runner imports; watch.py json usage; journal.py full replay; rundir.py status logic; lanes.py CAP_STALL; rollcall.py full (all shapes' checks); claude_runner build_command for hermetic flags.
B. Read dsh JS projectKey.
C. Check matrix.json figures.
D. Verify README criterion 5 grep.
E. Run exit criteria 1,2,3 (fast subsets).
F. Red-first spot checks against exported base.
G. Build a resumed run in temp dir and run status/watch myself (beyond the unit tests).
H. Run the three shards (foreground, ~5 min each) to verify suite figure and exit 0.
I. Run criterion 4 live rollcall with the env vars and --out mktemp.
J. Check iteration budgets in the criterion-4 result.json vs spec.json.

Let me start with A and B and C and D in parallel.

</details>
The diff is read. Now let me inspect the surrounding code: `run_tests.py`'s `-k`, the lanes' `CAP_STALL`, `seat_runner`'s leftover imports, `watch.py`'s `json` usage, and the journal replay.
**toolCall bash** id=`call_1f599e30c4da4370a9691fbd`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && sed -n 1,80p oh-dispatch/tests/run_tests.py && grep -n \"import re\" oh-dispatch/scripts/ohflow/seat_runner.py; grep -n \"re\\.\" oh-dispatch/scripts/ohflow/seat_runner.py; grep -n \"^import\\|^from\" oh-dispatch/scripts/ohflow/watch.py"
}
```
**toolCall bash** id=`call_a8c3e1cdfe2f42d1bbbd28ad`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && grep -n \"CAP_STALL\" oh-dispatch/scripts/ohflow/lanes.py | head; grep -n \"finished\" oh-dispatch/scripts/ohflow/journal.py | head -40"
}
```

#### [18] line 18 · message · toolResult · 2026-10-02T01:52:45.933Z
#!/usr/bin/env python
"""The one command that runs the oh-dispatch suite.

    python oh-dispatch/tests/run_tests.py            # deterministic tests only
    python oh-dispatch/tests/run_tests.py --e2e      # plus the real-model run
    python oh-dispatch/tests/run_tests.py -k failure # only matching test names
    python oh-dispatch/tests/run_tests.py --shard 1/3 # one third of the tests
    python oh-dispatch/tests/run_tests.py --durations 15 # name the slowest tests

Why a script and not pytest. This box's interpreter is Python 3.14 and has no
pytest, and neither does the OpenHands virtual environment the workers run in.
The brief asks that a fresh clone plus one command works. `unittest` is in the
standard library, so it always does. What this script adds on top of
`python -m unittest` is the part `unittest` gets wrong for this suite: it prints
every skip with its reason, unconditionally, instead of a silent `s`.

Every path is resolved from `__file__`. The script may be run from any working
directory and it reads nothing outside this repository.

Exit code 0 when everything that ran passed, 1 otherwise.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent          # oh-dispatch/tests
SKILL_ROOT = HERE.parent                        # oh-dispatch
IMPORT_ROOT = SKILL_ROOT / "scripts"            # holds the `ohflow` package

for p in (str(SKILL_ROOT), str(IMPORT_ROOT), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

from ohflow import proc
from summary_schema_audit import SummarySchemaAudit


class ReasonedResult(unittest.TextTestResult):
    """A result that remembers why things were skipped, and how long each test ran."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.skip_reasons: list[tuple[str, str]] = []
        self.timings: list[tuple[float, str]] = []
        self._started = 0.0

    def startTest(self, test):
        self._started = time.perf_counter()
        super().startTest(test)

    def stopTest(self, test):
        super().stopTest(test)
        self.timings.append((time.perf_counter() - self._started, test.id()))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.skip_reasons.append((str(test), reason))


class ReasonedRunner(unittest.TextTestRunner):
    resultclass = ReasonedResult


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="run_tests.py",
        description="the oh-dispatch regression suite")
    ap.add_argument(
        "--e2e", action="store_true",
        help="also run the end-to-end test against a real model. It needs "
             "ZAI_CODING_CN_API_KEY and the OpenHands virtual environment, "
             "and it costs several minutes of wall time.")
    ap.add_argument("-k", dest="pattern", default=None,
                    help="run only tests whose name contains this substring")
21:import re
5:on `cli_lane.CliAgentRuntime`; this module holds what the three share.
52:    found = re.findall(r'"%dp0%\\([^"]+\.(?:exe|js|cjs|mjs))"', text)
224:        if not isinstance(profile, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", profile):
9:from __future__ import annotations
11:import json
12:import re
13:import time
14:from dataclasses import dataclass, field
15:from pathlib import Path
17:from . import exit_report as ohexit
18:from . import live, proc, rundir, runstatus
19:from .paths import win
**toolResult** for `call_1f599e30c4da4370a9691fbd` (bash)

#### [19] line 19 · message · toolResult · 2026-10-02T01:52:45.937Z
30:CAP_STALL = "stall_timeout"
59:                   frozenset({CAP_STALL, CAP_CARRY, CAP_QUALIFIED_MCP})),
61:                       frozenset({CAP_STALL, CAP_CARRY, CAP_OAUTH, CAP_PROFILE,
64:                      frozenset({CAP_STALL, CAP_OAUTH, CAP_PROFILE,
67:                    frozenset({CAP_STALL, CAP_OAUTH, CAP_PROFILE,
21:#: The attempt number a `step_finished` carries when nothing was ever started
31:#: Events that say nothing about the run going again after a `run_finished`.
32:_NOT_WORK_EVENTS = frozenset({"run_started", "run_finished",
44:    "run_started", "phase_started", "step_started", "step_finished",
45:    "gate_ran", "phase_settled", "run_finished",
112:    finished: str | None = None
138:        """coord -> fingerprint, for every step that finished in a good state."""
148:            "finished": self.finished,
278:            if state.finished and ev not in _NOT_WORK_EVENTS:
280:                # `run_finished` is the run going again.
282:                state.finished = None
324:                    # a policy relabel all write `step_finished` alone, and
335:            elif ev == "step_finished":
437:            elif ev == "run_finished":
438:                state.finished = rec.get("ts")
439:                state.status = payload.get("status", "finished")
**toolResult** for `call_a8c3e1cdfe2f42d1bbbd28ad` (bash)

#### [20] line 20 · message · assistant · 2026-10-02T01:52:51.681Z
<details><summary>thinking</summary>

seat_runner still uses `re` — good, no unused import. watch.py still imports `json` and `re` — check usage: `re` used? Let me grep `re.` and `json.` in watch.py. Also let me read journal.py replay fully around line 270-300 and rundir.py Run.status.

</details>
**toolCall bash** id=`call_3f0c6668ab7d45ea9bb6a471`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && grep -n \"json\\.\\|re\\.\" oh-dispatch/scripts/ohflow/watch.py | head; sed -n 255,300p oh-dispatch/scripts/ohflow/journal.py"
}
```
**toolCall bash** id=`call_3920190f770047849c8178f4`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && sed -n 300,360p oh-dispatch/scripts/ohflow/rundir.py && grep -n \"def status\" oh-dispatch/scripts/ohflow/rundir.py"
}
```

#### [21] line 21 · message · toolResult · 2026-10-02T01:52:51.801Z
24:CURSOR_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
58:        data = json.loads(path.read_text(encoding="utf-8"))
66:        path.write_text(json.dumps(data), encoding="utf-8")
    @classmethod
    def replay(cls, run_dir: Path) -> RunState:
        """Rebuild the board from the journal file alone."""
        j = cls(run_dir)
        state = cls.replay_records(j.read())
        if j.recovery:
            state.meta["journal_recovery"] = dict(j.recovery)
        return state

    @staticmethod
    def replay_records(records) -> RunState:
        """Rebuild the board from records already parsed.

        `replay` reads the file and calls this. The run dashboard calls it
        directly, because it reads the journal from its last byte offset and
        already holds every record; reading the whole file again on each poll
        would cost a full parse per refresh for no new information.
        """
        state = RunState()
        for rec in records:
            ev = rec.get("event")
            payload = rec.get("payload") or {}
            coord = rec.get("coord")
            if state.finished and ev not in _NOT_WORK_EVENTS:
                # A resume appends no run-level event. Work after a
                # `run_finished` is the run going again.
                state.status = "running"
                state.finished = None
            if ev == "run_started":
                state.run_id = payload.get("run_id", state.run_id)
                state.plan_name = payload.get("plan", state.plan_name)
                state.started = rec.get("ts")
                state.meta.update(payload.get("meta") or {})
                state.status = "running"
            elif ev == "phase_started":
                state.phases[coord or payload.get("phase", "")] = {
                    "name": payload.get("name"),
                    "status": "running",
                    "started": rec.get("ts"),
                    "policy": payload.get("policy"),
                    "min_success": payload.get("min_success"),
                    # The limit the engine actually applied, not the one the
                    # plan asked for. A journal from before this key replays
                    # with None, which the board renders as a dash.
                    "max_parallel": payload.get("max_parallel"),
                }
**toolResult** for `call_3f0c6668ab7d45ea9bb6a471` (bash)

#### [22] line 22 · message · toolResult · 2026-10-02T01:52:51.808Z
            return {"name": plan.get("name") or state.plan_name,
                    "max_parallel": plan.get("max_parallel"),
                    "auto_resume": plan.get("auto_resume"),
                    "repo": plan.get("repo"),
                    "base_branch": plan.get("base_branch"),
                    "phases": phases, "from_plan": True}

        known: dict[str, dict] = {}
        for rec in self._journal_records():
            if rec.get("event") != "phase_started" or not rec.get("coord"):
                continue
            pc = rec["coord"]
            payload = rec.get("payload") or {}
            if pc not in known:
                known[pc] = {"coord": pc, "index": len(known) + 1,
                             "name": payload.get("name") or pc, "raw": {},
                             "steps": [{"coord": c, "id": _step_id_of(c), "raw": {}}
                                       for c in payload.get("steps") or []]}
        for c, rec in state.steps.items():
            pc = c.split("/", 1)[0]
            entry = known.setdefault(pc, {"coord": pc, "index": len(known) + 1,
                                          "name": pc, "raw": {}, "steps": []})
            if all(s["coord"] != c for s in entry["steps"]):
                entry["steps"].append({"coord": c,
                                   "id": rec.step_id or _step_id_of(c),
                                   "raw": {"kind": rec.kind,
                                           "id": rec.step_id}})
        return {"name": state.plan_name, "max_parallel": None,
                "auto_resume": None, "repo": None, "base_branch": None,
                "phases": list(known.values()), "from_plan": False}

    def _journal_records(self) -> list[dict]:
        if self._records is None:
            self._records = list(Journal(self.run_dir).read())
        return self._records

    def steps(self, *, kind_default: str = "worker") -> list[StepView]:
        """Every step in plan order, each with its attempts."""
        out = []
        for ph in self.plan["phases"]:
            for st in ph["steps"]:
                c = st["coord"]
                rec = self.state.steps.get(c)
                raw = st["raw"]
                kind = raw.get("kind") or (rec.kind if rec else None) \
                    or kind_default
                step_id = st["id"]
                out.append(StepView(
                    coord=c, phase=ph["coord"], step_id=step_id, kind=kind,
                    status=step_status(self.state, c),
                    attempt=rec.attempt if rec and rec.attempt else 0,
                    raw=raw, attempts=self.attempts(c, kind)))
        return out

    # ---- attempts

    def step_dir(self, coord: str) -> Path:
        return step_dir(self.run_dir, coord)

    def attempt_dir(self, coord: str, attempt: int) -> Path:
        return attempt_dir(self.run_dir, coord, attempt)
251:    def status_without_journal(self) -> str:
265:    def status(self) -> str:
**toolResult** for `call_3920190f770047849c8178f4` (bash)

#### [23] line 23 · message · assistant · 2026-10-02T01:52:56.132Z
**toolCall bash** id=`call_4a2835eda8534c8397a8e51a`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && sed -n 246,300p oh-dispatch/scripts/ohflow/rundir.py"
}
```
**toolCall bash** id=`call_ce246342809c4aefb9ca01e7`

```json
{
 "command": "cat \"$APPDATA/npm/node_modules/@deepseek-ai/dsh/node_modules/@deepseek-ai/dsh-session-persistence-jsonl/lib/index.js\" | sed -n 860,900p"
}
```

#### [24] line 24 · message · toolResult · 2026-10-02T01:52:56.344Z
        A resume appends to the journal after the earlier stop wrote its exit
        record. That record then describes a stop the run has since left."""
        return exit_record(self.run_dir)

    @property
    def status_without_journal(self) -> str:
        """The name of a run that has no journal line, from its files.

        `starting` while a supervisor or owner lives. The status that
        `exit.json` records when it records a stopped one (a preflight crash
        writes `crashed`). `not started` otherwise.
        """
        if self.supervisor_alive:
            return STARTING
        recorded = self.exit_record()
        status = recorded.get("status") if recorded else None
        return status if status in STOPPED_STATUSES else NOT_STARTED

    @property
    def status(self) -> str:
        """The journal's status, with `orphaned` for a dead supervisor."""
        if self.state.status == "running" and not self.supervisor_alive:
            return ORPHANED
        return self.state.status

    # ---- plan order

    @property
    def plan(self) -> dict:
        """Plan order, phase names and step definitions.

        `plan.json` is the source. Before the engine writes it, the journal's
        `phase_started` payloads still name every step of a phase that began.
        """
        if self._plan is None:
            self._plan = self._plan_model()
        return self._plan

    def _plan_model(self) -> dict:
        state = self.state
        plan = _read_json(self.run_dir / "plan.json")
        phases: list[dict] = []
        if isinstance(plan, dict) and isinstance(plan.get("phases"), list):
            for pi, ph in enumerate(plan["phases"], start=1):
                ph = ph if isinstance(ph, dict) else {}
                name = str(ph.get("name") or f"phase {pi}")
                pc = f"{pi:02d}.{ph.get('slug_override') or _slug(name)}"
                steps = []
                for si, st in enumerate(ph.get("steps") or [], start=1):
                    st = st if isinstance(st, dict) else {}
                    steps.append({"coord": f"{pc}/{si:02d}.{st.get('id')}",
                                  "id": str(st.get("id")), "raw": st})
                phases.append({"coord": pc, "index": pi, "name": name,
                               "raw": ph, "steps": steps})
            return {"name": plan.get("name") or state.plan_name,
**toolResult** for `call_4a2835eda8534c8397a8e51a` (bash)

#### [25] line 25 · message · toolResult · 2026-10-02T01:52:56.349Z
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
**toolResult** for `call_ce246342809c4aefb9ca01e7` (bash)

#### [26] line 26 · message · assistant · 2026-10-02T01:53:11.524Z
<details><summary>thinking</summary>

The dsh JS `projectKey` matches the Python port exactly:
- iterate UTF-16 code units (`charCodeAt` in JS; Python decodes utf-16-le units) ✓
- separators `/ \ :` runs → one `-` ✓
- `~` excluded explicitly (redundant but same) ✓
- readable `[A-Za-z0-9._-]` ✓
- else `~XXXX` uppercase hex ✓
- `replace(/^-+/, "")` strips *leading hyphens* — Python `.lstrip("-")` ✓
- `|| "root"` ✓
- `.slice(0, 251)` ✓
- wrapped in `--`...`--` ✓ (JS builds `--${key}--` after slicing key; Python slices key then wraps `f"--{key}--"` — same)
- empty path throws in JS; Python raises ValueError ✓

Wait, one subtlety: JS `readable.replace(/^-+/, "")` removes leading `-` *from the encoded string*. Python `lstrip("-")` — same. But note in JS, this happens before `|| "root"` and slice — same order in Python: `("".join(readable).lstrip("-") or "root")[:251]`. ✓

One more subtlety: in the JS, the `~` case: `ch !== "~"` — for `~` (code 126), the else branch: `"~" + code.toString(16)` = `~007E`. Python: same. ✓

Edge: the JS `code.toString(16).toUpperCase().padStart(4, "0")` — for surrogates D800-DFFF: Python `f"~{code:04X}"` — same 4-hex uppercase. ✓

Test expectations: "a backslash before two hyphens", r"C:\a\--b" → JS: C, : → sep -, a, \ → sep run? After `a`, `\` is a separator: separatorRun was false → append "-", set true. Then `-`: it's readable (`-` is in the readable set!), so append "-", separatorRun=false. Then `-` again → append. Then `b`. So readable = "C-a---b". Python: same logic. Expected "--C-a---b--" ✓ matches test.

Wait, but in Python port, `-` is in `"._-"` so readable, and sets separator_run=False. Same as JS. ✓

Now `mktemp -d` case: `C:\Users\<user>\AppData\Local\Temp\tmp.YBNLOpDXik\03-relay` → "C-Users-user-AppData-Local-Temp-tmp.YBNLOpDXik-03-relay" ✓.

The port looks faithful.

Now, `rundir.Run.status`: journal status "running" + dead supervisor → ORPHANED. And `exit_info_from_files` uses `run.state.status` — note: `run.state.status` is the journal's raw status (not Run.status with orphaned). For a resumed run with dead supervisor: state.status = "running" (reopened) → not in terminal → prior = run.exit_record() → old exit.json older than journal → None → `run.status` (with orphaned) → ORPHANED → returns exit_info(ORPHANED)? Let me check the rest of exit_info_from_files to see ORPHANED handling. Let me read exit_report.py fully.

Also check `watch.py` around `_exit_report` for the `written` variable — is it `_exit_status`? Let me read watch.py 85-115.

</details>
The dsh `projectKey` port matches the JavaScript line for line (UTF-16 code units, separator runs, `~XXXX` escape, leading-dash strip, `root`, 251 cut, `--` wrapping). Now `exit_report.py` and `watch.py` in full context:
**toolCall bash** id=`call_5b6219bcf79b4595be7e300c`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && sed -n 60,120p oh-dispatch/scripts/ohflow/exit_report.py && sed -n 85,125p oh-dispatch/scripts/ohflow/watch.py"
}
```
**toolCall bash** id=`call_e77ac86db4384d61a081e7e3`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && grep -rn \"os.environ\" oh-dispatch/scripts/ohflow/*.py oh-dispatch/scripts/ohflow/plans/*.py | grep -v \"get(\" | grep -v worker_env"
}
```

#### [27] line 27 · message · toolResult · 2026-10-02T01:53:11.736Z
        text = f"{type(error).__name__}: {error}".rstrip(": ")
    else:
        text = error
    tail = (traceback_text or "").rstrip().splitlines()[-20:]
    return {"status": status, "error": text or None, "traceback_tail": tail}


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def exit_info_from_files(run_dir: Path) -> dict:
    """The exit status the files support, for `ohflow report`.

    `run_finished` names it when the journal has one. Without it, a crash or
    an interrupt that `cmd_run` already reported keeps its own status and its
    error, a live supervisor means the run is still going, and anything else
    is a run whose supervisor died without writing a word: `orphaned`.
    """
    run_dir = Path(run_dir)
    run = rundir.open_run(run_dir)
    if run.state.status in ("finished", "failed", "paused"):
        return exit_info(run.state.status)
    prior = run.exit_record()
    if prior and prior.get("status") in ("crashed", "interrupted"):
        return {"status": prior["status"], "error": prior.get("error"),
                "traceback_tail": list(prior.get("traceback_tail") or [])}
    if run.status == rundir.ORPHANED:
        return exit_info("orphaned",
                         "the supervisor stopped without finishing the run and "
                         "wrote no exit report: a hard kill or a machine restart")
    return exit_info("running",
                     "the supervisor is still running; this report is a "
                     "snapshot and the run replaces it when it stops")


# ------------------------------------------------------------ the numbers


def human_duration(seconds: float | None) -> str:
    if seconds is None:
        return "unknown time"
    s = int(round(seconds))
    if s < 60:
        return f"{s} s"
    m = int(round(s / 60))
    if m < 60:
        return f"{m} min"
    return f"{m // 60} h {m % 60} min"


def _human_tokens(n: int) -> str:
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        return f"{n / 1000:.1f} k"
    return f"{n / 1_000_000:.1f} M"

def _exit_error(run_dir: Path) -> str | None:
    """The first line of the `error` that `exit.json` records, or None."""
    error = (rundir.exit_record(run_dir) or {}).get("error")
    lines = str(error or "").strip().splitlines()
    return lines[0] if lines else None


def _exit_report(run_dir: Path, snap: dict) -> tuple[Path | None, str | None]:
    """The exit report's path and verdict. An orphaned run gets one written."""
    written = _exit_status(run_dir)
    if written is None or written == "running":
        deadline = _clock() + EXIT_REPORT_WAIT_S
        while snap["run"].get("supervisor_alive") and _clock() < deadline:
            _sleep(0.5)
            written = _exit_status(run_dir)
            if written not in (None, "running"):
                break
            snap = live.snapshot(run_dir)
        if written is None or written == "running":
            _info, paths, verdict = ohexit.rebuild(run_dir)
            return paths["html"], verdict
    verdict = (rundir.exit_record(run_dir) or {}).get("verdict")
    return run_dir / "exit-report.html", verdict


def _idle_seconds(run_dir: Path) -> float:
    """Seconds since the newest file in the run directory changed. A watcher's
    own cursor files do not count: each call would reset the clock."""
    newest = 0.0
    for entry in Path(run_dir).iterdir():
        if entry.is_file() and not entry.name.startswith(".watch."):
            try:
                newest = max(newest, entry.stat().st_mtime)
            except OSError:
                pass
    return time.time() - newest if newest else 0.0


def _never_launched(run_dir: Path, status: str) -> bool:
    """A `not started` run with no handoff file.
**toolResult** for `call_5b6219bcf79b4595be7e300c` (bash)

#### [28] line 28 · message · toolResult · 2026-10-02T01:53:11.742Z
oh-dispatch/scripts/ohflow/campaign.py:297:    env = dict(os.environ, GIT_PAGER="cat", PAGER="cat")
oh-dispatch/scripts/ohflow/cli.py:342:        env = dict(os.environ)
oh-dispatch/scripts/ohflow/cli.py:787:        env = dict(os.environ)
oh-dispatch/scripts/ohflow/exec.py:81:    child_env = dict(os.environ)
oh-dispatch/scripts/ohflow/host_runner.py:33:os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")
oh-dispatch/scripts/ohflow/host_runner.py:36:# `build_terminal_env` starts from `os.environ`. git starts a pager when it
oh-dispatch/scripts/ohflow/host_runner.py:42:os.environ.update(NO_PAGER_ENV)
oh-dispatch/scripts/ohflow/proc.py:30:    source = os.environ if base is None else base
oh-dispatch/scripts/ohflow/worker.py:72:    variable name, and only `host_runner.py` reads os.environ."""
**toolResult** for `call_e77ac86db4384d61a081e7e3` (bash)

#### [29] line 29 · message · assistant · 2026-10-02T01:53:21.353Z
<details><summary>thinking</summary>

Interesting — several places still build a child environment from raw `os.environ`:

1. `campaign.py:297`: `env = dict(os.environ, GIT_PAGER="cat", PAGER="cat")` — what child is this? Probably a git subprocess for campaign bookkeeping, not a *worker* launch. The spec says "One rule removes the launching session's variables from every worker, on every lane." So only worker launches. Git doesn't care about CLAUDE*.

2. `cli.py:342` and `cli.py:787`: `env = dict(os.environ)` — need to check what these launch. If one of them launches the detached supervisor (which in turn launches workers), the supervisor would carry CLAUDE* into its own os.environ... but workers launched by the supervisor go through worker_env() anyway, which strips them. So that's fine for workers. But wait — does anything in the supervisor itself read CLAUDE*? The dashboard? Not a defect per spec.

3. `exec.py:81`: `child_env = dict(os.environ)` — what's this? A command cap runner? If a worker's *terminal command* runs with CLAUDE* inherited... but that env is built inside the worker process (which already has no CLAUDE*). Actually exec.py might be the command-cap enforcement for workers. If the worker process itself has a clean env, `dict(os.environ)` inside it is clean. Fine.

4. `host_runner.py`: this runs *inside* the host worker process (the OpenHands runtime). `build_terminal_env` starts from os.environ of the host worker — which is now clean because HostLane.launch uses worker_env(). Good.

5. `worker.py:72`: comment says "only `host_runner.py` reads os.environ" — hmm, that's a docstring/comment about WorkerSpec env maybe. Fine.

Let me check cli.py:342 and 787 and campaign.py:297 to be sure they're not worker launches.

</details>
Several places still build a child env from raw `os.environ`. Let me check whether any of them is a worker launch:
**toolCall bash** id=`call_bc3af9e3f1dd4c3b9950380f`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && sed -n 330,355p oh-dispatch/scripts/ohflow/cli.py && echo ---- && sed -n 775,800p oh-dispatch/scripts/ohflow/cli.py && echo ---- && sed -n 288,305p oh-dispatch/scripts/ohflow/campaign.py && echo ---- && sed -n 70,95p oh-dispatch/scripts/ohflow/exec.py"
}
```

#### [30] line 30 · message · toolResult · 2026-10-02T01:53:21.464Z
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
    return states


# ------------------------------------------------------------------ git


def _git(cwd: Path, *args: str, check: bool = True) -> str:
    flags = ({"creationflags": subprocess.CREATE_NO_WINDOW}
             if os.name == "nt" else {})
    env = dict(os.environ, GIT_PAGER="cat", PAGER="cat")
    p = proc.run(["git", *args], cwd=str(cwd), capture_output=True,
                 text=True, encoding="utf-8", errors="replace", env=env,
                 **flags)
    if check and p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} in {win(cwd)} exited "
                           f"{p.returncode}: {p.stderr.strip()[:400]}")
    return p.stdout.strip()

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
**toolResult** for `call_bc3af9e3f1dd4c3b9950380f` (bash)

#### [31] line 31 · message · assistant · 2026-10-02T01:53:39.485Z
<details><summary>thinking</summary>

These are all supervisor/git/command-cap launches, not worker launches:

- `cli.py:342`: detached run supervisor (`ohflow run --detach`). The supervisor is ohflow itself, not a worker. It later launches workers via the lanes, which all call `worker_env()` from their own `os.environ`. But wait — the supervisor inherits `CLAUDE*` and passes its own `os.environ` to... the lanes strip them at launch time. So workers are clean. ✓
- `cli.py:787`: detached campaign supervisor — same reasoning.
- `campaign.py:297`: `_git` — git doesn't read CLAUDE*.
- `exec.py:81`: command cap for commands run *inside* a worker process (the worker's env is already clean) or inside the supervisor. Hmm — actually wait. Where does exec.py run? It's the command-cap runner used by workers. The worker process env is clean, so `dict(os.environ)` there is clean. But is exec.py ever used by the *engine* (supervisor) to run gate commands? If the supervisor runs gate commands with CLAUDE* in env — gates are python checks, not agents. Not a worker identity problem. The spec's rule is about *workers*. Fine.

Now, key check: do all five lanes actually pass through the stripped env? 
- claude/codex/dsh: via `seat_env()` in seat_runner → `proc.worker_env()` ✓
- pi: `pi_runner.prepare` → `env = proc.worker_env()` ✓
- host: `worker.py HostLane.launch` → `env = worker_env()` ✓
- CliLane (generic runner that launches the per-lane CLI adapter process): `cli_lane.py` → `env = worker_env()` ✓

Wait — CliLane launches a *runner process* (python -m ohflow.claude_runner or similar) with worker_env, and then that runner process calls `seat_env()`/`prepare()` which does `worker_env()` again on its own (already clean) os.environ. Double-stripping is harmless. ✓

But hold on — the codex lane: does CodexAdapter use seat_env? Let me check codex_runner prepare. And does the codex runner set `CODEX_HOME` (a hermetic mechanism)? `CODEX_HOME` doesn't start with CLAUDE so it survives. ✓

What about `ANTHROPIC_AUTH_TOKEN` or `ANTHROPIC_API_KEY`? The pattern only strips `ANTHROPIC_BASE_URL`. Spec says exactly that pattern (from the pre-existing rule). The desktop app exports ANTHROPIC_BASE_URL pointing at its proxy; ANTHROPIC_API_KEY might not be exported by desktop. The spec's item 1 says "The rule and the variable pattern live in one place" — the pattern is the pre-existing one. OK.

Hmm, wait — one important subtlety: the claude lane worker needs its OAuth login. Claude Code stores login in `~/.claude` (keychain etc.). Does stripping `CLAUDE_CODE_ENTRYPOINT=claude-desktop` and friends break anything? No — removing them makes the CLI behave as a normal CLI session. Actually the m7 failure was that the host worker *inherited* these and OpenHands read them... fine.

Another subtlety: `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` is set *after* worker_env (via seat_env extra) — confirmed in seat_env: `env = proc.worker_env(); env["PYTHONIOENCODING"]=...; env.update(extra)`. ✓ So the hermetic var survives.

Now — does the *pi* lane also need hermetic-ish stripping of its own? Not in scope.

Next, check `rollcall.py` fully — every shape's report checks carry lane; also `_solo` for retry/review/campaign shapes. And where's `judge_spec`? Also check the ROLLCALL_SCHEMA — does it have "lane" as required field with the right enum? If schema requires `lane` then defect-46 test "missing fails" is covered by schema too.

</details>
All remaining raw-`os.environ` child launches are supervisors, git calls, or in-process command caps — no worker launch bypasses the rule. Now the rollcall plan in full — every shape's checks, the schema, and `judge_spec`:
**toolCall bash** id=`call_90fd6dd08605497ba4a28c99`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && grep -n \"_report_checks\\|rollcall_matches\\|judge_spec\\|max_iterations\\|ROLLCALL_SCHEMA\" oh-dispatch/scripts/ohflow/plans/rollcall.py"
}
```
**toolCall bash** id=`call_0a2a7837bfdd4c4b84999bae`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && sed -n 100,180p oh-dispatch/scripts/ohflow/plans/rollcall.py"
}
```

#### [32] line 32 · message · toolResult · 2026-10-02T01:53:39.602Z
4:The lane records what the harness announced, and `rollcall_matches` fails a
31:`max_iterations` (default 30: a worker that looks up its own facts needs more
52:ROLLCALL_SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
399:        max_iter=int(args.get("max_iterations", 30)),
408:def judge_spec(args) -> WorkerSpec:
422:                      lane=lane, tools=tools, max_iterations=spec.max_iter,
429:          schema: dict | None = ROLLCALL_SCHEMA, role: str | None = None) -> Step:
439:def _report_checks(owns: str, lane: str, *, since: str = "base",
443:             CheckSpec("rollcall_matches", {"lane": lane})) + extra)
459:                 checks=_report_checks(owns, lane, since=since, extra=extra),
504:            checks=_report_checks("ROLLCALL.md", lane, since="step_start",
531:        checks=_report_checks("ROLLCALL.md", spec.consolidator,
**toolResult** for `call_90fd6dd08605497ba4a28c99` (bash)

#### [33] line 33 · message · toolResult · 2026-10-02T01:53:39.607Z
directory. Write `unknown` for a value they do not show. Do not search the disk,
the environment or the run directory for it.

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
**toolResult** for `call_0a2a7837bfdd4c4b84999bae` (bash)

#### [34] line 34 · message · assistant · 2026-10-02T01:53:46.853Z
<details><summary>thinking</summary>

The REPORT template puts `{"lane": "{lane}", ...}` in the JSON block — so the brief tells the worker its lane and the report's lane is templated per step. But note: for the consolidate step, what lane goes in the template? Let me look at `_worker` and the review/campaign shapes, plus judge_spec. Also check whether every `rollcall_matches` check has lane — from grep, all four `_report_checks` call sites pass lane. But are there steps in `review`/`campaign` shapes that use `rollcall_matches` without going through `_report_checks`? The grep shows only those four sites + line 4 docstring. So every `rollcall_matches` occurrence goes through `_report_checks(owns, lane, ...)`. 

Wait — what about the judge in the review/campaign shape? `judge_spec` at 408. Judges don't have rollcall_matches checks presumably. OK.

Let me read lines 405-560 to see _worker, judge_spec, review and campaign shapes.

</details>
**toolCall bash** id=`call_b807cb002fe64a46a70d6bfb`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && sed -n 405,425p oh-dispatch/scripts/ohflow/plans/rollcall.py && sed -n 533,640p oh-dispatch/scripts/ohflow/plans/rollcall.py"
}
```

#### [35] line 35 · message · toolResult · 2026-10-02T01:53:47.020Z
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
**toolResult** for `call_b807cb002fe64a46a70d6bfb` (bash)

#### [36] line 36 · message · assistant · 2026-10-02T01:53:50.088Z
<details><summary>thinking</summary>

All shapes funnel through `_solo`/`_relay`/`_merge`, which all pass lane. Good.

Now check ROLLCALL_SCHEMA — does it require "lane"? Let me look at the schema file. Also check `HERMETIC_LANES`.

</details>
**toolCall bash** id=`call_be2897a3eff1434c89e479f2`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && grep -rn \"SCHEMA_PATH\\s*=\" oh-dispatch/scripts/ohflow/plans/rollcall.py && find oh-dispatch -name \"*.json\" -path \"*rollcall*\""
}
```

#### [37] line 37 · message · toolResult · 2026-10-02T01:53:50.163Z
50:SCHEMA_PATH = (Path(__file__).resolve().parents[3] / "references" / "examples" /
oh-dispatch/references/examples/rollcall/rollcall.schema.json
**toolResult** for `call_be2897a3eff1434c89e479f2` (bash)

#### [38] line 38 · message · assistant · 2026-10-02T01:53:53.673Z
**toolCall bash** id=`call_72192abf7539417d92f1ff56`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && cat oh-dispatch/references/examples/rollcall/rollcall.schema.json"
}
```

#### [39] line 39 · message · toolResult · 2026-10-02T01:53:53.723Z
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
**toolResult** for `call_72192abf7539417d92f1ff56` (bash)

#### [40] line 40 · message · assistant · 2026-10-02T01:53:58.139Z
<details><summary>thinking</summary>

Schema requires `lane` as a string (no enum). Good — schema_valid catches missing lane; rollcall_matches catches wrong lane.

Now check the claude runner's `build_command` for the hermetic flags (`--setting-sources project,local`):

</details>
**toolCall bash** id=`call_21b7a9d7c1b84387bf246089`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && grep -n \"setting-sources\\|strict-mcp\\|hermetic\\|HERMETIC\" oh-dispatch/scripts/ohflow/claude_runner.py | head -20 && sed -n '/def build_command/,/return/p' oh-dispatch/scripts/ohflow/claude_runner.py | head -60"
}
```

#### [41] line 41 · message · toolResult · 2026-10-02T01:53:58.286Z
4:usual setup unless the step names `profile="hermetic"`. A hermetic worker loads
29:# Shared surface names to Claude built-ins, for a hermetic worker.
30:HERMETIC_TOOLS = {
35:HERMETIC_DEFAULT = ("terminal", "file_editor")
37:# `--setting-sources project,local` drops the user's settings but not the
41:HERMETIC_ENV = {"CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1"}
86:    if spec.get("profile") == "hermetic":
87:        only = list((spec.get("tools") or {}).get("only") or HERMETIC_DEFAULT)
88:        tools = [t for name in only for t in HERMETIC_TOOLS.get(name, ())]
92:        command.extend(["--tools", ",".join(tools), "--strict-mcp-config",
93:                        "--mcp-config", str(mcp_path), "--setting-sources", "project,local"])
332:        hermetic = spec.get("profile") == "hermetic"
336:            env=seat_env(HERMETIC_ENV if hermetic else None),
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
**toolResult** for `call_21b7a9d7c1b84387bf246089` (bash)

#### [42] line 42 · message · assistant · 2026-10-02T01:54:04.052Z
<details><summary>thinking</summary>

The claude hermetic flags are in place. Now let me verify `CLAUDE_CODE_DISABLE_CLAUDE_MDS` is a real Claude Code mechanism. Let me check the installed claude CLI docs. `claude --help` might mention it, or the docs. Let me check the version and search the CLI's JS bundle for the env var name. The claude.exe is a native wrapper; the JS is somewhere in AppData. Let me find it.

Actually — a quicker check: grep the claude installation for "DISABLE_CLAUDE_MDS".

</details>
The claude hermetic mechanism needs verification against the installed CLI. Let me confirm `CLAUDE_CODE_DISABLE_CLAUDE_MDS` is real and what it does:
**toolCall bash** id=`call_d4be02ab62ce44aca84dabbe`

```json
{
 "command": "where claude 2>/dev/null; claude --version 2>/dev/null | head -2"
}
```
**toolCall bash** id=`call_0c28fa46e5ff4f61a8efeb89`

```json
{
 "command": "ls \"$APPDATA/npm/node_modules/@anthropic-ai/claude-code/\" 2>/dev/null | head; grep -rl \"DISABLE_CLAUDE_MDS\" \"$APPDATA/npm/node_modules/@anthropic-ai/claude-code/\" 2>/dev/null | head -3"
}
```

#### [43] line 43 · message · toolResult · 2026-10-02T01:54:05.242Z
C:\Users\<user>\AppData\Roaming\npm\claude
C:\Users\<user>\AppData\Roaming\npm\claude.cmd
2.1.281 (Claude Code)
**toolResult** for `call_d4be02ab62ce44aca84dabbe` (bash)

#### [44] line 44 · message · toolResult · 2026-10-02T01:54:05.242Z
LICENSE.md
README.md
bin
cli-wrapper.cjs
install.cjs
node_modules
package.json
sdk-tools.d.ts
C:\Users\<user>\AppData\Roaming/npm/node_modules/@anthropic-ai/claude-code/bin/claude.exe
C:\Users\<user>\AppData\Roaming/npm/node_modules/@anthropic-ai/claude-code/node_modules/@anthropic-ai/claude-code-win32-x64/claude.exe
**toolResult** for `call_0c28fa46e5ff4f61a8efeb89` (bash)

#### [45] line 45 · message · assistant · 2026-10-02T01:54:09.281Z
<details><summary>thinking</summary>

The env var `DISABLE_CLAUDE_MDS` appears in the claude.exe binaries. Let me extract the surrounding context to confirm semantics (does it disable all CLAUDE.md including project?). The exe is a compiled bun binary; strings search may still work. Let me try to grep the binary for context around the var name. Actually a more reliable check: run `claude --help` and search settings docs. But `--setting-sources` governs settings; CLAUDE.md loading is governed by memory. Let me grep binary with a context window using `grep -aob` and then `dd`.

</details>
The variable exists in the installed CLI binary. Let me pull surrounding context from the binary to confirm its semantics:
**toolCall bash** id=`call_528abbfa707c4e75ab312e0e`

```json
{
 "command": "cd \"$APPDATA/npm/node_modules/@anthropic-ai/claude-code\" && grep -aob \"CLAUDE_CODE_DISABLE_CLAUDE_MDS\" node_modules/@anthropic-ai/claude-code-win32-x64/claude.exe | head -5"
}
```

#### [46] line 46 · message · toolResult · 2026-10-02T01:54:09.555Z
97768316:CLAUDE_CODE_DISABLE_CLAUDE_MDS
197786458:CLAUDE_CODE_DISABLE_CLAUDE_MDS
202789876:CLAUDE_CODE_DISABLE_CLAUDE_MDS
205608694:CLAUDE_CODE_DISABLE_CLAUDE_MDS
205608929:CLAUDE_CODE_DISABLE_CLAUDE_MDS
**toolResult** for `call_528abbfa707c4e75ab312e0e` (bash)

#### [47] line 47 · message · assistant · 2026-10-02T01:54:14.037Z
**toolCall bash** id=`call_8007e3e642254dbe96539937`

```json
{
 "command": "cd \"$APPDATA/npm/node_modules/@anthropic-ai/claude-code\" && for off in 97768316 202789876 205608694; do echo \"=== offset $off ===\"; dd if=node_modules/@anthropic-ai/claude-code-win32-x64/claude.exe bs=1 skip=$((off-700)) count=1400 2>/dev/null | tr -c '[:print:]\\n' ' ' | grep -o '.\\{0,120\\}CLAUDE_CODE_DISABLE_CLAUDE_MDS.\\{0,220\\}' | head -2; done"
}
```

#### [48] line 48 · message · toolResult · 2026-10-02T01:54:14.325Z
=== offset 97768316 ===
ared-interactive      V userLayer           cache           CLAUDE_CODE_SIMPLE       MM CLAUDE_CODE_SAFE_MODE       x   CLAUDE_CODE_DISABLE_CLAUDE_MDS          length       3  explicitlyRequested       c realPath     >  CLAUDE_CODE_AGENT           autocompact $    1G CLAUDE_CODE_INCLUDE_PARTIAL_MESSAGES!       CLAUDE_CODE_FORWARD_SUBAGENT_TEXT        P  hasSdkUrl     
=== offset 202789876 ===
on zr(e,s){if(Cr()&&!l[e])return!0;if(uo()&&!s?.explicitlyRequested)return t[e];return!1}function cO(){return Boolean(a.CLAUDE_CODE_DISABLE_CLAUDE_MDS||zr("claudeMd",{explicitlyRequested:iu().length>0}))}
=== offset 205608694 ===
ject"||e.type==="Local")&&x("tengu_paper_halyard",!1))return!1;return Boolean(e.content)}async function iet(e,n,r){if(a.CLAUDE_CODE_DISABLE_CLAUDE_MDS)return[];let s=[],g=fat();if(s.push(...await Y9(e,g,"Managed",n,!1,r)),pr("userSettings")){let h=bLe();s.push(...await Y9(e,h,"User",n,!0,r))}return s}async function gCn(e,n,r,{skipProject:s=!1}={}){if(a.CLAUDE_CODE_DIS
**toolResult** for `call_8007e3e642254dbe96539937` (bash)

#### [49] line 49 · message · assistant · 2026-10-02T01:54:19.871Z
<details><summary>thinking</summary>

From offset 205608694: `iet` builds the CLAUDE.md memory list: `if(a.CLAUDE_CODE_DISABLE_CLAUDE_MDS) return []` — then it loads "Managed" and "User" CLAUDE.md sources (`userSettings` gate). So `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` returns an empty list for those sources. The next function `gCn` also checks it with `skipProject`. Let me get more context on gCn to see whether *project* CLAUDE.md is also disabled by the env var, since lanes.md claims hermetic claude "Keeps ... the project's own `.claude` files".

</details>
**toolCall bash** id=`call_672b3ce9393a4287b460e82d`

```json
{
 "command": "cd \"$APPDATA/npm/node_modules/@anthropic-ai/claude-code\" && dd if=node_modules/@anthropic-ai/claude-code-win32-x64/claude.exe bs=1 skip=$((205608694-100)) count=1600 2>/dev/null | tr -c '[:print:]\\n' ' ' | grep -o 'gCn.\\{0,900\\}' | head -1"
}
```

#### [50] line 50 · message · toolResult · 2026-10-02T01:54:20.305Z
gCn(e,n,r,{skipProject:s=!1}={}){if(a.CLAUDE_CODE_DISABLE_CLAUDE_MDS)return[];let g=[],h=yw("projectSettings")&&!s;if(h){let _=Gu(e,"CLAUDE.md");g.push(...await u5(_,"Project",r,!1));let w=Gu(e,".claude","CLAUDE.md");g.push(...await u5(w,"Project",r,!1))}if(yw("localSettings")){let _=Gu(e,"CLAUDE.local.md");g.push(...await u5(_,"Local",r,!1))}if(h){let _=Gu(e,".claude","rules"),w=new Set(r);g.push(...await MPe({rulesDir:_,type:"Project",processedPaths:w,includeExternal:!1,conditionalRule:!1})),g.push(...await Y9(n,_,"Project",r,!1));for(let D of w)r.add(D)}return g}async function aet(e,n,r){if(a.CLAUDE_CODE_DISABLE_CLAUDE_MDS||!yw("projectSettings"))return[];let s=Gu(e,".claude","rules");return Y9(n,s,"Project",r,!1)}async function Y9(e,n,r,s,g,h){let _=await MPe({rulesDir:n,type:r,processedPaths:s,includeExternal:g,conditionalRule:!0,storageV5:h}),w=r==="Project"?AO(AO(n)):he(),D=xO(e)?dye
**toolResult** for `call_672b3ce9393a4287b460e82d` (bash)

#### [51] line 51 · message · assistant · 2026-10-02T01:54:41.240Z
<details><summary>thinking</summary>

This is important. `gCn` is the project-level CLAUDE.md loader: `if(a.CLAUDE_CODE_DISABLE_CLAUDE_MDS) return []` — it returns an empty list *before* loading Project CLAUDE.md, `.claude/CLAUDE.md`, `CLAUDE.local.md`, and `.claude/rules`. So `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` disables **all** instruction files: user, project, and local.

But `lanes.md` says hermetic claude **Keeps**: "the OAuth login, the plan's `--mcp-config` servers, the project's own `.claude` files".

Is "the project's own `.claude` files" about *settings* rather than instruction files? The `--setting-sources project,local` flag keeps project and local *settings* (`.claude/settings.json`, `.claude/settings.local.json`) while dropping user settings. But project `.claude/CLAUDE.md` and `.claude/rules` are instruction files, and they ARE dropped by the env var.

Hmm — the lanes.md table: "Removes: the user's instruction files (`CLAUDE_CODE_DISABLE_CLAUDE_MDS=1`), the user's settings (`--setting-sources project,local`), ..." and "Keeps: the OAuth login, the plan's `--mcp-config` servers, the project's own `.claude` files".

Reading strictly: it says the env var removes "the user's instruction files" — but per the binary, it removes *all* CLAUDE.md sources including the project's CLAUDE.md, `.claude/CLAUDE.md`, `CLAUDE.local.md`, and `.claude/rules`. And "Keeps ... the project's own `.claude` files" — the project's `.claude` *settings* are kept (via --setting-sources project,local), but the project's `.claude` *instruction* files (CLAUDE.md, rules) are NOT kept.

So the lanes.md sentence is at best ambiguous, at worst wrong: "the project's own `.claude` files" in the Keeps column contradicts "removes ... instruction files" only if you read "instruction files" as user-only. Given the binary evidence, the accurate statement: hermetic claude removes every CLAUDE.md/rule source (user, project, local), keeps project+local settings and login and mcp-config servers.

Is this prose contradiction a blocker? The charter bar #6: "no statement the code contradicts". The statement "Keeps: the project's own `.claude` files" — hmm, what does `.claude` files mean? If it means `.claude/settings.json` (settings), it's true via --setting-sources project,local. If a reader understands "the project's own .claude files" as including `.claude/CLAUDE.md`, it's false.

The Removes column says "the user's instruction files (CLAUDE_CODE_DISABLE_CLAUDE_MDS=1)" — attributing to the env var only the removal of user instruction files, when it removes project instruction files too. That's a genuine prose-code mismatch in the doc changed by this milestone. Severity: moderate — the doc misleads a developer about what hermetic means for a repo that has its own CLAUDE.md (the roll-call repo might have one; the workers' worktrees are fresh checkouts of a scratch repo, so live tests won't catch it).

Actually wait — let me double-check the "Keeps" claim about the OAuth login, too. Login is in `~/.claude/.credentials.json` or keychain — not affected by --setting-sources or the env var. The live criterion 4 run will prove it (single:claude:1:profile=hermetic must pass, which requires the login).

Let me verify my reading of `zr`/`cO` (the "setting-sources" gate functions). From offset 202789876: `function cO(){return Boolean(a.CLAUDE_CODE_DISABLE_CLAUDE_MDS||zr("claudeMd",{explicitlyRequested:iu().length>0}))}`. And `iet` handles "Managed"/"User" memory; `gCn` handles project/local memory. Both check the env var. So with the env var set, no CLAUDE.md at all loads — user, managed, enterprise, project, or local. Yes.

So the finding: `references/lanes.md` hermetic table row for claude says the env var removes "the user's instruction files" and that "the project's own `.claude` files" are kept — but `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` also removes the project's `CLAUDE.md`, `.claude/CLAUDE.md`, `CLAUDE.local.md` and `.claude/rules`. Only the project's *settings* (`--setting-sources project,local`) survive. Prose contradicts code.

Is this BLOCKED-worthy? The charter: "Prose is code... no statement the code contradicts." It's a wrong statement in a doc the milestone itself was required to write ("say in references/lanes.md, for each lane, what hermetic removes and what it keeps"). A wrong hermetic description is exactly within the milestone's scope item 2. I'd rank it a real defect but not a shipped-code defect — it's prose. The instructions: "BLOCKED when any exit criterion fails or any finding would ship a defect." Prose is code in this campaign, so a false statement in lanes.md ships a defect in the prose.

Hmm, but let me be careful about the strength of evidence. `gCn`'s first branch returns [] when the env var is set, before loading Project CLAUDE.md. Also `aet` (`.claude/rules` helper) checks it. And `iet` (Managed/User) checks it. This is unambiguous: the env var disables ALL claudeMd loading regardless of source. The `--setting-sources` controls `yw("projectSettings")` gates etc. So:

- Keeps (true): OAuth login; `--mcp-config` servers; project and local *settings* files (`.claude/settings.json`, `.claude/settings.local.json`).
- Removes (beyond what lanes.md says): the project's own `CLAUDE.md`, `.claude/CLAUDE.md`, `.claude/rules`, `CLAUDE.local.md`.

The "Keeps: the project's own `.claude` files" row is therefore wrong unless narrowly read as settings only. Also the claude_runner.py comment at line 37-40 says "`--setting-sources project,local` drops the user's settings but not the user's instruction files (CLAUDE.md). This variable drops them and keeps the `--mcp-config` servers and the login." — that comment says "This variable drops them" where "them" = "the user's instruction files". It doesn't claim project files are kept. The comment is fine-ish (it just doesn't mention project instruction files also being dropped). The lanes.md Keeps column is the misleading one.

Let me also check `CLAUDE_CODE_SAFE_MODE` / `--safe-mode` claim: "drops the mcp-config servers" — plausible, not needed.

Now, next checks:

1. matrix.json figures — verify the sums.
2. Criterion 5 grep.
3. Exit criteria 1-3 test subsets.
4. Red-first spot checks.
5. Resumed-run manual build.
6. Three shards.
7. Criterion 4 live run.

Let me look at the matrix.json.

</details>
`CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` short-circuits **all** CLAUDE.md loading — the `gCn` function returns `[]` before the Project `CLAUDE.md`, `.claude/CLAUDE.md`, `CLAUDE.local.md` and `.claude/rules` branches are even reached. I'll weigh that against the lanes.md table shortly. First, the README figures against the measured matrix:
**toolCall bash** id=`call_4164479875d144019441d15f`

```json
{
 "command": "python -c \"\nimport json\np = r'C:\\Users\\<user>\\AppData\\Local\\Temp\\claude\\C--Users-user\\bb0fac07-fb14-4ec9-82d9-33b3b7c2e4f4\\scratchpad\\matrix-full\\matrix.json'\nd = json.load(open(p))\nprint(type(d))\ncells = d['cells'] if isinstance(d, dict) and 'cells' in d else d\nprint(len(cells))\nfor c in cells:\n    print(c.get('cell') or c.get('name'), c.get('status'), c.get('duration_s') or c.get('wall_s') or c.get('seconds'))\n\""
}
```
**toolCall bash** id=`call_ecdd22e754ca4d33824bebb9`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && grep -n \"not measured yet\" oh-dispatch/README.md; echo \"grep exit: $?\""
}
```

#### [52] line 52 · message · toolResult · 2026-10-02T01:54:41.377Z
<class 'dict'>
15
None None 27.1
None None 138.1
None None 92.7
None None 58.4
None None 160.6
None None 196.9
None None 334.4
None None 347.2
None None 51.6
None None 59.5
None None 41.8
None None 215.1
None None 37.4
None None 42.3
None None 139.6
**toolResult** for `call_4164479875d144019441d15f` (bash)

#### [53] line 53 · message · toolResult · 2026-10-02T01:54:41.377Z
grep exit: 1
**toolResult** for `call_ecdd22e754ca4d33824bebb9` (bash)

#### [54] line 54 · message · assistant · 2026-10-02T01:54:45.748Z
**toolCall bash** id=`call_d6bd6b8b4a114dc78839234f`

```json
{
 "command": "python -c \"\nimport json\np = r'C:\\Users\\<user>\\AppData\\Local\\Temp\\claude\\C--Users-user\\bb0fac07-fb14-4ec9-82d9-33b3b7c2e4f4\\scratchpad\\matrix-full\\matrix.json'\nd = json.load(open(p))\ncells = d['cells'] if 'cells' in d else d\nimport pprint\npprint.pprint(cells[0])\nprint('keys of dict:', list(d.keys()) if isinstance(d, dict) else None)\n\""
}
```

#### [55] line 55 · message · toolResult · 2026-10-02T01:54:45.955Z
{'count': 1,
 'index': 1,
 'label': 'single pi count=1',
 'lanes': ['pi'],
 'options': {},
 'reason': '',
 'resume': 'ok',
 'run_dir': 'C:\\Users\\<user>\\AppData\\Local\\Temp\\claude\\C--Users-user\\bb0fac07-fb14-4ec9-82d9-33b3b7c2e4f4\\scratchpad\\matrix-full\\01-single-pi-1\\run',
 'seconds': 27.1,
 'shape': 'single',
 'tokens': 5761,
 'verdict': 'PASS'}
keys of dict: ['matrix', 'configuration', 'repo', 'out', 'cells_total', 'cells']
**toolResult** for `call_d6bd6b8b4a114dc78839234f` (bash)

#### [56] line 56 · message · assistant · 2026-10-02T01:54:52.083Z
<details><summary>thinking</summary>

Now I can compute the sums. The `full` matrix = 15 cells. The `quick` matrix = 10 cells: "single on all five lanes; fanout, relay and merge on pi, claude, codex, dsh; retry on pi; review on pi then claude". Let me list all 15 cells with labels and verdicts, compute full total and quick-cell subset total, and check against README (quick: 1466.5 s, full: 1942.7 s, failures 2/10 and 3/15).

</details>
**toolCall bash** id=`call_94cf8358f655449a9ae9ad88`

```json
{
 "command": "python -c \"\nimport json\np = r'C:\\Users\\<user>\\AppData\\Local\\Temp\\claude\\C--Users-user\\bb0fac07-fb14-4ec9-82d9-33b3b7c2e4f4\\scratchpad\\matrix-full\\matrix.json'\nd = json.load(open(p))\ncells = d['cells']\ntotal = 0\nquick_labels = set()\nfor c in cells:\n    total += c['seconds']\n    l = c['label']\n    print(f\\\"{c['index']:2d} {l:38s} {c['verdict']:5s} {c['seconds']:7.1f}\\\")\nprint('FULL total seconds:', total)\nprint('configuration:', json.dumps(d['configuration'])[:200])\n\""
}
```

#### [57] line 57 · message · toolResult · 2026-10-02T01:54:52.203Z
 1 single pi count=1                      PASS     27.1
 2 single host count=1                    FAIL    138.1
 3 single claude count=1                  PASS     92.7
 4 single codex count=1                   PASS     58.4
 5 single dsh count=1                     PASS    160.6
 6 fanout pi,claude,codex,dsh count=1     PASS    196.9
 7 relay pi,claude,codex,dsh count=1      FAIL    334.4
 8 merge pi,claude,codex,dsh count=1      PASS    347.2
 9 retry pi count=1                       PASS     51.6
10 review pi,claude count=1               PASS     59.5
11 fanout pi count=3                      PASS     41.8
12 campaign pi count=1                    PASS    215.1
13 single claude count=1 profile=hermetic FAIL     37.4
14 single codex count=1 profile=hermetic  PASS     42.3
15 retry claude count=1 carry_context     PASS    139.6
FULL total seconds: 1942.6999999999996
configuration: "default"
**toolResult** for `call_94cf8358f655449a9ae9ad88` (bash)

#### [58] line 58 · message · assistant · 2026-10-02T01:55:04.737Z
<details><summary>thinking</summary>

Full total = 1942.7 s ✓ matches README "32 m 23 s (1942.7 s)". 3 of 15 failed ✓ (cells 2, 7, 13).

Quick matrix (10 cells): single×5 (1-5), fanout (6), relay (7), merge (8), retry pi (9), review pi,claude (10). Sum: 27.1+138.1+92.7+58.4+160.6+196.9+334.4+347.2+51.6+59.5 = let me compute: 27.1+138.1=165.2; +92.7=257.9; +58.4=316.3; +160.6=476.9; +196.9=673.8; +334.4=1008.2; +347.2=1355.4; +51.6=1407.0; +59.5=1466.5. ✓ matches README "24 m 27 s (1466.5 s)". 2 of 10 failed (cells 2 and 7) ✓.

Wait, but README says "review on pi then claude" is in quick — yes cell 10 is review pi,claude. And quick excludes fanout pi count=3 (11), campaign (12), hermetic singles (13,14), retry claude carry_context (15). ✓ 10 cells.

README quick note: "the sum of these ten cells' times in the first full matrix run on 2026-10-01, not a run of quick; 2 of the 10 failed before the m7 fixes" ✓ honest.

Criterion 5: grep no match ✓.

Suite figure "902 tests" — the README commit 01b5719 predates defect 50 (5 tests) and defect 51 (4 tests). So current count should be 911 unless something else changed. Hmm wait — let me re-check the commit order. `git log --oneline` lists newest first:

f4a6063 (51), 470cf16 (50), 01b5719 (README 902), caed658, 3bbb2ef, 235a9fa, c9004e3 (README first figures), bd76078, 52dbe58, 139fac7, 18f4bcd.

So yes, README says 902 tests measured at 01b5719, before 50 and 51 test files (5+4=9 tests) were added. Unless... the shard count at 01b5719 was 902, and now it's 911. That would make the README stale by 9 tests — a prose/figure mismatch with a shard run, which my own shard runs will reveal. Let me count tests quickly with a discovery command (without running): run_tests.py might have a --list? Let me count via unittest discovery. Actually easier: run the three shards (required anyway) and read the counts. But shard runs are ~5 min each. Let me first count tests cheaply:

python -c with unittest discovery in the tests dir. run_tests.py builds a suite; let me check how it discovers (loadTestsFromModule over files?) and whether -k filters. Let me read the rest of run_tests.py.

</details>
README wall-time figures check out exactly (full 1942.7 s, quick subset 1466.5 s, failure counts 3/15 and 2/10). Criterion 5 passes (no match). Now let me check how `run_tests.py` counts and lists tests, to verify the "902 tests" suite figure:
**toolCall bash** id=`call_0d3dc0b8195548d9a9dbc996`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && sed -n 80,190p oh-dispatch/tests/run_tests.py"
}
```

#### [59] line 59 · message · toolResult · 2026-10-02T01:55:04.794Z
                    help="run only tests whose name contains this substring")
    ap.add_argument("--shard", metavar="K/N", default=None,
                    help="run shard K of N (1-based). The tests sorted by "
                         "name go to the shards in turn, so the N shards "
                         "together run every test once.")
    ap.add_argument("--durations", metavar="N", type=int, default=0,
                    help="after the run, print the N slowest tests")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="name every test as it runs")
    ap.add_argument("-q", "--quiet", action="store_true",
                    help="dots only")
    return ap


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def parse_shard(text: str) -> tuple[int, int]:
    try:
        k, n = (int(part) for part in text.split("/"))
    except ValueError:
        k = n = 0
    if not 1 <= k <= n:
        raise SystemExit(f"--shard takes K/N with 1 <= K <= N, got {text!r}")
    return k, n


def main(argv: list[str] | None = None) -> int:
    ns = build_parser().parse_args(argv)
    shard = parse_shard(ns.shard) if ns.shard else None
    # A run without a console (run-hidden.vbs) has no stdin handle, and every
    # test that starts a child through plain `subprocess` would fail on it.
    proc.ensure_stdin()

    # The end-to-end test reads this variable and skips when it is unset. The
    # flag is the only way it is ever set by this script, so the deterministic
    # suite can never start a provider call by accident.
    if ns.e2e:
        os.environ["OHFLOW_E2E"] = "1"

    verbosity = 2 if ns.verbose else (0 if ns.quiet else 1)

    loader = unittest.TestLoader()
    if ns.pattern:
        loader.testNamePatterns = [f"*{ns.pattern}*"]
    suite = loader.discover(start_dir=str(HERE), pattern="test_*.py",
                            top_level_dir=str(SKILL_ROOT))
    if shard:
        k, n = shard
        ordered = sorted(flatten(suite), key=lambda t: t.id())
        suite = unittest.TestSuite(ordered[k - 1::n])

    print(f"oh-dispatch suite   python {sys.version.split()[0]}")
    print(f"  tests:  {HERE}")
    print(f"  ohflow: {IMPORT_ROOT / 'ohflow'}")
    print(f"  e2e:    {'requested with --e2e' if ns.e2e else 'off (pass --e2e to include it)'}")
    if shard:
        print(f"  shard:  {shard[0]} of {shard[1]}")
    print("")

    t0 = time.time()
    runner = ReasonedRunner(verbosity=verbosity, stream=sys.stdout)
    with SummarySchemaAudit() as summary_audit:
        result = runner.run(suite)
    elapsed = time.time() - t0

    # A suite that silently skips its only real test is worse than one that
    # never had it. Every skip is named here with the reason it carried.
    if result.skip_reasons:
        print("")
        print(f"SKIPPED ({len(result.skip_reasons)}) - each with its reason:")
        for name, reason in result.skip_reasons:
            print(f"  - {name}")
            print(f"      {reason}")
    if ns.durations:
        print("")
        print(f"SLOWEST {ns.durations}:")
        for seconds, name in sorted(result.timings, reverse=True)[:ns.durations]:
            print(f"  {seconds:7.1f}s  {name}")
    print("")
    print(f"summary schema checks: {summary_audit.checked}   "
          f"unexpected rejections: {summary_audit.rejected}")
    audit_ok = (summary_audit.rejected == 0
                and (summary_audit.checked > 0 or ns.pattern is not None))
    if not audit_ok:
        reason = ("the unfiltered suite produced no summary audit receipts"
                  if summary_audit.checked == 0
                  else "one or more summaries failed schema validation")
        print(f"SUMMARY SCHEMA AUDIT FAILED: {reason}")
    elif summary_audit.checked == 0:
        print("summary schema audit: this filtered selection produced no "
              "Engine summary")
    print(f"ran {result.testsRun} tests in {elapsed:.1f}s   "
          f"failures={len(result.failures)} errors={len(result.errors)} "
          f"skipped={len(result.skipped)}")
    return 0 if result.wasSuccessful() and audit_ok else 1


if __name__ == "__main__":
    sys.exit(main())
**toolResult** for `call_0d3dc0b8195548d9a9dbc996` (bash)

#### [60] line 60 · message · assistant · 2026-10-02T01:55:16.864Z
<details><summary>thinking</summary>

`-k` uses `testNamePatterns` which matches against the full test id (module path + class + method). So `-k parent_session` matches `test_defect_44_parent_session_vars_reach_no_worker` module name — yes since id contains module path.

Now, count all tests quickly without running them. Discovery + count via flatten — cheap (imports all modules, which some tests might do heavy work at import? Probably fine).

</details>
**toolCall bash** id=`call_617b7ee7efdb48bda07c58ad`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && python -c \"\nimport sys, unittest\nfrom pathlib import Path\nHERE = Path('oh-dispatch/tests'); SKILL = HERE.parent; ROOT = SKILL/'scripts'\nfor p in (str(SKILL), str(ROOT), str(HERE)): sys.path.insert(0, p)\nloader = unittest.TestLoader()\nsuite = loader.discover(start_dir=str(HERE), pattern='test_*.py', top_level_dir=str(SKILL))\ndef flat(s):\n    for i in s:\n        if isinstance(i, unittest.TestSuite): yield from flat(i)\n        else: yield i\ntests = list(flat(suite))\nprint('total discovered:', len(tests))\nimport collections\nper = collections.Counter(t.id().split('.')[0] + '/' + t.id().split('.')[1] for t in tests)\nfor k in sorted(per):\n    if 'defect_4' in k or 'defect_5' in k: print(k, per[k])\n\""
}
```

#### [61] line 61 · message · toolResult · 2026-10-02T01:55:17.589Z
total discovered: 911
tests/test_defect_40_detach_env_stays_off_disk 2
tests/test_defect_41_tree_kill_run_quiet 2
tests/test_defect_42_tests_ignore_the_workers_environment 2
tests/test_defect_43_spawn_resumes_without_a_thread_snapshot 2
tests/test_defect_44_parent_session_vars_reach_no_worker 6
tests/test_defect_45_hermetic_claude_loads_no_instruction_files 3
tests/test_defect_46_rollcall_report_lane_must_match_the_step 5
tests/test_defect_47_rollcall_stall_limit_is_per_lane 4
tests/test_defect_48_dsh_session_bucket_follows_dsh 4
tests/test_defect_49_campaign_watch_is_not_a_stray_edit 1
tests/test_defect_50_a_resumed_run_is_not_finished 5
tests/test_defect_51_rollcall_worker_budget 4
**toolResult** for `call_617b7ee7efdb48bda07c58ad` (bash)

#### [62] line 62 · message · assistant · 2026-10-02T01:55:26.822Z
<details><summary>thinking</summary>

911 tests discovered, but the README says 902. The README figure was measured at commit 01b5719, before the defect-50 (5) and defect-51 (4) test files were committed (9 more tests). So the README's "902 tests" is stale — 911 is the count on this branch. Unless the discovery count differs from what runs (skips still count as run). Skips count in testsRun. So the suite runs 911.

This is a real finding: exit-criterion-adjacent (spec scope item 5: "update the suite figure from a shard run on this branch. One place each."). The figure says 902 but the branch has 911 tests. The wall-time figure (873 s) was also measured before the last two commits. My shard runs will give the true numbers.

Severity: prose figure mismatch — the spec explicitly asked for the README suite figure from a shard run on this branch, and the last commits invalidated it. It's a doc defect, fixable in one line. Under "prose is code", this is a defect that ships.

Hmm — wait. Let me double check whether some tests are skipped at discovery (e.g., Windows-only skipUnless still discovered and counted in testsRun? Yes, skipped tests still count as run). So 911.

Let me now run the exit criteria 1-3 subsets (fast), then the red-first checks, then the resumed-run scenario, then shards, then the live criterion 4.

</details>
911 tests discovered on this branch, but the README says 902 — the figure was measured at commit `01b5719`, before defect-50 (5 tests) and defect-51 (4 tests) landed. That's a stale figure; my shard runs will confirm. Now exit criteria 1–3:
**toolCall bash** id=`call_16a5a5d1deec47e5bc08475d`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && python oh-dispatch/tests/run_tests.py -k parent_session -q 2>&1 | tail -8"
}
```
**toolCall bash** id=`call_86bf0bfc16824ddca81939c7`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && python oh-dispatch/tests/run_tests.py -k hermetic -q 2>&1 | tail -6"
}
```

#### [63] line 63 · message · toolResult · 2026-10-02T01:55:28.772Z
----------------------------------------------------------------------
Ran 6 tests in 0.036s

OK

summary schema checks: 0   unexpected rejections: 0
summary schema audit: this filtered selection produced no Engine summary
ran 6 tests in 0.0s   failures=0 errors=0 skipped=0
**toolResult** for `call_16a5a5d1deec47e5bc08475d` (bash)

#### [64] line 64 · message · toolResult · 2026-10-02T01:55:28.772Z

OK

summary schema checks: 0   unexpected rejections: 0
summary schema audit: this filtered selection produced no Engine summary
ran 10 tests in 1.0s   failures=0 errors=0 skipped=0
**toolResult** for `call_86bf0bfc16824ddca81939c7` (bash)

#### [65] line 65 · message · assistant · 2026-10-02T01:55:33.048Z
**toolCall bash** id=`call_da853d60b4944392bf0afb0e`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && python oh-dispatch/tests/run_tests.py -k report_lane -q 2>&1 | tail -5"
}
```
**toolCall bash** id=`call_d148f61c1048454db30d142b`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && python oh-dispatch/tests/run_tests.py -k stall_limit -q 2>&1 | tail -4; python oh-dispatch/tests/run_tests.py -k session_bucket -q 2>&1 | tail -4"
}
```

#### [66] line 66 · message · toolResult · 2026-10-02T01:55:34.554Z
OK

summary schema checks: 0   unexpected rejections: 0
summary schema audit: this filtered selection produced no Engine summary
ran 5 tests in 0.0s   failures=0 errors=0 skipped=0
**toolResult** for `call_da853d60b4944392bf0afb0e` (bash)

#### [67] line 67 · message · toolResult · 2026-10-02T01:55:34.554Z

summary schema checks: 0   unexpected rejections: 0
summary schema audit: this filtered selection produced no Engine summary
ran 4 tests in 0.0s   failures=0 errors=0 skipped=0

summary schema checks: 0   unexpected rejections: 0
summary schema audit: this filtered selection produced no Engine summary
ran 4 tests in 0.0s   failures=0 errors=0 skipped=0
**toolResult** for `call_d148f61c1048454db30d142b` (bash)

#### [68] line 68 · message · assistant · 2026-10-02T01:55:41.484Z
<details><summary>thinking</summary>

Exit criteria 1, 2, 3 pass:
1. `-k parent_session`: 6 tests ≥ 5, one per lane ✓, exit 0 ✓
2. `-k hermetic`: 10 tests ≥ 2 ✓
3. `-k report_lane`: 5 tests ≥ 1 ✓

Now the red-first proofs. Export base (arch/deepening) to a temp dir, copy the new test files in, run them against the old code. Files to copy: defect_44, 45, 46, 47, 48, 49, 50, 51. Note defect_49 imports test_campaign_01_loop (exists in base). defect_50 imports dashboard_support, verb_support (exist in base? presumably). Also fake_dsh changed but defect_48 doesn't need it.

Careful: don't create anything inside the worktree. Use a temp dir outside: C:\Users\<user>\AppData\Local\Temp\m7review\redcheck.

</details>
Criteria 1–3 pass (6, 10, 5 tests). Now red-first proofs: export the base tree to a temp dir, overlay the new defect test files, and run them against the old code:
**toolCall bash** id=`call_e7c60f6c8920482eb445c70b`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && R=\"$TEMP/m7review/redcheck\" && rm -rf \"$R\" && mkdir -p \"$R\" && git archive arch/deepening | tar -x -C \"$R\" && for n in 44 45 46 47 48 49 50 51; do cp oh-dispatch/tests/test_defect_${n}_*.py \"$R/oh-dispatch/tests/\"; done && ls \"$R/oh-dispatch/tests/\" | grep -c test_defect && echo OK"
}
```

#### [69] line 69 · message · toolResult · 2026-10-02T01:55:42.890Z
66
OK
**toolResult** for `call_e7c60f6c8920482eb445c70b` (bash)

#### [70] line 70 · message · assistant · 2026-10-02T01:55:45.013Z
**toolCall bash** id=`call_7c4765fc34214e549cf068aa`

```json
{
 "command": "cd \"$TEMP/m7review/redcheck\" && for n in 44 45 46 47; do echo \"=== defect $n vs base ===\"; python oh-dispatch/tests/run_tests.py -k defect_$n -q 2>/dev/null | tail -2; done"
}
```

#### [71] line 71 · message · toolResult · 2026-10-02T01:55:54.407Z
=== defect 44 vs base ===
summary schema audit: this filtered selection produced no Engine summary
ran 6 tests in 0.2s   failures=5 errors=1 skipped=0
=== defect 45 vs base ===
summary schema audit: this filtered selection produced no Engine summary
ran 3 tests in 0.0s   failures=1 errors=0 skipped=0
=== defect 46 vs base ===
summary schema audit: this filtered selection produced no Engine summary
ran 5 tests in 0.0s   failures=0 errors=4 skipped=0
=== defect 47 vs base ===
summary schema audit: this filtered selection produced no Engine summary
ran 4 tests in 0.0s   failures=1 errors=1 skipped=0
**toolResult** for `call_7c4765fc34214e549cf068aa` (bash)

#### [72] line 72 · message · assistant · 2026-10-02T01:56:01.320Z
<details><summary>thinking</summary>

Defect 44 on base: 5 failures + 1 error. The error is probably `test_parent_session_vars_are_the_only_names_the_rule_removes` (worker_env doesn't exist) — that's fine; the 5 behavioral tests fail red. Actually wait, one of the 5 failures... let me quickly check which failed to confirm the lane tests fail behaviorally (not just import). Actually 6 tests ran, 5 failures + 1 error. The import succeeded (ohflow.lanes, ohflow.proc exist in base). Good.

Defect 45 on base: 1 failure of 3 (hermetic sets no env var). The other two pass on base too (`--setting-sources` flag already existed and the usual-setup test). Fine — at least one red.

Defect 46 on base: 4 errors (TypeError lane kwarg) + 1 pass (lane not checked when step names none). Red overall.

Defect 47 on base: 1 failure + 1 error. Red.

Now 48, 49, 50, 51 on base.

</details>
**toolCall bash** id=`call_7fd423e29910401b9747f914`

```json
{
 "command": "cd \"$TEMP/m7review/redcheck\" && for n in 48 49 50 51; do echo \"=== defect $n vs base ===\"; python oh-dispatch/tests/run_tests.py -k defect_$n -q 2>/dev/null | tail -2; done"
}
```

#### [73] line 73 · message · toolResult · 2026-10-02T01:56:09.930Z
=== defect 48 vs base ===
summary schema audit: this filtered selection produced no Engine summary
ran 4 tests in 0.0s   failures=11 errors=0 skipped=0
=== defect 49 vs base ===
summary schema checks: 2   unexpected rejections: 0
ran 1 tests in 5.5s   failures=1 errors=0 skipped=0
=== defect 50 vs base ===
summary schema audit: this filtered selection produced no Engine summary
ran 5 tests in 0.1s   failures=4 errors=0 skipped=0
=== defect 51 vs base ===
summary schema audit: this filtered selection produced no Engine summary
ran 4 tests in 0.0s   failures=3 errors=0 skipped=0
**toolResult** for `call_7fd423e29910401b9747f914` (bash)

#### [74] line 74 · message · assistant · 2026-10-02T01:56:18.795Z
<details><summary>thinking</summary>

All eight defect test files fail against the base code. Red-first proven for all.

Now: the manual resumed-run scenario. The review brief asks: "a resumed run (journal events after its last run_finished, a live supervisor, an older exit.json) that ohflow status, ohflow watch or the dashboard snapshot still calls finished; build one in a temp dir and run both verbs on it".

The unit tests cover this, but let me build one myself independently — with a *live supervisor* variant too. The unit test used `mark_alive` (a live supervisor marker) and a dead pid variant. Let me construct my own scenario without reusing their helpers where possible... Actually reusing the CLI is the point: build a run dir with journal.jsonl + plan.json + supervisor.pid pointing at a live process + old exit.json, then run `ohflow status --run` and `ohflow watch --run`. Let me check what `mark_alive` does — supervisor.pid + started_at? Let me look at verb_support/dashboard_support to mimic a real layout. Simpler: use the tests' own helpers but through the CLI — that's what defect_50's tests do via `call("status", ...)`. My independent check: write journal by hand.

Let me check the journal event format quickly from an existing test helper (dashboard_support.Journal) to write raw JSONL by hand. Actually — I'll write the JSONL by hand; format: {"ts": ..., "event": ..., "coord": ..., "payload": {...}}. Let me check what `ohflow status` needs: plan.json, journal.jsonl, supervisor.pid (with pid alive check pid_alive: pid + started_before). Writing a truly-live supervisor pid: use the current shell's PID? The check `pid_alive(pid, started_before=written)` — supervisor.pid contains a pid; there's probably a supervisor.started or the pid file mtime. Simplest: spawn a long-running python process (sleep 300), write its pid.

Let me look at how pid_alive works and what files are needed (supervisor.pid + maybe supervisor.started).

</details>
All eight defect files are red against the base — red-first holds. Now my own resumed-run scenario, built by hand, with a genuinely live supervisor:
**toolCall bash** id=`call_a81e439556064fbcaa46ff80`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && grep -n \"def pid_alive\\|supervisor.pid\\|supervisor.started\" oh-dispatch/scripts/ohflow/rundir.py | head -12 && grep -n \"def mark_alive\" -A 8 oh-dispatch/tests/dashboard_support.py"
}
```

#### [75] line 75 · message · toolResult · 2026-10-02T01:56:18.878Z
186:    be the run's supervisor before it writes `supervisor.pid`.
213:        """`supervisor.pid`, or without it `.ohflow-owner.json`, names a live
218:        journal line writes `supervisor.pid`.
225:            pid_path = self.run_dir / "supervisor.pid"
138:def mark_alive(run_dir: Path) -> None:
139-    """Name this test process as the run's supervisor.
140-
141-    The process was created before the file is written, which is exactly what
142-    `proc.pid_alive(pid, started_before=mtime)` requires of a real supervisor.
143-    """
144-    (Path(run_dir) / "supervisor.pid").write_text(str(os.getpid()),
145-                                                  encoding="utf-8")
146-
**toolResult** for `call_a81e439556064fbcaa46ff80` (bash)

#### [76] line 76 · message · assistant · 2026-10-02T01:56:28.971Z
**toolCall bash** id=`call_89a43b9dd36045a38410619b`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && D=\"$TEMP/m7review/resumed\" && rm -rf \"$D\" && mkdir -p \"$D/run\" && python - \"$D\" <<'EOF'\nimport json, os, subprocess, sys, time\nfrom pathlib import Path\nd = Path(sys.argv[1]) / \"run\"\n(d / \"plan.json\").write_text(json.dumps({\n    \"name\": \"resumed-check\", \"repo\": \".\", \"base_branch\": \"main\",\n    \"phases\": [{\"name\": \"Map\", \"slug_override\": \"map\",\n                \"steps\": [{\"id\": \"a\", \"kind\": \"worker\"}]}]}), encoding=\"utf-8\")\ndef rec(ts, ev, coord=None, **payload):\n    r = {\"ts\": ts, \"event\": ev}\n    if coord: r[\"coord\"] = coord\n    r[\"payload\"] = payload\n    (d / \"journal.jsonl\").write_text((d/\"journal.jsonl\").read_text(encoding=\"utf-8\") if (d/\"journal.jsonl\").exists() else \"\" + json.dumps(r) + \"\\n\", encoding=\"utf-8\", )\n# build journal in order\nlines = []\ndef add(ts, ev, coord=None, **payload):\n    r = {\"ts\": ts, \"event\": ev}\n    if coord: r[\"coord\"] = coord\n    r[\"payload\"] = payload\n    lines.append(json.dumps(r))\nadd(\"2026-10-02T10:00:00Z\", \"run_started\", run_id=\"r1\", plan=\"resumed-check\")\nadd(\"2026-10-02T10:00:01Z\", \"phase_started\", \"01.map\", name=\"Map\", steps=[\"01.map/01.a\"])\nadd(\"2026-10-02T10:00:02Z\", \"step_started\", \"01.map/01.a\")\nadd(\"2026-10-02T10:00:30Z\", \"step_finished\", \"01.map/01.a\", status=\"failed\")\nadd(\"2026-10-02T10:00:31Z\", \"phase_settled\", \"01.map\", status=\"failed\")\nadd(\"2026-10-02T10:00:32Z\", \"run_finished\", status=\"failed\")\n# the resume: no run-level event, work again\nadd(\"2026-10-02T11:00:00Z\", \"phase_started\", \"01.map\", name=\"Map\", steps=[\"01.map/01.a\"])\nadd(\"2026-10-02T11:00:01Z\", \"step_started\", \"01.map/01.a\")\n(d / \"journal.jsonl\").write_text(\"\\n\".join(lines) + \"\\n\", encoding=\"utf-8\")\n# old exit.json from the first stop, older than the journal\nex = d / \"exit.json\"\nex.write_text(json.dumps({\"status\": \"failed\", \"verdict\": \"Run r1 finished: 0 of 1 agents passed\", \"error\": None, \"traceback_tail\": []}), encoding=\"utf-8\")\npast = time.time() - 500\nos.utime(ex, (past, past))\n# a live supervisor: a sleeping child started before the pid file is written\nsleeper = subprocess.Popen([sys.executable, \"-c\", \"import time; time.sleep(120)\"],\n                           creationflags=subprocess.CREATE_NO_WINDOW)\n(d / \"supervisor.pid\").write_text(str(sleeper.pid), encoding=\"utf-8\")\nprint(\"run dir:\", d)\nprint(\"live supervisor pid:\", sleeper.pid)\nEOF"
}
```

#### [77] line 77 · message · toolResult · 2026-10-02T01:56:29.244Z
run dir: C:\Users\<user>\AppData\Local\Temp\m7review\resumed\run
live supervisor pid: 59248
**toolResult** for `call_89a43b9dd36045a38410619b` (bash)

#### [78] line 78 · message · assistant · 2026-10-02T01:56:35.114Z
**toolCall bash** id=`call_d2843e49fc39497697878027`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes/oh-dispatch/scripts\" && python -m ohflow.cli status --run \"C:/Users/<user>/AppData/Local/Temp/m7review/resumed/run\" 2>&1 | head -6; echo \"status exit: $?\""
}
```
**toolCall bash** id=`call_989c727e66c447b2874260cf`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes/oh-dispatch/scripts\" && python -m ohflow.cli watch --run \"C:/Users/<user>/AppData/Local/Temp/m7review/resumed/run\" --timeout 2 2>&1 | head -6; echo \"watch exit: $?\"; python -c \"\nimport sys; sys.path.insert(0, r'C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes/oh-dispatch/scripts')\nfrom pathlib import Path\nfrom ohflow import live\nsnap = live.snapshot(Path(r'C:/Users/<user>/AppData/Local/Temp/m7review/resumed/run'))\nprint('snapshot run status:', snap['run']['status'], '| finished:', snap['run'].get('finished'))\n\""
}
```

#### [79] line 79 · message · toolResult · 2026-10-02T01:56:35.569Z
running: 0 of 1 steps passed, 1 running, 0 failed, 0 pending · 0 s
status exit: 0
**toolResult** for `call_d2843e49fc39497697878027` (bash)

#### [80] line 80 · message · toolResult · 2026-10-02T01:56:35.570Z
running: 0 of 1 steps passed, 1 running, 0 failed, 0 pending · 0 s
01.map/01.a started (attempt 1)
watch exit: 0
snapshot run status: running | finished: None
**toolResult** for `call_989c727e66c447b2874260cf` (bash)

#### [81] line 81 · message · assistant · 2026-10-02T01:56:43.124Z
<details><summary>thinking</summary>

The resumed run with a live supervisor:
- `status` says "running" ✓ (not finished)
- `watch` says "running" ✓ (exit code — hmm, "watch exit: 0"? The echo shows 0 but that's the exit of `head`... Actually `python ... | head -6; echo $?` gives head's exit. Whatever — the first line says running.)
- snapshot: running, finished None ✓

Wait, one oddity: the step shows "1 running" but "attempt 1"? The resume wrote a second step_started without attempt... The step_started payload in my handmade journal lacks attempt info; fine, not the code under review.

Also the old exit.json was correctly ignored (status would have said "failed" otherwise).

Now kill the sleeper and check the orphaned path... Actually defect_50's test covers the dead-supervisor case. Let me kill the sleeper anyway to be clean, and also verify `watch` with dead supervisor shows orphaned:

</details>
**toolCall bash** id=`call_906fff4c316a4a88bf82ad1c`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes/oh-dispatch/scripts\" && python -c \"\nimport os, signal\nos.kill(59248, signal.SIGTERM)\n\" ; sleep 1; python -m ohflow.cli watch --run \"C:/Users/<user>/AppData/Local/Temp/m7review/resumed/run\" --timeout 2 2>&1 | head -3; python -m ohflow.cli status --run \"C:/Users/<user>/AppData/Local/Temp/m7review/resumed/run\" 2>&1 | head -2"
}
```

#### [82] line 82 · message · toolResult · 2026-10-02T01:56:44.746Z
orphaned: 0 of 1 steps passed, 0 running, 0 failed, 0 pending, 1 interrupted · 0 s
01.map/01.a interrupted
run orphaned
orphaned: 0 of 1 steps passed, 0 running, 0 failed, 0 pending, 1 interrupted · 0 s
`01.map/01.a` was running when the supervisor stopped; `--resume` starts a new attempt
**toolResult** for `call_906fff4c316a4a88bf82ad1c` (bash)

#### [83] line 83 · message · assistant · 2026-10-02T01:56:50.537Z
<details><summary>thinking</summary>

The dead-supervisor resumed run reads "orphaned", not "finished", and the old exit.json verdict is not printed. The resumed-run fix holds end to end.

Now the three shards. Each ~5 min. I must run them one at a time in the foreground, logging outside the worktree. Log path: `$TEMP/m7review/shardK.log`.

Before that, let me kick off... no — never run two suites at once. Run shard 1 first.

</details>
The resumed-run fix holds end to end (live → running; dead → orphaned; old exit.json ignored). Now the three shards, one at a time, logged outside the worktree:
**toolCall bash** id=`call_4d93747208b4450881c526c8`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && python oh-dispatch/tests/run_tests.py --shard 1/3 > \"$TEMP/m7review/shard1.log\" 2>&1; tail -3 \"$TEMP/m7review/shard1.log\"",
 "timeout": 660
}
```

#### [84] line 84 · message · toolResult · 2026-10-02T02:02:32.369Z

summary schema checks: 79   unexpected rejections: 0
ran 304 tests in 340.9s   failures=0 errors=0 skipped=1
**toolResult** for `call_4d93747208b4450881c526c8` (bash)

#### [85] line 85 · message · assistant · 2026-10-02T02:02:36.373Z
**toolCall bash** id=`call_1ddc3c3ac8794505b3550737`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && python oh-dispatch/tests/run_tests.py --shard 2/3 > \"$TEMP/m7review/shard2.log\" 2>&1; tail -3 \"$TEMP/m7review/shard2.log\"",
 "timeout": 660
}
```

#### [86] line 86 · message · toolResult · 2026-10-02T02:07:53.970Z

summary schema checks: 82   unexpected rejections: 0
ran 304 tests in 316.6s   failures=0 errors=0 skipped=0
**toolResult** for `call_1ddc3c3ac8794505b3550737` (bash)

#### [87] line 87 · message · assistant · 2026-10-02T02:07:57.019Z
**toolCall bash** id=`call_b00000ea83f54572aec4ca84`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && python oh-dispatch/tests/run_tests.py --shard 3/3 > \"$TEMP/m7review/shard3.log\" 2>&1; tail -3 \"$TEMP/m7review/shard3.log\"",
 "timeout": 660
}
```

#### [88] line 88 · message · toolResult · 2026-10-02T02:12:49.060Z

summary schema checks: 87   unexpected rejections: 0
ran 303 tests in 291.2s   failures=0 errors=0 skipped=0
**toolResult** for `call_b00000ea83f54572aec4ca84` (bash)

#### [89] line 89 · message · assistant · 2026-10-02T02:12:56.693Z
<details><summary>thinking</summary>

Three shards: 304 + 304 + 303 = 911 tests, 0 failures, 0 errors, 1 skip. Total wall 340.9 + 316.6 + 291.2 = 948.7 s.

README says: "A full run takes about fifteen minutes (902 tests, 873 s on 2026-10-02)" and "Each shard takes about five minutes (328.9 s, 285.4 s and 258.4 s on 2026-10-02)".

Measured now: 911 tests, 948.7 s total, shards 340.9/316.6/291.2. So the README's figures are stale on both count (902 vs 911) and times — the count is wrong by exactly the 9 tests added after the README commit. The times are load-dependent, but the *count* is objective and wrong. This is a real prose defect against spec scope item 5 ("update the suite figure from a shard run on this branch. One place each.").

Severity: it's a documentation figure the spec explicitly required to be from this branch, and it isn't (it's from a mid-branch commit). I'd call this a genuine finding but modest — not shippable-blocker? Hmm. "BLOCKED when any exit criterion fails or any finding would ship a defect." Prose is code in this campaign. A README that misstates the test count ships a defect in prose. It's borderline; let me collect all findings first and weigh.

Now the big one: exit criterion 4 — the live rollcall with the desktop-session env exported, with `--out "$(mktemp -d)"`. From `oh-dispatch/scripts`. The cells: single:host, single:claude:1:profile=hermetic, relay:pi,claude,codex,dsh. Expected last line `ROLLCALL PASS: 3 of 3 cells`.

Command shape: `ohflow rollcall --cells ...`. Let me check the rollcall CLI verb to get exact flags (--matrix? --cells? --out?).

</details>
911 tests, all green (304+304+303, one opt-in skip). The README's "902 tests" is stale — confirmed by my shard run. Now exit criterion 4, the live matrix. First the exact CLI:
**toolCall bash** id=`call_84a0f9c084434c67be6d57a7`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && grep -n \"rollcall\" oh-dispatch/scripts/ohflow/cli.py | head -15"
}
```

#### [90] line 90 · message · toolResult · 2026-10-02T02:12:56.754Z
24:    ohflow rollcall [--matrix smoke|quick|full | --cells shape:lanes[:count] ...]
499:def cmd_rollcall(ns) -> int:
500:    from . import rollcall
502:        for line in rollcall.list_lines():
505:    return rollcall.run_matrix(
974:    p = sub.add_parser("rollcall",
995:    p.set_defaults(fn=cmd_rollcall)
**toolResult** for `call_84a0f9c084434c67be6d57a7` (bash)

#### [91] line 91 · message · assistant · 2026-10-02T02:13:01.635Z
**toolCall bash** id=`call_5bf866ba2c8f4a2382797216`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && sed -n 974,996p oh-dispatch/scripts/ohflow/cli.py && sed -n 499,510p oh-dispatch/scripts/ohflow/cli.py"
}
```

#### [92] line 92 · message · toolResult · 2026-10-02T02:13:01.745Z
    p = sub.add_parser("rollcall",
                       help="run the roll-call matrix: every shape on every "
                            "lane, one verdict line per cell")
    p.add_argument("--matrix", default=None, metavar="NAME",
                   help="smoke, quick or full (default quick)")
    p.add_argument("--cells", nargs="+", default=None,
                   metavar="shape:lanes[:count]",
                   help="run these cells instead of a matrix")
    p.add_argument("--dry-run", action="store_true",
                   help="build and validate every cell's plan; start nothing")
    p.add_argument("--config", default=None, metavar="FILE",
                   help="a JSON file that sets model and params per lane")
    p.add_argument("--repo", default=None,
                   help="a git repository to run in; the default is a "
                        "throwaway one under --out")
    p.add_argument("--out", default=None,
                   help="where the cells and matrix.json go")
    p.add_argument("--list", action="store_true",
                   help="print each matrix's cells and exit")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="stream each run's own lines")
    p.set_defaults(fn=cmd_rollcall)

def cmd_rollcall(ns) -> int:
    from . import rollcall
    if ns.list:
        for line in rollcall.list_lines():
            print(line)
        return EXIT_OK
    return rollcall.run_matrix(
        matrix=ns.matrix, cells=ns.cells, repo=ns.repo, out=ns.out,
        config=ns.config, dry=ns.dry_run, verbose=ns.verbose, lanes=ns.lanes,
        write=print)
**toolResult** for `call_5bf866ba2c8f4a2382797216` (bash)

#### [93] line 93 · message · assistant · 2026-10-02T02:13:19.418Z
<details><summary>thinking</summary>

Now run criterion 4 exactly as specified: with `CLAUDECODE=1`, `CLAUDE_CODE_ENTRYPOINT=claude-desktop`, `CLAUDE_AGENT_SDK_VERSION=0.3.284` exported, from `oh-dispatch/scripts`, with `--out "$(mktemp -d)"`. This runs live workers on pi, claude, codex, dsh and host lanes. The full matrix took ~33 min for 15 cells; these 3 cells took 138+37+334 ≔ 510 s ≈ 8.5 min in the first matrix. With retries maybe longer. Timeout: 600000 ms = 10 min max per bash call. Risky — the relay cell alone was 334 s and might retry. Hmm, the bash tool timeout parameter — the brief said "longer than one shell call may run (600000 ms)". So a bash call maxes at 600 s. If the rollcall exceeds 10 min, my call dies. 

Wait, actually let me re-read: "The full suite now takes about fifteen minutes ... longer than one shell call may run (600000 ms)". So the max timeout is 600000 ms = 600 s. The 3 cells: single host 138 s + single claude hermetic ~37 s (failed fast before; now should pass, maybe ~90 s) + relay ~334 s (failed at stall before; now codex gets 600 s stall, could run longer). Total maybe 560-700 s + matrix overhead. Could exceed 600 s.

Can I pass a longer timeout? The tool schema says timeout is a number in seconds, "no default timeout". The 600000 ms limit was mentioned for the implementer's harness. Let me try timeout 1200 and see if it's accepted. If the harness rejects >600... I'll try. Actually the brief for me (reviewer) says "each under ten minutes" for shards only. For criterion 4 it doesn't state a limit. I'll set a generous timeout (1500 s) and hope the tool allows it. If the tool caps at 600, I may need to split cells across calls — but the criterion requires one command producing `ROLLCALL PASS: 3 of 3 cells`. Hmm — "at most three times each" was for the implementer; for me, run it once properly.

Also: don't run two suites at once — nothing else running now. The run writes to a mktemp -d dir outside the worktree. ✓

One more thing to check before the live run: the rollcall verb needs the scratch repo — default "a throwaway one under --out". Good, self-contained.

Env vars: export CLAUDECODE=1 CLAUDE_CODE_ENTRYPOINT=claude-desktop CLAUDE_AGENT_SDK_VERSION=0.3.284. In Git bash on Windows, `export` works for the python child. 

Let me run it with `--out "$(mktemp -d)"` exactly. In bash on this box mktemp -d gives /tmp/tmp.XXXX which maps to the user's temp. The dsh bucket needs the `.` in the path — that's the point (a run on the default --out hid a dsh defect). Let me capture the out dir path to a file so I can inspect result.json afterwards.

</details>
Now exit criterion 4, exactly as the campaign driver runs it — exported desktop-session vars, `--out "$(mktemp -d)"`, from `oh-dispatch/scripts`. This runs live workers on all five lanes; giving it a long leash:
**toolCall bash** id=`call_337251c7b9c642da8cb24322`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes/oh-dispatch/scripts\" && export CLAUDECODE=1 CLAUDE_CODE_ENTRYPOINT=claude-desktop CLAUDE_AGENT_SDK_VERSION=0.3.284 && OUT=$(mktemp -d) && echo \"$OUT\" > \"$TEMP/m7review/crit4-out.txt\" && python -m ohflow.cli rollcall --cells single:host single:claude:1:profile=hermetic relay:pi,claude,codex,dsh --out \"$OUT\" > \"$TEMP/m7review/crit4.log\" 2>&1; echo \"exit: $?\"; tail -6 \"$TEMP/m7review/crit4.log\"",
 "timeout": 1500
}
```

#### [94] line 94 · message · toolResult · 2026-10-02T02:22:17.717Z
exit: 0
PASS single host count=1  1m47s  75.5 k tokens  C:\Users\<user>\AppData\Local\Temp\tmp.yYeyfLXeNB\01-single-host-1\run
PASS single claude count=1 profile=hermetic  0m34s  97.4 k tokens  C:\Users\<user>\AppData\Local\Temp\tmp.yYeyfLXeNB\02-single-claude-1\run
PASS relay pi,claude,codex,dsh count=1  6m34s  1845.8 k tokens  C:\Users\<user>\AppData\Local\Temp\tmp.yYeyfLXeNB\03-relay-pi-claude-codex-dsh-1\run
ROLLCALL PASS: 3 of 3 cells
**toolResult** for `call_337251c7b9c642da8cb24322` (bash)

#### [95] line 95 · message · assistant · 2026-10-02T02:22:24.200Z
<details><summary>thinking</summary>

Criterion 4 PASSES: `ROLLCALL PASS: 3 of 3 cells`, exit 0, with the desktop-session variables exported and a `tmp.XXXXXXXXXX` out dir (which exercises the dsh bucket with a `.`).

Now the review checklist item: "a roll-call worker whose iteration budget a normal run can use up: in your criterion-4 run, read each step's `llm_calls` (or turn count) in `result.json` against `max_iterations` in its `spec.json`, and report the host cell's two numbers."

Let me read every step's spec.json max_iterations and result.json llm_calls (or turns / iterations) from all three cell run dirs.

</details>
Criterion 4 passes: `ROLLCALL PASS: 3 of 3 cells` under the desktop-session env, on a `tmp.` path (dsh bucket exercised). Now the iteration-budget audit of every step in that run:
**toolCall bash** id=`call_c3aa6fe2742c458698f11c0a`

```json
{
 "command": "OUT=$(cat \"$TEMP/m7review/crit4-out.txt\") && python - \"$OUT\" <<'EOF'\nimport json, sys\nfrom pathlib import Path\nroot = Path(sys.argv[1])\nfor run in sorted(root.glob(\"*/run\")):\n    for spec in sorted(run.rglob(\"spec.json\")):\n        d = spec.parent\n        rj = d / \"result.json\"\n        specd = json.loads(spec.read_text(encoding=\"utf-8\"))\n        worker = specd.get(\"worker\") or specd\n        mi = worker.get(\"max_iterations\") or specd.get(\"max_iterations\")\n        res = json.loads(rj.read_text(encoding=\"utf-8\")) if rj.exists() else {}\n        calls = (res.get(\"llm_calls\") or res.get(\"iterations\")\n                 or res.get(\"turns\") or res.get(\"usage\", {}).get(\"turns\"))\n        lane = worker.get(\"lane\") or specd.get(\"lane\")\n        print(f\"{run.parent.name:38s} {str(d.relative_to(run)):28s} lane={lane:6s} \"\n              f\"max_iter={mi} llm_calls={calls} error={res.get('error')}\")\nEOF"
}
```

#### [96] line 96 · message · toolResult · 2026-10-02T02:22:24.509Z
01-single-host-1                       phases\01.report\01.host-1\attempts\01 lane=host   max_iter=30 llm_calls=8 error=None
01-single-host-1                       phases\01.report\01.host-1   lane=host   max_iter=30 llm_calls=8 error=None
02-single-claude-1                     phases\01.report\01.claude-1\attempts\01 lane=claude max_iter=30 llm_calls=6 error=None
02-single-claude-1                     phases\01.report\01.claude-1 lane=claude max_iter=30 llm_calls=6 error=None
03-relay-pi-claude-codex-dsh-1         phases\01.relay-1-pi-1\01.pi-1\attempts\01 lane=pi     max_iter=30 llm_calls=4 error=None
03-relay-pi-claude-codex-dsh-1         phases\01.relay-1-pi-1\01.pi-1 lane=pi     max_iter=30 llm_calls=4 error=None
03-relay-pi-claude-codex-dsh-1         phases\02.relay-2-claude-1\01.claude-1\attempts\01 lane=claude max_iter=30 llm_calls=8 error=None
03-relay-pi-claude-codex-dsh-1         phases\02.relay-2-claude-1\01.claude-1 lane=claude max_iter=30 llm_calls=8 error=None
03-relay-pi-claude-codex-dsh-1         phases\03.relay-3-codex-1\01.codex-1\attempts\01 lane=codex  max_iter=30 llm_calls=1 error=None
03-relay-pi-claude-codex-dsh-1         phases\03.relay-3-codex-1\01.codex-1 lane=codex  max_iter=30 llm_calls=1 error=None
03-relay-pi-claude-codex-dsh-1         phases\04.relay-4-dsh-1\01.dsh-1\attempts\01 lane=dsh    max_iter=30 llm_calls=9 error=None
03-relay-pi-claude-codex-dsh-1         phases\04.relay-4-dsh-1\01.dsh-1 lane=dsh    max_iter=30 llm_calls=9 error=None
**toolResult** for `call_c3aa6fe2742c458698f11c0a` (bash)

#### [97] line 97 · message · assistant · 2026-10-02T02:22:31.409Z
<details><summary>thinking</summary>

Every step: max_iterations=30, llm_calls between 1 and 9. The host cell: **max_iterations 30, llm_calls 8**. Comfortable headroom (the defect-51 report said the old failing host worker hit 15; with the new "fill from your own prompt" instruction it used 8).

Interesting: codex llm_calls=1? That might be counting turns differently for codex (one exec call). Fine.

Also: did the workers report the right identity this time? Let me check the host worker's report — the harness line — and the hermetic claude's mcp_servers (should be none, and no instruction-file servers like cortex/archive). Also check the gate passed rollcall_matches with lane matching. Let me read the structured reports from the runs.

</details>
Every step sits well under budget. The host cell: **max_iterations 30, llm_calls 8**. Now verify the workers' actual reports — the host identity fix and the hermetic claude's isolation:
**toolCall bash** id=`call_b2f66d36429f4461b8f4188f`

```json
{
 "command": "OUT=$(cat \"$TEMP/m7review/crit4-out.txt\") && python - \"$OUT\" <<'EOF'\nimport json, sys\nfrom pathlib import Path\nroot = Path(sys.argv[1])\nfor run in sorted(root.glob(\"*/run\")):\n    for rj in sorted(run.rglob(\"attempts/*/result.json\")):\n        res = json.loads(rj.read_text(encoding=\"utf-8\"))\n        rep = res.get(\"structured\") or {}\n        if not rep: continue\n        print(f\"== {run.parent.name} {rj.parent.parent.parent.name}\")\n        print(\"   lane:\", rep.get(\"lane\"), \"| harness:\", rep.get(\"harness\"))\n        print(\"   model:\", rep.get(\"model\"))\n        print(\"   tools:\", rep.get(\"tools\"))\n        print(\"   mcp_servers:\", rep.get(\"mcp_servers\"))\nEOF"
}
```

#### [98] line 98 · message · toolResult · 2026-10-02T02:22:31.574Z
== 01-single-host-1 01.host-1
   lane: host | harness: OpenHands (version unknown)
   model: unknown
   tools: ['terminal', 'file_editor', 'task_tracker', 'finish', 'think']
   mcp_servers: []
== 02-single-claude-1 01.claude-1
   lane: claude | harness: Claude Code (Claude Agent SDK)
   model: claude-haiku-4-5-20251001
   tools: ['Bash', 'Edit', 'Glob', 'Grep', 'Read', 'Write', 'StructuredOutput']
   mcp_servers: []
== 03-relay-pi-claude-codex-dsh-1 01.pi-1
   lane: pi | harness: pi coding agent (version unknown)
   model: claude-opus-4-6
   tools: ['bash', 'read', 'edit', 'write']
   mcp_servers: []
== 03-relay-pi-claude-codex-dsh-1 01.claude-1
   lane: claude | harness: Claude Code
   model: claude-haiku-4-5-20251001
   tools: ['Agent', 'Bash', 'Edit', 'Glob', 'Grep', 'ListAgents', 'Monitor', 'PowerShell', 'Read', 'ScheduleWakeup', 'Skill', 'ToolSearch', 'Workflow', 'Write', 'StructuredOutput']
   mcp_servers: ['archive', 'forum', 'deepthink', 'flaui', 'google-search', 'brave-search', 'mcp-inspector', 'web-surfer-llm', 'linkedin', 'google-workspace']
== 03-relay-pi-claude-codex-dsh-1 01.codex-1
   lane: codex | harness: Codex (version unknown)
   model: GPT-5
   tools: ['exec_command']
   mcp_servers: []
== 03-relay-pi-claude-codex-dsh-1 01.dsh-1
   lane: dsh | harness: DSH (DeepSeek Harness), version unknown
   model: glm-5.3-flash
   tools: ['create_goal', 'edit', 'exit_plan_mode', 'get_goal', 'glob', 'grep', 'interrupt_agent', 'job_kill', 'job_list', 'job_output', 'list_agents', 'pwsh', 'ralph', 'read', 'read_image', 'send_message', 'skill', 'subconscious_rate', 'subconscious_status', 'todo_write', 'update_goal', 'web_fetch', 'web_search', 'workflow', 'write']
   mcp_servers: ['apthunt', 'brave-search', 'cortex-generic', 'deepthink', 'doctolib', 'fff', 'flaui', 'forum', 'gemini', 'google-search', 'google-workspace', 'isession', 'linkedin', 'mcp-inspector', 'archive', 'note-store', 'memory', 'n8n-mcp', 'serena', 'web-surfer-llm']
**toolResult** for `call_b2f66d36429f4461b8f4188f` (bash)

#### [99] line 99 · message · assistant · 2026-10-02T02:23:12.983Z
<details><summary>thinking</summary>

The evidence is exactly what the milestone promised:

1. **Host worker** (with `CLAUDECODE=1`, `CLAUDE_CODE_ENTRYPOINT=claude-desktop`, `CLAUDE_AGENT_SDK_VERSION=0.3.284` exported in my shell, inherited by the driver): reports "OpenHands (version unknown)" with OpenHands tools (`terminal`, `file_editor`, `task_tracker`, `finish`, `think`) — no more "Claude Code 2.1.284". The env stripping works end to end. ✓

2. **Hermetic claude**: `mcp_servers: []` — the ten user MCP servers from `~/.claude/CLAUDE.md` are gone. Model claude-haiku-4-5. Login kept (the run passed and produced output). ✓

3. **Relay**: claude (usual setup) reports its MCP servers; codex passed without a stall kill; dsh found its session on the `tmp.` path. ✓

Now let me double-check the exported env actually reached the driver process — i.e., that my criterion-4 run genuinely had the parent session vars. `export CLAUDECODE=1 ... && python -m ohflow.cli rollcall ...` — yes, the python child inherited them, and workers stripped them. And note: *this reviewer session itself* runs inside some environment — my own shell had those vars exported only for that command. Good.

Wait — one more check on the host worker: `model: unknown`. The REPORT now says to write unknown when not shown. Fine.

Now remaining checks from the review list:

- "a stall limit that a lane's normal silence can still trip (codex reasoning, a long foreground command)" — codex got 600 s; the relay codex step passed (relay total 6m34s across 4 workers). dsh 180 s with session-log mtime liveness. pi 180 s: a pi worker running a long foreground command — pi emits per-action stdout? The pi runner watches stdout lines; a long silent command could trip 180 s... pre-existing behavior, not changed by this milestone; the first live matrix had pi passing everywhere. Not a new defect.

- "a report whose lane names another lane and still passes the gate" — gate now fails it; test 46 red-first proven. Also all four `_report_checks` call sites pass lane; the live run's reports all named their own lanes (and passed). ✓

- "a dsh session bucket that differs from dsh's own projectKey rule for any path" — port matches the JS exactly; I compared line by line. Also the live run on a `tmp.` path passed. ✓

- "a hermetic claude session that can still read the user's instruction files or settings" — live: no user MCP servers leaked, so instruction files did not load. Settings: `--setting-sources project,local` drops user settings. Login kept (run passed). ✓ But the lanes.md prose issue stands (project `.claude` files claimed kept while the env var also drops project CLAUDE.md/rules).

Let me now double-check the lanes.md claim once more, since it's my main candidate finding. The table:

| `claude` | Removes: the user's instruction files (`CLAUDE_CODE_DISABLE_CLAUDE_MDS=1`), the user's settings (`--setting-sources project,local`), every built-in tool the plan does not name (`--tools`), every MCP server the plan does not name (`--strict-mcp-config`) | Keeps: the OAuth login, the plan's `--mcp-config` servers, the project's own `.claude` files |

Binary evidence: `gCn` (project memory loader) returns [] when CLAUDE_CODE_DISABLE_CLAUDE_MDS is set — before touching project CLAUDE.md, .claude/CLAUDE.md, CLAUDE.local.md, .claude/rules. `iet` (managed+user memory) same. So the env var removes *all* instruction files, not only "the user's". And "the project's own `.claude` files" in Keeps is true only for *settings* (`.claude/settings.json`, `.claude/settings.local.json` via --setting-sources project,local), false for instruction files under `.claude/` (CLAUDE.md, rules).

Hmm, wait — is it possible that `--setting-sources` affects which of gCn's branches run (yw("projectSettings")) and the env var check in gCn... no. The env var check is first and unconditional. So with profile=hermetic: project CLAUDE.md does NOT load. The doc says hermetic keeps "the project's own `.claude` files" — a reader would take that to include `.claude/CLAUDE.md`/rules. At minimum the Removes column under-states (says "the user's instruction files" when it's every instruction file), and the Keeps column over-states.

Is this worth BLOCKED? The campaign bar #6: "no statement the code contradicts". This is a statement the installed CLI binary contradicts. The spec scope item 2 explicitly required: "say in references/lanes.md, for each lane, what hermetic removes and what it keeps". The sentence says something wrong about what hermetic removes/keeps. It's a one-line prose fix, but reviews in this campaign treat prose as code.

Let me weigh: Does it "ship a defect"? A developer relying on lanes.md to know that a hermetic claude worker still reads the project's CLAUDE.md would be wrong — their hermetic roll-call/review worker in a repo with a project CLAUDE.md would NOT see it. Conversely someone wanting hermeticity might be told project files leak in when they don't (less harmful direction, but still wrong). The practical direction of wrongness: doc claims *less* isolation than reality in Removes ("user's" only) and *more* retention in Keeps (project .claude files). Hmm, actually which way? Reality: hermetic is *more* isolated than documented. The doc says it keeps project .claude files; actually it drops the instruction ones. So the doc under-claims isolation for instruction files, over-claims for settings? No — settings: `--setting-sources project,local` genuinely keeps project+local settings. So "the project's own `.claude` files" is true for settings files and false for instruction files. Ambiguous at best, false at worst.

Also the comment in claude_runner.py lines 37-41: "This variable drops them [the user's instruction files] and keeps the `--mcp-config` servers and the login." — also silent on project instruction files. And test_defect_45's docstring similarly. The code comment says "--setting-sources project,local drops the user's settings but not the user's instruction files (CLAUDE.md). This variable drops them..." — accurate as far as it goes.

I'll report this as a finding. Is it BLOCKED-worthy alone? Let me think about the two candidate findings:

F1. lanes.md hermetic table misstates what CLAUDE_CODE_DISABLE_CLAUDE_MDS removes (all instruction files, including the project's own CLAUDE.md/.claude/rules/CLAUDE.local.md) and what is kept ("the project's own `.claude` files" is true only of settings). Evidence: the installed CLI binary's gCn/iet short-circuit. This contradicts charter bar #6 and the spec's scope item 2 requirement to "say in references/lanes.md ... what hermetic removes and what it keeps" — the sentence says it wrong.

F2. README suite figure stale: "902 tests" but the branch runs 911; shard times also predate the last two commits. Spec scope item 5: "update the suite figure from a shard run on this branch". The figure came from a mid-branch commit. My measurement: 911 tests, 340.9/316.6/291.2 s.

F2 is unambiguous — the number is objectively wrong (911 ≠ 902). The spec explicitly required this figure from a shard run on this branch. That's a failed spec scope item, though not one of the five exit criteria (criterion 5 only checks "not measured yet" absence). Under "any finding would ship a defect" — a wrong measured figure in the README ships a prose defect.

Hmm. How severe are these? Both are one-line doc fixes. The instructions say BLOCKED when any exit criterion fails OR any finding would ship a defect. Strictly, both findings ship prose defects ("prose is code"). But I should be careful not to be pedantic to the point of uselessness... Let me think about what a careful adversarial reviewer in this campaign would do. The campaign treats prose defects as real defects — m6 is the documents milestone, but "until then each milestone keeps them true". A README figure that is off by 9 tests (1%) — is it " untrue"? It says "A full run takes about fifteen minutes (902 tests, 873 s on 2026-10-02)". The branch it ships on has 911 tests. It's a false measured claim about the artifact being merged. The spec scope item says "update the suite figure from a shard run on this branch" — the implementer did run shards mid-branch and updated, then added 9 more tests without re-updating. That's a process slip, small but real and objective.

F1 is a subtler semantic error but more consequential for users of the skill.

Let me also finish the remaining checklist items before deciding:

- "a test that passes both with and without its fix" — defect 45: `test_hermetic_profile_keeps_the_setting_source_flag` passes on base too (the flag pre-existed). And `test_the_usual_setup_keeps_the_instruction_files` passes on base too. Only 1 of 3 is red. The file as a whole is red on base, which satisfies "a test that fails against the old code". Similarly defect 46's `test_report_lane_is_not_checked_when_the_step_names_none` passes on base. That's fine — the *defect* tests are red, extra pinning tests may pass. The rule: "Prove a defect test fails against the old code before you keep it" — the defect assertion (hermetic sets the env var) does fail on base. OK.

- Also check defect_42 ("tests ignore the workers environment") — not changed.

- Check that `worker_env` doesn't break `seat_runner.NPM_DIR` etc. — no.

- One more code-level check on `worker_env` docstring: "Measured 2026-09-30 from a desktop-app session: 25 CLAUDE* names" — comment moved verbatim. Fine.

- Check `proc.py` imports `re` — yes, added.

- gates.py decorator lambda uses a['lane'] — f-string with a['lane'] inside a lambda default... it's `lambda a: ... + (f"; the report names lane {a['lane']}" if a.get("lane") else "")`. Careful with quotes: outer f-string uses double quotes, inner a['lane'] single. OK.

- journal.py `_NOT_WORK_EVENTS` includes "journal_recovered". What other run-level events exist? From STATUSES/events list at line 44-45: run_started, phase_started, step_started, step_finished, gate_ran, phase_settled, run_finished... any "run_paused"/"run_resumed" events? Let me grep for journal event names to make sure a pause event after run_finished can't exist (pause implies not finished). Events that could appear after run_finished without being work: "journal_recovered". What about "gate_ran" — that IS work (a gate ran after finish? possible during resume). OK it counts as work → running. Reasonable.

  Edge: `state.finished` is a truthy timestamp string. After run_finished at ts X, a `journal_recovered` event → not work. Good, because recovery happens at open time before replay... fine.

- `exit_record` mtime comparison: `journal.jsonl` mtime > exit.json mtime → ignore exit.json. Subtle failure mode: a *finished* run whose journal was later touched (e.g., a recovery append or someone `touch`ed it) — then a valid exit.json would be ignored and `watch` would rebuild the exit report instead of reading the verdict... In `_exit_report`, `written = _exit_status(run_dir)` returns None → it goes to `ohexit.rebuild(run_dir)` which rebuilds from the journal → verdict from journal. For a genuinely finished run, journal says finished; rebuild produces the right verdict. And `exit_info_from_files` checks `run.state.status` (journal) first — only falls to exit_record for crashed/interrupted without journal verdict. A crash writes exit.json but no run_finished; is the journal newer or older than exit.json then? On crash, exit.json is written last → journal older → counts. On resume-after-crash: journal appended after → ignored → correct.

  One more: `watch._idle_seconds` and `.watch.` files — fine.

  What about `status_without_journal` for a run with NO journal but an exit.json — unchanged path. OK.

- The dashboard snapshot (`live.snapshot`) uses Journal.replay → reopened logic applies. ✓ (tested + my manual run).

- campaign.py `.watch.*.json` ignore: `ensure_ignores` runs when? At campaign setup — for *existing* campaigns the .gitignore gets the line appended on next driver start. Defect 49's test asserts it. ✓

- README "quick" figure note honestly says it's a sum, not a run. Spec said: "Fill the 'Wall time' column of the quick and full rows from the measured matrix.json above" ✓ done exactly.

- "One place each" for figures — suite figure appears once (README line 29 + shard line 31 — the shard seconds are a second place but that's the shard breakdown, arguably fine; spec's "one place each" refers to the wall-time figures... it says "Fill the Wall time column of the quick and full rows from the measured matrix.json above, and update the suite figure from a shard run on this branch. One place each." I read "one place each" as: each figure lives in one place (no duplication elsewhere in docs). Let me grep for other occurrences of the figures in references/ and SKILL.md.

</details>
All five lanes report their own identity now. Two remaining checks — figure duplication ("one place each") and any other prose claims about the new behavior:
**toolCall bash** id=`call_ad17cf646f6a44da828ca0ec`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && grep -rn \"1466\\|1942\\|24 m\\|32 m\\|902\\|911\" oh-dispatch/README.md oh-dispatch/SKILL.md oh-dispatch/references/ 2>/dev/null; grep -rn \"stall\" oh-dispatch/SKILL.md | head -8"
}
```
**toolCall bash** id=`call_dd3bd67c7a13488b8a701288`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && grep -rn \"CLAUDE\\|ANTHROPIC\" oh-dispatch/SKILL.md oh-dispatch/references/*.md | grep -iv \"claude code\\|claude lane\\|claude.md\\b\" | head -12"
}
```

#### [100] line 100 · message · toolResult · 2026-10-02T02:23:13.148Z
oh-dispatch/README.md:29:The suite uses `unittest` from the standard library. It runs from a fresh clone and needs no network. A full run takes about fifteen minutes (902 tests, 873 s on 2026-10-02). Run it in three shards. Each shard stays under ten minutes.
oh-dispatch/README.md:100:| `quick` | 10 | `single` on all five lanes; `fanout`, `relay` and `merge` on `pi`, `claude`, `codex`, `dsh`; `retry` on `pi`; `review` on `pi` then `claude` | 24 m 27 s (1466.5 s: the sum of these ten cells' times in the first full matrix run on 2026-10-01, not a run of `quick`; 2 of the 10 failed before the m7 fixes) |
oh-dispatch/README.md:101:| `full` | 15 | `quick`, plus `fanout` on `pi` with `count=3`, `campaign` on `pi`, `single` hermetic on `claude` and on `codex`, `retry` on `claude` with `carry_context` | 32 m 23 s (1942.7 s, same run; 3 of 15 cells failed before the m7 fixes) |
**toolResult** for `call_ad17cf646f6a44da828ca0ec` (bash)

#### [101] line 101 · message · toolResult · 2026-10-02T02:23:13.150Z
oh-dispatch/references/lanes.md:52:| Executable | pi CLI | `~/sdk/.venv` Python | `OHFLOW_CLAUDE_EXE`, else the npm `claude.cmd` target `claude.exe` | `OHFLOW_CODEX_EXE`, else `node` + `codex.js` | `OHFLOW_DSH_EXE`, else `node` + `dsh/lib/bin.js` |
oh-dispatch/references/lanes.md:61:A hermetic worker starts from nothing the seat owns, except its login. Every lane also drops the launching session's variables (`CLAUDE*`, `CLAUDECODE`, `ANTHROPIC_BASE_URL`), hermetic or not.
oh-dispatch/references/lanes.md:67:| `claude` | the user's instruction files (`CLAUDE_CODE_DISABLE_CLAUDE_MDS=1`), the user's settings (`--setting-sources project,local`), every built-in tool the plan does not name (`--tools`), every MCP server the plan does not name (`--strict-mcp-config`) | the OAuth login, the plan's `--mcp-config` servers, the project's own `.claude` files |
oh-dispatch/references/lanes.md:163:- **A clean environment.** Every `CLAUDE*` variable and `ANTHROPIC_BASE_URL` is removed. A desktop-app session exports 25 `CLAUDE*` names and an `ANTHROPIC_BASE_URL` that points at the app's own proxy.
**toolResult** for `call_dd3bd67c7a13488b8a701288` (bash)

#### [102] line 102 · message · assistant · 2026-10-02T02:23:19.502Z
<details><summary>thinking</summary>

Figures appear only in README. ✓ "One place each" holds.

Let me now also check `references/ohflow.md` line about resume (added) — read it in context; it's in the diff and looks accurate against the code I read. One claim to verify: "A resumed run whose supervisor died reads `orphaned`." ✓ proven by my manual run. "The resume leaves the old exit files in place, and the next stop replaces them." — that's engine behavior; plausible, not verified but consistent.

Also the SKILL.md — does it describe stall defaults or the hermetic profile anywhere that now contradicts? Let me grep SKILL.md for hermetic/stall/180.

</details>
**toolCall bash** id=`call_10052db8e36a4303ba474e79`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && grep -n \"hermetic\\|stall\\|180\\|600\" oh-dispatch/SKILL.md | head -15"
}
```
**toolCall bash** id=`call_c1f318e2d58e47d59397b95e`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && git log --format=\"%H %an <%ae>\" arch/deepening..HEAD | sort -k2 | uniq -c -f1 | head && git log arch/deepening..HEAD --format=\"%B\" | grep -i \"co-authored\\|generated\" ; echo \"authorship grep exit: $?\""
}
```

#### [103] line 103 · message · toolResult · 2026-10-02T02:23:19.664Z
(no output)
**toolResult** for `call_10052db8e36a4303ba474e79` (bash)

#### [104] line 104 · message · toolResult · 2026-10-02T02:23:19.665Z
     11 01b5719c66f87fae70d56af8b0369d66f3f49a23 Example Operator <operator@example.com>
authorship grep exit: 1
**toolResult** for `call_c1f318e2d58e47d59397b95e` (bash)

#### [105] line 105 · message · assistant · 2026-10-02T02:24:06.102Z
<details><summary>thinking</summary>

SKILL.md has no claims about stall defaults or hermetic — no contradiction there. Clean authorship: all 11 commits by Example Operator, no Co-Authored-By, no generated-with footers. ✓

Let me also double-check the one remaining subtle code question: the `stall_for` behavior when the plan argument is given as 0 or the lane has no stall cap. And the `host` lane: `lane_info("host").has(CAP_STALL)` is False (host not in the CAP_STALL sets? line 59-67 showed lanes with CAP_STALL; let me verify host's capability set). Test 47 covers it. Fine.

One more possible issue: `rollcall.py` docstring says "`stall_timeout_s` (replaces the per-lane `STALL_S` table; codex gets 600 s, `pi`, `claude` and `dsh` get 180 s, and `host` takes no stall limit)". ✓ matches STALL_S.

And `Spec.stall` docstring: "the caller's override; None takes STALL_S" ✓.

Now — the `max_iter` default change from 15 to 30: does anything else depend on the default 15? The `judge_spec` uses `spec.max_iter` → 30. Test says judge ≥ 30 ✓.

What about `report lane` in the REPORT template: `{"lane": "{lane}", ...}` — for the consolidate step, `{lane}` is spec.consolidator. ✓ (test asserts consolidate: claude).

Now the last checklist item I haven't fully verified myself: "a stall limit that a lane's normal silence can still trip (codex reasoning, a long foreground command)". Codex 600 s. But what about **dsh's 180 s** with "dsh spends about 30 s shutting down its MCP fleet" — pre-existing, log mtime moves per event. The live relay dsh passed. **pi 180 s**: pi emits events per action; a single long-running bash command inside pi (say a 4-minute build) would emit nothing... but that's pre-existing matrix-passing behavior, unchanged by m7. **claude 180 s**: claude stream-json emits per event; long tool runs emit results... pre-existing. Not m7 regressions.

One more: **the host lane takes no stall limit** — `stall_for` returns None for host; `_step` passes `stall_timeout_s=spec.stall_for(lane)`. For host, None → Step without stall. ✓ matches lanes/README ("host has no stall row").

Now let me reconsider the two findings and their severity, and decide the verdict.

**Finding A (lanes.md hermetic table).** Evidence is strong (binary disassembly of the very CLI the lane launches, version 2.1.281 — same as the runner comment "Measured 2026-10-01 (2.1.281)"). The env var removes ALL CLAUDE.md sources: Managed, User (via `iet`), Project `CLAUDE.md`, `.claude/CLAUDE.md`, `CLAUDE.local.md`, `.claude/rules` (via `gCn` and `aet`). The doc says hermetic removes "the user's instruction files" and keeps "the project's own `.claude` files". The Keeps claim is false for `.claude/CLAUDE.md` and `.claude/rules`; the Removes claim understates. Charter bar #6: "no statement the code contradicts". This is exactly such a statement, in the very sentence scope item 2 required. 

Counter-consideration: could "the project's own `.claude` files" be meant as "project settings"? The Removes column already covers "the user's settings (--setting-sources project,local)" and the keeps column "the project's own `.claude` files" would naturally mean `.claude/settings.json` etc. But a fair reading includes instruction files, and the Removes column's "(CLAUDE_CODE_DISABLE_CLAUDE_MDS=1)" attribution to "the user's instruction files" is wrong either way — the flag's effect is broader than "the user's". A developer writing a repo-level CLAUDE.md for their roll-call repo, reading this table, would believe hermetic workers see it. They don't. That's a wrong fact in shipped prose.

**Finding B (README suite figure).** 902 vs measured 911; also the shard seconds (328.9/285.4/258.4) vs my (340.9/316.6/291.2) — times vary with load, but the count is objective. Spec scope item 5: "update the suite figure from a shard run on this branch". The figure was from a shard run mid-branch; the branch then gained 9 tests. The shipped README misstates the suite it ships with. Also "873 s" total no longer matches (my run: 948.7 s, but that's load-dependent — weaker evidence; the count is the hard evidence).

Are either of these "would ship a defect"? Under this campaign's rules, prose is code; a false measured figure and a false capability claim are defects. Both are trivially fixable (one line each), but my job as adversarial reviewer is to report, and the gate rule says BLOCKED when any finding would ship a defect.

Hmm, let me think hard about whether Finding A is really solid. Let me re-verify by checking the behavior claim more carefully — maybe `iu().length>0` (explicitlyRequested) matters: `cO(){return Boolean(a.CLAUDE_CODE_DISABLE_CLAUDE_MDS||zr("claudeMd",{explicitlyRequested:iu().length>0}))}`. cO seems to be "claudeMd disabled?" for some other purpose. But `iet` and `gCn` and `aet` each begin with `if(a.CLAUDE_CODE_DISABLE_CLAUDE_MDS)return[]`. These are the memory loaders. Unambiguous.

But wait — could there be *another* loader for project CLAUDE.md that doesn't check the env var? `gCn` loads project CLAUDE.md (Gu(e,"CLAUDE.md") with type "Project"). `iet` loads Managed+User. `aet` loads .claude/rules with conditional... These are all guarded. There might be an "explicitly requested" path (`@CLAUDE.md` file reads) that bypasses — that's the agent reading a file with its own tool, not harness injection. Fine — the harness-level loading is fully disabled. Also `zr("claudeMd", ...)`: `zr(e,s){if(Cr()&&!l[e])return!0;if(uo()&&!s?.explicitlyRequested)return t[e];return!1}` — some settings gate; not relevant.

Additionally the live evidence corroborates the *user* instruction files being dropped (mcp_servers: [] — those server names came from ~/.claude/CLAUDE.md). It can't corroborate project files (the scratch repo has no CLAUDE.md). So the binary reading stands.

Severity ranking: Finding A (prose contradicts the CLI's actual behavior, in the sentence the spec explicitly required) > Finding B (stale measured figure, off by 9 tests).

Is there anything else? Let me do a final sweep for things I may have missed:

1. Exit criteria: 1 ✓ (6 tests, 5 lanes), 2 ✓ (10), 3 ✓ (5), 4 ✓ (ROLLCALL PASS: 3 of 3), 5 ✓ (no match). All five pass.

2. Full suite: three shards, 911 tests, 0 failures, 1 skip (opt-in e2e presumably). ✓ gate will pass.

3. Scope: only oh-dispatch/** changed ✓ (diffstat), tree clean ✓, no push.

4. Host cell numbers: max_iterations=30, llm_calls=8. ✓ comfortable.

5. Report-lane: verified in gate code + tests + live (all reports named their own lane).

6. dsh bucket: port verified against JS source; live run on tmp. path passed; miss error names bucket.

7. Resumed run: manually verified status/watch/snapshot.

8. Tests passing with and without fix: none of the defect files wholly passes on base (all red). Individual pinning tests inside some files pass on base (45's flag test, 46's "names none" test) but each file's core defect assertion is red. Acceptable per the rules.

9. Prose contradictions: Finding A. Also check "measured 2026-09-30 ... 25 CLAUDE* names" comment moved to proc.py — consistent with charter's "The desktop session exports 26 CLAUDE* names"?? The charter says "The desktop session exports 26 `CLAUDE*` names." The comment says 25 CLAUDE* names plus ANTHROPIC_BASE_URL. Hmm — charter (why-section): "The desktop session exports 26 CLAUDE* names." Comment: "Measured 2026-09-30 from a desktop-app session: 25 CLAUDE* names plus an ANTHROPIC_BASE_URL". 26 vs 25 — this discrepancy predates m7 (the comment was in seat_runner before, moved verbatim). Not introduced by this milestone; the charter's own count may include CLAUDECODE or not. Not a new finding; skip (or mention as a nit? It's pre-existing prose moved, not changed. I'll skip it).

10. lanes.md dsh section: "The key follows dsh's own `projectKey`..." ✓ matches. "When no session is found, the error names the bucket the runner looked in." ✓ code does that.

11. campaign.md `.watch.<name>.json` ✓ matches code.

12. ohflow.md resume paragraph ✓ verified by my manual scenario.

13. The README stall sentence: "The stall limit defaults per lane: 600 s for codex, 180 s for pi, claude and dsh. The host lane takes no stall limit. The argument replaces that table for every lane that takes a limit." ✓ matches code.

14. gates.py registered description: appends "; the report names lane X" — fine.

15. One more thing to check: `run_tests.py -k parent_session` "ran ≥ 5 tests, one per lane" — 6 tests include all five lanes ✓.

16. Also verify nothing in the diff touches files outside oh-dispatch/ ✓ (diffstat).

17. Check the commit for "dsh docstring escape fixed" (caed658) — the fake_dsh docstring? Let me glance at what that fixed — "dsh docstring escape fixed". In fake_dsh.py the docstring `/\\:` etc. Fine.

Now, the verdict. The gate instruction: "BLOCKED when any exit criterion fails or any finding would ship a defect." All exit criteria pass. Findings A and B are prose defects. Would they "ship a defect"? Under this campaign's explicit doctrine ("prose is code... no statement the code contradicts"), yes: Finding A is a statement the launched CLI contradicts, in the exact sentence the spec scoped; Finding B is a measured figure that does not match a shard run on this branch (my shard run), which the spec explicitly demanded.

I keep going back and forth on whether these rise to BLOCKED. Let me apply the adversarial-reviewer standard the brief sets: it lists exactly these categories to hunt — "README figures that do not match the measured matrix.json or a shard run" (Finding B is precisely this category!) and "prose that now contradicts the code" (Finding A is precisely this category). The brief's author put these categories on the hunt list, which signals they are the kind of finding that matters. The verdict rule: "BLOCKED when ... any finding would ship a defect." A README figure that misstates the suite and a lanes.md row that misstates hermetic's contract are defects in shipped text under this campaign's bar.

Both are one-line fixes; a retry attempt (attempt 4) can fix them in minutes. Blocking is cheap and correct here. 

Hmm, but let me sanity-check Finding B once more. Is it possible run_tests.py counts differently with skips? My discovery count: 911. Shard runs: 304+304+303 = 911 tests run, 1 skipped (skipped tests count in testsRun). So the suite on this branch is 911. README says 902. Definitively stale.

And Finding A — one more angle: does the *spec itself* say what the fix should be? "Find the Claude CLI's own mechanism ... keep the login working, and say in references/lanes.md, for each lane, what hermetic removes and what it keeps." The mechanism found (env var) is real and works (live proof). The *sentence* about what it removes/keeps is partially wrong. So the spec's deliverable contains a false statement. BLOCKED-able.

Wait — actually, let me re-read the lanes.md row once more to be scrupulously fair:

"| `claude` | the user's instruction files (`CLAUDE_CODE_DISABLE_CLAUDE_MDS=1`), the user's settings (`--setting-sources project,local`), every built-in tool the plan does not name (`--tools`), every MCP server the plan does not name (`--strict-mcp-config`) | the OAuth login, the plan's `--mcp-config` servers, the project's own `.claude` files |"

Also check the table intro: "A hermetic worker starts from nothing the seat owns, except its login."

The claim "the project's own `.claude` files" in Keeps: with the env var set, `.claude/settings.json` (project settings) DO load (setting-sources includes project), `.claude/settings.local.json` (local) load, but `.claude/CLAUDE.md` and `.claude/rules/*` do NOT. So the Keeps cell is half-true; the Removes cell's parenthetical pins the env var to "the user's instruction files" when it removes all instruction files. The most defensible reading of the row as written is factually wrong about project instruction files.

Additionally, is there an argument that this is *intended*? The hermetic profile of the *roll call* — surface check requires the worker to report only announced tools; project CLAUDE.md could inject MCP server names → gate fails. Removing project CLAUDE.md is *desirable* for hermeticity, and the code does the right thing; only the doc misdescribes it. So the fix is doc-side.

Decision: BLOCKED, with two findings, both prose, both one-line fixes, everything else green. Also report the minor pre-existing 25-vs-26 nit? The charter says 26 CLAUDE* names; proc.py comment says 25. The comment was moved from seat_runner (m5-era, presumably measured then). The charter's "26" is the operator's spec-side count (maybe including CLAUDECODE, which the regex also strips: `CLAUDE|CLAUDECODE$` — CLAUDECODE starts with CLAUDE so already matched). Eh — 25 CLAUDE* + CLAUDECODE = 26? CLAUDECODE starts with "CLAUDE" so it IS a CLAUDE* name... The comment says "25 CLAUDE* names plus an ANTHROPIC_BASE_URL". The charter says 26 CLAUDE* names. One of them counts differently. This is pre-existing (the comment predates m7 verbatim), so not a milestone finding; I'll mention it as a nit without weight.

Let me also double check there are no untracked files in my worktree (I created logs outside; the run dirs are in temp). git status --porcelain must print nothing for the gate — I changed nothing. Let me verify, and also clean up my sleeper process (already killed) and temp dirs (leave them; they're outside the worktree).

One more possible check: criterion 4's matrix.json exists in the tmp out dir with 3 cells PASS — good for the record.

Also — the review brief asks: "in your criterion-4 run, read each step's llm_calls (or turn count) in result.json against max_iterations in its spec.json, and report the host cell's two numbers". Host cell: max_iterations=30, llm_calls=8. Done.

Final sweep of numbers for my report:
- Tests before (trunk arch/deepening): let me get the base count for the record — discovery on the redcheck export.

</details>
Everything on the checklist is now verified. Let me capture the base test count for the record and confirm the worktree is untouched:
**toolCall bash** id=`call_128fbe80637e4a7da1db1660`

```json
{
 "command": "cd \"$TEMP/m7review/redcheck\" && python -c \"\nimport sys, unittest\nfrom pathlib import Path\nHERE = Path('oh-dispatch/tests'); SKILL = HERE.parent; ROOT = SKILL/'scripts'\nfor p in (str(SKILL), str(ROOT), str(HERE)): sys.path.insert(0, p)\nloader = unittest.TestLoader()\nsuite = loader.discover(start_dir=str(HERE), pattern='test_*.py', top_level_dir=str(SKILL))\ndef flat(s):\n    for i in s:\n        if isinstance(i, unittest.TestSuite): yield from flat(i)\n        else: yield i\nprint('base (arch/deepening) test count:', len(list(flat(suite))))\n\""
}
```
**toolCall bash** id=`call_42f041a5195945bb8f1a24f9`

```json
{
 "command": "cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && git status --porcelain; echo \"porcelain exit: $? (empty above = clean)\"; git log --oneline arch/deepening..HEAD | wc -l"
}
```

#### [106] line 106 · message · toolResult · 2026-10-02T02:24:11.327Z
base (arch/deepening) test count: 911
**toolResult** for `call_128fbe80637e4a7da1db1660` (bash)

#### [107] line 107 · message · toolResult · 2026-10-02T02:24:11.327Z
porcelain exit: 0 (empty above = clean)
11
**toolResult** for `call_42f041a5195945bb8f1a24f9` (bash)

#### [108] line 108 · message · assistant · 2026-10-02T02:24:17.726Z
<details><summary>thinking</summary>

Wait — the redcheck export says 911 too? That's because I *copied the new test files into it* for the red-first check. The base count needs a clean export. Let me recount from a pristine archive.

</details>
The redcheck dir was contaminated with the copied test files — recounting from a pristine base export:
**toolCall bash** id=`call_926f38c273d24b9788d7dbda`

```json
{
 "command": "R=\"$TEMP/m7review/pristine\" && rm -rf \"$R\" && mkdir -p \"$R\" && cd \"C:/Users/<user>/dev/_wt/oh-dispatch-deepening/m7-smoke-fixes\" && git archive arch/deepening | tar -x -C \"$R\" && cd \"$R\" && python -c \"\nimport sys, unittest\nfrom pathlib import Path\nHERE = Path('oh-dispatch/tests'); SKILL = HERE.parent; ROOT = SKILL/'scripts'\nfor p in (str(SKILL), str(ROOT), str(HERE)): sys.path.insert(0, p)\nloader = unittest.TestLoader()\nsuite = loader.discover(start_dir=str(HERE), pattern='test_*.py', top_level_dir=str(SKILL))\ndef flat(s):\n    for i in s:\n        if isinstance(i, unittest.TestSuite): yield from flat(i)\n        else: yield i\nprint('base (arch/deepening) test count:', len(list(flat(suite))))\n\" && rm -rf \"$R\""
}
```

#### [109] line 109 · message · toolResult · 2026-10-02T02:24:21.812Z
base (arch/deepening) test count: 879
**toolResult** for `call_926f38c273d24b9788d7dbda` (bash)

#### [110] line 110 · message · assistant · 2026-10-02T02:24:46.227Z
<details><summary>thinking</summary>

Base: 879 tests. Branch: 911. Diff: +32 (matches the 32 new tests I counted in the eight new files). The old README (on trunk) said 875 — close to 879 (trunk README may have been 4 off already, or discovery-count nuance; not my milestone's concern). Current README on branch says 902, actual 911.

Now I have everything. Let me clean up my temp artifacts? They're outside the worktree, harmless. The sleeper process was killed.

Summary of exit criteria results:
1. `-k parent_session`: exit 0, 6 tests (≥5, one per lane: claude, codex, dsh, pi, host) ✓ PASS
2. `-k hermetic`: exit 0, 10 tests (≥2) ✓ PASS
3. `-k report_lane`: exit 0, 5 tests (≥1) ✓ PASS
4. Live rollcall with CLAUDECODE=1, CLAUDE_CODE_ENTRYPOINT=claude-desktop, CLAUDE_AGENT_SDK_VERSION=0.3.284, --out $(mktemp -d): `ROLLCALL PASS: 3 of 3 cells`, exit 0 ✓ PASS. Host worker reported OpenHands with OpenHands tools; hermetic claude reported no MCP servers; relay passed with codex unstalled (relay 6m34s); dsh found its session under the tmp. path.
5. grep "not measured yet": no match ✓ PASS

Full suite in 3 shards: 304+304+303 = 911 tests, 0 failures, 0 errors, 1 skip; 340.9 + 316.6 + 291.2 s.

Host cell: max_iterations=30, llm_calls=8.

Red-first: all eight defect test files fail against arch/deepening (44: 5F+1E; 45: 1F; 46: 4E; 47: 1F+1E; 48: 11F; 49: 1F; 50: 4F; 51: 3F).

Findings, most severe first:

**F1 — lanes.md:67 hermetic claude row misstates the flag's reach.** `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` disables every CLAUDE.md/rule source, including the project's own. Binary evidence (claude.exe 2.1.281, offsets 202789876/205608694): `iet` returns [] before Managed/User memory; `gCn` returns [] before Project `CLAUDE.md`, `.claude/CLAUDE.md`, `CLAUDE.local.md` and `.claude/rules`; `aet` likewise. The doc's Removes column pins the variable to "the user's instruction files" and the Keeps column claims "the project's own `.claude` files" — true only of project/local *settings*, false of project instruction files. Charter bar #6 (no statement the code contradicts); spec scope item 2 explicitly required this sentence to be right.

**F2 — README.md:29/31 suite figure stale.** "902 tests, 873 s (328.9/285.4/258.4 s)" was measured at commit 01b5719; commits 470cf16 and f4a6063 added 9 tests after it. Branch runs 911 tests (my shards: 304/304/303, 340.9/316.6/291.2 s). Spec scope item 5: "update the suite figure from a shard run on this branch."

Minor nit (pre-existing, no weight): proc.py comment says "25 CLAUDE* names" while the charter says 26 — the comment was moved verbatim from seat_runner, predates m7.

Both findings are prose defects; prose is code in this campaign; the gate rule says BLOCKED when any finding would ship a defect. Verdict: BLOCKED (fixable in two one-line edits; everything else — all five exit criteria, the suite, the live matrix, red-first, the dsh port, the resume logic — is green).

Let me write the final report with file:line references and evidence commands.

</details>
The review is complete. Everything measured, everything run. Final report:

---

## Review of m7-smoke-fixes (11 commits, `18f4bcd..f4a6063`, +795/−75, `oh-dispatch/` only, clean tree, clean authorship)

### Exit criteria, run by me

| # | Result |
|---|---|
| 1 | `-k parent_session` → exit 0, **6 tests**, one per lane (claude, codex, dsh, pi, host) — **PASS** |
| 2 | `-k hermetic` → exit 0, **10 tests** — **PASS** |
| 3 | `-k report_lane` → exit 0, **5 tests** — **PASS** |
| 4 | With `CLAUDECODE=1`, `CLAUDE_CODE_ENTRYPOINT=claude-desktop`, `CLAUDE_AGENT_SDK_VERSION=0.3.284` exported, `--out "$(mktemp -d)"` from `oh-dispatch/scripts`: **`ROLLCALL PASS: 3 of 3 cells`**, exit 0 (host 1m47s, hermetic claude 0m34s, relay 6m34s) — **PASS** |
| 5 | `grep -n "not measured yet" oh-dispatch/README.md` → no match — **PASS** |

**Full suite, three shards, foreground, one at a time:** 304 + 304 + 303 = **911 tests, 0 failures, 0 errors, 1 opt-in skip** (340.9 s / 316.6 s / 291.2 s). Base `arch/deepening` count: 879 → +32, matching the eight new defect files.

### What I verified beyond the criteria

- **Env rule.** Every worker launch goes through `proc.worker_env()` (host: `worker.py:154`; pi: `pi_runner.py:163`; claude/codex/dsh via `seat_env` → `seat_runner.py:41`; the CLI runner processes via `cli_lane.py:251`). Remaining raw `os.environ` children (`cli.py:342/787` detached supervisors, `campaign.py:297` git, `exec.py:81` in-worker caps) launch no worker. Live proof: with the desktop vars exported, the host worker reported `OpenHands (version unknown)` with OpenHands tools — no trace of Claude Code.
- **dsh bucket.** The port in `dsh_runner.session_bucket` matches dsh 0.1.5-rc.2's `projectKey` line for line (UTF-16 code units, `/ \ :` runs → one `-`, `[A-Za-z0-9._-]` kept, `~XXXX` escape, leading `-` stripped, `root`, 251 cut, `--` wrap), checked against `.../dsh-session-persistence-jsonl/lib/index.js` offsets 874–893. The criterion-4 run on `tmp.yYeyfLXeNB` found its dsh session.
- **Resumed run.** Built by hand in a temp dir (journal work events after `run_finished`, live sleeper as supervisor, `exit.json` aged older than the journal): `ohflow status` → `running`, `watch` → `running`, snapshot → `running`/`finished: None`; after killing the supervisor both verbs said `orphaned` and never printed the old verdict.
- **Budget.** Every criterion-4 step: `max_iterations=30`, `llm_calls` 1–9. **Host cell: max_iterations 30, llm_calls 8.**
- **Red-first.** All eight defect files fail against a pristine `arch/deepening` export (44: 5F+1E, 45: 1F, 46: 4E, 47: 1F+1E, 48: 11F, 49: 1F, 50: 4F, 51: 3F).
- **README wall times.** Recomputed from the measured `matrix.json`: full 1942.7 s (3/15 failed), quick subset 1466.5 s (2/10 failed) — exactly what the README says.

### Findings, most severe first

1. **`references/lanes.md:67` — the hermetic claude row misstates what `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` removes and keeps.** The row says the variable removes "the user's instruction files" and keeps "the project's own `.claude` files". In the installed CLI (2.1.281, the version the runner documents) the variable short-circuits **every** instruction-file source: `iet` returns `[]` before Managed/User memory, and `gCn` returns `[]` before the Project `CLAUDE.md`, `.claude/CLAUDE.md`, `CLAUDE.local.md` and `.claude/rules` branches (`grep -aob CLAUDE_CODE_DISABLE_CLAUDE_MDS …/claude.exe` → offsets 202789876, 205608694; `dd`-extracted context shows `if(a.CLAUDE_CODE_DISABLE_CLAUDE_MDS)return[]` ahead of each loader). Only project/local *settings* survive (`--setting-sources project,local`). A developer reading the row would believe a hermetic worker still reads the repo's own `CLAUDE.md`; it does not. Charter bar 6 ("no statement the code contradicts"); spec scope item 2 required precisely this sentence.
2. **`README.md:29,31` — the suite figure is stale for this branch.** "902 tests, 873 s … (328.9 s, 285.4 s and 258.4 s on 2026-10-02)" was measured at `01b5719`; `470cf16` and `f4a6063` added 9 tests after it. My shard run: 911 tests. Spec scope item 5: "update the suite figure from a shard run on this branch. One place each."

Minor, pre-existing, no weight: `proc.py:18` comment says "25 `CLAUDE*` names" where the charter says 26 — moved verbatim from `seat_runner`, not introduced here.

Both findings are prose defects, each a one-line fix; under this campaign's "prose is code" bar they ship defects as they stand. Everything else — all five exit criteria, the full suite, the live three-cell matrix under the launching session's variables, the dsh port, the resume logic, red-first, authorship — is green.

VERDICT: BLOCKED

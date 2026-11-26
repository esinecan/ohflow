# Capped loop: build, operate and fix

A capped loop runs one or more phases of a workflow again and again, one loop round at a time,
until a stop command exits 0. After each loop round a progress command prints a number. The loop
also ends when two loop rounds in a row bring no improvement, or when it reaches its cap. Its
behaviour is the 32 scenarios in `features/`. This file says how the loop gets built, how an
orchestrator agent uses it, and how a failure gets fixed.

## The notation

The features are written in agentic Gherkin, which is Gherkin written from the agent's seat. "I"
is an agent: the orchestrator agent, or the agent in a loop round. The feature line names which.
The system under spec is everything around the agent: the engine, the files, the commands, the
gates and the run log. The model's reasoning and the person are never the subject of a step,
because nobody can spec either one.

- **Given** states what the agent can read before the step. **When** is one event that reaches
  the agent, or one call it makes. **Then** is what the engine or the world does in answer, stated
  so that a test can check it.
- **Each scenario carries one tag, and the tag says who makes the scenario true.**
  - `@gate:<reason>` means the engine enforces it whatever the agent does. The reason is
    `irreversible`, `untrusted-input`, `decay` or `repetition`. A test proves a gate with a fake
    agent or a fake workflow module that tries the forbidden thing.
  - `@flow` is engine plumbing, and a unit test proves it with fakes.
  - `@brief` means the engine only gives the agent a fact. Nothing enforces what the agent does
    with it, so the run notes of the live hand-try measure it.

Most gates here carry `repetition`, because a loop is unattended work that repeats. A check that
one loop round can skip will be skipped on some loop round. The refusal of a loop in an empirical
procedure carries `irreversible`, because nothing can repair an experiment that stopped on its own
result.

## The design

**The loop is copied out before the run starts, and the engine only ends it early.**
`patterns.loop(...)` copies the loop's phases once per loop round, up to the cap. Every phase
name and step id gets the suffix `.r01`, `.r02` and so on. Each loop round is then an ordinary
phase with its own coordinate. So `workflow.json`, the dashboard, `summary.json`, the judge packet,
the cache and the token count of a resume all see every loop round without a change. Phases added
at run time would break all of these. A coordinate is `NN.phase/NN.step`, and an inserted phase
shifts every later coordinate and the hashed "Phase N of M" line. Every reader of a run also lists
steps from `workflow.json` only. So the loop needs no intervention checkpoint and no change to
future work, and it does not wait on the item "Replanning during a run" in `docs/todo.md`.

**A loop is declared in one call.**

```python
phases, green = loop(
    "green",
    phases=(fix,),
    stop_cmd="bash checks/green.sh",
    progress_cmd="bash checks/failing.sh",
    progress_goal="down",
    check_paths=("checks/**",),
    max_rounds=4,
)
workflow = Workflow(..., phases=(*before, *phases, *after), loops=(green,), kind="delivery")
```

| Field | What it holds | Default |
|---|---|---|
| `phases` | the phases of one loop round | required |
| `stop_cmd` | a command whose exit 0 ends the loop | required |
| `progress_cmd` | a command whose last line of output is the progress number | required |
| `progress_goal` | `down` or `up`, the direction that counts as better | required |
| `check_paths` | the files the two commands read, which no loop round may change | required |
| `max_rounds` | the cap, at least 1 | required |
| `stall_rounds` | how many loop rounds in a row without improvement end the loop | 2 |
| `check_timeout_s` | the time limit of each check command | 600 |

**The copy wires each loop round to the one before it.** Each step of loop round k names its own
step of loop round k−1 in `depends_on`. It also names it in `consumes` when that step writes a
handover. All loop rounds work in one worktree, so a loop round starts at the last commit of the
one before. The gate of each agent step in the loop gains `paths_untouched` over `check_paths`.
The loop adds no `Step` field: the loop round lives in the step id and in the new `Phase.loop` and
`Phase.loop_round`.

**The engine decides after the last phase of each loop round settles.** A loop can hold several
phases, so the decision sits in the phase loop of `Engine.run()` in `scripts/ohflow/engine.py`,
not in `_run_phase`.

1. Before loop round 1, the engine runs both commands at the loop's base. The result is loop
   round 0, the baseline.
2. After a loop round, it runs the stop command in the loop's worktree. Exit 0 gives `done`.
3. Otherwise it runs the progress command and reads its last line as a number. No number, or a
   command that runs past `check_timeout_s`, gives `error`.
4. A number better than the best so far, in the direction of `progress_goal`, sets the stall count
   to 0. Any other number adds 1. A stall count of `stall_rounds` gives `stalled`.
5. Otherwise the last loop round gives `capped`, and every other loop round gives `continue`.

Each decision is one `loop_decided` event in the run log. Its payload holds `loop`, `round`,
`stop_exit`, `progress`, `best`, `stall`, `decision` and `reason`. The two outputs go to
`loops/<loop>/rNN/stop.log` and `loops/<loop>/rNN/progress.log` in the run directory.

**`done` skips the rest of the loop, and every other end fails the run.** On `done` the engine
records every step of the remaining loop rounds `skipped`, with the reason "loop <id> ended done
at loop round N". The run goes on with the first phase after the loop. On `stalled`, `capped` or
`error` the engine records every later step `skipped` with its reason and sets the run's abort, so
the run finishes `failed`. A loop round whose own phase fails, or that holds a killed step, gets no
decision. The rules that apply to any failed or paused phase apply to it.

**A loop requires the workflow to name its objective kind.** `Workflow.kind` is a new field.
`KINDS` moves from `construct.py` to `workflow.py`, and `construct` writes the bundle's kind into
each milestone workflow. `validate` refuses a loop when the workflow's kind is empty or
`empirical`.

**The term is "loop round".** `CONTEXT.md` reserves the bare word *round* for a milestone round,
so every text says *loop round*. The glossary gains entries for loop, loop round, loop decision,
stop command, progress command, progress trail and stall count. The decisions are `continue`,
`done`, `stalled`, `capped` and `error`.

**A resume reads the loop's past from the run log.** Finished loop rounds keep their coordinates,
so they come back `cached`. The engine decides a cached loop round again from the numbers in its
`loop_decided` event and runs no command for it, so a raised `max_rounds` continues a capped loop.
The stall count restarts at every resume, and the count of loop rounds does not. A loop that ended
`done` stays done while its declaration is unchanged. A changed `stop_cmd` or `progress_cmd`
measures again at the head of the loop's worktree and starts a new baseline.

## Build

**The build is a campaign that `ohflow construct` writes, and its supervisor runs from a run
clone.** The campaign changes ohflow itself. A broken milestone must not break the campaign that
runs it, so the supervisor runs from a clone of this checkout at the commit before the build. The
milestones land on the integration branch `campaign/capped-loop`, and `main` moves only after the
last PASS. The bundle lives in a campaign folder outside this repository, such as
`~/workflows/capped-loop/`. Its `bundle.md` reads `kind: delivery`. Each milestone spec reads
`pattern: implement-and-review` and names this file and its feature files as its spec. `ohflow
campaign estimate` prices the campaign before `campaign run --hold --detach`.

| Milestone | Code | Features | Hand-try |
|---|---|---|---|
| `01-declare` | `Loop`, `Workflow.loops`, `Workflow.kind`, `Phase.loop` and `Phase.loop_round` in `workflow.py`; `loop()` in `patterns.py`; `_loop_errors` beside `_unit_errors` in `validate`; `KINDS` moved, and `construct` writing the kind; the loop line of `validate` | `01-declaring` | `ohflow validate` on an example module, once clean and once for each refusal |
| `02-decide` | the decision in `Engine.run()`; `loop_decided` in `EVENTS` in `run_log.py`; the check outputs under `loops/`; the skip reasons; the abort after a short end; the `paths_untouched` gate in the copy; a "Loop" section in the position block in `coords.py` | `02-deciding`, `03-working-in-a-loop-round` | three loops of command steps in a scratch repository, which spend no tokens: one ends `done` at loop round 3, one `stalled` and one `capped` |
| `03-resume-and-readers` | the resume rules and the killed loop round; `live.py` for `watch`; `status`; one dashboard row for the skipped loop rounds; `summary.json` and the exit report; the judge packet in `campaign.py`; `estimate`; `pilot.py` | `04-watching-and-pricing`, `05-resuming` | resume the capped command loop with a raised cap; one look at the dashboard in a browser, by a subagent |
| `04-docs-and-live` | a "Loop" row and section in `references/workflow-patterns.md`; a "Loops" section in `references/ohflow.md`; the decision line in `references/monitor-a-run.md`; the route row in `SKILL.md`; an example loop workflow; the item in `docs/todo.md` closed | none new | one live loop on `pi`, described below |

**Each `@flow` and `@gate` scenario becomes one test, and a script keeps the two in step.** The
tests are `tests/test_loop_NN_<claim>.py` on `unittest`. They use the fakes of `tests/support.py`:
`FakeHarnessExecutor` and `AgentScript` for agent steps. The check commands are short scripts in a
`git_repo`, run by real Git Bash. A test method's docstring opens with its scenario's name. A
`@gate` test uses a fake agent or a fake workflow module that does the forbidden thing. The fake
ends with "the loop can stop" while the stop command fails, edits a check file, or declares a loop
without a cap. The script `docs/loop/check_scenarios.py`, which milestone `01-declare` writes,
reads `docs/loop/features/` and must exit 1 for any `@flow` or `@gate` scenario that lacks a test
with that docstring. Each milestone's acceptance checks run it for that milestone's feature files.
A `@brief` scenario gets its evidence from the live loop's run notes instead of a unit test, because
only a real model shows what an agent does with a fact.

**Each milestone keeps the docs check green.** A new dataclass field, event or flag changes the
vocabulary surface. So the milestone adds its `CONTEXT.md` entries, runs `python
docs/glossary_sync.py --write` and `--accept-surface`, and passes `python tests/check_docs.py`.

**The live loop is the last hand-try.** A scratch repository holds a small module with six failing
tests. The loop's one agent step runs on `pi` with a cheap model and the brief "fix at most two
failing tests, commit each fix, then write your handover". `stop_cmd` runs the tests,
`progress_cmd` prints the number of failures, and `max_rounds` is 5. The expected end is `done` by
loop round 3. For each loop round, the run notes record what the two `@brief` scenarios ask:
whether the agent's commits worked on a failure that the quoted stop output names, and whether it
repeated an approach that the handover before it says failed.

## Operate

**Choose a loop when the same kind of step repeats an unknown number of times, a command can say
"done", and a number can say "closer".** Failing tests, lint errors, the open findings of a sweep
and the open questions in a research file fit. A relay fits steps that differ from each other.
Units fit items that are known before the run.

**Write the two check commands first, and commit them under `check_paths`.** Both run in the
loop's worktree with `OHFLOW_RUN_DIR` set. The stop command exits 0 only when the work is done. The
progress command prints the number as its last line, with nothing after it.

**Give each loop round a bounded share of the work.** A brief such as "fix at most two failing
tests" keeps a loop round inside its execution timeout, and it makes the number move in every loop
round. A loop round that tries to finish everything turns the loop into one long step.

**Guard the number against the cheap way to move it.** A count of failing tests also falls when a
test is deleted. So the gate of the loop round carries `test_counts` with a minimum, or
`paths_untouched` over the tests.

**Size the cap from the price of one loop round.** `ohflow estimate` prints the price of one loop
round and the price at the cap. The bill names the price at the cap as the most the loop can spend,
beside the spending cap. The run's `token_budget` stays the hard stop.

**Judge the loop at each decision line.** `ohflow watch` prints one line for each `loop_decided`.
In a delivery, the orchestrator agent may kill the running loop round's step when the trail has
stopped paying before the stall rule fires. The run then pauses, and a resume with a changed brief
or a lower cap continues it.

**In a campaign the judge reads the trail.** The judge packet lists every loop's decisions. A
REVISE resumes the run directory, so the finished loop rounds come back `cached`.

## Fix

| What you see | What it means | What to do |
|---|---|---|
| `stalled`, although each loop round committed real fixes | The progress command does not measure the work that the loop rounds do | Fix the progress command, commit it under `check_paths`, and resume. The engine measures a new baseline. |
| `capped`, with a number that improved in every loop round | The cap was too low for the work | Raise `max_rounds` and resume. The finished loop rounds stay `cached`. |
| `done` at loop round 0 | The stop command passed before any work | The stop command tests nothing that the loop changes. Fix it and start a new run. |
| `error` that quotes the last line of output | The progress command printed text after its number, or printed no number | Make the number the last line, and resume. |
| `error` "stop command timed out" | A check command takes longer than `check_timeout_s` | Raise `check_timeout_s`, or make the check cheaper, for example by running only the tests the loop works on. |
| A loop round fails `paths_untouched` on a check file | The agent changed a check file | Read its diff and its handover. State in the brief that the check files are fixed and why, then resume. |
| The same number after every loop round, although the loop rounds commit | The loop rounds undo each other's work | Read two handovers side by side. The brief or the bounded share must name what stays done. |
| A loop test fails after a code change | The code broke the behaviour that the scenario names | Fix the code until the test, `docs/loop/check_scenarios.py` and `python tests/check_docs.py` pass. |

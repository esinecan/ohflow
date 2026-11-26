# Brief templates

Three briefs drive the implement-review loop. Copy the template, fill every
`<slot>`, delete nothing else.

Three rules apply to every acceptance item in every brief.

- **Command-shaped.** An item is a command the agent can run plus the exact
  output that means pass. "Tests pass" is a slot, `npm test` exits 0 with every
  test passing is an item.
- **Hold the field constant.** A check varies the one property under test and
  nothing else. The first run's rarity check compared a name-field hit with a
  body-field hit and measured field weight instead of rarity; the reviewer
  reported a false BLOCKED in good faith.
- **Combine the rules.** A rule is one sentence that names a condition and what
  the code does under it. When a change claims two rules that can fire on the
  same object in one run, the pair is an acceptance case of its own: a sequence
  of events that fires both, and the result that means pass. Each rule can hold
  alone while the pair fails. The durable executor reused an attempt number when
  a host loss was followed by a stall, and two reviews that checked each rule
  alone passed it.

The implementation brief lists the rules and their pairs. The review brief
repeats the rules and makes the reviewer combine them in a scenario of its own,
because the implementer's tests prove only the cases the implementer thought of.

The workflow owns the harness executor, tools, skills, thinking level, timeouts, and context
carry. Keep those controls out of the brief. For a pi agent, set them in the
`AgentSpec` and read [harness executors](harness-executors.md#pi); the brief still describes only the
work and its acceptance checks.

Every agent brief must account for its command time cap, as [ohflow](ohflow.md#command-time-caps) states it.

For findings another agent needs, declare `Step.consumes` and the producer's
`HandoverSpec` in the workflow. The engine supplies questions and the exact
attempt-file path in the position block. Keep the brief focused on the work;
see [step handovers](step-handover.md) for the shared question contract.

## Four rules from the retire-dsh run

The run that retired the `dsh` executor lost 35 minutes of a cloud step to a
hung test suite, and its docs step left the README's test case counts as they
were before the removal. Four rules came out of it.

- **A cloud step runs only the tests its brief names.** The brief lists the test
  files or the `-k` patterns of the change, and says in one sentence that the
  agent does not run the whole suite. No time limit stops a running tool call of
  `claude-cloud` or `codex-cloud`, so a hung suite holds the container until the
  execution timeout.
- **A gate runs the tests the change reaches, and CI runs the full suite.** Give
  the step a `command_exit` check whose `cmd` selects the tests from the step's
  changes, such as `python3 tests/run_tests.py --changed {base}`.
  It runs once, on the operator's machine, in minutes, and its exit code is the
  gate. The full suite never runs in a step or a gate: [ohflow](ohflow.md#gate-checks)
  states the rule.
- **A long step commits before it starts anything long.** The brief orders the
  work so that a commit comes before any command that can run for minutes: a
  wide test run, a build, a live call. A step killed at a time limit then leaves
  its work on the branch.
- **A removal workflow greps for counts.** The removal brief greps the documents
  for every number that counts the removed thing, in digits and in words, next
  to its grep for the name. The docs step's brief lists those numbers, and for
  each one the command that prints it from the code. The README's test case
  count of each test matrix is the one such number a check holds:
  `tests/check_docs.py` compares it with `MATRICES`.

## impl.brief.md

```markdown
# Task: <feature, one line>

You are working in a git worktree of the `<repo>` repository, on branch `<branch>`.
The working directory is the repository root. <Toolchain: runtime, package manager,
dependencies already installed.> Run the tests of the files you change.

## Context

<What the code does today. Name the file and the function. Two to five sentences.
State the fault the feature fixes, in terms the code shows.>

<The shape of the data the agent will touch: the object returned by the entry
point, its fields with their types down to the element type of each list or map,
who calls it. What invalidates or replaces it. Example: "`servers` is a list of
objects `{name: str, tools: int}`, not a list of strings.>

## What to build

<Numbered steps. Each step names a file and a function. Public signatures that
must not change are listed as such. Constants get names and values here.>

## Rules

<Every rule the change claims, numbered R1, R2 and on, one sentence each: a
condition and what the code does under it. Example: "R1. A host loss reattaches
the attempt under the same attempt number.">

<Under each rule, one worked example with its input events and the outcome the
rule gives, which you check against the design before the run. Example: "R2
example: a connection succeeds at t=0 and drops at t=10; with LOST_S=30 the
Worker is lost at t=40." The example exposes a rule whose wording gives the wrong
outcome, such as a clock that resets only on a new connection.>

## Interactions

<Every pair of rules that can fire on the same object in one run, as a case: the
rules, the sequence of events, and the result that means pass. Example:
"R1 and R3: host loss, then stall, then success. The stall's retry starts
attempt 2 in its own directory, and the step passes." When no two rules can meet,
say why in one sentence.>

## Tests

<Which test file, placed after which existing test, using which existing helpers.
Fixture names and what each fixture contains. One assertion per claim the feature
makes. One test per rule, and one test per interaction case, named after it.>

## Acceptance

All of the following must be true before you finish. Run each one and read its output.

1. <The tests of the files you changed and the new tests, by file or `-k`> exit 0.
   The gate runs `<changed-test selection, such as run_tests.py --changed {base}>` once
   after you finish, and CI runs the full suite after the push; run neither yourself.
2. <A command against real data, in a fenced block, with the expected output stated
   in words: "prints X first on line one".>
3. <The command that runs the interaction tests alone> exits 0, with one passing
   test per case in the Interactions section.
4. `git status --porcelain` prints nothing: every change is committed on `<branch>`.

## Commit

One commit, or two if the tests are separate. Subject line under 72 characters,
body in plain sentences. No `Co-Authored-By` trailer, no "generated with" line,
no mention of any AI model or tool in the message.

When the acceptance checks pass, reply with the commit hashes and the output of
acceptance command 2, then finish.
```

## review.brief.md

```markdown
# Task: review the <feature> change on branch `<branch>`

You are in a git worktree of the `<repo>` repository, on branch `<branch>`. The
working directory is the repository root. You have a terminal and nothing else.
Read files with `cat` or `sed -n`. Do not edit, create or delete any file in this
worktree, and do not run `git commit`, `git checkout` or `git reset`. Step 3 writes
its scripts under `<scratch directory outside the worktree, such as %TEMP%\review-<branch>>`.
Your output is your final message.

The change claims these rules:

<R1, R2 and on, verbatim from the implementation brief's Rules section. When that
brief has none, write each rule its design states as one sentence: a condition
and what the code does under it.>

## Step 1: craftsmanship

Run `git log --oneline <base>..HEAD` and `git diff <base>...HEAD`. <If more than one
commit: "Judge the combined diff."> Then read <the changed files> in full and
<the caller, with line range>.

Judge this diff only. Do not scan the rest of the repository. Judge:

- Is <the module> a deep module: one narrow interface over real work?
- Is <the seam the feature introduced> the right seam, given <the invalidation
  or lifecycle fact>?
- Are there names, comments or duplicated logic that make the file harder to
  navigate than it was?
- Does the test prove <each claim the feature makes>, or only that the code still runs?
- Does a test fire each pair of rules in one sequence, or does each test fire one rule?
- Does a test run each rule's worked example and assert the outcome the example states?
- Does the commit message describe the change without naming any AI tool or model?

Each finding is one sentence with a file and line, followed by one sentence saying
why it matters. Rank findings as BLOCKING or MINOR. A BLOCKING finding is one you
would not merge over.

If there is at least one BLOCKING finding, skip Step 2. Step 3 runs when the
implementation brief lists an interaction case.

## Step 2: behaviour

Run each check and paste its output.

1. Read the implementer's gate log for `<changed-test selection>`: its pass is the test
   evidence on this commit, and your gate reuses it. Run one test file only to
   answer a specific doubt, and name it.
2. <The implementer's acceptance command 2, verbatim, with its expected output.>
3. <One check per property the feature claims, each holding the field constant,
   each a command with the expected relation between two printed values. A check
   runs code and compares printed values. Quoting the implementer's test
   assertions is not a check.>
4. <A timing or size bound, if the feature has one.>
5. <The implementer's interaction tests, by name, when the implementation brief
   has an Interactions section.>

## Step 3: combine the rules

The tests on this branch prove the cases the implementer thought of. This step
finds a case the implementer did not think of.

1. List each pair of the rules above that can fire on the same object in one run.
2. Choose at least <one, or more for a change with many rules> of these pairs.
   Prefer a pair that no test on the branch fires in one sequence. Read the tests
   to learn which pairs they cover.
3. For each pair, write a script under the scratch directory that drives the
   branch's code through a sequence that fires both rules. <The fakes and
   fixtures the script can drive, such as `tests/fakes/fake_x.py`, the entry point
   to call, and how a script outside the worktree imports the branch's code, such
   as `PYTHONPATH=<worktree>/scripts`.>
4. Before you run it, write the result the rules predict. Then run it and paste
   the script, the command and the output.

A seen result that differs from the predicted result is a BLOCKING finding. Name
the two rules, the sequence and the line of code where the result goes wrong.

## Output format

Your final message has exactly these sections, in this order:

    ## Findings
    - BLOCKING | file:line | finding. Why it matters.
    - MINOR | file:line | finding. Why it matters.
    (or: none)

    ## Behaviour
    1. <check>: <result>
    ...

    ## Scenarios
    1. <Rn and Rm>: <sequence>. Predicted: <result>. Seen: <result>.
       <script path, command, pasted output>
    ...

    VERDICT: MERGEABLE

The verdict line stands alone as the final line of the message, nothing before it
on that line and nothing after it. The last line is `VERDICT: MERGEABLE` when there
is no BLOCKING finding, every behaviour check passed, and the Scenarios section
holds at least one scenario that ran, each with a seen result equal to its
predicted result. Otherwise the last line is `VERDICT: BLOCKED`.
```

## fix.brief.md

```markdown
# Task: address review findings on branch `<branch>`

You are in a git worktree of the `<repo>` repository, on branch `<branch>`, at the
repository root. Your earlier commit `<hash>` <did what>. A reviewer read the diff
and returned these findings. Address each one, then commit.

## Findings

1. **<finding title>.** <The reviewer's sentence, verbatim.> <One instruction:
   what to change, in which file, to what.>
2. ...

Do not change <behaviour that must hold>. Touch only the files the findings name,
plus any file that still refers to a symbol you rename.

## Acceptance

1. The tests of the files you change exit 0. The gate runs `<changed-test selection>`
   after you finish; do not run it yourself.
2. <Acceptance command 2 from the implementer brief, verbatim.>
3. `git status --porcelain` prints nothing.

## Commit

One commit on top of `<hash>`. Subject under 72 characters. No `Co-Authored-By`
trailer, no "generated with" line, no mention of any AI model or tool.

When the acceptance checks pass, reply with the commit hash and finish.
```

## contract_fanout briefs

[`workflows/contract_fanout.py`](../scripts/ohflow/workflows/contract_fanout.py)
writes these two briefs from its arguments; the braces are its slots. The
orchestrator agent writes the spec, with one section per piece, and `contracts.md`, as
[campaign](campaign.md#write-the-contracts) describes it. The template names
each child step after its piece, so the dashboard row reads as the piece. Each
child's position block also carries the full contracts text and the order to
stop and report. Change a brief in the module, and this section with it.

Run it with one `--args` per key. The template resolves `root`, `spec` and
`contracts` to absolute paths, because every child reads them from its own
worktree:

    cd <ohflow clone>/scripts && PYTHONPATH=. python3 -m ohflow.cli run \
      --workflow ohflow/workflows/contract_fanout.py \
      --args repo=<repo> --args root=<output root> --args spec=<spec.md> \
      --args contracts=<contracts.md> --args "test_cmd=<changed-test selection>" \
      --args "pieces=parser=src/parser/**;tests/test_parser*,printer=src/printer/**" \
      --out <runs root> --detach

Each child appends a start line and an end line to `<root>/heartbeat.log`, and
its gate fails when either line is missing. Poll the file every twenty minutes:
a piece with a start line, no end line and no new commit on its branch since
the last poll has stalled.

### When a piece stops on a contract

A child that finds a contract unworkable commits nothing, so its
`commits_past_base` check fails. "Build pieces" aborts on a failed step, so the
pieces beside it stop too, and the merges and the review never run. Read the
child's handover under Open for the contract and the reason, and edit
`contracts.md`. Then run the same command again with `--resume <run id>` and
the same `--out`. The edited contract changes every step's fingerprint, so
every piece runs again against it.

### Child brief, one per piece

```markdown
# Task: build the piece `{name}`

You are in a git worktree of `{repo}`, on branch `{branch}`. Pieces beside you
run at the same time on their own branches, and none of you sees the others'
work. Build the piece `{name}` as the spec at `{spec}` describes it. Your write
scope is {scope}; every other path is frozen.

## Contracts

`{contracts}` fixes every interface your piece shares with another piece. Build
against it exactly, and call the other pieces only through it. If a contract is
unworkable for your piece, stop: commit nothing that works around it, and name
the contract and the reason in your handover under Open.

## Heartbeat

`{heartbeat}` is the one file outside your worktree you write; the position
block's rule against writing outside your worktree does not cover it, and your
gate checks it. Before any other command, append one line to it:
`echo "$(date -u +%FT%TZ) {name} start" >> "{heartbeat}"`.
As your last command, append one line naming the outcome, `done` or
`stopped: <contract>`: `echo "$(date -u +%FT%TZ) {name} end <outcome>" >> "{heartbeat}"`.

## Definition of done

1. Every behaviour the spec gives `{name}` exists inside your write scope.
2. The tests of your piece pass; name the command and its result.
3. Hand-try: use the piece once by hand, the way its caller would, through the
   interface the contracts name. Paste the command and its output in your
   handover under Hand-try.
4. Every change is committed on `{branch}`, `git status --porcelain` prints
   nothing, and no commit message names an AI tool or model.
```

### Review brief

The review step runs after the merges, in the output worktree, on the
`terminal` alone. Its schema holds the lists `blocking`, `should_fix` and
`notes`, the test command and its exit (field `suite`), and a summary.

```markdown
# Task: review the merged pieces against the spec and the contracts

You are in the output worktree of `{repo}`, on branch `{branch}`, where
the branches {branches} are merged onto `{base}`. You have a terminal and
nothing else. Do not edit, create or delete any file in this worktree, and do
not commit.

1. Read the spec at `{spec}` and the contracts at `{contracts}`.
2. For each piece, read `git diff {base}...<its branch>` and its handover.
   Check the piece against its part of the spec and against every contract it
   makes or uses. Run each piece's hand-try again.
3. Run `{test_cmd}` once in this worktree and record the command and its exit.
4. Sort every finding into one list. `blocking`: it breaks a contract, the
   spec or the test command, and you would not merge over it. `should_fix`: it
   is wrong but the merge can stand. `notes`: anything else worth knowing.

A non-empty `blocking` list fails this step on purpose: that is how the fix
cycle starts. Report every blocking finding you find. Give each finding its
piece, a repository-relative path, a one-based line, the contract it breaks
when one does, the claim, and the fix in one sentence.
```

### When the review blocks

The review gate fails when the `blocking` list is not empty. The engine has no
step that turns findings into work, so the orchestrator agent starts the fix cycle.

1. Read `blocking` from the review step's
   `<run>/phases/03.review/01.review/attempts/<NN>/result.json`, under
   `structured`.
2. Write `<root>/fix.brief.md` from the [fix.brief.md](#fixbriefmd)
   template, one finding per item: piece, `path:line`, claim, fix. Its
   `<branch>` is `fanout/output`, and its `<hash>` is that branch's HEAD
   after the merges, as `git -C <root>/worktrees/output rev-parse HEAD`
   prints it. Add a `should_fix` item only when you choose to. Write
   `<root>/review.brief.md` from the [review.brief.md](#reviewbriefmd)
   template, with the contracts among the rules. Both paths are absolute,
   because implement-review reads them from the scripts directory.
3. Fire the [implement-review](implement-review.md) fix mode on the fan-out
   output branch:

       cd <ohflow clone>/scripts && PYTHONPATH=. python3 -m ohflow.cli run \
         --workflow ohflow/workflows/implement_review.py --args mode=fix \
         --args repo=<repo> --args branch=fanout/output \
         --args worktree=<root>/worktrees/output --args base=<base> \
         --args fix_brief=<root>/fix.brief.md --args review_brief=<root>/review.brief.md \
         --args contracts=<contracts.md> --args "test_cmd=<changed-test selection>" \
         --args harness_executor=pi --args skills_dir=$HOME/.agents/skills \
         --out <runs root>

   The `contracts` argument puts the same contracts in the fixer's and the
   reviewer's position blocks.
4. Read the fix run's result from its files, not from its step status. Its
   review gate passes on `VERDICT: MERGEABLE` and on `VERDICT: BLOCKED` alike,
   so read the last line of
   `<fix run>/phases/02.review/01.review/attempts/<NN>/final.md` and start
   another cycle on BLOCKED. Its `commits_past_base` check counts the merge
   commits already on `fanout/output`, so it passes when the fixer
   committed nothing: check that `git -C <root>/worktrees/output log -1`
   shows a new fix commit past the `<hash>` above.

Make at most two fix cycles, as implement-review states, then hand the last
review to the operator.

## Slots that were wrong in past runs

- A "do not touch file X" line in the fix brief kept a stale symbol name in that
  file. List the files the findings touch, and let the agent fix a stale
  reference wherever it lives.
- The durable executor's review brief asked the reviewer to quote the reattach
  test's assertions as the behaviour check. Two reviewers quoted them and returned
  MERGEABLE over the retry-after-reattach bug. The reviewer that found the bug ran
  its own sequence, host loss, then stall, then success, with the tests' fake
  executor. Step 3 asks a reviewer for that kind of scenario when the
  implementation brief lists an interaction case. A review from this template, on the
  same model, returned BLOCKED at `d3704cb` with that scenario
  ([examples/review-hardening/](examples/review-hardening/)). It cost 4.0 M
  tokens, twice a review without Step 3, because the reviewer ran four scenarios.

# Task: review the `durable` harness executor change on branch `proof/review-d3704cb`

You are in a git worktree of the `example-operator/agent-skills` repository, on branch
`proof/review-d3704cb`. The working directory is the repository root. You have a terminal and
nothing else. Read files with `cat` or `sed -n`. Do not edit, create or delete any file in this
worktree, and do not run `git commit`, `git checkout` or `git reset`. Step 3 writes its scripts under
`%TEMP%\review-hardening-proof`. Your output is your final message.

The change adds the ohflow harness executor `durable`, which runs a step on the buildbox PC through the
pi-durable host, its git transport `ohflow/remote_git.py`, and the reattach rule in the engine. The
implementer's brief states the design; read it first:

    cat C:/Users/<user>/ohflow-home/workflows/review-hardening/durable.impl.brief.md

The change claims these rules:

- R1. `push_start` refuses a worktree whose `git status --porcelain` is not empty, and names the
  paths.
- R2. `fetch_result` returns the fetched commit when the worktree already holds it, fast-forwards a
  worktree at `start_sha` when `start_sha` is an ancestor of the fetched commit, and refuses every
  other case with both shas.
- R3. A supervisor death, or a `host_lost` error from a harness executor with `CAP_REATTACH`,
  reattaches the attempt: the same attempt number, the same attempt directory, and
  `start_kind: "reattach"`.
- R4. A reattach closes the interrupted execution `deferred` with `abort_victim` and `reattached`, so
  the execution counts toward `attempts()` and stays out of `failed_executions()`.
- R5. A stall, the command cap or a judged failure starts a fresh attempt under the usual retry
  rules, not a reattach.
- R6. A reattach spends a start from the total-executions bound and no per-kind budget, so a step
  that keeps losing its host stops when its starts run out and is not excluded.
- R7. `build_result` counts tokens, cost and tool calls from every `message_end`, replayed ones
  included.

## Step 1: craftsmanship

Run `git log --oneline proof/review-base..HEAD` and `git diff proof/review-base...HEAD`. Judge the
combined diff. Then read in full `ohflow/scripts/ohflow/remote_git.py`,
`ohflow/scripts/ohflow/durable_runner.py`, the changed parts of
`ohflow/scripts/ohflow/engine.py` and `ohflow/scripts/ohflow/attempts.py`, and the new
tests.

Read the review method first:

    cat ~/.agents/skills/improve-codebase-architecture/SKILL.md
    cat ~/.agents/skills/codebase-design/SKILL.md

Apply the method to this diff only. Do not scan the rest of the repository. Do not produce an HTML
page and do not ask the user questions. Judge:

- Is `remote_git.py` a deep module with a narrow interface, free of any import from an executor
  module, so that a second executor can use it unchanged?
- Does `durable_runner.py` reuse pi's event helpers, or does it copy them?
- Does the engine hold the reattach in one place?
- Are there names, comments or duplicated logic that make the files harder to navigate than they
  were?
- Does each new test prove the claim it names, or only that the code runs?
- Does a test fire each pair of rules in one sequence, or does each test fire one rule?
- Do `references/harness-executors.md`, `README.md` and `references/ohflow.md` state what the code
  does?
- Does any commit message name an AI tool or model, or carry a `Co-Authored-By` line?

Each finding is one sentence with a file and line, followed by one sentence saying why it matters.
Rank findings as BLOCKING or MINOR. A BLOCKING finding is one you would not merge over.

If there is at least one BLOCKING finding, skip Step 2. Step 3 runs in every review.

## Step 2: behaviour

Run each check from the repository root and paste its output.

1. `python ohflow/tests/run_tests.py -k durable` must exit 0.
2. `python ohflow/tests/run_tests.py -k reattach` must exit 0.
3. From `ohflow/scripts`, run
   `PYTHONPATH=. python -c "from ohflow.harness_executors import harness_executor_info as i; print(sorted(i('durable').caps))"`.
   It must print a list holding `reattach`, `profile`, `stall_timeout` and `qualified_mcp`.

## Step 3: combine the rules

The tests on this branch prove the cases the implementer thought of. This step finds a case the
implementer did not think of.

1. List each pair of the rules above that can fire on the same object in one run.
2. Choose at least two of these pairs. Prefer a pair that no test on the branch fires in one
   sequence. Read the tests to learn which pairs they cover.
3. For each pair, write a script under `%TEMP%\review-hardening-proof` that drives the branch's code
   through a sequence that fires both rules. `ohflow/tests/support.py` holds `TempCase`,
   `FakeHarnessExecutor`, `AgentScript` (its `sequence` lists one result per execution, such as
   `{"error": None}`), `simple_workflow`, `git_repo`, `install_fake_harness_executor`,
   `stub_preflight`, `read_run_log` and `step_statuses`. `ohflow/tests/test_durable_03_reattach.py`
   holds `DurableFake`, a fake harness executor with `CAP_REATTACH`, and `durable_step`.
   `ohflow/tests/fakes/fake_durable.py` is a fake `ssh` and `scp` for the transport. A script
   outside the worktree imports all of these after it puts `<worktree>/ohflow/tests` and
   `<worktree>/ohflow/scripts` at the front of `sys.path`. `ohflow.workflow.RetryPolicy` sets
   a step's retries.
4. Before you run it, write the result the rules predict. Then run it and paste the script, the
   command and the output.

A seen result that differs from the predicted result is a BLOCKING finding. Name the two rules, the
sequence and the line of code where the result goes wrong.

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

The verdict line stands alone as the final line of the message, nothing before it on that line and
nothing after it. The last line is `VERDICT: MERGEABLE` when there is no BLOCKING finding, every
behaviour check passed, and the Scenarios section holds at least one scenario that ran, each with a
seen result equal to its predicted result. Otherwise the last line is `VERDICT: BLOCKED`.

# Monitor a run

Read this file when you hand the user the dashboard. A phase boundary is the moment the last step of a phase reaches a final state.

## At hand-over: write the bill

The message that carries the dashboard URL is a bill: what the run costs, what it is worth in one sentence, and the one decision that belongs to the user.

1. **Name the objective kind and its reason.** Write the kind and one sentence on why the user wants this kind now, because the reason lets you and the judge apply the kind to cases its rule never lists. The kind sets how far you, a judge or the user may intervene after `go` ([rules](campaign.md#intervention-by-kind-of-objective)). A delivery, such as a feature, a fix, a search, research or an output, may change course: a deviation or a design flaw aborts it for a fix, and after a miss you may replan, pause, continue or propose a restart. An empirical procedure, such as a hypothesis test or an A/B test, is fixed at `go`: it stops only for a deviation, and a change to the procedure restarts every arm. For an empirical procedure, write its arms, its procedure and its stopping rules into the bill.
2. **Price the run in four scalars.** Agent tokens per model, wall time, the user's attention minutes, and money paid out. Take tokens and minutes from the `ESTIMATE` line or the pilot projection. Guess attention as the decisions the user will face, a few minutes each, plus reading time. Price money for the steps that call a billed API, such as a per-token model API or a per-call search API, and show the line only when it is above zero. A cloud step (`pi-cloud`, `claude-cloud` or `codex-cloud`) also pays Cloudflare for its container, about $0.04 per container hour on `standard-1`, so give each cloud step its container line in the bill.
3. **Propose the caps, each with its basis.** A cap is the most the user would spend on the outcome, one per scalar. Base them on five criteria: the income tied to the outcome, the people or runs it serves, the later work or reusable knowledge it unlocks, the deadline it meets, and your confidence that it yields. Beside each cap, name the forecast its scalar rests on: the pilot projection, or the `basis` and `n` that the `ESTIMATE` step table gives the steps that carry most of the cost, with the `confidence` of their phase from the phase table. A forecast is a guess when its `confidence` is `low`, when its basis is `no history`, or when its basis counts attempts of another role, model or executor. The forecast of a cloud step is a guess until the history holds real tasks on that executor: one forecast said 16 minutes and 1.3 M tokens, and the step took 73 minutes and 4.2 M. Write "guess" beside such a cap and set it from the five criteria alone. The user's answer sets the caps. When the user defers, your proposal does.
4. **Give each cap a limit that acts in time.** A cap acts only through a limit, and a limit has one of three forms. An execution timeout is enforced by the engine: it kills the step and asks nobody. A stop-and-ask limit is a threshold below the cap at which you stop and ask the user. Use a stop-and-ask limit only when the answer can arrive while the step runs: the user reads this session directly, not through a relay such as another session, and the step runs on for longer than the user takes to answer. Otherwise make it an execution timeout: during the hold, set the step's `execution_timeout_s` so that the step cannot pass the cap, and `go` loads the edited module. The execution timeout bounds one attempt, so divide the cap by the attempts the step's retry policy permits. A token budget is the third form, enforced by the engine for the whole run: during the hold, set `token_budget` in the workflow module, which `go` loads, or pass `--token-budget N` to `run`. [The token budget](ohflow.md#token-budget) admits, extends and stops agent attempts against it, and its overshoot per harness executor is known, so name that overshoot in the bill. The engine limits no money, so convert a money cap into tokens or minutes at the forecast's rate. On a `durable` or cloud step the execution timeout also stops the remote work: the kill ends a durable host on the local box, its tether ends it on an ssh box, and a cloud executor posts `abort` for the attempt's container. Write each limit into the bill with its form, and give a stop-and-ask limit the default that applies when no answer comes.
5. **State the run's worth in one sentence.** Say what the outcome gives the user, in the user's terms.
6. **Say first when the run does not pay.** A projected total above any cap means the run does not pay, and the bill says so first.
7. **Close with the decision.** End the bill with the one decision that is the user's, your recommendation first, and the line "Say lost for a short walk-through."
8. **Log the bill.** `notes log --run <run-dir> "bill: <kind>: <reason>; caps <cap (basis), ...>; limits <limit (form), ...>; worth <one sentence>"`.

Done when the user has the bill and its log line exists.

## Each poll: read the engine

Call `watch --run <run-dir>`. Tell the user about each restart, each red signal and a pause. Before you write to the user, read the `attention` lines `watch` prints. Each line is one item of the dashboard's attention strip, with its next step and its run-log line, and `attention cleared:` says an item went away. A line that starts `attention standing` is an item that was there before this cursor first looked, so do not report it as something that just happened. `watch --until attention` returns only on an `intervention` item the cursor has not reported or the end of the run. An `intervention` item is what the user must decide on, and its `next:` part is the one command the engine permits, or why there is none, so quote it. A `recovering` item is the engine's own next move, so say what it waits for. A `signal` item is a threshold, so call it a signal.

Compare each running step with its stop-and-ask limits. When a step has passed one, ask the user in this session at once: name the limit, the default and the time the step is expected to end. When no answer has come by the next poll, apply the default.

When a step fails, run `explain --run <run-dir> --step <step>` before you write to the user: its first line names the failure class and the retry decision, and its lines carry the failed gate checks, the tool output and the evidence. When that leaves open where the agent went wrong, run `actions` on the same step: one line per model call, with the actions it launched and their results.

When an agent goes wrong, or wastes time, choose your move in [steer-a-run](steer-a-run.md).

Exit 10 means the run is still going: call again. Done when `watch` exits with a code other than 10.

## At each phase boundary: take the critical look

1. **Re-read the objective kind and its reason.** Take them from the `bill:` line in the run's `notes.md`, because a compacted session may have lost them. Judge each problem you see as a deviation, a design flaw or a miss, and let the kind's rule ([campaign](campaign.md#intervention-by-kind-of-objective)) say what you may do.
2. **Compare the cost still to come with the run's worth.** Count only the cost still to come. A result can change what the rest of the run is worth: a recon that found nothing lowers the steps that would have used it.
3. **Answer one question: knowing what you know now, would you start this run?**
4. **Report a bad trade in two sentences.** A bad trade is a "no" to that question, or a cap the run will pass. The first sentence states the trade as it stands. The second offers the correction and its default if the user defers. Example: "The remaining 40 review steps cost 4 hours and can change no decision that is left. Default if you defer: skip them." In an empirical procedure, the correction cannot change the procedure while the arms run: it is continue, or a restart of every arm under a changed procedure, and that restart is the user's decision.

Done when the boundary has a notes line with the cost left and your answer.

## Each reply from the user: check understanding

Three signals say that a message held more than the user could take in:

- The user says so, in words such as "lost", "too much" or "can't digest".
- The reply passes over the decision your message named.
- The user answered a batch with one "yes", and the batch held a decision on scope, effort, budget or stop.

A "yes" on a mechanical change is taken as given.

1. **For a doubtful "yes", ask one teach-back question.** The question asks the user to choose or to predict, such as "After this yes, how many agent runs do you expect?". A correct answer closes the check.
2. **For a stated overload or a missed teach-back, open the walk-through.**
   - The first message opens with "Step 1 of N, ending in <the decision>.", where N is 2 to 10. Every later message opens with its position: "Step 3 of 5." A detour opens with "Detour from step 3 of 5" and closes by restating step 3.
   - Each step holds one fact and one question that needs a choice or a prediction, and nothing more.
   - A prediction comes before its number. The step that asks for the guess holds no number the answer follows from, and the next step shows the number. The gap between the guess and the number is what the user was missing.
   - The walk-through ends in the user's decision, or in "carry on as planned".
3. **Log each firing.** `notes log --run <run-dir> "check: <signal>; <what you did>; <the reply>"`.

Done when every signal has its notes line.

## At the end: report the cloud bill

A run with a cloud step ends with a Cloudflare line in its verdict and a `## Cloudflare` section in `exit-report.md`. Cloudflare's meters lag by a few minutes, so when the section says "the bill so far", run `cloud-spend --run <run-dir>` again after the time it names. Put the billed figure in the final report to the user, next to the token cost. A flag in that section means a container ran on after its step and kept billing, so name the attempt and the extra time in the report.

Done when the final report names the Cloudflare figure that `cloud-spend` read after the lag, or says that the meters could not be read and why.

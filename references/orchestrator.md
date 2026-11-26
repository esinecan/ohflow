# Guidance for the orchestrator agent

The orchestrator owns the user's outcome across runs. A workflow's verdict describes
that execution; accepted artifacts establish which parts of the task were delivered.
After a failed run, preserve its evidence and reuse verified inputs in a separately
identified revision. Keep an experiment's procedure fixed during execution; record
changes between trials. Existing authorization carries routine recovery within scope
and agreed limits. Ask about a material change or a limit that requires a new decision.

## Choose models and effort deliberately

Honor the user's model and executor constraints. Put model, thinking level, tools and
limits in `AgentSpec`; verify their effective values in the attempt's telemetry.
Capability checks and a successful model call establish different things: preflight
is not proof that the model can finish the assignment.

Use effort appropriate to the step: metadata selection and mechanical extraction
usually need less deliberation than interpreting competing explanations. Measure
this on a bounded real task. If a revision changes the input packet, reasoning level
and tools together, report the observed improvement without attributing it to one
change. A fresh reviewer on the same model family provides a fresh context, not
independent model-family evidence.

## Give a step's agent the task, not the orchestration

Supply the canonical input, output contract and one acceptance command. When a bounded
source fits comfortably in the prompt, embedding it can remove repeated filesystem
discovery. Otherwise name the exact source and coverage required. Reading both a raw
capture and its complete rendered transcript spends context twice; let deterministic
checks establish byte integrity when the agent only needs the readable source.

Render tables or Markdown deterministically from a structured result when that retains
the findings faithfully. An agent should not have to author the same analysis twice.
For a read-only assessment, consider a schema-valid final response and a separate
command that checks, saves and commits it. The [review-by-dimension pattern](review-by-dimension.md)
uses this division. File editing and commits belong in an agent's contract when its
task requires them; they need not be imposed on every research reviewer.
Keep workflow source, repository setup and unrelated project history out of its input
packet. Narrow the actual tool policy where the executor permits it; distinguish
restrictions the tool policy enforces from instructions that cooperative tools merely follow.

## Price the work you are actually starting

State the usage measure: input, cached input and output are distinct, and repeatedly
read cached context still counts toward a total-token budget. Model list-price estimates,
subscription charges and the container chronometer's infra cost are separate figures. Match history by role,
model, executor and task size; label unmatched forecasts as guesses.

Per-step timeouts bound attempts, not a run's aggregate tokens or money. If the engine
lacks admission control, describe an operator checkpoint honestly and reserve headroom
for every concurrent call that can settle after the last observation. Choose a threshold
that can act before the agreed cap; polling alone cannot guarantee a hard token ceiling.
Carry prior attempts' usage into the budget for a recovery run.

## Verify before declaring progress

Use one watch cursor per independent reader. Read the execution error as well as
the failed gates: a missing artifact after a stall is a consequence, not the cause.
An interrupted last assistant message is not a completed final answer.

Check each command's exit status before logging its result or running dependent actions.
A shell can continue after a failed command. Recheck transferred evidence in an
independent checkout before relying on it; [the run procedure](operate-a-run.md)
owns raw-byte transport. Never relax an evidence check merely to obtain a passing run.
Schema validity establishes the response shape, not quotation accuracy or factual truth.
Check citations against the source separately. A source-only citation repair must retain
the original response, record each edit and leave substantive judgments identifiable.

After a remote stop, verify that the remote operation and container stopped. Preserve
accepted artifacts and account for interrupted usage explicitly. Report the task as
unfinished when the user's deliverable is incomplete, even if the notes checker passes.

## Learn while operating

At a phase boundary or a new failure, record the expected behavior, actual observation,
reproduction command or artifact, and what remains uncertain in the run notes. Separate
an operator mistake, a documentation omission, a confirmed defect and a design proposal.
Update steering guidance when the evidence warrants it; keep open work in
[docs/todo.md](../docs/todo.md), its single owner, with an observable completion check.
Mark a fix complete only after the relevant code or documentation change is verified.
Preserve failed trials rather than rewriting them as successes after a later repair.

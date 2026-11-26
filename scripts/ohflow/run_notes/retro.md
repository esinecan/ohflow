# Retro - run {{run_id}}

Workflow: {{workflow}}.
ohflow drafts the first part when the run ends. You fill in the second part.

## What the engine recorded

<!-- ohflow:auto begin -->
Filled in when the run ends.
<!-- ohflow:auto end -->

Full numbers for every step (run from the ohflow scripts directory):

    python -m ohflow.cli table --runs {{run_dir}} --by step

## What I judge

| Step | What it was for | My verdict | Gate right? | Cause if not good | Note |
|---|---|---|---|---|---|
{{step_rows}}

- **My verdict:** kept, fixed by hand, or reverted.
- **Gate right?:** yes, or no. No means the gate passed bad work, or failed good work.
- **Cause:** brief, agent, gate, workflow, infra or environment.

## Seven questions

One line each.

1. Did it deliver? (`ground-truth.md`)
2. Where did time and cost go? (the per-step table above; when cost reads `unpriced`, read tokens)
3. What failed, and why? (the pointers above; `run-log.jsonl`: `failure_class`)
4. What did I do by hand? (`notes.md`)
5. Did the gates tell the truth? (the two gate columns, and any pointer about an error that passed)
6. Was the workflow right? (its pattern, waits, retries, steps too big or too small)
7. What do I change next time? (a brief, the workflow, a gate)

## Best step, worst step, one change

- Best step:
- Worst step:
- One change for next time:

## Predictions against outcome

Compare `predictions.md`, the orchestrator calibration, with what happened: line 2
against the agent time and tokens of the per-step table. Which line was furthest
off, and does the gap show rigor that costs more than it returns, or too little?

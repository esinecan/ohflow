# Predictions - run {{run_id}}

Workflow: {{workflow}}
Repo: {{repo}} ({{base_branch}} at {{base_sha_short}})
Started: {{started}}

The orchestrator calibration. The orchestrator agent fills this when the operator
asks for one, from the workflow and its briefs, before it reads the estimate or any
result. The operator reads it for a check every step repeats, a fix loop on every
edit, or a gate too loose for its risk; after the run, the retro compares it with
what happened. One line each. A guess is fine. Left empty, it is no gap for
`notes check`.

1. Expected cost and wall time:
2. The steps that will burn the most wall time and tokens, and why:
3. The gate I trust least, and why:
4. What "good" looks like when the run ends:
5. What would make me stop the run:

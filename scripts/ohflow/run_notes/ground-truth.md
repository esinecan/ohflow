# Ground truth - run {{run_id}}

What is true about the code after the run, measured outside ohflow.
Base: {{base_branch}} at {{base_sha}}{{baseline_line}}

Fill this after the run. An agent's report is a claim; this file is the evidence.

## 1. Checks on the merged head

`notes check` accepts the gate's recorded pass when the merged head has the gated tree.
Otherwise link the CI run on the pushed head.

- The gate's recorded pass on this tree, or the CI run on the pushed head:

## 2. What changed

Command: `git diff --stat {{base_sha_short}}..HEAD`

(paste the output)

# Review by dimension

Use `scripts/ohflow/workflows/review_by_dimension.py` when several independent questions need separate reviewers: correctness, security, compatibility or another named dimension. Each read-only agent inspects the same existing worktree and returns a structured report. A command combines those reports into `review.md` and `verdict.json`.

Create one `<dimension>.md` brief per dimension. Give the workflow `repo`, `worktree`, `base`, `branch`, `dimensions=correctness,security` and `brief_dir=<directory>`. Give it `harness_executor=pi` as well, because every reviewer runs on `pi` and the workflow has no default. The workflow validates names, briefs and supported executors before starting.

Each report carries its dimension, PASS or BLOCKED verdict, findings and summary. Schema checks gate the reports, and consolidation preserves dimension order. No agent handover is required because the consolidator reads structured artifacts directly. A combined PASS establishes the reviewers' reported verdicts, so check the cited evidence before accepting the product.

The feature template can use the same review phase through its [implement/review procedure](implement-review.md). For running and inspecting the workflow, see [ohflow](ohflow.md) and [operate-a-run](operate-a-run.md).

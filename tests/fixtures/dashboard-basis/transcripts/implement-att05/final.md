Attempt 5 found one failing test, `test_defect_08_suite_time_is_measured`, and I fixed it in commit 7bb6f78. The tree is clean and I changed only `oh-dispatch/README.md`.

**Cause.** Attempt 4's README gave the suite total as `857.8 s`. The test regex wants whole seconds (`\d+ s`), so shard 2 failed and the gate exited 1. The test checks the shape of the figure, not one number.

**Item D, suite figure.** The README now says `911 tests, 861 s on 2026-10-02`. The shard times are 299.8 s, 303.0 s and 258.6 s, from a fresh three-shard run on this branch.

I ran the shards in the foreground with stdin closed. The three `ran N tests` lines are:
- `ran 304 tests in 299.8s failures=0 errors=0 skipped=1`
- `ran 304 tests in 303.0s failures=1 errors=0 skipped=0` (the README test above)
- `ran 303 tests in 258.6s failures=0 errors=0 skipped=0`

After the README fix I re-ran only `test_defect_08_suite_time_is_measured`, and it passes. I did not re-run all three shards.

**Item C, hermetic claude prose.** The attempt 4 commit 9c434d7 had already rewritten the `claude` row in `references/lanes.md` and the `HERMETIC_ENV` comment in `claude_runner.py`. A grep of `oh-dispatch` finds no other sentence saying hermetic claude keeps the project's instruction files.

I ran the probe in a temp repo with `CLAUDE.md` ("codeword PELICAN-77") and `.claude/CLAUDE.md` ("codeword OTTER-12"):
- With `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` the output was `NONE`.
- Without the variable the output was: "You want the codewords from my instructions, and they are PELICAN-77 (project `CLAUDE.md`) and OTTER-12 (`.claude/CLAUDE.md`)."

I ran no live roll-call cell.
Items C and D are fixed and committed on `arch/m7-smoke-fixes`; this pass changed prose and one code comment, and ran no live roll-call cell. The tree is clean, only `oh-dispatch/**` changed, and no commit message carries model attribution. The gate's full-suite run is still to come. The three shards below all passed, and `-k hermetic` ran 10 tests with no failures.

**C: `references/lanes.md` and `claude_runner.py`** (commit `9c434d7`)
- **Removes:** the `claude` row now says `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` removes every `CLAUDE.md` instruction file, the user's and the project's. It also lists `.claude/CLAUDE.md`, `CLAUDE.local.md` and `.claude/rules`. It still lists the user's settings, built-in tools and MCP servers.
- **Keeps:** the OAuth login, the plan's `--mcp-config` servers, and the project's and local settings files (`.claude/settings.json`, `.claude/settings.local.json`).
- **Not probed:** my probe showed only the two `CLAUDE.md` files. The "settings files kept" half follows your brief and the meaning of `--setting-sources project,local`.
- **`HERMETIC_ENV` comment:** it now says the variable drops every instruction file, the user's and the project's.
- **Hermetic command line:** I also added the variable to the Hermetic command-line paragraph in `lanes.md`, which listed only the flags.
- **Grep:** no other sentence in `SKILL.md`, `README.md`, `references/` or `CONTEXT.md` says hermetic claude keeps the project's instruction files.

Probe in a temp git repo (Claude Code 2.1.281) with `CLAUDE.md` ("codeword PELICAN-77") and `.claude/CLAUDE.md` ("codeword OTTER-12"):
- With `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1`: `NONE. No codewords appear in my instructions, and no CLAUDE.md or memory index contents were loaded into this conversation.`
- Without it: `You want the codewords from my instructions, and they are PELICAN-77 (project CLAUDE.md) and OTTER-12 (.claude/CLAUDE.md).`

**D: README suite figure** (commit `ccfe082`)
- The README now gives "911 tests, 857.8 s on 2026-10-02" and shard times of 310.7 s, 290.1 s and 257.0 s, one place each. The old 902 and 873 figures appear nowhere else in the skill's `.md` files except a history document that holds neither as a suite figure.
- Shard lines, each run in the foreground with stdin closed:
  - `ran 304 tests in 310.7s   failures=0 errors=0 skipped=1` (the 1 skip is the opt-in test)
  - `ran 304 tests in 290.1s   failures=0 errors=0 skipped=0`
  - `ran 303 tests in 257.0s   failures=0 errors=0 skipped=0`

Test counts: 902 before and 911 after the whole attempt. Attempt 4 added no tests and deleted nothing.
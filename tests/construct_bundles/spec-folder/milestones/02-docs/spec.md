# Document strict mode

source: specs/strict-mode.md
pattern: single agent
box: local
harness: codex
tier: light
writes: README.md

## Scope

Add a section "Strict mode" to `README.md` with one example of a refused key and its error.

## Acceptance

- command: grep -q "Strict mode" README.md

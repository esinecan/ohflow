# Document strict mode

source: specs/milestones/02-docs/spec.md
pattern: single-agent
box: local
harness: claude
tier: light
writes: README.md

## Scope

Add a section "Strict mode" to `README.md` with one example of a refused key and the error it
raises.

## Acceptance

- command: `grep -q "Strict mode" README.md`

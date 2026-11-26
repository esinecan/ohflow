# Strict mode in the config parser

source: specs/milestones/01-strict/spec.md
pattern: implement-and-review
box: local
harness: claude
tier: light
review harness: claude

## Scope

`parse(text, strict=True)` raises `ConfigError` for a key that the schema does not name. The error
names the key and its line. Without `strict`, the parser keeps today's behaviour. Add tests for
both.

## Acceptance

- command: `python3 -m unittest discover -s tests`
- rubric: The error message names the unknown key and its line number.

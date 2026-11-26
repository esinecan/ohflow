# Strict mode in the config parser

source: specs/strict-mode.md
pattern: implement-and-review
box: local
harness: pi
tier: heavy
review harness: claude

## Scope

`parse(text, strict=True)` refuses a key that the schema does not name, with an error that names
the key and its line. Without `strict` the parser keeps today's behaviour.

## Acceptance

- command: `python -m unittest discover -s tests`
- rubric: The error message names the unknown key and its line number.

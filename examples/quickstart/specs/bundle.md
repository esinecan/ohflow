# Strict config parsing

kind: delivery
judge harness: claude
judge tier: light

## The operator's words

Add a strict mode to the config parser, so a typo in a key stops the program instead of being
kept as text. Then document it.

## The bar

- In strict mode the parser refuses a key the schema does not name, and a test shows it.
- Without strict mode the parser behaves as it does today, and the existing tests still pass.
- The README explains strict mode with one example.

## Decisions already made

- Strict mode is a keyword argument of `parse`, and it is off by default.

## Stop and ask

- A change to the config file format.

## Workspace app

path: ../app
base: main

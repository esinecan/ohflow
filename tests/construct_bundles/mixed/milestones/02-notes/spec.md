# Migration notes and the deprecation shim

source: TICKET-102
pattern: relay
workspaces: notes, api
box: local
harness: codex
tier: light

## Scope

Write the migration notes for the rename, then add a deprecated `lookup_user` alias to the API
that the notes point to.

## Steps

### notes
workspace: notes
writes: MIGRATION.md

List every renamed call in `MIGRATION.md`, with the old and the new name.

### shim
workspace: api
writes: src/users.py
box: cloud
harness: claude

Add `lookup_user` as a deprecated alias of `find_user`, as the notes describe.

## Acceptance

- command in notes: test -s MIGRATION.md
- rubric: The notes name every renamed call, and the shim's warning points to the notes.

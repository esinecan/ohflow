# Rename the lookup in both repositories

source: TICKET-101
pattern: fan-out under contracts
workspaces: api, client
box: local
harness: pi
tier: light
review harness: claude
review tier: heavy

## Scope

`lookup_user` becomes `find_user` in the API, and the client calls the new name. No other
behaviour changes.

## Steps

### api
workspace: api
writes: src/**, tests/**

Rename `lookup_user` to `find_user` in `src/users.py` and in its tests.

### client
workspace: client
writes: lib/**, tests/**

Call `find_user` from `lib/lookup.py`, and update the client's tests.

## Acceptance

- command in api: python -m unittest discover -s tests
- command in client: PYTHONPATH={api}/src python -m unittest discover -s tests

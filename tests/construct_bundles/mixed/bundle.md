# Api and client

integration branch: campaign/find-user

## The operator's words

Rename the user lookup to find_user in the API and in its client at once, and keep migration
notes for the people who call it.

## The bar

- The API and the client build against one signature, and each suite passes.
- The migration notes name every renamed call.

## Workspace api

path: ../api

## Workspace client

path: ../client
base: trunk

## Workspace notes

owned: yes

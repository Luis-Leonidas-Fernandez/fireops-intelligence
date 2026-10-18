# Inventory asset transfers

## Objective

Allow an authenticated user to transfer an existing asset to an active location while preserving an operational movement history.

## Problem and constraints

- Updating `bienes.ubicacion_id` alone loses origin, destination, time, reason, and actor.
- The physical model 1.1 defines `movimientos` with a required asset, user, controlled movement type, timestamp, and optional origin/destination and descriptive fields.
- Keep the asset state update and movement insertion atomic; reject missing/inactive destinations, same-location transfers, and containment cycles.
- Apply new migrations only to a verified `fireassets_test`, never to `fireassets`.
- Do not add general stock movements, an inventory frontend form, or authorization changes to unrelated endpoints.

## Tasks

- [x] T01 — Add isolated transfer API tests and observe RED. Route: inline under runtime delegation constraint. Check: focused pytest failed with `404` before the route existed.
- [x] T02 — Add `movimientos` table and ORM relationships according to physical model. Route: inline under runtime delegation constraint. Check: upgraded verified `fireassets_test` to `a6a239f7b4dc`; Alembic check found no pending operations.
- [x] T03 — Add authenticated transfer API with one transaction for state and history. Route: inline under runtime delegation constraint. Check: five transfer tests passed, including atomic rollback after containment-cycle rejection.
- [x] T04 — Run regressions, document behavior, and inspect diff. Route: inline under runtime delegation constraint. Check: 70 Python tests, 12 frontend tests, Ruff, inventory mypy, changed-file formatting, and Git diff whitespace checks passed.

## Acceptance criteria

- A valid transfer changes the asset's current location and creates exactly one `TRASLADO` movement with actor, origin, destination, and time.
- Failed transfers leave both the current location and movement count unchanged.
- The endpoint requires a valid local session; a user ID is not accepted from the request body.
- Users can inspect transfers for an asset in chronological order.
- Tests remain independent and use `fireassets_test` only.

## Progress

- Branch: `codex/inventory-locations`.
- State: implemented and verified locally. Migration `a6a239f7b4dc` applied exclusively to `fireassets_test`.
- Rollback boundary: revert the movement migration, `Movement` ORM mappings, transfer router/schemas, transfer tests, and transfer documentation together; leave the earlier location feature intact.
- Commit: `4310787` includes transfers together with the dependent inventory workflows. It has not been pushed. An unrelated untracked DOCX remains untouched.
- Delivery: no push or merge without user authorization.

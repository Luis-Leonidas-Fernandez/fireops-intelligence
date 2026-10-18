# Edit assets with an atomic audit record

## Objective
Implement `PATCH /inventory/assets/{asset_id}` for fields currently persisted on `bienes`, preserving the physical model's audit requirement and SRP.

## Problem and constraints
- Current Asset persists internal code, name, category ID, and current location. Only code, name, and category are directly editable; location changes must use transfers and movement history.
- The model's `auditoria_cambios` table is not yet implemented. An edit must persist previous/new values, reason, actor and time in the same transaction as the asset update.
- Preserve current authenticated inventory behavior, response schema and earlier staged/uncommitted work. No frontend or roles/invitations in this feature.
- Apply a new migration only after proving the effective database is `fireassets_test`; never migrate normal `fireassets`.

## Tasks
- [x] E1 — Added isolated endpoint tests for PATCH success, audit, auth, validation, missing/duplicate references, and rollback. Route: delegated; multiple non-trivial files. RED observed: 12 tests failed with HTTP 405 after the audit model and test migration were in place.
- [x] E2 — Added audit model and migration matching physical model 1.1, then applied it only to the verified test DB. Route: delegated; model, migration and fixture changes. Real `SELECT current_database()` returned `fireassets_test`; Alembic moved from `a6a239f7b4dc` to `c15b4e3d9a20`.
- [x] E3 — Implemented PATCH schema, service and thin router; registered the route and preserved transfer semantics. Route: delegated; multiple non-trivial files. GREEN observed: 57 focused PATCH/auth tests passed, including rollback on an audit FK failure.
- [x] E4 — Verified focused/full suite, Alembic consistency, lint/types and updated docs. Route: delegated checks plus parent spot check. Full Python suite: 133 passed; `alembic current`: `c15b4e3d9a20 (head)`; `alembic check`: no new upgrade operations; Ruff check/format, mypy and `git diff --check` passed.

## API contract
- Partial body: one or more of `internal_code`, `name`, `category_id`; `reason` required and non-blank. `location_id` and unknown fields rejected.
- Existing response schema, HTTP 200; missing asset 404; invalid input 422; duplicate code or missing category 409; missing session 401.
- Audit action `CORRECCION`, entity `BIEN`, full before/after snapshots, actor from the authenticated session, reason, timestamp and operation ID.
- Asset and audit are one transaction; any failure rolls both back. No movement row for metadata edits.

## Acceptance criteria
- Every successful edit changes only requested fields and creates exactly one correct audit row.
- Failed edits leave asset and audit unchanged; location and movement history never change through PATCH.
- Test isolation and auth behavior match existing inventory conventions.
- Migration is verified/applied only to `fireassets_test`, and no unrelated schema change is introduced.

## Verification and delivery
- Test-first RED/GREEN, full Python suite, Ruff, mypy, Alembic current/check, `git diff --check`.
- Delivery strategy: ask-on-risk; likely >400 authored lines because model, migration, service and tests must ship as one behavior. Do not omit tests to fit the heuristic.
- Commit pending: earlier inventory work remains staged and overlaps files in this unit. Do not mix work units. Runtime boundary: ASGI endpoint tests exercised PostgreSQL through `fireassets_test`; no browser test applies because no frontend changed. Rollback boundary: remove the PATCH router, service, schema, audit model/migration and their tests/docs without touching location or transfer behavior. Next step: isolate the earlier inventory work before preparing a work-unit commit; do not push or merge automatically.

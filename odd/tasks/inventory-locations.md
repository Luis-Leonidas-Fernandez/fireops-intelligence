# Inventory locations

## Objective

Implement the location fields and relationships from the documented physical model 1.1 while preserving existing assets and categories.

## Scope and constraints

- Add `ubicaciones` with physical/vehicle type, optional container asset, description, active flag, and timestamps.
- Add nullable `bienes.ubicacion_id`; existing assets must remain valid.
- Enforce the documented foreign keys, vehicle-container uniqueness, type/container consistency, and prevent self-containment or containment cycles.
- Expose minimal create/list location APIs and allow asset registration/read APIs to use a location.
- Do not add movements, responsible users, or unrelated asset attributes in this change.
- Apply migrations only to `fireassets_test` after confirming the effective and actual target. Do not modify `fireassets`.

## Tasks

- [x] L01 — Add failing tests for location rules and asset location assignment. Route: inline because this runtime does not permit spawning without explicit delegation. Check: focused pytest RED observed before implementing `Location`.
- [x] L02 — Add the migration and SQLAlchemy models according to the physical model. Route: inline under the runtime delegation constraint. Check: Alembic upgrade on verified `fireassets_test`, schema inspection, and `alembic check` with no pending operations.
- [x] L03 — Add location API and extend asset schemas/routes. Route: inline under the runtime delegation constraint. Check: location tests GREEN.
- [x] L04 — Run regression tests, document the resulting API and migration procedure, and review the diff. Route: inline under the runtime delegation constraint. Check: 65 Python tests and 12 frontend tests passed; Ruff, mypy, formatting of changed code, and `git diff --check` passed.

## Acceptance criteria

- Existing assets have `location_id = null` after migration.
- A physical location has no container asset; a vehicle location has exactly one existing container asset, and an asset can represent at most one vehicle location.
- New assets can optionally reference an existing active location. Read/list responses include its ID.
- Direct self-containment and containment cycles are rejected.
- Tests are isolated on `fireassets_test`; no operation mutates `fireassets`.

## Progress

- Branch: `codex/inventory-locations` (from `main` at `421870a`).
- Current state: implemented and verified locally. Alembic current: `e42c7910b6af (head)` on `fireassets_test`; no migration was run on `fireassets`.
- Verification: `ENV_FILE=.env.test python -m pytest -q` → 65 passed; frontend `node --test frontend/tests/*.test.cjs` → 12 passed; `python -m mypy app/modules/inventory` → no issues; `ruff check` and changed-file `ruff format --check` passed. Full-tree format check still reports two pre-existing files in `register_category`.
- Rollback boundary: revert the inventory-location migration, location router/schemas, asset location fields, related tests, and corresponding documentation together; do not revert unrelated authentication or category changes.
- Delivery: no push or merge without user authorization.

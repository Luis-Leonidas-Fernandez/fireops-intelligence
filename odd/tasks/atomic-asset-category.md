# Atomic asset and category registration

## Objective
Allow `POST /inventory/assets` to accept either an existing `category_id` or a `new_category_name`. Create/reuse the category and asset atomically, so an asset failure never leaves a new category behind.

## Scope and constraints
- Backend and backend tests only; no frontend or database migration.
- Preserve the existing `category_id` request and response contract.
- Keep HTTP mapping in the router and persistence/transaction orchestration in a service (SRP).
- Preserve all pre-existing staged work on `codex/inventory-locations`; do not touch production data.

## Tasks
- [x] T1 — Add isolated RED tests for new category, existing category reuse, invalid input, and rollback after asset failure. Route: delegated; multiple non-trivial files and test infrastructure. Evidence: focused pytest reported 5 failed, 1 passed before implementation; `tests/modules/inventory/conftest.py` shares the transactional fixture.
- [x] T2 — Add request validation and a service for atomic category/asset creation; keep the router thin. Route: delegated; multiple non-trivial files. Evidence: focused pytest reported 6 passed after implementation; PostgreSQL `ON CONFLICT DO NOTHING` safely reuses a same-name category. The service owns `commit()` and rollback for all pre-commit errors; the router only maps exceptions to HTTP.
- [x] T3 — Run focused and full backend checks, document behavior, inspect diff, and record delivery evidence. Route: delegated verification/inline state inspection. Evidence: full pytest 76 passed; Ruff lint/format, mypy and `git diff --check` passed; architecture/progress docs updated.

## Acceptance criteria
- A request with exactly one category source creates an asset and returns the existing response schema.
- An existing category name is reused without creating a duplicate.
- Invalid category source, invalid location, or asset write failure does not persist a new category.
- Independent tests run against `fireassets_test`; old category-ID clients keep working.
- No migration or frontend change is required.

## Verification and delivery
- Planned checks: focused pytest, full backend pytest, Ruff lint/format check, mypy, and `git diff --check`.
- RED/GREEN evidence: RED 5 failed/1 passed; GREEN focused 6 passed and full suite 76 passed against `fireassets_test`.
- Runtime harness: ASGI/httpx tests exercising the real FastAPI route and PostgreSQL test database; no browser/frontend change in scope.
- Rollback boundary: the service, request extension and HTTP integration in `app/modules/inventory/register_asset/`, the shared fixture plus new tests, and the two documentation updates; preserve the pre-existing location/transfer work.
- Commit evidence: pending. The index already contains unrelated staged location/transfer changes, including earlier versions of the same router and docs. Do not combine them into this feature's commit or reset them.
- Delivery strategy: ask-on-risk. Forecast ~300 authored lines; update actual count after implementation.
- Next step: separate earlier staged location/transfer work into its own commit before committing this atomic registration unit; frontend form remains a separate future task.

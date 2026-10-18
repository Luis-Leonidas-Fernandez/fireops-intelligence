# Authenticate all inventory endpoints

## Objective
Require a valid local session and an existing user for every inventory endpoint, using one shared FastAPI authentication dependency.

## Scope and constraints
- Cover all ten operations across the five inventory routers, including reads and writes.
- Reuse the current session cookie and centralized `AuthenticationError` response; do not add roles or invitations.
- Preserve endpoint URLs, successful response shapes, location/transfer behavior, and existing staged work.
- No frontend changes or database migration. Work against `fireassets_test` only.

## Tasks
- [x] A1 — Add isolated RED tests for unauthenticated access to all inventory operations and authenticated compatibility. Route: delegated; multiple test files and fixtures. Evidence: 11 failures and 2 passes before implementation; 40 security cases pass after implementation.
- [x] A2 — Add shared auth dependency, attach it to inventory routers, and remove transfer-specific duplication. Route: delegated; multiple production files. Evidence: all five inventory routers use `require_authenticated_user`; transfer reuses the injected user.
- [x] A3 — Run focused/full checks, update architecture/progress docs, inspect diff, and record delivery evidence. Route: delegated verification and inline state inspection. Evidence: 116 Python tests passed against `fireassets_test`; Ruff check and scoped format check passed; mypy passed for 34 source files; `git diff --check` passed.

## Acceptance criteria
- Missing, invalid, expired, or orphan-user session receives HTTP 401 with centralized `AUTH_REQUIRED` error from every inventory route.
- Authenticated requests retain existing successful behavior.
- The shared dependency performs authentication and user lookup; endpoint handlers do not duplicate it.
- Tests are isolated and cannot persist test users or inventory data outside `fireassets_test`.

## Verification and delivery
- Test-first RED/GREEN and full Python suite; Ruff, mypy, and `git diff --check`.
- Forecast ~350 authored changed lines; ask-on-risk delivery strategy.
- Commit pending: earlier inventory-location/transfer changes are staged and overlap files in this unit; do not mix them.
- The requested full-directory Ruff format check finds a pre-existing missing final newline in `app/modules/inventory/register_category/schemas.py` (outside the authorized edit surface). All changed Python files pass the scoped format check.
- Runtime scenario: `pytest` exercised FastAPI endpoints through `ASGITransport` with both authenticated and unauthenticated clients. Rollback boundary: the shared auth dependency, router-level dependency declarations, and inventory auth tests/fixtures can be removed independently of the earlier staged location/transfer changes.
- The authenticated client fixture owns the HTTPX lifecycle with `async with` and yields an open client; endpoint tests reuse it without re-entering it. Follow-up verification: 68 inventory tests and 116 total Python tests passed, plus Ruff, mypy, and `git diff --check`.

# Auth SRP refactor

## Objective

Separate registration-request HTTP transport, use-case coordination, persistence, authorization, and public-link construction without changing existing behavior or database schema.

## Constraints

- Work only in the audited auth/config/docs/test surfaces on `codex/auth-srp-refactor`.
- Preserve per-request `AsyncSession`, OAuth state/nonce/PKCE, existing HTTP contracts, and transaction order.
- Do not edit models, migrations, Google/Gmail adapters, or unrelated local changes.
- Do not commit, merge, or push without additional authorization.

## Tasks

- [x] T1: Add focused regression tests and observe a failing pre-implementation result. Route: delegated writer; tests plus source require coordinated analysis. RED: two tests failed for missing link builder and router-to-router import.
- [x] T2: Move use-case coordination to workflows, policy and link construction out of routers; retain contracts. Route: delegated writer; multiple non-trivial files. GREEN: focused auth tests 47 passed.
- [x] T3: Document PUBLIC_BASE_URL and the existing email-before-commit risk. Route: delegated writer; documentation accompanies the behavior. Updated `.env.example`, registration setup, and backend architecture.
- [x] T4: Run focused and full regression checks, static import check, and `git diff --check`. Route: delegated writer; verification evidence required. Backend 224 passed against verified `fireassets_test`, frontend 16 passed, Ruff passed, router-import test passed, `git diff --check` passed.

## Acceptance

- No router module imports another router module.
- Public links derive only from a validated `PUBLIC_BASE_URL`; missing/invalid configuration reports a controlled error without secrets.
- Public requests commit before best-effort notice; approval sends before commit and rolls back on delivery failure.
- Before and after test results are recorded; no real provider calls or test database migrations occur.

## Baseline

- Backend: 219 passed against verified `fireassets_test`.
- Frontend: 16 passed.
- `git diff --check`: passed before this refactor.

## Progress

The initial 36-file work unit is committed as `264fa17101d2f7d3bbcfa975a8feed11abfe4da2`. The follow-up auth SRP work unit was committed with 17 paths (16 SRP paths plus `.gitignore`). No merge, push, migration, real Google call, or real Gmail send has occurred.

Independent review found that an empty trailing `?` or `#` in `PUBLIC_BASE_URL` could produce a malformed link. Both delimiters are now rejected and covered by the link-validation test. After this correction, the backend suite passed (258 tests) against the verified `fireassets_test` database, frontend passed (16 tests), and Ruff on `app` and `tests` passed. Repo-wide Ruff reports an existing `I001` in `migrations/env.py`, outside this refactor; `git diff --check` passed.

The existing Gmail adapter still emits `ApplicationError` with an HTTP status; it was explicitly excluded from this refactor. Approval still sends before commit, leaving a risk of an unusable delivered link if that commit fails. A separate delivery/outbox design would be required to change this ordering.

Rollback boundary: revert only the second (auth SRP) work-unit commit; preserve the first commit (`264fa17101d2f7d3bbcfa975a8feed11abfe4da2`) and the unrelated local DOCX.

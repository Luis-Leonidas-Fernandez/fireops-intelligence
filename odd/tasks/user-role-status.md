# Add modeled user role and active state

## Objective
Reflect the existing physical model's `roles` catalog, `usuarios.rol_id`, and `usuarios.activo` in documentation first, then in SQLAlchemy and a safe Alembic migration. This is a schema foundation, not role enforcement or invitations.

## Original problem
`User` originally had neither role nor active state. The physical model and RNF-SEG-02/03 require role-based access, but implementing permissions before a compatible schema would create inconsistent behavior.

## Scope and constraints
- Preserve existing users and Google-only accounts (`password_hash` remains nullable).
- Seed stable roles `ADMINISTRADOR` and `SUPERVISOR` without granting one automatically to existing accounts.
- Add `rol_id` as nullable for this transitional migration; a later controlled backfill and invitation rollout can make it mandatory. Add `activo` as non-null with default true.
- The physical model already specifies `roles` and the `usuarios.rol_id` / `usuarios.activo` relationship; the backend architecture page records the implemented schema, not role enforcement.
- Do not claim this schema migration enforces permissions. Existing inventory guards remain authentication-only until the next feature.
- Do not implement invitations, role administration, or frontend changes here.
- Verify the effective PostgreSQL database is `fireassets_test` before any migration/test that writes to a database. Never migrate `fireassets`.
- Preserve unrelated untracked DOCX and do not push or merge.

## Tasks
- [x] R1 — Document the transitional role/active schema and migration boundaries before editing production code. Route: delegated (documentation prepares multi-file implementation). Check: structural readback and `git diff --check` completed; see progress evidence below.
- [x] R2 — Add model and migration tests, observe a meaningful RED where possible, implement Role/User mappings and safe migration with seeded catalog. Route: delegated; model, migration, and tests. Check: focused tests against verified test DB.
- [x] R3 — Run full backend/frontend checks, Alembic current/check, Ruff and mypy; update progress documentation. Route: delegated verification and parent spot check. Commit remains pending.

## Acceptance criteria
- ORM and database have roles with unique name, description, active flag, and timestamps; users have nullable role FK and non-null active flag.
- Existing users remain present and active; no existing or newly registered user silently receives ADMINISTRADOR or SUPERVISOR.
- Google-only users still work with nullable password hash; existing auth behavior remains intact.
- Documentation distinguishes schema readiness from future permission enforcement and invitation-only registration.
- Only `fireassets_test` receives the migration locally and all applicable tests pass.

## Verification and delivery
- Completed: focused auth/migration tests, full Python suite, frontend tests, Alembic current/check, Ruff changed-file lint/format, mypy, git diff --check.
- Delivery strategy: ask-on-risk; forecast about 300 authored changed lines, not a hard limit.
- Runtime boundary: local ASGI/auth tests and PostgreSQL migration in `fireassets_test`; no frontend behavior changes.
- Rollback boundary: revert the new role migration, ORM mapping, tests, and matching documentation together; preserve current auth and inventory behavior.
- Commit pending; no push or merge has been performed.

## Progress evidence

- R1: `docs/architecture/backend/backend-architecture.md` now labels the physical-model schema as a proposal, records nullable `rol_id`, non-null/default-true `activo`, seeded role names, nullable Google-only `password_hash`, and the boundary before permission enforcement and invitations. Structural readback and `git diff --check` passed. No source code, migration, or database was changed in R1.
- R2: The effective URL and `SELECT current_database()` both identified `fireassets_test` before the only migration. Focused tests first failed at collection because `Role` did not exist (RED), then passed after implementation (`4 passed in 0.08s`). Alembic upgraded `c15b4e3d9a20` to `e7d4c2f9a621`; `alembic current` reports the new head and `alembic check` reports no upgrade operations. The two pre-existing users remain active and unassigned (`2/2` for both), including one Google-only account with a null password hash. Ruff check/format, mypy auth, and `git diff --check` passed. R2 touched only the ORM model, migration, focused tests, and this tracker. At this stage, R3 full checks and commit evidence remained pending.

- Correction: User explicitly limited the initial seed to `ADMINISTRADOR` and `SUPERVISOR`; `CARGA` was removed from the migration and, after verifying the effective URL and actual database were `fireassets_test` and that it had zero assignments, its seed row alone was deleted from that test database. The focused test no longer assumes all pre-existing users have null roles.
- R3: After a fresh effective-URL and live `current_database()` guard confirmed `fireassets_test`, focused Python tests passed (4), full Python tests passed (137), and Alembic reported `e7d4c2f9a621 (head)` with no new upgrade operations. Frontend Node tests passed (12). Ruff check and format check passed for both changed Python files; mypy passed for 14 auth source files; `git diff --check` passed. An initial bare `pytest` invocation failed during import because `app` was absent from its import path; rerunning via `python -m pytest` resolved the invocation issue. No staging or commit was performed in this work unit.

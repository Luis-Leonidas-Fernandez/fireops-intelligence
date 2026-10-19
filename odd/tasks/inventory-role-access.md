# Inventory role access

## Objective and scope

Require an active authenticated user with an active `ADMINISTRADOR` or `SUPERVISOR` role for all existing inventory endpoints. Assign the two explicitly selected accounts in local `fireassets_test`: `test1@gmail.com` as `ADMINISTRADOR` and `reviewer@example.com` as `SUPERVISOR`. Do not change registration, login, invitations, or other databases.

## Constraints and approach

- Reuse the existing `require_authenticated_user` dependency shared by every inventory router; do not add a second guard to each endpoint.
- Keep unauthenticated requests at `401` and return a controlled `403` for authenticated users without an active allowed role.
- Keep fixture-created users isolated in the existing rollback transaction; give them an allowed test role explicitly.
- Before touching account rows, verify the configured and actual database are both `fireassets_test` and that target accounts and roles are unique.
- Route: delegated direct, because implementation and tests touch multiple non-trivial files. Forecast: approximately 220 authored changed lines; the 400-line heuristic is advisory only.

## Checklist and evidence

- [x] T1: Added tests for both allowed roles on all eleven inventory endpoints, plus missing/inactive/unapproved roles and inactive accounts. Before implementation, the new negative cases produced 33 failures while the two positive cases passed.
- [x] T2: Centralized the `403` guard in the existing auth dependency and updated inventory test users to receive an explicit supervisor role. Inventory suite: `151 passed`.
- [x] T3: Verified the configured and actual database were both `fireassets_test`; in one transaction assigned the two exact active accounts to their requested active roles. Read-only post-check confirmed both assignments.
- [x] T4: Updated backend architecture documentation. Full pytest suite: `203 passed`; Ruff check passed; isolated mypy (`--follow-imports=skip`) passed; `git diff --check` passed. Broad mypy reports three existing `app/main.py` exception-handler signature errors outside this edit surface. Work-unit commit: pending.

## Checks

- `ENV_FILE=.env.test`, with `DATABASE_URL` unset; verify configured URL and `SELECT current_database()` before tests.
- `.venv/bin/python -m pytest -q tests/modules/inventory`
- `.venv/bin/python -m pytest -q`
- Ruff and mypy on affected Python files, if installed/configured.
- `git diff --check`

## Next step

Record the work-unit commit and leave push/merge to the project owner. Rollback boundary: revert the guard, error class, fixture/test and documentation changes in this work unit; the two local database assignments must be changed separately in `fireassets_test` if a rollback is requested.

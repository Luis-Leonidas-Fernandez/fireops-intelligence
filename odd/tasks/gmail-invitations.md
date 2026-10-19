# Gmail invitations (superseded)

> Superseded by `odd/tasks/registration-approval.md`. The staged admin-issued flow described below is being replaced by applicant-initiated approval; completion and acceptance claims below describe the earlier staged candidate, not the desired feature.


## Objective

Only an active administrator can invite a specific email as `ADMINISTRADOR` or `SUPERVISOR`. New password and Google accounts require a one-use, expiring invitation. Existing accounts continue to sign in.

## Constraints

- Keep Google identity OAuth scopes unchanged; Gmail sending uses separately authorized `gmail.send` offline refresh credentials.
- Never expose invitation token hashes, refresh credentials, or provider responses in logs.
- Never run migrations against `fireassets`; migration and tests require a verified `fireassets_test` destination.
- Preserve existing users, account-linking rules, and current inventory permissions.
- Route: delegated direct; one writer because backend, frontend, migration, tests, and docs are nontrivial. Forecast exceeds 400 authored lines because both signup paths and isolated tests are required; the heuristic is advisory.

## Work units

- [x] INV-1: Added invitation persistence, Gmail adapter, and admin-only API. Mocked send, unauthorized access, missing config, and provider failure are tested.
- [x] INV-2: Gated password and first-time Google registration atomically; the registration page carries the token in JSON or POST body, and the signed OAuth flow carries only its hash. Invalid, expired, reused, mismatched, and successful cases are tested.
- [x] INV-3: Documented private setup and verified the complete backend/frontend suites against only the verified test DB. Manual Gmail delivery remains pending until the sender's offline `gmail.send` refresh token is configured.

## Verification evidence

- Before the migration, confirmed both effective URL database and `SELECT current_database()` equal `fireassets_test`; then upgraded only that database to `f09a6e2112b4`.
- `ENV_FILE=.env.test .venv/bin/python -m pytest -q`: 210 passed. `node --test frontend/tests/*.test.cjs`: 14 passed.
- Ruff check passed for changed Python files; mypy `--follow-imports=skip` passed for eleven changed source files; `alembic check` reported no new upgrade operations; `git diff --check` passed.
- A live Gmail send was intentionally skipped: no sender refresh token was provided to this task. Existing unrelated untracked DOCX was preserved.
- Commit evidence: pending. Rollback boundary: revert invitation migration/model, issuance/delivery modules, registration gates/UI, matching tests, and setup docs as one coherent feature; local test DB migration requires a separate downgrade only if explicitly chosen.

## Acceptance

- `POST /auth/invitations` sends a minimal text email only for an active administrator and returns a controlled error if Gmail is unavailable.
- A token is high-entropy, stored only as a hash, bound to one normalized email and a seeded role, expires after 48 hours, and is consumed once in the same transaction as account creation.
- Existing password and linked Google sign-in continue unchanged; first-time registration without a valid invitation is rejected.
- Automated tests never contact Gmail and remain isolated in `fireassets_test`.

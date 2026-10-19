# Self-requested registration approval

## Objective
Anyone can request registration without creating a usable account. An active administrator reviews the request in the authenticated app; approval sends the applicant a one-use signup link for password or Google registration.

## Constraints and scope
- Replace staged admin-issued invitations, not unrelated authentication or inventory architecture.
- Notification recipient is configurable; do not hardcode an email, expose account existence, store a pending password or OAuth token, or mutate on an email GET.
- Approved accounts receive the active SUPERVISOR role. Preserve hash-only invitation tokens, expiry, and atomic consumption.
- `f09a6e2112b4` is already applied on `fireassets_test`; use a forward migration, never rewrite the old revision or touch `fireassets`.
- Preserve the unrelated untracked DOCX and staged user work. No live Gmail send, commit, push, or deployment is authorized.
- Route: delegated direct, one writer. Forecast: over 400 authored changed lines because persistence, public/admin flows, UI, tests, and documentation change together. The per-task line heuristic is advisory.
- Delivery strategy: ask-on-risk; no PR or remote delivery is in scope.

## Work units
- [x] RA-1 — Persist pending requests and expose generic public request API with bounded duplicate/cooldown behavior; notify configured administrator safely. Acceptance: no account or signup token from a public request; responses do not reveal account existence; tests cover duplicates and failures. Route: delegated (backend and tests).
- [x] RA-2 — Add authenticated admin list/approve/reject; approval sends hash-only one-use applicant link with controlled delivery failure. Acceptance: no GET mutation and no non-admin action; tests cover transitions and retries. Route: delegated (backend and tests).
- [x] RA-3 — Wire password and Google request/signup UI, preserving state/nonce/PKCE and existing-account login. Acceptance: Google request identity is verified before persistence; both signup paths use the approved token; frontend and backend tests pass. Route: delegated (multiple files).
- [x] RA-4 — Update setup/architecture/progress docs and run complete applicable verification against verified `fireassets_test`. Acceptance: no real Gmail delivery claim; record exact check results, skipped checks, rollback boundary. Route: delegated (multiple docs and verification).

## Scoped P2 corrections
- [x] RA-P2-1 — An approved, unused but expired invite can return to pending review after cooldown; active invites and registered accounts cannot. Observed RED: renewal test failed; GREEN: focused regression passed.
- [x] RA-P2-2 — A failed Gmail notice retains the pending row and returns the same generic `202` as an existing account. A pending request may retry one notice per 15-minute cooldown. Observed RED: new email returned `503` while existing returned `202`; GREEN: focused regressions passed.
- Per-origin/global abuse hardening remains a separate follow-up; it is not included in this scoped correction.
- After P2 corrections, reconfirmed effective URL and `SELECT current_database()` both equal `fireassets_test`; `ENV_FILE=.env.test .venv/bin/python -m pytest -q`: 219 passed. Ruff check, Ruff format check (4 files formatted), and staged/unstaged `git diff --check`: passed. No schema change or real Gmail send.

## Verification and progress
- RA-1 RED: public endpoint returned 404 (1 failed); GREEN: `tests/modules/auth/test_registration_requests.py` 2 passed after implementation.
- Confirmed effective URL database and `SELECT current_database()` both equal `fireassets_test`; applied forward revision `a4d9c2b7e631` only there.
- RA-2: admin list/approve/reject, authorization, replay rejection, no-token reject, and Gmail rollback tested; focused `test_registration_requests.py`: 6 passed.
- RA-3: Google request state rejection and verified callback tested; password/Google token signup covered by existing suites; frontend request behavior tested. Node suite: 16 passed.
- Prior to P2 corrections: `ENV_FILE=.env.test .venv/bin/python -m pytest -q`: 216 passed; `/opt/homebrew/bin/node --test frontend/tests/*.test.cjs`: 16 passed; Ruff check passed; Ruff format check: 14 files already formatted; mypy `--follow-imports=skip`: 11 source files clean; Alembic check: no new upgrade operations; staged and unstaged `git diff --check`: passed.
- Live Gmail delivery: not authorized or tested.
- Commit evidence: parent handles delivery; no writer commit.
- Rollback boundary: reverse the new registration-request migration and remove the approval request routes/UI, while preserving the already-applied invitation migration and unrelated user files.
- Engram mirror: synchronized after each completed work unit; final readback verified.

## Next step
P2 checks complete; parent owns review and delivery. Configure `REGISTRATION_ADMIN_EMAIL` privately and obtain explicit authorization before any real Gmail send; no writer commit was made.

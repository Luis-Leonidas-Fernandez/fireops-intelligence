# Google OAuth return to registration requests

## Objective
After an unauthenticated visitor opens `/solicitudes`, preserve that fixed internal destination through Google sign-in and return there after success. Direct sign-in continues to `/`.

## Problem and scope
`/solicitudes` currently redirects to login without a destination; the Google callback always redirects successful sign-in to `/`. Keep the existing signed OAuth state, nonce, PKCE, session cookie and review authorization. Allow only the fixed `/solicitudes` return target; all other requested destinations fall back to `/`. Concurrent attempts must not mix destinations or invalidate the newer flow when an older callback arrives.

## Constraints
- Work on the authorized `codex/auth-srp-refactor` branch and preserve unrelated local edits. The eight local commits were rebuilt with a verified noreply identity; a local backup ref is retained.
- Do not alter roles, registration requests, invitations, review decisions, `.env`, `.env.test`, PostgreSQL schema, or migrations.
- No real Google sign-in or email in automated tests. The user authorizes a sanitized commit, fast-forward integration to `main`, and push to `origin/main`; no migrations, deployment, or force-push are authorized.
- Verification may use the existing transactional `fireassets_test` fixtures only after confirming the effective database.

## Tasks
- [x] T1 — Add focused regression tests for retained destination, direct-login fallback, rejected external destinations, OAuth state mismatch and concurrent starts. Route: delegated; backend RED reproduced all three missing behaviors.
- [x] T2 — Implement the minimal route, signed-flow and login-button changes. Route: delegated; return target is signed and limited to `/solicitudes`; stale state mismatch neither uses the flow's source nor clears its cookie.
- [x] T3 — Run affected backend/frontend tests and structural checks; report real-browser verification separately. Route: delegated verification; updated only the stale redirect expectation in `tests/modules/auth/test_registration_requests.py`, then reran the affected backend suite successfully. Real-browser verification remains manual.

## Acceptance criteria
- `/solicitudes` → login → mocked successful Google OAuth returns `/solicitudes`.
- Direct Google login returns `/`; external, scheme-relative or manipulated destinations never become redirect targets.
- Invalid state remains rejected and cannot consume a newer concurrent flow; a valid newer flow still succeeds.
- Authorized `/solicitudes` access remains 200; unauthorized access remains 403.
- Existing signed state, nonce, PKCE and cookie behavior remain intact.
- No test data persists, no real email is sent, and the eight commits/local changes are preserved.

## Verification
- Baseline and RED/GREEN: focused pytest cases under `tests/modules/auth/test_google_oauth.py` and `tests/test_main_endpoints.py`, plus `frontend/tests/auth-form.test.cjs` if frontend runner is available.
- Regression: affected authentication suite against confirmed `fireassets_test`, frontend tests, Ruff and `git diff --check`.
- Real Google browser login is manual and must not be claimed from mocks.

## Progress
Implementation and affected verification complete. Baseline passed: 36 backend tests and 11 frontend tests. RED reproduced the missing `/solicitudes` login return, unrestricted target behavior and stale-flow cookie deletion. GREEN passed: 3 focused backend regressions, then 39 focused backend tests. An existing assertion outside the focused files required an expected-redirect update; the affected backend suite then passed 124 tests. Final verification passed: 275 backend tests, 18 frontend tests, Ruff for `app` and `tests`, and `git diff --check`; the database was confirmed as `fireassets_test`. Outbound network access was blocked. Whole-repository Ruff has a previously observed import-order failure at `migrations/env.py:20`. The user confirmed earlier that the OAuth browser flow was exercised; this agent did not run a live browser test. Commit and push remain pending parent confirmation. The eight local commits were rebuilt with a verified noreply identity, and a local backup ref is retained. No migrations or deployment were performed. Gentle AI assessment was unassessable with existing untracked files, and its read-only preflight failed safely due to sandbox permission; no native review started.

## Next step
No implementation work remains. Commit, fast-forward integration, and push are pending parent confirmation under the user's authorization.

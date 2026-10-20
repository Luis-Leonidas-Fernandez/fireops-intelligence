# Registration request review policy

## Objective
Allow only the designated, verified account to review registration requests while keeping ADMINISTRADOR and SUPERVISOR equivalent for inventory operations.

## Problem and scope
The review guard must bind reviewer authority to one verified Google subject, not a published mailbox value. Registration notices use a separately configured private recipient. The authorized change is limited to reviewer authorization, notice routing, focused tests, and required configuration documentation. Existing invitation delivery and HTTP contracts remain unchanged.

## Constraints
- Do not change database roles, models, or migrations.
- Do not add UI, bootstrap, or general role management.
- The user authorizes a sanitized commit, fast-forward integration to `main`, and push to `origin/main`.
- Do not run migrations, deploy, or force-push.
- Test only against a verified `fireassets_test` target.
- Fail closed when the designated account's trusted Google subject is not configured.

## Tasks
- [x] T1 (delegated): Bind reviewer identity only to the configured Google subject, while requiring an active user and active operational role. Preserve HTTP 403 and inventory permissions.
- [x] T2 (delegated): Send registration notices only to the privately configured recipient; keep requests pending and emit a sanitized operational error when configuration is missing. Changing the recipient does not change reviewer authority. Preserve applicant invitation delivery.
- [x] T3 (delegated): Add focused security and regression tests and document required configuration. Confirm effective test database before tests; report results and pending risks.

## Acceptance and checks
- Designated account can review as ADMINISTRADOR or SUPERVISOR; all other accounts, inactive accounts, invalid roles, and missing identity configuration are denied.
- Only the private `REGISTRATION_ADMIN_EMAIL` recipient receives pending-request notices. Changing it does not grant review authority; missing configuration keeps the request pending and reports an operational error.
- Approval, rejection, invitation-to-applicant, and existing HTTP contracts remain unchanged.
- Test database verified as `fireassets_test`; focused and full applicable backend checks, Ruff, and `git diff --check` reported honestly.

## Progress
The privacy correction is implemented. The two initial expected-denial fixture failures were corrected with distinct fictional Google subjects because the original fixtures used the configured reviewer subject. Final verification passed: 275 backend tests, 18 frontend tests, Ruff for `app` and `tests`, and `git diff --check`; the database was confirmed as `fireassets_test`. Outbound network access was blocked. The eight local commits were rebuilt with a verified noreply identity, and a local backup ref is retained. Commit and push remain pending parent confirmation. No migrations or deployment were performed. No live Google ownership or mail delivery was tested; the designated account's real Google subject must be verified out of band and configured privately before review is available.

## Route and forecast
Delegated direct: policy, settings, workflow, tests, and documentation are multiple non-trivial files. Approximately 250 authored changed lines expected. The user's authorized delivery is a sanitized commit followed by fast-forward integration and push; parent orchestration owns those Git operations.

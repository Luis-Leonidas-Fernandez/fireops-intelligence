# Registration approval

Applicants request access at `/registro`. Only the designated reviewer account receives a pending-request notification and may approve or reject at `/solicitudes`. Approval emails a one-use signup link to the applicant; opening the reviewer notification never approves anything.

## Local setup

1. Set the Gmail sender variables (`GMAIL_SENDER_EMAIL`, `GMAIL_REFRESH_TOKEN`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REDIRECT_URI`) in your private environment file. The sender refresh token requires separately authorized `gmail.send`; Google identity OAuth remains unchanged.
2. Set `PUBLIC_BASE_URL=http://127.0.0.1:8000` for the local application (or your deployed public origin). This must be an `http` or `https` origin only, without a path, query, fragment, or credentials. It is not a secret. Review links are no longer inferred from the Google callback URI. If this value is missing or invalid, approval returns a controlled configuration error before attempting delivery; a public request still returns its generic `202` after saving its pending row, but its best-effort notification cannot be sent.
3. Set `REGISTRATION_ADMIN_EMAIL` to the private mailbox that should receive pending-request notices. A missing value prevents the notice; the request remains pending and an operational error is logged without disclosing addresses. This notification destination does not grant review access. The applicant invitation still goes to the applicant after approval.
4. Set `REGISTRATION_REVIEWER_GOOGLE_SUB` to the exact Google subject (`google_sub`) already bound to the verified designated account in that environment. Confirm account ownership out of band before enabling review. A numeric user ID is not portable across databases. Never publish the real subject in `.env.example`, Git, logs, or screenshots. Missing or mismatched configuration denies review with the existing `403` contract.
5. Before a local migration, verify the effective settings URL database and `SELECT current_database()` are both `fireassets_test`. Then run `ENV_FILE=.env.test .venv/bin/alembic upgrade head`. Never apply the local test instructions to `fireassets`.
6. Sign in using the Google-linked account whose verified `google_sub` matches `REGISTRATION_REVIEWER_GOOGLE_SUB`. It must be active and hold an active `ADMINISTRADOR` or `SUPERVISOR` role. Neither role nor notification email alone grants review authority. The review page lists up to 100 pending requests and provides explicit approve/reject buttons.

## Behavior and boundaries

| Step | Behavior |
| --- | --- |
| Public password request | Sends email only; no password is collected or stored. Existing accounts, duplicates, and notification failures get the same generic `202` response. A failed or misconfigured notice leaves the request pending for review; retrying after 15 minutes sends at most one additional notice per cooldown window. |
| Google request | Completes the signed OAuth state, nonce, and PKCE flow before a request row is created; no raw OAuth tokens are stored. |
| Approval | Sends an expiring, one-use link for an active `SUPERVISOR` role. If Gmail delivery fails, the transaction rolls back and the request stays pending. |
| Renewal | After an approved link expires unused and the cooldown has passed, the applicant may request review again. Active links and registered accounts cannot be renewed. |
| Signup | Password or first-time Google signup consumes the token atomically. Existing accounts continue to sign in normally. |

The earlier `f09a6e2112b4` invitation migration is retained because it has been applied locally. `a4d9c2b7e631` adds request tracking as a forward revision. Automated tests mock Gmail; they do not prove live delivery. A real send requires separate sender authorization and an explicitly authorized manual test.

**Known transactional risk:** approval sends the applicant email before committing the invitation/request transaction. If Gmail succeeds but the database commit later fails, the delivered link may not resolve. This refactor preserves that ordering and rollback-on-delivery-failure behavior; it does not add an outbox or change the schema.

# Registration approval

Applicants request access at `/registro`. An administrator receives a review notification, signs in, and approves or rejects the request at `/solicitudes`. Approval emails a one-use signup link to the applicant; opening the administrator notification never approves anything.

## Local setup

1. Set the Gmail sender variables (`GMAIL_SENDER_EMAIL`, `GMAIL_REFRESH_TOKEN`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REDIRECT_URI`) in your private environment file. The sender refresh token requires separately authorized `gmail.send`; Google identity OAuth remains unchanged.
2. Set `REGISTRATION_ADMIN_EMAIL` to the administrator notification mailbox in your private `.env.test` for local testing. Do not put the actual address or credentials in `.env.example` or source control.
3. Before a local migration, verify the effective settings URL database and `SELECT current_database()` are both `fireassets_test`. Then run `ENV_FILE=.env.test .venv/bin/alembic upgrade head`. Never apply the local test instructions to `fireassets`.
4. Sign in with an active `ADMINISTRADOR` account before opening `/solicitudes`. The review page lists up to 100 pending requests and provides explicit approve/reject buttons.

## Behavior and boundaries

| Step | Behavior |
| --- | --- |
| Public password request | Sends email only; no password is collected or stored. Existing accounts, duplicates, and notification failures get the same generic `202` response. A failed notice leaves the request pending for manual administrator review; retrying the email after 15 minutes sends at most one additional notice per cooldown window. |
| Google request | Completes the signed OAuth state, nonce, and PKCE flow before a request row is created; no raw OAuth tokens are stored. |
| Approval | Sends an expiring, one-use link for an active `SUPERVISOR` role. If Gmail delivery fails, the transaction rolls back and the request stays pending. |
| Renewal | After an approved link expires unused and the cooldown has passed, the applicant may request review again. Active links and registered accounts cannot be renewed. |
| Signup | Password or first-time Google signup consumes the token atomically. Existing accounts continue to sign in normally. |

The earlier `f09a6e2112b4` invitation migration is retained because it has been applied locally. `a4d9c2b7e631` adds request tracking as a forward revision. Automated tests mock Gmail; they do not prove live delivery. A real send requires separate sender authorization and an explicitly authorized manual test.

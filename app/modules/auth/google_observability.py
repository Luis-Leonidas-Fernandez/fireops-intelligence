"""Safe, correlated audit events for the Google sign-in flow."""

import json
import logging
import secrets
from datetime import UTC, datetime
from typing import Literal

logger = logging.getLogger("uvicorn.error")

Stage = Literal["start", "callback", "token_exchange", "identity", "account"]
Outcome = Literal["started", "succeeded", "rejected", "failed"]
SAFE_REASONS = frozenset({
    "not_configured", "login_required", "missing_flow", "invalid_flow",
    "invalid_state", "provider_denied", "missing_code", "invalid_response",
    "missing_id_token", "provider_http_error", "transport_error",
    "invalid_subject", "unverified_email", "invalid_nonce", "verification_error",
    "GOOGLE_AUTH_FAILED", "GOOGLE_LOGIN_REQUIRED", "GOOGLE_ACCOUNT_CONFLICT",
    "GOOGLE_LINK_REQUIRED", "GOOGLE_EMAIL_MISMATCH", "GOOGLE_ALREADY_LINKED",
})


def new_attempt_id() -> str:
    # This identifier is independent of OAuth state, nonce, and PKCE verifier.
    return secrets.token_hex(12)


def observe_google_auth(
    stage: Stage,
    outcome: Outcome,
    attempt_id: str,
    *,
    reason: str | None = None,
    http_status: int | None = None,
) -> None:
    """Emit only allowlisted metadata; never include provider/user payloads."""
    if len(attempt_id) != 24 or any(char not in "0123456789abcdef" for char in attempt_id):
        attempt_id = "untracked"
    event: dict[str, str | int] = {
        "event": "google_oauth",
        "timestamp": datetime.now(UTC).isoformat(),
        "attempt_id": attempt_id,
        "stage": stage,
        "outcome": outcome,
    }
    if reason is not None:
        event["reason"] = reason if reason in SAFE_REASONS else "unspecified"
    if http_status is not None and 100 <= http_status <= 599:
        event["http_status"] = http_status
    logger.log(
        logging.WARNING if outcome in {"rejected", "failed"} else logging.INFO,
        json.dumps(event, separators=(",", ":")),
    )

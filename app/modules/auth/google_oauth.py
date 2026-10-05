"""Provider-facing Google OpenID Connect operations."""

import base64
import hashlib
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from fastapi.concurrency import run_in_threadpool
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token

from app.config.settings import Settings
from app.modules.auth.google_observability import observe_google_auth
from app.modules.auth.validations.credentials import (
    normalize_display_name,
    normalize_email,
)

AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


class GoogleOAuthFailure(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class GoogleIdentity:
    sub: str
    email: str
    display_name: str | None = None


def create_authorization_url(
    settings: Settings, *, state: str, nonce: str, verifier: str
) -> str:
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    return AUTHORIZATION_ENDPOINT + "?" + urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": "openid profile email",
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )


async def exchange_code(
    code: str, verifier: str, settings: Settings, *, attempt_id: str = "untracked"
) -> str:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                TOKEN_ENDPOINT,
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": settings.google_redirect_uri,
                    "grant_type": "authorization_code",
                    "code_verifier": verifier,
                },
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                observe_google_auth("token_exchange", "failed", attempt_id, reason="invalid_response")
                raise GoogleOAuthFailure("GOOGLE_AUTH_FAILED")
            token = payload.get("id_token")
            if not isinstance(token, str) or not token:
                observe_google_auth("token_exchange", "failed", attempt_id, reason="missing_id_token")
                raise GoogleOAuthFailure("GOOGLE_AUTH_FAILED")
            observe_google_auth("token_exchange", "succeeded", attempt_id)
            return token
    except (httpx.HTTPError, ValueError, TypeError) as error:
        if isinstance(error, httpx.HTTPStatusError):
            observe_google_auth(
                "token_exchange", "failed", attempt_id,
                reason="provider_http_error", http_status=error.response.status_code,
            )
        else:
            observe_google_auth(
                "token_exchange", "failed", attempt_id,
                reason="transport_error" if isinstance(error, httpx.HTTPError) else "invalid_response",
            )
        raise GoogleOAuthFailure("GOOGLE_AUTH_FAILED") from error


async def verify_identity(
    token: str, nonce: str, settings: Settings, *, attempt_id: str = "untracked"
) -> GoogleIdentity:
    try:
        claims = await run_in_threadpool(
            id_token.verify_oauth2_token,
            token,
            GoogleRequest(),
            settings.google_client_id,
        )
        sub = claims.get("sub")
        email = claims.get("email")
        verified_claim = claims.get("email_verified")
        verified = verified_claim is True or verified_claim == "true"
        actual_nonce = claims.get("nonce")
        if not isinstance(sub, str) or not sub or len(sub) > 255:
            observe_google_auth("identity", "rejected", attempt_id, reason="invalid_subject")
            raise GoogleOAuthFailure("GOOGLE_AUTH_FAILED")
        if not isinstance(email, str) or not verified:
            observe_google_auth("identity", "rejected", attempt_id, reason="unverified_email")
            raise GoogleOAuthFailure("GOOGLE_AUTH_FAILED")
        if not isinstance(actual_nonce, str) or not secrets.compare_digest(actual_nonce, nonce):
            observe_google_auth("identity", "rejected", attempt_id, reason="invalid_nonce")
            raise GoogleOAuthFailure("GOOGLE_AUTH_FAILED")
        raw_name = claims.get("name")
        try:
            display_name = normalize_display_name(raw_name) if isinstance(raw_name, str) else None
        except ValueError:
            display_name = None
        identity = GoogleIdentity(
            sub=sub, email=normalize_email(email), display_name=display_name
        )
        observe_google_auth("identity", "succeeded", attempt_id)
        return identity
    except GoogleOAuthFailure:
        raise
    except Exception as error:
        # Keep crypto/network errors generic; exception text may contain provider data.
        observe_google_auth("identity", "failed", attempt_id, reason="verification_error")
        raise GoogleOAuthFailure("GOOGLE_AUTH_FAILED") from error

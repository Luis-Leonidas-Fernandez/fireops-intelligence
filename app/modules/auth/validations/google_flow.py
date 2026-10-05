"""Short-lived, signed browser flow state. Never contains provider tokens."""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from app.modules.auth.google_oauth import GoogleOAuthFailure
from app.modules.auth.google_observability import new_attempt_id

GOOGLE_FLOW_COOKIE = "fire_control_google_flow"
GOOGLE_FLOW_TTL = timedelta(minutes=5)


@dataclass(frozen=True)
class GoogleFlow:
    attempt_id: str
    state: str
    nonce: str
    verifier: str
    source: str
    flow: str
    user_id: int | None


def new_google_flow(flow: str, source: str, user_id: int | None) -> GoogleFlow:
    return GoogleFlow(
        attempt_id=new_attempt_id(),
        state=secrets.token_urlsafe(32),
        nonce=secrets.token_urlsafe(32),
        verifier=secrets.token_urlsafe(64),
        source=source,
        flow=flow,
        user_id=user_id,
    )


def encode_google_flow(flow: GoogleFlow, secret_key: str) -> str:
    return jwt.encode(
        {
            "type": "google_oauth",
            "attempt_id": flow.attempt_id,
            "state": flow.state,
            "nonce": flow.nonce,
            "verifier": flow.verifier,
            "source": flow.source,
            "flow": flow.flow,
            "user_id": flow.user_id,
            "exp": datetime.now(UTC) + GOOGLE_FLOW_TTL,
        },
        secret_key,
        algorithm="HS256",
    )


def decode_google_flow(token: str, secret_key: str) -> GoogleFlow:
    try:
        claims = jwt.decode(
            token,
            secret_key,
            algorithms=["HS256"],
            options={"require": ["type", "attempt_id", "state", "nonce", "verifier", "source", "flow", "exp"]},
        )
        if claims["type"] != "google_oauth":
            raise ValueError("Wrong token type")
        if claims["flow"] not in {"signin", "link"}:
            raise ValueError("Wrong flow")
        if claims["source"] not in {"login", "register", "dashboard"}:
            raise ValueError("Wrong source")
        if (claims["flow"] == "link") != (claims["source"] == "dashboard"):
            raise ValueError("Flow/source mismatch")
        user_id = claims.get("user_id")
        if claims["flow"] == "link" and (type(user_id) is not int or user_id <= 0):
            raise ValueError("Missing link user")
        for key in ("state", "nonce", "verifier"):
            if not isinstance(claims[key], str) or len(claims[key]) < 32:
                raise ValueError("Invalid flow value")
        attempt_id = claims["attempt_id"]
        if (
            not isinstance(attempt_id, str)
            or len(attempt_id) != 24
            or any(char not in "0123456789abcdef" for char in attempt_id)
        ):
            raise ValueError("Invalid attempt identifier")
        return GoogleFlow(
            attempt_id=attempt_id,
            state=claims["state"],
            nonce=claims["nonce"],
            verifier=claims["verifier"],
            source=claims["source"],
            flow=claims["flow"],
            user_id=user_id,
        )
    except (jwt.PyJWTError, KeyError, ValueError, TypeError) as error:
        raise GoogleOAuthFailure("GOOGLE_SESSION_EXPIRED") from error

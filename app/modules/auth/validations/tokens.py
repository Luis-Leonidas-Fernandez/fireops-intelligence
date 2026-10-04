from datetime import UTC, datetime, timedelta

import jwt

from app.shared.errors.authentication_error import AuthenticationError

ACCESS_TOKEN_COOKIE = "fire_control_access"
ACCESS_TOKEN_TTL = timedelta(minutes=30)
ALGORITHM = "HS256"


def create_access_token(
    user_id: int, secret_key: str, *, now: datetime | None = None
) -> str:
    issued_at = now or datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": issued_at,
        "exp": issued_at + ACCESS_TOKEN_TTL,
    }
    return jwt.encode(payload, secret_key, algorithm=ALGORITHM)


def validate_access_token(token: str, secret_key: str) -> int:
    try:
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=[ALGORITHM],
            options={"require": ["sub", "exp", "iat", "type"]},
        )
        if payload.get("type") != "access" or not str(payload["sub"]).isdigit():
            raise ValueError("Invalid token payload")
        return int(payload["sub"])
    except (jwt.PyJWTError, ValueError, TypeError) as error:
        raise AuthenticationError(
            code="INVALID_TOKEN",
            message="Tu sesión no es válida o expiró. Iniciá sesión nuevamente.",
        ) from error

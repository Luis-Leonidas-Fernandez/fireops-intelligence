import base64
import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Self
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.main import app
from app.modules.auth import google_oauth
from app.modules.auth import router as auth_router
from app.modules.auth.google_oauth import GoogleIdentity, GoogleOAuthFailure
from app.modules.auth.google_observability import observe_google_auth
from app.modules.auth.models import User
from app.modules.auth.validations.google_flow import (
    GOOGLE_FLOW_COOKIE,
    decode_google_flow,
)
from app.modules.auth.validations.tokens import (
    ACCESS_TOKEN_COOKIE,
    validate_access_token,
)


def email() -> str:
    return f"google-{uuid4().hex}@example.test"


def test_settings_repr_does_not_expose_secrets() -> None:
    settings = get_settings().model_copy(update={
        "secret_key": "local-app-secret-for-unit-test-only",
        "google_client_secret": "local-google-secret-for-unit-test-only",
    })

    assert "local-app-secret-for-unit-test-only" not in repr(settings)
    assert "local-google-secret-for-unit-test-only" not in repr(settings)


@pytest.fixture
def google_provider(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    settings = get_settings().model_copy(
        update={
            "google_client_id": "web-client-id.example",
            "google_client_secret": "test-secret-not-real",
            "google_redirect_uri": "http://127.0.0.1:8000/auth/google/callback",
        }
    )
    monkeypatch.setattr(auth_router, "get_settings", lambda: settings)
    identity: dict[str, object] = {
        "sub": f"google-{uuid4().hex}",
        "email": email(),
        "display_name": "Bombera de Prueba",
        "nonce": None,
    }

    async def exchange(
        code: str, verifier: str, configured: object, *, attempt_id: str
    ) -> str:
        assert code == "one-time-code"
        assert len(verifier) >= 43
        assert len(attempt_id) == 24
        assert configured is settings
        return "provider-id-token"

    async def verify(
        token: str, nonce: str, configured: object, *, attempt_id: str
    ) -> GoogleIdentity:
        assert token == "provider-id-token"
        assert len(attempt_id) == 24
        assert configured is settings
        assert nonce == identity["nonce"]
        return GoogleIdentity(
            sub=str(identity["sub"]), email=str(identity["email"]),
            display_name=str(identity["display_name"]),
        )

    monkeypatch.setattr(auth_router, "exchange_code", exchange)
    monkeypatch.setattr(auth_router, "verify_identity", verify)
    return identity


def google_events(caplog: pytest.LogCaptureFixture) -> list[dict[str, object]]:
    return [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "uvicorn.error" and record.message.startswith('{"event":"google_oauth"')
    ]


def test_google_observability_redacts_untrusted_fields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="uvicorn.error")
    observe_google_auth(
        "token_exchange", "failed", "user-supplied-state",
        reason="secret=must-not-appear", http_status=400,
    )

    event = google_events(caplog)[0]
    assert isinstance(event.pop("timestamp"), str)
    assert event == {
        "event": "google_oauth", "attempt_id": "untracked",
        "stage": "token_exchange", "outcome": "failed",
        "reason": "unspecified", "http_status": 400,
    }
    assert "must-not-appear" not in caplog.text


@pytest.mark.asyncio
async def test_google_observability_correlates_start_and_callback(
    auth_session: AsyncSession,
    google_provider: dict[str, object],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="uvicorn.error")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        state, google_provider["nonce"] = await start_google(client)
        completed = await finish_google(client, state)

    assert completed.headers["location"] == "/"
    events = google_events(caplog)
    assert [(event["stage"], event["outcome"]) for event in events] == [
        ("start", "started"), ("account", "started"),
        ("account", "succeeded"), ("callback", "succeeded"),
    ]
    assert len({event["attempt_id"] for event in events}) == 1
    assert state not in caplog.text
    assert str(google_provider["email"]) not in caplog.text


@pytest.mark.asyncio
async def test_google_observability_marks_state_rejection(
    auth_session: AsyncSession,
    google_provider: dict[str, object],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="uvicorn.error")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        state, google_provider["nonce"] = await start_google(client)
        rejected = await finish_google(client, "bad-state")

    assert rejected.headers["location"] == "/iniciar-sesion?auth_error=GOOGLE_SESSION_EXPIRED"
    events = google_events(caplog)
    assert events[-1]["reason"] == "invalid_state"
    assert events[-1]["attempt_id"] == events[0]["attempt_id"]
    assert state not in caplog.text


async def start_google(client: AsyncClient, *, flow: str = "signin", source: str = "login") -> tuple[str, str]:
    response = await client.get(f"/auth/google/start?flow={flow}&source={source}")
    assert response.status_code == 303
    assert GOOGLE_FLOW_COOKIE in response.cookies
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=lax" in response.headers["set-cookie"].lower()
    params = parse_qs(urlparse(response.headers["location"]).query)
    assert params["scope"] == ["openid profile email"]
    assert params["code_challenge_method"] == ["S256"]
    assert params["redirect_uri"] == ["http://127.0.0.1:8000/auth/google/callback"]
    flow_cookie = decode_google_flow(
        client.cookies[GOOGLE_FLOW_COOKIE], get_settings().secret_key
    )
    expected_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(flow_cookie.verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    assert params["code_challenge"] == [expected_challenge]
    return params["state"][0], params["nonce"][0]


async def finish_google(client: AsyncClient, state: str) -> object:
    return await client.get(
        "/auth/google/callback", params={"state": state, "code": "one-time-code"}
    )


@pytest.mark.asyncio
async def test_google_signup_and_repeat_login_use_one_local_account(
    auth_session: AsyncSession, google_provider: dict[str, object]
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        state, google_provider["nonce"] = await start_google(client, source="register")
        first = await finish_google(client, state)
        assert first.status_code == 303
        assert first.headers["location"] == "/"
        assert "Max-Age=1800" in first.headers["set-cookie"]
        user_id = validate_access_token(
            first.cookies[ACCESS_TOKEN_COOKIE], get_settings().secret_key
        )
        user = await auth_session.get(User, user_id)
        assert user is not None
        assert user.password_hash is None
        assert user.google_sub == google_provider["sub"]
        assert user.email == google_provider["email"]
        assert user.display_name == "Bombera de Prueba"

        state, google_provider["nonce"] = await start_google(client)
        second = await finish_google(client, state)
        assert second.status_code == 303
        assert validate_access_token(
            second.cookies[ACCESS_TOKEN_COOKIE], get_settings().secret_key
        ) == user_id
        assert len((await auth_session.scalars(
            select(User).where(User.google_sub == google_provider["sub"])
        )).all()) == 1

        # Google email can change; its stable subject still identifies this user.
        google_provider["email"] = email()
        state, google_provider["nonce"] = await start_google(client)
        changed_email = await finish_google(client, state)
        assert validate_access_token(
            changed_email.cookies[ACCESS_TOKEN_COOKIE], get_settings().secret_key
        ) == user_id
        await auth_session.refresh(user)
        assert user.email != google_provider["email"]

        password_login = await client.post(
            "/auth/login", json={"email": user.email, "password": "ClaveSegura123"}
        )
        assert password_login.status_code == 401
        assert password_login.json()["error"]["code"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_google_login_fills_missing_name_without_overwriting_existing_name(
    auth_session: AsyncSession, google_provider: dict[str, object]
) -> None:
    user = User(
        email=str(google_provider["email"]), password_hash=None,
        google_sub=str(google_provider["sub"]), display_name=None,
    )
    auth_session.add(user)
    await auth_session.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        state, google_provider["nonce"] = await start_google(client)
        assert (await finish_google(client, state)).headers["location"] == "/"
        assert (await client.get("/auth/me")).json()["display_name"] == "Bombera de Prueba"
        google_provider["display_name"] = "Nombre cambiado en Google"
        state, google_provider["nonce"] = await start_google(client)
        assert (await finish_google(client, state)).headers["location"] == "/"
        assert (await client.get("/auth/me")).json()["display_name"] == "Bombera de Prueba"


@pytest.mark.asyncio
async def test_existing_password_account_requires_explicit_link(
    auth_session: AsyncSession, google_provider: dict[str, object]
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        registered = await client.post(
            "/auth/register",
            json={"email": google_provider["email"], "password": "ClaveSegura123"},
        )
        assert registered.status_code == 201
        await client.post("/auth/logout")
        state, google_provider["nonce"] = await start_google(client)
        refused = await finish_google(client, state)
        assert refused.headers["location"] == "/iniciar-sesion?auth_error=GOOGLE_LINK_REQUIRED"
        user = await auth_session.scalar(select(User).where(User.email == google_provider["email"]))
        assert user is not None and user.google_sub is None

        signed_in = await client.post(
            "/auth/login",
            json={"email": google_provider["email"], "password": "ClaveSegura123"},
        )
        assert signed_in.status_code == 200
        state, google_provider["nonce"] = await start_google(client, flow="link")
        linked = await finish_google(client, state)
        assert linked.headers["location"] == "/?auth_status=GOOGLE_LINKED"
        await auth_session.refresh(user)
        assert user.google_sub == google_provider["sub"]

        await client.post("/auth/logout")
        state, google_provider["nonce"] = await start_google(client)
        again = await finish_google(client, state)
        assert again.headers["location"] == "/"


@pytest.mark.asyncio
async def test_link_requires_session_and_matching_verified_email(
    auth_session: AsyncSession, google_provider: dict[str, object]
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        unauthenticated = await client.get("/auth/google/start?flow=link")
        assert unauthenticated.headers["location"] == "/iniciar-sesion?auth_error=GOOGLE_LOGIN_REQUIRED"
        registered = await client.post(
            "/auth/register", json={"email": email(), "password": "ClaveSegura123"}
        )
        user_id = registered.json()["user"]["id"]
        state, google_provider["nonce"] = await start_google(client, flow="link")
        mismatch = await finish_google(client, state)
        assert mismatch.headers["location"] == "/?auth_error=GOOGLE_EMAIL_MISMATCH"
        assert (await auth_session.get(User, user_id)).google_sub is None


@pytest.mark.asyncio
async def test_link_rejects_other_provider_account_and_other_session(
    auth_session: AsyncSession, google_provider: dict[str, object]
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(
            "/auth/register", json={"email": google_provider["email"], "password": "ClaveSegura123"}
        )
        state, google_provider["nonce"] = await start_google(client, flow="link")
        await client.post("/auth/logout")
        lost_session = await finish_google(client, state)
        assert lost_session.headers["location"] == "/iniciar-sesion?auth_error=GOOGLE_LOGIN_REQUIRED"
        assert (await auth_session.get(User, first.json()["user"]["id"])).google_sub is None

        await client.post(
            "/auth/login", json={"email": google_provider["email"], "password": "ClaveSegura123"}
        )
        state, google_provider["nonce"] = await start_google(client, flow="link")
        assert (await finish_google(client, state)).headers["location"] == "/?auth_status=GOOGLE_LINKED"
        state, google_provider["nonce"] = await start_google(client, flow="link")
        assert (await finish_google(client, state)).headers["location"] == "/?auth_status=GOOGLE_LINKED"
        google_provider["sub"] = f"other-{uuid4().hex}"
        state, google_provider["nonce"] = await start_google(client, flow="link")
        refused = await finish_google(client, state)
        assert refused.headers["location"] == "/?auth_error=GOOGLE_ALREADY_LINKED"


@pytest.mark.asyncio
async def test_google_subject_cannot_be_linked_to_two_users(
    auth_session: AsyncSession, google_provider: dict[str, object]
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        state, google_provider["nonce"] = await start_google(client)
        created = await finish_google(client, state)
        first_id = validate_access_token(
            created.cookies[ACCESS_TOKEN_COOKIE], get_settings().secret_key
        )
        await client.post("/auth/logout")
        google_provider["email"] = email()
        second = await client.post(
            "/auth/register",
            json={"email": google_provider["email"], "password": "ClaveSegura123"},
        )
        second_id = second.json()["user"]["id"]
        state, google_provider["nonce"] = await start_google(client, flow="link")
        rejected = await finish_google(client, state)
        assert rejected.headers["location"] == "/?auth_error=GOOGLE_ACCOUNT_CONFLICT"
        assert (await auth_session.get(User, first_id)).google_sub == google_provider["sub"]
        assert (await auth_session.get(User, second_id)).google_sub is None


@pytest.mark.asyncio
async def test_google_state_and_provider_denial_are_rejected(
    auth_session: AsyncSession, google_provider: dict[str, object]
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        state, google_provider["nonce"] = await start_google(client)
        wrong = await finish_google(client, "wrong-state")
        assert wrong.headers["location"] == "/iniciar-sesion?auth_error=GOOGLE_SESSION_EXPIRED"
        state, google_provider["nonce"] = await start_google(client)
        denied = await client.get(
            "/auth/google/callback", params={"state": state, "error": "access_denied"}
        )
        assert denied.headers["location"] == "/iniciar-sesion?auth_error=GOOGLE_ACCESS_DENIED"
        missing = await client.get("/auth/google/callback?state=not-valid&code=x")
        assert missing.headers["location"] == "/iniciar-sesion?auth_error=GOOGLE_SESSION_EXPIRED"


@pytest.mark.asyncio
async def test_google_flow_cookie_is_signed_and_expires(
    auth_session: AsyncSession, google_provider: dict[str, object]
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        state, google_provider["nonce"] = await start_google(client)
        token = client.cookies[GOOGLE_FLOW_COOKIE]
        flow = decode_google_flow(token, get_settings().secret_key)
        assert flow.state == state
        assert flow.nonce == google_provider["nonce"]
        assert flow.verifier
        altered = token[:-2] + ("AA" if token[-2:] != "AA" else "BB")
        client.cookies.set(GOOGLE_FLOW_COOKIE, altered, path="/auth/google")
        rejected = await finish_google(client, state)
        assert rejected.headers["location"] == "/iniciar-sesion?auth_error=GOOGLE_SESSION_EXPIRED"

        expired = jwt.encode(
            {**jwt.decode(token, get_settings().secret_key, algorithms=["HS256"]),
             "exp": datetime.now(UTC) - timedelta(seconds=1)},
            get_settings().secret_key,
            algorithm="HS256",
        )
        client.cookies.set(GOOGLE_FLOW_COOKIE, expired, path="/auth/google")
        rejected = await finish_google(client, state)
        assert rejected.headers["location"] == "/iniciar-sesion?auth_error=GOOGLE_SESSION_EXPIRED"


@pytest.mark.asyncio
async def test_google_config_missing_does_not_break_password_login(
    auth_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings().model_copy(update={
        "google_client_id": None, "google_client_secret": None, "google_redirect_uri": None
    })
    monkeypatch.setattr(auth_router, "get_settings", lambda: settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        unavailable = await client.get("/auth/google/start")
        assert unavailable.headers["location"] == "/iniciar-sesion?auth_error=GOOGLE_NOT_CONFIGURED"
        registered = await client.post(
            "/auth/register", json={"email": email(), "password": "ClaveSegura123"}
        )
        assert registered.status_code == 201


@pytest.mark.asyncio
@pytest.mark.parametrize("claims", [
    {"email_verified": False},
    {"email_verified": "false"},
    {"email_verified": 1},
    {"nonce": "another-nonce"},
    {"sub": ""},
    {"email": "not-an-email"},
])
async def test_google_identity_rejects_invalid_claims(
    claims: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    valid = {
        "sub": "stable-google-sub", "email": email(), "email_verified": True,
        "nonce": "expected-nonce",
    }
    monkeypatch.setattr(
        google_oauth.id_token, "verify_oauth2_token", lambda *args: {**valid, **claims}
    )
    settings = get_settings().model_copy(update={"google_client_id": "web-client-id.example"})
    with pytest.raises(GoogleOAuthFailure):
        await google_oauth.verify_identity("token", "expected-nonce", settings)


@pytest.mark.asyncio
async def test_google_identity_accepts_verified_email_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    google_email = email()
    monkeypatch.setattr(
        google_oauth.id_token,
        "verify_oauth2_token",
        lambda *_args: {
            "sub": "stable-google-sub",
            "email": google_email,
            "email_verified": "true",
            "nonce": "expected-nonce",
        },
    )
    settings = get_settings().model_copy(update={"google_client_id": "web-client-id.example"})

    identity = await google_oauth.verify_identity("token", "expected-nonce", settings)

    assert identity == GoogleIdentity(sub="stable-google-sub", email=google_email)


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["wrong audience", "expired", "invalid signature"])
async def test_google_identity_rejects_provider_verification_errors(
    reason: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def reject(*_args: object) -> None:
        raise ValueError(reason)

    monkeypatch.setattr(google_oauth.id_token, "verify_oauth2_token", reject)
    settings = get_settings().model_copy(update={"google_client_id": "web-client-id.example"})
    with pytest.raises(GoogleOAuthFailure) as failure:
        await google_oauth.verify_identity("token", "nonce", settings)
    assert failure.value.code == "GOOGLE_AUTH_FAILED"


@pytest.mark.asyncio
async def test_real_google_token_verifier_checks_signature_audience_issuer_and_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    jwk.update({"kid": "local-test-key", "use": "sig"})
    monkeypatch.setattr(
        google_oauth.id_token, "_fetch_certs", lambda *_args: {"keys": [jwk]}
    )
    settings = get_settings().model_copy(update={"google_client_id": "web-client-id.example"})
    claims = {
        "iss": "https://accounts.google.com",
        "aud": settings.google_client_id,
        "sub": "verified-sub",
        "email": "PERSON@EXAMPLE.TEST",
        "email_verified": True,
        "nonce": "expected-nonce",
        "iat": int(datetime.now(UTC).timestamp()),
        "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
    }

    def signed(payload: dict[str, object]) -> str:
        return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": "local-test-key"})

    identity = await google_oauth.verify_identity(signed(claims), "expected-nonce", settings)
    assert identity == GoogleIdentity(sub="verified-sub", email="person@example.test")
    named_identity = await google_oauth.verify_identity(
        signed({**claims, "name": "  Ana   Pérez  "}), "expected-nonce", settings
    )
    assert named_identity.display_name == "Ana Pérez"
    for mutation in (
        {"aud": "another-client"},
        {"iss": "https://attacker.example"},
        {"exp": int((datetime.now(UTC) - timedelta(minutes=1)).timestamp())},
    ):
        with pytest.raises(GoogleOAuthFailure):
            await google_oauth.verify_identity(
                signed({**claims, **mutation}), "expected-nonce", settings
            )

    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode(
        claims, other_key, algorithm="RS256", headers={"kid": "local-test-key"}
    )
    with pytest.raises(GoogleOAuthFailure):
        await google_oauth.verify_identity(forged, "expected-nonce", settings)


@pytest.mark.asyncio
async def test_google_token_exchange_failure_is_controlled(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FailingClient:
        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def post(self, *_args: object, **_kwargs: object) -> None:
            raise google_oauth.httpx.TimeoutException("timeout")

    monkeypatch.setattr(google_oauth.httpx, "AsyncClient", lambda **_kwargs: FailingClient())
    settings = get_settings().model_copy(update={
        "google_client_id": "client", "google_client_secret": "test-secret",
        "google_redirect_uri": "http://127.0.0.1:8000/auth/google/callback",
    })
    with pytest.raises(GoogleOAuthFailure) as failure:
        await google_oauth.exchange_code("code", "verifier", settings)
    assert failure.value.code == "GOOGLE_AUTH_FAILED"
    assert google_events(caplog)[-1]["reason"] == "transport_error"
    assert "test-secret" not in caplog.text


@pytest.mark.asyncio
async def test_google_token_exchange_logs_status_without_provider_body(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class RejectedClient:
        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def post(self, *_args: object, **_kwargs: object) -> google_oauth.httpx.Response:
            return google_oauth.httpx.Response(
                400,
                json={"error_description": "secret-provider-detail"},
                request=google_oauth.httpx.Request("POST", google_oauth.TOKEN_ENDPOINT),
            )

    monkeypatch.setattr(google_oauth.httpx, "AsyncClient", lambda **_kwargs: RejectedClient())
    settings = get_settings().model_copy(update={
        "google_client_id": "client", "google_client_secret": "secret-local-test",
        "google_redirect_uri": "http://127.0.0.1:8000/auth/google/callback",
    })

    with pytest.raises(GoogleOAuthFailure):
        await google_oauth.exchange_code("one-time-code", "verifier", settings)

    event = google_events(caplog)[-1]
    assert event["stage"] == "token_exchange"
    assert event["http_status"] == 400
    assert event["reason"] == "provider_http_error"
    assert "secret-provider-detail" not in caplog.text
    assert "secret-local-test" not in caplog.text
    assert "one-time-code" not in caplog.text

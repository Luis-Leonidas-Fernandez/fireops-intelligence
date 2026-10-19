"""Invitation boundary tests; Gmail is always replaced by a local fake."""

import base64
from datetime import UTC, datetime, timedelta
from email import message_from_bytes
from uuid import uuid4

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.main import app
from app.modules.auth.invitations import mail
from app.modules.auth.models import Invitation, RegistrationRequest, Role, User
from app.shared.errors.application_error import ApplicationError
from tests.modules.auth.conftest import create_test_invitation


def address() -> str:
    return f"invite-{uuid4().hex}@example.test"


@pytest.mark.asyncio
async def test_password_registration_requires_matching_unused_invitation(
    auth_session: AsyncSession,
) -> None:
    email = address()
    token = await create_test_invitation(auth_session, email, "SUPERVISOR")
    other = address()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        missing = await client.post(
            "/auth/register", json={"email": email, "password": "ClaveSegura123"}
        )
        mismatch = await client.post(
            "/auth/register",
            json={
                "email": other,
                "password": "ClaveSegura123",
                "invitation_token": token,
            },
        )
        created = await client.post(
            "/auth/register",
            json={
                "email": email.upper(),
                "password": "ClaveSegura123",
                "invitation_token": token,
            },
        )
        replay = await client.post(
            "/auth/register",
            json={
                "email": other,
                "password": "ClaveSegura123",
                "invitation_token": token,
            },
        )
    assert missing.status_code == mismatch.status_code == replay.status_code == 403
    assert created.status_code == 201
    user = await auth_session.scalar(select(User).where(User.email == email))
    role = await auth_session.scalar(select(Role).where(Role.nombre == "SUPERVISOR"))
    assert user is not None and role is not None and user.rol_id == role.id
    invite = await auth_session.scalar(
        select(Invitation).where(Invitation.email == email)
    )
    assert invite is not None and invite.used_at is not None
    # Removing the account does not make its one-time invitation reusable.
    await auth_session.delete(user)
    await auth_session.commit()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        used = await client.post(
            "/auth/register",
            json={
                "email": email,
                "password": "ClaveSegura123",
                "invitation_token": token,
            },
        )
    assert used.status_code == 403


@pytest.mark.asyncio
async def test_expired_invitation_rejected(auth_session: AsyncSession) -> None:
    email = address()
    token = await create_test_invitation(auth_session, email)
    invitation = await auth_session.scalar(
        select(Invitation).where(Invitation.email == email)
    )
    assert invitation is not None
    invitation.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await auth_session.commit()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        result = await client.post(
            "/auth/register",
            json={
                "email": email,
                "password": "ClaveSegura123",
                "invitation_token": token,
            },
        )
    assert result.status_code == 403
    assert result.json()["error"]["code"] == "INVITATION_INVALID"
    assert await auth_session.scalar(select(User.id).where(User.email == email)) is None


@pytest.mark.asyncio
async def test_unconfigured_gmail_keeps_generic_pending_request(
    auth_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.modules.auth.invitations.router.get_settings",
        lambda: get_settings().model_copy(update={"gmail_refresh_token": None}),
    )
    target = address()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        result = await client.post(
            "/auth/registration-requests", json={"email": target}
        )
    assert result.status_code == 202
    assert result.json() == {
        "message": "Si corresponde, recibirás novedades por correo."
    }
    pending = await auth_session.scalar(
        select(RegistrationRequest).where(RegistrationRequest.email == target)
    )
    assert pending is not None and pending.status == "pending"


@pytest.mark.asyncio
async def test_gmail_adapter_refreshes_sender_and_sends_minimal_plain_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings().model_copy(
        update={
            "google_client_id": "client-id",
            "google_client_secret": "client-secret",
            "google_redirect_uri": "http://127.0.0.1:8000/auth/google/callback",
            "gmail_sender_email": "sender@example.test",
            "gmail_refresh_token": "sender-refresh",
        }
    )
    monkeypatch.setattr(mail, "get_settings", lambda: settings)
    calls: list[tuple[str, dict[str, object]]] = []

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url: str, **kwargs: object) -> httpx.Response:
            calls.append((url, kwargs))
            payload = (
                {"access_token": "access-only-for-test"}
                if url == mail.TOKEN_URL
                else {"id": "provider-message-id"}
            )
            return httpx.Response(200, json=payload, request=httpx.Request("POST", url))

    monkeypatch.setattr(mail.httpx, "AsyncClient", lambda **_kwargs: Client())
    await mail.send_invitation_email(
        "recipient@example.test", "http://127.0.0.1:8000/registro#invite=example"
    )
    assert [call[0] for call in calls] == [mail.TOKEN_URL, mail.SEND_URL]
    assert calls[0][1]["data"]["refresh_token"] == "sender-refresh"
    assert calls[1][1]["headers"]["Authorization"] == "Bearer access-only-for-test"
    encoded = calls[1][1]["json"]["raw"]
    message = message_from_bytes(base64.urlsafe_b64decode(encoded))
    assert message["To"] == "recipient@example.test"
    assert message.get_content_type() == "text/plain"
    assert "#invite=example" in message.get_payload(decode=True).decode()


@pytest.mark.asyncio
async def test_gmail_provider_failure_is_controlled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings().model_copy(
        update={
            "google_client_id": "client-id",
            "google_client_secret": "client-secret",
            "google_redirect_uri": "http://127.0.0.1:8000/auth/google/callback",
            "gmail_sender_email": "sender@example.test",
            "gmail_refresh_token": "sender-refresh",
        }
    )
    monkeypatch.setattr(mail, "get_settings", lambda: settings)

    class RejectedClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url: str, **_kwargs: object) -> httpx.Response:
            return httpx.Response(403, request=httpx.Request("POST", url))

    monkeypatch.setattr(mail.httpx, "AsyncClient", lambda **_kwargs: RejectedClient())
    with pytest.raises(ApplicationError) as failure:
        await mail.send_invitation_email(
            "recipient@example.test", "http://127.0.0.1:8000/registro#invite=x"
        )
    assert getattr(failure.value, "code", None) == "INVITATION_DELIVERY_UNAVAILABLE"

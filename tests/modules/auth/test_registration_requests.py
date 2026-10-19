"""Applicant-initiated registration review boundaries."""

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.main import app
from app.modules.auth.models import User


@pytest.mark.asyncio
async def test_public_request_is_generic_and_creates_no_user(
    auth_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent = []

    async def fake_notice(email: str, link: str) -> None:
        sent.append((email, link))

    settings = get_settings().model_copy(
        update={
            "google_client_id": "client",
            "google_client_secret": "secret",
            "google_redirect_uri": "http://127.0.0.1:8000/auth/google/callback",
            "gmail_sender_email": "sender@example.test",
            "gmail_refresh_token": "refresh",
            "registration_admin_email": "admin@example.test",
        }
    )
    monkeypatch.setattr(
        "app.modules.auth.invitations.router.get_settings", lambda: settings
    )
    monkeypatch.setattr(
        "app.modules.auth.invitations.router.send_registration_notice", fake_notice
    )
    email = f"request-{uuid4().hex}@example.test"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        result = await client.post("/auth/registration-requests", json={"email": email})
    assert result.status_code == 202
    assert result.json() == {
        "message": "Si corresponde, recibirás novedades por correo."
    }
    assert await auth_session.scalar(select(User.id).where(User.email == email)) is None
    assert sent == [("admin@example.test", "http://127.0.0.1:8000/solicitudes")]


@pytest.mark.asyncio
async def test_duplicate_and_existing_account_requests_are_indistinguishable(
    auth_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.auth.models import RegistrationRequest

    settings = get_settings().model_copy(
        update={
            "google_client_id": "client",
            "google_client_secret": "secret",
            "google_redirect_uri": "http://127.0.0.1:8000/auth/google/callback",
            "gmail_sender_email": "sender@example.test",
            "gmail_refresh_token": "refresh",
            "registration_admin_email": "admin@example.test",
        }
    )
    sent: list[str] = []

    async def fake_notice(email: str, link: str) -> None:
        sent.append(link)

    monkeypatch.setattr(
        "app.modules.auth.invitations.router.get_settings", lambda: settings
    )
    monkeypatch.setattr(
        "app.modules.auth.invitations.router.send_registration_notice", fake_notice
    )
    email = f"repeat-{uuid4().hex}@example.test"
    existing = User(
        email=f"existing-{uuid4().hex}@example.test", password_hash="not-used"
    )
    auth_session.add(existing)
    existing_email = existing.email
    await auth_session.commit()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.post("/auth/registration-requests", json={"email": email})
        again = await client.post("/auth/registration-requests", json={"email": email})
        known = await client.post(
            "/auth/registration-requests", json={"email": existing_email}
        )
    assert first.status_code == again.status_code == known.status_code == 202
    assert first.json() == again.json() == known.json()
    assert len(sent) == 1
    rows = (
        await auth_session.scalars(
            select(RegistrationRequest).where(RegistrationRequest.email == email)
        )
    ).all()
    assert len(rows) == 1 and rows[0].status == "pending"


@pytest.mark.asyncio
async def test_admin_review_requires_login_and_issues_supervisor_link(
    auth_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from urllib.parse import urlsplit

    from app.modules.auth.invitations.service import token_digest
    from app.modules.auth.models import Invitation, RegistrationRequest, Role
    from app.modules.auth.validations.tokens import (
        ACCESS_TOKEN_COOKIE,
        create_access_token,
    )

    settings = get_settings().model_copy(
        update={
            "google_client_id": "client",
            "google_client_secret": "secret",
            "google_redirect_uri": "http://127.0.0.1:8000/auth/google/callback",
            "gmail_sender_email": "sender@example.test",
            "gmail_refresh_token": "refresh",
            "registration_admin_email": "admin@example.test",
        }
    )
    sent: list[tuple[str, str]] = []

    async def fake_invitation(email: str, link: str) -> None:
        sent.append((email, link))

    monkeypatch.setattr(
        "app.modules.auth.invitations.router.get_settings", lambda: settings
    )
    monkeypatch.setattr(
        "app.modules.auth.invitations.router.send_invitation_email", fake_invitation
    )
    admin_role = await auth_session.scalar(
        select(Role).where(Role.nombre == "ADMINISTRADOR")
    )
    supervisor_role = await auth_session.scalar(
        select(Role).where(Role.nombre == "SUPERVISOR")
    )
    assert admin_role and supervisor_role
    admin = User(email=f"admin-{uuid4().hex}@example.test", rol_id=admin_role.id)
    supervisor = User(
        email=f"super-{uuid4().hex}@example.test", rol_id=supervisor_role.id
    )
    target = f"approval-{uuid4().hex}@example.test"
    item = RegistrationRequest(
        email=target,
        status="pending",
        source="password",
        requested_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
    )
    auth_session.add_all((admin, supervisor, item))
    await auth_session.flush()
    ids = admin.id, supervisor.id, item.id
    supervisor_role_id = supervisor_role.id
    await auth_session.commit()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        anonymous = await client.get("/auth/registration-requests")
        client.cookies.set(
            ACCESS_TOKEN_COOKIE, create_access_token(ids[1], get_settings().secret_key)
        )
        forbidden = await client.post(
            f"/auth/registration-requests/{ids[2]}/review",
            json={"decision": "approved"},
        )
        client.cookies.set(
            ACCESS_TOKEN_COOKIE, create_access_token(ids[0], get_settings().secret_key)
        )
        listed = await client.get("/auth/registration-requests")
        approved = await client.post(
            f"/auth/registration-requests/{ids[2]}/review",
            json={"decision": "approved"},
        )
        repeated = await client.post(
            f"/auth/registration-requests/{ids[2]}/review",
            json={"decision": "approved"},
        )
    assert anonymous.status_code == 401
    assert forbidden.status_code == 403
    assert listed.status_code == 200 and any(
        row["id"] == ids[2] for row in listed.json()
    )
    assert approved.status_code == 200 and repeated.status_code == 409
    assert len(sent) == 1 and sent[0][0] == target
    token = urlsplit(sent[0][1]).fragment.removeprefix("invite=")
    stored = await auth_session.scalar(
        select(Invitation).where(Invitation.token_hash == token_digest(token))
    )
    assert stored and stored.email == target and stored.rol_id == supervisor_role_id


@pytest.mark.asyncio
async def test_rejection_never_issues_signup_token(auth_session: AsyncSession) -> None:
    from datetime import UTC, datetime

    from app.modules.auth.models import Invitation, RegistrationRequest, Role
    from app.modules.auth.validations.tokens import (
        ACCESS_TOKEN_COOKIE,
        create_access_token,
    )

    admin_role = await auth_session.scalar(
        select(Role).where(Role.nombre == "ADMINISTRADOR")
    )
    assert admin_role
    admin = User(email=f"admin-{uuid4().hex}@example.test", rol_id=admin_role.id)
    target = f"rejected-{uuid4().hex}@example.test"
    item = RegistrationRequest(
        email=target,
        source="password",
        status="pending",
        requested_at=datetime.now(UTC),
    )
    auth_session.add_all((admin, item))
    await auth_session.flush()
    admin_id, request_id = admin.id, item.id
    await auth_session.commit()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.cookies.set(
            ACCESS_TOKEN_COOKIE,
            create_access_token(admin_id, get_settings().secret_key),
        )
        result = await client.post(
            f"/auth/registration-requests/{request_id}/review",
            json={"decision": "rejected"},
        )
    assert result.status_code == 200
    await auth_session.refresh(item)
    assert item.status == "rejected"
    assert (
        await auth_session.scalar(
            select(Invitation.id).where(Invitation.email == target)
        )
        is None
    )


@pytest.mark.asyncio
async def test_review_page_redirects_anonymous_and_rejects_non_admin(
    auth_session: AsyncSession,
) -> None:
    from app.modules.auth.models import Role
    from app.modules.auth.validations.tokens import (
        ACCESS_TOKEN_COOKIE,
        create_access_token,
    )

    role = await auth_session.scalar(select(Role).where(Role.nombre == "SUPERVISOR"))
    assert role
    person = User(email=f"review-{uuid4().hex}@example.test", rol_id=role.id)
    auth_session.add(person)
    await auth_session.flush()
    person_id = person.id
    await auth_session.commit()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        anonymous = await client.get("/solicitudes")
        client.cookies.set(
            ACCESS_TOKEN_COOKIE,
            create_access_token(person_id, get_settings().secret_key),
        )
        forbidden = await client.get("/solicitudes")
    assert (
        anonymous.status_code == 303
        and anonymous.headers["location"] == "/iniciar-sesion"
    )
    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_failed_approval_delivery_leaves_request_pending(
    auth_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime

    from app.modules.auth.invitations.mail import delivery_error
    from app.modules.auth.models import Invitation, RegistrationRequest, Role
    from app.modules.auth.validations.tokens import (
        ACCESS_TOKEN_COOKIE,
        create_access_token,
    )

    settings = get_settings().model_copy(
        update={
            "google_client_id": "client",
            "google_client_secret": "secret",
            "google_redirect_uri": "http://127.0.0.1:8000/auth/google/callback",
            "gmail_sender_email": "sender@example.test",
            "gmail_refresh_token": "refresh",
            "registration_admin_email": "admin@example.test",
        }
    )

    async def fail_send(email: str, link: str) -> None:
        raise delivery_error()

    monkeypatch.setattr(
        "app.modules.auth.invitations.router.get_settings", lambda: settings
    )
    monkeypatch.setattr(
        "app.modules.auth.invitations.router.send_invitation_email", fail_send
    )
    role = await auth_session.scalar(select(Role).where(Role.nombre == "ADMINISTRADOR"))
    assert role
    admin = User(email=f"admin-{uuid4().hex}@example.test", rol_id=role.id)
    target = f"failure-{uuid4().hex}@example.test"
    item = RegistrationRequest(
        email=target,
        source="password",
        status="pending",
        requested_at=datetime.now(UTC),
    )
    auth_session.add_all((admin, item))
    await auth_session.flush()
    admin_id, request_id = admin.id, item.id
    await auth_session.commit()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.cookies.set(
            ACCESS_TOKEN_COOKIE,
            create_access_token(admin_id, get_settings().secret_key),
        )
        failed = await client.post(
            f"/auth/registration-requests/{request_id}/review",
            json={"decision": "approved"},
        )
    assert failed.status_code == 503
    await auth_session.refresh(item)
    assert item.status == "pending"
    assert (
        await auth_session.scalar(
            select(Invitation.id).where(Invitation.email == target)
        )
        is None
    )


@pytest.mark.asyncio
async def test_expired_approval_can_request_review_again_but_active_link_cannot(
    auth_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime, timedelta

    from app.modules.auth.models import Invitation, RegistrationRequest, Role

    settings = get_settings().model_copy(
        update={
            "google_client_id": "client",
            "google_client_secret": "secret",
            "google_redirect_uri": "http://127.0.0.1:8000/auth/google/callback",
            "gmail_sender_email": "sender@example.test",
            "gmail_refresh_token": "refresh",
            "registration_admin_email": "admin@example.test",
        }
    )
    sent: list[str] = []

    async def fake_notice(email: str, link: str) -> None:
        sent.append(link)

    monkeypatch.setattr(
        "app.modules.auth.invitations.router.get_settings", lambda: settings
    )
    monkeypatch.setattr(
        "app.modules.auth.invitations.router.send_registration_notice", fake_notice
    )
    admin_role = await auth_session.scalar(
        select(Role).where(Role.nombre == "ADMINISTRADOR")
    )
    supervisor_role = await auth_session.scalar(
        select(Role).where(Role.nombre == "SUPERVISOR")
    )
    assert admin_role and supervisor_role
    admin = User(email=f"admin-{uuid4().hex}@example.test", rol_id=admin_role.id)
    expired_email = f"expired-{uuid4().hex}@example.test"
    active_email = f"active-{uuid4().hex}@example.test"
    old = datetime.now(UTC) - timedelta(days=3)
    expired = RegistrationRequest(
        email=expired_email,
        status="approved",
        source="password",
        requested_at=old,
        reviewed_at=old,
    )
    active = RegistrationRequest(
        email=active_email,
        status="approved",
        source="password",
        requested_at=old,
        reviewed_at=old,
    )
    auth_session.add_all((admin, expired, active))
    await auth_session.flush()
    auth_session.add_all(
        (
            Invitation(
                email=expired_email,
                token_hash=uuid4().hex + uuid4().hex,
                rol_id=supervisor_role.id,
                invited_by_id=admin.id,
                expires_at=datetime.now(UTC) - timedelta(hours=1),
            ),
            Invitation(
                email=active_email,
                token_hash=uuid4().hex + uuid4().hex,
                rol_id=supervisor_role.id,
                invited_by_id=admin.id,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            ),
        )
    )
    await auth_session.commit()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        renewed = await client.post(
            "/auth/registration-requests", json={"email": expired_email}
        )
        blocked = await client.post(
            "/auth/registration-requests", json={"email": active_email}
        )
    assert renewed.status_code == blocked.status_code == 202
    await auth_session.refresh(expired)
    await auth_session.refresh(active)
    assert expired.status == "pending"
    assert active.status == "approved"
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_notice_failure_keeps_pending_and_never_reveals_account_existence(
    auth_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.auth.invitations.mail import delivery_error
    from app.modules.auth.models import RegistrationRequest

    settings = get_settings().model_copy(
        update={
            "google_client_id": "client",
            "google_client_secret": "secret",
            "google_redirect_uri": "http://127.0.0.1:8000/auth/google/callback",
            "gmail_sender_email": "sender@example.test",
            "gmail_refresh_token": "refresh",
            "registration_admin_email": "admin@example.test",
        }
    )

    async def fail_notice(email: str, link: str) -> None:
        raise delivery_error()

    monkeypatch.setattr(
        "app.modules.auth.invitations.router.get_settings", lambda: settings
    )
    monkeypatch.setattr(
        "app.modules.auth.invitations.router.send_registration_notice", fail_notice
    )
    existing_email = f"existing-{uuid4().hex}@example.test"
    new_email = f"new-{uuid4().hex}@example.test"
    auth_session.add(User(email=existing_email))
    await auth_session.commit()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        new_result = await client.post(
            "/auth/registration-requests", json={"email": new_email}
        )
        known_result = await client.post(
            "/auth/registration-requests", json={"email": existing_email}
        )
    assert new_result.status_code == known_result.status_code == 202
    assert new_result.json() == known_result.json()
    row = await auth_session.scalar(
        select(RegistrationRequest).where(RegistrationRequest.email == new_email)
    )
    assert row is not None and row.status == "pending"


@pytest.mark.asyncio
async def test_pending_notice_retry_is_bounded_by_cooldown(
    auth_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime, timedelta

    from app.modules.auth.models import RegistrationRequest

    settings = get_settings().model_copy(
        update={
            "google_client_id": "client",
            "google_client_secret": "secret",
            "google_redirect_uri": "http://127.0.0.1:8000/auth/google/callback",
            "gmail_sender_email": "sender@example.test",
            "gmail_refresh_token": "refresh",
            "registration_admin_email": "admin@example.test",
        }
    )
    sent: list[str] = []

    async def fake_notice(email: str, link: str) -> None:
        sent.append(link)

    monkeypatch.setattr(
        "app.modules.auth.invitations.router.get_settings", lambda: settings
    )
    monkeypatch.setattr(
        "app.modules.auth.invitations.router.send_registration_notice", fake_notice
    )
    target = f"retry-{uuid4().hex}@example.test"
    row = RegistrationRequest(
        email=target,
        status="pending",
        source="password",
        requested_at=datetime.now(UTC) - timedelta(minutes=16),
    )
    auth_session.add(row)
    await auth_session.commit()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        retried = await client.post(
            "/auth/registration-requests", json={"email": target}
        )
        immediate = await client.post(
            "/auth/registration-requests", json={"email": target}
        )
    assert retried.status_code == immediate.status_code == 202
    assert len(sent) == 1
    await auth_session.refresh(row)
    assert row.status == "pending"

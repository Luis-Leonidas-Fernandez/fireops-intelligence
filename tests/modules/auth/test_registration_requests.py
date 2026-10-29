"""Applicant-initiated registration review boundaries."""

import ast
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.main import app
from app.modules.auth.models import User


@pytest.fixture(autouse=True)
def configured_reviewer(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.infrastructure.rate_limit.limiter import reset_rate_limit_storage
    from app.modules.auth.invitations import policy

    reset_rate_limit_storage()
    settings = get_settings().model_copy(
        update={"registration_reviewer_google_sub": "reviewer-sub-for-tests"}
    )
    monkeypatch.setattr(policy, "get_settings", lambda: settings)


def test_public_link_requires_explicit_safe_base_url() -> None:
    from app.modules.auth.invitations.errors import PublicBaseURLConfigurationError
    from app.modules.auth.invitations.links import public_link

    settings = get_settings()
    for invalid in (
        None,
        "",
        "not-a-url",
        "https://user:secret@example.test",
        "http://example.test?",
        "http://example.test#",
    ):
        with pytest.raises(PublicBaseURLConfigurationError) as failure:
            public_link(
                settings.model_copy(update={"public_base_url": invalid}), "/solicitudes"
            )
        assert "secret" not in str(failure.value)

    configured = settings.model_copy(
        update={"public_base_url": "http://127.0.0.1:8000"}
    )
    assert (
        public_link(configured, "/solicitudes") == "http://127.0.0.1:8000/solicitudes"
    )


@pytest.mark.parametrize(
    ("environment", "origin", "expected"),
    (
        ("production", "https://example.test", "https://example.test/solicitudes"),
        ("development", "http://localhost:8000", "http://localhost:8000/solicitudes"),
        ("test", "http://127.0.0.1:8000", "http://127.0.0.1:8000/solicitudes"),
        ("testing", "http://[::1]:8000", "http://[::1]:8000/solicitudes"),
    ),
)
def test_public_link_accepts_secure_or_local_test_origin(
    environment: str, origin: str, expected: str
) -> None:
    from app.modules.auth.invitations.links import public_link

    settings = get_settings().model_copy(
        update={"environment": environment, "public_base_url": origin}
    )
    assert public_link(settings, "/solicitudes") == expected


@pytest.mark.parametrize(
    ("environment", "origin"),
    (
        ("production", "http://example.test"),
        ("development", "http://example.test"),
        ("production", "http://localhost:8000"),
        ("production", "http://127.0.0.1:8000"),
        ("production", "http://[::1]:8000"),
        ("staging", "http://localhost:8000"),
        ("development", "http://localhost.evil.test"),
        ("development", "http://127.0.0.2"),
        ("development", "http://[::1%25eth0]"),
        ("development", "http://127.0.0.1.evil.test"),
        ("production", "https://user:secret@example.test"),
        ("production", "https://example.test?"),
        ("production", "https://example.test#"),
        ("production", "https://example.test/path"),
        ("production", "https://example.test/"),
        ("production", "https://example.test:invalid"),
        ("production", "https://example.test:0"),
        ("production", "https://example.test:65536"),
        ("production", "https://example.test:443:444"),
        ("production", "https://-bad.test"),
        ("production", "https://bad..test"),
        ("production", "https://example.test."),
        ("production", "https://example.test\\@evil.test"),
        ("production", "https://example.test%2Fevil.test"),
        ("production", "https://example.test\n.evil.test"),
        ("production", "https://example.test "),
        ("production", "ftp://example.test"),
    ),
)
def test_public_link_rejects_insecure_or_ambiguous_origin(
    environment: str, origin: str
) -> None:
    from app.modules.auth.invitations.errors import PublicBaseURLConfigurationError
    from app.modules.auth.invitations.links import public_link

    settings = get_settings().model_copy(
        update={"environment": environment, "public_base_url": origin}
    )
    with pytest.raises(PublicBaseURLConfigurationError) as failure:
        public_link(settings, "/solicitudes")
    assert "secret" not in str(failure.value)


def test_auth_routers_do_not_import_other_routers() -> None:
    root = Path(__file__).resolve().parents[3] / "app" / "modules" / "auth"
    for path in (root / "router.py", root / "invitations" / "router.py"):
        parsed = ast.parse(path.read_text())
        assert not any(
            isinstance(node, ast.ImportFrom)
            and node.module is not None
            and node.module.endswith(".router")
            for node in ast.walk(parsed)
        ), path


@pytest.mark.asyncio
async def test_public_request_commits_before_best_effort_notice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.auth.invitations import workflows

    events: list[str] = []

    class Session:
        async def commit(self) -> None:
            events.append("commit")

        async def rollback(self) -> None:
            events.append("rollback")

    async def create(*_args: object) -> object:
        events.append("create")
        return object()

    async def notice(_email: str, _link: str) -> None:
        events.append("notice")

    settings = get_settings().model_copy(
        update={
            "google_client_id": "client",
            "google_client_secret": "secret",
            "google_redirect_uri": "http://127.0.0.1:8000/auth/google/callback",
            "gmail_sender_email": "sender@example.test",
            "gmail_refresh_token": "refresh",
            "registration_admin_email": "reviewer@example.test",
            "public_base_url": "http://127.0.0.1:8000",
        }
    )
    monkeypatch.setattr(workflows, "get_settings", lambda: settings)
    monkeypatch.setattr(workflows, "create_registration_request", create)
    monkeypatch.setattr(workflows, "send_registration_notice", notice)
    await workflows.submit_request(Session(), "applicant@example.test", "password")  # type: ignore[arg-type]
    assert events == ["create", "commit", "notice"]


@pytest.mark.asyncio
async def test_missing_notice_recipient_keeps_request_and_logs_operational_error(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from app.modules.auth.invitations import workflows

    events: list[str] = []

    class Session:
        async def commit(self) -> None:
            events.append("commit")

        async def rollback(self) -> None:
            events.append("rollback")

    async def create(*_args: object) -> object:
        events.append("create")
        return object()

    async def unexpected_notice(_email: str, _link: str) -> None:
        pytest.fail("Invalid recipient must never receive a notice")

    settings = get_settings().model_copy(
        update={
            "registration_admin_email": None,
            "google_client_id": "client",
            "google_client_secret": "secret",
            "google_redirect_uri": "http://127.0.0.1:8000/auth/google/callback",
            "gmail_sender_email": "sender@example.test",
            "gmail_refresh_token": "refresh",
            "public_base_url": "http://127.0.0.1:8000",
        }
    )
    monkeypatch.setattr(workflows, "get_settings", lambda: settings)
    monkeypatch.setattr(workflows, "create_registration_request", create)
    monkeypatch.setattr(workflows, "send_registration_notice", unexpected_notice)
    with caplog.at_level("ERROR", logger="uvicorn.error"):
        await workflows.submit_request(Session(), "applicant@example.test", "password")  # type: ignore[arg-type]
    assert events == ["create", "commit"]
    assert (
        "registration_notice_unavailable: recipient_configuration_invalid"
        in caplog.text
    )
    assert "other-admin@example.test" not in caplog.text


@pytest.mark.asyncio
async def test_notice_uses_configured_recipient_independent_of_reviewer_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.auth.invitations import workflows

    sent: list[str] = []

    class Session:
        async def commit(self) -> None:
            return None

        async def rollback(self) -> None:
            return None

    async def create(*_args: object) -> object:
        return object()

    async def notice(email: str, _link: str) -> None:
        sent.append(email)

    settings = get_settings().model_copy(
        update={
            "registration_admin_email": "ops-notifications@example.test",
            "google_client_id": "client",
            "google_client_secret": "secret",
            "google_redirect_uri": "http://127.0.0.1:8000/auth/google/callback",
            "gmail_sender_email": "sender@example.test",
            "gmail_refresh_token": "refresh",
            "public_base_url": "http://127.0.0.1:8000",
        }
    )
    monkeypatch.setattr(workflows, "get_settings", lambda: settings)
    monkeypatch.setattr(workflows, "create_registration_request", create)
    monkeypatch.setattr(workflows, "send_registration_notice", notice)
    await workflows.submit_request(Session(), "applicant@example.test", "password")  # type: ignore[arg-type]
    assert sent == ["ops-notifications@example.test"]


@pytest.mark.asyncio
async def test_approval_sends_before_commit_and_rolls_back_on_delivery_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.auth.invitations import workflows
    from app.modules.auth.invitations.mail import delivery_error
    from app.shared.errors.application_error import ApplicationError

    events: list[str] = []

    class Session:
        async def commit(self) -> None:
            events.append("commit")

        async def rollback(self) -> None:
            events.append("rollback")

    async def review(*_args: object) -> tuple[object, str]:
        events.append("review")
        return SimpleNamespace(email="applicant@example.test"), "invite-token"

    async def reject_delivery(_email: str, _link: str) -> None:
        events.append("send")
        raise delivery_error()

    settings = get_settings().model_copy(
        update={
            "google_client_id": "client",
            "google_client_secret": "secret",
            "google_redirect_uri": "http://127.0.0.1:8000/auth/google/callback",
            "gmail_sender_email": "sender@example.test",
            "gmail_refresh_token": "refresh",
            "public_base_url": "http://127.0.0.1:8000",
        }
    )
    monkeypatch.setattr(workflows, "get_settings", lambda: settings)
    monkeypatch.setattr(workflows, "review_request", review)
    monkeypatch.setattr(workflows, "send_invitation_email", reject_delivery)
    with pytest.raises(ApplicationError) as failure:
        await workflows.review_registration_request(Session(), 1, 1, "approved")  # type: ignore[arg-type]
    assert failure.value.code == "INVITATION_DELIVERY_UNAVAILABLE"
    assert events == ["review", "send", "rollback"]


@pytest.mark.asyncio
async def test_approval_commit_failure_rolls_back_after_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.auth.invitations import workflows

    events: list[str] = []

    class Session:
        async def commit(self) -> None:
            events.append("commit")
            raise RuntimeError("controlled commit failure")

        async def rollback(self) -> None:
            events.append("rollback")

    async def review(*_args: object) -> tuple[object, str]:
        events.append("review")
        return SimpleNamespace(email="applicant@example.test"), "invite-token"

    async def send(_email: str, _link: str) -> None:
        events.append("send")

    settings = get_settings().model_copy(
        update={"environment": "test", "public_base_url": "http://127.0.0.1:8000"}
    )
    monkeypatch.setattr(workflows, "get_settings", lambda: settings)
    monkeypatch.setattr(workflows, "review_request", review)
    monkeypatch.setattr(workflows, "send_invitation_email", send)
    with pytest.raises(RuntimeError, match="controlled commit failure"):
        await workflows.review_registration_request(Session(), 1, 1, "approved")  # type: ignore[arg-type]
    assert events == ["review", "send", "commit", "rollback"]


@pytest.mark.asyncio
async def test_approval_with_outbox_enabled_rolls_back_without_delivery_on_commit_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies that M-02Transactional Outbox never sends emails when commit fails."""
    import base64

    from app.modules.auth.invitations import workflows

    events: list[str] = []

    class Session:
        def add(self, _entity: object) -> None:
            events.append("add")

        async def flush(self) -> None:
            events.append("flush")

        async def commit(self) -> None:
            events.append("commit")
            raise RuntimeError("controlled commit failure")

        async def rollback(self) -> None:
            events.append("rollback")

    async def review(*_args: object) -> tuple[object, str]:
        events.append("review")
        return SimpleNamespace(id=1, email="applicant@example.test"), "invite-token"

    async def send(_email: str, _link: str) -> None:
        events.append("send")

    key_b64 = base64.b64encode(b"\x07" * 32).decode("ascii")
    settings = get_settings().model_copy(
        update={
            "environment": "test",
            "public_base_url": "http://127.0.0.1:8000",
            "google_client_id": "client",
            "google_client_secret": "secret",
            "google_redirect_uri": "http://127.0.0.1:8000/auth/google/callback",
            "gmail_sender_email": "sender@example.test",
            "gmail_refresh_token": "refresh",
            "outbox_enabled": True,
            "outbox_encryption_key": key_b64,
            "outbox_encryption_key_id": "v1",
        }
    )
    monkeypatch.setattr(workflows, "get_settings", lambda: settings)
    monkeypatch.setattr(workflows, "review_request", review)
    monkeypatch.setattr(workflows, "send_invitation_email", send)
    with pytest.raises(RuntimeError, match="controlled commit failure"):
        await workflows.review_registration_request(Session(), 1, 1, "approved")  # type: ignore[arg-type]
    # Invariant: 'send' is NEVER called; outbox event added and flushed, then rolled back on commit failure
    assert "send" not in events
    assert events == ["review", "add", "flush", "commit", "rollback"]


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
            "registration_admin_email": "reviewer@example.test",
            "public_base_url": "http://127.0.0.1:8000",
        }
    )
    monkeypatch.setattr(
        "app.modules.auth.invitations.workflows.get_settings", lambda: settings
    )
    monkeypatch.setattr(
        "app.modules.auth.invitations.workflows.send_registration_notice", fake_notice
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
    assert sent == [("reviewer@example.test", "http://127.0.0.1:8000/solicitudes")]


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
            "registration_admin_email": "reviewer@example.test",
            "public_base_url": "http://127.0.0.1:8000",
        }
    )
    sent: list[str] = []

    async def fake_notice(email: str, link: str) -> None:
        sent.append(link)

    monkeypatch.setattr(
        "app.modules.auth.invitations.workflows.get_settings", lambda: settings
    )
    monkeypatch.setattr(
        "app.modules.auth.invitations.workflows.send_registration_notice", fake_notice
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
            "registration_admin_email": "reviewer@example.test",
            "public_base_url": "http://127.0.0.1:8000",
        }
    )
    sent: list[tuple[str, str]] = []

    async def fake_invitation(email: str, link: str) -> None:
        sent.append((email, link))

    monkeypatch.setattr(
        "app.modules.auth.invitations.workflows.get_settings", lambda: settings
    )
    monkeypatch.setattr(
        "app.modules.auth.invitations.router.get_settings", lambda: settings
    )
    monkeypatch.setattr(
        "app.modules.auth.invitations.workflows.send_invitation_email", fake_invitation
    )
    admin_role = await auth_session.scalar(
        select(Role).where(Role.nombre == "ADMINISTRADOR")
    )
    supervisor_role = await auth_session.scalar(
        select(Role).where(Role.nombre == "SUPERVISOR")
    )
    assert admin_role and supervisor_role
    admin = User(
        email="REVIEWER@EXAMPLE.TEST",
        google_sub="reviewer-sub-for-tests",
        rol_id=admin_role.id,
    )
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
    admin = User(
        email="REVIEWER@EXAMPLE.TEST",
        google_sub="reviewer-sub-for-tests",
        rol_id=admin_role.id,
    )
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
        and anonymous.headers["location"] == "/iniciar-sesion?next=%2Fsolicitudes"
    )
    assert forbidden.status_code == 403


@pytest.mark.parametrize("role_name", ("ADMINISTRADOR", "SUPERVISOR"))
@pytest.mark.parametrize("decision", ("approved", "rejected"))
@pytest.mark.asyncio
async def test_designated_reviewer_can_decide_with_either_operational_role(
    auth_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    role_name: str,
    decision: str,
) -> None:
    from datetime import UTC, datetime

    from app.modules.auth.models import RegistrationRequest, Role
    from app.modules.auth.validations.tokens import (
        ACCESS_TOKEN_COOKIE,
        create_access_token,
    )

    role = await auth_session.scalar(select(Role).where(Role.nombre == role_name))
    assert role is not None
    reviewer = User(
        email="REVIEWER@EXAMPLE.TEST",
        google_sub="reviewer-sub-for-tests",
        rol_id=role.id,
    )
    item = RegistrationRequest(
        email=f"applicant-{uuid4().hex}@example.test",
        source="password",
        status="pending",
        requested_at=datetime.now(UTC),
    )
    auth_session.add_all((reviewer, item))
    await auth_session.flush()
    reviewer_id, item_id = reviewer.id, item.id
    await auth_session.commit()

    async def fake_invitation(_email: str, _link: str) -> None:
        return None

    settings = get_settings().model_copy(
        update={
            "google_client_id": "client",
            "google_client_secret": "secret",
            "google_redirect_uri": "http://127.0.0.1:8000/auth/google/callback",
            "gmail_sender_email": "sender@example.test",
            "gmail_refresh_token": "refresh",
            "registration_admin_email": "ops-notifications@example.test",
            "registration_reviewer_google_sub": "reviewer-sub-for-tests",
            "public_base_url": "http://127.0.0.1:8000",
        }
    )
    from app.modules.auth.invitations import policy

    monkeypatch.setattr(policy, "get_settings", lambda: settings)
    monkeypatch.setattr(
        "app.modules.auth.invitations.router.get_settings", lambda: settings
    )
    monkeypatch.setattr(
        "app.modules.auth.invitations.workflows.get_settings", lambda: settings
    )
    monkeypatch.setattr(
        "app.modules.auth.invitations.workflows.send_invitation_email", fake_invitation
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.cookies.set(
            ACCESS_TOKEN_COOKIE,
            create_access_token(reviewer_id, get_settings().secret_key),
        )
        listed = await client.get("/auth/registration-requests")
        invitations = await client.get("/auth/invitations")
        page = await client.get("/solicitudes")
        result = await client.post(
            f"/auth/registration-requests/{item_id}/review", json={"decision": decision}
        )
    await auth_session.refresh(item)
    if role_name == "ADMINISTRADOR":
        assert listed.status_code == 200
        assert invitations.status_code == 200
        assert (
            page.status_code == 303
            and page.headers["location"] == "/?view=Invitaciones&tab=requests"
        )
        assert result.status_code == 200
        assert item.status == decision
        if decision == "approved":
            assert item.current_invitation_id is not None
        else:
            assert item.current_invitation_id is None
    else:
        assert listed.status_code == 403
        assert invitations.status_code == 403
        assert page.status_code == 403
        assert result.status_code == 403
        assert item.status == "pending"
        assert item.current_invitation_id is None


@pytest.mark.parametrize(
    ("role_name", "email", "subject", "active", "configured_sub"),
    (
        (
            "ADMINISTRADOR",
            "other-admin@example.test",
            "other-admin-sub-for-tests",
            True,
            "reviewer-sub-for-tests",
        ),
        (
            "SUPERVISOR",
            "other-supervisor@example.test",
            "other-supervisor-sub-for-tests",
            True,
            "reviewer-sub-for-tests",
        ),
        (
            "SUPERVISOR",
            "REVIEWER@EXAMPLE.TEST",
            "reviewer-sub-for-tests",
            True,
            "reviewer-sub-for-tests",
        ),
        (
            "ADMINISTRADOR",
            "notification@example.test",
            "different-sub",
            True,
            "reviewer-sub-for-tests",
        ),
        (
            "ADMINISTRADOR",
            "reviewer@example.test",
            None,
            True,
            "reviewer-sub-for-tests",
        ),
        (
            "ADMINISTRADOR",
            "REVIEWER@EXAMPLE.TEST",
            "reviewer-sub-for-tests",
            False,
            "reviewer-sub-for-tests",
        ),
        (
            None,
            "REVIEWER@EXAMPLE.TEST",
            "reviewer-sub-for-tests",
            True,
            "reviewer-sub-for-tests",
        ),
        (
            "ADMINISTRADOR",
            "REVIEWER@EXAMPLE.TEST",
            "reviewer-sub-for-tests",
            True,
            None,
        ),
        (
            "ADMINISTRADOR",
            "REVIEWER@EXAMPLE.TEST",
            "reviewer-sub-for-tests",
            True,
            "incorrect-config",
        ),
    ),
)
@pytest.mark.asyncio
async def test_review_requires_designated_active_google_identity_and_role(
    auth_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    role_name: str | None,
    email: str,
    subject: str | None,
    active: bool,
    configured_sub: str | None,
) -> None:
    from datetime import UTC, datetime

    from app.modules.auth.invitations import policy
    from app.modules.auth.models import RegistrationRequest, Role
    from app.modules.auth.validations.tokens import (
        ACCESS_TOKEN_COOKIE,
        create_access_token,
    )

    role = (
        await auth_session.scalar(select(Role).where(Role.nombre == role_name))
        if role_name
        else None
    )
    actor = User(
        email=email,
        google_sub=subject,
        rol_id=role.id if role else None,
        activo=active,
    )
    item = RegistrationRequest(
        email=f"applicant-{uuid4().hex}@example.test",
        source="password",
        status="pending",
        requested_at=datetime.now(UTC),
    )
    auth_session.add_all((actor, item))
    await auth_session.flush()
    actor_id, item_id = actor.id, item.id
    await auth_session.commit()
    settings = get_settings().model_copy(
        update={
            "registration_reviewer_google_sub": configured_sub,
            "registration_admin_email": "notification@example.test",
        }
    )
    monkeypatch.setattr(policy, "get_settings", lambda: settings)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.cookies.set(
            ACCESS_TOKEN_COOKIE,
            create_access_token(actor_id, get_settings().secret_key),
        )
        listed = await client.get("/auth/registration-requests")
        invitations = await client.get("/auth/invitations")
        page = await client.get("/solicitudes")
        rejected = await client.post(
            f"/auth/registration-requests/{item_id}/review",
            json={"decision": "rejected"},
        )
    assert listed.status_code == 403
    assert invitations.status_code == 403
    assert page.status_code == 403
    assert rejected.status_code == 403
    await auth_session.refresh(item)
    assert item.status == "pending"


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
            "registration_admin_email": "reviewer@example.test",
            "public_base_url": "http://127.0.0.1:8000",
        }
    )

    async def fail_send(email: str, link: str) -> None:
        raise delivery_error()

    monkeypatch.setattr(
        "app.modules.auth.invitations.workflows.get_settings", lambda: settings
    )
    monkeypatch.setattr(
        "app.modules.auth.invitations.router.get_settings", lambda: settings
    )
    monkeypatch.setattr(
        "app.modules.auth.invitations.workflows.send_invitation_email", fail_send
    )
    role = await auth_session.scalar(select(Role).where(Role.nombre == "ADMINISTRADOR"))
    assert role
    admin = User(
        email="REVIEWER@EXAMPLE.TEST",
        google_sub="reviewer-sub-for-tests",
        rol_id=role.id,
    )
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


@pytest.mark.parametrize(
    ("environment", "origin"),
    (
        ("development", None),
        ("production", "http://example.test"),
        ("production", "http://localhost:8000"),
    ),
)
@pytest.mark.asyncio
async def test_approval_without_public_origin_returns_controlled_error(
    auth_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
    origin: str | None,
) -> None:
    from datetime import UTC, datetime

    from app.modules.auth.models import RegistrationRequest, Role
    from app.modules.auth.validations.tokens import (
        ACCESS_TOKEN_COOKIE,
        create_access_token,
    )

    settings = get_settings().model_copy(
        update={
            "google_client_id": "client",
            "google_client_secret": "secret-local-test",
            "google_redirect_uri": "http://127.0.0.1:8000/auth/google/callback",
            "gmail_sender_email": "sender@example.test",
            "gmail_refresh_token": "refresh-local-test",
            "environment": environment,
            "public_base_url": origin,
        }
    )
    monkeypatch.setattr(
        "app.modules.auth.invitations.router.get_settings", lambda: settings
    )
    monkeypatch.setattr(
        "app.modules.auth.invitations.workflows.get_settings", lambda: settings
    )

    async def unexpected_send(_email: str, _link: str) -> None:
        pytest.fail("Missing public origin must prevent delivery")

    monkeypatch.setattr(
        "app.modules.auth.invitations.workflows.send_invitation_email",
        unexpected_send,
    )
    role = await auth_session.scalar(select(Role).where(Role.nombre == "ADMINISTRADOR"))
    assert role
    actor = User(
        email="REVIEWER@EXAMPLE.TEST",
        google_sub="reviewer-sub-for-tests",
        rol_id=role.id,
    )
    pending = RegistrationRequest(
        email=f"pending-{uuid4().hex}@example.test",
        source="password",
        status="pending",
        requested_at=datetime.now(UTC),
    )
    auth_session.add_all((actor, pending))
    await auth_session.flush()
    actor_id, request_id = actor.id, pending.id
    await auth_session.commit()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.cookies.set(
            ACCESS_TOKEN_COOKIE,
            create_access_token(actor_id, get_settings().secret_key),
        )
        response = await client.post(
            f"/auth/registration-requests/{request_id}/review",
            json={"decision": "approved"},
        )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PUBLIC_BASE_URL_UNAVAILABLE"
    assert "secret-local-test" not in str(response.json())
    await auth_session.refresh(pending)
    assert pending.status == "pending"


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
            "registration_admin_email": "reviewer@example.test",
            "public_base_url": "http://127.0.0.1:8000",
        }
    )
    sent: list[str] = []

    async def fake_notice(email: str, link: str) -> None:
        sent.append(link)

    monkeypatch.setattr(
        "app.modules.auth.invitations.workflows.get_settings", lambda: settings
    )
    monkeypatch.setattr(
        "app.modules.auth.invitations.workflows.send_registration_notice", fake_notice
    )
    admin_role = await auth_session.scalar(
        select(Role).where(Role.nombre == "ADMINISTRADOR")
    )
    supervisor_role = await auth_session.scalar(
        select(Role).where(Role.nombre == "SUPERVISOR")
    )
    assert admin_role and supervisor_role
    admin = User(
        email="REVIEWER@EXAMPLE.TEST",
        google_sub="reviewer-sub-for-tests",
        rol_id=admin_role.id,
    )
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
            "registration_admin_email": "reviewer@example.test",
            "public_base_url": "http://127.0.0.1:8000",
        }
    )

    async def fail_notice(email: str, link: str) -> None:
        raise delivery_error()

    monkeypatch.setattr(
        "app.modules.auth.invitations.workflows.get_settings", lambda: settings
    )
    monkeypatch.setattr(
        "app.modules.auth.invitations.workflows.send_registration_notice", fail_notice
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
            "registration_admin_email": "reviewer@example.test",
            "public_base_url": "http://127.0.0.1:8000",
        }
    )
    sent: list[str] = []

    async def fake_notice(email: str, link: str) -> None:
        sent.append(link)

    monkeypatch.setattr(
        "app.modules.auth.invitations.workflows.get_settings", lambda: settings
    )
    monkeypatch.setattr(
        "app.modules.auth.invitations.workflows.send_registration_notice", fake_notice
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


@pytest.mark.asyncio
async def test_approval_links_current_invitation_id_and_repeated_request_resets_state(
    auth_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime, timedelta

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
            "registration_admin_email": "reviewer@example.test",
            "registration_reviewer_google_sub": "reviewer-sub-for-tests",
            "public_base_url": "http://127.0.0.1:8000",
        }
    )

    async def fake_mail(_email: str, _link: str) -> None:
        return None

    from app.modules.auth.invitations import policy

    monkeypatch.setattr(policy, "get_settings", lambda: settings)
    monkeypatch.setattr(
        "app.modules.auth.invitations.router.get_settings", lambda: settings
    )
    monkeypatch.setattr(
        "app.modules.auth.invitations.workflows.get_settings", lambda: settings
    )
    monkeypatch.setattr(
        "app.modules.auth.invitations.workflows.send_invitation_email", fake_mail
    )
    monkeypatch.setattr(
        "app.modules.auth.invitations.workflows.send_registration_notice", fake_mail
    )

    admin_role = await auth_session.scalar(
        select(Role).where(Role.nombre == "ADMINISTRADOR")
    )
    assert admin_role is not None
    admin = User(
        email=f"admin-{uuid4().hex}@example.test",
        google_sub="reviewer-sub-for-tests",
        rol_id=admin_role.id,
    )
    target_email = f"trace-{uuid4().hex}@example.test"
    req_row = RegistrationRequest(
        email=target_email,
        source="password",
        status="pending",
        requested_at=datetime.now(UTC) - timedelta(hours=2),
        reissue_count=2,
        last_reissue_idempotency_key="stale-key",
    )
    auth_session.add_all((admin, req_row))
    await auth_session.flush()
    admin_id, req_id = admin.id, req_row.id
    await auth_session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.cookies.set(
            ACCESS_TOKEN_COOKIE,
            create_access_token(admin_id, get_settings().secret_key),
        )
        approved = await client.post(
            f"/auth/registration-requests/{req_id}/review",
            json={"decision": "approved"},
        )
    assert approved.status_code == 200
    await auth_session.refresh(req_row)
    inv_row = await auth_session.scalar(
        select(Invitation).where(Invitation.email == target_email)
    )
    assert inv_row is not None
    assert req_row.status == "approved"
    assert req_row.current_invitation_id == inv_row.id
    assert req_row.reissue_count == 0
    assert req_row.last_reissue_idempotency_key is None

    # Simulate expiry + re-issue state, then applicant submits a new registration request
    inv_row.expires_at = datetime.now(UTC) - timedelta(minutes=5)
    req_row.requested_at = datetime.now(UTC) - timedelta(hours=1)
    req_row.reissue_count = 1
    req_row.last_reissue_idempotency_key = "idem-1"
    await auth_session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        renewed = await client.post(
            "/auth/registration-requests", json={"email": target_email}
        )
    assert renewed.status_code == 202
    await auth_session.refresh(req_row)
    assert req_row.status == "pending"
    assert req_row.current_invitation_id is None
    assert req_row.reissue_count == 0
    assert req_row.last_reissue_idempotency_key is None


@pytest.mark.asyncio
async def test_list_invitations_endpoint_returns_real_invitations_and_lifecycle_statuses(
    auth_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime, timedelta

    from app.infrastructure.outbox.models import OutboxEvent
    from app.modules.auth.models import Invitation, RegistrationRequest, Role
    from app.modules.auth.validations.tokens import (
        ACCESS_TOKEN_COOKIE,
        create_access_token,
    )

    admin_role = await auth_session.scalar(
        select(Role).where(Role.nombre == "ADMINISTRADOR")
    )
    supervisor_role = await auth_session.scalar(
        select(Role).where(Role.nombre == "SUPERVISOR")
    )
    assert admin_role is not None and supervisor_role is not None

    admin = User(
        email=f"admin-inv-{uuid4().hex}@example.test",
        google_sub="reviewer-sub-for-tests",
        rol_id=admin_role.id,
    )
    supervisor = User(
        email=f"sup-inv-{uuid4().hex}@example.test",
        google_sub="supervisor-sub-for-tests",
        rol_id=supervisor_role.id,
    )
    auth_session.add_all((admin, supervisor))
    await auth_session.flush()

    now = datetime.now(UTC)

    # 1. Active invitation (normal, not eligible for reissue)
    email_active = f"active-inv-{uuid4().hex}@example.test"
    inv_active = Invitation(
        email=email_active,
        token_hash=uuid4().hex + uuid4().hex,
        rol_id=supervisor_role.id,
        invited_by_id=admin.id,
        expires_at=now + timedelta(hours=24),
    )
    # 2. Superseded (revoked) + Reissued active invitation with DEAD_LETTER outbox
    email_reissued = f"reissued-inv-{uuid4().hex}@example.test"
    inv_old_revoked = Invitation(
        email=email_reissued,
        token_hash=uuid4().hex + uuid4().hex,
        rol_id=supervisor_role.id,
        invited_by_id=admin.id,
        expires_at=now - timedelta(hours=2),
    )
    inv_new_dead_letter = Invitation(
        email=email_reissued,
        token_hash=uuid4().hex + uuid4().hex,
        rol_id=supervisor_role.id,
        invited_by_id=admin.id,
        expires_at=now + timedelta(hours=24),
    )
    # 3. Expired invitation (eligible for reissue: reissue_count < 3)
    email_expired = f"expired-inv-{uuid4().hex}@example.test"
    inv_expired = Invitation(
        email=email_expired,
        token_hash=uuid4().hex + uuid4().hex,
        rol_id=supervisor_role.id,
        invited_by_id=admin.id,
        expires_at=now - timedelta(hours=1),
    )
    # 4. Expired invitation at max reissue limit (reissue_count == 3 -> can_reissue False)
    email_maxed = f"maxed-inv-{uuid4().hex}@example.test"
    inv_maxed = Invitation(
        email=email_maxed,
        token_hash=uuid4().hex + uuid4().hex,
        rol_id=supervisor_role.id,
        invited_by_id=admin.id,
        expires_at=now - timedelta(hours=1),
    )
    # 5. Consumed invitation
    email_consumed = f"consumed-inv-{uuid4().hex}@example.test"
    inv_consumed = Invitation(
        email=email_consumed,
        token_hash=uuid4().hex + uuid4().hex,
        rol_id=supervisor_role.id,
        invited_by_id=admin.id,
        expires_at=now + timedelta(hours=12),
        used_at=now - timedelta(minutes=30),
    )
    auth_session.add_all(
        (
            inv_active,
            inv_old_revoked,
            inv_new_dead_letter,
            inv_expired,
            inv_maxed,
            inv_consumed,
        )
    )
    await auth_session.flush()

    req_active = RegistrationRequest(
        email=email_active,
        source="password",
        status="approved",
        requested_at=now - timedelta(hours=2),
        reviewed_at=now - timedelta(hours=1),
        reviewed_by_id=admin.id,
        current_invitation_id=inv_active.id,
        reissue_count=0,
    )
    req_reissued = RegistrationRequest(
        email=email_reissued,
        source="google",
        status="approved",
        requested_at=now - timedelta(days=2),
        reviewed_at=now - timedelta(days=2),
        reviewed_by_id=admin.id,
        current_invitation_id=inv_new_dead_letter.id,
        reissue_count=1,
    )
    req_expired = RegistrationRequest(
        email=email_expired,
        source="password",
        status="approved",
        requested_at=now - timedelta(days=3),
        reviewed_at=now - timedelta(days=3),
        reviewed_by_id=admin.id,
        current_invitation_id=inv_expired.id,
        reissue_count=2,
    )
    req_maxed = RegistrationRequest(
        email=email_maxed,
        source="password",
        status="approved",
        requested_at=now - timedelta(days=4),
        reviewed_at=now - timedelta(days=4),
        reviewed_by_id=admin.id,
        current_invitation_id=inv_maxed.id,
        reissue_count=3,
    )
    req_consumed = RegistrationRequest(
        email=email_consumed,
        source="password",
        status="approved",
        requested_at=now - timedelta(days=1),
        reviewed_at=now - timedelta(days=1),
        reviewed_by_id=admin.id,
        current_invitation_id=inv_consumed.id,
        reissue_count=0,
    )
    auth_session.add_all(
        (req_active, req_reissued, req_expired, req_maxed, req_consumed)
    )
    await auth_session.flush()

    dead_letter_event = OutboxEvent(
        event_type="auth.invitation.reissued",
        aggregate_type="registration_request",
        aggregate_id=str(req_reissued.id),
        recipient_email=email_reissued,
        status="DEAD_LETTER",
        idempotency_key=f"test-dl-{uuid4().hex}",
        payload_ciphertext="cipher",
        payload_nonce="123456789012",
        payload_key_id="v1",
    )
    auth_session.add(dead_letter_event)
    await auth_session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        unauth = await client.get("/auth/invitations")
        assert unauth.status_code == 401

        client.cookies.set(
            ACCESS_TOKEN_COOKIE,
            create_access_token(supervisor.id, get_settings().secret_key),
        )
        forbidden = await client.get("/auth/invitations")
        assert forbidden.status_code == 403

        client.cookies.set(
            ACCESS_TOKEN_COOKIE,
            create_access_token(admin.id, get_settings().secret_key),
        )
        ok_resp = await client.get("/auth/invitations")
        assert ok_resp.status_code == 200
        payload = ok_resp.json()

    by_id = {row["id"]: row for row in payload}
    for inv_obj in (
        inv_active,
        inv_old_revoked,
        inv_new_dead_letter,
        inv_expired,
        inv_maxed,
        inv_consumed,
    ):
        assert inv_obj.id in by_id
        assert "token_hash" not in by_id[inv_obj.id]
        assert "token" not in by_id[inv_obj.id]

    assert by_id[inv_active.id]["status"] == "active"
    assert by_id[inv_active.id]["can_reissue"] is False
    assert by_id[inv_active.id]["registration_request_id"] == req_active.id

    assert by_id[inv_old_revoked.id]["status"] == "revoked"
    assert by_id[inv_old_revoked.id]["can_reissue"] is False

    assert by_id[inv_new_dead_letter.id]["status"] == "active"
    assert by_id[inv_new_dead_letter.id]["can_reissue"] is True
    assert by_id[inv_new_dead_letter.id]["reissue_count"] == 1

    assert by_id[inv_expired.id]["status"] == "expired"
    assert by_id[inv_expired.id]["can_reissue"] is True
    assert by_id[inv_expired.id]["reissue_count"] == 2

    assert by_id[inv_maxed.id]["status"] == "expired"
    assert by_id[inv_maxed.id]["can_reissue"] is False
    assert by_id[inv_maxed.id]["reissue_count"] == 3

    assert by_id[inv_consumed.id]["status"] == "consumed"
    assert by_id[inv_consumed.id]["can_reissue"] is False
    assert by_id[inv_consumed.id]["used_at"] is not None

"""Unit tests for Stage M-05A: Delivery Matrix, Crypto Validation, and Historical Idempotency."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.config.settings import Settings
from app.infrastructure.idempotency.models import IdempotencyRecord
from app.infrastructure.idempotency.service import compute_request_hash
from app.modules.auth.invitations.reissue import (
    reissue_registration_invitation,
)
from app.modules.auth.models import Invitation, RegistrationRequest, Role, User
from app.shared.errors.application_error import ApplicationError

VALID_KEY_B64 = base64.b64encode(b"\x05" * 32).decode("ascii")


def make_settings(
    *,
    outbox_enabled: bool = False,
    enable_gmail: bool = False,
    outbox_encryption_key: str | None = None,
) -> Settings:
    key = outbox_encryption_key or (VALID_KEY_B64 if outbox_enabled else None)
    return Settings(
        database_url="postgresql+asyncpg://dummy:dummy@127.0.0.1:55432/fireassets_dummy",
        secret_key="dummy_secret_key_for_testing_purposes_at_least_32_chars",
        outbox_enabled=outbox_enabled,
        outbox_encryption_key=key,
        outbox_encryption_key_id="v1",
        google_client_id="dummy-id" if enable_gmail else None,
        google_client_secret="dummy-secret" if enable_gmail else None,
        google_redirect_uri="https://app.example.test/auth/callback" if enable_gmail else None,
        gmail_sender_email="admin@example.test" if enable_gmail else None,
        gmail_refresh_token="dummy-token" if enable_gmail else None,
        public_base_url="https://app.example.test",
        admin_rate_limit_reissue_requests=20,
    )


class MockScalars:
    def __init__(self, items: list[Any]) -> None:
        self._items = items

    def all(self) -> list[Any]:
        return self._items


class MockSessionM05A:
    def __init__(
        self,
        *,
        request: RegistrationRequest | None,
        role: Role | None = None,
        existing_user: User | None = None,
        prior_invitations: list[Invitation] | None = None,
        idempotency_records: list[IdempotencyRecord] | None = None,
    ) -> None:
        self.request = request
        self.role = role or Role(id=2, nombre="SUPERVISOR", activo=True)
        self.existing_user = existing_user
        self.prior_invitations = prior_invitations or []
        self.idempotency_records = idempotency_records or []
        self.added: list[Any] = []
        self.flushed = False
        self.committed = False
        self.rolled_back = False

    async def scalar(self, statement: Any) -> Any:
        stmt_str = str(statement).lower()
        if "from idempotency_records" in stmt_str:
            for rec in self.idempotency_records:
                return rec
            return None
        if "from auth_registration_requests" in stmt_str:
            return self.request
        if "from usuarios" in stmt_str:
            return self.existing_user.id if self.existing_user else None
        if "from roles" in stmt_str:
            return self.role
        if "from outbox_events" in stmt_str:
            return None
        if "from auth_invitations" in stmt_str:
            return self.prior_invitations[0].id if self.prior_invitations else None
        return None

    async def scalars(self, statement: Any) -> MockScalars:
        return MockScalars(self.prior_invitations)

    def add(self, item: Any) -> None:
        if isinstance(item, Invitation) and getattr(item, "id", None) is None:
            item.id = 999
        self.added.append(item)

    async def flush(self) -> None:
        self.flushed = True

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


# =========================================================================
# 1. Delivery Configuration Matrix Tests (P1-A Remediation)
# =========================================================================


@pytest.mark.asyncio
async def test_reissue_both_delivery_mechanisms_disabled_fails_closed() -> None:
    """When OUTBOX_ENABLED=false and GMAIL_INVITATION_ENABLED=false, reject with HTTP 503."""
    admin_user = User(id=1, email="admin@example.test", rol_id=1, activo=True)
    session = MockSessionM05A(request=None)
    settings = make_settings(outbox_enabled=False, enable_gmail=False)
    assert not settings.outbox_enabled
    assert not settings.gmail_invitation_enabled

    with patch("app.modules.auth.invitations.reissue.require_reissue_admin", new=AsyncMock(return_value=None)), \
         patch("app.modules.auth.invitations.reissue.get_settings", return_value=settings):

        with pytest.raises(ApplicationError) as exc_info:
            await reissue_registration_invitation(
                session=session,  # type: ignore[arg-type]
                request_id=1,
                actor=admin_user,
                idempotency_key="key-delivery-none",
            )

        assert exc_info.value.status_code == 503
        assert exc_info.value.code == "INVITATION_DELIVERY_UNAVAILABLE"
        assert len(session.added) == 0, "No state changes permitted under fail-closed"


@pytest.mark.asyncio
async def test_reissue_outbox_enabled_gmail_disabled_enqueues_atomically() -> None:
    """When OUTBOX_ENABLED=true and GMAIL_INVITATION_ENABLED=false, atomic enqueue succeeds without WAN."""
    admin_user = User(id=1, email="admin@example.test", rol_id=1, activo=True)
    now = datetime.now(UTC)
    request_item = RegistrationRequest(
        id=10,
        email="outbox_only@example.test",
        status="approved",
        source="password",
        requested_at=now - timedelta(days=2),
        reissue_count=0,
    )
    old_inv = Invitation(id=1, email=request_item.email, token_hash="h1", rol_id=2, invited_by_id=1, expires_at=now - timedelta(hours=1))
    session = MockSessionM05A(request=request_item, prior_invitations=[old_inv])
    settings = make_settings(outbox_enabled=True, enable_gmail=False, outbox_encryption_key=VALID_KEY_B64)
    assert settings.outbox_enabled
    assert not settings.gmail_invitation_enabled

    with patch("app.modules.auth.invitations.reissue.require_reissue_admin", new=AsyncMock(return_value=None)), \
         patch("app.modules.auth.invitations.reissue.get_settings", return_value=settings), \
         patch("app.infrastructure.outbox.service.OutboxService.enqueue_event", new=AsyncMock(return_value=None)) as mock_enqueue:

        result = await reissue_registration_invitation(
            session=session,  # type: ignore[arg-type]
            request_id=10,
            actor=admin_user,
            idempotency_key="key-outbox-valid",
        )

        assert result.request_id == 10
        assert result.reissue_count == 1
        assert result.idempotent_replay is False
        assert mock_enqueue.called, "Outbox event must be enqueued"


@pytest.mark.asyncio
async def test_reissue_outbox_disabled_gmail_enabled_sends_legacy_email() -> None:
    """When OUTBOX_ENABLED=false and GMAIL_INVITATION_ENABLED=true, legacy email is called directly."""
    admin_user = User(id=1, email="admin@example.test", rol_id=1, activo=True)
    now = datetime.now(UTC)
    request_item = RegistrationRequest(
        id=20,
        email="gmail_legacy@example.test",
        status="approved",
        source="password",
        requested_at=now - timedelta(days=2),
        reissue_count=0,
    )
    old_inv = Invitation(id=2, email=request_item.email, token_hash="h2", rol_id=2, invited_by_id=1, expires_at=now - timedelta(hours=1))
    session = MockSessionM05A(request=request_item, prior_invitations=[old_inv])
    settings = make_settings(outbox_enabled=False, enable_gmail=True)
    assert not settings.outbox_enabled
    assert settings.gmail_invitation_enabled

    with patch("app.modules.auth.invitations.reissue.require_reissue_admin", new=AsyncMock(return_value=None)), \
         patch("app.modules.auth.invitations.reissue.get_settings", return_value=settings), \
         patch("app.modules.auth.invitations.reissue.send_invitation_email", new=AsyncMock(return_value=None)) as mock_send_email:

        result = await reissue_registration_invitation(
            session=session,  # type: ignore[arg-type]
            request_id=20,
            actor=admin_user,
            idempotency_key="key-gmail-legacy",
        )

        assert result.reissue_count == 1
        assert mock_send_email.called, "send_invitation_email must be called in legacy mode"


@pytest.mark.asyncio
async def test_reissue_both_enabled_outbox_preempts_without_double_sending() -> None:
    """When both OUTBOX and GMAIL are enabled, Outbox takes deterministic precedence and legacy mail is NOT called."""
    admin_user = User(id=1, email="admin@example.test", rol_id=1, activo=True)
    now = datetime.now(UTC)
    request_item = RegistrationRequest(
        id=30,
        email="both_enabled@example.test",
        status="approved",
        source="password",
        requested_at=now - timedelta(days=2),
        reissue_count=0,
    )
    old_inv = Invitation(id=3, email=request_item.email, token_hash="h3", rol_id=2, invited_by_id=1, expires_at=now - timedelta(hours=1))
    session = MockSessionM05A(request=request_item, prior_invitations=[old_inv])
    settings = make_settings(outbox_enabled=True, enable_gmail=True, outbox_encryption_key=VALID_KEY_B64)
    assert settings.outbox_enabled
    assert settings.gmail_invitation_enabled

    with patch("app.modules.auth.invitations.reissue.require_reissue_admin", new=AsyncMock(return_value=None)), \
         patch("app.modules.auth.invitations.reissue.get_settings", return_value=settings), \
         patch("app.infrastructure.outbox.service.OutboxService.enqueue_event", new=AsyncMock(return_value=None)) as mock_enqueue, \
         patch("app.modules.auth.invitations.reissue.send_invitation_email", new=AsyncMock(return_value=None)) as mock_send_email:

        result = await reissue_registration_invitation(
            session=session,  # type: ignore[arg-type]
            request_id=30,
            actor=admin_user,
            idempotency_key="key-both-enabled",
        )

        assert result.reissue_count == 1
        assert mock_enqueue.called, "Outbox event must be enqueued"
        assert not mock_send_email.called, "Direct legacy email must NOT be sent (no double delivery)"


@pytest.mark.asyncio
async def test_reissue_outbox_invalid_crypto_fails_closed_before_db() -> None:
    """When Outbox service initialization fails (e.g. invalid keyring), fail closed with 503 before any mutations."""
    admin_user = User(id=1, email="admin@example.test", rol_id=1, activo=True)
    session = MockSessionM05A(request=None)
    settings = make_settings(outbox_enabled=True, enable_gmail=False, outbox_encryption_key=VALID_KEY_B64)

    with patch("app.modules.auth.invitations.reissue.require_reissue_admin", new=AsyncMock(return_value=None)), \
         patch("app.modules.auth.invitations.reissue.get_settings", return_value=settings), \
         patch("app.infrastructure.outbox.service.OutboxService.from_settings", side_effect=ValueError("Corrupted keyring")):

        with pytest.raises(ApplicationError) as exc_info:
            await reissue_registration_invitation(
                session=session,  # type: ignore[arg-type]
                request_id=1,
                actor=admin_user,
                idempotency_key="key-invalid-crypto",
            )

        assert exc_info.value.status_code == 503
        assert exc_info.value.code == "OUTBOX_CONFIGURATION_INVALID"
        assert len(session.added) == 0


# =========================================================================
# 2. Historical Idempotency & Conflict Detection Tests (P1-B Remediation)
# =========================================================================


@pytest.mark.asyncio
async def test_reissue_historical_idempotency_replay_preserves_count() -> None:
    """Historical replay of K1 after K2 returns K1 result without incrementing count or creating new invitation."""
    admin_user = User(id=1, email="admin@example.test", rol_id=1, activo=True)
    req_hash = compute_request_hash({"request_id": 40, "reason": "Acceso inicial"})
    k1_record = IdempotencyRecord(
        id=1,
        scope="invitation.reissue",
        aggregate_id="40",
        idempotency_key="key-k1",
        request_hash=req_hash,
        response_status=200,
        response_data={
            "request_id": 40,
            "invitation_id": 101,
            "reissue_count": 1,
        },
    )

    session = MockSessionM05A(request=None, idempotency_records=[k1_record])
    settings = make_settings(outbox_enabled=False, enable_gmail=True)

    with patch("app.modules.auth.invitations.reissue.require_reissue_admin", new=AsyncMock(return_value=None)), \
         patch("app.modules.auth.invitations.reissue.get_settings", return_value=settings), \
         patch("app.modules.auth.invitations.reissue.get_idempotency_record", new=AsyncMock(return_value=k1_record)):

        result = await reissue_registration_invitation(
            session=session,  # type: ignore[arg-type]
            request_id=40,
            actor=admin_user,
            idempotency_key="key-k1",
            reason="Acceso inicial",
        )

        assert result.request_id == 40
        assert result.invitation_id == 101
        assert result.reissue_count == 1
        assert result.idempotent_replay is True
        assert len(session.added) == 0, "Replay must have zero side effects"


@pytest.mark.asyncio
async def test_reissue_idempotency_key_reuse_with_different_params_raises_conflict() -> None:
    """Reusing K1 with different parameters returns HTTP 409 IDEMPOTENCY_CONFLICT."""
    admin_user = User(id=1, email="admin@example.test", rol_id=1, activo=True)
    initial_hash = compute_request_hash({"request_id": 50, "reason": "Motivo A"})
    k1_record = IdempotencyRecord(
        id=1,
        scope="invitation.reissue",
        aggregate_id="50",
        idempotency_key="key-conflict",
        request_hash=initial_hash,
        response_status=200,
        response_data={"request_id": 50, "invitation_id": 102, "reissue_count": 1},
    )

    session = MockSessionM05A(request=None)
    settings = make_settings(outbox_enabled=False, enable_gmail=True)

    with patch("app.modules.auth.invitations.reissue.require_reissue_admin", new=AsyncMock(return_value=None)), \
         patch("app.modules.auth.invitations.reissue.get_settings", return_value=settings), \
         patch("app.modules.auth.invitations.reissue.get_idempotency_record", new=AsyncMock(return_value=k1_record)):

        with pytest.raises(ApplicationError) as exc_info:
            await reissue_registration_invitation(
                session=session,  # type: ignore[arg-type]
                request_id=50,
                actor=admin_user,
                idempotency_key="key-conflict",
                reason="Motivo B completamente distinto",
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "IDEMPOTENCY_CONFLICT"

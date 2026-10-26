"""Unit and component tests for administrative invitation reissuance (Stage M-03A).

Validates:
- Successful reissuance by authorized ADMINISTRADOR.
- Authorization barriers (non-admin, inactive, unauthenticated).
- Status validation (only approved requests eligible).
- Invalidation of previous invitations and generation of fresh token.
- Consumption protection (consumed invitations cannot be reissued).
- Expiration and DEAD_LETTER eligibility gating.
- Request-level idempotency (replay returns identical response without duplicate work).
- Persistent reissuance limits (max 3 reissues per request).
- Atomic AuditChange logging without sensitive tokens or credentials.
- Outbox Format Version 3 length-prefixed AAD delimiter collision resistance.
- Backward compatibility across AAD Format Versions 1, 2, and 3.
- Adversarial metadata tampering rejection.
- HTTP router endpoint payload and response structure.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.config.settings import Settings
from app.infrastructure.outbox.crypto import (
    DEFAULT_FORMAT_VERSION,
    Keyring,
    OutboxTamperedError,
    build_aad,
    decrypt_outbox_payload,
    encrypt_outbox_payload,
)
from app.infrastructure.outbox.models import OutboxEvent
from app.modules.auth.invitations.policy import require_reissue_admin
from app.modules.auth.invitations.reissue import (
    MAX_REISSUES_PER_REQUEST,
    ReissueResult,
    reissue_registration_invitation,
)
from app.modules.auth.invitations.router import (
    ReissueInvitationPayload,
    reissue_invitation,
)
from app.modules.auth.models import Invitation, RegistrationRequest, Role, User
from app.modules.inventory.shared.models import AuditChange
from app.shared.errors.application_error import ApplicationError
from app.shared.errors.authorization_error import AuthorizationError

VALID_KEY_B64 = base64.b64encode(b"\x09" * 32).decode("ascii")


def make_test_settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://dummy:dummy@127.0.0.1:55432/fireassets_dummy",
        secret_key="dummy_secret_key_for_testing_purposes",
        outbox_enabled=True,
        outbox_encryption_key=VALID_KEY_B64,
        outbox_encryption_key_id="v1",
        google_client_id="dummy-id",
        google_client_secret="dummy-secret",
        google_redirect_uri="https://app.example.test/auth/callback",
        gmail_sender_email="admin@example.test",
        gmail_refresh_token="dummy-token",
        public_base_url="https://app.example.test",
        admin_rate_limit_reissue_requests=20,
    )


class MockScalars:
    def __init__(self, items: list[Any]) -> None:
        self._items = items

    def all(self) -> list[Any]:
        return self._items


class ReissueMockSession:
    """Mock database session simulating SQLAlchemy AsyncSession behavior for reissuance."""

    def __init__(
        self,
        *,
        request: RegistrationRequest | None,
        role: Role | None,
        existing_user: User | None = None,
        prior_invitations: list[Invitation] | None = None,
        outbox_event: OutboxEvent | None = None,
    ) -> None:
        self.request = request
        self.role = role
        self.existing_user = existing_user
        self.prior_invitations = prior_invitations or []
        self.outbox_event = outbox_event
        self.added: list[Any] = []
        self.flushed = False
        self.committed = False
        self.rolled_back = False

    async def scalar(self, statement: Any) -> Any:
        # Determine query target
        stmt_str = str(statement).lower()
        if "from auth_registration_requests" in stmt_str:
            return self.request
        if "from usuarios" in stmt_str:
            return self.existing_user.id if self.existing_user else None
        if "from roles" in stmt_str:
            return self.role
        if "from outbox_events" in stmt_str:
            return self.outbox_event
        if "from auth_invitations" in stmt_str:
            return self.prior_invitations[0].id if self.prior_invitations else None
        return None

    async def scalars(self, statement: Any) -> MockScalars:
        return MockScalars(self.prior_invitations)

    async def get(self, model: type, ident: Any) -> Any:
        if model is Role:
            return self.role
        if model is Invitation:
            for inv in self.prior_invitations:
                if inv.id == ident:
                    return inv
            for item in self.added:
                if isinstance(item, Invitation) and item.id == ident:
                    return item
            return None
        return None

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
# 1. Authorization tests
# =========================================================================

@pytest.mark.asyncio
async def test_require_reissue_admin_allows_active_admin() -> None:
    session = AsyncMock()
    admin_role = Role(id=1, nombre="ADMINISTRADOR", activo=True)
    admin_user = User(id=10, email="admin@example.test", rol_id=1, activo=True)
    session.get = AsyncMock(return_value=admin_role)

    with patch("app.modules.auth.invitations.policy.get_settings", return_value=make_test_settings()):
        await require_reissue_admin(session, admin_user)


@pytest.mark.asyncio
async def test_require_reissue_admin_rejects_supervisor() -> None:
    session = AsyncMock()
    supervisor_role = Role(id=2, nombre="SUPERVISOR", activo=True)
    supervisor_user = User(id=20, email="sup@example.test", rol_id=2, activo=True)
    session.get = AsyncMock(return_value=supervisor_role)

    with patch("app.modules.auth.invitations.policy.get_settings", return_value=make_test_settings()):
        with pytest.raises(AuthorizationError) as exc_info:
            await require_reissue_admin(session, supervisor_user)
        assert exc_info.value.code == "REISSUE_PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_require_reissue_admin_rejects_inactive_admin() -> None:
    session = AsyncMock()
    admin_role = Role(id=1, nombre="ADMINISTRADOR", activo=True)
    inactive_user = User(id=10, email="admin@example.test", rol_id=1, activo=False)
    session.get = AsyncMock(return_value=admin_role)

    with patch("app.modules.auth.invitations.policy.get_settings", return_value=make_test_settings()):
        with pytest.raises(AuthorizationError) as exc_info:
            await require_reissue_admin(session, inactive_user)
        assert exc_info.value.code == "REISSUE_PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_require_reissue_admin_enforces_reviewer_google_sub_if_configured() -> None:
    session = AsyncMock()
    admin_role = Role(id=1, nombre="ADMINISTRADOR", activo=True)
    session.get = AsyncMock(return_value=admin_role)

    # Settings configured with specific reviewer sub
    settings = make_test_settings()
    settings.registration_reviewer_google_sub = "google-sub-authorized-admin"

    # User 1: Admin without google_sub (None) -> Rejected
    user_no_sub = User(id=10, email="admin1@example.test", rol_id=1, activo=True, google_sub=None)
    with patch("app.modules.auth.invitations.policy.get_settings", return_value=settings):
        with pytest.raises(AuthorizationError) as exc_info:
            await require_reissue_admin(session, user_no_sub)
        assert exc_info.value.code == "REISSUE_PERMISSION_DENIED"

    # User 2: Admin with wrong google_sub -> Rejected
    user_wrong_sub = User(id=11, email="admin2@example.test", rol_id=1, activo=True, google_sub="attacker-sub")
    with patch("app.modules.auth.invitations.policy.get_settings", return_value=settings):
        with pytest.raises(AuthorizationError) as exc_info:
            await require_reissue_admin(session, user_wrong_sub)
        assert exc_info.value.code == "REISSUE_PERMISSION_DENIED"

    # User 3: Admin with matching google_sub -> Allowed
    user_matching_sub = User(id=12, email="admin3@example.test", rol_id=1, activo=True, google_sub="google-sub-authorized-admin")
    with patch("app.modules.auth.invitations.policy.get_settings", return_value=settings):
        await require_reissue_admin(session, user_matching_sub)


# =========================================================================
# 2. Reissuance domain workflow tests
# =========================================================================

@pytest.mark.asyncio
async def test_reissue_success_for_expired_invitation() -> None:
    supervisor_role = Role(id=2, nombre="SUPERVISOR", activo=True)
    admin_user = User(id=10, email="admin@example.test", rol_id=1, activo=True)

    now = datetime.now(UTC)
    request_item = RegistrationRequest(
        id=42,
        email="applicant@example.test",
        status="approved",
        source="password",
        requested_at=now - timedelta(days=3),
        reissue_count=0,
        last_reissue_idempotency_key=None,
    )

    old_invitation = Invitation(
        id=101,
        email="applicant@example.test",
        token_hash="hash_old",
        rol_id=2,
        invited_by_id=10,
        expires_at=now - timedelta(hours=1),  # Expired
        used_at=None,
    )

    session = ReissueMockSession(
        request=request_item,
        role=supervisor_role,
        prior_invitations=[old_invitation],
    )
    session.role = supervisor_role

    settings = make_test_settings()
    with patch("app.modules.auth.invitations.reissue.get_settings", return_value=settings), \
         patch("app.modules.auth.invitations.reissue.require_reissue_admin", new=AsyncMock(return_value=None)):
        result = await reissue_registration_invitation(
            session=session,  # type: ignore[arg-type]
            request_id=42,
            actor=admin_user,
            idempotency_key="idemp-key-1",
            reason="Applicant lost previous link and token expired",
        )

    assert isinstance(result, ReissueResult)
    assert result.request_id == 42
    assert result.reissue_count == 1
    assert not result.idempotent_replay

    # Check request state updated
    assert request_item.reissue_count == 1
    assert request_item.last_reissue_idempotency_key == "idemp-key-1"

    # Check old invitation was invalidated
    assert old_invitation.expires_at <= now

    # Check added items: new Invitation, OutboxEvent, AuditChange
    types_added = [type(item) for item in session.added]
    assert Invitation in types_added
    assert OutboxEvent in types_added
    assert AuditChange in types_added

    # Check outbox event attributes
    outbox_event = next(item for item in session.added if isinstance(item, OutboxEvent))
    assert outbox_event.event_type == "auth.invitation.reissued"
    assert outbox_event.aggregate_id == "42"
    assert outbox_event.recipient_email == "applicant@example.test"
    assert outbox_event.payload_format_version == DEFAULT_FORMAT_VERSION
    assert "idemp-key-1" in outbox_event.idempotency_key

    # Check audit change attributes
    audit_item = next(item for item in session.added if isinstance(item, AuditChange))
    assert audit_item.entidad_tipo == "USUARIO"
    assert audit_item.entidad_id == 42
    assert audit_item.accion == "MODIFICACION"
    assert audit_item.datos_anteriores is not None
    assert audit_item.datos_nuevos is not None
    assert audit_item.datos_anteriores["previous_invitation_id"] == 101
    assert audit_item.datos_nuevos["reissue_count"] == 1
    assert "token" not in audit_item.datos_nuevos
    assert "link" not in audit_item.datos_nuevos


@pytest.mark.asyncio
async def test_reissue_success_for_dead_letter_event() -> None:
    admin_user = User(id=10, email="admin@example.test", rol_id=1, activo=True)
    supervisor_role = Role(id=2, nombre="SUPERVISOR", activo=True)
    now = datetime.now(UTC)

    request_item = RegistrationRequest(
        id=55,
        email="deadletter@example.test",
        status="approved",
        source="password",
        requested_at=now - timedelta(hours=5),
        reissue_count=1,
        last_reissue_idempotency_key="old-key",
    )

    unexpired_invitation = Invitation(
        id=202,
        email="deadletter@example.test",
        token_hash="hash_dl",
        rol_id=2,
        invited_by_id=10,
        expires_at=now + timedelta(hours=40),  # Not expired
        used_at=None,
    )

    # Associated outbox event failed terminally
    dead_letter_event = OutboxEvent(
        id=999,
        event_type="auth.invitation.created",
        aggregate_type="registration_request",
        aggregate_id="55",
        recipient_email="deadletter@example.test",
        status="DEAD_LETTER",
    )

    session = ReissueMockSession(
        request=request_item,
        role=supervisor_role,
        prior_invitations=[unexpired_invitation],
        outbox_event=dead_letter_event,
    )

    settings = make_test_settings()
    with patch("app.modules.auth.invitations.reissue.get_settings", return_value=settings), \
         patch("app.modules.auth.invitations.reissue.require_reissue_admin", new=AsyncMock(return_value=None)):
        result = await reissue_registration_invitation(
            session=session,  # type: ignore[arg-type]
            request_id=55,
            actor=admin_user,
            idempotency_key="reissue-after-deadletter",
        )

    assert result.request_id == 55
    assert result.reissue_count == 2
    assert not result.idempotent_replay
    # Prior invitation revoked
    assert unexpired_invitation.expires_at <= datetime.now(UTC)


@pytest.mark.asyncio
async def test_reissue_rejected_for_unapproved_request() -> None:
    admin_user = User(id=10, email="admin@example.test", rol_id=1, activo=True)
    now = datetime.now(UTC)

    pending_request = RegistrationRequest(
        id=60,
        email="pending@example.test",
        status="pending",  # NOT approved
        source="password",
        requested_at=now,
    )
    session = ReissueMockSession(request=pending_request, role=None)

    with patch("app.modules.auth.invitations.reissue.require_reissue_admin", new=AsyncMock(return_value=None)):
        with pytest.raises(ApplicationError) as exc_info:
            await reissue_registration_invitation(
                session=session,  # type: ignore[arg-type]
                request_id=60,
                actor=admin_user,
                idempotency_key="key-pending",
            )
        assert exc_info.value.code == "REGISTRATION_REQUEST_NOT_APPROVED"


@pytest.mark.asyncio
async def test_reissue_rejected_for_consumed_invitation() -> None:
    admin_user = User(id=10, email="admin@example.test", rol_id=1, activo=True)
    now = datetime.now(UTC)

    request_item = RegistrationRequest(
        id=70,
        email="consumed@example.test",
        status="approved",
        source="password",
        requested_at=now - timedelta(days=2),
        reissue_count=0,
    )
    consumed_inv = Invitation(
        id=301,
        email="consumed@example.test",
        token_hash="hash_used",
        rol_id=2,
        invited_by_id=10,
        expires_at=now + timedelta(hours=20),
        used_at=now - timedelta(hours=1),  # Consumed!
    )
    session = ReissueMockSession(request=request_item, role=None, prior_invitations=[consumed_inv])

    with patch("app.modules.auth.invitations.reissue.require_reissue_admin", new=AsyncMock(return_value=None)):
        with pytest.raises(ApplicationError) as exc_info:
            await reissue_registration_invitation(
                session=session,  # type: ignore[arg-type]
                request_id=70,
                actor=admin_user,
                idempotency_key="key-consumed",
            )
        assert exc_info.value.code == "INVITATION_ALREADY_CONSUMED"


@pytest.mark.asyncio
async def test_reissue_rejected_if_user_already_in_database() -> None:
    admin_user = User(id=10, email="admin@example.test", rol_id=1, activo=True)
    now = datetime.now(UTC)

    request_item = RegistrationRequest(
        id=71,
        email="registered@example.test",
        status="approved",
        source="password",
        requested_at=now - timedelta(days=2),
        reissue_count=0,
    )
    existing_user = User(id=50, email="registered@example.test", rol_id=2, activo=True)
    session = ReissueMockSession(request=request_item, role=None, existing_user=existing_user)

    with patch("app.modules.auth.invitations.reissue.require_reissue_admin", new=AsyncMock(return_value=None)):
        with pytest.raises(ApplicationError) as exc_info:
            await reissue_registration_invitation(
                session=session,  # type: ignore[arg-type]
                request_id=71,
                actor=admin_user,
                idempotency_key="key-registered",
            )
        assert exc_info.value.code == "INVITATION_ALREADY_CONSUMED"


@pytest.mark.asyncio
async def test_reissue_rejected_for_active_unexpired_invitation_without_dead_letter() -> None:
    admin_user = User(id=10, email="admin@example.test", rol_id=1, activo=True)
    now = datetime.now(UTC)

    request_item = RegistrationRequest(
        id=80,
        email="active@example.test",
        status="approved",
        source="password",
        requested_at=now - timedelta(hours=1),
        reissue_count=0,
    )
    active_inv = Invitation(
        id=401,
        email="active@example.test",
        token_hash="hash_act",
        rol_id=2,
        invited_by_id=10,
        expires_at=now + timedelta(hours=47),  # Active and valid
        used_at=None,
    )
    session = ReissueMockSession(request=request_item, role=None, prior_invitations=[active_inv], outbox_event=None)

    with patch("app.modules.auth.invitations.reissue.require_reissue_admin", new=AsyncMock(return_value=None)):
        with pytest.raises(ApplicationError) as exc_info:
            await reissue_registration_invitation(
                session=session,  # type: ignore[arg-type]
                request_id=80,
                actor=admin_user,
                idempotency_key="key-active",
            )
        assert exc_info.value.code == "INVITATION_NOT_ELIGIBLE"


@pytest.mark.asyncio
async def test_reissue_idempotent_replay_returns_cached_result() -> None:
    admin_user = User(id=10, email="admin@example.test", rol_id=1, activo=True)
    now = datetime.now(UTC)

    request_item = RegistrationRequest(
        id=90,
        email="idemp@example.test",
        status="approved",
        source="password",
        requested_at=now - timedelta(days=1),
        reissue_count=2,
        last_reissue_idempotency_key="existing-idempotency-key",
        current_invitation_id=555,
    )
    existing_inv = Invitation(id=555, email="idemp@example.test", token_hash="h555", rol_id=2, invited_by_id=10, expires_at=now + timedelta(hours=20))
    session = ReissueMockSession(request=request_item, role=None, prior_invitations=[existing_inv])

    with patch("app.modules.auth.invitations.reissue.require_reissue_admin", new=AsyncMock(return_value=None)):
        result = await reissue_registration_invitation(
            session=session,  # type: ignore[arg-type]
            request_id=90,
            actor=admin_user,
            idempotency_key="existing-idempotency-key",  # Exact same key
        )

    assert result.request_id == 90
    assert result.invitation_id == 555
    assert result.reissue_count == 2
    assert result.idempotent_replay is True
    # Zero items added to session during replay
    assert len(session.added) == 0


@pytest.mark.asyncio
async def test_reissue_ceiling_max_3_rejected() -> None:
    admin_user = User(id=10, email="admin@example.test", rol_id=1, activo=True)
    now = datetime.now(UTC)

    request_item = RegistrationRequest(
        id=95,
        email="capped@example.test",
        status="approved",
        source="password",
        requested_at=now - timedelta(days=4),
        reissue_count=MAX_REISSUES_PER_REQUEST,  # Already at ceiling (3)
        last_reissue_idempotency_key="prior-attempt",
    )
    session = ReissueMockSession(request=request_item, role=None)

    with patch("app.modules.auth.invitations.reissue.require_reissue_admin", new=AsyncMock(return_value=None)):
        with pytest.raises(ApplicationError) as exc_info:
            await reissue_registration_invitation(
                session=session,  # type: ignore[arg-type]
                request_id=95,
                actor=admin_user,
                idempotency_key="attempt-number-4",
            )
        assert exc_info.value.code == "REISSUE_LIMIT_EXCEEDED"
        assert exc_info.value.status_code == 429


# =========================================================================
# 3. Cryptographic AAD Format 3 tests & delimiter collision resistance
# =========================================================================

def test_aad_format_3_prevents_delimiter_collision() -> None:
    """Demonstrate that Format Version 3 prevents delimiter collisions that could occur in format 2."""
    key_id = "v1"
    event_type = "auth.invitation.reissued"
    recipient = "victim@example.test"

    # Case A: aggregate_id has colon
    aad_v2_a = build_aad(
        format_version=2,
        key_id=key_id,
        event_type=event_type,
        aggregate_id="1:foo",
        idempotency_key="bar",
        recipient_email=recipient,
    )
    # Case B: idempotency_key has colon
    aad_v2_b = build_aad(
        format_version=2,
        key_id=key_id,
        event_type=event_type,
        aggregate_id="1",
        idempotency_key="foo:bar",
        recipient_email=recipient,
    )
    # In Format Version 2, these produced the EXACT SAME string!
    assert aad_v2_a == aad_v2_b, "Format 2 was vulnerable to colon delimiter collision"

    # In Format Version 3, length-prefixing guarantees distinct AAD!
    aad_v3_a = build_aad(
        format_version=3,
        key_id=key_id,
        event_type=event_type,
        aggregate_id="1:foo",
        idempotency_key="bar",
        recipient_email=recipient,
    )
    aad_v3_b = build_aad(
        format_version=3,
        key_id=key_id,
        event_type=event_type,
        aggregate_id="1",
        idempotency_key="foo:bar",
        recipient_email=recipient,
    )
    assert aad_v3_a != aad_v3_b, "Format 3 successfully eliminated delimiter collision"


def test_aad_backward_compatibility_decrypts_v1_v2_v3() -> None:
    keyring = Keyring.from_raw(VALID_KEY_B64, "v1")
    payload = {"data": "secret_invite_data", "email": "compat@example.test"}

    # Format Version 1
    enc_v1 = encrypt_outbox_payload(
        keyring=keyring,
        payload=payload,
        event_type="auth.invitation.created",
        aggregate_id="10",
        idempotency_key="ik-1",
        recipient_email="compat@example.test",
        format_version=1,
    )
    dec_v1 = decrypt_outbox_payload(
        keyring=keyring,
        ciphertext_b64=enc_v1.ciphertext_b64,
        nonce_b64=enc_v1.nonce_b64,
        format_version=1,
        key_id="v1",
        event_type="auth.invitation.created",
        aggregate_id="10",
        idempotency_key="ik-1",
        recipient_email="compat@example.test",
    )
    assert dec_v1["data"] == "secret_invite_data"

    # Format Version 2
    enc_v2 = encrypt_outbox_payload(
        keyring=keyring,
        payload=payload,
        event_type="auth.invitation.created",
        aggregate_id="10",
        idempotency_key="ik-2",
        recipient_email="compat@example.test",
        format_version=2,
    )
    dec_v2 = decrypt_outbox_payload(
        keyring=keyring,
        ciphertext_b64=enc_v2.ciphertext_b64,
        nonce_b64=enc_v2.nonce_b64,
        format_version=2,
        key_id="v1",
        event_type="auth.invitation.created",
        aggregate_id="10",
        idempotency_key="ik-2",
        recipient_email="compat@example.test",
    )
    assert dec_v2["data"] == "secret_invite_data"

    # Format Version 3 (Default)
    enc_v3 = encrypt_outbox_payload(
        keyring=keyring,
        payload=payload,
        event_type="auth.invitation.reissued",
        aggregate_id="10",
        idempotency_key="ik-3",
        recipient_email="compat@example.test",
        format_version=3,
    )
    assert enc_v3.format_version == 3
    dec_v3 = decrypt_outbox_payload(
        keyring=keyring,
        ciphertext_b64=enc_v3.ciphertext_b64,
        nonce_b64=enc_v3.nonce_b64,
        format_version=3,
        key_id="v1",
        event_type="auth.invitation.reissued",
        aggregate_id="10",
        idempotency_key="ik-3",
        recipient_email="compat@example.test",
    )
    assert dec_v3["data"] == "secret_invite_data"


def test_tampering_metadata_rejected_by_v3_aad() -> None:
    keyring = Keyring.from_raw(VALID_KEY_B64, "v1")
    payload = {"data": "confidential", "email": "victim@example.test"}

    enc = encrypt_outbox_payload(
        keyring=keyring,
        payload=payload,
        event_type="auth.invitation.reissued",
        aggregate_id="100",
        idempotency_key="key-safe",
        recipient_email="victim@example.test",
        format_version=3,
    )

    # 1. Tampered recipient email
    with pytest.raises(OutboxTamperedError):
        decrypt_outbox_payload(
            keyring=keyring,
            ciphertext_b64=enc.ciphertext_b64,
            nonce_b64=enc.nonce_b64,
            format_version=3,
            key_id="v1",
            event_type="auth.invitation.reissued",
            aggregate_id="100",
            idempotency_key="key-safe",
            recipient_email="attacker@example.test",
        )

    # 2. Tampered aggregate_id
    with pytest.raises(OutboxTamperedError):
        decrypt_outbox_payload(
            keyring=keyring,
            ciphertext_b64=enc.ciphertext_b64,
            nonce_b64=enc.nonce_b64,
            format_version=3,
            key_id="v1",
            event_type="auth.invitation.reissued",
            aggregate_id="999",
            idempotency_key="key-safe",
            recipient_email="victim@example.test",
        )

    # 3. Tampered event_type
    with pytest.raises(OutboxTamperedError):
        decrypt_outbox_payload(
            keyring=keyring,
            ciphertext_b64=enc.ciphertext_b64,
            nonce_b64=enc.nonce_b64,
            format_version=3,
            key_id="v1",
            event_type="auth.other.event",
            aggregate_id="100",
            idempotency_key="key-safe",
            recipient_email="victim@example.test",
        )


# =========================================================================
# 4. HTTP Transport Router endpoint tests
# =========================================================================

@pytest.mark.asyncio
async def test_router_reissue_endpoint_success() -> None:
    admin_user = User(id=1, email="admin@example.test", rol_id=1, activo=True)
    mock_session = AsyncMock()
    mock_request = AsyncMock()

    mock_reissue_result = ReissueResult(
        request_id=42,
        invitation_id=777,
        reissue_count=1,
        idempotent_replay=False,
    )

    with patch("app.modules.auth.invitations.router.require_reissue_admin", new=AsyncMock(return_value=None)), \
         patch("app.modules.auth.invitations.router.get_settings", return_value=make_test_settings()), \
         patch("app.modules.auth.invitations.router.get_rate_limiter") as mock_limiter, \
         patch("app.modules.auth.invitations.router.reissue_registration_invitation", new=AsyncMock(return_value=mock_reissue_result)):

        mock_limiter.return_value.check_admin_action_limit = AsyncMock(return_value=None)

        response = await reissue_invitation(
            request_id=42,
            payload=ReissueInvitationPayload(idempotency_key="test-idem-header-none", reason="Resend invite"),
            request=mock_request,
            session=mock_session,
            actor=admin_user,
            idempotency_key_header=None,
        )

    assert response.request_id == 42
    assert response.invitation_id == 777
    assert response.reissue_count == 1
    assert response.idempotent_replay is False
    assert mock_session.commit.called

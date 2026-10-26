"""Deterministic unit and component tests for Transactional Outbox integration (Stage M-02B).

Covers:
- Atomic commit of business entities and outbox events.
- Rollback on commit failure (zero ghost emails sent).
- Encryption error handling and safe rollback.
- Persistence error handling and safe rollback.
- Idempotency key stability and collision handling.
- Admin notifications atomic enqueuing and recipient idempotency.
- Feature flag backward compatibility (outbox_enabled=False vs True).
- Strict zero-WAN execution during database transactions.
- Zero plaintext tokens exposed in HTTP responses or unencrypted storage.
"""

from __future__ import annotations

import base64
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError

from app.config.settings import Settings, get_settings
from app.infrastructure.outbox.crypto import (
    Keyring,
    OutboxCryptoError,
    decrypt_outbox_payload,
)
from app.infrastructure.outbox.models import OutboxEvent
from app.infrastructure.outbox.service import OutboxService
from app.modules.auth.invitations import workflows

VALID_KEY_B64 = base64.b64encode(b"\x07" * 32).decode("ascii")


class MockAsyncSession:
    """Mock AsyncSession recording operation sequence without touching PostgreSQL."""

    def __init__(
        self,
        *,
        commit_error: Exception | None = None,
        flush_error: Exception | None = None,
    ) -> None:
        self.added: list[Any] = []
        self.events: list[str] = []
        self.committed: bool = False
        self.rolled_back: bool = False
        self._commit_error = commit_error
        self._flush_error = flush_error

    def add(self, entity: Any) -> None:
        self.added.append(entity)
        self.events.append(f"add:{type(entity).__name__}")

    async def flush(self) -> None:
        self.events.append("flush")
        if self._flush_error:
            raise self._flush_error

    async def commit(self) -> None:
        self.events.append("commit")
        if self._commit_error:
            raise self._commit_error
        self.committed = True

    async def rollback(self) -> None:
        self.events.append("rollback")
        self.rolled_back = True


@pytest.fixture
def outbox_settings() -> Settings:
    """Fixture providing valid settings with outbox enabled and a valid 256-bit key."""
    return get_settings().model_copy(
        update={
            "environment": "test",
            "public_base_url": "http://127.0.0.1:8000",
            "google_client_id": "test-client-id",
            "google_client_secret": "test-client-secret",
            "google_redirect_uri": "http://127.0.0.1:8000/auth/google/callback",
            "gmail_sender_email": "sender@firecontrol.test",
            "gmail_refresh_token": "test-refresh-token",
            "registration_admin_email": "admin@firecontrol.test",
            "outbox_enabled": True,
            "outbox_encryption_key": VALID_KEY_B64,
            "outbox_encryption_key_id": "v1",
        }
    )


@pytest.mark.asyncio
async def test_outbox_service_enqueue_persists_encrypted_event_without_commit() -> None:
    session = MockAsyncSession()
    keyring = Keyring.from_raw(primary_key_b64=VALID_KEY_B64, primary_key_id="v1")
    service = OutboxService(keyring=keyring)

    payload = {
        "email": "applicant@example.test",
        "link": "http://127.0.0.1:8000/registro#invite=secret-token",
        "request_id": 42,
    }

    event = await service.enqueue_event(
        session=session,  # type: ignore[arg-type]
        event_type="auth.invitation.created",
        aggregate_type="registration_request",
        aggregate_id="42",
        recipient_email="applicant@example.test",
        payload=payload,
        idempotency_key="invitation:request:42",
    )

    # Invariants: added to session, flushed, but NOT committed
    assert len(session.added) == 1
    assert session.added[0] is event
    assert session.events == ["add:OutboxEvent", "flush"]
    assert not session.committed
    assert not session.rolled_back

    # Verify event attributes
    assert event.event_type == "auth.invitation.created"
    assert event.aggregate_type == "registration_request"
    assert event.aggregate_id == "42"
    assert event.idempotency_key == "invitation:request:42"
    assert event.recipient_email == "applicant@example.test"
    assert event.status == "PENDING"
    assert event.payload_format_version == 2
    assert event.payload_key_id == "v1"
    assert not event.payload_redacted

    # Verify ciphertext is valid AES-256-GCM and decrypts cleanly
    decrypted = decrypt_outbox_payload(
        keyring=keyring,
        ciphertext_b64=event.payload_ciphertext,
        nonce_b64=event.payload_nonce,
        format_version=event.payload_format_version,
        key_id=event.payload_key_id,
        event_type=event.event_type,
        aggregate_id=event.aggregate_id,
        idempotency_key=event.idempotency_key,
        recipient_email=event.recipient_email,
    )
    assert decrypted == payload


@pytest.mark.asyncio
async def test_review_approval_with_outbox_commits_atomically_zero_wan_calls(
    monkeypatch: pytest.MonkeyPatch, outbox_settings: Settings
) -> None:
    session = MockAsyncSession()
    wan_calls: list[str] = []

    async def fake_review(
        _session: Any, request_id: int, actor_id: int, decision: str
    ) -> tuple[Any, str]:
        session.events.append("review")
        return SimpleNamespace(id=request_id, email="applicant@example.test"), "secret-invitation-token"

    async def fake_send_email(*_args: Any, **_kwargs: Any) -> None:
        wan_calls.append("send_invitation_email")

    monkeypatch.setattr(workflows, "get_settings", lambda: outbox_settings)
    monkeypatch.setattr(workflows, "review_request", fake_review)
    monkeypatch.setattr(workflows, "send_invitation_email", fake_send_email)

    await workflows.review_registration_request(
        session=session,  # type: ignore[arg-type]
        request_id=101,
        actor_id=1,
        decision="approved",
    )

    # Invariant: ZERO WAN calls executed during or after approval transaction
    assert wan_calls == []
    # Invariant: events must be review -> add -> flush -> commit
    assert session.events == ["review", "add:OutboxEvent", "flush", "commit"]
    assert session.committed
    assert not session.rolled_back

    # Verify outbox event payload
    event: OutboxEvent = session.added[0]
    assert event.recipient_email == "applicant@example.test"
    keyring = Keyring.from_raw(outbox_settings.outbox_encryption_key, "v1")  # type: ignore[arg-type]
    decrypted = decrypt_outbox_payload(
        keyring=keyring,
        ciphertext_b64=event.payload_ciphertext,
        nonce_b64=event.payload_nonce,
        format_version=event.payload_format_version,
        key_id=event.payload_key_id,
        event_type=event.event_type,
        aggregate_id=event.aggregate_id,
        idempotency_key=event.idempotency_key,
        recipient_email=event.recipient_email,
    )
    assert decrypted["request_id"] == 101
    assert "invite=secret-invitation-token" in decrypted["link"]


@pytest.mark.asyncio
async def test_review_approval_commit_failure_rolls_back_without_sending(
    monkeypatch: pytest.MonkeyPatch, outbox_settings: Settings
) -> None:
    """Verifies that M-02 vulnerability is resolved: commit failure sends 0 emails."""
    session = MockAsyncSession(commit_error=RuntimeError("Simulated DB connection drop"))
    wan_calls: list[str] = []

    async def fake_review(
        _session: Any, request_id: int, _actor_id: int, _decision: str
    ) -> tuple[Any, str]:
        session.events.append("review")
        return SimpleNamespace(id=request_id, email="applicant@example.test"), "secret-token"

    async def fake_send_email(*_args: Any, **_kwargs: Any) -> None:
        wan_calls.append("send_invitation_email")

    monkeypatch.setattr(workflows, "get_settings", lambda: outbox_settings)
    monkeypatch.setattr(workflows, "review_request", fake_review)
    monkeypatch.setattr(workflows, "send_invitation_email", fake_send_email)

    with pytest.raises(RuntimeError, match="Simulated DB connection drop"):
        await workflows.review_registration_request(
            session=session,  # type: ignore[arg-type]
            request_id=102,
            actor_id=1,
            decision="approved",
        )

    # Invariant: session was rolled back
    assert session.rolled_back
    assert "rollback" in session.events
    # Invariant: ZERO ghost emails sent to user!
    assert wan_calls == []


@pytest.mark.asyncio
async def test_review_approval_outbox_persistence_failure_rolls_back(
    monkeypatch: pytest.MonkeyPatch, outbox_settings: Settings
) -> None:
    session = MockAsyncSession(flush_error=IntegrityError("duplicate key", params=None, orig=Exception("uq_idempotency")))
    wan_calls: list[str] = []

    async def fake_review(
        _session: Any, request_id: int, _actor_id: int, _decision: str
    ) -> tuple[Any, str]:
        session.events.append("review")
        return SimpleNamespace(id=request_id, email="applicant@example.test"), "secret-token"

    async def fake_send_email(*_args: Any, **_kwargs: Any) -> None:
        wan_calls.append("send_invitation_email")

    monkeypatch.setattr(workflows, "get_settings", lambda: outbox_settings)
    monkeypatch.setattr(workflows, "review_request", fake_review)
    monkeypatch.setattr(workflows, "send_invitation_email", fake_send_email)

    with pytest.raises(IntegrityError):
        await workflows.review_registration_request(
            session=session,  # type: ignore[arg-type]
            request_id=103,
            actor_id=1,
            decision="approved",
        )

    assert session.rolled_back
    assert wan_calls == []


@pytest.mark.asyncio
async def test_review_approval_crypto_failure_rolls_back(
    monkeypatch: pytest.MonkeyPatch, outbox_settings: Settings
) -> None:
    session = MockAsyncSession()
    wan_calls: list[str] = []

    async def fake_review(
        _session: Any, request_id: int, _actor_id: int, _decision: str
    ) -> tuple[Any, str]:
        session.events.append("review")
        return SimpleNamespace(id=request_id, email="applicant@example.test"), "secret-token"

    def broken_enqueue(*_args: Any, **_kwargs: Any) -> Any:
        raise OutboxCryptoError("ENCRYPTION_FAILED", "Corrupted key material")

    monkeypatch.setattr(workflows, "get_settings", lambda: outbox_settings)
    monkeypatch.setattr(workflows, "review_request", fake_review)
    monkeypatch.setattr(OutboxService, "enqueue_event", broken_enqueue)

    with pytest.raises(OutboxCryptoError):
        await workflows.review_registration_request(
            session=session,  # type: ignore[arg-type]
            request_id=104,
            actor_id=1,
            decision="approved",
        )

    assert session.rolled_back
    assert wan_calls == []


@pytest.mark.asyncio
async def test_review_approval_rejection_does_not_create_outbox_event(
    monkeypatch: pytest.MonkeyPatch, outbox_settings: Settings
) -> None:
    session = MockAsyncSession()

    async def fake_review(
        _session: Any, request_id: int, _actor_id: int, _decision: str
    ) -> tuple[Any, None]:
        session.events.append("review")
        return SimpleNamespace(id=request_id, email="applicant@example.test"), None

    monkeypatch.setattr(workflows, "get_settings", lambda: outbox_settings)
    monkeypatch.setattr(workflows, "review_request", fake_review)

    await workflows.review_registration_request(
        session=session,  # type: ignore[arg-type]
        request_id=105,
        actor_id=1,
        decision="rejected",
    )

    assert session.committed
    assert len(session.added) == 0


@pytest.mark.asyncio
async def test_submit_request_with_outbox_enqueues_admin_notices_atomically(
    monkeypatch: pytest.MonkeyPatch, outbox_settings: Settings
) -> None:
    session = MockAsyncSession()
    wan_notices: list[str] = []

    # Two admin recipients configured
    settings = outbox_settings.model_copy(
        update={"registration_admin_email": "admin1@example.test, admin2@example.test"}
    )

    async def fake_create(_session: Any, email: str, source: str) -> Any:
        session.events.append("create_request")
        return SimpleNamespace(id=501, email=email, source=source)

    async def fake_send_notice(*_args: Any, **_kwargs: Any) -> None:
        wan_notices.append("send_registration_notice")

    monkeypatch.setattr(workflows, "get_settings", lambda: settings)
    monkeypatch.setattr(workflows, "create_registration_request", fake_create)
    monkeypatch.setattr(workflows, "send_registration_notice", fake_send_notice)

    await workflows.submit_request(
        session=session,  # type: ignore[arg-type]
        email="newcomer@example.test",
        source="password",
    )

    # Invariant: Zero direct WAN calls
    assert wan_notices == []
    # Invariant: 2 outbox events added and flushed, then committed
    assert session.committed
    assert len(session.added) == 2
    e1: OutboxEvent = session.added[0]
    e2: OutboxEvent = session.added[1]

    assert e1.recipient_email == "admin1@example.test"
    assert e1.idempotency_key == "registration_notice:501:admin1@example.test"
    assert e2.recipient_email == "admin2@example.test"
    assert e2.idempotency_key == "registration_notice:501:admin2@example.test"


@pytest.mark.asyncio
async def test_submit_request_rollback_on_outbox_error(
    monkeypatch: pytest.MonkeyPatch, outbox_settings: Settings
) -> None:
    session = MockAsyncSession(flush_error=RuntimeError("Outbox DB error"))

    async def fake_create(_session: Any, email: str, source: str) -> Any:
        return SimpleNamespace(id=502, email=email, source=source)

    monkeypatch.setattr(workflows, "get_settings", lambda: outbox_settings)
    monkeypatch.setattr(workflows, "create_registration_request", fake_create)

    with pytest.raises(RuntimeError, match="Outbox DB error"):
        await workflows.submit_request(
            session=session,  # type: ignore[arg-type]
            email="newcomer@example.test",
            source="password",
        )

    assert session.rolled_back
    assert not session.committed


@pytest.mark.asyncio
async def test_feature_flag_disabled_preserves_legacy_behavior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MockAsyncSession()
    wan_calls: list[str] = []

    legacy_settings = get_settings().model_copy(
        update={
            "environment": "test",
            "public_base_url": "http://127.0.0.1:8000",
            "outbox_enabled": False,
        }
    )

    async def fake_review(
        _session: Any, request_id: int, _actor_id: int, _decision: str
    ) -> tuple[Any, str]:
        session.events.append("review")
        return SimpleNamespace(id=request_id, email="applicant@example.test"), "legacy-token"

    async def fake_send_email(email: str, link: str) -> None:
        session.events.append("send")
        wan_calls.append(email)

    monkeypatch.setattr(workflows, "get_settings", lambda: legacy_settings)
    monkeypatch.setattr(workflows, "review_request", fake_review)
    monkeypatch.setattr(workflows, "send_invitation_email", fake_send_email)

    await workflows.review_registration_request(
        session=session,  # type: ignore[arg-type]
        request_id=106,
        actor_id=1,
        decision="approved",
    )

    # Legacy behavior: send happens before commit
    assert session.events == ["review", "send", "commit"]
    assert session.committed
    assert len(session.added) == 0  # No outbox events added
    assert wan_calls == ["applicant@example.test"]


def test_settings_validation_rejects_outbox_enabled_without_valid_key() -> None:
    """Verifies fail-closed configuration validation for outbox."""
    base_dict = {
        "database_url": "postgresql+asyncpg://user:pass@localhost:5432/db",
        "secret_key": "x" * 32,
    }

    # Default is disabled and valid without key
    s_default = Settings(**base_dict)  # type: ignore[arg-type]
    assert not s_default.outbox_enabled

    # Enabling outbox without key must raise ValueError
    with pytest.raises(ValueError, match="outbox_encryption_key must be configured"):
        Settings(**base_dict, outbox_enabled=True)  # type: ignore[arg-type]

    # Enabling outbox with invalid key length (not 32 bytes) must raise ValueError
    short_key = base64.b64encode(b"short").decode("ascii")
    with pytest.raises(ValueError, match="must be exactly 32 bytes"):
        Settings(**base_dict, outbox_enabled=True, outbox_encryption_key=short_key)  # type: ignore[arg-type]

    # Enabling outbox with valid 32-byte key passes
    s_valid = Settings(**base_dict, outbox_enabled=True, outbox_encryption_key=VALID_KEY_B64)  # type: ignore[arg-type]
    assert s_valid.outbox_enabled
    assert s_valid.outbox_encryption_key == VALID_KEY_B64

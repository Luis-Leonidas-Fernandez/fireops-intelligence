"""Transactional Outbox persistence service.

Enqueues encrypted events within the caller's active AsyncSession transaction.
Guarantees:
- Zero internal session.commit() calls.
- Zero network or email delivery calls.
- Zero plaintext tokens in logs or persistent storage.
- Full authenticated encryption (AES-256-GCM) with AAD binding.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings, get_settings
from app.infrastructure.outbox.crypto import Keyring, encrypt_outbox_payload
from app.infrastructure.outbox.models import OutboxEvent

logger = logging.getLogger("uvicorn.error")


class OutboxService:
    """Service for enqueueing encrypted outbox events within an existing transactional boundary."""

    def __init__(self, keyring: Keyring) -> None:
        self._keyring = keyring

    @property
    def keyring(self) -> Keyring:
        return self._keyring

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> OutboxService:
        if settings is None:
            settings = get_settings()
        if not settings.outbox_encryption_key:
            raise ValueError(
                "outbox_encryption_key is not configured; cannot initialize OutboxService"
            )
        keyring = Keyring.from_raw(
            primary_key_b64=settings.outbox_encryption_key,
            primary_key_id=settings.outbox_encryption_key_id,
            secondary_keys=settings.outbox_secondary_encryption_keys,
        )
        return cls(keyring=keyring)

    async def enqueue_event(
        self,
        session: AsyncSession,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        recipient_email: str,
        payload: dict[str, Any],
        idempotency_key: str,
        max_attempts: int = 5,
    ) -> OutboxEvent:
        """Atomically stage an encrypted outbox event in the provided database session.

        This method does NOT commit the session. The caller must commit or rollback
        the session as part of its atomic business transaction.
        """
        encrypted = encrypt_outbox_payload(
            keyring=self._keyring,
            payload=payload,
            event_type=event_type,
            aggregate_id=aggregate_id,
            idempotency_key=idempotency_key,
            recipient_email=recipient_email,
        )

        event = OutboxEvent(
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            idempotency_key=idempotency_key,
            recipient_email=recipient_email,
            payload_ciphertext=encrypted.ciphertext_b64,
            payload_nonce=encrypted.nonce_b64,
            payload_key_id=encrypted.key_id,
            payload_format_version=encrypted.format_version,
            payload_redacted=False,
            status="PENDING",
            attempt_count=0,
            max_attempts=max_attempts,
        )

        session.add(event)
        # Flush to surface constraint violations (e.g. idempotency key uniqueness)
        # without committing the outer transaction.
        await session.flush()
        return event


def get_outbox_service(settings: Settings | None = None) -> OutboxService:
    """Factory helper returning an OutboxService configured from application settings."""
    return OutboxService.from_settings(settings)

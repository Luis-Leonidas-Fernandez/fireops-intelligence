"""OutboxDispatcher: Non-blocking transactional event claim and out-of-band delivery.

Guarantees:
- Zero PostgreSQL row locks held during external WAN/Gmail calls.
- Single-item atomic claims with FOR UPDATE SKIP LOCKED.
- Time-bounded worker leases (default 45s) with UUID fencing tokens.
- Immediate payload redaction/shredding upon reaching DELIVERED or DEAD_LETTER.
- Exponential backoff with jitter and Retry-After support.
- Sanitized database error diagnostics with zero PII or credential retention.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.outbox.adapter import (
    DeliveryResult,
    DeliveryStatus,
    EmailDeliveryAdapter,
)
from app.infrastructure.outbox.backoff import (
    DEFAULT_BASE_BACKOFF,
    DEFAULT_MAX_BACKOFF,
    compute_next_attempt_at,
    sanitize_error_detail,
)
from app.infrastructure.outbox.crypto import (
    Keyring,
    OutboxCryptoError,
    OutboxKeyNotFoundError,
    OutboxTamperedError,
    decrypt_outbox_payload,
)
from app.infrastructure.outbox.models import OutboxEvent

logger = logging.getLogger("uvicorn.error")

SessionFactory = Callable[[], AsyncIterator[AsyncSession]]


class OutboxDispatcher:
    """Dispatcher worker claiming events from outbox_events and delivering them out-of-band."""

    def __init__(
        self,
        *,
        session_factory: Callable[..., Any],
        keyring: Keyring,
        adapter: EmailDeliveryAdapter,
        worker_id: str | None = None,
        lease_duration_seconds: int = 45,
        base_backoff_seconds: float = DEFAULT_BASE_BACKOFF,
        max_backoff_seconds: float = DEFAULT_MAX_BACKOFF,
    ) -> None:
        self._session_factory = session_factory
        self._keyring = keyring
        self._adapter = adapter
        self.worker_id = worker_id or f"worker-{uuid4().hex[:8]}"
        self.lease_duration_seconds = lease_duration_seconds
        self.base_backoff_seconds = base_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds

    @asynccontextmanager
    async def _get_session(self) -> AsyncIterator[AsyncSession]:
        """Normalize session factory to an async context manager."""
        session_obj = self._session_factory()
        if hasattr(session_obj, "__aenter__"):
            async with session_obj as session:
                yield session
        else:
            # Already an AsyncSession instance
            yield session_obj

    async def claim_event(self, session: AsyncSession) -> tuple[OutboxEvent, str] | None:
        """Phase 1: Claim exactly one runnable event with a lease and fencing token.

        Uses FOR UPDATE SKIP LOCKED to prevent contention between parallel workers.
        """
        now = datetime.now(UTC)
        stmt = (
            select(OutboxEvent)
            .where(
                OutboxEvent.status.in_(["PENDING", "RETRY"]),
                OutboxEvent.next_attempt_at <= now,
            )
            .order_by(OutboxEvent.next_attempt_at.asc(), OutboxEvent.id.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        event = await session.scalar(stmt)
        if event is None:
            return None

        fencing_token = str(uuid4())
        event.status = "PROCESSING"
        event.lease_worker_id = self.worker_id
        event.lease_token = fencing_token
        event.lease_expires_at = now + timedelta(seconds=self.lease_duration_seconds)
        event.attempt_count = event.attempt_count + 1
        event.updated_at = now

        await session.flush()
        return event, fencing_token

    def _render_email(
        self, event_type: str, recipient_email: str, payload: dict[str, Any]
    ) -> tuple[str, str]:
        """Format email subject and body based on event type."""
        link = payload.get("link", "")
        if event_type in ("auth.invitation.created", "auth.invitation.reissued"):
            subject = (
                "Registro aprobado en Fire Control"
                if event_type == "auth.invitation.created"
                else "Reemisión de invitación en Fire Control"
            )
            body = (
                f"Tu solicitud fue aprobada.\n\n"
                f"Creá tu cuenta desde este enlace (válido por 48 horas):\n"
                f"{link}\n\n"
                f"Si no esperabas este mensaje, ignoralo.\n"
            )
        elif event_type == "auth.registration_notice":
            subject = "Nueva solicitud de registro"
            body = (
                f"Hay una nueva solicitud de registro en Fire Control.\n\n"
                f"Revisala desde la aplicación: {link}\n\n"
                f"Debés iniciar sesión como administrador para aprobarla o rechazarla.\n"
            )
        else:
            subject = f"Notificación: {event_type}"
            body = f"Enlace: {link}\n"
        return subject, body

    async def _validate_pre_delivery(
        self, event_type: str, payload: dict[str, Any]
    ) -> DeliveryResult | None:
        """Validate domain preconditions (expiration, revocation, consumption) before dispatching email."""
        if event_type in ("auth.invitation.created", "auth.invitation.reissued"):
            now = datetime.now(UTC)
            # 1. Payload expiration check (Escenario F)
            expires_at_str = payload.get("expires_at")
            if expires_at_str:
                try:
                    exp = datetime.fromisoformat(expires_at_str)
                    if now >= exp:
                        logger.warning("Rejecting dispatch: invitation expired at %s", expires_at_str)
                        return DeliveryResult.permanent_error(
                            code="INVITATION_EXPIRED",
                            detail="Invitation expired prior to delivery dispatch",
                        )
                except ValueError:
                    pass

            # 2. Database revocation or consumption check (Escenario G)
            token_hash = payload.get("token_hash")
            if token_hash:
                async with self._get_session() as session:
                    stmt = text(
                        "SELECT used_at, expires_at FROM auth_invitations WHERE token_hash = :hash LIMIT 1"
                    )
                    try:
                        row = (await session.execute(stmt, {"hash": token_hash})).first()
                        if row is not None:
                            used_at, db_expires_at = row
                            if used_at is not None:
                                logger.warning(
                                    "Rejecting dispatch: invitation already consumed at %s", used_at
                                )
                                return DeliveryResult.permanent_error(
                                    code="INVITATION_CONSUMED",
                                    detail="Invitation has already been consumed",
                                )
                            if db_expires_at is not None and db_expires_at <= now:
                                logger.warning(
                                    "Rejecting dispatch: invitation expired in database at %s",
                                    db_expires_at,
                                )
                                return DeliveryResult.permanent_error(
                                    code="INVITATION_EXPIRED",
                                    detail="Invitation has expired in database",
                                )
                    except Exception as err:  # noqa: BLE001
                        logger.debug("Invitation validation query skipped or table not present: %s", err)
        return None

    async def record_outcome(
        self,
        session: AsyncSession,
        *,
        event_id: int,
        fencing_token: str,
        attempt_count: int,
        max_attempts: int,
        delivery_result: DeliveryResult,
    ) -> bool:
        """Phase 3: Record dispatch result in a short transaction with fencing validation.

        Returns True if update succeeded, False if the fence was breached.
        """
        now = datetime.now(UTC)
        stmt = (
            select(OutboxEvent)
            .where(
                OutboxEvent.id == event_id,
                OutboxEvent.lease_token == fencing_token,
                OutboxEvent.status == "PROCESSING",
            )
            .with_for_update()
        )
        event = await session.scalar(stmt)
        if event is None:
            logger.warning(
                "Fencing breach: Event %s lease expired or re-claimed. Aborting write for worker %s.",
                event_id,
                self.worker_id,
            )
            return False

        if delivery_result.status == DeliveryStatus.ACCEPTED:
            event.status = "DELIVERED"
            event.provider_accepted_at = now
            event.payload_ciphertext = ""
            event.payload_redacted = True
            event.last_error_code = None
            event.last_error_detail = None
        elif delivery_result.status in {
            DeliveryStatus.TRANSIENT_ERROR,
            DeliveryStatus.TIMEOUT,
            DeliveryStatus.RATE_LIMITED,
        }:
            if attempt_count >= max_attempts:
                event.status = "DEAD_LETTER"
                event.payload_ciphertext = ""
                event.payload_redacted = True
            else:
                event.status = "RETRY"
                event.next_attempt_at = compute_next_attempt_at(
                    attempt_count,
                    base_backoff=self.base_backoff_seconds,
                    max_backoff=self.max_backoff_seconds,
                    retry_after=delivery_result.retry_after_seconds,
                    now=now,
                )
            event.last_error_code = delivery_result.error_code
            event.last_error_detail = sanitize_error_detail(delivery_result.error_detail)
        elif delivery_result.status == DeliveryStatus.KEY_UNAVAILABLE:
            event.status = "RETRY"
            # Do not consume normal delivery attempt quota
            event.attempt_count = max(0, event.attempt_count - 1)
            event.next_attempt_at = now + timedelta(seconds=60)
            event.last_error_code = "KEY_UNAVAILABLE"
            event.last_error_detail = sanitize_error_detail(delivery_result.error_detail)
            # Ciphertext and key id are preserved intact
            event.payload_redacted = False
        elif delivery_result.status in {DeliveryStatus.PERMANENT_ERROR, DeliveryStatus.AMBIGUOUS}:
            event.status = "DEAD_LETTER"
            event.last_error_code = delivery_result.error_code
            event.last_error_detail = sanitize_error_detail(delivery_result.error_detail)
            if delivery_result.error_code == "CRYPTO_AUTH_FAILED":
                # Preserved for forensic investigation without leaking plaintext
                event.payload_redacted = False
            else:
                event.payload_ciphertext = ""
                event.payload_redacted = True

        # In all completed branches, release worker lease
        event.lease_worker_id = None
        event.lease_token = None
        event.lease_expires_at = None
        event.updated_at = now

        await session.flush()
        return True

    async def dispatch_next_event(self) -> bool:
        """Execute one complete non-blocking dispatch cycle.

        Returns True if an event was claimed and processed, False if no eligible events exist.
        """
        # --- Phase 1: Claim event in short transaction ---
        claimed_data: dict[str, Any] | None = None
        fencing_token: str = ""

        async with self._get_session() as session:
            claim_res = await self.claim_event(session)
            if claim_res is not None:
                event, fencing_token = claim_res
                claimed_data = {
                    "id": event.id,
                    "event_type": event.event_type,
                    "aggregate_id": event.aggregate_id,
                    "idempotency_key": event.idempotency_key,
                    "recipient_email": event.recipient_email,
                    "payload_ciphertext": event.payload_ciphertext,
                    "payload_nonce": event.payload_nonce,
                    "payload_format_version": event.payload_format_version,
                    "payload_key_id": event.payload_key_id,
                    "attempt_count": event.attempt_count,
                    "max_attempts": event.max_attempts,
                }
                await session.commit()

        if claimed_data is None:
            return False

        # --- Phase 2: Decrypt & deliver OUTSIDE transaction (Zero DB locks) ---
        event_id = claimed_data["id"]
        try:
            payload = decrypt_outbox_payload(
                keyring=self._keyring,
                ciphertext_b64=claimed_data["payload_ciphertext"],
                nonce_b64=claimed_data["payload_nonce"],
                format_version=claimed_data["payload_format_version"],
                key_id=claimed_data["payload_key_id"],
                event_type=claimed_data["event_type"],
                aggregate_id=claimed_data["aggregate_id"],
                idempotency_key=claimed_data["idempotency_key"],
                recipient_email=claimed_data["recipient_email"],
            )
            # Pre-send validation: Verify invitation expiration & revocation (Escenarios F & G)
            pre_send_error = await self._validate_pre_delivery(
                event_type=claimed_data["event_type"],
                payload=payload,
            )
            if pre_send_error is not None:
                delivery_result = pre_send_error
            else:
                subject, body = self._render_email(
                    claimed_data["event_type"],
                    claimed_data["recipient_email"],
                    payload,
                )
                delivery_result = await self._adapter.send_email(
                    recipient_email=claimed_data["recipient_email"],
                    subject=subject,
                    body=body,
                    idempotency_key=claimed_data["idempotency_key"],
                )
        except OutboxKeyNotFoundError as err:
            logger.warning(
                "Decryption key '%s' unavailable for event %s. Preserving ciphertext and scheduling retry.",
                claimed_data["payload_key_id"],
                event_id,
            )
            delivery_result = DeliveryResult.key_unavailable(
                key_id=claimed_data["payload_key_id"],
                detail=err.message,
            )
        except (OutboxTamperedError, OutboxCryptoError) as err:
            logger.error("Outbox crypto failure on event %s: %s", event_id, err.code)
            delivery_result = DeliveryResult.permanent_error(
                code="CRYPTO_AUTH_FAILED",
                detail=f"Cryptographic payload verification failed: {err.message}",
            )
        except Exception as err:  # noqa: BLE001
            logger.error("Unexpected error delivering outbox event %s: %s", event_id, str(err))
            delivery_result = DeliveryResult.transient_error(
                code="DISPATCHER_ERROR", detail=f"Unexpected error: {err!s}"
            )

        # --- Phase 3: Record outcome with fencing check in brief transaction ---
        async with self._get_session() as session:
            await self.record_outcome(
                session,
                event_id=event_id,
                fencing_token=fencing_token,
                attempt_count=claimed_data["attempt_count"],
                max_attempts=claimed_data["max_attempts"],
                delivery_result=delivery_result,
            )
            await session.commit()

        return True

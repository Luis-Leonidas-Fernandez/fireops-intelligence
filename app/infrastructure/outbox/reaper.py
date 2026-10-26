"""LeaseReaper: Periodic recovery of expired worker leases in Outbox.

Recovers abandoned PROCESSING events when a worker process crashed, timed out,
or disconnected before recording the delivery outcome.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.outbox.models import OutboxEvent

logger = logging.getLogger("uvicorn.error")

DEFAULT_REAP_BATCH_SIZE = 10
DEFAULT_REAP_RETRY_DELAY = 30.0


class LeaseReaper:
    """Worker task scanning for expired worker leases and transitioning them to RETRY or DEAD_LETTER."""

    def __init__(
        self,
        *,
        session_factory: Callable[..., Any],
        batch_size: int = DEFAULT_REAP_BATCH_SIZE,
        retry_delay_seconds: float = DEFAULT_REAP_RETRY_DELAY,
    ) -> None:
        self._session_factory = session_factory
        self.batch_size = batch_size
        self.retry_delay_seconds = retry_delay_seconds

    @asynccontextmanager
    async def _get_session(self) -> AsyncIterator[AsyncSession]:
        session_obj = self._session_factory()
        if hasattr(session_obj, "__aenter__"):
            async with session_obj as session:
                yield session
        else:
            yield session_obj

    async def reap_expired_leases(self) -> int:
        """Scan and recover up to batch_size expired PROCESSING leases.

        Returns the number of reaped events.
        """
        now = datetime.now(UTC)
        reaped_count = 0

        async with self._get_session() as session:
            stmt = (
                select(OutboxEvent)
                .where(
                    OutboxEvent.status == "PROCESSING",
                    OutboxEvent.lease_expires_at <= now,
                )
                .order_by(OutboxEvent.lease_expires_at.asc())
                .limit(self.batch_size)
                .with_for_update(skip_locked=True)
            )
            events = (await session.scalars(stmt)).all()

            for event in events:
                reaped_count += 1
                previous_worker = event.lease_worker_id or "unknown"

                if event.attempt_count >= event.max_attempts:
                    logger.warning(
                        "Reaping event %s to DEAD_LETTER: attempts (%s) reached max (%s).",
                        event.id,
                        event.attempt_count,
                        event.max_attempts,
                    )
                    event.status = "DEAD_LETTER"
                    event.payload_ciphertext = ""
                    event.payload_redacted = True
                    event.last_error_code = "LEASE_EXPIRED_MAX_ATTEMPTS"
                    event.last_error_detail = (
                        f"Worker {previous_worker} lease expired and max attempts exhausted."
                    )
                else:
                    logger.info(
                        "Reaping event %s to RETRY: worker %s lease expired.",
                        event.id,
                        previous_worker,
                    )
                    event.status = "RETRY"
                    event.next_attempt_at = now + timedelta(seconds=self.retry_delay_seconds)
                    event.last_error_code = "LEASE_EXPIRED"
                    event.last_error_detail = (
                        f"Worker {previous_worker} lease expired; returned to retry queue."
                    )

                # Clear lease fields
                event.lease_worker_id = None
                event.lease_token = None
                event.lease_expires_at = None
                event.updated_at = now

            if reaped_count > 0:
                await session.commit()

        return reaped_count

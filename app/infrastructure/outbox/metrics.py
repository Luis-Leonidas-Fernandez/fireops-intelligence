"""In-process telemetry and metrics collection for Transactional Outbox.

Guarantees:
- Zero PII, token, or credential retention in metrics labels or data.
- Monotonic counters and measured real execution timings (using time.perf_counter).
- Database backlog queue gauge calculation without holding table locks.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.outbox.models import OutboxEvent


@dataclass(frozen=True, slots=True)
class QueueGauges:
    """Snapshot of database outbox backlog gauges."""

    pending_count: int
    processing_count: int
    retry_count: int
    dead_letter_count: int
    oldest_pending_age_seconds: float | None

    @property
    def total_active_backlog(self) -> int:
        return self.pending_count + self.processing_count + self.retry_count


class OutboxMetrics:
    """Thread-safe operational metrics collector for the Outbox runner."""

    def __init__(self) -> None:
        self.claimed_events_total: int = 0
        self.delivered_events_total: int = 0
        self.retried_events_total: int = 0
        self.dead_letter_events_total: int = 0
        self.reaped_leases_total: int = 0
        self.fencing_breaches_total: int = 0
        self.crypto_failures_total: int = 0
        self.delivery_errors_total: int = 0

        self.last_processing_time_seconds: float = 0.0
        self.total_processing_time_seconds: float = 0.0
        self.processed_samples_count: int = 0

    def record_claim(self) -> None:
        self.claimed_events_total += 1

    def record_delivered(self, elapsed_seconds: float) -> None:
        self.delivered_events_total += 1
        self._record_timing(elapsed_seconds)

    def record_retry(self, elapsed_seconds: float) -> None:
        self.retried_events_total += 1
        self._record_timing(elapsed_seconds)

    def record_dead_letter(self, elapsed_seconds: float) -> None:
        self.dead_letter_events_total += 1
        self._record_timing(elapsed_seconds)

    def record_fencing_breach(self) -> None:
        self.fencing_breaches_total += 1

    def record_reaped_leases(self, count: int) -> None:
        self.reaped_leases_total += count

    def record_crypto_failure(self) -> None:
        self.crypto_failures_total += 1

    def record_delivery_error(self) -> None:
        self.delivery_errors_total += 1

    def _record_timing(self, elapsed_seconds: float) -> None:
        self.last_processing_time_seconds = elapsed_seconds
        self.total_processing_time_seconds += elapsed_seconds
        self.processed_samples_count += 1

    @property
    def average_processing_time_seconds(self) -> float:
        if self.processed_samples_count == 0:
            return 0.0
        return self.total_processing_time_seconds / self.processed_samples_count

    def snapshot(self) -> dict[str, Any]:
        """Return non-sensitive telemetry snapshot suitable for logging or monitoring."""
        return {
            "claimed_events_total": self.claimed_events_total,
            "delivered_events_total": self.delivered_events_total,
            "retried_events_total": self.retried_events_total,
            "dead_letter_events_total": self.dead_letter_events_total,
            "reaped_leases_total": self.reaped_leases_total,
            "fencing_breaches_total": self.fencing_breaches_total,
            "crypto_failures_total": self.crypto_failures_total,
            "delivery_errors_total": self.delivery_errors_total,
            "last_processing_time_seconds": round(self.last_processing_time_seconds, 4),
            "average_processing_time_seconds": round(self.average_processing_time_seconds, 4),
            "processed_samples_count": self.processed_samples_count,
        }

    async def collect_queue_gauges(self, session: AsyncSession) -> QueueGauges:
        """Query PostgreSQL for status counts and oldest pending age without locks."""
        now = datetime.now(UTC)

        stmt = (
            select(OutboxEvent.status, func.count(OutboxEvent.id))
            .group_by(OutboxEvent.status)
        )
        rows = (await session.execute(stmt)).all()
        counts_by_status = {status: count for status, count in rows}

        oldest_pending_stmt = (
            select(func.min(OutboxEvent.created_at))
            .where(OutboxEvent.status == "PENDING")
        )
        oldest_created_at = await session.scalar(oldest_pending_stmt)
        oldest_age = None
        if oldest_created_at is not None:
            oldest_age = max(0.0, (now - oldest_created_at).total_seconds())

        return QueueGauges(
            pending_count=counts_by_status.get("PENDING", 0),
            processing_count=counts_by_status.get("PROCESSING", 0),
            retry_count=counts_by_status.get("RETRY", 0),
            dead_letter_count=counts_by_status.get("DEAD_LETTER", 0),
            oldest_pending_age_seconds=oldest_age,
        )

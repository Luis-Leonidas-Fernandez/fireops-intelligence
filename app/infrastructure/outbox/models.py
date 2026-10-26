"""SQLAlchemy models for PostgreSQL Transactional Outbox."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class OutboxStatus(str, enum.Enum):
    """Operational state of an outbox event."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    RETRY = "RETRY"
    DELIVERED = "DELIVERED"
    DEAD_LETTER = "DEAD_LETTER"


class OutboxEvent(Base):
    """PostgreSQL Transactional Outbox entity.

    Persisted atomically within the same database transaction as domain changes.
    Sensitive payload components are encrypted at rest with AES-256-GCM.
    """

    __tablename__ = "outbox_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(320), nullable=False)

    # Cryptographic envelope
    payload_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    payload_nonce: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_key_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_format_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    payload_redacted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    # State machine and retries
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'PENDING'")
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("5")
    )
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Worker leases & fencing
    lease_worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Error diagnostics (sanitized, zero PII or credentials)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Audit timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    provider_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'RETRY', 'DELIVERED', 'DEAD_LETTER')",
            name="ck_outbox_events_status",
        ),
        # Partial index for polling active tasks (avoids full table scans)
        Index(
            "ix_outbox_events_poll",
            "next_attempt_at",
            "id",
            postgresql_where=text("status IN ('PENDING', 'RETRY')"),
        ),
        # Partial index for reaping expired leases
        Index(
            "ix_outbox_events_lease_reap",
            "lease_expires_at",
            postgresql_where=text("status = 'PROCESSING'"),
        ),
        # Index for aggregate tracing
        Index(
            "ix_outbox_events_aggregate",
            "aggregate_type",
            "aggregate_id",
        ),
    )

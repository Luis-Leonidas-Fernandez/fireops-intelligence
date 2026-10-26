"""SQLAlchemy model for persistent, cross-session transactional idempotency records."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class IdempotencyRecord(Base):
    """Persistent transactional idempotency registry.

    Guarantees that state-mutating operations can be safely replayed across
    process restarts, network retries, and concurrent requests.

    Enforces uniqueness at the PostgreSQL engine level via:
    UniqueConstraint(scope, aggregate_id, idempotency_key)

    Stores a cryptographic canonical hash of the request parameters to detect
    parameter mismatch conflicts (HTTP 409) when the same key is reused.
    """

    __tablename__ = "idempotency_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_data: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "scope",
            "aggregate_id",
            "idempotency_key",
            name="uq_idempotency_records_scope_aggregate_key",
        ),
        Index(
            "ix_idempotency_records_scope_agg_key",
            "scope",
            "aggregate_id",
            "idempotency_key",
        ),
        Index("ix_idempotency_records_created_at", "created_at"),
    )

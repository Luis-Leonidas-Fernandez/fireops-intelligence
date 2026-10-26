"""Create transactional outbox events table.

Revision ID: e8c91a2d3b45
Revises: b3f81e7d2c94
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e8c91a2d3b45"
down_revision: str | Sequence[str] | None = "b3f81e7d2c94"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("recipient_email", sa.String(length=320), nullable=False),
        sa.Column("payload_ciphertext", sa.Text(), nullable=False),
        sa.Column("payload_nonce", sa.String(length=32), nullable=False),
        sa.Column("payload_key_id", sa.String(length=64), nullable=False),
        sa.Column(
            "payload_format_version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "payload_redacted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'PENDING'"),
            nullable=False,
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "max_attempts",
            sa.Integer(),
            server_default=sa.text("5"),
            nullable=False,
        ),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("lease_worker_id", sa.String(length=64), nullable=True),
        sa.Column("lease_token", sa.String(length=64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("last_error_detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "provider_accepted_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_outbox_idempotency_key"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'RETRY', 'DELIVERED', 'DEAD_LETTER')",
            name="ck_outbox_events_status",
        ),
    )

    op.create_index(
        "ix_outbox_events_poll",
        "outbox_events",
        ["next_attempt_at", "id"],
        unique=False,
        postgresql_where=sa.text("status IN ('PENDING', 'RETRY')"),
    )
    op.create_index(
        "ix_outbox_events_lease_reap",
        "outbox_events",
        ["lease_expires_at"],
        unique=False,
        postgresql_where=sa.text("status = 'PROCESSING'"),
    )
    op.create_index(
        "ix_outbox_events_aggregate",
        "outbox_events",
        ["aggregate_type", "aggregate_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_events_aggregate", table_name="outbox_events")
    op.drop_index("ix_outbox_events_lease_reap", table_name="outbox_events")
    op.drop_index("ix_outbox_events_poll", table_name="outbox_events")
    op.drop_table("outbox_events")

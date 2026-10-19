"""Track applicant-initiated registration requests.

Revision ID: a4d9c2b7e631
Revises: f09a6e2112b4
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a4d9c2b7e631"
down_revision: str | Sequence[str] | None = "f09a6e2112b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auth_registration_requests",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(length=320), unique=True, nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="pending"
        ),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("reviewed_by_id", sa.BigInteger(), sa.ForeignKey("usuarios.id")),
    )


def downgrade() -> None:
    op.drop_table("auth_registration_requests")

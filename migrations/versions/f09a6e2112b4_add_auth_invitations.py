"""Add single-use invitations.

Revision ID: f09a6e2112b4
Revises: e7d4c2f9a621
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f09a6e2112b4"
down_revision: str | Sequence[str] | None = "e7d4c2f9a621"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auth_invitations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("rol_id", sa.BigInteger(), sa.ForeignKey("roles.id"), nullable=False),
        sa.Column(
            "invited_by_id",
            sa.BigInteger(),
            sa.ForeignKey("usuarios.id"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_auth_invitations_email", "auth_invitations", ["email"])


def downgrade() -> None:
    op.drop_index("ix_auth_invitations_email", table_name="auth_invitations")
    op.drop_table("auth_invitations")

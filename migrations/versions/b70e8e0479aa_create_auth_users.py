"""Create users for email and password authentication.

Revision ID: b70e8e0479aa
Revises: 0374d9a573a1
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b70e8e0479aa"
down_revision: str | Sequence[str] | None = "0374d9a573a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "usuarios",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )


def downgrade() -> None:
    op.drop_table("usuarios")

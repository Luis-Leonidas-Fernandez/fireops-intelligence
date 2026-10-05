"""Add optional Google identity to users.

Revision ID: c4e9f1d2a7b3
Revises: b70e8e0479aa
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4e9f1d2a7b3"
down_revision: str | Sequence[str] | None = "b70e8e0479aa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("usuarios", "password_hash", existing_type=sa.String(255), nullable=True)
    op.add_column("usuarios", sa.Column("google_sub", sa.String(255), nullable=True))
    op.create_unique_constraint("uq_usuarios_google_sub", "usuarios", ["google_sub"])


def downgrade() -> None:
    connection = op.get_bind()
    google_only = connection.execute(
        sa.text("SELECT EXISTS(SELECT 1 FROM usuarios WHERE password_hash IS NULL)")
    ).scalar()
    if google_only:
        raise RuntimeError(
            "Cannot downgrade while Google-only users exist; assign real passwords first."
        )
    op.drop_constraint("uq_usuarios_google_sub", "usuarios", type_="unique")
    op.drop_column("usuarios", "google_sub")
    op.alter_column("usuarios", "password_hash", existing_type=sa.String(255), nullable=False)

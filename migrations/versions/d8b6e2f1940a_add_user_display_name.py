"""Add optional display name to authenticated users.

Revision ID: d8b6e2f1940a
Revises: c4e9f1d2a7b3
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d8b6e2f1940a"
down_revision: str | Sequence[str] | None = "c4e9f1d2a7b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("usuarios", sa.Column("display_name", sa.String(120), nullable=True))


def downgrade() -> None:
    op.drop_column("usuarios", "display_name")

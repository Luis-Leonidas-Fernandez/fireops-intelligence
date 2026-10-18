"""Add role catalog and transitional user role and active columns.

Revision ID: e7d4c2f9a621
Revises: c15b4e3d9a20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7d4c2f9a621"
down_revision: str | Sequence[str] | None = "c15b4e3d9a20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    roles = op.create_table(
        "roles",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column(
            "activo", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nombre"),
    )
    op.bulk_insert(
        roles,
        [
            {"nombre": "ADMINISTRADOR", "descripcion": "System administrator"},
            {"nombre": "SUPERVISOR", "descripcion": "Inventory supervisor"},
        ],
    )

    op.add_column("usuarios", sa.Column("rol_id", sa.BigInteger(), nullable=True))
    op.add_column(
        "usuarios",
        sa.Column(
            "activo", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
    )
    op.create_foreign_key(
        "fk_usuarios_rol_id_roles", "usuarios", "roles", ["rol_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_usuarios_rol_id_roles", "usuarios", type_="foreignkey")
    op.drop_column("usuarios", "activo")
    op.drop_column("usuarios", "rol_id")
    op.drop_table("roles")

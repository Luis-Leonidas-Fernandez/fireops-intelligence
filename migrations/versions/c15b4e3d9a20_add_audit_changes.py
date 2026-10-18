"""Add the inventory audit log from physical model 1.1.

Revision ID: c15b4e3d9a20
Revises: a6a239f7b4dc
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "c15b4e3d9a20"
down_revision: str | Sequence[str] | None = "a6a239f7b4dc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auditoria_cambios",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("operacion_id", UUID(as_uuid=True), nullable=True),
        sa.Column("entidad_tipo", sa.String(length=30), nullable=False),
        sa.Column("entidad_id", sa.BigInteger(), nullable=False),
        sa.Column("accion", sa.String(length=30), nullable=False),
        sa.Column("datos_anteriores", JSONB(), nullable=True),
        sa.Column("datos_nuevos", JSONB(), nullable=True),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("realizado_por_usuario_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "fecha",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "entidad_tipo IN ('BIEN', 'MOVIMIENTO', 'USUARIO', 'UBICACION', "
            "'CATEGORIA', 'OTRO')",
            name="ck_auditoria_cambios_entidad_tipo",
        ),
        sa.CheckConstraint(
            "accion IN ('ALTA', 'MODIFICACION', 'CORRECCION', "
            "'ELIMINACION_LOGICA', 'ELIMINACION_FISICA', 'RESTAURACION')",
            name="ck_auditoria_cambios_accion",
        ),
        sa.ForeignKeyConstraint(
            ["realizado_por_usuario_id"], ["usuarios.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_auditoria_cambios_entidad",
        "auditoria_cambios",
        ["entidad_tipo", "entidad_id"],
    )
    op.create_index(
        "ix_auditoria_cambios_operacion_id", "auditoria_cambios", ["operacion_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_auditoria_cambios_operacion_id", table_name="auditoria_cambios")
    op.drop_index("ix_auditoria_cambios_entidad", table_name="auditoria_cambios")
    op.drop_table("auditoria_cambios")

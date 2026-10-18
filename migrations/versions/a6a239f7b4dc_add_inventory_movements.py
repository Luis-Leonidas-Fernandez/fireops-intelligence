"""Add operational movement history for inventory assets.

Revision ID: a6a239f7b4dc
Revises: e42c7910b6af
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a6a239f7b4dc"
down_revision: str | Sequence[str] | None = "e42c7910b6af"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "movimientos",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("bien_id", sa.BigInteger(), nullable=False),
        sa.Column("usuario_id", sa.BigInteger(), nullable=False),
        sa.Column("tipo_movimiento", sa.String(length=30), nullable=False),
        sa.Column(
            "fecha",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("cantidad", sa.Integer(), nullable=True),
        sa.Column("ubicacion_origen_id", sa.BigInteger(), nullable=True),
        sa.Column("ubicacion_destino_id", sa.BigInteger(), nullable=True),
        sa.Column("estado_origen", sa.String(length=30), nullable=True),
        sa.Column("estado_destino", sa.String(length=30), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "tipo_movimiento IN ('ALTA', 'BAJA_TOTAL', 'BAJA_PARCIAL', "
            "'TRASLADO', 'ASIGNACION', 'DESASIGNACION', 'CAMBIO_ESTADO', "
            "'AJUSTE_CANTIDAD', 'RESTAURACION', 'CORRECCION')",
            name="ck_movimientos_tipo_movimiento",
        ),
        sa.CheckConstraint(
            "tipo_movimiento <> 'TRASLADO' OR "
            "(ubicacion_destino_id IS NOT NULL AND "
            "ubicacion_origen_id IS DISTINCT FROM ubicacion_destino_id)",
            name="ck_movimientos_traslado_destino",
        ),
        sa.ForeignKeyConstraint(["bien_id"], ["bienes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["ubicacion_origen_id"], ["ubicaciones.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["ubicacion_destino_id"], ["ubicaciones.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_movimientos_bien_id_fecha", "movimientos", ["bien_id", "fecha", "id"]
    )


def downgrade() -> None:
    op.drop_index("ix_movimientos_bien_id_fecha", table_name="movimientos")
    op.drop_table("movimientos")

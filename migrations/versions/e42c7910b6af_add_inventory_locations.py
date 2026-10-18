"""Add inventory locations and asset placement.

Revision ID: e42c7910b6af
Revises: d8b6e2f1940a
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e42c7910b6af"
down_revision: str | Sequence[str] | None = "d8b6e2f1940a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ubicaciones",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("bien_contenedor_id", sa.BigInteger(), nullable=True),
        sa.Column("nombre", sa.String(length=150), nullable=False),
        sa.Column("tipo_ubicacion", sa.String(length=20), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column(
            "activa", sa.Boolean(), server_default=sa.text("true"), nullable=False
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
        sa.CheckConstraint(
            "tipo_ubicacion IN ('FISICA', 'VEHICULO')",
            name="ck_ubicaciones_tipo_ubicacion",
        ),
        sa.CheckConstraint(
            "(tipo_ubicacion = 'FISICA' AND bien_contenedor_id IS NULL) OR "
            "(tipo_ubicacion = 'VEHICULO' AND bien_contenedor_id IS NOT NULL)",
            name="ck_ubicaciones_contenedor_por_tipo",
        ),
        sa.ForeignKeyConstraint(
            ["bien_contenedor_id"], ["bienes.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_ubicaciones_bien_contenedor_id",
        "ubicaciones",
        ["bien_contenedor_id"],
        unique=True,
        postgresql_where=sa.text("bien_contenedor_id IS NOT NULL"),
    )
    op.add_column("bienes", sa.Column("ubicacion_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_bienes_ubicacion_id_ubicaciones",
        "bienes",
        "ubicaciones",
        ["ubicacion_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_bienes_ubicacion_id", "bienes", ["ubicacion_id"])

    # Both sides can change through SQL, so validate the complete containment graph.
    op.execute(
        """
        CREATE FUNCTION prevent_location_containment_cycles()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF EXISTS (
                WITH RECURSIVE paths(current_id, seen, cycle) AS (
                    SELECT u.bien_contenedor_id,
                           ARRAY[b.id, u.bien_contenedor_id],
                           u.bien_contenedor_id = b.id
                    FROM bienes b
                    JOIN ubicaciones u ON u.id = b.ubicacion_id
                    WHERE u.bien_contenedor_id IS NOT NULL
                    UNION ALL
                    SELECT u.bien_contenedor_id,
                           paths.seen || u.bien_contenedor_id,
                           u.bien_contenedor_id = ANY(paths.seen)
                    FROM paths
                    JOIN bienes b ON b.id = paths.current_id
                    JOIN ubicaciones u ON u.id = b.ubicacion_id
                    WHERE NOT paths.cycle
                      AND u.bien_contenedor_id IS NOT NULL
                )
                SELECT 1 FROM paths WHERE cycle
            ) THEN
                RAISE EXCEPTION 'Location containment cycle is not allowed'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_bienes_location_cycle
        AFTER INSERT OR UPDATE OF ubicacion_id ON bienes
        FOR EACH ROW EXECUTE FUNCTION prevent_location_containment_cycles();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ubicaciones_location_cycle
        AFTER INSERT OR UPDATE OF bien_contenedor_id ON ubicaciones
        FOR EACH ROW EXECUTE FUNCTION prevent_location_containment_cycles();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_ubicaciones_location_cycle ON ubicaciones")
    op.execute("DROP TRIGGER trg_bienes_location_cycle ON bienes")
    op.execute("DROP FUNCTION prevent_location_containment_cycles()")
    op.drop_index("ix_bienes_ubicacion_id", table_name="bienes")
    op.drop_constraint(
        "fk_bienes_ubicacion_id_ubicaciones", "bienes", type_="foreignkey"
    )
    op.drop_column("bienes", "ubicacion_id")
    op.drop_index("uq_ubicaciones_bien_contenedor_id", table_name="ubicaciones")
    op.drop_table("ubicaciones")

"""Add advisory transaction lock to location cycle trigger function.

Revision ID: b3f81e7d2c94
Revises: a4d9c2b7e631
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b3f81e7d2c94"
down_revision: str | Sequence[str] | None = "a4d9c2b7e631"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_location_containment_cycles()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            -- Defensive guard: Enforce READ COMMITTED isolation level.
            -- Statement-level SPI snapshot refresh during lock wait requires READ COMMITTED.
            IF current_setting('transaction_isolation') <> 'read committed' THEN
                RAISE EXCEPTION 'Location containment hierarchy validation requires READ COMMITTED isolation level, current is %',
                    current_setting('transaction_isolation')
                    USING ERRCODE = '0A000';
            END IF;

            -- Transaction-scoped advisory lock serializes containment cycle validation
            -- across all write paths under PostgreSQL READ COMMITTED.
            PERFORM pg_advisory_xact_lock(hashtext('prevent_location_containment_cycles'));

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


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_location_containment_cycles()
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

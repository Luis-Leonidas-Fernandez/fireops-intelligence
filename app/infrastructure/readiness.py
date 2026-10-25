"""app/infrastructure/readiness.py.

FastAPI readiness probe implementation for PostgreSQL and schema compatibility.
Part of H-03 Stage D: Production Readiness, Operations Runbook, and Disaster Recovery.
"""

from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI_PATH = REPO_ROOT / "alembic.ini"


@lru_cache(maxsize=1)
def get_expected_migration_head() -> str | None:
    """Resolve and cache the expected Alembic migration head from repository files.

    Returns the head revision hash if configured, or None if alembic.ini is absent.
    Raises RuntimeError if divergent repository heads are detected.
    """
    if not ALEMBIC_INI_PATH.is_file():
        logger.warning(
            "alembic.ini not found at %s; migration check cannot verify head",
            ALEMBIC_INI_PATH,
        )
        return None

    config = Config(str(ALEMBIC_INI_PATH))
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()

    if not heads:
        return None
    if len(heads) > 1:
        raise RuntimeError(
            f"Multiple migration heads detected in repository: {heads}"
        )
    return heads[0]


def clear_cached_migration_head() -> None:
    """Clear cached migration head for testing purposes."""
    get_expected_migration_head.cache_clear()


def get_readiness_engine() -> AsyncEngine:
    """FastAPI dependency provider returning the shared database AsyncEngine."""
    from app.infrastructure.database.session import engine

    return engine


async def check_database_readiness(
    engine: AsyncEngine,
    timeout: float = 2.0,
    check_migration: bool = True,
    expected_revision: str | None = None,
) -> tuple[int, dict[str, Any]]:
    """Execute read-only readiness probes verifying connectivity and schema alignment.

    Guarantees:
    - Zero credentials, DSN strings, passwords, or internal traces in responses or logs.
    - Zero schema mutations (pure SELECT queries).
    - Explicit timeout handling via asyncio.timeout.
    - Transient recovery: no sticky failure state; recalculates dynamically on each call.

    Returns:
    - (200, {"status": "ready", "database": "connected"}) on full operational readiness.
    - (503, {"status": "unready", "database": "<reason>", "detail": "<safe message>"}) on failure.
    """
    try:
        async with asyncio.timeout(timeout):
            async with engine.connect() as conn:
                # 1. Pure read-only ping to verify live PostgreSQL connection
                await conn.execute(text("SELECT 1"))

                # 2. Schema compatibility verification
                if check_migration:
                    target_head = expected_revision
                    if target_head is None:
                        try:
                            target_head = get_expected_migration_head()
                        except RuntimeError:
                            return (
                                503,
                                {
                                    "status": "unready",
                                    "database": "schema_incompatible",
                                    "detail": "Multiple repository migration heads detected",
                                },
                            )

                    if target_head is not None:
                        # Verify existence of alembic_version table without raising an error
                        has_version_table = await conn.scalar(
                            text("SELECT to_regclass('alembic_version') IS NOT NULL")
                        )
                        if not has_version_table:
                            return (
                                503,
                                {
                                    "status": "unready",
                                    "database": "schema_not_initialized",
                                    "detail": "Database migration table is missing",
                                },
                            )

                        rows = (
                            await conn.execute(
                                text("SELECT version_num FROM alembic_version LIMIT 2")
                            )
                        ).scalars().all()

                        if not rows:
                            return (
                                503,
                                {
                                    "status": "unready",
                                    "database": "schema_empty",
                                    "detail": "No migration records found",
                                },
                            )
                        if len(rows) > 1:
                            return (
                                503,
                                {
                                    "status": "unready",
                                    "database": "schema_incompatible",
                                    "detail": "Multiple database revision heads detected",
                                },
                            )

                        current_rev = rows[0]
                        if current_rev != target_head:
                            return (
                                503,
                                {
                                    "status": "unready",
                                    "database": "schema_incompatible",
                                    "detail": "Database revision does not match expected version",
                                },
                            )

        return (
            200,
            {
                "status": "ready",
                "database": "connected",
            },
        )

    except TimeoutError:
        logger.warning("Database readiness probe timed out after %.1fs", timeout)
        return (
            503,
            {
                "status": "unready",
                "database": "unavailable",
                "detail": "Database readiness check timed out",
            },
        )
    except (SQLAlchemyError, OSError, RuntimeError, ValueError) as exc:
        # Mask exception details to prevent credential or internal topology leakage in logs
        logger.warning("Database readiness probe failed: %s", type(exc).__name__)
        return (
            503,
            {
                "status": "unready",
                "database": "unavailable",
                "detail": "Database connection failed",
            },
        )
    except Exception as exc:  # noqa: BLE001
        # Ultimate defensive fallback ensuring probe never raises an unhandled 500 error
        logger.warning("Unexpected database readiness probe error: %s", type(exc).__name__)
        return (
            503,
            {
                "status": "unready",
                "database": "unavailable",
                "detail": "Database connection failed",
            },
        )

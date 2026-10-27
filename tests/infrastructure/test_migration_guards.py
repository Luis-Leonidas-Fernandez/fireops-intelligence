"""Tests for Alembic fail-closed migration target guards and CLI isolation."""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from app.config.settings import Settings
from app.infrastructure.database.migration_guards import (
    MigrationTargetError,
    validate_migration_target,
)

ROOT = Path(__file__).resolve().parents[2]


# ==============================================================================
# Unit Tests for validate_migration_target
# ==============================================================================


def test_missing_database_url_raises_error():
    s = Settings(
        database_url="",
        secret_key="x" * 32,
    )
    with pytest.raises(MigrationTargetError, match="DATABASE_URL no está configurada"):
        validate_migration_target(s)


def test_malformed_database_url_raises_error():
    s = Settings(
        database_url="not_a_valid_url",
        secret_key="x" * 32,
    )
    with pytest.raises(MigrationTargetError, match="no es una URL de conexión válida"):
        validate_migration_target(s)


def test_development_environment_targeting_protected_fireassets_fails():
    s = Settings(
        database_url="postgresql+asyncpg://user:pass@localhost:5432/fireassets",
        environment="development",
        secret_key="x" * 32,
    )
    with patch.dict(os.environ, {"ENV_FILE": ".env"}, clear=False):
        with pytest.raises(MigrationTargetError, match="DISCREPANCIA PELIGROSA"):
            validate_migration_target(s)


def test_production_environment_targeting_test_database_fails():
    s = Settings(
        database_url="postgresql+asyncpg://user:pass@localhost:5432/fireassets_test",
        environment="production",
        secret_key="x" * 32,
    )
    with pytest.raises(MigrationTargetError, match="DISCREPANCIA PELIGROSA"):
        validate_migration_target(s)


def test_env_file_test_targeting_non_test_db_fails():
    s = Settings(
        database_url="postgresql+asyncpg://user:pass@localhost:5432/some_other_db",
        environment="development",
        secret_key="x" * 32,
    )
    with patch.dict(os.environ, {"ENV_FILE": ".env.test"}, clear=False):
        with pytest.raises(MigrationTargetError, match="DISCREPANCIA PELIGROSA"):
            validate_migration_target(s)


def test_production_without_explicit_env_file_fails():
    s = Settings(
        database_url="postgresql+asyncpg://user:pass@localhost:5432/fireassets",
        environment="production",
        secret_key="x" * 32,
    )
    with patch.dict(os.environ, {"ENV_FILE": ""}, clear=False):
        with pytest.raises(MigrationTargetError, match="BLOQUEO FAIL-CLOSED"):
            validate_migration_target(s)


def test_production_with_allow_migrations_alone_fails_without_db_confirmation():
    s = Settings(
        database_url="postgresql+asyncpg://user:pass@localhost:5432/fireassets",
        environment="production",
        secret_key="x" * 32,
    )
    with patch.dict(
        os.environ,
        {
            "ENV_FILE": ".env",
            "ALLOW_PRODUCTION_MIGRATIONS": "1",
            "CONFIRM_PRODUCTION_DATABASE": "",
        },
        clear=False,
    ):
        with pytest.raises(
            MigrationTargetError, match="Confirmación de base de producción incorrecta"
        ):
            validate_migration_target(s)


def test_production_with_wrong_confirmed_db_name_fails():
    s = Settings(
        database_url="postgresql+asyncpg://user:pass@localhost:5432/fireassets",
        environment="production",
        secret_key="x" * 32,
    )
    with patch.dict(
        os.environ,
        {
            "ENV_FILE": ".env",
            "ALLOW_PRODUCTION_MIGRATIONS": "1",
            "CONFIRM_PRODUCTION_DATABASE": "wrong_db_name",
        },
        clear=False,
    ):
        with pytest.raises(
            MigrationTargetError, match="Confirmación de base de producción incorrecta"
        ):
            validate_migration_target(s)


def test_valid_test_migration_target_succeeds():
    s = Settings(
        database_url="postgresql+asyncpg://user:pass@localhost:5432/fireassets_test",
        environment="development",
        secret_key="x" * 32,
    )
    with patch.dict(os.environ, {"ENV_FILE": ".env.test"}, clear=False):
        db = validate_migration_target(s)
        assert db == "fireassets_test"


def test_production_with_dual_confirmation_succeeds():
    s = Settings(
        database_url="postgresql+asyncpg://user:pass@localhost:5432/fireassets",
        environment="production",
        secret_key="x" * 32,
    )
    with patch.dict(
        os.environ,
        {
            "ENV_FILE": ".env",
            "ALLOW_PRODUCTION_MIGRATIONS": "1",
            "CONFIRM_PRODUCTION_DATABASE": "fireassets",
        },
        clear=False,
    ):
        db = validate_migration_target(s)
        assert db == "fireassets"


# ==============================================================================
# End-to-End CLI Tests: Naked Invocations Fail Closed
# ==============================================================================


def test_cli_naked_alembic_upgrade_head_fails_closed():
    """An accidental 'alembic upgrade head' without ENV_FILE must be blocked immediately."""
    env = {k: v for k, v in os.environ.items() if k not in ("ENV_FILE", "ALLOW_PRODUCTION_MIGRATIONS", "CONFIRM_PRODUCTION_DATABASE")}
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode != 0
    assert "BLOQUEO FAIL-CLOSED" in proc.stderr or "OPERACIÓN BLOQUEADA" in proc.stderr


def test_cli_naked_alembic_downgrade_fails_closed():
    """An accidental 'alembic downgrade -1' without ENV_FILE must be blocked immediately."""
    env = {k: v for k, v in os.environ.items() if k not in ("ENV_FILE", "ALLOW_PRODUCTION_MIGRATIONS", "CONFIRM_PRODUCTION_DATABASE")}
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "-1"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode != 0
    assert "BLOQUEO FAIL-CLOSED" in proc.stderr or "OPERACIÓN BLOQUEADA" in proc.stderr


def test_cli_naked_alembic_stamp_fails_closed():
    """An accidental 'alembic stamp head' without ENV_FILE must be blocked immediately."""
    env = {k: v for k, v in os.environ.items() if k not in ("ENV_FILE", "ALLOW_PRODUCTION_MIGRATIONS", "CONFIRM_PRODUCTION_DATABASE")}
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "stamp", "head"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode != 0
    assert "BLOQUEO FAIL-CLOSED" in proc.stderr or "OPERACIÓN BLOQUEADA" in proc.stderr


def test_cli_migrate_test_script_runs_safely():
    """scripts/migrate-test.sh with 'heads' or 'current' must safely target fireassets_test."""
    proc = subprocess.run(
        ["./scripts/migrate-test.sh", "heads"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "g3b7e1d5a8c2" in proc.stdout

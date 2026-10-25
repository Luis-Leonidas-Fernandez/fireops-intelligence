"""tests/test_migration_preflight.py.

Automated verification suite for Alembic & PostgreSQL migration preflight.
Part of H-03: Production Deployment & Data Recovery Architecture (Stage C).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import asyncpg  # type: ignore[import-untyped]
import pytest
import pytest_asyncio

ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT_SCRIPT = ROOT / "scripts" / "preflight_migrations.py"

FORBIDDEN_DATABASES: set[str] = {
    "fireassets",
    "fireassets_test",
    "fireassets_concurrency_test",
    "postgres",
    "template0",
    "template1",
}


def assert_safe_ephemeral_db_name(name: str) -> None:
    """Security assertion: Enforce isolated ephemeral naming pattern."""
    assert name.startswith("fireassets_preflight_"), (
        f"SAFETY VIOLATION: Database name '{name}' does not match ephemeral pattern!"
    )
    assert name.lower() not in FORBIDDEN_DATABASES, (
        f"SAFETY VIOLATION: Database name '{name}' targets a protected database!"
    )


async def execute_admin_sql(sql: str) -> None:
    """Execute administrative SQL statement against postgres maintenance database."""
    admin_conn = await asyncpg.connect(
        database="postgres",
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5432"),
        user=os.getenv("PGUSER", os.getenv("USER", "postgres")),
        password=os.getenv("PGPASSWORD", ""),
    )
    try:
        await admin_conn.execute(sql)
    finally:
        await admin_conn.close()


async def run_cli_command(
    cmd: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """Execute a CLI process asynchronously, capturing stdout and stderr."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return (
        proc.returncode if proc.returncode is not None else 0,
        stdout.decode(),
        stderr.decode(),
    )


@pytest_asyncio.fixture
async def ephemeral_preflight_db() -> AsyncGenerator[str, None]:
    """Fixture that provisions an isolated ephemeral database and guarantees teardown."""
    unique_suffix = uuid.uuid4().hex[:8]
    db_name = f"fireassets_preflight_{unique_suffix}"
    assert_safe_ephemeral_db_name(db_name)

    # Verify absence before creating
    admin_conn = await asyncpg.connect(
        database="postgres",
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5432"),
        user=os.getenv("PGUSER", os.getenv("USER", "postgres")),
        password=os.getenv("PGPASSWORD", ""),
    )
    try:
        exists = await admin_conn.fetchval(
            f"SELECT 1 FROM pg_database WHERE datname = '{db_name}';"
        )
        assert exists is None, f"SAFETY: DB '{db_name}' unexpectedly exists!"
        await admin_conn.execute(f'CREATE DATABASE "{db_name}";')
    finally:
        await admin_conn.close()

    try:
        yield db_name
    finally:
        assert_safe_ephemeral_db_name(db_name)
        await execute_admin_sql(f'DROP DATABASE IF EXISTS "{db_name}";')


async def run_alembic_upgrade(db_name: str, revision: str = "head") -> None:
    """Run Alembic upgrade to a specific target revision."""
    assert_safe_ephemeral_db_name(db_name)
    host = os.getenv("PGHOST", "localhost")
    port = os.getenv("PGPORT", "5432")
    user = os.getenv("PGUSER", os.getenv("USER", "postgres"))
    pw = os.getenv("PGPASSWORD", "")
    auth = f"{user}:{pw}@" if pw else f"{user}@"
    db_url = f"postgresql+asyncpg://{auth}{host}:{port}/{db_name}"

    env = os.environ.copy()
    env["DATABASE_URL"] = db_url

    rc, _, stderr = await run_cli_command(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        cwd=ROOT,
        env=env,
    )
    assert rc == 0, f"Alembic migration to {revision} failed (exit {rc}):\n{stderr}"


# ==============================================================================
# TEST SUITE: Migration Preflight
# ==============================================================================


@pytest.mark.asyncio
async def test_preflight_synced_database_returns_code_0(
    ephemeral_preflight_db: str,
) -> None:
    """Test scenario 1: Database fully migrated to repo head returns exit code 0 (SYNCED)."""
    db_name = ephemeral_preflight_db
    await run_alembic_upgrade(db_name, "head")

    rc, stdout, stderr = await run_cli_command(
        [sys.executable, str(PREFLIGHT_SCRIPT), db_name, "--json"]
    )
    assert rc == 0, f"Expected exit code 0, got {rc}. Stderr: {stderr}"
    data = json.loads(stdout)
    assert data["status"] == "SYNCED"
    assert data["exit_code"] == 0
    assert data["target_head"] == "b3f81e7d2c94"
    assert data["current_revision"] == "b3f81e7d2c94"
    assert data["pending_revisions"] == []
    assert data["is_empty"] is False
    assert data["has_version_table"] is True


@pytest.mark.asyncio
async def test_preflight_pending_migrations_returns_code_10(
    ephemeral_preflight_db: str,
) -> None:
    """Test scenario 2: Database at intermediate revision returns exit code 10 with ordered pending list."""
    db_name = ephemeral_preflight_db
    # Migrate to intermediate revision e7d4c2f9a621 (head is b3f81e7d2c94)
    intermediate_rev = "e7d4c2f9a621"
    await run_alembic_upgrade(db_name, intermediate_rev)

    rc, stdout, stderr = await run_cli_command(
        [sys.executable, str(PREFLIGHT_SCRIPT), db_name, "--json"]
    )
    assert rc == 10, f"Expected exit code 10 (PENDING_MIGRATIONS), got {rc}. Stderr: {stderr}"
    data = json.loads(stdout)
    assert data["status"] == "PENDING_MIGRATIONS"
    assert data["exit_code"] == 10
    assert data["current_revision"] == intermediate_rev
    assert data["target_head"] == "b3f81e7d2c94"
    # Expected pending chain in application order: f09a6e2112b4 -> a4d9c2b7e631 -> b3f81e7d2c94
    assert data["pending_revisions"] == [
        "f09a6e2112b4",
        "a4d9c2b7e631",
        "b3f81e7d2c94",
    ]


@pytest.mark.asyncio
async def test_preflight_empty_database_returns_code_11(
    ephemeral_preflight_db: str,
) -> None:
    """Test scenario 3: Fresh database with 0 tables returns exit code 11 (EMPTY_DATABASE)."""
    db_name = ephemeral_preflight_db
    # Ephemeral DB is created empty, do not run migrations

    rc, stdout, stderr = await run_cli_command(
        [sys.executable, str(PREFLIGHT_SCRIPT), db_name, "--json"]
    )
    assert rc == 11, f"Expected exit code 11 (EMPTY_DATABASE), got {rc}. Stderr: {stderr}"
    data = json.loads(stdout)
    assert data["status"] == "EMPTY_DATABASE"
    assert data["exit_code"] == 11
    assert data["is_empty"] is True
    assert data["table_count"] == 0
    assert data["has_version_table"] is False
    assert data["current_revision"] is None
    # All revisions from base to head should be listed as pending
    assert len(data["pending_revisions"]) >= 11
    assert data["pending_revisions"][-1] == "b3f81e7d2c94"


@pytest.mark.asyncio
async def test_preflight_unversioned_tables_returns_code_12(
    ephemeral_preflight_db: str,
) -> None:
    """Test scenario 4: Existing database with tables but no alembic_version table returns exit code 12."""
    db_name = ephemeral_preflight_db
    # Create an unversioned table
    conn = await asyncpg.connect(
        database=db_name,
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5432"),
        user=os.getenv("PGUSER", os.getenv("USER", "postgres")),
        password=os.getenv("PGPASSWORD", ""),
    )
    try:
        await conn.execute(
            "CREATE TABLE legacy_sample_table (id serial PRIMARY KEY, note text);"
        )
    finally:
        await conn.close()

    rc, stdout, stderr = await run_cli_command(
        [sys.executable, str(PREFLIGHT_SCRIPT), db_name, "--json"]
    )
    assert rc == 12, f"Expected exit code 12 (UNVERSIONED_TABLES), got {rc}. Stderr: {stderr}"
    data = json.loads(stdout)
    assert data["status"] == "UNVERSIONED_TABLES"
    assert data["exit_code"] == 12
    assert data["is_empty"] is False
    assert data["has_version_table"] is False
    assert data["table_count"] == 1


@pytest.mark.asyncio
async def test_preflight_empty_version_table_returns_code_12(
    ephemeral_preflight_db: str,
) -> None:
    """Test scenario 5: Database has alembic_version table but 0 rows returns exit code 12."""
    db_name = ephemeral_preflight_db
    conn = await asyncpg.connect(
        database=db_name,
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5432"),
        user=os.getenv("PGUSER", os.getenv("USER", "postgres")),
        password=os.getenv("PGPASSWORD", ""),
    )
    try:
        await conn.execute(
            "CREATE TABLE alembic_version (version_num varchar(32) NOT NULL);"
        )
    finally:
        await conn.close()

    rc, stdout, stderr = await run_cli_command(
        [sys.executable, str(PREFLIGHT_SCRIPT), db_name, "--json"]
    )
    assert rc == 12, f"Expected exit code 12 (UNVERSIONED_TABLES), got {rc}. Stderr: {stderr}"
    data = json.loads(stdout)
    assert data["status"] == "EMPTY_VERSION_TABLE"
    assert data["exit_code"] == 12


@pytest.mark.asyncio
async def test_preflight_divergent_unknown_revision_returns_code_20(
    ephemeral_preflight_db: str,
) -> None:
    """Test scenario 6: Database version does not exist in repository returns exit code 20 (DIVERGENT)."""
    db_name = ephemeral_preflight_db
    conn = await asyncpg.connect(
        database=db_name,
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5432"),
        user=os.getenv("PGUSER", os.getenv("USER", "postgres")),
        password=os.getenv("PGPASSWORD", ""),
    )
    try:
        await conn.execute(
            """
            CREATE TABLE alembic_version (version_num varchar(32) NOT NULL);
            INSERT INTO alembic_version (version_num) VALUES ('deadbeef9999_unknown');
            """
        )
    finally:
        await conn.close()

    rc, stdout, stderr = await run_cli_command(
        [sys.executable, str(PREFLIGHT_SCRIPT), db_name, "--json"]
    )
    assert rc == 20, f"Expected exit code 20 (DIVERGENT_REVISION), got {rc}. Stderr: {stderr}"
    data = json.loads(stdout)
    assert data["status"] == "DIVERGENT_REVISION"
    assert data["exit_code"] == 20
    assert "does not exist in repository" in data["message"]


@pytest.mark.asyncio
async def test_preflight_multiple_db_heads_returns_code_22(
    ephemeral_preflight_db: str,
) -> None:
    """Test scenario 7: Multiple version rows in alembic_version returns exit code 22 (MULTIPLE_DB_HEADS)."""
    db_name = ephemeral_preflight_db
    conn = await asyncpg.connect(
        database=db_name,
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5432"),
        user=os.getenv("PGUSER", os.getenv("USER", "postgres")),
        password=os.getenv("PGPASSWORD", ""),
    )
    try:
        await conn.execute(
            """
            CREATE TABLE alembic_version (version_num varchar(32) NOT NULL);
            INSERT INTO alembic_version (version_num) VALUES ('0374d9a573a1');
            INSERT INTO alembic_version (version_num) VALUES ('b70e8e0479aa');
            """
        )
    finally:
        await conn.close()

    rc, stdout, stderr = await run_cli_command(
        [sys.executable, str(PREFLIGHT_SCRIPT), db_name, "--json"]
    )
    assert rc == 22, f"Expected exit code 22 (MULTIPLE_DB_HEADS), got {rc}. Stderr: {stderr}"
    data = json.loads(stdout)
    assert data["status"] == "MULTIPLE_DB_HEADS"
    assert data["exit_code"] == 22


@pytest.mark.asyncio
async def test_preflight_connection_error_and_credentials_masked() -> None:
    """Test scenario 8: Unreachable PostgreSQL returns exit code 30 and never leaks passwords."""
    secret_pass = "super_classified_pw_12345"
    bad_dsn = f"postgresql://admin_user:{secret_pass}@127.0.0.1:54329/non_existent_db"

    rc, stdout, stderr = await run_cli_command(
        [sys.executable, str(PREFLIGHT_SCRIPT), bad_dsn, "--json"]
    )
    assert rc == 30, f"Expected exit code 30 (CONNECTION_ERROR), got {rc}"
    data = json.loads(stdout)
    assert data["status"] == "CONNECTION_ERROR"
    assert data["exit_code"] == 30
    # Strict secrecy check
    assert secret_pass not in stdout
    assert secret_pass not in stderr
    assert "admin_user:***@" in data["message"] or secret_pass not in data["message"]


@pytest.mark.asyncio
async def test_preflight_configuration_error_missing_ini() -> None:
    """Test scenario 9: Missing configuration file returns exit code 31 (CONFIGURATION_ERROR)."""
    rc, stdout, _stderr = await run_cli_command(
        [
            sys.executable,
            str(PREFLIGHT_SCRIPT),
            "any_db",
            "--config",
            "non_existent_alembic_config.ini",
            "--json",
        ]
    )
    assert rc == 31, f"Expected exit code 31 (CONFIGURATION_ERROR), got {rc}"
    data = json.loads(stdout)
    assert data["status"] == "CONFIGURATION_ERROR"
    assert data["exit_code"] == 31


@pytest.mark.asyncio
async def test_preflight_zero_database_mutations(
    ephemeral_preflight_db: str,
) -> None:
    """Test scenario 10: Preflight is strictly read-only and never modifies database objects or rows."""
    db_name = ephemeral_preflight_db
    await run_alembic_upgrade(db_name, "0374d9a573a1")

    # Snapshot tables and records before preflight
    conn = await asyncpg.connect(
        database=db_name,
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5432"),
        user=os.getenv("PGUSER", os.getenv("USER", "postgres")),
        password=os.getenv("PGPASSWORD", ""),
    )
    try:
        tables_before = await conn.fetch(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;"
        )
        rev_before = await conn.fetchval("SELECT version_num FROM alembic_version;")
    finally:
        await conn.close()

    # Execute preflight multiple times
    for _ in range(3):
        rc, _, _ = await run_cli_command(
            [sys.executable, str(PREFLIGHT_SCRIPT), db_name, "--json"]
        )
        assert rc == 10

    # Snapshot tables and records after preflight
    conn = await asyncpg.connect(
        database=db_name,
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5432"),
        user=os.getenv("PGUSER", os.getenv("USER", "postgres")),
        password=os.getenv("PGPASSWORD", ""),
    )
    try:
        tables_after = await conn.fetch(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;"
        )
        rev_after = await conn.fetchval("SELECT version_num FROM alembic_version;")
    finally:
        await conn.close()

    assert tables_before == tables_after, "SAFETY: Preflight modified table catalog!"
    assert rev_before == rev_after, "SAFETY: Preflight modified Alembic revision!"


@pytest.mark.asyncio
async def test_preflight_human_readable_text_output(
    ephemeral_preflight_db: str,
) -> None:
    """Test scenario 11: Text output emits clean human-readable report without --json."""
    db_name = ephemeral_preflight_db
    await run_alembic_upgrade(db_name, "head")

    rc, stdout, _stderr = await run_cli_command(
        [sys.executable, str(PREFLIGHT_SCRIPT), db_name]
    )
    assert rc == 0
    assert "ALEMBIC MIGRATION PREFLIGHT REPORT" in stdout
    assert f"Database:          {db_name}" in stdout
    assert "Status:            SYNCED ✅" in stdout
    assert "Exit Code:         0" in stdout
    assert "Current DB Rev:    b3f81e7d2c94" in stdout
    assert "Repository Head:   b3f81e7d2c94" in stdout
    assert "Pending Count:     0" in stdout


@pytest.mark.asyncio
async def test_preflight_early_errors_never_leak_credentials() -> None:
    """Test scenario 12: Early errors (missing config, invalid params, URLs without path) never leak secrets."""
    secret = "classified_early_leak_pass_7788"

    # 1. Missing alembic.ini with URL containing password
    bad_config_url = f"postgresql://admin:{secret}@localhost:5432/mydb"
    rc, stdout, stderr = await run_cli_command(
        [
            sys.executable,
            str(PREFLIGHT_SCRIPT),
            bad_config_url,
            "--config",
            "non_existent_ini_file.ini",
            "--json",
        ]
    )
    assert rc == 31
    assert secret not in stdout, "Password leaked in stdout on missing config!"
    assert secret not in stderr, "Password leaked in stderr on missing config!"
    data1 = json.loads(stdout)
    assert data1["database"] == "mydb"
    assert secret not in data1["database"]

    # 2. URL without database path
    no_path_url = f"postgresql://admin:{secret}@127.0.0.1:5432"
    rc2, stdout2, stderr2 = await run_cli_command(
        [
            sys.executable,
            str(PREFLIGHT_SCRIPT),
            no_path_url,
            "--config",
            "non_existent_ini_file.ini",
            "--json",
        ]
    )
    assert rc2 == 31
    assert secret not in stdout2
    assert secret not in stderr2
    data2 = json.loads(stdout2)
    assert secret not in data2["database"]
    assert "127.0.0.1:5432/<unspecified>" in data2["database"]

    # 3. URL with malformed parameters
    malformed_url = f"postgresql://admin:{secret}@invalid_host::port/db"
    rc3, stdout3, stderr3 = await run_cli_command(
        [sys.executable, str(PREFLIGHT_SCRIPT), malformed_url, "--json"]
    )
    assert rc3 in (30, 31)
    assert secret not in stdout3
    assert secret not in stderr3
    data3 = json.loads(stdout3)
    assert secret not in data3["database"]


def test_sanitize_dsn_ipv6_and_various_formats() -> None:
    """Test scenario 13: sanitize_dsn successfully masks IPv4, IPv6 ([::1]), DNS, and complex passwords."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import preflight_migrations  # type: ignore[import-not-found]

    cases = [
        ("postgresql://user:pass@[::1]:5432/db", "postgresql://user:***@[::1]:5432/db"),
        (
            "postgresql://user:pass@[2001:db8::1]:5432/db",
            "postgresql://user:***@[2001:db8::1]:5432/db",
        ),
        (
            "postgresql://admin:secret_pass@127.0.0.1:5432/mydb",
            "postgresql://admin:***@127.0.0.1:5432/mydb",
        ),
        (
            "postgresql://admin:secret_pass@db.internal.corp:5432/mydb",
            "postgresql://admin:***@db.internal.corp:5432/mydb",
        ),
        (
            "postgresql://usr:p%40ss%3Aword%23%3F%24@[::1]/testdb",
            "postgresql://usr:***@[::1]/testdb",
        ),
        (
            "Error: failed connecting to postgresql://admin:unquoted@password@[::1]:5432/db in asyncpg",
            "Error: failed connecting to postgresql://admin:***@[::1]:5432/db in asyncpg",
        ),
    ]

    for raw, expected in cases:
        sanitized = preflight_migrations.sanitize_dsn(raw)
        assert "pass" not in sanitized or "password" in raw
        assert "***@" in sanitized
        assert sanitized == expected, f"Failed on raw: {raw}\nGot: {sanitized}"


@pytest.mark.asyncio
async def test_preflight_classifies_interface_error_as_code_30(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test scenario 14: asyncpg.InterfaceError is classified as code 30 (CONNECTION_ERROR)."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import preflight_migrations  # type: ignore[import-not-found]

    async def mock_inspect(*_args: Any, **_kwargs: Any) -> Any:
        raise asyncpg.InterfaceError("Simulated client-side handshake/SSL failure")

    monkeypatch.setattr(
        preflight_migrations, "inspect_database_schema", mock_inspect
    )

    result = await preflight_migrations.run_preflight(
        "mock_db", Path("alembic.ini")
    )
    assert result["exit_code"] == 30
    assert result["status"] == "CONNECTION_ERROR"
    assert "Simulated client-side handshake/SSL failure" in result["message"]


@pytest.mark.asyncio
async def test_runbook_deployment_script_pattern_executable(
    tmp_path: Path,
) -> None:
    """Test scenario 15: Executable test of runbook deployment script pattern under set -euo pipefail."""
    bash_script = tmp_path / "deploy_test.sh"
    # Create an executable mock preflight runner that accepts an exit code and status to simulate
    mock_preflight = tmp_path / "mock_preflight.sh"
    mock_preflight.write_text(
        """#!/usr/bin/env bash
SIMULATED_CODE="$1"
SIMULATED_STATUS="$2"
echo "{\\"status\\": \\"$SIMULATED_STATUS\\", \\"exit_code\\": $SIMULATED_CODE}"
exit "$SIMULATED_CODE"
"""
    )
    mock_preflight.chmod(0o755)

    # Test the exact runbook template logic for all exit codes
    template = f"""#!/usr/bin/env bash
set -euo pipefail

TARGET_CODE="$1"
TARGET_STATUS="$2"

set +e
PREFLIGHT_OUTPUT="$("{mock_preflight}" "$TARGET_CODE" "$TARGET_STATUS" 2>&1)"
PREFLIGHT_CODE=$?
set -e

PREFLIGHT_STATUS="$(echo "$PREFLIGHT_OUTPUT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', 'ERROR'))" 2>/dev/null || echo "UNKNOWN")"

case "$PREFLIGHT_CODE" in
  0)
    echo "ACTION: DEPLOY_CODE ($PREFLIGHT_STATUS)"
    ;;
  10)
    echo "ACTION: RUN_MIGRATIONS ($PREFLIGHT_STATUS)"
    ;;
  11)
    echo "ACTION: INITIAL_SCHEMA ($PREFLIGHT_STATUS)"
    ;;
  *)
    echo "ACTION: BLOCKED ($PREFLIGHT_CODE, $PREFLIGHT_STATUS)" >&2
    exit "$PREFLIGHT_CODE"
    ;;
esac
"""
    bash_script.write_text(template)
    bash_script.chmod(0o755)

    # 1. Test code 0 (SYNCED)
    rc0, out0, _ = await run_cli_command([str(bash_script), "0", "SYNCED"])
    assert rc0 == 0
    assert "ACTION: DEPLOY_CODE (SYNCED)" in out0

    # 2. Test code 10 (PENDING_MIGRATIONS) -> must not abort under set -e!
    rc10, out10, _ = await run_cli_command(
        [str(bash_script), "10", "PENDING_MIGRATIONS"]
    )
    assert rc10 == 0
    assert "ACTION: RUN_MIGRATIONS (PENDING_MIGRATIONS)" in out10

    # 3. Test code 11 (EMPTY_DATABASE) -> must not abort under set -e!
    rc11, out11, _ = await run_cli_command(
        [str(bash_script), "11", "EMPTY_DATABASE"]
    )
    assert rc11 == 0
    assert "ACTION: INITIAL_SCHEMA (EMPTY_DATABASE)" in out11

    # 4. Test code 12, 20, 21, 22, 30, 31 -> must block and exit with that exact code!
    for block_code, block_status in (
        ("12", "UNVERSIONED_TABLES"),
        ("20", "DIVERGENT_REVISION"),
        ("21", "MULTIPLE_REPO_HEADS"),
        ("22", "MULTIPLE_DB_HEADS"),
        ("30", "CONNECTION_ERROR"),
        ("31", "CONFIGURATION_ERROR"),
    ):
        rc_b, _, err_b = await run_cli_command(
            [str(bash_script), block_code, block_status]
        )
        assert rc_b == int(block_code)
        assert f"ACTION: BLOCKED ({block_code}, {block_status})" in err_b

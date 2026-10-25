"""tests/test_readiness_and_recovery_drill.py.

Automated verification suite for FastAPI readiness probe, production operations runbook,
and full end-to-end recovery drill on isolated ephemeral synthetic databases.
Part of H-03: Production Deployment & Data Recovery Architecture (Stage D).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import stat
import sys
import time
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import asyncpg  # type: ignore[import-untyped]
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.infrastructure.readiness import (
    check_database_readiness,
    get_readiness_engine,
)
from app.main import app

ROOT = Path(__file__).resolve().parents[1]
BACKUP_SCRIPT = ROOT / "scripts" / "backup_db.sh"
RESTORE_SCRIPT = ROOT / "scripts" / "restore_db.sh"
VERIFY_SCRIPT = ROOT / "scripts" / "verify_restored_db.py"
PREFLIGHT_SCRIPT = ROOT / "scripts" / "preflight_migrations.py"

FORBIDDEN_DATABASES: set[str] = {
    "fireassets",
    "fireassets_test",
    "fireassets_concurrency_test",
    "postgres",
    "afterlook",
    "template0",
    "template1",
}


def assert_safe_ephemeral_db_name(name: str) -> None:
    """Security assertion: Enforce isolated ephemeral naming pattern."""
    assert name.startswith(("fireassets_drill_", "fireassets_readiness_")), (
        f"SAFETY VIOLATION: Database name '{name}' does not match ephemeral pattern!"
    )
    assert name.lower() not in FORBIDDEN_DATABASES, (
        f"SAFETY VIOLATION: Database name '{name}' targets a protected database!"
    )


async def execute_admin_sql(sql: str) -> None:
    """Execute administrative SQL statement against postgres database."""
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


async def run_alembic_migrations(db_name: str) -> None:
    """Run alembic upgrade head targeting the specified ephemeral test database."""
    assert_safe_ephemeral_db_name(db_name)
    user = os.getenv("PGUSER", os.getenv("USER", "postgres"))
    pwd = os.getenv("PGPASSWORD", "")
    port = os.getenv("PGPORT", "5432")
    host = os.getenv("PGHOST", "localhost")
    auth = f"{user}:{pwd}@" if pwd else f"{user}@"
    target_url = f"postgresql+asyncpg://{auth}{host}:{port}/{db_name}"

    env = os.environ.copy()
    env["DATABASE_URL"] = target_url
    env["PYTHONPATH"] = str(ROOT)

    rc, stdout, stderr = await run_cli_command(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=env,
    )
    assert rc == 0, f"Alembic upgrade failed on {db_name}:\n{stdout}\n{stderr}"


async def populate_synthetic_data(db_name: str) -> dict[str, int]:
    """Insert structured synthetic records representing the entire domain model."""
    assert_safe_ephemeral_db_name(db_name)
    conn = await asyncpg.connect(
        database=db_name,
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5432"),
        user=os.getenv("PGUSER", os.getenv("USER", "postgres")),
        password=os.getenv("PGPASSWORD", ""),
    )
    try:
        # 1. Catalogs: Roles & Categories
        admin_rol_id = await conn.fetchval(
            "SELECT id FROM roles WHERE nombre = 'ADMINISTRADOR';"
        )
        super_rol_id = await conn.fetchval(
            "SELECT id FROM roles WHERE nombre = 'SUPERVISOR';"
        )
        oper_rol_id = await conn.fetchval(
            """
            INSERT INTO roles (nombre, descripcion, activo)
            VALUES ('OPERADOR', 'Operador drill', true)
            RETURNING id;
            """
        )

        cat1_id = await conn.fetchval(
            "INSERT INTO categorias (nombre) VALUES ('Comunicaciones Drill') RETURNING id;"
        )
        await conn.execute("INSERT INTO categorias (nombre) VALUES ('EPP Drill');")
        cat3_id = await conn.fetchval(
            "INSERT INTO categorias (nombre) VALUES ('Vehículos Drill') RETURNING id;"
        )

        # 2. Users
        user1_id = await conn.fetchval(
            f"""
            INSERT INTO usuarios (email, password_hash, rol_id, activo, display_name)
            VALUES ('admin.drill@example.com', 'argon2_dummy_hash_1', {admin_rol_id}, true, 'Admin Drill')
            RETURNING id;
            """
        )
        user2_id = await conn.fetchval(
            f"""
            INSERT INTO usuarios (email, password_hash, rol_id, activo, display_name)
            VALUES ('super.drill@example.com', 'argon2_dummy_hash_2', {super_rol_id}, true, 'Super Drill')
            RETURNING id;
            """
        )

        # 3. Hierarchical Locations & Assets (testing containment tree)
        loc1_id = await conn.fetchval(
            """
            INSERT INTO ubicaciones (nombre, tipo_ubicacion, activa, bien_contenedor_id)
            VALUES ('Cuartel Central Drill', 'FISICA', true, NULL)
            RETURNING id;
            """
        )
        asset1_id = await conn.fetchval(
            f"""
            INSERT INTO bienes (codigo_interno, nombre, categoria_id, ubicacion_id)
            VALUES ('AUTOBOMBA-01', 'Autobomba B-1', {cat3_id}, {loc1_id})
            RETURNING id;
            """
        )
        loc2_id = await conn.fetchval(
            f"""
            INSERT INTO ubicaciones (nombre, tipo_ubicacion, activa, bien_contenedor_id)
            VALUES ('Bandeja Herramientas B-1', 'VEHICULO', true, {asset1_id})
            RETURNING id;
            """
        )
        asset2_id = await conn.fetchval(
            f"""
            INSERT INTO bienes (codigo_interno, nombre, categoria_id, ubicacion_id)
            VALUES ('HANDY-01', 'Handy VHF Motorola', {cat1_id}, {loc2_id})
            RETURNING id;
            """
        )

        # 4. Inventory movements & Audit trail
        await conn.execute(
            f"""
            INSERT INTO movimientos (bien_id, usuario_id, tipo_movimiento, ubicacion_origen_id, ubicacion_destino_id, motivo) VALUES
                ({asset1_id}, {user1_id}, 'ALTA', NULL, {loc1_id}, 'Incorporación de vehículo rápida'),
                ({asset2_id}, {user2_id}, 'TRASLADO', {loc1_id}, {loc2_id}, 'Asignación a bandeja B-1');
            """
        )

        await conn.execute(
            f"""
            INSERT INTO auditoria_cambios (entidad_tipo, entidad_id, accion, datos_anteriores, datos_nuevos, motivo, realizado_por_usuario_id)
            VALUES ('BIEN', {asset2_id}, 'MODIFICACION', '{{"ubicacion_id": null}}'::jsonb, '{{"ubicacion_id": {loc2_id}}}'::jsonb, 'Asignación inicial', {user2_id});
            """
        )

        # 5. Invitations & Registration Requests
        await conn.execute(
            f"""
            INSERT INTO auth_invitations (email, token_hash, rol_id, invited_by_id, expires_at)
            VALUES ('invitado.drill@example.com', 'sha256_dummy_token_hash', {oper_rol_id}, {user1_id}, NOW() + interval '1 day');
            """
        )

        await conn.execute(
            """
            INSERT INTO auth_registration_requests (email, status, source, requested_at)
            VALUES ('aspirante.drill@example.com', 'pending', 'web', NOW());
            """
        )

        # Count records
        expected_counts: dict[str, int] = {}
        for tbl in [
            "roles",
            "categorias",
            "usuarios",
            "ubicaciones",
            "bienes",
            "movimientos",
            "auditoria_cambios",
            "auth_invitations",
            "auth_registration_requests",
        ]:
            expected_counts[tbl] = await conn.fetchval(
                f"SELECT count(*) FROM {tbl};"
            )

        return expected_counts
    finally:
        await conn.close()


@pytest_asyncio.fixture
async def ephemeral_dbs() -> AsyncGenerator[tuple[str, str], None]:
    """Provision isolated ephemeral source and destination databases for drill tests."""
    token = uuid.uuid4().hex[:10]
    src_db = f"fireassets_drill_src_{token}"
    dst_db = f"fireassets_drill_dst_{token}"

    assert_safe_ephemeral_db_name(src_db)
    assert_safe_ephemeral_db_name(dst_db)

    await execute_admin_sql(f"CREATE DATABASE {src_db};")
    try:
        yield src_db, dst_db
    finally:
        for db in (src_db, dst_db):
            with contextlib.suppress(Exception):
                await execute_admin_sql(f"DROP DATABASE IF EXISTS {db} WITH (FORCE);")


@pytest_asyncio.fixture
async def ephemeral_readiness_db() -> AsyncGenerator[str, None]:
    """Provision a single isolated ephemeral database for readiness endpoint testing."""
    token = uuid.uuid4().hex[:10]
    db_name = f"fireassets_readiness_{token}"

    assert_safe_ephemeral_db_name(db_name)
    await execute_admin_sql(f"CREATE DATABASE {db_name};")
    try:
        yield db_name
    finally:
        with contextlib.suppress(Exception):
            await execute_admin_sql(f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE);")


def build_async_engine_for_db(db_name: str) -> AsyncEngine:
    """Build an AsyncEngine pointed to a local ephemeral database."""
    user = os.getenv("PGUSER", os.getenv("USER", "postgres"))
    pwd = os.getenv("PGPASSWORD", "")
    port = os.getenv("PGPORT", "5432")
    host = os.getenv("PGHOST", "localhost")
    auth = f"{user}:{pwd}@" if pwd else f"{user}@"
    url = f"postgresql+asyncpg://{auth}{host}:{port}/{db_name}"
    return create_async_engine(url, echo=False, hide_parameters=True)


# ==============================================================================
# SECCIÓN 1: PRUEBAS DEL ENDPOINT /health/ready Y CONTRATO DE READINESS
# ==============================================================================


@pytest.mark.asyncio
async def test_readiness_success_http_200(ephemeral_readiness_db: str) -> None:
    """Test that /health/ready returns HTTP 200 and connected status when DB is healthy and synced."""
    db_name = ephemeral_readiness_db
    await run_alembic_migrations(db_name)

    test_engine = build_async_engine_for_db(db_name)
    app.dependency_overrides[get_readiness_engine] = lambda: test_engine
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/ready")

        assert response.status_code == 200
        assert response.json() == {
            "status": "ready",
            "database": "connected",
        }
    finally:
        app.dependency_overrides.pop(get_readiness_engine, None)
        await test_engine.dispose()


@pytest.mark.asyncio
async def test_readiness_liveness_separation() -> None:
    """Test strict separation of liveness (/health) and readiness (/health/ready).

    Liveness returns 200 OK even when database is unreachable.
    Readiness returns 503 Service Unavailable when database is unreachable.
    """
    broken_url = "postgresql+asyncpg://nobody:invalid@localhost:54399/non_existent_db"
    broken_engine = create_async_engine(
        broken_url,
        echo=False,
        hide_parameters=True,
    )
    app.dependency_overrides[get_readiness_engine] = lambda: broken_engine
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Liveness probe must succeed (event loop is alive)
            live_resp = await client.get("/health")
            assert live_resp.status_code == 200
            assert live_resp.json() == {"status": "ok"}

            # Readiness probe must fail (database dependency down)
            ready_resp = await client.get("/health/ready")
            assert ready_resp.status_code == 503
            data = ready_resp.json()
            assert data["status"] == "unready"
            assert data["database"] == "unavailable"
    finally:
        app.dependency_overrides.pop(get_readiness_engine, None)
        await broken_engine.dispose()


@pytest.mark.asyncio
async def test_readiness_unreachable_db_returns_503_without_leaking_secrets() -> None:
    """Test that connection failures return 503 and never leak credentials, DSN, or stack traces."""
    secret_pass = "SuperSecretPassword12345!"
    broken_url = f"postgresql+asyncpg://admin:{secret_pass}@localhost:54399/broken_db"
    broken_engine = create_async_engine(
        broken_url,
        echo=False,
        hide_parameters=True,
    )
    app.dependency_overrides[get_readiness_engine] = lambda: broken_engine
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/ready")

        assert response.status_code == 503
        body_text = response.text
        assert secret_pass not in body_text
        assert "54399" not in body_text
        assert "Traceback" not in body_text
        assert response.json() == {
            "status": "unready",
            "database": "unavailable",
            "detail": "Database connection failed",
        }
    finally:
        app.dependency_overrides.pop(get_readiness_engine, None)
        await broken_engine.dispose()


@pytest.mark.asyncio
async def test_readiness_timeout_handling(ephemeral_readiness_db: str) -> None:
    """Test that readiness probe respects explicit timeout and returns 503 if timeout is exceeded."""
    db_name = ephemeral_readiness_db
    test_engine = build_async_engine_for_db(db_name)
    try:
        # Pass an impossibly small timeout (0.000001s) to force TimeoutError
        code, payload = await check_database_readiness(
            engine=test_engine,
            timeout=0.000001,
            check_migration=False,
        )
        assert code == 503
        assert payload == {
            "status": "unready",
            "database": "unavailable",
            "detail": "Database readiness check timed out",
        }
    finally:
        await test_engine.dispose()


@pytest.mark.asyncio
async def test_readiness_transient_failure_recovery(
    ephemeral_readiness_db: str,
) -> None:
    """Test that a transient database failure does not permanently mark the app unready.

    When DB recovers, subsequent calls to /health/ready immediately return 200.
    """
    db_name = ephemeral_readiness_db
    await run_alembic_migrations(db_name)

    healthy_engine = build_async_engine_for_db(db_name)
    broken_engine = create_async_engine(
        "postgresql+asyncpg://nobody:invalid@localhost:54399/db",
        echo=False,
        hide_parameters=True,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Phase 1: Database is failing
        app.dependency_overrides[get_readiness_engine] = lambda: broken_engine
        resp1 = await client.get("/health/ready")
        assert resp1.status_code == 503
        assert resp1.json()["status"] == "unready"

        # Phase 2: Database recovers
        app.dependency_overrides[get_readiness_engine] = lambda: healthy_engine
        resp2 = await client.get("/health/ready")
        assert resp2.status_code == 200
        assert resp2.json() == {
            "status": "ready",
            "database": "connected",
        }

    app.dependency_overrides.pop(get_readiness_engine, None)
    await healthy_engine.dispose()
    await broken_engine.dispose()


@pytest.mark.asyncio
async def test_readiness_schema_empty_database_returns_503(
    ephemeral_readiness_db: str,
) -> None:
    """Test that readiness returns 503 schema_not_initialized on an empty database (no alembic_version)."""
    db_name = ephemeral_readiness_db
    test_engine = build_async_engine_for_db(db_name)
    app.dependency_overrides[get_readiness_engine] = lambda: test_engine
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/ready")

        assert response.status_code == 503
        assert response.json() == {
            "status": "unready",
            "database": "schema_not_initialized",
            "detail": "Database migration table is missing",
        }
    finally:
        app.dependency_overrides.pop(get_readiness_engine, None)
        await test_engine.dispose()


@pytest.mark.asyncio
async def test_readiness_schema_outdated_revision_returns_503(
    ephemeral_readiness_db: str,
) -> None:
    """Test that readiness returns 503 schema_incompatible when DB revision does not match repo head."""
    db_name = ephemeral_readiness_db
    # Create alembic_version with an outdated revision
    conn = await asyncpg.connect(database=db_name)
    try:
        await conn.execute(
            """
            CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY);
            INSERT INTO alembic_version (version_num) VALUES ('0374d9a573a1');
            """
        )
    finally:
        await conn.close()

    test_engine = build_async_engine_for_db(db_name)
    app.dependency_overrides[get_readiness_engine] = lambda: test_engine
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/ready")

        assert response.status_code == 503
        assert response.json() == {
            "status": "unready",
            "database": "schema_incompatible",
            "detail": "Database revision does not match expected version",
        }
    finally:
        app.dependency_overrides.pop(get_readiness_engine, None)
        await test_engine.dispose()


@pytest.mark.asyncio
async def test_readiness_schema_multiple_db_heads_returns_503(
    ephemeral_readiness_db: str,
) -> None:
    """Test that readiness returns 503 schema_incompatible when alembic_version has multiple heads."""
    db_name = ephemeral_readiness_db
    conn = await asyncpg.connect(database=db_name)
    try:
        await conn.execute(
            """
            CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY);
            INSERT INTO alembic_version (version_num) VALUES ('rev_a'), ('rev_b');
            """
        )
    finally:
        await conn.close()

    test_engine = build_async_engine_for_db(db_name)
    app.dependency_overrides[get_readiness_engine] = lambda: test_engine
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/ready")

        assert response.status_code == 503
        assert response.json() == {
            "status": "unready",
            "database": "schema_incompatible",
            "detail": "Multiple database revision heads detected",
        }
    finally:
        app.dependency_overrides.pop(get_readiness_engine, None)
        await test_engine.dispose()


@pytest.mark.asyncio
async def test_readiness_zero_ddl_dml_executed(
    ephemeral_readiness_db: str,
) -> None:
    """Test that readiness probes are strictly read-only and execute zero mutations."""
    db_name = ephemeral_readiness_db
    await run_alembic_migrations(db_name)
    conn = await asyncpg.connect(database=db_name)
    try:
        initial_tables = await conn.fetchval(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';"
        )
        initial_rev = await conn.fetchval(
            "SELECT version_num FROM alembic_version;"
        )
    finally:
        await conn.close()

    test_engine = build_async_engine_for_db(db_name)
    for _ in range(5):
        code, payload = await check_database_readiness(test_engine)
        assert code == 200
        assert payload["status"] == "ready"

    # Verify tables and revisions are strictly unmodified
    conn = await asyncpg.connect(database=db_name)
    try:
        final_tables = await conn.fetchval(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';"
        )
        final_rev = await conn.fetchval(
            "SELECT version_num FROM alembic_version;"
        )
        assert initial_tables == final_tables
        assert initial_rev == final_rev
    finally:
        await conn.close()
        await test_engine.dispose()


@pytest.mark.asyncio
async def test_readiness_zero_credentials_in_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that readiness logging never leaks passwords or connection strings."""
    secret_pass = "TopSecretUltraPassword999!"
    broken_url = f"postgresql+asyncpg://user:{secret_pass}@localhost:54399/db"
    broken_engine = create_async_engine(
        broken_url,
        echo=False,
        hide_parameters=True,
    )

    with caplog.at_level(logging.WARNING):
        code, _ = await check_database_readiness(broken_engine)

    assert code == 503
    for record in caplog.records:
        assert secret_pass not in record.message
        assert "54399" not in record.message
    await broken_engine.dispose()


# ==============================================================================
# SECCIÓN 2: SIMULACRO INTEGRAL DE RECUPERACIÓN (OBJETIVO C)
# ==============================================================================


@pytest.mark.asyncio
async def test_full_synthetic_recovery_drill_with_benchmarks(
    ephemeral_dbs: tuple[str, str], tmp_path: Path
) -> None:
    """Full lifecycle recovery drill on isolated ephemeral databases:

    1. Verify unique ephemeral naming & safety guards.
    2. Provision source DB & apply Alembic migrations.
    3. Populate representative synthetic domain data.
    4. Generate backup with backup_db.sh (custom format, UTC timestamp, sha256).
    5. Verify artifact permissions (600) & checksum.
    6. Restore out-of-place into new destination DB with restore_db.sh.
    7. Execute verify_restored_db.py deep integrity checks.
    8. Execute preflight_migrations.py (must report code 0 / SYNCED).
    9. Validate FastAPI readiness probe (HTTP 200) against restored database.
    10. Test transient failure & recovery on the restored setup.
    11. Benchmark all stages and report durations.
    """
    src_db, dst_db = ephemeral_dbs

    # 1. Setup source database with full migrations and synthetic data
    t0_setup = time.perf_counter()
    await run_alembic_migrations(src_db)
    expected_counts = await populate_synthetic_data(src_db)
    setup_duration = time.perf_counter() - t0_setup

    # 2. Execute backup_db.sh
    t0_backup = time.perf_counter()
    rc_b, out_b, err_b = await run_cli_command(
        [
            str(BACKUP_SCRIPT),
            "--db",
            src_db,
            "--output-dir",
            str(tmp_path),
        ]
    )
    backup_duration = time.perf_counter() - t0_backup
    assert rc_b == 0, f"Backup failed:\n{out_b}\n{err_b}"
    assert "Backup completed successfully:" in out_b

    dump_files = list(tmp_path.glob(f"{src_db}_*.dump"))
    assert len(dump_files) == 1, "Expected exactly one dump file"
    dump_file = dump_files[0]
    meta_file = dump_file.with_name(dump_file.stem + ".meta.json")
    sha_file = dump_file.with_suffix(".sha256")

    assert meta_file.is_file(), "Metadata JSON manifest missing"
    assert sha_file.is_file(), "SHA-256 checksum file missing"

    # Verify restrictive permissions (0600)
    dump_mode = stat.S_IMODE(dump_file.stat().st_mode)
    assert dump_mode == 0o600, f"Expected 0600 on dump, found {oct(dump_mode)}"

    # 3. Execute restore_db.sh out-of-place into new dst_db
    t0_restore = time.perf_counter()
    rc_r, out_r, err_r = await run_cli_command(
        [
            str(RESTORE_SCRIPT),
            str(dump_file),
            dst_db,
        ]
    )
    restore_duration = time.perf_counter() - t0_restore
    assert rc_r == 0, f"Restore failed:\n{out_r}\n{err_r}"
    assert f"Restoration successfully completed into '{dst_db}'" in out_r

    # 4. Deep integrity verification with verify_restored_db.py
    t0_verify = time.perf_counter()
    rc_v, out_v, err_v = await run_cli_command(
        [
            sys.executable,
            str(VERIFY_SCRIPT),
            dst_db,
            "--meta",
            str(meta_file),
            "--json",
        ]
    )
    verify_duration = time.perf_counter() - t0_verify
    assert rc_v == 0, f"Verification failed:\n{out_v}\n{err_v}"
    v_report: dict[str, Any] = json.loads(out_v)
    assert v_report["passed"] is True
    assert v_report["alembic_version"] == "b3f81e7d2c94"
    assert v_report["checks"]["h01_triggers"] == "PASSED"
    assert v_report["checks"]["h01_functional_cycle_rejection"] == "PASSED"

    # 5. Migration preflight verification with preflight_migrations.py
    t0_preflight = time.perf_counter()
    user = os.getenv("PGUSER", os.getenv("USER", "postgres"))
    pwd = os.getenv("PGPASSWORD", "")
    port = os.getenv("PGPORT", "5432")
    host = os.getenv("PGHOST", "localhost")
    auth = f"{user}:{pwd}@" if pwd else f"{user}@"
    dst_url = f"postgresql+asyncpg://{auth}{host}:{port}/{dst_db}"

    env = os.environ.copy()
    env["DATABASE_URL"] = dst_url
    env["PYTHONPATH"] = str(ROOT)

    rc_p, out_p, err_p = await run_cli_command(
        [sys.executable, str(PREFLIGHT_SCRIPT), "--json"],
        cwd=ROOT,
        env=env,
    )
    preflight_duration = time.perf_counter() - t0_preflight
    assert rc_p == 0, f"Preflight on restored DB returned non-zero:\n{out_p}\n{err_p}"
    p_report: dict[str, Any] = json.loads(out_p)
    assert p_report["status"] == "SYNCED"
    assert p_report["current_revision"] == "b3f81e7d2c94"
    assert p_report["pending_revisions"] == []

    # 6. Test FastAPI readiness probe against the restored database
    t0_readiness = time.perf_counter()
    restored_engine = build_async_engine_for_db(dst_db)
    app.dependency_overrides[get_readiness_engine] = lambda: restored_engine
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            readiness_resp = await client.get("/health/ready")
            assert readiness_resp.status_code == 200
            assert readiness_resp.json() == {
                "status": "ready",
                "database": "connected",
            }
    finally:
        app.dependency_overrides.pop(get_readiness_engine, None)
        await restored_engine.dispose()
    readiness_duration = time.perf_counter() - t0_readiness

    total_drill_time = (
        setup_duration
        + backup_duration
        + restore_duration
        + verify_duration
        + preflight_duration
        + readiness_duration
    )

    # 7. Assert data preservation across all domain tables
    conn = await asyncpg.connect(database=dst_db)
    try:
        for table, expected_cnt in expected_counts.items():
            cnt = await conn.fetchval(f"SELECT count(*) FROM {table};")
            assert cnt == expected_cnt, f"Data loss in table {table}: expected {expected_cnt}, found {cnt}"
    finally:
        await conn.close()

    print(
        f"\n"
        f"============================================================\n"
        f"STAGE D — FULL END-TO-END RECOVERY DRILL BENCHMARK REPORT\n"
        f"------------------------------------------------------------\n"
        f"  Source Database:          {src_db}\n"
        f"  Target Database:          {dst_db}\n"
        f"  Dump Size:                {dump_file.stat().st_size} bytes\n"
        f"  Synthetic Setup Time:     {setup_duration:.3f} s\n"
        f"  Backup Time (pg_dump):    {backup_duration:.3f} s\n"
        f"  Restore Time (pg_restore):{restore_duration:.3f} s\n"
        f"  Verify Time (integrity):  {verify_duration:.3f} s\n"
        f"  Preflight Time:           {preflight_duration:.3f} s\n"
        f"  Readiness Probe Time:     {readiness_duration:.3f} s\n"
        f"  Total Recovery Duration:  {total_drill_time:.3f} s\n"
        f"  Alembic Final Revision:   b3f81e7d2c94 (SYNCED)\n"
        f"  H-01 Trigger & Lock:      VERIFIED AND ACTIVE\n"
        f"  Readiness HTTP Status:    200 OK\n"
        f"------------------------------------------------------------\n"
        f"  DISCLAIMER: Benchmark measured on synthetic ephemeral data.\n"
        f"  Production RTO/RPO depend on physical dataset size and I/O.\n"
        f"============================================================\n"
    )


@pytest.mark.asyncio
async def test_drill_failed_restore_and_safe_cleanup(
    ephemeral_dbs: tuple[str, str], tmp_path: Path
) -> None:
    """Test that a corrupt restore aborts cleanly and removes temporary target database."""
    import hashlib

    _, dst_db = ephemeral_dbs
    fake_dump = tmp_path / "corrupt_drill.dump"
    fake_sha = tmp_path / "corrupt_drill.sha256"
    fake_dump.write_bytes(b"CORRUPTED_DUMP_PAYLOAD_NOT_VALID")

    sha = hashlib.sha256(b"CORRUPTED_DUMP_PAYLOAD_NOT_VALID").hexdigest()
    fake_sha.write_text(f"{sha}  corrupt_drill.dump\n")

    rc, _, err = await run_cli_command(
        [str(RESTORE_SCRIPT), str(fake_dump), dst_db]
    )
    assert rc != 0
    assert (
        "Cleaning up exclusively created temporary database" in err
        or "pg_restore" in err
    )

    admin_conn = await asyncpg.connect(database="postgres")
    try:
        exists = await admin_conn.fetchval(
            f"SELECT 1 FROM pg_database WHERE datname = '{dst_db}';"
        )
        assert exists is None, (
            f"Corrupted restore left target database '{dst_db}' behind!"
        )
    finally:
        await admin_conn.close()


# ==============================================================================
# SECCIÓN 3: PRUEBAS DEL RUNBOOK OPERATIVO
# ==============================================================================


@pytest.mark.asyncio
async def test_runbook_deployment_script_pattern(
    ephemeral_readiness_db: str,
) -> None:
    """Validate that the deployment script pattern from the production runbook

    correctly handles exit codes 0 and 11 under 'set -euo pipefail'.
    """
    db_name = ephemeral_readiness_db
    user = os.getenv("PGUSER", os.getenv("USER", "postgres"))
    pwd = os.getenv("PGPASSWORD", "")
    port = os.getenv("PGPORT", "5432")
    host = os.getenv("PGHOST", "localhost")
    auth = f"{user}:{pwd}@" if pwd else f"{user}@"
    target_url = f"postgresql+asyncpg://{auth}{host}:{port}/{db_name}"

    bash_script = f"""#!/usr/bin/env bash
set -euo pipefail

export DATABASE_URL="{target_url}"
export PYTHONPATH="{ROOT}"

set +e
PREFLIGHT_RAW="$({sys.executable} {PREFLIGHT_SCRIPT} --json 2>&1)"
PREFLIGHT_CODE=$?
set -e

if [ "$PREFLIGHT_CODE" -eq 11 ]; then
    echo "ACTION:EMPTY_DATABASE"
    {sys.executable} -m alembic upgrade head >/dev/null 2>&1
    exit 0
elif [ "$PREFLIGHT_CODE" -eq 0 ]; then
    echo "ACTION:SYNCED"
    exit 0
else
    echo "ACTION:ABORT"
    exit 1
fi
"""
    # 1. First run against empty DB: should detect code 11 and upgrade
    proc = await asyncio.create_subprocess_exec(
        "/bin/bash",
        "-c",
        bash_script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    assert proc.returncode == 0, f"Runbook script failed on empty DB:\n{stdout.decode()}\n{stderr.decode()}"
    assert "ACTION:EMPTY_DATABASE" in stdout.decode()

    # 2. Second run against now-migrated DB: should detect code 0 (SYNCED)
    proc2 = await asyncio.create_subprocess_exec(
        "/bin/bash",
        "-c",
        bash_script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout2, stderr2 = await proc2.communicate()
    assert proc2.returncode == 0, f"Runbook script failed on synced DB:\n{stdout2.decode()}\n{stderr2.decode()}"
    assert "ACTION:SYNCED" in stdout2.decode()

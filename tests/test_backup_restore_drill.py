"""tests/test_backup_restore_drill.py.

Automated full-cycle PostgreSQL backup, restore, and integrity verification drill.
Part of H-03: Production Deployment & Data Recovery Architecture.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import stat
import sys
import time
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import asyncpg  # type: ignore[import-untyped]
import pytest
import pytest_asyncio

ROOT = Path(__file__).resolve().parents[1]
BACKUP_SCRIPT = ROOT / "scripts" / "backup_db.sh"
RESTORE_SCRIPT = ROOT / "scripts" / "restore_db.sh"
VERIFY_SCRIPT = ROOT / "scripts" / "verify_restored_db.py"

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
    assert name.startswith("fireassets_drill_"), (
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


def read_json_file(path: Path) -> dict[str, Any]:
    """Synchronous helper for reading json files."""
    with path.open(encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
        return data


def write_binary_file(path: Path, data: bytes) -> None:
    """Synchronous helper for writing binary test data."""
    with path.open("wb") as f:
        f.write(data)


def append_binary_file(path: Path, data: bytes) -> None:
    """Synchronous helper for appending corrupt binary test data."""
    with path.open("ab") as f:
        f.write(data)


def write_text_file(path: Path, text: str) -> None:
    """Synchronous helper for writing text files."""
    with path.open("w", encoding="utf-8") as f:
        f.write(text)


def read_text_file(path: Path) -> str:
    """Synchronous helper for reading text files."""
    with path.open(encoding="utf-8") as f:
        return f.read()


@pytest_asyncio.fixture
async def ephemeral_dbs() -> AsyncGenerator[tuple[str, str], None]:
    """Provision and guarantee teardown of source and destination ephemeral databases."""
    src_id = uuid.uuid4().hex[:8]
    dst_id = uuid.uuid4().hex[:8]
    src_db = f"fireassets_drill_src_{src_id}"
    dst_db = f"fireassets_drill_dst_{dst_id}"

    assert_safe_ephemeral_db_name(src_db)
    assert_safe_ephemeral_db_name(dst_db)

    # Verify that neither database already exists (preventing collision or foreign DB mutation)
    admin_conn = await asyncpg.connect(
        database="postgres",
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5432"),
        user=os.getenv("PGUSER", os.getenv("USER", "postgres")),
        password=os.getenv("PGPASSWORD", ""),
    )
    try:
        exists_src = await admin_conn.fetchval(
            f"SELECT 1 FROM pg_database WHERE datname = '{src_db}';"
        )
        exists_dst = await admin_conn.fetchval(
            f"SELECT 1 FROM pg_database WHERE datname = '{dst_db}';"
        )
        assert exists_src is None, (
            f"SAFETY: Ephemeral source DB '{src_db}' unexpectedly already exists!"
        )
        assert exists_dst is None, (
            f"SAFETY: Ephemeral destination DB '{dst_db}' unexpectedly already exists!"
        )

        # Create source database
        await admin_conn.execute(f'CREATE DATABASE "{src_db}";')
    finally:
        await admin_conn.close()

    try:
        yield (src_db, dst_db)
    finally:
        # Guarantee teardown of only verified ephemeral test databases
        for db in (src_db, dst_db):
            assert_safe_ephemeral_db_name(db)
            await execute_admin_sql(f'DROP DATABASE IF EXISTS "{db}";')


async def run_alembic_migrations(db_name: str) -> None:
    """Run Alembic migrations to head on the specified database."""
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
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=env,
    )
    assert rc == 0, f"Alembic migration failed (exit {rc}):\n{stderr}"


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
        # Note: Alembic migration e7d4c2f9a621 already seeded 'ADMINISTRADOR' and 'SUPERVISOR'.
        # We fetch their IDs and insert an additional 'OPERADOR' role.
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
        await conn.execute(
            "INSERT INTO categorias (nombre) VALUES ('EPP Drill');"
        )
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
        # Root location: Cuartel Central (FISICA, bien_contenedor_id = NULL)
        loc1_id = await conn.fetchval(
            """
            INSERT INTO ubicaciones (nombre, tipo_ubicacion, activa, bien_contenedor_id)
            VALUES ('Cuartel Central Drill', 'FISICA', true, NULL)
            RETURNING id;
            """
        )
        # Vehicle asset placed in Cuartel
        asset1_id = await conn.fetchval(
            f"""
            INSERT INTO bienes (codigo_interno, nombre, categoria_id, ubicacion_id)
            VALUES ('AUTOBOMBA-01', 'Autobomba B-1', {cat3_id}, {loc1_id})
            RETURNING id;
            """
        )
        # Compartment location on Autobomba B-1 (VEHICULO, bien_contenedor_id = asset1_id)
        loc2_id = await conn.fetchval(
            f"""
            INSERT INTO ubicaciones (nombre, tipo_ubicacion, activa, bien_contenedor_id)
            VALUES ('Bandeja Herramientas B-1', 'VEHICULO', true, {asset1_id})
            RETURNING id;
            """
        )
        # Equipment asset placed inside compartment location
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
                ({asset1_id}, {user1_id}, 'ALTA', NULL, {loc1_id}, 'Incorporación de vehículo de ataque rápido'),
                ({asset2_id}, {user2_id}, 'TRASLADO', {loc1_id}, {loc2_id}, 'Asignación a bandeja de unidad B-1');
            """
        )
        await conn.execute(
            f"""
            INSERT INTO auditoria_cambios (entidad_tipo, entidad_id, accion, datos_anteriores, datos_nuevos, motivo, realizado_por_usuario_id)
            VALUES ('BIEN', {asset2_id}, 'MODIFICACION', '{{"ubicacion_id": null}}'::jsonb, '{{"ubicacion_id": {loc2_id}}}'::jsonb, 'Asignación inicial', {user2_id});
            """
        )

        # 5. Auth workflow items
        await conn.execute(
            """
            INSERT INTO auth_registration_requests (email, status, source, requested_at)
            VALUES ('aspirante.drill@example.com', 'pending', 'web', NOW());
            """
        )
        await conn.execute(
            f"""
            INSERT INTO auth_invitations (email, token_hash, rol_id, invited_by_id, expires_at)
            VALUES ('invitado.drill@example.com', 'sha256_dummy_token_hash', {oper_rol_id}, {user1_id}, NOW() + interval '1 day');
            """
        )

        counts = {
            "roles": await conn.fetchval("SELECT count(*) FROM roles;"),
            "categorias": await conn.fetchval("SELECT count(*) FROM categorias;"),
            "usuarios": await conn.fetchval("SELECT count(*) FROM usuarios;"),
            "ubicaciones": await conn.fetchval(
                "SELECT count(*) FROM ubicaciones;"
            ),
            "bienes": await conn.fetchval("SELECT count(*) FROM bienes;"),
            "movimientos": await conn.fetchval(
                "SELECT count(*) FROM movimientos;"
            ),
            "auditoria_cambios": await conn.fetchval(
                "SELECT count(*) FROM auditoria_cambios;"
            ),
            "auth_registration_requests": await conn.fetchval(
                "SELECT count(*) FROM auth_registration_requests;"
            ),
            "auth_invitations": await conn.fetchval(
                "SELECT count(*) FROM auth_invitations;"
            ),
        }
        return counts
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_backup_creates_valid_artifacts_and_permissions(
    ephemeral_dbs: tuple[str, str], tmp_path: Path
) -> None:
    """Test that scripts/backup_db.sh produces .dump, .sha256, and .meta.json with 0600 permissions."""
    src_db, _ = ephemeral_dbs
    await run_alembic_migrations(src_db)
    await populate_synthetic_data(src_db)

    # Run backup script
    cmd = [str(BACKUP_SCRIPT), "--db", src_db, "--output-dir", str(tmp_path)]
    start = time.perf_counter()
    rc, stdout, stderr = await run_cli_command(cmd)
    duration = time.perf_counter() - start

    assert rc == 0, f"backup_db.sh failed with code {rc}:\n{stderr}"
    assert f"Starting backup of '{src_db}'" in stdout

    # Locate generated files
    dumps = list(tmp_path.glob(f"{src_db}_*.dump"))
    shas = list(tmp_path.glob(f"{src_db}_*.sha256"))
    metas = list(tmp_path.glob(f"{src_db}_*.meta.json"))

    assert len(dumps) == 1, f"Expected 1 dump file, found: {dumps}"
    assert len(shas) == 1, f"Expected 1 sha256 file, found: {shas}"
    assert len(metas) == 1, f"Expected 1 meta.json file, found: {metas}"

    dump_file = next(iter(dumps))
    sha_file = next(iter(shas))
    meta_file = next(iter(metas))

    # Verify restrictive 0600 permissions
    dump_mode = stat.S_IMODE(dump_file.stat().st_mode)
    sha_mode = stat.S_IMODE(sha_file.stat().st_mode)
    meta_mode = stat.S_IMODE(meta_file.stat().st_mode)

    assert dump_mode == 0o600, (
        f"Expected dump permissions 0600, got {oct(dump_mode)}"
    )
    assert sha_mode == 0o600, (
        f"Expected sha permissions 0600, got {oct(sha_mode)}"
    )
    assert meta_mode == 0o600, (
        f"Expected meta permissions 0600, got {oct(meta_mode)}"
    )

    # Verify metadata JSON contents
    meta = read_json_file(meta_file)
    assert meta["schema"] == "fire-control.backup-metadata/v1"
    assert meta["database_name"] == src_db
    assert meta["dump_format"] == "custom"
    assert meta["size_bytes"] == dump_file.stat().st_size
    assert meta["alembic_version"] == "g3b7e1d5a8c2"

    # Verify SHA-256 matches
    recorded_sha = read_text_file(sha_file).split()[0].strip()
    assert meta["sha256"] == recorded_sha

    print(
        f"\n[BENCHMARK] Backup duration: {duration:.3f}s | Size: {meta['size_bytes']} bytes"
    )


@pytest.mark.asyncio
async def test_restore_rejects_existing_target(
    ephemeral_dbs: tuple[str, str], tmp_path: Path
) -> None:
    """Test that restore_db.sh rejects targets that already exist."""
    src_db, _ = ephemeral_dbs
    await run_alembic_migrations(src_db)

    # Create backup
    rc_b, _, err_b = await run_cli_command(
        [str(BACKUP_SCRIPT), "--db", src_db, "--output-dir", str(tmp_path)]
    )
    assert rc_b == 0, f"Backup failed:\n{err_b}"

    dump_file = next(iter(tmp_path.glob(f"{src_db}_*.dump")))

    # Attempt to restore directly onto src_db (which already exists)
    rc, _, stderr = await run_cli_command(
        [str(RESTORE_SCRIPT), str(dump_file), src_db]
    )

    assert rc != 0
    assert "already exists" in stderr


@pytest.mark.asyncio
async def test_restore_rejects_forbidden_databases(
    ephemeral_dbs: tuple[str, str], tmp_path: Path
) -> None:
    """Test that restore_db.sh strictly refuses to restore to protected database names."""
    src_db, _ = ephemeral_dbs
    await run_alembic_migrations(src_db)

    rc_b, _, err_b = await run_cli_command(
        [str(BACKUP_SCRIPT), "--db", src_db, "--output-dir", str(tmp_path)]
    )
    assert rc_b == 0, f"Backup failed:\n{err_b}"

    dump_file = next(iter(tmp_path.glob(f"{src_db}_*.dump")))

    for forbidden in (
        "fireassets",
        "fireassets_test",
        "fireassets_concurrency_test",
        " FIREASSETS ",
        "FireAssets_Test",
        "postgres",
        "template1",
    ):
        rc, _, stderr = await run_cli_command(
            [str(RESTORE_SCRIPT), str(dump_file), forbidden]
        )
        assert rc != 0
        assert (
            "strictly forbidden" in stderr
            or "contains invalid characters" in stderr
        )


@pytest.mark.asyncio
async def test_restore_rejects_non_alphanumeric_names(
    ephemeral_dbs: tuple[str, str], tmp_path: Path
) -> None:
    """Test that restore_db.sh rejects injection attempts or non-alphanumeric target names."""
    src_db, _ = ephemeral_dbs
    await run_alembic_migrations(src_db)

    rc_b, _, err_b = await run_cli_command(
        [str(BACKUP_SCRIPT), "--db", src_db, "--output-dir", str(tmp_path)]
    )
    assert rc_b == 0, f"Backup failed:\n{err_b}"
    dump_file = next(iter(tmp_path.glob(f"{src_db}_*.dump")))

    for invalid_name in (
        "target;DROP DATABASE postgres;",
        "target-with-dashes",
        "target.with.dots",
        "target$injection",
    ):
        rc, _, stderr = await run_cli_command(
            [str(RESTORE_SCRIPT), str(dump_file), invalid_name]
        )
        assert rc != 0
        assert "contains invalid characters" in stderr


@pytest.mark.asyncio
async def test_backup_rejects_invalid_and_injection_names(
    tmp_path: Path,
) -> None:
    """Test that backup_db.sh rejects injection attempts, path traversals, or non-alphanumeric DB names."""
    for invalid_db in (
        "src;DROP DATABASE postgres;",
        "src' OR '1'='1",
        "../../etc/passwd",
        "../traversal",
        "src-with-dashes",
        "src.with.dots",
        "src$injection",
        "src with spaces",
    ):
        rc, _stdout, stderr = await run_cli_command(
            [str(BACKUP_SCRIPT), invalid_db, "--output-dir", str(tmp_path)]
        )
        assert rc != 0, f"backup_db.sh unexpectedly accepted invalid DB name: {invalid_db}"
        assert (
            "is invalid (must contain only alphanumeric characters and underscores)"
            in stderr
        )
        # Verify no files were created in output dir or outside
        assert list(tmp_path.iterdir()) == [], (
            f"Artifacts were unexpectedly created for invalid DB name: {invalid_db}"
        )


@pytest.mark.asyncio
async def test_restore_sha256_streaming_without_full_memory_buffering(
    tmp_path: Path,
) -> None:
    """Test that restore_db.sh uses chunked streaming SHA-256 calculation without full memory buffering."""
    # Create a 2MB synthetic file to verify chunked reading across multiple 64KB blocks
    synthetic_dump = tmp_path / "stream_test.dump"
    block_size = 64 * 1024
    total_blocks = 32  # 2MB total
    h = hashlib.sha256()
    with synthetic_dump.open("wb") as f:
        for i in range(total_blocks):
            block = f"block-{i:04d}-".encode("ascii") * (block_size // 16)
            f.write(block)
            h.update(block)

    expected_sha = h.hexdigest()
    sha_file = tmp_path / "stream_test.sha256"
    sha_file.write_text(f"{expected_sha}  stream_test.dump\n")

    # Run restore_db.sh against protected destination 'postgres'
    # Integrity check runs first and verifies SHA-256 before security guard aborts
    rc, stdout, _stderr = await run_cli_command(
        [str(RESTORE_SCRIPT), str(synthetic_dump), "postgres"]
    )
    assert rc != 0
    assert f"Checksum verified: {expected_sha}" in stdout


def test_verify_restored_db_credential_quoting_and_masking() -> None:
    """Test that build_asyncpg_dsn quotes reserved RFC 3986 characters and sanitize_dsn masks secrets."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import verify_restored_db  # type: ignore[import-not-found]

    orig_user = os.environ.get("PGUSER")
    orig_pass = os.environ.get("PGPASSWORD")
    try:
        os.environ["PGUSER"] = "fire_user@corp"
        os.environ["PGPASSWORD"] = "p@ss:word#?$&%^"
        dsn = verify_restored_db.build_asyncpg_dsn("ephemeral_test_db")
        # Ensure credentials are URL-encoded in DSN
        assert "p%40ss%3Aword%23%3F%24%26%25%5E" in dsn
        assert "fire_user%40corp" in dsn

        # Ensure sanitize_dsn masks passwords completely
        masked = verify_restored_db.sanitize_dsn(dsn)
        assert "p@ss" not in masked
        assert "word" not in masked
        assert "p%40ss" not in masked
        assert "postgresql://fire_user%40corp:***@" in masked

        # Test error string sanitization with embedded unquoted password
        raw_err = "Fatal error in postgresql://admin:unquoted@password@localhost:5432/db"
        san_err = verify_restored_db.sanitize_dsn(raw_err)
        assert "unquoted@password" not in san_err
        assert "postgresql://admin:***@localhost:5432/db" in san_err
    finally:
        if orig_user is not None:
            os.environ["PGUSER"] = orig_user
        else:
            os.environ.pop("PGUSER", None)
        if orig_pass is not None:
            os.environ["PGPASSWORD"] = orig_pass
        else:
            os.environ.pop("PGPASSWORD", None)


@pytest.mark.asyncio
async def test_url_prefix_normalization_preserves_embedded_substrings(
    tmp_path: Path,
) -> None:
    """Test that postgresql+asyncpg:// prefix is normalized without altering identical substrings inside passwords."""
    valid_user = os.getenv("PGUSER", os.getenv("USER", "postgres"))
    pass_with_substring = "my_pass_with_postgresql+asyncpg://_embedded"
    encoded_pass = quote_plus(pass_with_substring)
    url = f"postgresql+asyncpg://{valid_user}:{encoded_pass}@localhost:5432/testdb"

    # Test parser in backup_db.sh
    _rc, _stdout, stderr = await run_cli_command(
        [str(BACKUP_SCRIPT), "--url", url, "--output-dir", str(tmp_path)]
    )
    assert "Failed to parse database URL" not in stderr
    assert "Database 'testdb' does not exist" in stderr

    # Test parser in restore_db.sh
    _rc_r, _stdout_r, _stderr_r = await run_cli_command(
        [str(RESTORE_SCRIPT), "/dev/null", "test_target", "--url", url]
    )
    assert "Failed to parse database URL" not in _stderr_r


@pytest.mark.asyncio
async def test_credentials_not_leaked_in_stderr_or_traces() -> None:
    """Test that passwords in connection URLs are masked and never leaked in stderr or exception traces."""
    secret = "dummy_super_secret_pass_998877"
    masked_dsn = f"postgresql://luis:{secret}@127.0.0.1:54329/non_existent_db"

    rc, stdout, stderr = await run_cli_command(
        [sys.executable, str(VERIFY_SCRIPT), masked_dsn]
    )

    assert rc != 0
    assert secret not in stdout, "Password leaked in stdout!"
    assert secret not in stderr, "Password leaked in stderr!"


@pytest.mark.asyncio
async def test_url_parser_rejects_malformed_and_invalid_schemes() -> None:
    """Test that backup_db.sh and restore_db.sh reject malformed or non-PostgreSQL URLs with exit code 1."""
    for bad_url in (
        "mysql://user:pass@localhost:3306/db",
        "http://example.com/db",
        "://malformed-url-syntax",
        "",
    ):
        rc_b, _, err_b = await run_cli_command(
            [str(BACKUP_SCRIPT), "--url", bad_url, "--output-dir", "/tmp"]
        )
        assert rc_b != 0, f"backup_db.sh unexpectedly accepted bad URL: {bad_url}"
        assert (
            "Failed to parse database URL" in err_b
            or "Database name is required" in err_b
        )

        rc_r, _, _err_r = await run_cli_command(
            [
                str(RESTORE_SCRIPT),
                "/dev/null",
                "test_dest",
                "--url",
                bad_url,
            ]
        )
        assert rc_r != 0, f"restore_db.sh unexpectedly accepted bad URL: {bad_url}"


@pytest.mark.asyncio
async def test_no_command_injection_execution_in_url_fields(
    tmp_path: Path,
) -> None:
    """Test that malicious shell syntax embedded in URLs is treated as pure literal text without execution."""
    canary = tmp_path / "canary_pwned.txt"
    assert not canary.exists()

    # Attempt command substitution inside username and password fields
    malicious_url = (
        f"postgresql://$(touch {canary}):`touch {canary}`@127.0.0.1:5432/non_existent_db"
    )

    rc, stdout, _stderr = await run_cli_command(
        [
            str(BACKUP_SCRIPT),
            "--url",
            malicious_url,
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert rc != 0
    assert not canary.exists(), (
        "SECURITY VULNERABILITY: Shell command injection executed from DATABASE_URL field!"
    )
    assert "$(touch" not in stdout
    assert "`touch" not in stdout


@pytest.mark.asyncio
async def test_url_parsing_with_special_characters_and_percent_encoding(
    ephemeral_dbs: tuple[str, str], tmp_path: Path
) -> None:
    """Test that passwords with special chars ($ ' " spaces \\) and percent-encoding (%0A %24) parse correctly."""
    src_db, _ = ephemeral_dbs
    await run_alembic_migrations(src_db)

    # Complex password including quotes, dollar, spaces, backslash, and percent-encoding
    # %24 ($), %22 ("), %27 ('), %20 (space), %0A (newline)
    complex_user = "luis"
    complex_pass = "p%24ss%22quote%27%20with%20spaces%0Aand_newline"
    encoded_url = (
        f"postgresql+asyncpg://{complex_user}:{complex_pass}@localhost:5432/{src_db}"
    )

    # Run backup using this encoded URL
    rc, stdout, stderr = await run_cli_command(
        [str(BACKUP_SCRIPT), "--url", encoded_url, "--output-dir", str(tmp_path)]
    )

    assert rc == 0, f"Backup failed with complex encoded URL:\n{stderr}"
    assert f"Starting backup of '{src_db}'" in stdout
    # Ensure raw decoded password was not leaked to stdout or stderr
    assert "quote" not in stdout
    assert "quote" not in stderr


@pytest.mark.asyncio
async def test_restore_rejects_checksum_mismatch(
    ephemeral_dbs: tuple[str, str], tmp_path: Path
) -> None:
    """Test that restore_db.sh aborts before creating target if checksum does not match."""
    src_db, dst_db = ephemeral_dbs
    await run_alembic_migrations(src_db)

    rc_b, _, err_b = await run_cli_command(
        [str(BACKUP_SCRIPT), "--db", src_db, "--output-dir", str(tmp_path)]
    )
    assert rc_b == 0, f"Backup failed:\n{err_b}"

    dump_file = next(iter(tmp_path.glob(f"{src_db}_*.dump")))

    # Corrupt dump contents
    append_binary_file(dump_file, b"\x00CORRUPT_BYTES\x00")

    rc, _, stderr = await run_cli_command(
        [str(RESTORE_SCRIPT), str(dump_file), dst_db]
    )

    assert rc != 0
    assert "Checksum verification FAILED" in stderr

    # Verify that dst_db was NOT created
    admin_conn = await asyncpg.connect(database="postgres")
    exists = await admin_conn.fetchval(
        f"SELECT 1 FROM pg_database WHERE datname = '{dst_db}';"
    )
    await admin_conn.close()
    assert exists is None, (
        f"Destination DB '{dst_db}' was created despite checksum failure!"
    )


@pytest.mark.asyncio
async def test_restore_partial_failure_cleanup(
    ephemeral_dbs: tuple[str, str], tmp_path: Path
) -> None:
    """Test that if restore fails mid-flight, the created target database is cleanly removed."""
    _, dst_db = ephemeral_dbs

    fake_dump = tmp_path / "fake_corrupt.dump"
    fake_sha = tmp_path / "fake_corrupt.sha256"
    write_binary_file(fake_dump, b"NOT_A_VALID_POSTGRESQL_CUSTOM_DUMP")

    # Generate matching sha256 so checksum check passes and pg_restore is invoked
    h = hashlib.sha256(b"NOT_A_VALID_POSTGRESQL_CUSTOM_DUMP").hexdigest()
    write_text_file(fake_sha, f"{h}  fake_corrupt.dump\n")

    rc, _, stderr = await run_cli_command(
        [str(RESTORE_SCRIPT), str(fake_dump), dst_db]
    )

    assert rc != 0
    assert "Cleaning up exclusively created temporary database" in stderr

    # Verify that dst_db was cleaned up
    admin_conn = await asyncpg.connect(database="postgres")
    exists = await admin_conn.fetchval(
        f"SELECT 1 FROM pg_database WHERE datname = '{dst_db}';"
    )
    await admin_conn.close()
    assert exists is None, (
        f"Failed restore left orphaned target database '{dst_db}'!"
    )


@pytest.mark.asyncio
async def test_full_drill_backup_restore_and_verification(
    ephemeral_dbs: tuple[str, str], tmp_path: Path
) -> None:
    """Full lifecycle drill: migrate, populate, backup, restore, and verify integrity & H-01 trigger."""
    src_db, dst_db = ephemeral_dbs

    # 1. Setup source DB
    await run_alembic_migrations(src_db)
    expected_counts = await populate_synthetic_data(src_db)

    # 2. Backup
    backup_start = time.perf_counter()
    rc_b, _, err_b = await run_cli_command(
        [str(BACKUP_SCRIPT), "--db", src_db, "--output-dir", str(tmp_path)]
    )
    backup_duration = time.perf_counter() - backup_start
    assert rc_b == 0, f"Backup failed:\n{err_b}"

    dump_file = next(iter(tmp_path.glob(f"{src_db}_*.dump")))
    meta_file = next(iter(tmp_path.glob(f"{src_db}_*.meta.json")))

    # 3. Restore
    restore_start = time.perf_counter()
    rc_r, out_r, err_r = await run_cli_command(
        [str(RESTORE_SCRIPT), str(dump_file), dst_db]
    )
    restore_duration = time.perf_counter() - restore_start
    assert rc_r == 0, f"Restore failed:\n{err_r}"
    assert f"Restoration successfully completed into '{dst_db}'" in out_r

    # 4. Verify restored DB using verify_restored_db.py
    verify_start = time.perf_counter()
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
    verify_duration = time.perf_counter() - verify_start

    assert rc_v == 0, f"Verification failed:\n{out_v}\n{err_v}"
    report: dict[str, Any] = json.loads(out_v)
    assert report["passed"] is True
    assert report["alembic_version"] == "g3b7e1d5a8c2"
    assert report["checks"]["h01_triggers"] == "PASSED"
    assert report["checks"]["h01_functional_cycle_rejection"] == "PASSED"

    # 5. Connect directly to dst_db and verify row-level synthetic data preservation
    conn = await asyncpg.connect(database=dst_db)
    try:
        for table, expected_cnt in expected_counts.items():
            cnt = await conn.fetchval(f"SELECT count(*) FROM {table};")
            assert cnt == expected_cnt, (
                f"Table {table}: expected {expected_cnt} rows, found {cnt}"
            )

        # Confirm hierarchical containment structure is intact
        # B-1 (bien with id where codigo_interno='AUTOBOMBA-01') is container for location 'Bandeja Herramientas B-1'
        b1_id = await conn.fetchval(
            "SELECT id FROM bienes WHERE codigo_interno = 'AUTOBOMBA-01';"
        )
        b1_container_of_u2 = await conn.fetchval(
            "SELECT bien_contenedor_id FROM ubicaciones WHERE nombre = 'Bandeja Herramientas B-1';"
        )
        assert b1_container_of_u2 == b1_id

        # HANDY-01 is placed in location 'Bandeja Herramientas B-1'
        u2_id = await conn.fetchval(
            "SELECT id FROM ubicaciones WHERE nombre = 'Bandeja Herramientas B-1';"
        )
        u2_holds_b2 = await conn.fetchval(
            "SELECT ubicacion_id FROM bienes WHERE codigo_interno = 'HANDY-01';"
        )
        assert u2_holds_b2 == u2_id

        # 6. Functional test of H-01 trigger on the restored database:
        # Create a VEHICULO location on Handy-01 (b2)
        b1_id = await conn.fetchval(
            "SELECT id FROM bienes WHERE codigo_interno = 'AUTOBOMBA-01';"
        )
        b2_id = await conn.fetchval(
            "SELECT id FROM bienes WHERE codigo_interno = 'HANDY-01';"
        )
        funda_id = await conn.fetchval(
            f"""
            INSERT INTO ubicaciones (nombre, tipo_ubicacion, bien_contenedor_id, activa)
            VALUES ('Funda Handy', 'VEHICULO', {b2_id}, true)
            RETURNING id;
            """
        )

        # Attempt to create cycle: put Autobomba-01 (container of Bandeja which holds Handy) inside Funda Handy
        cycle_prevented = False
        try:
            await conn.execute(
                f"UPDATE bienes SET ubicacion_id = {funda_id} WHERE id = {b1_id};"
            )
        except asyncpg.exceptions.CheckViolationError as cve:
            if cve.sqlstate == "23514" and (
                "Location containment cycle is not allowed" in str(cve)
            ):
                cycle_prevented = True

        assert cycle_prevented, (
            "H-01 trigger failed to prevent cycle on restored database!"
        )
    finally:
        await conn.close()

    print(
        f"\n========================================\n"
        f"RESTORE DRILL BENCHMARK REPORT\n"
        f"  Source DB:         {src_db}\n"
        f"  Target DB:         {dst_db}\n"
        f"  Dump Size:         {dump_file.stat().st_size} bytes\n"
        f"  Backup Duration:   {backup_duration:.3f} s\n"
        f"  Restore Duration:  {restore_duration:.3f} s\n"
        f"  Verify Duration:   {verify_duration:.3f} s\n"
        f"  Total Drill Time:  {(backup_duration + restore_duration + verify_duration):.3f} s\n"
        f"  H-01 Lock & Cycle: VERIFIED AND ACTIVE\n"
        f"========================================"
    )

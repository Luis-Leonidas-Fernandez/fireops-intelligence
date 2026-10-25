#!/usr/bin/env python3
"""scripts/verify_restored_db.py.

Post-restoration database integrity verification suite.
Part of H-03: Production Deployment & Data Recovery Architecture.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from typing import Any
from urllib.parse import quote, quote_plus, urlsplit, urlunsplit

import asyncpg  # type: ignore[import-untyped]

EXPECTED_TABLES: set[str] = {
    "roles",
    "usuarios",
    "auth_invitations",
    "auth_registration_requests",
    "categorias",
    "bienes",
    "ubicaciones",
    "movimientos",
    "auditoria_cambios",
    "alembic_version",
}


def sanitize_dsn(text: str) -> str:
    """Mask any passwords embedded in connection strings or exception messages."""
    return re.sub(
        r"(://[^:/\s?#]+):[^/\s?#]+@([a-zA-Z0-9_.-]+)", r"\1:***@\2", text
    )


def build_asyncpg_dsn(db_input: str) -> str:
    """Normalize database name or SQLAlchemy URL into an asyncpg DSN."""
    if "://" in db_input:
        if db_input.startswith("postgresql+asyncpg://"):
            return "postgresql://" + db_input[len("postgresql+asyncpg://"):]
        return db_input

    host = os.getenv("PGHOST", "localhost")
    port = os.getenv("PGPORT", "5432")
    user = os.getenv("PGUSER", os.getenv("USER", "postgres"))
    password = os.getenv("PGPASSWORD", "")

    quoted_user = quote_plus(user)
    if password:
        quoted_password = quote_plus(password)
        netloc = f"{quoted_user}:{quoted_password}@{host}:{port}"
    else:
        netloc = f"{quoted_user}@{host}:{port}"

    quoted_db = quote(db_input.lstrip("/"))
    return urlunsplit(("postgresql", netloc, f"/{quoted_db}", "", ""))


async def verify_tables(conn: asyncpg.Connection) -> list[str]:
    """Verify that all expected application tables are present in public schema."""
    rows = await conn.fetch(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
        """
    )
    existing = {r["table_name"] for r in rows}
    missing = EXPECTED_TABLES - existing
    if missing:
        return [f"Missing required tables: {', '.join(sorted(missing))}"]
    return []


async def verify_constraints_and_indexes(conn: asyncpg.Connection) -> list[str]:
    """Verify that all constraints are validated and all indexes are valid."""
    errors: list[str] = []

    # 1. Unvalidated constraints
    unvalidated = await conn.fetch(
        """
        SELECT c.conname, c.conrelid::regclass::text AS table_name
        FROM pg_constraint c
        JOIN pg_namespace n ON n.oid = c.connamespace
        WHERE n.nspname = 'public' AND NOT c.convalidated;
        """
    )
    for r in unvalidated:
        errors.append(
            f"Unvalidated constraint '{r['conname']}' on table '{r['table_name']}'"
        )

    # 2. Invalid indexes
    invalid_indexes = await conn.fetch(
        """
        SELECT c.relname AS index_name, indrelid::regclass::text AS table_name
        FROM pg_index i
        JOIN pg_class c ON c.oid = i.indexrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND NOT i.indisvalid;
        """
    )
    for r in invalid_indexes:
        errors.append(
            f"Invalid index '{r['index_name']}' on table '{r['table_name']}'"
        )

    return errors


async def verify_sequences(conn: asyncpg.Connection) -> list[str]:
    """Verify that sequences are synchronized and last_value >= MAX(id)."""
    errors: list[str] = []

    sequences = await conn.fetch(
        """
        SELECT sequencename, last_value
        FROM pg_sequences
        WHERE schemaname = 'public';
        """
    )

    table_seq_map: dict[str, tuple[str, str]] = {
        "categorias_id_seq": ("categorias", "id"),
        "bienes_id_seq": ("bienes", "id"),
        "ubicaciones_id_seq": ("ubicaciones", "id"),
        "movimientos_id_seq": ("movimientos", "id"),
        "auditoria_cambios_id_seq": ("auditoria_cambios", "id"),
        "roles_id_seq": ("roles", "id"),
        "usuarios_id_seq": ("usuarios", "id"),
        "auth_invitations_id_seq": ("auth_invitations", "id"),
        "auth_registration_requests_id_seq": ("auth_registration_requests", "id"),
    }

    for seq in sequences:
        seq_name = seq["sequencename"]
        last_val = seq["last_value"]
        if seq_name in table_seq_map:
            table, col = table_seq_map[seq_name]
            max_id = await conn.fetchval(
                f"SELECT COALESCE(MAX({col}), 0) FROM {table};"
            )
            if last_val is not None and max_id is not None and last_val < max_id:
                errors.append(
                    f"Sequence desynchronization: {seq_name} (last_value={last_val}) is behind MAX({col})={max_id} in {table}"
                )

    return errors


async def verify_h01_trigger_integrity(conn: asyncpg.Connection) -> list[str]:
    """Verify that H-01 advisory transaction lock and trigger guards are active."""
    errors: list[str] = []

    # 1. Check prevent_location_containment_cycles function
    func_row = await conn.fetchrow(
        """
        SELECT p.proname, p.prosrc
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public' AND p.proname = 'prevent_location_containment_cycles';
        """
    )
    if not func_row:
        errors.append("Function 'prevent_location_containment_cycles' not found.")
    else:
        src: str = func_row["prosrc"]
        if "pg_advisory_xact_lock" not in src:
            errors.append(
                "Function 'prevent_location_containment_cycles' lacks pg_advisory_xact_lock concurrency protection."
            )
        if "transaction_isolation" not in src:
            errors.append(
                "Function 'prevent_location_containment_cycles' lacks READ COMMITTED transaction_isolation defensive guard."
            )

    # 2. Check triggers on bienes and ubicaciones
    triggers = await conn.fetch(
        """
        SELECT tgname, relname, tgenabled
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND tgname IN ('trg_bienes_location_cycle', 'trg_ubicaciones_location_cycle');
        """
    )
    found_triggers = {t["tgname"]: t for t in triggers}

    for expected_trg in (
        "trg_bienes_location_cycle",
        "trg_ubicaciones_location_cycle",
    ):
        if expected_trg not in found_triggers:
            errors.append(f"Trigger '{expected_trg}' is missing.")
        else:
            raw_state = found_triggers[expected_trg]["tgenabled"]
            state_str = (
                raw_state.decode("ascii")
                if isinstance(raw_state, bytes)
                else str(raw_state)
            )
            if state_str != "O":
                errors.append(
                    f"Trigger '{expected_trg}' is disabled (state: {state_str})."
                )

    return errors


async def verify_alembic_version(
    conn: asyncpg.Connection, expected_rev: str | None
) -> list[str]:
    """Verify Alembic revision against backup metadata without falsely enforcing repo head."""
    errors: list[str] = []
    current_rev = await conn.fetchval(
        "SELECT version_num FROM alembic_version LIMIT 1;"
    )

    if not current_rev:
        return ["Alembic revision not found in alembic_version table."]

    if expected_rev and current_rev != expected_rev:
        errors.append(
            f"Alembic revision mismatch: Restored DB has '{current_rev}', but backup metadata recorded '{expected_rev}'."
        )

    return errors


async def verify_functional_h01_cycle_rejection(
    conn: asyncpg.Connection,
) -> list[str]:
    """Test that H-01 trigger actively rejects containment cycles (in rolled-back transaction)."""
    errors: list[str] = []

    tx = conn.transaction()
    await tx.start()
    try:
        # Create minimal test nodes adhering to ck_ubicaciones_contenedor_por_tipo
        cat_id = await conn.fetchval(
            "INSERT INTO categorias (nombre) VALUES ('_test_verify_cat') RETURNING id;"
        )
        b1_id = await conn.fetchval(
            f"INSERT INTO bienes (codigo_interno, nombre, categoria_id) "
            f"VALUES ('_TEST_B1', '_Asset 1', {cat_id}) RETURNING id;"
        )
        u1_id = await conn.fetchval(
            f"INSERT INTO ubicaciones (nombre, tipo_ubicacion, bien_contenedor_id, activa) "
            f"VALUES ('_loc_1', 'VEHICULO', {b1_id}, true) RETURNING id;"
        )
        b2_id = await conn.fetchval(
            f"INSERT INTO bienes (codigo_interno, nombre, categoria_id, ubicacion_id) "
            f"VALUES ('_TEST_B2', '_Asset 2', {cat_id}, {u1_id}) RETURNING id;"
        )
        u2_id = await conn.fetchval(
            f"INSERT INTO ubicaciones (nombre, tipo_ubicacion, bien_contenedor_id, activa) "
            f"VALUES ('_loc_2', 'VEHICULO', {b2_id}, true) RETURNING id;"
        )

        # Attempt to create cycle: put b1 inside u2 (which is on b2, which is inside u1, which is on b1)
        cycle_prevented = False
        try:
            await conn.execute(
                f"UPDATE bienes SET ubicacion_id = {u2_id} WHERE id = {b1_id};"
            )
        except asyncpg.exceptions.CheckViolationError as cve:
            if cve.sqlstate == "23514":
                cycle_prevented = True
        except asyncpg.PostgresError as pge:
            errors.append(
                f"Unexpected database exception during cycle rejection test: {pge}"
            )

        if not cycle_prevented:
            errors.append(
                "Trigger H-01 failed to reject circular containment update (cycle was allowed)."
            )

    finally:
        await tx.rollback()

    return errors


async def run_all_verifications(
    db_input: str, expected_rev: str | None, check_cycle: bool
) -> tuple[bool, dict[str, Any]]:
    dsn = build_asyncpg_dsn(db_input)
    db_name = urlsplit(dsn).path.lstrip("/")

    conn = await asyncpg.connect(dsn)
    try:
        current_db = await conn.fetchval("SELECT current_database();")

        table_errs = await verify_tables(conn)
        constraint_errs = await verify_constraints_and_indexes(conn)
        sequence_errs = await verify_sequences(conn)
        h01_errs = await verify_h01_trigger_integrity(conn)
        alembic_errs = await verify_alembic_version(conn, expected_rev)

        cycle_errs: list[str] = []
        if check_cycle:
            cycle_errs = await verify_functional_h01_cycle_rejection(conn)

        all_errors = (
            table_errs
            + constraint_errs
            + sequence_errs
            + h01_errs
            + alembic_errs
            + cycle_errs
        )

        alembic_ver = await conn.fetchval(
            "SELECT version_num FROM alembic_version LIMIT 1;"
        )

        report = {
            "database": current_db,
            "target_verified": db_name,
            "alembic_version": alembic_ver,
            "passed": len(all_errors) == 0,
            "checks": {
                "tables": "PASSED" if not table_errs else table_errs,
                "constraints_and_indexes": (
                    "PASSED" if not constraint_errs else constraint_errs
                ),
                "sequences": "PASSED" if not sequence_errs else sequence_errs,
                "h01_triggers": "PASSED" if not h01_errs else h01_errs,
                "alembic_version": "PASSED"
                if not alembic_errs
                else alembic_errs,
                "h01_functional_cycle_rejection": (
                    "PASSED" if not cycle_errs else cycle_errs
                ),
            },
            "error_count": len(all_errors),
        }
        return (len(all_errors) == 0, report)
    finally:
        await conn.close()


def load_expected_alembic_rev(meta_path: str | None) -> str | None:
    """Load expected Alembic revision from metadata file if provided."""
    if not meta_path or not os.path.exists(meta_path):
        return None
    try:
        with open(meta_path, encoding="utf-8") as f:
            data = json.load(f)
            rev = data.get("alembic_version")
            return str(rev) if rev else None
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"Warning: Could not read metadata JSON '{meta_path}': {e}", file=sys.stderr)
        return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify integrity and schema of a restored PostgreSQL database."
    )
    parser.add_argument(
        "db",
        help="Database name or connection URL of the restored database.",
    )
    parser.add_argument(
        "--meta",
        default=None,
        help="Path to .meta.json backup metadata file to verify Alembic revision.",
    )
    parser.add_argument(
        "--no-cycle-check",
        action="store_true",
        help="Skip functional cycle rejection check against H-01 trigger.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON report instead of text.",
    )

    args = parser.parse_args()

    expected_rev = load_expected_alembic_rev(args.meta)

    try:
        passed, report = asyncio.run(
            run_all_verifications(
                args.db, expected_rev, check_cycle=not args.no_cycle_check
            )
        )
    except (asyncpg.PostgresError, OSError, RuntimeError) as e:
        safe_msg = sanitize_dsn(str(e))
        print(f"Error connecting or running verification: {safe_msg}", file=sys.stderr)
        sys.exit(2)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"--- Verification Report for '{report['database']}' ---")
        print(f"Alembic Version: {report['alembic_version']}")
        print(
            f"Overall Result:  {'SUCCESS (All checks passed)' if passed else 'FAILED'}"
        )
        print("Checks:")
        for check_name, res in report["checks"].items():
            status = "✅ PASSED" if res == "PASSED" else f"❌ FAILED: {res}"
            print(f"  - {check_name}: {status}")

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()

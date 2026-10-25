#!/usr/bin/env python3
"""scripts/preflight_migrations.py.

PostgreSQL & Alembic Migration Preflight Inspection Tool.
Part of H-03: Production Deployment & Data Recovery Architecture (Stage C).

Strictly READ-ONLY: Never executes alembic upgrade, downgrade, or stamp.
Inspects database connectivity, public tables, alembic_version state, and
compares against repository migration heads to determine deployment readiness.

Documented Exit Codes:
  0  - SYNCED: Database is fully up to date with repository head.
  10 - PENDING_MIGRATIONS: Database is behind head; migrations are pending.
  11 - EMPTY_DATABASE: Database has no public tables; requires initial migration.
  12 - UNVERSIONED_TABLES: Database has tables but lacks alembic_version tracking.
  20 - DIVERGENT_REVISION: Database revision is unknown or diverged from repository.
  21 - MULTIPLE_REPO_HEADS: Repository migration tree contains multiple unmerged heads.
  22 - MULTIPLE_DB_HEADS: Database alembic_version table contains multiple version rows.
  30 - CONNECTION_ERROR: Could not connect to PostgreSQL database.
  31 - CONFIGURATION_ERROR: Invalid or missing Alembic configuration or parameters.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Self-bootstrap virtualenv if invoked via unactivated system python
if sys.prefix == sys.base_prefix:
    _venv_py = Path(__file__).resolve().parents[1] / ".venv" / "bin" / "python"
    if _venv_py.is_file() and os.access(_venv_py, os.X_OK):
        os.execv(str(_venv_py), [str(_venv_py), *sys.argv])

import argparse
import asyncio
import datetime
import json
import re
from enum import IntEnum
from typing import Any
from urllib.parse import quote, quote_plus, urlsplit, urlunsplit

import asyncpg  # type: ignore[import-untyped]
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError


class PreflightCode(IntEnum):
    """Documented exit codes for migration preflight."""

    SYNCED = 0
    PENDING_MIGRATIONS = 10
    EMPTY_DATABASE = 11
    UNVERSIONED_TABLES = 12
    DIVERGENT_REVISION = 20
    MULTIPLE_REPO_HEADS = 21
    MULTIPLE_DB_HEADS = 22
    CONNECTION_ERROR = 30
    CONFIGURATION_ERROR = 31


def sanitize_dsn(text: str) -> str:
    """Mask any passwords embedded in connection strings or exception messages.

    Supports IPv4, IPv6 literals (e.g. @[::1]), DNS hostnames, and percent-encoded characters.
    """
    # 1. Mask explicit user:password@host (including IPv6 [::1], ports, and unquoted passwords)
    sanitized = re.sub(
        r"(://[^:/?#\s]+):.*@([a-zA-Z0-9_.\-\[\]:]+)", r"\1:***@\2", text
    )
    # 2. Fallback to mask any remaining ://user:password@ structures
    sanitized = re.sub(r"(://[^:/?#\s]+):[^@/?#\s]+@", r"\1:***@", sanitized)
    return sanitized


def extract_safe_db_name(db_input: str) -> str:
    """Extract a non-sensitive database identifier, strictly removing all credentials.

    Never returns passwords or connection strings with secrets.
    """
    if not db_input or not db_input.strip():
        return "<unspecified>"

    stripped = db_input.strip()

    # Plain database identifier without URI scheme or userinfo
    if "://" not in stripped and "@" not in stripped:
        return stripped

    try:
        raw = stripped
        if raw.startswith("postgresql+asyncpg://"):
            raw = "postgresql://" + raw[len("postgresql+asyncpg://"):]
        parsed = urlsplit(raw)
        db_path = parsed.path.lstrip("/")
        if db_path:
            return db_path
        # When URL has no path, identify safely by host without userinfo
        host = parsed.hostname or "<unknown-host>"
        port_str = f":{parsed.port}" if parsed.port else ""
        return f"{host}{port_str}/<unspecified>"
    except ValueError:
        return sanitize_dsn(stripped)


def build_asyncpg_dsn(db_input: str) -> str:
    """Normalize database name or SQLAlchemy URL into an asyncpg DSN with RFC 3986 encoding."""
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


def load_alembic_script_directory(
    config_path: Path,
) -> tuple[ScriptDirectory, list[str]]:
    """Load Alembic ScriptDirectory and inspect repository heads without database connection."""
    if not config_path.is_file():
        raise FileNotFoundError(
            f"Alembic configuration file not found: {config_path}"
        )

    cfg = Config(str(config_path))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    return script, heads


async def inspect_database_schema(
    dsn: str, timeout_seconds: float = 10.0
) -> tuple[set[str], list[str]]:
    """Inspect database public tables and alembic_version rows using read-only SQL queries.

    Never executes DDL, DML, or Alembic commands.
    """
    conn = await asyncpg.connect(dsn, timeout=timeout_seconds)
    try:
        # 1. Fetch all public base tables
        table_rows = await conn.fetch(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
            """
        )
        tables = {r["table_name"] for r in table_rows}

        # 2. Fetch alembic version rows if the table exists
        db_revisions: list[str] = []
        if "alembic_version" in tables:
            rev_rows = await conn.fetch(
                "SELECT version_num FROM alembic_version;"
            )
            db_revisions = [r["version_num"] for r in rev_rows if r["version_num"]]

        return tables, db_revisions
    finally:
        await conn.close()


def evaluate_preflight(
    db_name: str,
    tables: set[str],
    db_revisions: list[str],
    script: ScriptDirectory,
    repo_heads: list[str],
) -> dict[str, Any]:
    """Pure evaluation function comparing database schema state against repository migration tree."""
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    is_empty = len(tables) == 0
    has_version_table = "alembic_version" in tables

    # Base payload structure
    report: dict[str, Any] = {
        "database": db_name,
        "timestamp_utc": timestamp,
        "is_empty": is_empty,
        "table_count": len(tables),
        "has_version_table": has_version_table,
        "db_revisions": db_revisions,
        "current_revision": db_revisions[0] if len(db_revisions) == 1 else None,
        "repo_heads": repo_heads,
        "target_head": repo_heads[0] if len(repo_heads) == 1 else None,
        "pending_revisions": [],
        "status": "",
        "exit_code": PreflightCode.SYNCED,
        "message": "",
    }

    # Check 1: Multiple heads in repository
    if len(repo_heads) > 1:
        report["status"] = "MULTIPLE_REPO_HEADS"
        report["exit_code"] = int(PreflightCode.MULTIPLE_REPO_HEADS)
        report["message"] = (
            f"Repository has {len(repo_heads)} unmerged migration heads: {repo_heads}. "
            "Alembic merge required before deployment."
        )
        return report

    if len(repo_heads) == 0:
        report["status"] = "NO_REPO_HEADS"
        report["exit_code"] = int(PreflightCode.CONFIGURATION_ERROR)
        report["message"] = "Repository has no migration revisions defined."
        return report

    target_head = repo_heads[0]

    # Check 2: Brand-new empty database
    if is_empty:
        # Calculate full migration chain from base to head
        all_revs: list[str] = []
        try:
            base = script.get_base()
            if base is not None:
                revs = list(script.iterate_revisions(target_head, base))
                all_revs = [base] + [r.revision for r in reversed(revs)]
        except CommandError:
            all_revs = [target_head]

        report["status"] = "EMPTY_DATABASE"
        report["exit_code"] = int(PreflightCode.EMPTY_DATABASE)
        report["pending_revisions"] = all_revs
        report["message"] = (
            "Database is empty (0 public tables). Initial migration required."
        )
        return report

    # Check 3: Database has tables but no alembic_version table
    if not has_version_table:
        report["status"] = "UNVERSIONED_TABLES"
        report["exit_code"] = int(PreflightCode.UNVERSIONED_TABLES)
        report["message"] = (
            f"Database contains {len(tables)} tables but lacks 'alembic_version' tracking. "
            "Manual inspection or baseline stamp required."
        )
        return report

    # Check 4: alembic_version table exists but has 0 rows
    if len(db_revisions) == 0:
        report["status"] = "EMPTY_VERSION_TABLE"
        report["exit_code"] = int(PreflightCode.UNVERSIONED_TABLES)
        report["message"] = (
            "Database has 'alembic_version' table but 0 version rows recorded. "
            "Baseline stamp or inspection required."
        )
        return report

    # Check 5: Multiple revisions in alembic_version
    if len(db_revisions) > 1:
        report["status"] = "MULTIPLE_DB_HEADS"
        report["exit_code"] = int(PreflightCode.MULTIPLE_DB_HEADS)
        report["message"] = (
            f"Database alembic_version contains multiple version rows: {db_revisions}. "
            "Database migration tree is branched."
        )
        return report

    current_rev = db_revisions[0]

    # Check 6: Check whether current_rev exists in the repository
    try:
        script.get_revision(current_rev)
    except CommandError:
        report["status"] = "DIVERGENT_REVISION"
        report["exit_code"] = int(PreflightCode.DIVERGENT_REVISION)
        report["message"] = (
            f"Database revision '{current_rev}' does not exist in repository migrations. "
            "Database has diverged or code was rolled back without database downgrade."
        )
        return report

    # Check 7: Current revision exactly matches target head
    if current_rev == target_head:
        report["status"] = "SYNCED"
        report["exit_code"] = int(PreflightCode.SYNCED)
        report["message"] = (
            f"Database is fully synchronized with repository head '{target_head}'."
        )
        return report

    # Check 8: Check if current_rev is an ancestor of target_head (pending migrations)
    try:
        pending_objs = list(script.iterate_revisions(target_head, current_rev))
        pending_revs = [r.revision for r in reversed(pending_objs)]
        report["status"] = "PENDING_MIGRATIONS"
        report["exit_code"] = int(PreflightCode.PENDING_MIGRATIONS)
        report["pending_revisions"] = pending_revs
        report["message"] = (
            f"Database revision '{current_rev}' is behind repository head '{target_head}'. "
            f"{len(pending_revs)} pending migration(s) required."
        )
        return report
    except CommandError:
        # Not a direct ancestor of target_head; path diverged or current_rev is ahead
        report["status"] = "DIVERGENT_REVISION"
        report["exit_code"] = int(PreflightCode.DIVERGENT_REVISION)
        report["message"] = (
            f"Database revision '{current_rev}' cannot cleanly reach repository head '{target_head}'. "
            "Migration paths have diverged."
        )
        return report


async def run_preflight(
    db_input: str,
    config_file: Path,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Execute complete migration preflight asynchronously."""
    # Compute safe database name upfront so no early error path ever leaks credentials
    safe_db_name = extract_safe_db_name(db_input)

    # 1. Load Alembic configuration and ScriptDirectory
    try:
        script, heads = load_alembic_script_directory(config_file)
    except FileNotFoundError as fnf:
        return {
            "database": safe_db_name,
            "status": "CONFIGURATION_ERROR",
            "exit_code": int(PreflightCode.CONFIGURATION_ERROR),
            "message": str(fnf),
        }
    except (CommandError, OSError, ValueError) as e:
        return {
            "database": safe_db_name,
            "status": "CONFIGURATION_ERROR",
            "exit_code": int(PreflightCode.CONFIGURATION_ERROR),
            "message": f"Failed to initialize Alembic script directory: {e}",
        }

    # 2. Build DSN and connect to database
    try:
        dsn = build_asyncpg_dsn(db_input)
    except (ValueError, TypeError) as e:
        return {
            "database": safe_db_name,
            "status": "CONFIGURATION_ERROR",
            "exit_code": int(PreflightCode.CONFIGURATION_ERROR),
            "message": f"Invalid database connection parameters: {e}",
        }

    # 3. Query schema and version state
    try:
        tables, db_revisions = await inspect_database_schema(
            dsn, timeout_seconds=timeout
        )
    except (
        asyncpg.PostgresError,
        asyncpg.InterfaceError,
        OSError,
        asyncio.TimeoutError,
    ) as err:
        safe_msg = sanitize_dsn(str(err))
        return {
            "database": safe_db_name,
            "status": "CONNECTION_ERROR",
            "exit_code": int(PreflightCode.CONNECTION_ERROR),
            "message": f"Could not connect to PostgreSQL: {safe_msg}",
        }
    except ValueError as val_err:
        safe_msg = sanitize_dsn(str(val_err))
        return {
            "database": safe_db_name,
            "status": "CONFIGURATION_ERROR",
            "exit_code": int(PreflightCode.CONFIGURATION_ERROR),
            "message": f"Invalid connection string or DSN parameters: {safe_msg}",
        }

    # 4. Pure evaluation
    return evaluate_preflight(
        safe_db_name, tables, db_revisions, script, heads
    )


def main() -> None:
    """CLI entrypoint for migration preflight inspection."""
    parser = argparse.ArgumentParser(
        description="Alembic Migration Preflight Inspection (Read-Only)."
    )
    parser.add_argument(
        "db",
        nargs="?",
        default=os.getenv("DATABASE_URL", os.getenv("PGDATABASE", "fireassets")),
        help="Database name or connection URL (default: $DATABASE_URL, $PGDATABASE, or 'fireassets').",
    )
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=Path("alembic.ini"),
        help="Path to alembic.ini configuration file (default: alembic.ini).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit output in structured JSON format.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="PostgreSQL connection timeout in seconds (default: 10.0).",
    )

    args = parser.parse_args()

    result = asyncio.run(
        run_preflight(args.db, args.config, timeout=args.timeout)
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        status_symbol = "✅" if result["exit_code"] == 0 else "⚠️" if result["exit_code"] < 20 else "❌"
        print("==================================================")
        print("ALEMBIC MIGRATION PREFLIGHT REPORT")
        print("==================================================")
        print(f"Database:          {result.get('database', args.db)}")
        print(f"Status:            {result.get('status')} {status_symbol}")
        print(f"Exit Code:         {result.get('exit_code')}")
        print(f"Current DB Rev:    {result.get('current_revision', 'None')}")
        print(f"Repository Head:   {result.get('target_head', 'None')}")
        pending = result.get("pending_revisions", [])
        print(f"Pending Count:     {len(pending)}")
        if pending:
            print("Pending Migrations:")
            for p in pending:
                print(f"  - {p}")
        print(f"Details:           {result.get('message')}")
        print("==================================================")

    sys.exit(result["exit_code"])


if __name__ == "__main__":
    main()

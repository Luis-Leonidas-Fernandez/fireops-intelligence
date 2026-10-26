"""Database environment protection and credential sanitization for Outbox runner."""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

PROTECTED_DATABASE_NAMES = frozenset(
    {
        "fireassets",
        "fireassets_test",
        "postgres",
        "template0",
        "template1",
    }
)


class EnvironmentProtectionError(RuntimeError):
    """Raised when an operation attempts to run against a forbidden or protected database."""


def extract_database_name(url: str) -> str:
    """Extract database name from a SQLAlchemy or asyncpg connection URL."""
    if not url:
        return ""
    try:
        # Strip scheme to handle custom dialect schemes like postgresql+asyncpg://
        parsed = urlsplit(url)
        path = parsed.path.lstrip("/")
        return path.split("?")[0].strip().lower()
    except (ValueError, TypeError):
        # Fallback regex
        match = re.search(r"/([^/?]+)(?:\?|$)", url)
        return match.group(1).lower() if match else ""


def redact_database_url(url: str) -> str:
    """Redact user password and query credentials from a database URL for safe logging."""
    if not url:
        return "<empty>"
    try:
        parsed = urlsplit(url)
        netloc = parsed.netloc
        if "@" in netloc:
            creds, host_port = netloc.split("@", 1)
            user = creds.split(":", 1)[0]
            netloc = f"{user}:[REDACTED]@{host_port}"
        # Strip query parameters that might carry tokens
        return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))
    except (ValueError, TypeError):
        return re.sub(r"://([^:]+):([^@]+)@", r"://\1:[REDACTED]@", url)


def validate_target_database(
    url: str,
    *,
    allow_protected: bool = False,
    require_ephemeral: bool = False,
    allow_production: bool = False,
    environment: str = "test",
) -> str:
    """Validate that the database URL does not target a protected database.

    Enforces two distinct policies:
    1. Test policy: strictly blocks protected databases and enforces ephemeral naming.
    2. Operational policy: allows production database ('fireassets') ONLY when
       environment == 'production' AND allow_production=True.

    Returns the extracted database name on success.
    Raises EnvironmentProtectionError on violation.
    """
    db_name = extract_database_name(url)
    if not db_name:
        raise EnvironmentProtectionError("Cannot determine target database name from URL.")

    # 1. Ephemeral database enforcement (for test suites)
    if require_ephemeral and "ephemeral" not in db_name:
        raise EnvironmentProtectionError(
            f"Operation rejected: Database '{db_name}' is not an authorized ephemeral test database."
        )

    # 2. Operational production guard: 'fireassets' allowed only with explicit opt-in in production env
    if db_name == "fireassets":
        if allow_production and environment == "production":
            return db_name
        redacted = redact_database_url(url)
        raise EnvironmentProtectionError(
            f"Operation rejected: Database '{db_name}' ({redacted}) is protected. "
            f"Transactional Outbox runner execution against production requires environment='production' "
            f"and explicit opt-in (--allow-production-db)."
        )

    # 3. Development / test protected databases are always blocked unless allow_protected is set
    if not allow_protected and db_name in PROTECTED_DATABASE_NAMES:
        redacted = redact_database_url(url)
        raise EnvironmentProtectionError(
            f"Operation rejected: Database '{db_name}' ({redacted}) is protected. "
            f"Transactional Outbox runner execution against existing/protected databases is strictly forbidden."
        )

    return db_name

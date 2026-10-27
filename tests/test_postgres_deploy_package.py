"""tests/test_postgres_deploy_package.py.

Automated verification suite for deploy/postgres/ manual installation package.
Validates fail-closed behavior, security policies, least privilege, parameter sizing,
SQL injection defense, atomic write with os.replace, symlink protections,
and guard constraints without connecting to or modifying remote infrastructure.
"""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
from pathlib import Path
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEPLOY_DIR = REPO_ROOT / "deploy" / "postgres"


# ==============================================================================
# 1. Tests for init-db.sh (Least Privilege & SQL Injection Defense)
# ==============================================================================

def test_init_db_script_does_not_precreate_fireassets():
    """Verify that init-db.sh does NOT pre-create the fireassets database,
    preventing rename collisions with staging during bundle restoration.
    """
    init_script = DEPLOY_DIR / "init-db.sh"
    assert init_script.exists(), "init-db.sh must exist in deploy/postgres"

    content = init_script.read_text(encoding="utf-8")
    assert "CREATE DATABASE fireassets" not in content, (
        "init-db.sh must NOT create database fireassets (handled by staging promotion)"
    )
    assert "CREATE DATABASE $FIREOPS_APP_DB" not in content, (
        "init-db.sh must NOT pre-create target application database"
    )


def test_init_db_script_least_privilege_role():
    """Verify that fireops_app role is provisioned with least privilege
    (NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOREPLICATION, NOBYPASSRLS)
    and public connect on db 'postgres' is revoked.
    """
    init_script = DEPLOY_DIR / "init-db.sh"
    content = init_script.read_text(encoding="utf-8")

    assert "NOSUPERUSER" in content
    assert "NOCREATEDB" in content
    assert "NOCREATEROLE" in content
    assert "NOREPLICATION" in content
    assert "NOBYPASSRLS" in content
    assert "REVOKE CONNECT ON DATABASE postgres FROM PUBLIC;" in content
    assert "GRANT CONNECT ON DATABASE postgres TO" in content


def test_init_db_script_sql_injection_defense():
    """Verify that init-db.sh avoids raw bash variable interpolation inside SQL commands.
    It must use psql typed variables (-v), format(%I, %L), \\gexec, and quoted here-doc.
    """
    init_script = DEPLOY_DIR / "init-db.sh"
    content = init_script.read_text(encoding="utf-8")

    # Here-doc delimiter must be quoted ('EOSQL') to prevent shell expansion
    assert "<<-'EOSQL'" in content or "<<'EOSQL'" in content, (
        "init-db.sh must quote here-doc delimiter ('EOSQL') to prevent bash variable expansion"
    )

    # Variables passed via psql -v
    assert "-v app_user=\"$FIREOPS_APP_USER\"" in content or "-v app_user=" in content
    assert "-v app_pass=\"$FIREOPS_APP_PASSWORD\"" in content or "-v app_pass=" in content

    # Uses format(%I, %L) and \gexec
    assert "format(" in content
    assert "%I" in content  # SQL identifier escaping
    assert "%L" in content  # SQL literal escaping
    assert "\\gexec" in content

    # Raw bash interpolation must NOT appear inside SQL
    lines = content.splitlines()
    in_sql = False
    for line in lines:
        stripped = line.strip()
        if stripped in ("<<-'EOSQL'", "<<'EOSQL'"):
            in_sql = True
            continue
        if in_sql and stripped == "EOSQL":
            in_sql = False
            continue
        if in_sql:
            assert "$FIREOPS_APP_USER" not in line, (
                f"Raw variable $FIREOPS_APP_USER found in SQL line: {line}"
            )
            assert "$FIREOPS_APP_PASSWORD" not in line, (
                f"Raw variable $FIREOPS_APP_PASSWORD found in SQL line: {line}"
            )


# ==============================================================================
# 2. Tests for docker-compose.yml (Configuration, Memory Limits & Networking)
# ==============================================================================

def test_docker_compose_configuration_and_memory_budget():
    """Verify that docker-compose.yml defines PostgreSQL 18 with 384M memory limit,
    0.5 CPU, tuned parameters, pgdata subfolder, and loopback binding.
    """
    compose_file = DEPLOY_DIR / "docker-compose.yml"
    assert compose_file.exists(), "docker-compose.yml must exist"

    with open(compose_file, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    services = data.get("services", {})
    assert "postgres" in services, "Service 'postgres' must be defined"
    pg = services["postgres"]

    # Image and container name
    assert pg.get("image") == "postgres:18-alpine"
    assert "fireassets-postgres" in str(pg.get("container_name"))
    assert pg.get("restart") == "unless-stopped"

    # Port binding: strictly loopback
    ports = pg.get("ports", [])
    assert "127.0.0.1:5432" in str(ports), (
        f"PostgreSQL port must be bound to 127.0.0.1:5432, got {ports}"
    )

    # Volume and PGDATA subfolder
    env = pg.get("environment", {})
    assert env.get("PGDATA") == "/var/lib/postgresql/data/pgdata", (
        "PGDATA must point to /var/lib/postgresql/data/pgdata subfolder to avoid lost+found conflict"
    )

    volumes = pg.get("volumes", [])
    volume_targets = [v.split(":")[1] for v in volumes]
    assert "/var/lib/postgresql/data" in volume_targets

    # Resource limits: 384 MB limit, 192 MB reservation
    deploy_cfg = pg.get("deploy", {})
    resources = deploy_cfg.get("resources", {})
    limits = resources.get("limits", {})
    reservations = resources.get("reservations", {})

    assert limits.get("memory") == "384M", f"Memory limit must be 384M, got {limits.get('memory')}"
    assert limits.get("cpus") == "0.50", f"CPU limit must be 0.50, got {limits.get('cpus')}"
    assert reservations.get("memory") == "192M", (
        f"Memory reservation must be 192M, got {reservations.get('memory')}"
    )

    # Parameter tuning in command
    cmd = pg.get("command", "")
    assert "-c shared_buffers=64MB" in cmd
    assert "-c max_connections=25" in cmd
    assert "-c work_mem=4MB" in cmd
    assert "-c maintenance_work_mem=32MB" in cmd
    assert "-c effective_cache_size=256MB" in cmd

    # Healthcheck
    health = pg.get("healthcheck", {})
    assert "pg_isready" in str(health.get("test", ""))


# ==============================================================================
# 3. Tests for generate_credentials.sh (Atomic Generation, Symlinks, & Guardrails)
# ==============================================================================

def test_generate_credentials_lifecycle():
    """Verify that generate_credentials.sh generates .env with 0600 permissions,
    refuses to overwrite on subsequent calls, and leaks zero secrets.
    """
    gen_script = DEPLOY_DIR / "generate_credentials.sh"
    assert gen_script.exists()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        script_copy = tmp_path / "generate_credentials.sh"
        script_copy.write_text(gen_script.read_text(encoding="utf-8"), encoding="utf-8")
        script_copy.chmod(0o755)

        target_env = tmp_path / ".env"
        assert not target_env.exists()

        # Step 1: Initial creation without arguments
        proc = subprocess.run(
            ["bash", str(script_copy)],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, f"Script failed: {proc.stderr}"
        assert target_env.exists(), ".env was not created"

        # Verify permissions: must be strictly 0600
        env_stat = os.stat(target_env)
        file_mode = stat.S_IMODE(env_stat.st_mode)
        assert file_mode == 0o600, f"Expected permissions 0600, got {oct(file_mode)}"

        content_1 = target_env.read_text(encoding="utf-8")
        assert "POSTGRES_SUPERUSER=postgres_admin" in content_1
        assert "FIREOPS_APP_USER=fireops_app" in content_1
        assert "FIREOPS_APP_DB=fireassets" in content_1
        assert "POSTGRES_SUPERUSER_PASSWORD=" in content_1
        assert "FIREOPS_APP_PASSWORD=" in content_1

        # Passwords must not be printed in stdout or stderr
        for line in content_1.splitlines():
            if "PASSWORD=" in line:
                val = line.split("=", 1)[1].strip()
                assert len(val) >= 40, "Generated password entropy must be at least 32 urlsafe bytes"
                assert val not in proc.stdout, "Password must not be leaked in stdout"
                assert val not in proc.stderr, "Password must not be leaked in stderr"

        # Step 2: Running again must fail-closed (exit 1) and forbid regeneration
        proc_reentry = subprocess.run(
            ["bash", str(script_copy)],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc_reentry.returncode == 1, "Must exit with code 1 if .env exists"
        assert "ya existe" in proc_reentry.stderr or "estrictamente prohibida" in proc_reentry.stderr


def test_generate_credentials_force_option_forbidden():
    """Verify that --force and -f flags are strictly rejected with exit code 1."""
    gen_script = DEPLOY_DIR / "generate_credentials.sh"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        script_copy = tmp_path / "generate_credentials.sh"
        script_copy.write_text(gen_script.read_text(encoding="utf-8"), encoding="utf-8")
        script_copy.chmod(0o755)

        for flag in ["--force", "-f", "--force=true", "-force"]:
            proc = subprocess.run(
                ["bash", str(script_copy), flag],
                cwd=tmpdir,
                capture_output=True,
                text=True,
                check=False,
            )
            assert proc.returncode == 1, f"Flag {flag} must be rejected"
            assert "RECHAZO DE SEGURIDAD" in proc.stderr
            assert "eliminada" in proc.stderr or "no permitido" in proc.stderr


def test_generate_credentials_symlink_rejection():
    """Verify that generate_credentials.sh detects and refuses to operate when
    .env is a symlink, preventing symlink traversal attacks.
    """
    gen_script = DEPLOY_DIR / "generate_credentials.sh"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        script_copy = tmp_path / "generate_credentials.sh"
        script_copy.write_text(gen_script.read_text(encoding="utf-8"), encoding="utf-8")
        script_copy.chmod(0o755)

        # Create a decoy file and a symlink named .env pointing to it
        decoy_file = tmp_path / "decoy_target.txt"
        decoy_file.write_text("ORIGINAL_DECOY_CONTENT", encoding="utf-8")

        target_symlink = tmp_path / ".env"
        target_symlink.symlink_to(decoy_file)
        assert target_symlink.is_symlink()

        proc = subprocess.run(
            ["bash", str(script_copy)],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 1, "Must exit with code 1 when .env is a symlink"
        assert "enlace simbólico" in proc.stderr or "symlink" in proc.stderr.lower()

        # Decoy file must remain 100% untouched
        assert decoy_file.read_text(encoding="utf-8") == "ORIGINAL_DECOY_CONTENT"


def test_generate_credentials_atomic_write_and_cleanup_on_interruption():
    """Verify that generate_credentials.sh uses os.replace() with a temporary file,
    and if write is interrupted or fails, no orphaned temp files or broken .env remain.
    """
    gen_script = DEPLOY_DIR / "generate_credentials.sh"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        script_copy = tmp_path / "generate_credentials.sh"
        content = gen_script.read_text(encoding="utf-8")

        # Verify script uses tempfile, os.replace, and finally cleanup
        assert "os.replace(tmp_path, target_path)" in content
        assert "tempfile.mkstemp" in content
        assert "os.unlink(tmp_path)" in content

        # Inject an intentional failure before os.replace to test cleanup
        broken_content = content.replace(
            "    os.replace(tmp_path, target_path)",
            "    raise RuntimeError('SIMULATED_INTERRUPTION_CRASH')\n    os.replace(tmp_path, target_path)",
        )
        script_copy.write_text(broken_content, encoding="utf-8")
        script_copy.chmod(0o755)

        proc = subprocess.run(
            ["bash", str(script_copy)],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 1, "Script must fail on simulated crash"
        assert "SIMULATED_INTERRUPTION_CRASH" in proc.stderr

        # Target .env must NOT exist
        assert not (tmp_path / ".env").exists()

        # Any temp file (.env.tmp.*) must have been cleaned up by finally block
        temp_files = list(tmp_path.glob(".env.tmp.*"))
        assert len(temp_files) == 0, f"Orphaned temp files found: {temp_files}"


# ==============================================================================
# 4. Tests for verify_persistence.sh (Safety Guard & Drill Restrictions)
# ==============================================================================

def test_verify_persistence_fails_without_allow_drill():
    """Verify that verify_persistence.sh strictly fails closed (exit 1)
    if --allow-drill is omitted.
    """
    script = DEPLOY_DIR / "verify_persistence.sh"
    assert script.exists()

    proc = subprocess.run(
        ["bash", str(script)],
        cwd=str(DEPLOY_DIR),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "BLOQUEO DE SEGURIDAD" in proc.stderr
    assert "--allow-drill" in proc.stderr


def test_verify_persistence_help_option():
    """Verify that verify_persistence.sh --help exits with code 0 and provides usage."""
    script = DEPLOY_DIR / "verify_persistence.sh"

    proc = subprocess.run(
        ["bash", str(script), "--help"],
        cwd=str(DEPLOY_DIR),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "--allow-drill" in proc.stdout


def test_verify_persistence_contains_no_destructive_volume_commands():
    """Verify that verify_persistence.sh never invokes 'docker compose down -v'
    or '--volumes' which would destroy production data.
    """
    script = DEPLOY_DIR / "verify_persistence.sh"
    content = script.read_text(encoding="utf-8")

    assert "down -v" not in content
    assert "down --volumes" not in content
    assert "-p \"$COMPOSE_PROJECT\"" in content or "-p $COMPOSE_PROJECT" in content


# ==============================================================================
# 5. Tests for restore_production_bundle.sh (Input Validation & Fail-Closed Safety)
# ==============================================================================

def test_restore_production_bundle_missing_arguments():
    """Verify that restore_production_bundle.sh fails closed when arguments are missing."""
    script = DEPLOY_DIR / "restore_production_bundle.sh"
    assert script.exists()

    proc = subprocess.run(
        ["bash", str(script)],
        cwd=str(DEPLOY_DIR),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "Uso:" in proc.stdout or "Uso:" in proc.stderr


def test_restore_production_bundle_nonexistent_files():
    """Verify that restore_production_bundle.sh fails closed when files do not exist."""
    script = DEPLOY_DIR / "restore_production_bundle.sh"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        fake_env = tmp_path / ".env"
        fake_env.write_text("POSTGRES_SUPERUSER=admin\nFIREOPS_APP_USER=app\nFIREOPS_APP_DB=fireassets\n", encoding="utf-8")
        fake_env.chmod(0o600)

        script_copy = tmp_path / "restore_production_bundle.sh"
        script_copy.write_text(script.read_text(encoding="utf-8"), encoding="utf-8")
        script_copy.chmod(0o755)

        env = os.environ.copy()
        env["ALLOW_NON_ROOT_ENV"] = "1"

        proc = subprocess.run(
            ["bash", str(script_copy), "/nonexistent/dump.dump", "/nonexistent/manifest.json"],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        assert proc.returncode == 1
        assert "no encontrado" in proc.stderr


def test_restore_production_bundle_staging_safety_and_stop_protocol():
    """Verify that restore_production_bundle.sh rejects pre-existing staging,
    contains zero DROP DATABASE commands in its workflow, preserves staging on failure
    for forensics, and strictly halts at the mandatory STOP point.
    """
    script = DEPLOY_DIR / "restore_production_bundle.sh"
    content = script.read_text(encoding="utf-8")

    # 1. Pre-existence guard on staging: Fail-closed without dropping or terminating connections
    assert "RECHAZO DE SEGURIDAD: La base de datos de staging" in content
    assert "SELECT 1 FROM pg_database WHERE datname = '$STAGING_DB'" in content
    assert "Restauración abortada sin modificaciones, sin terminar conexiones" in content
    assert "psql -v ON_ERROR_STOP=1" in content
    assert "STAGING_QUERY_ERR" in content
    assert "2>&1)" in content or "STAGING_QUERY_ERR=$?" in content

    # Strict database names validation
    assert "EXPECTED_STAGING_DB=\"fireassets_staging_vps\"" in content
    assert "EXPECTED_TARGET_DB=\"fireassets\"" in content
    assert "POSTGRES_STAGING_DB tiene un valor no permitido" in content
    assert "FIREOPS_APP_DB tiene un valor no permitido" in content

    # 2. Strict absence of DROP DATABASE in the entire restoration script
    # Any DROP DATABASE command is strictly forbidden in restore_production_bundle.sh
    sql_drop_lines = [
        line.strip() for line in content.splitlines()
        if "DROP DATABASE" in line and not line.strip().startswith("#")
        and "sin ejecutar DROP DATABASE" not in line
        and "No se ha ejecutado ningún DROP DATABASE" not in line
    ]
    assert len(sql_drop_lines) == 0, f"Forbidden DROP DATABASE command found: {sql_drop_lines}"

    # 3. Non-destructive diagnostic trap preserving staging on failure
    assert "notify_on_failure" in content
    assert "se ha preservado intacta para análisis forense" in content
    assert "trap notify_on_failure EXIT" in content

    # 4. Strict .env security validation
    assert "validate_env_security" in content
    assert "stat.S_ISLNK" in content
    assert "stat.S_ISREG" in content
    assert "0o077" in content

    # 5. Credential safety: passed via environment, not CLI arguments
    assert "PGPASSWORD=\"${FIREOPS_APP_PASSWORD}\"" in content or "PGPASSWORD=" in content
    assert "\"$PYTHON_EXEC\" \"$VERIFY_SCRIPT\" \"$STAGING_DB\"" in content

    # 6. Disarms trap upon successful verification
    assert "trap - EXIT" in content

    # 7. Mandatory STOP point: does NOT promote automatically, refers to promote_to_production.sh
    assert "STOP OBLIGATORIO" in content
    assert "promote_to_production.sh" in content
    assert "ALTER DATABASE $STAGING_DB RENAME TO" not in content, (
        "restore_production_bundle.sh must NOT execute promotion; promotion is decoupled"
    )


def test_restore_production_bundle_env_security_validations():
    """Verify that restore_production_bundle.sh strictly rejects insecure .env files:
    symlinks, directories, permissive permissions (0644/0666), and non-root ownership.
    """
    script = DEPLOY_DIR / "restore_production_bundle.sh"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        script_copy = tmp_path / "restore_production_bundle.sh"
        script_copy.write_text(script.read_text(encoding="utf-8"), encoding="utf-8")
        script_copy.chmod(0o755)

        # 1. Symlink rejection
        decoy = tmp_path / "decoy.env"
        decoy.write_text("POSTGRES_SUPERUSER=admin\n", encoding="utf-8")
        decoy.chmod(0o600)
        symlink_env = tmp_path / ".env"
        symlink_env.symlink_to(decoy)

        proc_symlink = subprocess.run(
            ["bash", str(script_copy), "dummy.dump", "dummy.json"],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc_symlink.returncode == 1
        assert "enlace simbólico" in proc_symlink.stderr or "RECHAZO DE SEGURIDAD" in proc_symlink.stderr
        symlink_env.unlink()

        # 2. Directory instead of regular file
        dir_env = tmp_path / ".env"
        dir_env.mkdir()
        proc_dir = subprocess.run(
            ["bash", str(script_copy), "dummy.dump", "dummy.json"],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc_dir.returncode == 1
        assert "archivo regular" in proc_dir.stderr or "RECHAZO DE SEGURIDAD" in proc_dir.stderr
        dir_env.rmdir()

        # 3. Insecure permissions (0644 - group/others readable)
        perm_env = tmp_path / ".env"
        perm_env.write_text("POSTGRES_SUPERUSER=admin\n", encoding="utf-8")
        perm_env.chmod(0o644)
        proc_perm = subprocess.run(
            ["bash", str(script_copy), "dummy.dump", "dummy.json"],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc_perm.returncode == 1
        assert "Permisos inseguros" in proc_perm.stderr or "RECHAZO DE SEGURIDAD" in proc_perm.stderr

        # 4. Strict root ownership rejection (running without ALLOW_NON_ROOT_ENV on non-root UID)
        perm_env.chmod(0o600)
        if os.geteuid() != 0:
            env_no_root = os.environ.copy()
            env_no_root.pop("ALLOW_NON_ROOT_ENV", None)
            proc_owner = subprocess.run(
                ["bash", str(script_copy), "dummy.dump", "dummy.json"],
                cwd=tmpdir,
                capture_output=True,
                text=True,
                check=False,
                env=env_no_root,
            )
            assert proc_owner.returncode == 1
            assert "root (UID 0)" in proc_owner.stderr or "RECHAZO DE SEGURIDAD" in proc_owner.stderr


def test_restore_production_bundle_rejects_unexpected_db_names():
    """Verify that restore_production_bundle.sh strictly rejects non-canonical
    database names in POSTGRES_STAGING_DB and FIREOPS_APP_DB.
    """
    script = DEPLOY_DIR / "restore_production_bundle.sh"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        script_copy = tmp_path / "restore_production_bundle.sh"
        script_copy.write_text(script.read_text(encoding="utf-8"), encoding="utf-8")
        script_copy.chmod(0o755)

        env_run = os.environ.copy()
        env_run["ALLOW_NON_ROOT_ENV"] = "1"

        # 1. Invalid staging DB name
        env_file = tmp_path / ".env"
        env_file.write_text(
            "POSTGRES_SUPERUSER=admin\nFIREOPS_APP_USER=app\n"
            "POSTGRES_STAGING_DB=malicious_staging_name\n"
            "FIREOPS_APP_DB=fireassets\n",
            encoding="utf-8",
        )
        env_file.chmod(0o600)

        proc = subprocess.run(
            ["bash", str(script_copy), "dummy.dump", "dummy.json"],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            check=False,
            env=env_run,
        )
        assert proc.returncode == 1
        assert "RECHAZO DE SEGURIDAD" in proc.stderr
        assert "POSTGRES_STAGING_DB tiene un valor no permitido" in proc.stderr

        # 2. Invalid target DB name
        env_file.write_text(
            "POSTGRES_SUPERUSER=admin\nFIREOPS_APP_USER=app\n"
            "POSTGRES_STAGING_DB=fireassets_staging_vps\n"
            "FIREOPS_APP_DB=other_production_db\n",
            encoding="utf-8",
        )
        proc2 = subprocess.run(
            ["bash", str(script_copy), "dummy.dump", "dummy.json"],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            check=False,
            env=env_run,
        )
        assert proc2.returncode == 1
        assert "RECHAZO DE SEGURIDAD" in proc2.stderr
        assert "FIREOPS_APP_DB tiene un valor no permitido" in proc2.stderr


def test_promote_to_production_standalone_logic():
    """Verify that promote_to_production.sh executes standalone ALTER DATABASE outside
    any DO/transaction block, enforces fail-closed guard against existing target,
    implements connection gating, sets ownership, and NEVER drops production data.
    """
    script = DEPLOY_DIR / "promote_to_production.sh"
    assert script.exists(), "promote_to_production.sh must exist"
    assert os.access(script, os.X_OK), "promote_to_production.sh must be executable"

    content = script.read_text(encoding="utf-8")

    # Fail-closed guard against pre-existing production database
    assert "RECHAZO DE SEGURIDAD" in content
    assert "SELECT 1 FROM pg_database WHERE datname = '$TARGET_DB'" in content

    # Connection gating before rename
    assert "WITH ALLOW_CONNECTIONS = false;" in content
    assert "pg_terminate_backend(pid)" in content

    # Standalone ALTER DATABASE execution (NOT inside DO $$ or BEGIN)
    assert "RENAME TO \\\"$TARGET_DB\\\";" in content or "RENAME TO \"$TARGET_DB\";" in content or "RENAME TO $TARGET_DB" in content
    assert "DO $$" not in content, "ALTER DATABASE RENAME must NOT be in a DO $$ block"
    assert "DO \\$\\$" not in content, "ALTER DATABASE RENAME must NOT be in a DO $$ block"

    # Post-rename connection enabling and ownership
    assert "WITH ALLOW_CONNECTIONS = true;" in content
    assert "OWNER TO" in content

    # Invariant: NEVER drop production database post-promotion
    assert "DROP DATABASE $TARGET_DB" not in content
    assert "DROP DATABASE IF EXISTS $TARGET_DB" not in content
    assert "DROP DATABASE \"$TARGET_DB\"" not in content
    assert "INVARIANTE DE SEGURIDAD" in content


def test_promote_to_production_cli_options():
    """Verify CLI options for promote_to_production.sh (--help and missing .env)."""
    script = DEPLOY_DIR / "promote_to_production.sh"

    # --help exits with 0
    proc_help = subprocess.run(
        ["bash", str(script), "--help"],
        cwd=str(DEPLOY_DIR),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_help.returncode == 0
    assert "Uso:" in proc_help.stdout

    # Missing .env fails closed with exit code 1
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        script_copy = tmp_path / "promote_to_production.sh"
        script_copy.write_text(script.read_text(encoding="utf-8"), encoding="utf-8")
        script_copy.chmod(0o755)

        proc_no_env = subprocess.run(
            ["bash", str(script_copy)],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc_no_env.returncode == 1
        assert "no encontrado" in proc_no_env.stderr


# ==============================================================================
# 6. Tests for preflight_check.sh (Static Rules and Sizing Bounds)
# ==============================================================================

def test_preflight_check_thresholds():
    """Verify that preflight_check.sh enforces >= 400 MB RAM and >= 5 GB disk thresholds."""
    script = DEPLOY_DIR / "preflight_check.sh"
    assert script.exists()

    content = script.read_text(encoding="utf-8")
    assert "400" in content, "RAM check must require at least 400 MB"
    assert "5" in content, "Disk check must require at least 5 GB"
    assert ":5432 " in content, "Port check must search for port 5432"

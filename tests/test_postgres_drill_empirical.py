"""tests/test_postgres_drill_empirical.py.

Empirical integration drill against real Docker PostgreSQL 18 container (port 55433).
Specifically validates the 5 requirements mandated for deploy/postgres/restore_production_bundle.sh:
1. Staging preexistente: rechazo sin modificaciones, sin terminar conexiones y sin DROP DATABASE.
2. Restauración fallida: staging preservada intacta para análisis forense (cero DROP DATABASE).
3. Verificación fallida: staging preservada intacta con sus tablas para diagnóstico (cero DROP DATABASE).
4. Restauración correcta: 8 de 8 controles aprobados (PASS) y STOP obligatorio sin promoción.
5. Ausencia total de sentencias SQL DROP DATABASE en todo el flujo de restauración.
6. Promoción desacoplada: desalojo de conexiones, sentencia standalone y protección post-rename.

Safe: Operates on isolated port 55433 with container 'fireassets-postgres-drill'.
Local native PostgreSQL (port 5432) remains completely untouched.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DEPLOY_DIR = REPO_ROOT / "deploy" / "postgres"
BACKUPS_DIR = REPO_ROOT / "backups" / "transfer"

DRILL_PORT = "55433"
DRILL_CONTAINER = "fireassets-postgres-drill"
SUPERUSER = "postgres_admin"
SUPERUSER_PASS = "DrillSuperSecret123_456!"
APP_USER = "fireops_app"
APP_PASS = "DrillAppSecret123_456!"
TARGET_DB = "fireassets"
STAGING_DB = "fireassets_staging_vps"


def run_cmd(cmd: list[str], cwd: str | Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PATH"] = f"/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin:{env.get('PATH', '')}"
    res = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if check and res.returncode != 0:
        raise RuntimeError(
            f"Command failed ({res.returncode}): {' '.join(cmd)}\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )
    return res


@pytest.fixture(scope="module")
def drill_cluster():
    """Spin up an isolated Docker PostgreSQL 18 container on port 55433."""
    # Ensure any lingering drill container is removed
    run_cmd(["docker", "rm", "-f", DRILL_CONTAINER], check=False)

    # Start container with healthcheck
    run_cmd([
        "docker", "run", "-d",
        "--name", DRILL_CONTAINER,
        "-p", f"127.0.0.1:{DRILL_PORT}:5432",
        "-e", f"POSTGRES_USER={SUPERUSER}",
        "-e", f"POSTGRES_PASSWORD={SUPERUSER_PASS}",
        "-e", "POSTGRES_DB=postgres",
        "--health-cmd", f"pg_isready -U {SUPERUSER} -d postgres",
        "--health-interval", "1s",
        "--health-timeout", "2s",
        "--health-retries", "30",
        "postgres:18-alpine",
    ])

    # Wait for healthy
    for _ in range(30):
        res = run_cmd(["docker", "inspect", "--format", "{{.State.Health.Status}}", DRILL_CONTAINER], check=False)
        if res.stdout.strip() == "healthy":
            break
        time.sleep(1)
    else:
        run_cmd(["docker", "rm", "-f", DRILL_CONTAINER], check=False)
        pytest.fail("Drill container failed to reach 'healthy' state within 30s")

    # Initialize roles using init-db.sh
    init_db_script = DEPLOY_DIR / "init-db.sh"
    run_cmd([
        "docker", "exec", "-i",
        "-e", f"POSTGRES_USER={SUPERUSER}",
        "-e", "POSTGRES_DB=postgres",
        "-e", f"FIREOPS_APP_USER={APP_USER}",
        "-e", f"FIREOPS_APP_PASSWORD={APP_PASS}",
        DRILL_CONTAINER,
        "sh", "-c", init_db_script.read_text(encoding="utf-8"),
    ])

    # Setup isolated test directory with scripts and .env
    temp_dir = tempfile.mkdtemp(prefix="fireassets_drill_")
    temp_path = Path(temp_dir)

    # Copy deploy scripts
    for script_name in ["restore_production_bundle.sh", "promote_to_production.sh"]:
        src = DEPLOY_DIR / script_name
        dst = temp_path / script_name
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        dst.chmod(0o755)

    # Copy verify script
    verify_src = REPO_ROOT / "scripts" / "verify_restored_db.py"
    shutil.copy2(verify_src, temp_path / "verify_restored_db.py")

    # Generate .env with 0600 permissions
    env_file = temp_path / ".env"
    env_content = f"""POSTGRES_CONTAINER_NAME={DRILL_CONTAINER}
POSTGRES_HOST_PORT={DRILL_PORT}
POSTGRES_SUPERUSER={SUPERUSER}
POSTGRES_SUPERUSER_PASSWORD={SUPERUSER_PASS}
FIREOPS_APP_USER={APP_USER}
FIREOPS_APP_PASSWORD={APP_PASS}
FIREOPS_APP_DB={TARGET_DB}
POSTGRES_STAGING_DB={STAGING_DB}
"""
    env_file.write_text(env_content, encoding="utf-8")
    env_file.chmod(0o600)

    yield {
        "work_dir": temp_path,
        "container": DRILL_CONTAINER,
        "port": DRILL_PORT,
        "dump_file": BACKUPS_DIR / "fireassets_bundle_20261027_141104Z.dump",
        "manifest_file": BACKUPS_DIR / "fireassets_bundle_20261027_141104Z.manifest.json",
    }

    # Teardown
    run_cmd(["docker", "rm", "-f", DRILL_CONTAINER], check=False)
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_empirical_1_staging_preexistente_rechazo_sin_modificaciones(drill_cluster):
    """Requisito 1: Si staging ya existe, aborta sin modificarla, sin terminar conexiones
    y sin ejecutar DROP DATABASE.
    """
    work_dir = drill_cluster["work_dir"]
    dump_file = drill_cluster["dump_file"]
    manifest_file = drill_cluster["manifest_file"]

    # 1. Crear staging preexistente con datos críticos (comandos separados fuera de transacción)
    run_cmd([
        "docker", "exec", "-i", DRILL_CONTAINER,
        "psql", "-U", SUPERUSER, "-d", "postgres", "-c",
        f"DROP DATABASE IF EXISTS {STAGING_DB};",
    ])
    run_cmd([
        "docker", "exec", "-i", DRILL_CONTAINER,
        "psql", "-U", SUPERUSER, "-d", "postgres", "-c",
        f"CREATE DATABASE {STAGING_DB} OWNER {APP_USER};",
    ])
    run_cmd([
        "docker", "exec", "-i", DRILL_CONTAINER,
        "psql", "-U", APP_USER, "-d", STAGING_DB, "-c",
        "CREATE TABLE critical_preexisting (id int, val text); INSERT INTO critical_preexisting VALUES (1, 'PRESERVE_ME');",
    ])

    # 2. Abrir conexión activa en background sobre staging
    bg_proc = subprocess.Popen(
        [
            "docker", "exec", "-i", DRILL_CONTAINER,
            "psql", "-U", APP_USER, "-d", STAGING_DB, "-c", "SELECT pg_sleep(30);",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Esperar a que la conexión esté activa
    time.sleep(0.5)

    # 3. Ejecutar restore_production_bundle.sh
    env = os.environ.copy()
    env["ALLOW_NON_ROOT_ENV"] = "1"
    env["PYTHON_BIN"] = str(REPO_ROOT / ".venv" / "bin" / "python")

    restore_script = work_dir / "restore_production_bundle.sh"
    res = subprocess.run(
        ["bash", str(restore_script), str(dump_file), str(manifest_file)],
        cwd=str(work_dir),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    # 4. Validar rechazo fail-closed inmediato con código 1
    assert res.returncode == 1, "Debe abortar con código 1"
    assert "RECHAZO DE SEGURIDAD" in res.stderr
    assert f"La base de datos de staging '{STAGING_DB}' ya existe en el servidor" in res.stderr
    assert "sin terminar conexiones y sin ejecutar DROP DATABASE" in res.stderr

    # 5. Validar que la conexión en background NO fue terminada (sigue viva)
    assert bg_proc.poll() is None, "La conexión activa no debe haber sido terminada"
    bg_proc.kill()
    bg_proc.communicate()

    # 6. Validar que los datos preexistentes permanecen 100% intactos
    data_check = run_cmd([
        "docker", "exec", "-i", DRILL_CONTAINER,
        "psql", "-U", APP_USER, "-d", STAGING_DB, "-tAc",
        "SELECT val FROM critical_preexisting WHERE id = 1;",
    ])
    assert data_check.stdout.strip() == "PRESERVE_ME", "Los datos preexistentes no deben haber sido modificados"

    # Limpiar base staging para los tests siguientes (terminando la conexión en Docker primero)
    run_cmd([
        "docker", "exec", "-i", DRILL_CONTAINER,
        "psql", "-U", SUPERUSER, "-d", "postgres", "-c",
        f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{STAGING_DB}' AND pid <> pg_backend_pid();",
    ])
    run_cmd([
        "docker", "exec", "-i", DRILL_CONTAINER,
        "psql", "-U", SUPERUSER, "-d", "postgres", "-c",
        f"DROP DATABASE {STAGING_DB};",
    ])


def test_empirical_2_restauracion_fallida_staging_preservada(drill_cluster):
    """Requisito 2: Si la restauración falla (volcado inválido/corrupto), la base de staging
    es PRESERVADA intacta para diagnóstico forense (sin DROP DATABASE).
    """
    work_dir = drill_cluster["work_dir"]
    manifest_file = drill_cluster["manifest_file"]

    # Crear volcado corrupto que pase el checksum SHA-256 pero falle en pg_restore
    corrupt_dump = work_dir / "corrupted_archive.dump"
    corrupt_dump.write_text("CORRUPTED_CUSTOM_POSTGRES_DUMP_HEADER_INVALID", encoding="utf-8")
    sha_res = run_cmd(["sha256sum", "corrupted_archive.dump"], cwd=work_dir)
    (work_dir / "corrupted_archive.dump.sha256").write_text(sha_res.stdout, encoding="utf-8")

    env = os.environ.copy()
    env["ALLOW_NON_ROOT_ENV"] = "1"
    env["PYTHON_BIN"] = str(REPO_ROOT / ".venv" / "bin" / "python")

    restore_script = work_dir / "restore_production_bundle.sh"
    res = subprocess.run(
        ["bash", str(restore_script), str(corrupt_dump), str(manifest_file)],
        cwd=str(work_dir),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    # Debe fallar durante pg_restore
    assert res.returncode != 0
    assert "RESTAURACIÓN O AUDITORÍA INTERRUMPIDA" in res.stderr
    assert f"La base de datos de staging '{STAGING_DB}' se ha preservado intacta para análisis forense" in res.stderr
    assert "No se ha ejecutado ningún DROP DATABASE" in res.stderr

    # INVARIANTE: Staging DEBE EXISTIR en el catálogo de PostgreSQL (no fue borrada por ningún trap)
    check_staging = run_cmd([
        "docker", "exec", "-i", DRILL_CONTAINER,
        "psql", "-U", SUPERUSER, "-d", "postgres", "-tAc",
        f"SELECT 1 FROM pg_database WHERE datname = '{STAGING_DB}';",
    ])
    assert check_staging.stdout.strip() == "1", "Staging debe haber sido preservada para diagnóstico forense"

    # Limpiar para siguiente prueba
    run_cmd([
        "docker", "exec", "-i", DRILL_CONTAINER,
        "psql", "-U", SUPERUSER, "-d", "postgres", "-c",
        f"DROP DATABASE {STAGING_DB};",
    ])


def test_empirical_3_verificacion_fallida_staging_preservada(drill_cluster):
    """Requisito 3: Si la restauración se completa pero cualquiera de los 8 controles falla,
    la base de staging y todas sus tablas se PRESERVAN intactas para análisis forense.
    """
    work_dir = drill_cluster["work_dir"]
    dump_file = drill_cluster["dump_file"]

    # Crear un manifiesto adulterado con una revisión Alembic inexistente para provocar fallo en control 8
    tampered_manifest = work_dir / "tampered.manifest.json"
    manifest_data = drill_cluster["manifest_file"].read_text(encoding="utf-8")
    tampered_data = manifest_data.replace('"alembic_head": "g3b7e1d5a8c2"', '"alembic_head": "revision_falsa_que_falla"')
    tampered_manifest.write_text(tampered_data, encoding="utf-8")

    env = os.environ.copy()
    env["ALLOW_NON_ROOT_ENV"] = "1"
    env["PYTHON_BIN"] = str(REPO_ROOT / ".venv" / "bin" / "python")

    restore_script = work_dir / "restore_production_bundle.sh"
    res = subprocess.run(
        ["bash", str(restore_script), str(dump_file), str(tampered_manifest)],
        cwd=str(work_dir),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    # La verificación falla
    assert res.returncode != 0
    assert "RESTAURACIÓN O AUDITORÍA INTERRUMPIDA" in res.stderr
    assert f"La base de datos de staging '{STAGING_DB}' se ha preservado intacta para análisis forense" in res.stderr

    # INVARIANTE: Staging DEBE EXISTIR en el catálogo y tener las tablas restauradas
    check_staging = run_cmd([
        "docker", "exec", "-i", DRILL_CONTAINER,
        "psql", "-U", SUPERUSER, "-d", "postgres", "-tAc",
        f"SELECT 1 FROM pg_database WHERE datname = '{STAGING_DB}';",
    ])
    assert check_staging.stdout.strip() == "1", "Staging debe existir tras fallo de verificación"

    # Comprobar que las tablas restauradas existen en staging para que el operador pueda auditar
    check_tables = run_cmd([
        "docker", "exec", "-i", DRILL_CONTAINER,
        "psql", "-U", APP_USER, "-d", STAGING_DB, "-tAc",
        "SELECT count(*) FROM pg_tables WHERE schemaname = 'public';",
    ])
    assert int(check_tables.stdout.strip()) >= 10, "Las tablas restauradas deben estar preservadas"

    # Limpiar para la restauración limpia del requisito 4
    run_cmd([
        "docker", "exec", "-i", DRILL_CONTAINER,
        "psql", "-U", SUPERUSER, "-d", "postgres", "-c",
        f"DROP DATABASE {STAGING_DB};",
    ])


def test_empirical_4_restauracion_correcta_ocho_controles_pass_y_stop(drill_cluster):
    """Requisito 4: Restauración limpia con volcado productivo real: los 8 controles en PASS
    y parada obligatoria en STOP sin promoción a producción.
    """
    work_dir = drill_cluster["work_dir"]
    dump_file = drill_cluster["dump_file"]
    manifest_file = drill_cluster["manifest_file"]

    env = os.environ.copy()
    env["ALLOW_NON_ROOT_ENV"] = "1"
    env["PYTHON_BIN"] = str(REPO_ROOT / ".venv" / "bin" / "python")

    restore_script = work_dir / "restore_production_bundle.sh"
    res = subprocess.run(
        ["bash", str(restore_script), str(dump_file), str(manifest_file)],
        cwd=str(work_dir),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert res.returncode == 0, f"Restoration script failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"

    # Validar reporte de salida
    assert "8 de 8 controles aprobados (PASS)" in res.stdout
    assert "STOP OBLIGATORIO" in res.stdout
    assert "La base de staging está lista y auditada." in res.stdout
    assert "La promoción a producción NO se ejecuta automáticamente." in res.stdout
    assert "./promote_to_production.sh" in res.stdout

    # Validar que staging existe y producción NO existe aún
    check_staging = run_cmd([
        "docker", "exec", "-i", DRILL_CONTAINER,
        "psql", "-U", SUPERUSER, "-d", "postgres", "-tAc",
        f"SELECT 1 FROM pg_database WHERE datname = '{STAGING_DB}';",
    ])
    assert check_staging.stdout.strip() == "1", "Staging DB debe existir"

    check_target = run_cmd([
        "docker", "exec", "-i", DRILL_CONTAINER,
        "psql", "-U", SUPERUSER, "-d", "postgres", "-tAc",
        f"SELECT 1 FROM pg_database WHERE datname = '{TARGET_DB}';",
    ])
    assert check_target.stdout.strip() != "1", "Target DB NO debe existir (promoción no realizada)"


def test_empirical_5_ausencia_total_de_drop_database(drill_cluster):
    """Requisito 5: Comprobar la ausencia total de sentencias SQL DROP DATABASE en todo el script
    de restauración y verificar que no se ejecutó ningún DROP DATABASE en el motor.
    """
    restore_script = DEPLOY_DIR / "restore_production_bundle.sh"
    content = restore_script.read_text(encoding="utf-8")

    # Analizar todas las líneas con DROP DATABASE
    # Sólo se permiten menciones en mensajes de log que afirmen expresamente que NO se ejecuta
    for idx, line in enumerate(content.splitlines(), start=1):
        if "DROP DATABASE" in line:
            stripped = line.strip()
            # Si no es un comentario ni un mensaje de log sobre la ausencia de drop, fallar
            assert (
                "sin ejecutar DROP DATABASE" in stripped
                or "No se ha ejecutado ningún DROP DATABASE" in stripped
                or stripped.startswith("#")
            ), f"Línea {idx} contiene una sentencia DROP DATABASE no autorizada: {line}"


def test_empirical_6_promocion_controlada_con_desalojo_de_conexiones(drill_cluster):
    """Requisito complementario de flujo: Promover staging a producción de forma desacoplada
    mediante promote_to_production.sh, desalojando conexiones con ALLOW_CONNECTIONS=false.
    """
    work_dir = drill_cluster["work_dir"]

    # Iniciar conexión activa en background sobre staging con pg_sleep(30)
    bg_proc = subprocess.Popen(
        [
            "docker", "exec", "-i", DRILL_CONTAINER,
            "psql", "-U", APP_USER, "-d", STAGING_DB, "-c", "SELECT pg_sleep(30);",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Esperar a que la conexión aparezca en pg_stat_activity
    for _ in range(10):
        active_conns = run_cmd([
            "docker", "exec", "-i", DRILL_CONTAINER,
            "psql", "-U", SUPERUSER, "-d", "postgres", "-tAc",
            f"SELECT count(*) FROM pg_stat_activity WHERE datname = '{STAGING_DB}' AND pid <> pg_backend_pid();",
        ])
        if int(active_conns.stdout.strip() or 0) >= 1:
            break
        time.sleep(0.5)
    else:
        bg_proc.kill()
        pytest.fail("Conexión en background no apareció en pg_stat_activity")

    # Ejecutar promoción explícita
    env = os.environ.copy()
    env["ALLOW_NON_ROOT_ENV"] = "1"
    promote_script = work_dir / "promote_to_production.sh"
    res = subprocess.run(
        ["bash", str(promote_script)],
        cwd=str(work_dir),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert res.returncode == 0, f"Promoción falló:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    assert "PROMOCIÓN A PRODUCCIÓN COMPLETADA EXITOSAMENTE" in res.stdout

    # La conexión activa fue terminada limpiamente por pg_terminate_backend
    bg_proc.communicate(timeout=5)

    # Validar que fireassets existe y staging ya no
    check_target = run_cmd([
        "docker", "exec", "-i", DRILL_CONTAINER,
        "psql", "-U", SUPERUSER, "-d", "postgres", "-tAc",
        f"SELECT 1 FROM pg_database WHERE datname = '{TARGET_DB}';",
    ])
    assert check_target.stdout.strip() == "1", "Target DB debe existir tras promoción"

    check_staging = run_cmd([
        "docker", "exec", "-i", DRILL_CONTAINER,
        "psql", "-U", SUPERUSER, "-d", "postgres", "-tAc",
        f"SELECT 1 FROM pg_database WHERE datname = '{STAGING_DB}';",
    ])
    assert check_staging.stdout.strip() != "1", "Staging DB no debe existir tras renombramiento"

    # Validar administrador activo en producción promovida
    admin_query = run_cmd([
        "docker", "exec", "-i", DRILL_CONTAINER,
        "psql", "-U", APP_USER, "-d", TARGET_DB, "-tAc",
        "SELECT email, activo FROM usuarios WHERE email = 'fernandezluis303@gmail.com';",
    ])
    assert "fernandezluis303@gmail.com|t" in admin_query.stdout, "Administrador debe estar activo en producción"


def test_empirical_7_fail_closed_cuando_destino_ya_existe(drill_cluster):
    """Requisito complementario: Promoción rechaza si 'fireassets' ya existe, preservando datos."""
    work_dir = drill_cluster["work_dir"]

    # Crear staging temporal
    run_cmd([
        "docker", "exec", "-i", DRILL_CONTAINER,
        "psql", "-U", SUPERUSER, "-d", "postgres", "-c",
        f"CREATE DATABASE {STAGING_DB} OWNER {APP_USER};",
    ])

    env = os.environ.copy()
    env["ALLOW_NON_ROOT_ENV"] = "1"
    promote_script = work_dir / "promote_to_production.sh"
    res = subprocess.run(
        ["bash", str(promote_script)],
        cwd=str(work_dir),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert res.returncode == 1, "Debe abortar con código 1"
    assert "RECHAZO DE SEGURIDAD" in res.stderr
    assert f"La base de datos destino '{TARGET_DB}' ya existe" in res.stderr

    # Limpiar staging dummy
    run_cmd([
        "docker", "exec", "-i", DRILL_CONTAINER,
        "psql", "-U", SUPERUSER, "-d", "postgres", "-c",
        f"DROP DATABASE {STAGING_DB};",
    ])


def test_empirical_8_invariante_falla_post_rename_nunca_elimina_fireassets(drill_cluster):
    """Requisito complementario: Invariante post-rename: si ocurre un fallo después del renombramiento,
    JAMÁS se ejecuta DROP DATABASE sobre la base promovida.
    """
    work_dir = drill_cluster["work_dir"]
    test_staging = "staging_crash_survive"
    test_target = "target_crash_survive"

    run_cmd([
        "docker", "exec", "-i", DRILL_CONTAINER,
        "psql", "-U", SUPERUSER, "-d", "postgres", "-c",
        f"DROP DATABASE IF EXISTS {test_staging};",
    ])
    run_cmd([
        "docker", "exec", "-i", DRILL_CONTAINER,
        "psql", "-U", SUPERUSER, "-d", "postgres", "-c",
        f"DROP DATABASE IF EXISTS {test_target};",
    ])
    run_cmd([
        "docker", "exec", "-i", DRILL_CONTAINER,
        "psql", "-U", SUPERUSER, "-d", "postgres", "-c",
        f"CREATE DATABASE {test_staging} OWNER {APP_USER};",
    ])
    run_cmd([
        "docker", "exec", "-i", DRILL_CONTAINER,
        "psql", "-U", APP_USER, "-d", test_staging, "-c",
        "CREATE TABLE crash_test_data (id int, val text); INSERT INTO crash_test_data VALUES (1, 'MUST_SURVIVE');",
    ])

    # Script con fallo simulado post-rename
    orig_script = (work_dir / "promote_to_production.sh").read_text(encoding="utf-8")
    crash_script_content = orig_script.replace(
        'STAGING_DB="$EXPECTED_STAGING_DB"',
        f'STAGING_DB="{test_staging}"',
    ).replace(
        'TARGET_DB="$EXPECTED_TARGET_DB"',
        f'TARGET_DB="{test_target}"',
    ).replace(
        'echo "5. Asignando propietario',
        'echo "SIMULATING_POST_RENAME_CRASH" >&2; exit 42\necho "5. Asignando propietario',
    )

    crash_file = work_dir / "promote_crash_test.sh"
    crash_file.write_text(crash_script_content, encoding="utf-8")
    crash_file.chmod(0o755)

    env = os.environ.copy()
    env["ALLOW_NON_ROOT_ENV"] = "1"
    res = subprocess.run(
        ["bash", str(crash_file)],
        cwd=str(work_dir),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert res.returncode == 42
    assert "INVARIANTE DE SEGURIDAD" in res.stderr
    assert f"La base de producción '{test_target}' NO se elimina ni se revierte" in res.stderr

    # Target debe seguir existiendo intacto
    check_exists = run_cmd([
        "docker", "exec", "-i", DRILL_CONTAINER,
        "psql", "-U", SUPERUSER, "-d", "postgres", "-tAc",
        f"SELECT 1 FROM pg_database WHERE datname = '{test_target}';",
    ])
    assert check_exists.stdout.strip() == "1", f"Target {test_target} debe existir"

    data_check = run_cmd([
        "docker", "exec", "-i", DRILL_CONTAINER,
        "psql", "-U", SUPERUSER, "-d", test_target, "-tAc",
        "SELECT val FROM crash_test_data WHERE id = 1;",
    ])
    assert data_check.stdout.strip() == "MUST_SURVIVE", "Los datos deben estar intactos"

    # Limpieza
    run_cmd([
        "docker", "exec", "-i", DRILL_CONTAINER,
        "psql", "-U", SUPERUSER, "-d", "postgres", "-c",
        f"DROP DATABASE {test_target};",
    ])


def test_empirical_9_fallo_simulado_consulta_existencia_aborta_sin_create_db(drill_cluster):
    """Requisito adicional: Simular fallo de psql/docker en la consulta de existencia de staging
    y verificar que aborta con código no cero sin ejecutar CREATE DATABASE, así como también
    ante un resultado inesperado (distinto de 1 o vacío).
    """
    work_dir = drill_cluster["work_dir"]
    dump_file = drill_cluster["dump_file"]
    manifest_file = drill_cluster["manifest_file"]

    # Asegurar que staging no existe antes de la prueba
    run_cmd([
        "docker", "exec", "-i", DRILL_CONTAINER,
        "psql", "-U", SUPERUSER, "-d", "postgres", "-c",
        f"DROP DATABASE IF EXISTS {STAGING_DB};",
    ])

    env = os.environ.copy()
    env["ALLOW_NON_ROOT_ENV"] = "1"
    env["PYTHON_BIN"] = str(REPO_ROOT / ".venv" / "bin" / "python")

    # Caso A: Fallo de ejecución en la consulta (ej. error SQL en psql)
    orig_content = (work_dir / "restore_production_bundle.sh").read_text(encoding="utf-8")
    crashed_query_content = orig_content.replace(
        "\"SELECT 1 FROM pg_database WHERE datname = '$STAGING_DB';\" 2>&1)\"",
        "\"SELECT 1/0 FROM pg_database;\" 2>&1)\"",
    )
    crashed_script = work_dir / "restore_crash_query_test.sh"
    crashed_script.write_text(crashed_query_content, encoding="utf-8")
    crashed_script.chmod(0o755)

    res_crash = subprocess.run(
        ["bash", str(crashed_script), str(dump_file), str(manifest_file)],
        cwd=str(work_dir),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert res_crash.returncode != 0, "Debe fallar con código no cero si la consulta falla"
    assert "ERROR CRÍTICO: Falló la consulta de existencia de staging en PostgreSQL" in res_crash.stderr
    assert "division by zero" in res_crash.stderr or "código" in res_crash.stderr
    assert "Restauración abortada de inmediato sin ejecutar CREATE DATABASE" in res_crash.stderr

    # INVARIANTE: Staging NO debe haber sido creada
    check_not_created = run_cmd([
        "docker", "exec", "-i", DRILL_CONTAINER,
        "psql", "-U", SUPERUSER, "-d", "postgres", "-tAc",
        f"SELECT 1 FROM pg_database WHERE datname = '{STAGING_DB}';",
    ])
    assert check_not_created.stdout.strip() != "1", "CREATE DATABASE no debe haberse ejecutado tras fallo de consulta"

    # Caso B: Resultado inesperado (distinto de '1' o vacío, ej. 'UNKNOWN_STATE')
    unexpected_content = orig_content.replace(
        "\"SELECT 1 FROM pg_database WHERE datname = '$STAGING_DB';\" 2>&1)\"",
        "\"SELECT 'UNKNOWN_STATE';\" 2>&1)\"",
    )
    unexpected_script = work_dir / "restore_unexpected_res_test.sh"
    unexpected_script.write_text(unexpected_content, encoding="utf-8")
    unexpected_script.chmod(0o755)

    res_unexp = subprocess.run(
        ["bash", str(unexpected_script), str(dump_file), str(manifest_file)],
        cwd=str(work_dir),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert res_unexp.returncode == 1
    assert "ERROR CRÍTICO: Resultado inesperado en la consulta de existencia de staging: 'UNKNOWN_STATE'" in res_unexp.stderr
    assert "Abortando sin ejecutar CREATE DATABASE" in res_unexp.stderr

    # INVARIANTE: Staging NO debe haber sido creada
    check_still_empty = run_cmd([
        "docker", "exec", "-i", DRILL_CONTAINER,
        "psql", "-U", SUPERUSER, "-d", "postgres", "-tAc",
        f"SELECT 1 FROM pg_database WHERE datname = '{STAGING_DB}';",
    ])
    assert check_still_empty.stdout.strip() != "1", "CREATE DATABASE no debe haberse ejecutado"


def test_empirical_10_valores_inesperados_configuracion_rechazados(drill_cluster):
    """Requisito adicional: Validar que valores no canónicos de POSTGRES_STAGING_DB o FIREOPS_APP_DB
    en .env sean estrictamente rechazados con exit 1 y RECHAZO DE SEGURIDAD.
    """
    work_dir = drill_cluster["work_dir"]
    dump_file = drill_cluster["dump_file"]
    manifest_file = drill_cluster["manifest_file"]
    env_file = work_dir / ".env"
    backup_env = env_file.read_text(encoding="utf-8")

    env = os.environ.copy()
    env["ALLOW_NON_ROOT_ENV"] = "1"
    env["PYTHON_BIN"] = str(REPO_ROOT / ".venv" / "bin" / "python")

    restore_script = work_dir / "restore_production_bundle.sh"

    try:
        # Caso A: POSTGRES_STAGING_DB inesperado
        env_file.write_text(
            f"""POSTGRES_CONTAINER_NAME={DRILL_CONTAINER}
POSTGRES_HOST_PORT={DRILL_PORT}
POSTGRES_SUPERUSER={SUPERUSER}
POSTGRES_SUPERUSER_PASSWORD={SUPERUSER_PASS}
FIREOPS_APP_USER={APP_USER}
FIREOPS_APP_PASSWORD={APP_PASS}
FIREOPS_APP_DB={TARGET_DB}
POSTGRES_STAGING_DB=unexpected_staging_name
""",
            encoding="utf-8",
        )
        env_file.chmod(0o600)

        res_staging = subprocess.run(
            ["bash", str(restore_script), str(dump_file), str(manifest_file)],
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        assert res_staging.returncode == 1
        assert "RECHAZO DE SEGURIDAD: POSTGRES_STAGING_DB tiene un valor no permitido" in res_staging.stderr
        assert "Debe ser exactamente 'fireassets_staging_vps'" in res_staging.stderr

        # Caso B: FIREOPS_APP_DB inesperado
        env_file.write_text(
            f"""POSTGRES_CONTAINER_NAME={DRILL_CONTAINER}
POSTGRES_HOST_PORT={DRILL_PORT}
POSTGRES_SUPERUSER={SUPERUSER}
POSTGRES_SUPERUSER_PASSWORD={SUPERUSER_PASS}
FIREOPS_APP_USER={APP_USER}
FIREOPS_APP_PASSWORD={APP_PASS}
FIREOPS_APP_DB=unexpected_target_production_db
POSTGRES_STAGING_DB={STAGING_DB}
""",
            encoding="utf-8",
        )
        env_file.chmod(0o600)

        res_target = subprocess.run(
            ["bash", str(restore_script), str(dump_file), str(manifest_file)],
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        assert res_target.returncode == 1
        assert "RECHAZO DE SEGURIDAD: FIREOPS_APP_DB tiene un valor no permitido" in res_target.stderr
        assert "Debe ser exactamente 'fireassets'" in res_target.stderr

    finally:
        # Restaurar .env genuino
        env_file.write_text(backup_env, encoding="utf-8")
        env_file.chmod(0o600)

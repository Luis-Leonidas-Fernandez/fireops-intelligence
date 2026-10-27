#!/usr/bin/env bash
# ==============================================================================
# deploy/postgres/restore_production_bundle.sh
# Restauración protegida en staging y auditoría de integridad de fireassets en VPS.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

usage() {
    cat <<EOF
Uso: $(basename "$0") <RUTA_ARCHIVO_DUMP_O_SQL> <RUTA_MANIFEST_JSON> [RUTA_VERIFY_SCRIPT]

Argumentos obligatorios:
  RUTA_ARCHIVO_DUMP_O_SQL   Ruta absoluta o relativa al volcado (.dump o .sql)
  RUTA_MANIFEST_JSON        Ruta al manifiesto .manifest.json generado con el volcado

Argumento opcional:
  RUTA_VERIFY_SCRIPT        Ruta a verify_restored_db.py (por defecto busca en el mismo directorio)
EOF
    exit 1
}

if [[ $# -lt 2 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
fi

ENV_FILE="${SCRIPT_DIR}/.env"

if [[ ! -e "$ENV_FILE" ]]; then
    echo "❌ Error: Archivo .env no encontrado en $SCRIPT_DIR" >&2
    exit 1
fi

# Validación estricta de seguridad de .env antes de cargarlo mediante source
validate_env_security() {
    local target="$1"
    python3 -c "
import os, stat, sys

target = sys.argv[1]
allow_non_root = os.getenv('ALLOW_NON_ROOT_ENV', '0') == '1'

try:
    st = os.lstat(target)
except OSError as e:
    sys.exit(f'Error accediendo a {target}: {e}')

if stat.S_ISLNK(st.st_mode):
    sys.exit('RECHAZO DE SEGURIDAD: .env es un enlace simbólico (prohibido).')

if not stat.S_ISREG(st.st_mode):
    sys.exit('RECHAZO DE SEGURIDAD: .env no es un archivo regular.')

mode = stat.S_IMODE(st.st_mode)
if mode & 0o077 != 0:
    sys.exit(f'RECHAZO DE SEGURIDAD: Permisos inseguros en .env ({oct(mode)}). Grupo u otros tienen permisos. Debe ser 0600 o 0400.')

# En producción VPS debe pertenecer a root (UID 0). En ensayos locales controlados se permite el usuario ejecutor con ALLOW_NON_ROOT_ENV=1
if st.st_uid != 0:
    if not allow_non_root:
        sys.exit(f'RECHAZO DE SEGURIDAD: .env pertenece al UID {st.st_uid}, no a root (UID 0).')
    elif st.st_uid != os.geteuid():
        sys.exit(f'RECHAZO DE SEGURIDAD: .env pertenece al UID {st.st_uid}, que no coincide con el usuario ejecutor ({os.geteuid()}).')
" "$target"
}

if ! validate_env_security "$ENV_FILE"; then
    echo "❌ Error de validación de seguridad sobre .env. Abortando antes de cargar variables." >&2
    exit 1
fi

set -a
# shellcheck disable=SC1091
source "$ENV_FILE"
set +a

ARCHIVE_PATH="$1"
MANIFEST_PATH="$2"
VERIFY_SCRIPT="${3:-}"

CONTAINER_NAME="${POSTGRES_CONTAINER_NAME:-fireassets-postgres}"
HOST_PORT="${POSTGRES_HOST_PORT:-5432}"

EXPECTED_STAGING_DB="fireassets_staging_vps"
EXPECTED_TARGET_DB="fireassets"

# Validar estrictamente los nombres canónicos inmutables de bases de datos
if [[ -n "${POSTGRES_STAGING_DB:-}" && "$POSTGRES_STAGING_DB" != "$EXPECTED_STAGING_DB" ]]; then
    echo "❌ RECHAZO DE SEGURIDAD: POSTGRES_STAGING_DB tiene un valor no permitido ('$POSTGRES_STAGING_DB'). Debe ser exactamente '$EXPECTED_STAGING_DB'." >&2
    exit 1
fi

if [[ -n "${FIREOPS_APP_DB:-}" && "$FIREOPS_APP_DB" != "$EXPECTED_TARGET_DB" ]]; then
    echo "❌ RECHAZO DE SEGURIDAD: FIREOPS_APP_DB tiene un valor no permitido ('$FIREOPS_APP_DB'). Debe ser exactamente '$EXPECTED_TARGET_DB'." >&2
    exit 1
fi

STAGING_DB="$EXPECTED_STAGING_DB"
TARGET_DB="$EXPECTED_TARGET_DB"

if [[ ! -f "$ARCHIVE_PATH" ]]; then
    echo "Error: Archivo de volcado no encontrado en '$ARCHIVE_PATH'." >&2
    exit 1
fi

if [[ ! -f "$MANIFEST_PATH" ]]; then
    echo "Error: Archivo de manifiesto no encontrado en '$MANIFEST_PATH'." >&2
    exit 1
fi

# Localizar verify_restored_db.py obligatoriamente (evita falsos PASS)
if [[ -z "$VERIFY_SCRIPT" || ! -f "$VERIFY_SCRIPT" ]]; then
    if [[ -f "${SCRIPT_DIR}/verify_restored_db.py" ]]; then
        VERIFY_SCRIPT="${SCRIPT_DIR}/verify_restored_db.py"
    elif [[ -f "$(dirname "$MANIFEST_PATH")/verify_restored_db.py" ]]; then
        VERIFY_SCRIPT="$(dirname "$MANIFEST_PATH")/verify_restored_db.py"
    elif [[ -f "${SCRIPT_DIR}/../../scripts/verify_restored_db.py" ]]; then
        VERIFY_SCRIPT="${SCRIPT_DIR}/../../scripts/verify_restored_db.py"
    else
        echo "❌ ERROR CRÍTICO: No se encontró 'verify_restored_db.py'." >&2
        echo "La verificación rigurosa es obligatoria; no se permiten restauraciones sin auditoría automatizada." >&2
        exit 1
    fi
fi

echo "=== [RESTAURACIÓN] Iniciando restauración protegida en VPS ==="
echo "Contenedor destino: $CONTAINER_NAME"
echo "Archivo volcado:    $ARCHIVE_PATH"
echo "Manifiesto:         $MANIFEST_PATH"
echo "Script verificador: $VERIFY_SCRIPT"

# 1. Comprobar que el contenedor esté en ejecución y saludable
STATUS="$(docker inspect --format '{{.State.Health.Status}}' "$CONTAINER_NAME" 2>/dev/null || echo "not_found")"
if [[ "$STATUS" != "healthy" ]]; then
    echo "❌ Error: El contenedor '$CONTAINER_NAME' no se encuentra en estado 'healthy' (estado: $STATUS)." >&2
    exit 1
fi
echo "✅ Contenedor '$CONTAINER_NAME' saludable."

# 2. Validar Checksum criptográfico SHA-256
SHA_FILE="${ARCHIVE_PATH}.sha256"
if [[ ! -f "$SHA_FILE" ]]; then
    SHA_FILE="${ARCHIVE_PATH%.*}.sha256"
fi

if [[ -f "$SHA_FILE" ]]; then
    echo "1. Validando hash SHA-256 contra archivo checksum..."
    (cd "$(dirname "$ARCHIVE_PATH")" && sha256sum -c "$(basename "$SHA_FILE")")
    echo "✅ Checksum SHA-256 verificado con éxito."
else
    echo "1. Validando hash SHA-256 contra el manifiesto JSON..."
    EXPECTED_SHA="$(python3 -c "
import json, sys
with open(sys.argv[1], encoding='utf-8') as f:
    m = json.load(f)
    ext = 'sql' if sys.argv[2].endswith('.sql') else 'dump'
    print(m.get('files', {}).get(ext, {}).get('sha256', ''))
" "$MANIFEST_PATH" "$ARCHIVE_PATH")"
    ACTUAL_SHA="$(sha256sum "$ARCHIVE_PATH" | awk '{print $1}')"
    if [[ -z "$EXPECTED_SHA" || "$EXPECTED_SHA" != "$ACTUAL_SHA" ]]; then
        echo "❌ ERROR CRÍTICO: Discrepancia en checksum SHA-256!" >&2
        echo "  Esperado por manifiesto: '$EXPECTED_SHA'" >&2
        echo "  Calculado en archivo:    '$ACTUAL_SHA'" >&2
        exit 1
    fi
    echo "✅ Checksum verificado contra manifiesto: $ACTUAL_SHA"
fi

# 3. Guarda Fail-Closed: La base de staging NO debe existir previamente
echo "2. Verificando que la base de staging '$STAGING_DB' no exista previamente..."

# Ejecución rigurosa con -v ON_ERROR_STOP=1 y sin supresión de errores ni redirección a null
STAGING_QUERY_ERR=0
STAGING_EXISTS="$(docker exec -i "$CONTAINER_NAME" psql -v ON_ERROR_STOP=1 \
    -U "$POSTGRES_SUPERUSER" -d postgres -tAc \
    "SELECT 1 FROM pg_database WHERE datname = '$STAGING_DB';" 2>&1)" || STAGING_QUERY_ERR=$?

if [[ $STAGING_QUERY_ERR -ne 0 ]]; then
    echo "❌ ERROR CRÍTICO: Falló la consulta de existencia de staging en PostgreSQL (código $STAGING_QUERY_ERR)." >&2
    echo "Detalle de error devuelto por PostgreSQL / Docker:" >&2
    echo "$STAGING_EXISTS" >&2
    echo "Restauración abortada de inmediato sin ejecutar CREATE DATABASE." >&2
    exit "$STAGING_QUERY_ERR"
fi

STAGING_EXISTS="$(echo "$STAGING_EXISTS" | tr -d '[:space:]')"

if [[ "$STAGING_EXISTS" == "1" ]]; then
    echo "❌ RECHAZO DE SEGURIDAD: La base de datos de staging '$STAGING_DB' ya existe en el servidor." >&2
    echo "Restauración abortada sin modificaciones, sin terminar conexiones y sin ejecutar DROP DATABASE." >&2
    echo "Para preservar datos existentes, resuelva la base de staging manualmente antes de reintentar." >&2
    exit 1
elif [[ -z "$STAGING_EXISTS" ]]; then
    echo "✅ Base de staging '$STAGING_DB' libre para creación limpia."
else
    echo "❌ ERROR CRÍTICO: Resultado inesperado en la consulta de existencia de staging: '$STAGING_EXISTS'." >&2
    echo "Se esperaba '1' o vacío. Abortando sin ejecutar CREATE DATABASE." >&2
    exit 1
fi

# Creación limpia de la base de datos de staging (sin DROP DATABASE)
echo "3. Creando base de datos de staging limpia '$STAGING_DB' con propietario '$FIREOPS_APP_USER'..."
docker exec -i "$CONTAINER_NAME" psql -v ON_ERROR_STOP=1 -U "$POSTGRES_SUPERUSER" -d postgres -c \
    "CREATE DATABASE \"$STAGING_DB\" WITH OWNER = \"$FIREOPS_APP_USER\" ENCODING = 'UTF8';"

# Trampa de diagnóstico no destructiva: Preservar staging ante fallos para análisis forense
notify_on_failure() {
    local rc=$?
    if [[ $rc -ne 0 ]]; then
        echo "❌ RESTAURACIÓN O AUDITORÍA INTERRUMPIDA (código $rc)." >&2
        echo "DIAGNÓSTICO: La base de datos de staging '$STAGING_DB' se ha preservado intacta para análisis forense." >&2
        echo "INVARIANTE DE SEGURIDAD: No se ha ejecutado ningún DROP DATABASE. Producción permanece intacta." >&2
    fi
}
trap notify_on_failure EXIT

# 4. Restaurar volcado en la base de staging
echo "3. Restaurando volcado dentro de '$STAGING_DB' como '$FIREOPS_APP_USER'..."
if [[ "$ARCHIVE_PATH" == *.sql ]]; then
    # Restauración SQL: ON_ERROR_STOP=1 garantiza fallo inmediato ante cualquier error SQL
    docker exec -i "$CONTAINER_NAME" psql -v ON_ERROR_STOP=1 \
        -U "$FIREOPS_APP_USER" -d "$STAGING_DB" < "$ARCHIVE_PATH"
else
    # Restauración Custom format: --exit-on-error detiene inmediatamente ante fallos de catálogo
    docker exec -i "$CONTAINER_NAME" pg_restore --no-owner --no-privileges --exit-on-error \
        -U "$FIREOPS_APP_USER" -d "$STAGING_DB" < "$ARCHIVE_PATH"
fi
echo "✅ Volcado procesado sin errores."

# 5. Ejecutar la suite exhaustiva de verificación
echo "4. Ejecutando suite de auditoría integral contra '$STAGING_DB'..."

PYTHON_EXEC="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_EXEC" ]]; then
    if [[ -f "${SCRIPT_DIR}/.venv/bin/python" ]]; then
        PYTHON_EXEC="${SCRIPT_DIR}/.venv/bin/python"
    elif [[ -f "/opt/fireassets-db/.venv/bin/python" ]]; then
        PYTHON_EXEC="/opt/fireassets-db/.venv/bin/python"
    elif [[ -f "${SCRIPT_DIR}/../../.venv/bin/python" ]]; then
        PYTHON_EXEC="${SCRIPT_DIR}/../../.venv/bin/python"
    else
        PYTHON_EXEC="python3"
    fi
fi

if ! "$PYTHON_EXEC" -c "import asyncpg" >/dev/null 2>&1; then
    echo "❌ ERROR CRÍTICO: El intérprete Python ('$PYTHON_EXEC') no contiene el módulo 'asyncpg'." >&2
    echo "Para mantener el sistema limpio, cree un entorno virtual aislado en el VPS:" >&2
    echo "  python3 -m venv ${SCRIPT_DIR}/.venv" >&2
    echo "  ${SCRIPT_DIR}/.venv/bin/pip install --no-cache-dir asyncpg" >&2
    exit 1
fi

# Pasar credenciales mediante variables de entorno de proceso (privadas) y sólo el nombre
# de la base como argumento de CLI para evitar filtraciones en 'ps aux' o '/proc/<pid>/cmdline'
PGHOST="127.0.0.1" \
PGPORT="${HOST_PORT}" \
PGUSER="${FIREOPS_APP_USER}" \
PGPASSWORD="${FIREOPS_APP_PASSWORD}" \
"$PYTHON_EXEC" "$VERIFY_SCRIPT" "$STAGING_DB" --manifest "$MANIFEST_PATH"

echo "✅ Todos los 8 checks de verificación superados exitosamente en '$STAGING_DB'."

# Desarmar trampa de limpieza tras verificación exitosa de staging
trap - EXIT

echo "========================================================================"
echo "✅ FASE DE RESTAURACIÓN Y AUDITORÍA EN STAGING COMPLETADA EXITOSAMENTE"
echo "Base de datos en staging: '$STAGING_DB'"
echo "Auditoría de integridad:  8 de 8 controles aprobados (PASS)"
echo "Base de producción:       '$TARGET_DB' permanece intacta y no creada aún"
echo ""
echo "🛑 STOP OBLIGATORIO:"
echo "La base de staging está lista y auditada."
echo "La promoción a producción NO se ejecuta automáticamente."
echo "Para promover '$STAGING_DB' a '$TARGET_DB' mediante la sentencia independiente,"
echo "ejecute con nueva autorización explícita:"
echo "  ./promote_to_production.sh"
echo "========================================================================"
exit 0

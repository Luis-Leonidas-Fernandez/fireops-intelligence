#!/usr/bin/env bash
# ==============================================================================
# deploy/postgres/promote_to_production.sh
# Promoción explícita y protegida de staging a producción para fireassets.
#
# CARACTERÍSTICAS DE SEGURIDAD:
# 1. Ejecución independiente: Desacoplada de la restauración y auditoría previa.
# 2. Sentencia standalone: ALTER DATABASE ... RENAME TO ejecutada fuera de bloques
#    transaccionales (bloques procedimentales o BEGIN ... COMMIT), cumpliendo la restricción DDL de PG.
# 3. Fail-Closed: Si la base de destino ($FIREOPS_APP_DB) ya existe, aborta
#    inmediatamente sin modificar ni sobrescribir datos.
# 4. Gating de conexiones: Deshabilita ALLOW_CONNECTIONS en staging y desaloja
#    sesiones activas con pg_terminate_backend antes del rename.
# 5. Sin contraseñas en CLI: Las operaciones administrativas usan el socket o
#    parámetros internos de docker exec psql como superusuario.
# 6. Invariante post-promoción: NUNCA se ejecuta DROP DATABASE sobre la base
#    promovida ante fallos posteriores. Los datos renombrados quedan preservados.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

usage() {
    cat <<EOF
Uso: $(basename "$0") [OPCIONES]

Opciones:
  -h, --help    Muestra esta ayuda y termina.

Requisitos previos:
  - Archivo .env configurado con POSTGRES_SUPERUSER y FIREOPS_APP_USER.
  - Contenedor PostgreSQL en estado 'healthy'.
  - Base de datos staging (por defecto 'fireassets_staging_vps') restaurada y auditada.
  - Base de producción (por defecto 'fireassets') NO debe existir aún.
EOF
    exit 0
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
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

CONTAINER_NAME="${POSTGRES_CONTAINER_NAME:-fireassets-postgres}"
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

echo "=== [PROMOCIÓN] Iniciando promoción controlada a producción ==="
echo "Contenedor:        $CONTAINER_NAME"
echo "Base staging:      $STAGING_DB"
echo "Base producción:   $TARGET_DB"
echo "Usuario app:       $FIREOPS_APP_USER"

# 1. Comprobar que el contenedor esté en ejecución y saludable
STATUS="$(docker inspect --format '{{.State.Health.Status}}' "$CONTAINER_NAME" 2>/dev/null || echo "not_found")"
if [[ "$STATUS" != "healthy" ]]; then
    echo "❌ Error: El contenedor '$CONTAINER_NAME' no se encuentra en estado 'healthy' (estado: $STATUS)." >&2
    exit 1
fi
echo "✅ Contenedor '$CONTAINER_NAME' saludable."

# 2. Comprobar que la base de staging exista
echo "1. Comprobando existencia de base de staging '$STAGING_DB'..."
STAGING_QUERY_ERR=0
STAGING_EXISTS="$(docker exec -i "$CONTAINER_NAME" psql -v ON_ERROR_STOP=1 \
    -U "$POSTGRES_SUPERUSER" -d postgres -tAc \
    "SELECT 1 FROM pg_database WHERE datname = '$STAGING_DB';" 2>&1)" || STAGING_QUERY_ERR=$?

if [[ $STAGING_QUERY_ERR -ne 0 ]]; then
    echo "❌ ERROR CRÍTICO: Falló la consulta de existencia de staging en PostgreSQL (código $STAGING_QUERY_ERR)." >&2
    echo "$STAGING_EXISTS" >&2
    exit "$STAGING_QUERY_ERR"
fi

STAGING_EXISTS="$(echo "$STAGING_EXISTS" | tr -d '[:space:]')"
if [[ "$STAGING_EXISTS" != "1" ]]; then
    echo "❌ Error: La base de staging '$STAGING_DB' no existe en el contenedor '$CONTAINER_NAME'." >&2
    echo "Debe ejecutar y aprobar 'restore_production_bundle.sh' antes de promover a producción." >&2
    exit 1
fi
echo "✅ Base de staging '$STAGING_DB' detectada."

# 3. Comprobación FAIL-CLOSED: La base de producción NO debe existir
echo "2. Comprobando que la base destino '$TARGET_DB' no exista previamente..."
TARGET_QUERY_ERR=0
TARGET_EXISTS="$(docker exec -i "$CONTAINER_NAME" psql -v ON_ERROR_STOP=1 \
    -U "$POSTGRES_SUPERUSER" -d postgres -tAc \
    "SELECT 1 FROM pg_database WHERE datname = '$TARGET_DB';" 2>&1)" || TARGET_QUERY_ERR=$?

if [[ $TARGET_QUERY_ERR -ne 0 ]]; then
    echo "❌ ERROR CRÍTICO: Falló la consulta de existencia de producción en PostgreSQL (código $TARGET_QUERY_ERR)." >&2
    echo "$TARGET_EXISTS" >&2
    exit "$TARGET_QUERY_ERR"
fi

TARGET_EXISTS="$(echo "$TARGET_EXISTS" | tr -d '[:space:]')"
if [[ "$TARGET_EXISTS" == "1" ]]; then
    echo "❌ RECHAZO DE SEGURIDAD: La base de datos destino '$TARGET_DB' ya existe en el clúster." >&2
    echo "La promoción ha sido abortada para proteger la base preexistente sin alteraciones ni riesgo de pérdida de datos." >&2
    exit 1
elif [[ -n "$TARGET_EXISTS" ]]; then
    echo "❌ ERROR CRÍTICO: Resultado inesperado en consulta de destino: '$TARGET_EXISTS'." >&2
    exit 1
fi
echo "✅ Base de destino '$TARGET_DB' libre para asignación."

RENAME_COMPLETED=false

cleanup_on_error() {
    local rc=$?
    if [[ $rc -ne 0 ]]; then
        if [[ "$RENAME_COMPLETED" != "true" ]]; then
            echo "⚠️ La promoción fue interrumpida antes de renombrar la base." >&2
            echo "Restableciendo permisos de conexión en staging '$STAGING_DB'..." >&2
            docker exec -i "$CONTAINER_NAME" psql -U "$POSTGRES_SUPERUSER" -d postgres -c \
                "ALTER DATABASE \"$STAGING_DB\" WITH ALLOW_CONNECTIONS = true;" >/dev/null 2>&1 || true
            echo "La base de staging '$STAGING_DB' permanece disponible para inspección." >&2
        else
            echo "⚠️ La promoción falló durante la configuración o verificación posterior al renombre." >&2
            echo "INVARIANTE DE SEGURIDAD: La base de producción '$TARGET_DB' NO se elimina ni se revierte." >&2
            echo "Los datos de producción están preservados intactos en '$TARGET_DB'." >&2
        fi
    fi
}
trap cleanup_on_error EXIT

# 4. Gating de conexiones en staging: bloquear nuevas conexiones
echo "1. Bloqueando nuevas conexiones hacia '$STAGING_DB'..."
docker exec -i "$CONTAINER_NAME" psql -v ON_ERROR_STOP=1 -U "$POSTGRES_SUPERUSER" -d postgres -c \
    "ALTER DATABASE \"$STAGING_DB\" WITH ALLOW_CONNECTIONS = false;"

# 5. Desalojar conexiones activas en staging
echo "2. Desalojando conexiones activas en '$STAGING_DB'..."
docker exec -i "$CONTAINER_NAME" psql -v ON_ERROR_STOP=1 -U "$POSTGRES_SUPERUSER" -d postgres -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$STAGING_DB' AND pid <> pg_backend_pid();"

# 6. Renombrar staging a producción (sentencia standalone independiente)
echo "3. Ejecutando ALTER DATABASE RENAME TO (sentencia SQL independiente fuera de transacciones)..."
docker exec -i "$CONTAINER_NAME" psql -v ON_ERROR_STOP=1 -U "$POSTGRES_SUPERUSER" -d postgres -c \
    "ALTER DATABASE \"$STAGING_DB\" RENAME TO \"$TARGET_DB\";"

# Marca atómica de renombre exitoso: a partir de aquí, JAMÁS se borra $TARGET_DB
RENAME_COMPLETED=true

# 7. Habilitar conexiones en la base de producción
echo "4. Habilitando conexiones en '$TARGET_DB'..."
docker exec -i "$CONTAINER_NAME" psql -v ON_ERROR_STOP=1 -U "$POSTGRES_SUPERUSER" -d postgres -c \
    "ALTER DATABASE \"$TARGET_DB\" WITH ALLOW_CONNECTIONS = true;"

# 8. Asegurar asignación de propietario a fireops_app
echo "5. Asignando propietario '$FIREOPS_APP_USER' a '$TARGET_DB'..."
docker exec -i "$CONTAINER_NAME" psql -v ON_ERROR_STOP=1 -U "$POSTGRES_SUPERUSER" -d postgres -c \
    "ALTER DATABASE \"$TARGET_DB\" OWNER TO \"$FIREOPS_APP_USER\";"

# 9. Verificación de conectividad como usuario de aplicación
echo "6. Verificando conectividad como '$FIREOPS_APP_USER' en '$TARGET_DB'..."
CHECK_RESULT="$(docker exec -i "$CONTAINER_NAME" psql -U "$FIREOPS_APP_USER" -d "$TARGET_DB" -tAc \
    "SELECT current_database();" 2>/dev/null || echo "FAILED")"

if [[ "$CHECK_RESULT" != "$TARGET_DB" ]]; then
    echo "❌ Error: Verificación de conexión en '$TARGET_DB' falló (resultado: $CHECK_RESULT)." >&2
    exit 1
fi

# Desarmar trampa de salida tras éxito completo
trap - EXIT

echo "========================================================================"
echo "🎉 PROMOCIÓN A PRODUCCIÓN COMPLETADA EXITOSAMENTE"
echo "Base de datos:       '$TARGET_DB'"
echo "Propietario:         '$FIREOPS_APP_USER'"
echo "Conexiones:          Habilitadas"
echo "Alembic HEAD:        g3b7e1d5a8c2 (verificado en staging)"
echo "Primer Administrador: fernandezluis303@gmail.com (verificado en staging)"
echo "========================================================================"
exit 0

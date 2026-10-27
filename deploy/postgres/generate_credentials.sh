#!/usr/bin/env bash
# ==============================================================================
# deploy/postgres/generate_credentials.sh
# Generación atómica y segura del archivo .env con permisos 0600.
# Sustitución atómica vía archivo temporal en el mismo directorio con os.replace().
# Protegido contra symlinks, preexistencia, regeneración y fallos de escritura.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_ENV="${SCRIPT_DIR}/.env"

# Forzar umask 077 inmediatamente: cualquier archivo creado tendrá permisos 0600 nativos
umask 077

# 1. Prohibir argumentos de sobreescritura forzada (--force)
for arg in "$@"; do
    case "$arg" in
        -h|--help)
            echo "Uso: $(basename "$0")"
            echo "Genera una única vez el archivo .env con contraseñas seguras (permisos 0600)."
            echo "NOTA DE SEGURIDAD: La regeneración forzada (--force) ha sido eliminada por directiva fail-closed."
            exit 0
            ;;
        *)
            echo "⛔ RECHAZO DE SEGURIDAD: Argumento no permitido '$arg'." >&2
            echo "La opción --force ha sido eliminada. La regeneración de credenciales sobre archivos existentes está estrictamente prohibida." >&2
            exit 1
            ;;
    esac
done

# 2. Protección contra enlaces simbólicos y archivos preexistentes
if [[ -L "$TARGET_ENV" ]]; then
    echo "⛔ RECHAZO DE SEGURIDAD: '$TARGET_ENV' es un enlace simbólico." >&2
    echo "Operación abortada para prevenir ataques de symlink traversal o sobreescritura arbitraria." >&2
    exit 1
fi

if [[ -e "$TARGET_ENV" ]]; then
    echo "⛔ RECHAZO DE SEGURIDAD: El archivo de credenciales '$TARGET_ENV' ya existe." >&2
    echo "La regeneración está estrictamente prohibida para prevenir la desincronización o pérdida de acceso al clúster." >&2
    exit 1
fi

# 3. Protección contra ejecución con contenedor o volumen PostgreSQL inicializado
CONTAINER_TARGET="${POSTGRES_CONTAINER_NAME:-fireassets-postgres}"
VOLUME_TARGET="${POSTGRES_VOLUME_NAME:-fireassets_pgdata}"

if command -v docker >/dev/null 2>&1; then
    if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -Eq "^${CONTAINER_TARGET}$"; then
        echo "⛔ RECHAZO DE SEGURIDAD: El contenedor Docker '$CONTAINER_TARGET' ya existe en el host." >&2
        echo "Generar nuevas credenciales dejaría huérfana la base de datos existente." >&2
        exit 1
    fi

    if docker volume ls --format '{{.Name}}' 2>/dev/null | grep -Eq "^${VOLUME_TARGET}$"; then
        echo "⛔ RECHAZO DE SEGURIDAD: El volumen persistente '$VOLUME_TARGET' ya existe en el host." >&2
        echo "Generar nuevas credenciales invalidaría la contraseña configurada en la inicialización (initdb)." >&2
        exit 1
    fi
fi

echo "Generando credenciales seguras de alta entropía mediante sustitución atómica..."

# 4. Generación atómica en Python con os.replace() y limpieza garantizada de temporales
# Las contraseñas se generan en memoria (secrets) y nunca pasan por argumentos de CLI (/proc)
python3 -c "
import os
import sys
import tempfile
import secrets

target_path = os.path.abspath('$TARGET_ENV')
target_dir = os.path.dirname(target_path)

# Verificación estricta contra symlinks antes de crear nada
if os.path.islink(target_path) or os.path.lexists(target_path):
    sys.stderr.write(f'⛔ RECHAZO DE SEGURIDAD: El destino \'{target_path}\' ya existe o es un enlace simbolico.\n')
    sys.exit(1)

if os.path.islink(target_dir):
    sys.stderr.write(f'⛔ RECHAZO DE SEGURIDAD: El directorio \'{target_dir}\' es un enlace simbolico.\n')
    sys.exit(1)

admin_pass = secrets.token_urlsafe(32)
app_pass = secrets.token_urlsafe(32)

tmp_path = None
try:
    # Crear archivo temporal estrictamente en el MISMO directorio para garantizar atomicidad de os.replace()
    # mkstemp aplica descriptor exclusivo y umask 077
    fd, tmp_path = tempfile.mkstemp(prefix='.env.tmp.', dir=target_dir)
    os.chmod(tmp_path, 0o600)

    with open(fd, 'w', encoding='utf-8') as f:
        f.write('# ==============================================================================\n')
        f.write('# Configuración de producción para PostgreSQL 18 en VPS\n')
        f.write('# Generado atómicamente con umask 077 y os.replace(). Permisos estrictos 0600.\n')
        f.write('# ==============================================================================\n\n')
        f.write('POSTGRES_SUPERUSER=postgres_admin\n')
        f.write(f'POSTGRES_SUPERUSER_PASSWORD={admin_pass}\n')
        f.write('POSTGRES_INIT_DB=postgres\n\n')
        f.write('FIREOPS_APP_USER=fireops_app\n')
        f.write(f'FIREOPS_APP_PASSWORD={app_pass}\n')
        f.write('FIREOPS_APP_DB=fireassets\n')
        f.flush()
        os.fsync(f.fileno())

    # Comprobación de no preexistencia inmediatamente antes del switch atómico
    if os.path.islink(target_path) or os.path.lexists(target_path):
        sys.stderr.write(f'⛔ RECHAZO DE SEGURIDAD: Condición de carrera detectada. \'{target_path}\' apareció concurrentemente.\n')
        sys.exit(1)

    # Sustitución atómica: solo reemplaza en el mismo sistema de archivos
    os.replace(tmp_path, target_path)
    tmp_path = None

except Exception as err:
    sys.stderr.write(f'❌ Error generando archivo de credenciales: {err}\n')
    sys.exit(1)
finally:
    if tmp_path and os.path.lexists(tmp_path):
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
"

# 5. Verificación final de permisos del archivo resultante
PERMS="$(stat -c "%a" "$TARGET_ENV" 2>/dev/null || stat -f "%Lp" "$TARGET_ENV" 2>/dev/null || echo "600")"
if [[ "$PERMS" != "600" ]]; then
    chmod 600 "$TARGET_ENV"
fi

echo "✅ Archivo .env generado exitosamente en: $TARGET_ENV"
echo "   Permisos verificados: 0600 (lectura/escritura exclusiva del propietario)."
echo "   Cero credenciales mostradas en pantalla ni registradas en el historial de comandos."
exit 0

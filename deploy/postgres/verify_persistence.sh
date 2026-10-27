#!/usr/bin/env bash
# ==============================================================================
# deploy/postgres/verify_persistence.sh
# Validación de persistencia y tolerancia a fallos para PostgreSQL 18.
#
# GUARDA DE SEGURIDAD:
# 1. Requiere la bandera obligatoria '--allow-drill' para ejecutarse.
# 2. Bloquea su ejecución si la base 'fireassets' ya contiene datos de usuarios.
# 3. Solo actúa sobre el proyecto compose 'fireassets-db'.
# 4. NUNCA utiliza banderas destructivas de volúmenes (-v o --volumes).
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ALLOW_DRILL=0
for arg in "$@"; do
    case "$arg" in
        --allow-drill)
            ALLOW_DRILL=1
            ;;
        -h|--help)
            echo "Uso: $(basename "$0") --allow-drill"
            echo "Ejecuta una prueba controlada de persistencia reiniciando el contenedor fireassets-postgres."
            echo "ADVERTENCIA: Esta prueba produce una breve indisponibilidad temporal y solo debe ejecutarse en fase de instalación inicial."
            exit 0
            ;;
    esac
done

if [[ $ALLOW_DRILL -eq 0 ]]; then
    echo "⛔ BLOQUEO DE SEGURIDAD: Este script interrumpe temporalmente el contenedor para verificar la retención del volumen." >&2
    echo "Para autorizar y ejecutar deliberadamente esta prueba, utilice la bandera '--allow-drill'." >&2
    exit 1
fi

if [[ ! -f .env ]]; then
    echo "Error: Archivo .env no encontrado en $SCRIPT_DIR" >&2
    exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

COMPOSE_PROJECT="${COMPOSE_PROJECT_NAME:-fireassets-db}"
CONTAINER_NAME="${POSTGRES_CONTAINER_NAME:-fireassets-postgres}"
NONCE="persist_test_$(date +%s)_$RANDOM"

echo "=== [PERSISTENCIA] Verificando estado inicial del proyecto '$COMPOSE_PROJECT' ==="

# 1. Comprobar que el contenedor esté en ejecución y saludable
STATUS="$(docker inspect --format '{{.State.Health.Status}}' "$CONTAINER_NAME" 2>/dev/null || echo "not_found")"
if [[ "$STATUS" != "healthy" ]]; then
    echo "Error: El contenedor '$CONTAINER_NAME' no se encuentra en estado 'healthy' (estado actual: $STATUS)." >&2
    exit 1
fi
echo "✅ Contenedor '$CONTAINER_NAME' detectado y saludable."

# 2. Guarda contra ejecución en producción activa con datos
# Si fireassets existe y contiene usuarios, bloquear el drill para no interrumpir producción
HAS_FIREASSETS="$(docker exec -i "$CONTAINER_NAME" psql -U "$POSTGRES_SUPERUSER" -d postgres -t -A -c "
    SELECT 1 FROM pg_database WHERE datname = 'fireassets';
" 2>/dev/null || echo "0")"

if [[ "$HAS_FIREASSETS" == "1" ]]; then
    PROD_DATA="$(docker exec -i "$CONTAINER_NAME" psql -U "$POSTGRES_SUPERUSER" -d fireassets -t -A -c "
        SELECT count(*) FROM usuarios;
    " 2>/dev/null || echo "0")"

    if [[ "$PROD_DATA" =~ ^[0-9]+$ ]] && [[ "$PROD_DATA" -gt 0 ]]; then
        echo "⛔ BLOQUEO CRÍTICO: La base de datos 'fireassets' ya contiene $PROD_DATA usuario(s) en producción." >&2
        echo "El drill de persistencia con reinicio del contenedor está estrictamente bloqueado en producción activa." >&2
        exit 1
    fi
fi

# 3. Insertar registro testigo con nonce en la base administrativa 'postgres' (no en fireassets)
echo "1. Insertando registro de prueba con nonce en tabla aislada..."
docker exec -i "$CONTAINER_NAME" psql -U "$POSTGRES_SUPERUSER" -d postgres <<-EOSQL
    CREATE TABLE IF NOT EXISTS _fireassets_persistence_probe (
        id SERIAL PRIMARY KEY,
        nonce VARCHAR(120) NOT NULL,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    INSERT INTO _fireassets_persistence_probe (nonce) VALUES ('$NONCE');
EOSQL

# 4. Reinicio suave del contenedor (docker compose restart)
echo "2. Reiniciando contenedor ('docker compose -p $COMPOSE_PROJECT restart')..."
docker compose -p "$COMPOSE_PROJECT" restart
sleep 4

echo "   Esperando estado healthy tras reinicio..."
for i in {1..15}; do
    STATUS="$(docker inspect --format '{{.State.Health.Status}}' "$CONTAINER_NAME")"
    if [[ "$STATUS" == "healthy" ]]; then
        break
    fi
    sleep 2
done

CHECK_RESTART="$(docker exec -i "$CONTAINER_NAME" psql -U "$POSTGRES_SUPERUSER" -d postgres -t -A -c \
    "SELECT count(*) FROM _fireassets_persistence_probe WHERE nonce = '$NONCE';")"

if [[ "$CHECK_RESTART" -ne 1 ]]; then
    echo "❌ FALLO: El registro no persistió tras 'restart'!" >&2
    exit 1
fi
echo "✅ Registro confirmado tras reinicio suave del contenedor."

# 5. Destrucción del contenedor sin eliminar volúmenes (docker compose down SIN -v)
echo "3. Destruyendo contenedor ('docker compose -p $COMPOSE_PROJECT down' - SIN -v)..."
docker compose -p "$COMPOSE_PROJECT" down
sleep 2

# 6. Recreación del contenedor desde el volumen persistente 'fireassets_pgdata'
echo "4. Recreando contenedor desde volumen ('docker compose -p $COMPOSE_PROJECT up -d')..."
docker compose -p "$COMPOSE_PROJECT" up -d
sleep 4

echo "   Esperando estado healthy tras recreación..."
for i in {1..15}; do
    STATUS="$(docker inspect --format '{{.State.Health.Status}}' "$CONTAINER_NAME" 2>/dev/null || echo "starting")"
    if [[ "$STATUS" == "healthy" ]]; then
        break
    fi
    sleep 2
done

CHECK_RECREATE="$(docker exec -i "$CONTAINER_NAME" psql -U "$POSTGRES_SUPERUSER" -d postgres -t -A -c \
    "SELECT count(*) FROM _fireassets_persistence_probe WHERE nonce = '$NONCE';")"

if [[ "$CHECK_RECREATE" -ne 1 ]]; then
    echo "❌ FALLO CRÍTICO: El volumen 'fireassets_pgdata' no retuvo los datos tras la recreación!" >&2
    exit 1
fi
echo "✅ Registro confirmado tras recreación completa del contenedor."

# 7. Limpieza de la tabla testigo
docker exec -i "$CONTAINER_NAME" psql -U "$POSTGRES_SUPERUSER" -d postgres <<-EOSQL
    DROP TABLE IF EXISTS _fireassets_persistence_probe;
EOSQL

echo "========================================================"
echo "🎉 PRUEBA DE PERSISTENCIA Y TOLERANCIA A FALLOS: EXITOSA"
echo "El volumen persistente 'fireassets_pgdata' preserva los datos de forma inmutable."
echo "========================================================"
exit 0

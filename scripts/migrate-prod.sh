#!/usr/bin/env bash
# Script seguro para ejecutar migraciones de Alembic en PRODUCCIÓN.
# NUNCA se ejecuta de forma automática. Requiere respaldo verificado y confirmación dual.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT/.venv/bin/python"

if [[ ! -f "$ROOT/.env" ]]; then
  echo "ERROR: No se encontró el archivo de producción .env en $ROOT/.env." >&2
  exit 1
fi

if [[ ! -x "$PYTHON" ]]; then
  echo "ERROR: Intérprete Python no encontrado en el entorno virtual ($PYTHON)." >&2
  exit 1
fi

cd "$ROOT"

# Pre-validación de base de datos de producción mediante make_url
PROD_INFO="$("$PYTHON" -c "
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

env_vals = dotenv_values('.env')
url_str = env_vals.get('DATABASE_URL', '')
env_name = env_vals.get('ENVIRONMENT', '')
try:
    db_name = make_url(url_str).database if url_str else 'NO_URL'
except Exception:
    db_name = 'INVALID_URL'
print(f'{db_name}|{env_name}')
")"

TARGET_DB="${PROD_INFO%%|*}"
TARGET_ENV="${PROD_INFO##*|}"

if [[ "$TARGET_DB" != "fireassets" ]]; then
  echo "🛑 ERROR: Este script solo puede operar sobre 'fireassets' (detectado: '$TARGET_DB')." >&2
  exit 1
fi

if [[ "$TARGET_ENV" != "production" ]]; then
  echo "🛑 ERROR: El archivo .env debe tener ENVIRONMENT='production' (detectado: '$TARGET_ENV')." >&2
  exit 1
fi

# 1. Comprobación de respaldo obligatorio
BACKUP_PATH="${VERIFIED_BACKUP_FILE:-}"
if [[ -z "$BACKUP_PATH" || ! -f "$BACKUP_PATH" || ! -s "$BACKUP_PATH" ]]; then
  echo "====================================================================" >&2
  echo "🛑 ERROR: SE REQUIERE UN RESPALDO VERIFICADO ANTES DE MIGRAR PRODUCCIÓN" >&2
  echo "Debes generar y validar un volcado consistente con pg_dump y exportar:" >&2
  echo "  export VERIFIED_BACKUP_FILE=\"/ruta/al/respaldo_verificado.dump\"" >&2
  echo "====================================================================" >&2
  exit 1
fi

# 2. Comprobación de confirmación dual explícita
if [[ "${ALLOW_PRODUCTION_MIGRATIONS:-}" != "1" || "${CONFIRM_PRODUCTION_DATABASE:-}" != "fireassets" ]]; then
  echo "====================================================================" >&2
  echo "🛑 OPERACIÓN BLOQUEADA: FALTA CONFIRMACIÓN DUAL DE PRODUCCIÓN" >&2
  echo "Para autorizar la migración sobre 'fireassets', debes exportar explícitamente:" >&2
  echo "  export ALLOW_PRODUCTION_MIGRATIONS=1" >&2
  echo "  export CONFIRM_PRODUCTION_DATABASE=\"fireassets\"" >&2
  echo "====================================================================" >&2
  exit 1
fi

echo "===================================================================="
echo "⚠️  ATENCIÓN: EJECUTANDO MIGRACIÓN SOBRE PRODUCCIÓN: fireassets"
echo "    Respaldo verificado: $BACKUP_PATH"
echo "===================================================================="

ENV_FILE=".env" \
ALLOW_PRODUCTION_MIGRATIONS=1 \
CONFIRM_PRODUCTION_DATABASE="fireassets" \
"$PYTHON" -m alembic "$@"

#!/usr/bin/env bash
# Script seguro para ejecutar migraciones de Alembic en el entorno de desarrollo y pruebas.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT/.venv/bin/python"

if [[ ! -f "$ROOT/.env.test" ]]; then
  echo "ERROR: No se encontró .env.test en la raíz del proyecto ($ROOT/.env.test)." >&2
  exit 1
fi

if [[ ! -x "$PYTHON" ]]; then
  echo "ERROR: Intérprete Python no encontrado en el entorno virtual ($PYTHON)." >&2
  exit 1
fi

cd "$ROOT"

# Pre-validación estricta de la base de datos de destino mediante make_url
TARGET_DB="$("$PYTHON" -c "
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

env_vals = dotenv_values('.env.test')
url_str = env_vals.get('DATABASE_URL', '')
if not url_str:
    print('ERROR_NO_URL')
else:
    try:
        print(make_url(url_str).database or 'ERROR_NO_DB')
    except Exception:
        print('ERROR_INVALID_URL')
")"

if [[ "$TARGET_DB" != "fireassets_test" ]]; then
  echo "🛑 ERROR CRÍTICO DE AISLAMIENTO: .env.test debe apuntar exclusivamente a 'fireassets_test'." >&2
  echo "   Base detectada: '$TARGET_DB'" >&2
  exit 1
fi

echo "===================================================================="
echo "🔧 Ejecutando Alembic sobre entorno de pruebas: fireassets_test"
echo "===================================================================="

ENV_FILE=".env.test" "$PYTHON" -m alembic "$@"

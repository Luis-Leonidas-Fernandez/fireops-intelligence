#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT/.venv/bin/python"

if [[ ! -f "$ROOT/.env.test" ]]; then
  echo "Falta .env.test en la raíz del proyecto." >&2
  exit 1
fi

if [[ ! -x "$PYTHON" ]]; then
  echo "Falta el entorno virtual .venv. Crealo e instalá las dependencias del proyecto." >&2
  exit 1
fi

cd "$ROOT"
DB_NAME="$("$PYTHON" -c "from pathlib import Path; from urllib.parse import urlsplit; line=next((x for x in Path('.env.test').read_text(encoding='utf-8').splitlines() if x.startswith('DATABASE_URL=')), ''); print(urlsplit(line.split('=', 1)[1]).path.lstrip('/') if line else '')")"

if [[ "$DB_NAME" != "fireassets_test" ]]; then
  echo "Por seguridad, .env.test debe apuntar a fireassets_test (detectado: ${DB_NAME:-sin base})." >&2
  exit 1
fi

echo "Iniciando Fire Control con fireassets_test. Detené el servidor con Ctrl+C."
ENV_FILE=".env.test" "$PYTHON" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

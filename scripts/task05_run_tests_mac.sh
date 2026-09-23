#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ! -f "$REPO_ROOT/.env.test" ]]; then
  echo "No se encontró .env.test en la raíz del proyecto." >&2
  exit 1
fi

cd "$REPO_ROOT"
export ENV_FILE=".env.test"

echo "Aplicando migraciones sobre la base de testing..."
python -m alembic upgrade head

echo "Ejecutando tests de la Task 05..."
python -m pytest -v -s

#!/usr/bin/env bash
# ==============================================================================
# scripts/backup_db.sh
# Consistent, fail-safe PostgreSQL backup tool using pg_dump -Fc and SHA-256.
# Part of H-03: Production Deployment & Data Recovery Architecture.
#
# SECURITY NOTICE:
# The SHA-256 checksum provides archive integrity against transmission errors,
# disk corruption, and truncation. It DOES NOT provide cryptographic authenticity
# or non-repudiation against an adversary with write access to storage.
# In production, off-site backups require digital signatures (e.g. GPG) or
# immutable object storage (S3 Object Lock in Compliance Mode).
# ==============================================================================
set -euo pipefail

# Ensure secure file permissions (owner read/write only: 0600)
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="python3"
fi

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS] [DB_NAME] [OUTPUT_DIR]

Options:
  -d, --db NAME          Database to back up
  -o, --output-dir DIR   Directory to store the backup (default: ./backups)
  --url DATABASE_URL     Database URL (postgresql:// or postgresql+asyncpg://)
  -h, --help             Show this help message and exit

Positional arguments:
  DB_NAME                Database name (alternative to -d)
  OUTPUT_DIR             Output directory (alternative to -o)
EOF
  exit 1
}

DB_NAME=""
OUTPUT_DIR=""
DB_URL=""

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    -d|--db)
      DB_NAME="$2"
      shift 2
      ;;
    -o|--output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --url)
      DB_URL="$2"
      shift 2
      ;;
    -h|--help)
      usage
      ;;
    -*)
      echo "Unknown option: $1" >&2
      usage
      ;;
    *)
      if [[ -z "$DB_NAME" ]]; then
        DB_NAME="$1"
      elif [[ -z "$OUTPUT_DIR" ]]; then
        OUTPUT_DIR="$1"
      else
        echo "Unexpected positional argument: $1" >&2
        usage
      fi
      shift
      ;;
  esac
done

# If DATABASE_URL was provided, parse credentials safely without command-line leakage or eval
DB_URL="${DB_URL:-${DATABASE_URL:-}}"
if [[ -n "$DB_URL" ]]; then
  PARSER_STATUS=""
  PARSED_HOST=""
  PARSED_PORT=""
  PARSED_USER=""
  PARSED_PASS=""
  PARSED_DB=""

  {
    IFS= read -r -d '' PARSED_HOST || true
    IFS= read -r -d '' PARSED_PORT || true
    IFS= read -r -d '' PARSED_USER || true
    IFS= read -r -d '' PARSED_PASS || true
    IFS= read -r -d '' PARSED_DB || true
    IFS= read -r -d '' PARSER_STATUS || true
  } < <(
    printf '%s' "$DB_URL" | "$PYTHON" -c '
import sys
from urllib.parse import unquote, urlsplit

try:
    raw = sys.stdin.read().rstrip("\r\n")
    if not raw:
        sys.exit(1)
    if raw.startswith("postgresql+asyncpg://"):
        raw_std = "postgresql://" + raw[len("postgresql+asyncpg://"):]
    else:
        raw_std = raw
    parsed = urlsplit(raw_std)
    if parsed.scheme != "postgresql":
        sys.stderr.write("Error: DATABASE_URL must have postgresql:// or postgresql+asyncpg:// scheme.\n")
        sys.exit(1)
    host = unquote(parsed.hostname) if parsed.hostname else ""
    port = str(parsed.port) if parsed.port else ""
    user = unquote(parsed.username) if parsed.username else ""
    pw = unquote(parsed.password) if parsed.password else ""
    db = unquote(parsed.path.lstrip("/")) if parsed.path else ""

    for field in (host, port, user, pw, db, "PARSE_SUCCESS_V1"):
        sys.stdout.buffer.write(field.encode("utf-8") + b"\0")
    sys.stdout.buffer.flush()
except Exception:
    sys.stderr.write("Error: malformed DATABASE_URL.\n")
    sys.exit(1)
'
  )

  if [[ "$PARSER_STATUS" != "PARSE_SUCCESS_V1" ]]; then
    echo "Error: Failed to parse database URL (invalid scheme or malformed URL)." >&2
    exit 1
  fi

  [[ -n "$PARSED_HOST" ]] && export PGHOST="$PARSED_HOST"
  [[ -n "$PARSED_PORT" ]] && export PGPORT="$PARSED_PORT"
  [[ -n "$PARSED_USER" ]] && export PGUSER="$PARSED_USER"
  [[ -n "$PARSED_PASS" ]] && export PGPASSWORD="$PARSED_PASS"
  if [[ -z "$DB_NAME" && -n "$PARSED_DB" ]]; then
    DB_NAME="$PARSED_DB"
  fi
fi

if [[ -z "$DB_NAME" ]]; then
  if [[ -n "${PGDATABASE:-}" ]]; then
    DB_NAME="$PGDATABASE"
  else
    echo "Error: Database name is required (via argument, --db, --url, or PGDATABASE)." >&2
    usage
  fi
fi

if [[ ! "$DB_NAME" =~ ^[a-zA-Z0-9_]+$ ]]; then
  echo "Error: Database name '$DB_NAME' is invalid (must contain only alphanumeric characters and underscores)." >&2
  exit 1
fi

# Set default output directory
OUTPUT_DIR="${OUTPUT_DIR:-$ROOT/backups}"
mkdir -p "$OUTPUT_DIR"

# Verify source database exists before attempting backup
EXISTS="$("$PYTHON" -c "
import subprocess, sys
db = sys.argv[1].replace(\"'\", \"''\")
try:
    res = subprocess.run(
        ['psql', '-d', 'postgres', '-t', '-A', '-c', f\"SELECT 1 FROM pg_database WHERE datname = '{db}';\"],
        capture_output=True, text=True, check=True
    )
    print(res.stdout.strip())
except subprocess.CalledProcessError as e:
    sys.stderr.write(f\"Error checking database existence: {e.stderr.strip()}\\n\")
    sys.exit(1)
except Exception as e:
    sys.stderr.write(f\"Error: {e}\\n\")
    sys.exit(1)
" "$DB_NAME")"

if [[ "$EXISTS" != "1" ]]; then
  echo "Error: Database '$DB_NAME' does not exist." >&2
  exit 1
fi

TIMESTAMP="$(date -u +"%Y%m%d_%H%M%SZ")"
BASE_NAME="${DB_NAME}_${TIMESTAMP}"
DUMP_FILE="${OUTPUT_DIR}/${BASE_NAME}.dump"
SHA_FILE="${OUTPUT_DIR}/${BASE_NAME}.sha256"
META_FILE="${OUTPUT_DIR}/${BASE_NAME}.meta.json"

# Fail-safe cleanup: remove incomplete artifacts if any error occurs
cleanup_on_error() {
  local exit_code=$?
  if [[ $exit_code -ne 0 ]]; then
    echo "Backup failed with exit code $exit_code. Cleaning up incomplete artifacts..." >&2
    rm -f "$DUMP_FILE" "$SHA_FILE" "$META_FILE"
  fi
}
trap cleanup_on_error EXIT

echo "Starting backup of '$DB_NAME' at $TIMESTAMP (UTC)..."

# 1. Run pg_dump in Custom format (-Fc)
pg_dump -Fc -f "$DUMP_FILE" "$DB_NAME"
chmod 600 "$DUMP_FILE"

# 2. Compute SHA-256 checksum
compute_sha256() {
  local target="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$target"
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$target"
  else
    "$PYTHON" -c "
import hashlib, sys
h = hashlib.sha256()
with open(sys.argv[1], 'rb') as f:
    for chunk in iter(lambda: f.read(65536), b''):
        h.update(chunk)
print(f'{h.hexdigest()}  {sys.argv[1]}')
" "$target"
  fi
}

# Write sha256 relative to output dir for clean portable verification
(cd "$OUTPUT_DIR" && compute_sha256 "$(basename "$DUMP_FILE")" > "$(basename "$SHA_FILE")")
chmod 600 "$SHA_FILE"

SHA256_HEX="$(cut -d' ' -f1 < "$SHA_FILE")"
SIZE_BYTES="$(wc -c < "$DUMP_FILE" | tr -d ' ')"
PG_DUMP_VER="$(pg_dump --version | head -n 1)"

# 3. Read current Alembic version from the database if table exists
ALEMBIC_VER="$("$PYTHON" -c "
import subprocess, sys
db = sys.argv[1]
try:
    res = subprocess.run(
        ['psql', '-d', db, '-t', '-A', '-c', 'SELECT version_num FROM alembic_version LIMIT 1;'],
        capture_output=True, text=True
    )
    if res.returncode == 0:
        print(res.stdout.strip())
except Exception:
    pass
" "$DB_NAME")"

# 4. Generate metadata JSON
"$PYTHON" -c "
import json, sys
data = {
    'schema': 'fire-control.backup-metadata/v1',
    'database_name': sys.argv[1],
    'timestamp_utc': sys.argv[2],
    'dump_format': 'custom',
    'pg_dump_version': sys.argv[3],
    'size_bytes': int(sys.argv[4]),
    'sha256': sys.argv[5],
    'alembic_version': sys.argv[6] if sys.argv[6] else None,
}
with open(sys.argv[7], 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)
" "$DB_NAME" "$TIMESTAMP" "$PG_DUMP_VER" "$SIZE_BYTES" "$SHA256_HEX" "$ALEMBIC_VER" "$META_FILE"
chmod 600 "$META_FILE"

# Disarm error trap on success
trap - EXIT

echo "Backup completed successfully:"
echo "  Dump:     $DUMP_FILE"
echo "  Checksum: $SHA_FILE ($SHA256_HEX)"
echo "  Metadata: $META_FILE"
exit 0

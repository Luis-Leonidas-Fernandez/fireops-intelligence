#!/usr/bin/env bash
# ==============================================================================
# scripts/create_production_transfer_bundle.sh
# Creates an authenticated, portable PostgreSQL production transfer bundle.
# Generates custom dump (-Fc), universal plain SQL, SHA-256 checksums, and manifest.
# ==============================================================================
set -euo pipefail

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
  -d, --db NAME          Database to export (default: fireassets)
  -o, --output-dir DIR   Output directory for the bundle (default: ./backups/transfer)
  --url DATABASE_URL     Database URL (postgresql:// or postgresql+asyncpg://)
  -h, --help             Show this help message and exit
EOF
  exit 1
}

DB_NAME="fireassets"
OUTPUT_DIR="$ROOT/backups/transfer"
DB_URL=""

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
      if [[ -z "$DB_NAME" || "$DB_NAME" == "fireassets" ]]; then
        DB_NAME="$1"
      elif [[ "$OUTPUT_DIR" == "$ROOT/backups/transfer" ]]; then
        OUTPUT_DIR="$1"
      else
        echo "Unexpected argument: $1" >&2
        usage
      fi
      shift
      ;;
  esac
done

if [[ ! "$DB_NAME" =~ ^[a-zA-Z0-9_]+$ ]]; then
  echo "Error: Invalid database name '$DB_NAME'." >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"

# Verify source database exists
EXISTS="$("$PYTHON" -c "
import subprocess, sys
db = sys.argv[1].replace(\"'\", \"''\")
try:
    res = subprocess.run(
        ['psql', '-d', 'postgres', '-t', '-A', '-c', f\"SELECT 1 FROM pg_database WHERE datname = '{db}';\"],
        capture_output=True, text=True, check=True
    )
    print(res.stdout.strip())
except Exception as e:
    sys.stderr.write(f'Database check error: {e}\\n')
    sys.exit(1)
" "$DB_NAME")"

if [[ "$EXISTS" != "1" ]]; then
  echo "Error: Database '$DB_NAME' does not exist." >&2
  exit 1
fi

TIMESTAMP="$(date -u +"%Y%m%d_%H%M%SZ")"
BUNDLE_ID="${DB_NAME}_bundle_${TIMESTAMP}"
DUMP_FILE="${OUTPUT_DIR}/${BUNDLE_ID}.dump"
SQL_FILE="${OUTPUT_DIR}/${BUNDLE_ID}.sql"
DUMP_SHA_FILE="${OUTPUT_DIR}/${BUNDLE_ID}.dump.sha256"
SQL_SHA_FILE="${OUTPUT_DIR}/${BUNDLE_ID}.sql.sha256"
MANIFEST_FILE="${OUTPUT_DIR}/${BUNDLE_ID}.manifest.json"

cleanup_on_error() {
  local exit_code=$?
  if [[ $exit_code -ne 0 ]]; then
    echo "Bundle creation failed (exit code $exit_code). Cleaning up partial files..." >&2
    rm -f "$DUMP_FILE" "$SQL_FILE" "$DUMP_SHA_FILE" "$SQL_SHA_FILE" "$MANIFEST_FILE"
  fi
}
trap cleanup_on_error EXIT

echo "=== Creating Transfer Bundle for '$DB_NAME' at $TIMESTAMP (UTC) ==="

# 1. Inspect source database and extract metadata in memory
METADATA_JSON="$("$PYTHON" -c "
import asyncio, asyncpg, json, sys

async def inspect():
    db = sys.argv[1]
    conn = await asyncpg.connect(database=db)
    try:
        # Alembic revision
        alembic_rev = await conn.fetchval('SELECT version_num FROM alembic_version LIMIT 1;')

        # Tables and exact row counts
        tables = await conn.fetch(\"\"\"
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name;
        \"\"\")
        table_counts = {}
        for t in tables:
            cnt = await conn.fetchval(f\"SELECT count(*) FROM {t['table_name']};\")
            table_counts[t['table_name']] = cnt

        # Sequences and last values
        seqs = await conn.fetch(\"\"\"
            SELECT sequencename, last_value FROM pg_sequences
            WHERE schemaname = 'public' ORDER BY sequencename;
        \"\"\")
        sequences = {s['sequencename']: s['last_value'] for s in seqs}

        # Admin user check
        admin = await conn.fetchrow(\"\"\"
            SELECT u.id, u.email, u.activo, u.password_hash IS NULL AS pwd_null,
                   r.nombre AS rol_nombre, r.activo AS rol_activo,
                   left(u.google_sub, 4) || '...' || right(u.google_sub, 4) AS masked_sub,
                   length(u.google_sub) as sub_len
            FROM usuarios u
            JOIN roles r ON r.id = u.rol_id
            WHERE u.email = 'fernandezluis303@gmail.com';
        \"\"\")

        admin_data = None
        if admin:
            admin_data = {
                'id': admin['id'],
                'email': admin['email'],
                'rol': admin['rol_nombre'],
                'activo': admin['activo'],
                'password_hash_null': admin['pwd_null'],
                'google_sub_masked': admin['masked_sub'],
                'google_sub_length': admin['sub_len'],
            }

        data = {
            'alembic_head': alembic_rev,
            'tables': table_counts,
            'sequences': sequences,
            'admin_identity': admin_data,
        }
        print(json.dumps(data))
    finally:
        await conn.close()

asyncio.run(inspect())
" "$DB_NAME")"

# 2. Generate Custom format dump (-Fc)
echo "1. Generating Custom format dump (-Fc)..."
pg_dump -Fc -f "$DUMP_FILE" "$DB_NAME"
chmod 600 "$DUMP_FILE"

# Verify TOC of custom dump
echo "   Verifying Custom dump TOC..."
pg_restore -l "$DUMP_FILE" >/dev/null

# 3. Generate plain SQL dump (universal cross-version fallback)
echo "2. Generating Plain SQL dump (cross-version compatibility)..."
pg_dump --format=plain --no-owner --no-privileges -f "$SQL_FILE" "$DB_NAME"
chmod 600 "$SQL_FILE"

# 4. Compute SHA-256 checksums
echo "3. Computing SHA-256 checksums..."
compute_sha256() {
  local target="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$target" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$target" | awk '{print $1}'
  else
    "$PYTHON" -c "
import hashlib, sys
h = hashlib.sha256()
with open(sys.argv[1], 'rb') as f:
    for chunk in iter(lambda: f.read(65536), b''):
        h.update(chunk)
print(h.hexdigest())
" "$target"
  fi
}

DUMP_SHA="$(compute_sha256 "$DUMP_FILE")"
SQL_SHA="$(compute_sha256 "$SQL_FILE")"

echo "$DUMP_SHA  $(basename "$DUMP_FILE")" > "$DUMP_SHA_FILE"
echo "$SQL_SHA  $(basename "$SQL_FILE")" > "$SQL_SHA_FILE"
chmod 600 "$DUMP_SHA_FILE" "$SQL_SHA_FILE"

DUMP_SIZE="$(wc -c < "$DUMP_FILE" | tr -d ' ')"
SQL_SIZE="$(wc -c < "$SQL_FILE" | tr -d ' ')"
PG_DUMP_VER="$(pg_dump --version | head -n 1)"

# 5. Build structured manifest
echo "4. Generating Transfer Manifest..."
"$PYTHON" -c "
import json, sys

base_meta = json.loads(sys.argv[1])
manifest = {
    'schema': 'fire-control.transfer-bundle/v1',
    'bundle_id': sys.argv[2],
    'source_database': sys.argv[3],
    'timestamp_utc': sys.argv[4],
    'pg_dump_version': sys.argv[5],
    'alembic_head': base_meta.get('alembic_head'),
    'files': {
        'dump': {
            'filename': sys.argv[6],
            'size_bytes': int(sys.argv[7]),
            'sha256': sys.argv[8],
            'format': 'custom (-Fc)',
            'recommended_for': 'PostgreSQL >= 18 on target VPS',
        },
        'sql': {
            'filename': sys.argv[9],
            'size_bytes': int(sys.argv[10]),
            'sha256': sys.argv[11],
            'format': 'plain SQL script',
            'recommended_for': 'PostgreSQL 14, 15, 16, 17, 18 on target VPS',
        }
    },
    'tables': base_meta.get('tables', {}),
    'sequences': base_meta.get('sequences', {}),
    'admin_identity': base_meta.get('admin_identity'),
    'compatibility': {
        'source_postgresql_version': '18.4',
        'custom_dump_min_pg_restore': '18.0',
        'sql_supported_versions': '>= 14.0',
        'required_extensions': ['plpgsql'],
        'required_encoding': 'UTF8',
        'portability_flags_used': ['--no-owner', '--no-privileges'],
    }
}

with open(sys.argv[12], 'w', encoding='utf-8') as f:
    json.dump(manifest, f, indent=2)
" "$METADATA_JSON" "$BUNDLE_ID" "$DB_NAME" "$TIMESTAMP" "$PG_DUMP_VER" \
  "$(basename "$DUMP_FILE")" "$DUMP_SIZE" "$DUMP_SHA" \
  "$(basename "$SQL_FILE")" "$SQL_SIZE" "$SQL_SHA" \
  "$MANIFEST_FILE"
chmod 600 "$MANIFEST_FILE"

# Disarm trap
trap - EXIT

echo "=== Transfer Bundle Created Successfully ==="
echo "Bundle ID: $BUNDLE_ID"
echo "Directory: $OUTPUT_DIR"
echo "Artifacts:"
echo "  - Custom Dump: $(basename "$DUMP_FILE") ($DUMP_SIZE bytes, SHA: $DUMP_SHA)"
echo "  - Plain SQL:   $(basename "$SQL_FILE") ($SQL_SIZE bytes, SHA: $SQL_SHA)"
echo "  - Manifest:    $(basename "$MANIFEST_FILE")"
exit 0

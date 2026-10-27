#!/bin/sh
# ==============================================================================
# deploy/postgres/init-db.sh
# Inicializador automático para PostgreSQL en primer arranque (entrypoint initdb).
# Ejecutado como el superusuario administrativo ($POSTGRES_USER).
#
# SEGURIDAD CONTRA INYECCIÓN SQL:
# - Evita interpolación bash de variables en comandos SQL mediante delimitador
#   de here-doc entrecomillado ('EOSQL').
# - Pasa nombres y contraseñas a través de parámetros tipados de psql (-v).
# - Utiliza format(%I, %L) y \gexec para escapar identificadores y literales.
#
# PRIVILEGIOS MÍNIMOS:
# - Crea el rol 'fireops_app' con atributos restrictivos (NOSUPERUSER, NOCREATEDB).
# - Revoca CONNECT sobre la base 'postgres' de PUBLIC.
# - NO pre-crea la base 'fireassets' para evitar colisiones con staging.
# ==============================================================================
set -eu

echo "=== [init-db.sh] Provisionando rol de aplicación con formato seguro y privilegios mínimos ==="

# Provisionar rol de aplicación usando parámetros de psql y format() con %I (identificador) y %L (literal)
# para prevenir inyección SQL ante caracteres especiales en contraseñas o nombres de usuario.
psql -v ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    -v app_user="$FIREOPS_APP_USER" \
    -v app_pass="$FIREOPS_APP_PASSWORD" \
    -v admin_user="$POSTGRES_USER" \
    <<-'EOSQL'
    -- Crear rol con identificador %I y contraseña %L de forma segura si no existe
    SELECT format(
        'CREATE USER %I WITH ENCRYPTED PASSWORD %L NOSUPERUSER INHERIT NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS',
        :'app_user',
        :'app_pass'
    )
    WHERE NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = :'app_user'
    ) \gexec

    -- Revocar permisos públicos de conexión sobre la base administrativa 'postgres'
    REVOKE CONNECT ON DATABASE postgres FROM PUBLIC;

    -- Conceder conexión al superusuario administrativo mediante identificador seguro
    SELECT format('GRANT CONNECT ON DATABASE postgres TO %I', :'admin_user') \gexec
EOSQL

echo "=== [init-db.sh] Configuración de roles completada exitosamente ==="

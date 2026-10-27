#!/usr/bin/env bash
# ==============================================================================
# deploy/postgres/preflight_check.sh
# Verificación no destructiva previa al despliegue de PostgreSQL 18 en el VPS.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ERRORS=0
WARNINGS=0

echo "=== [PREFLIGHT] Comprobaciones previas para PostgreSQL 18 en VPS ==="

# 1. Comprobar Docker
if command -v docker >/dev/null 2>&1; then
    if docker info >/dev/null 2>&1; then
        echo "✅ [DOCKER] Daemon Docker está activo y accesible."
    else
        echo "❌ [DOCKER] Daemon Docker no responde o faltan permisos."
        ERRORS=$((ERRORS + 1))
    fi
else
    echo "❌ [DOCKER] Binario 'docker' no encontrado en el sistema."
    ERRORS=$((ERRORS + 1))
fi

# 2. Comprobar Docker Compose v2
if docker compose version >/dev/null 2>&1; then
    COMPOSE_VER="$(docker compose version --short 2>/dev/null || docker compose version)"
    echo "✅ [COMPOSE] Docker Compose v2 detectado ($COMPOSE_VER)."
else
    echo "❌ [COMPOSE] 'docker compose' (plugin v2) no encontrado."
    ERRORS=$((ERRORS + 1))
fi

# 3. Comprobar que el puerto 5432 esté libre en el host
PORT_OCCUPIED=0
if command -v ss >/dev/null 2>&1; then
    if ss -tulpn | grep -q ":5432 "; then
        PORT_OCCUPIED=1
    fi
elif command -v netstat >/dev/null 2>&1; then
    if netstat -tlpn | grep -q ":5432 "; then
        PORT_OCCUPIED=1
    fi
fi

if [[ $PORT_OCCUPIED -eq 1 ]]; then
    echo "❌ [PUERTO] El puerto 5432 ya se encuentra ocupado por otro proceso."
    ERRORS=$((ERRORS + 1))
else
    echo "✅ [PUERTO] Puerto 5432 libre para enlace exclusivo a loopback."
fi

# 4. Comprobar colisión de nombres de contenedores
if docker ps -a --format '{{.Names}}' | grep -Eq '^fireassets-postgres$'; then
    echo "⚠️ [CONTENEDOR] Ya existe un contenedor llamado 'fireassets-postgres'."
    WARNINGS=$((WARNINGS + 1))
else
    echo "✅ [CONTENEDOR] Nombre 'fireassets-postgres' libre."
fi

# 5. Comprobar colisión de volumen
if docker volume ls --format '{{.Name}}' | grep -Eq '^fireassets_pgdata$'; then
    echo "⚠️ [VOLUMEN] El volumen 'fireassets_pgdata' ya existe previamente."
    WARNINGS=$((WARNINGS + 1))
else
    echo "✅ [VOLUMEN] Volumen 'fireassets_pgdata' libre para inicialización limpia."
fi

# 6. Comprobar memoria disponible en el host (mínimo 400 MB)
AVAILABLE_RAM_MB="$(free -m | awk '/^Mem:/{print $7}')"
if [[ "$AVAILABLE_RAM_MB" -ge 400 ]]; then
    echo "✅ [MEMORIA] RAM disponible: ${AVAILABLE_RAM_MB} MB (Requisito mínimo 400 MB superado)."
else
    echo "❌ [MEMORIA] RAM disponible insuficiente: ${AVAILABLE_RAM_MB} MB (menos de 400 MB)."
    ERRORS=$((ERRORS + 1))
fi

# 7. Comprobar espacio en disco disponible (mínimo 5 GB)
AVAILABLE_DISK_GB="$(df -BG / | awk 'NR==2{print $4}' | tr -d 'G')"
if [[ "$AVAILABLE_DISK_GB" -ge 5 ]]; then
    echo "✅ [DISCO] Espacio en disco disponible: ${AVAILABLE_DISK_GB} GB (Requisito mínimo 5 GB superado)."
else
    echo "❌ [DISCO] Espacio en disco insuficiente: ${AVAILABLE_DISK_GB} GB (menos de 5 GB)."
    ERRORS=$((ERRORS + 1))
fi

# 8. Comprobar presencia y permisos de .env
ENV_FILE="${SCRIPT_DIR}/.env"
if [[ -f "$ENV_FILE" ]]; then
    ENV_PERMS="$(stat -c "%a" "$ENV_FILE" 2>/dev/null || stat -f "%Lp" "$ENV_FILE" 2>/dev/null || echo "unknown")"
    if [[ "$ENV_PERMS" == "600" || "$ENV_PERMS" == "400" ]]; then
        echo "✅ [SEGURIDAD] Archivo .env detectado con permisos seguros ($ENV_PERMS)."
    else
        echo "⚠️ [SEGURIDAD] Archivo .env detectado con permisos inseguros ($ENV_PERMS). Se recomienda: chmod 600 $ENV_FILE"
        WARNINGS=$((WARNINGS + 1))
    fi
else
    echo "❌ [SEGURIDAD] Archivo .env no encontrado. Copie .env.example como .env antes del despliegue."
    ERRORS=$((ERRORS + 1))
fi

echo "--------------------------------------------------------"
if [[ $ERRORS -eq 0 ]]; then
    echo "🎉 RESULTADO: PREFLIGHT EXITOSO ($WARNINGS advertencias)."
    echo "El servidor cumple con todos los requisitos para desplegar PostgreSQL 18."
    exit 0
else
    echo "⛔ RESULTADO: PREFLIGHT FALLIDO ($ERRORS errores, $WARNINGS advertencias)."
    echo "Corrija los bloqueos identificados antes de proceder."
    exit 1
fi

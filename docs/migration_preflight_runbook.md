# Runbook: Preflight de Migraciones Alembic y Reproducibilidad

**Proyecto:** Bomberos / fireops-intelligence  
**Fase:** H-03 Etapa C — Reproducibilidad y Preflight de Migraciones  
**Fecha:** 2026-10-25  

---

## 1. Propósito y Arquitectura

El preflight de migraciones (`scripts/preflight_migrations.py`) es una herramienta de inspección **estrictamente de solo lectura (read-only)** diseñada para ejecutarse como compuerta preventiva previa a cualquier operación de despliegue o migración en producción.

### Principios Fundamentales
1. **Zero Auto-Execution:** El preflight **nunca** ejecuta automáticamente `alembic upgrade`, `alembic downgrade` ni `alembic stamp`.
2. **Zero Modificaciones:** No emite sentencias DDL ni DML. Inspecciona exclusivamente mediante consultas `SELECT` sobre `information_schema.tables` y `alembic_version`.
3. **Manejo Seguro de Credenciales:** Enmascara cualquier secreto o contraseña presente en URLs de conexión o mensajes de error (`sanitize_dsn`).
4. **Salida Programática y Humana:** Soporta tanto reporte formateado en terminal como salida estructurada JSON (`--json`) para integración en pipelines de CI/CD.

---

## 2. Códigos de Salida y Matriz Operativa

| Código | Estado (`status`) | Significado Técnico | Acción en Despliegue |
|:---:|---|---|---|
| `0` | `SYNCED` | La base de datos coincide exactamente con el `head` del repositorio (`b3f81e7d2c94`). | Proceder con despliegue de código sin ejecutar migraciones. |
| `10` | `PENDING_MIGRATIONS` | La base se encuentra en una revisión válida anterior al `head`; existen migraciones pendientes en orden lineal. | 1. Ejecutar backup previo (`backup_db.sh`).<br>2. Aplicar migraciones controladas (`alembic upgrade head`).<br>3. Verificar post-migración. |
| `11` | `EMPTY_DATABASE` | La base de datos no tiene tablas en el esquema `public` (base nueva). | Ejecutar migración inicial completa (`alembic upgrade head`). |
| `12` | `UNVERSIONED_TABLES` | Existen tablas de dominio pero falta la tabla `alembic_version` (o está vacía). | **ABORTAR DESPLIEGUE.** Requiere inspección manual para evitar colisiones de tablas o realizar `alembic stamp`. |
| `20` | `DIVERGENT_REVISION` | La revisión en base de datos no existe en el repositorio o la historia migratoria bifurcó. | **ABORTAR DESPLIEGUE.** Riesgo crítico de corrupción o rollback de código sin downgrade de base. |
| `21` | `MULTIPLE_REPO_HEADS` | El repositorio contiene múltiples `heads` de Alembic no fusionados. | **ABORTAR CI/BUILD.** Error de desarrollo: fusionar ramas con `alembic merge`. |
| `22` | `MULTIPLE_DB_HEADS` | La tabla `alembic_version` contiene más de una fila. | **ABORTAR DESPLIEGUE.** Árbol de migraciones en base de datos bifurcado. |
| `30` | `CONNECTION_ERROR` | Fallo de conexión o autenticación con PostgreSQL (timeout, red, credenciales). | **ABORTAR DESPLIEGUE.** Verificar estado del clúster de base de datos. |
| `31` | `CONFIGURATION_ERROR` | Archivo `alembic.ini` no encontrado o URL malformada. | **ABORTAR DESPLIEGUE.** Corregir configuración del entorno. |

---

## 3. Estrategia de Reproducibilidad de Dependencias

Para garantizar builds deterministas sin incorporar gestores adicionales (como Poetry, PDM o UV) que alteren la arquitectura ni agreguen capas de abstracción innecesarias:

1. **`requirements.txt` (Desarrollo y Declaración de Intención):**
   Define intenciones de compatibilidad con rangos seguros (`fastapi==0.141.1`, `SQLAlchemy>=2.0,<2.1`, etc.).
2. **`requirements.lock` (Despliegue / Producción Determinista):**
   Lockfile fijado exactamente con el árbol completo de 55 dependencias directas y transitivas (`package==x.y.z`), capturado desde el entorno verificado con **Python 3.14.4**.
3. **Instalación determinista en CI/CD:**
   ```bash
   # En producción o contenedores (sin resolución dinámica):
   pip install --no-deps -r requirements.lock
   # O con verificación de consistencia:
   pip install -r requirements.lock
   ```
4. **Diferencia entre Fijación de Versiones y Verificación de Hashes Criptográficos:**
   - **Fijación de Versiones (`==` en `requirements.lock`):** Garantiza que todos los entornos (CI, staging, producción) instalen idénticas versiones de bibliotecas directas y subdependencias, eliminando el riesgo de *dependency drift* o roturas por releases menores no controladas.
   - **Verificación de Hashes Criptográficos (`--require-hashes`):** Mecanismo complementario de `pip` que valida los hashes SHA-256 de cada archivo `.whl` / tarball contra un manifiesto pre-firmado. Es recomendable cuando los artefactos se descargan directamente de repositorios públicos no autenticados para mitigar ataques de cadena de suministro (*supply-chain tampering*). En entornos con espejos privados o caches controlados, la fijación exacta de versiones cubre el objetivo de reproducibilidad sin el overhead de compilación de hashes multiplataforma.

---

## 4. Guía de Integración en Pipeline de Despliegue Futuro

En un despliegue futuro (Etapa D), el preflight se integra como el primer paso de verificación antes de tocar la base de datos o el servicio en ejecución.

Para operar de forma robusta en scripts bash que utilicen `set -euo pipefail`, el script debe suspender temporalmente `errexit` durante la invocación del preflight para capturar los códigos de salida de negocio (`10` para migraciones pendientes, `11` para base vacía) sin abortar prematuramente:

```bash
#!/usr/bin/env bash
# Ejemplo de pipeline seguro de despliegue futuro:

set -euo pipefail

echo "1. Ejecutando preflight de migraciones..."

# Ejecutar preflight capturando salida y código de salida sin abortar por set -e
set +e
PREFLIGHT_OUTPUT="$(./scripts/preflight_migrations.py --json 2>&1)"
PREFLIGHT_CODE=$?
set -e

# Extraer el estado del reporte JSON
PREFLIGHT_STATUS="$(echo "$PREFLIGHT_OUTPUT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', 'ERROR'))" 2>/dev/null || echo "UNKNOWN")"

case "$PREFLIGHT_CODE" in
  0)
    # SYNCED: Base de datos al día con el head
    echo "Base de datos al día ($PREFLIGHT_STATUS). Procediendo con despliegue de código..."
    ;;
  10)
    # PENDING_MIGRATIONS: Migraciones pendientes en orden lineal
    echo "Migraciones pendientes detectadas ($PREFLIGHT_STATUS). Ejecutando backup previo obligatorio..."
    ./scripts/backup_db.sh
    echo "Aplicando migraciones Alembic..."
    alembic upgrade head
    ;;
  11)
    # EMPTY_DATABASE: Base nueva sin esquema
    echo "Base de datos vacía ($PREFLIGHT_STATUS). Aplicando esquema inicial..."
    alembic upgrade head
    ;;
  *)
    # Bloqueo estricto para códigos 12, 20, 21, 22, 30, 31
    echo "BLOQUEO DE SEGURIDAD: Preflight rechazó el despliegue (Código: $PREFLIGHT_CODE, Estado: $PREFLIGHT_STATUS)." >&2
    echo "$PREFLIGHT_OUTPUT" >&2
    exit "$PREFLIGHT_CODE"
    ;;
esac
```

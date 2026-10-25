# Runbook Operativo de Producción: Despliegue, Migraciones y Recuperación ante Desastres

**Proyecto:** Bomberos / fireops-intelligence  
**Fase:** H-03 Etapa D — Readiness real, Runbook de Operaciones y Simulacro de Recuperación  
**Fecha:** 2026-10-25  
**Revisión Alembic esperada:** `b3f81e7d2c94`  
**Entorno de ejecución:** Python 3.14.4 / PostgreSQL 18.x  

---

## 1. Preparación del Despliegue

Antes de autorizar el paso de una nueva versión a producción o aplicar cualquier cambio sobre la infraestructura de base de datos, el operador debe ejecutar secuencialmente las compuertas preventivas de preparación.

### 1.1 Verificación del Entorno Python
El proyecto requiere **Python 3.14.4** para garantizar paridad estricta con los entornos de prueba y auditoría:

```bash
python3 --version
# Salida esperada: Python 3.14.4
```

### 1.2 Instalación Determinista con Lockfile
Para prevenir la introducción inadvertida de dependencias no auditadas o derivas de versiones transitivas (*dependency drift*), la instalación en servidores de producción y contenedores debe realizarse exclusivamente a partir de `requirements.lock`:

```bash
# Instalación determinista sin resolución dinámica:
pip install --no-deps -r requirements.lock

# O verificación e instalación estricta:
pip install -r requirements.lock
```

### 1.3 Verificación de Consistencia de Dependencias
Confirmar que no existen colisiones, incompatibilidades ni dependencias rotas en el entorno virtual:

```bash
pip check
# Salida esperada: No broken requirements found.
```

### 1.4 Validación de Configuración sin Exposición de Secretos
Validar que las variables obligatorias estén presentes en el entorno (`DATABASE_URL`, `SECRET_KEY`, etc.) sin volcar sus contenidos ni imprimirlos en la consola o en trazas del sistema:

```bash
python3 -c "
from app.config.settings import get_settings
s = get_settings()
print(f'Configuración OK. App: {s.app_name}, Entorno: {s.environment}, OAuth habilitado: {s.google_oauth_enabled}')
"
```
> [!IMPORTANT]
> `Settings` enmascara los secretos en sus representaciones (`repr=False`). Nunca ejecute comandos que impriman `s.database_url` o `s.secret_key` directamente en consolas, salidas estándar compartidas ni logs de despliegue.

### 1.5 Preflight de Migraciones
Ejecutar la herramienta preventiva de inspección de migraciones (`scripts/preflight_migrations.py`). Esta herramienta opera en modo **estrictamente de solo lectura (read-only)** y no realiza ninguna modificación en la base de datos:

```bash
./scripts/preflight_migrations.py --json
```

### 1.6 Comprobación de Privilegios PostgreSQL
Verificar que la conexión del servicio no opera con privilegios de superusuario (`postgres`), sino con un rol de aplicación acotado (`fireops_app`) que tenga permisos estrictamente necesarios:
- `SELECT`, `INSERT`, `UPDATE`, `DELETE` sobre tablas de dominio.
- `USAGE`, `SELECT` sobre secuencias.
- Prohibición de permisos de `DROP DATABASE`, `ALTER SYSTEM` o `SUPERUSER`.

---

## 2. Migraciones Controladas

### 2.1 Matriz de Códigos de Salida del Preflight

El script `scripts/preflight_migrations.py` emite códigos de salida deterministas que rigen la compuerta de despliegue:

| Código | Estado (`status`) | Significado Operativo | Acción Automatizada / Humana |
|:---:|---|---|---|
| `0` | `SYNCED` | Base de datos sincronizada con el `head` del repositorio (`b3f81e7d2c94`). | **CONTINUAR:** Proceder con el despliegue del servicio web sin ejecutar migraciones. |
| `10` | `PENDING_MIGRATIONS` | Base de datos en una revisión anterior válida. Migraciones pendientes en orden lineal. | **BLOQUEAR ARRANQUE NORMAL:**<br>1. Ejecutar backup previo obligatorio (`scripts/backup_db.sh`).<br>2. Aplicar migraciones explícitas (`alembic upgrade head`).<br>3. Re-verificar preflight.<br>4. Iniciar servicio. |
| `11` | `EMPTY_DATABASE` | Base de datos vacía (sin tablas en esquema `public`). | **BLOQUEAR ARRANQUE NORMAL:** Aplicar esquema inicial completo con `alembic upgrade head`. |
| `12` | `UNVERSIONED_TABLES` | Existen tablas pero la tabla `alembic_version` no existe o está vacía. | **ABORTAR INMEDIATAMENTE:** Riesgo de colisión de esquema. Requiere inspección manual del DBA antes de continuar. |
| `20` | `DIVERGENT_REVISION` | La revisión en la base no pertenece al árbol de migraciones del repositorio. | **ABORTAR INMEDIATAMENTE:** Base corrupta o código desfasado respecto a migraciones aplicadas. |
| `21` | `MULTIPLE_REPO_HEADS` | El repositorio contiene ramas concurrentes de migración no fusionadas. | **ABORTAR CI/BUILD:** Error de código; fusionar con `alembic merge`. |
| `22` | `MULTIPLE_DB_HEADS` | La tabla `alembic_version` contiene múltiples filas (bifurcación en BD). | **ABORTAR INMEDIATAMENTE:** Base de datos bifurcada. Requiere reconciliación manual. |
| `30` | `CONNECTION_ERROR` | Fallo de conexión o autenticación con PostgreSQL (timeout, red, credenciales). | **ABORTAR INMEDIATAMENTE:** Comprobar conectividad, puerto 5432 y servicio PostgreSQL. |
| `31` | `CONFIGURATION_ERROR` | `alembic.ini` inexistente o URL de base de datos malformada. | **ABORTAR INMEDIATAMENTE:** Corregir configuración de entorno. |

### 2.2 Procedimiento de Migración Segura
Cuando el preflight retorne el código `10`, el operador o pipeline debe ejecutar la siguiente secuencia sin omitir ningún paso:

```bash
#!/usr/bin/env bash
set -euo pipefail

# 1. Suspender errexit para capturar el código de preflight sin abortar
set +e
PREFLIGHT_RAW="$(./scripts/preflight_migrations.py --json 2>&1)"
PREFLIGHT_CODE=$?
set -e

if [ "$PREFLIGHT_CODE" -eq 0 ]; then
    echo "Base de datos al día. No se requieren migraciones."
elif [ "$PREFLIGHT_CODE" -eq 10 ]; then
    echo "Migraciones pendientes detectadas. Iniciando protocolo de migración segura..."
    
    # PASO A: Backup preventivo obligatorio
    echo "Generando backup preventivo..."
    BACKUP_OUT="$(./scripts/backup_db.sh)"
    echo "$BACKUP_OUT"
    
    # PASO B: Ejecución explícitamente autorizada de Alembic
    echo "Aplicando migraciones hacia head..."
    alembic upgrade head
    
    # PASO C: Verificación posterior del esquema
    echo "Verificando esquema post-migración..."
    ./scripts/preflight_migrations.py --json
    echo "Migración completada y verificada exitosamente."
elif [ "$PREFLIGHT_CODE" -eq 11 ]; then
    echo "Base de datos vacía. Creando esquema inicial..."
    alembic upgrade head
    ./scripts/preflight_migrations.py --json
else
    echo "ERROR CRÍTICO: Preflight bloqueó el despliegue con código $PREFLIGHT_CODE" >&2
    exit "$PREFLIGHT_CODE"
fi
```

### 2.3 Habilitación de Tráfico tras Verificación de Readiness
Una vez aplicado el cambio y arrancado el contenedor de la aplicación, el enrutador / balanceador de carga no debe dirigir tráfico de usuarios hasta que el endpoint de readiness confirme estado operativo:

```bash
curl -f -s http://127.0.0.1:8000/health/ready
# Respuesta HTTP 200: {"status": "ready", "database": "connected"}
```

---

## 3. Recuperación ante Desastres (Disaster Recovery)

### 3.1 Identificación y Contención del Incidente
Ante indicios de corrupción lógica de datos, borrado accidental de registros o falla catastrófica de esquema:
1. **Aislar de inmediato la base afectada:** Cortar el tráfico de usuarios apagando las instancias web o configurando el balanceador en modo mantenimiento (*HTTP 503 Maintenance*).
2. **Prevenir escrituras divergentes:** Establecer la base de datos en modo de solo lectura para evitar que nuevas transacciones se mezclen con el estado comprometido:
   ```sql
   ALTER DATABASE fireassets SET default_transaction_read_only = on;
   ```
3. **Preservar la base afectada:** Nunca sobrescribir ni eliminar la base comprometida; su contenido es indispensable para la extracción forense y el rescate de datos en vuelo (*post-backup writes*).

### 3.2 Selección y Validación del Backup
1. Identificar el archivo de backup más reciente en el almacenamiento local o repositorio de réplicas:
   ```bash
   ls -la backups/
   ```
2. Confirmar la existencia de los tres artefactos indivisibles del backup:
   - Archivo de volcado binario: `backup_<db>_<timestamp>.dump`
   - Manifiesto de auditoría: `backup_<db>_<timestamp>.json`
   - Suma criptográfica de integridad: `backup_<db>_<timestamp>.sha256`
3. Verificar la integridad de los artefactos antes de restaurar:
   ```bash
   # La verificación SHA-256 es ejecutada automáticamente por restore_db.sh,
   # pero puede comprobarse manualmente con:
   shasum -a 256 -c backups/backup_<db>_<timestamp>.sha256
   ```

### 3.3 Restauración Exclusivamente Fuera de Lugar (Out-of-Place Restore)
> [!CAUTION]
> **REGLA DE ORO DE RECUPERACIÓN:** Queda terminantemente prohibido restaurar un backup sobre una base de datos preexistente (`fireassets`, `fireassets_test`, etc.). Toda restauración debe realizarse en una base nueva, aislada y con nombre unívoco (por ejemplo: `fireassets_recovered_20261025`).

El script `scripts/restore_db.sh` implementa guardas activas que rechazan expresamente cualquier intento de restauración sobre bases existentes o nombres protegidos:

```bash
./scripts/restore_db.sh backups/backup_fireassets_20261025T120000Z.dump fireassets_recovered_20261025
```

### 3.4 Verificación Profunda Post-Restauración
Una vez completada la restauración por `pg_restore`, es obligatorio validar la integridad estructural y relacional de la base restaurada utilizando `scripts/verify_restored_db.py`:

```bash
./scripts/verify_restored_db.py fireassets_recovered_20261025 \
  --meta backups/backup_fireassets_20261025T120000Z.json \
  --json
```
La herramienta verifica:
- Existencia y accesibilidad de todas las tablas catalogadas en el manifiesto.
- Conteo de registros idéntico al momento del backup.
- Estado y validez de las secuencias PostgreSQL.
- Presencia activa de constraints y llaves foráneas.
- Presencia activa y funcional de los triggers de concurrencia H-01 (prevención de ciclos de contención de inventario con lock consultivo).
- Consistencia de la revisión de `alembic_version`.

### 3.5 Tratamiento de Escrituras Posteriores al Backup (Post-Backup Writes)
Cualquier restauración a partir de un backup previo introduce una pérdida potencial de transacciones correspondiente a la ventana entre la hora del volcado y el momento del incidente:

> [!WARNING]
> La restauración directa de un backup NO contiene las escrituras efectuadas entre el momento de generación del volcado y el incidente. Omitir este análisis provocará **pérdida silenciosa de datos (silent data loss)**.

**Procedimiento de Rescate de Transacciones en Vuelo:**
1. Conectar en modo de solo lectura a la base original comprometida (`fireassets`).
2. Consultar la tabla de auditoría `auditoria_cambios` para identificar todas las operaciones registradas con posterioridad al timestamp del backup:
   ```sql
   SELECT entidad_tipo, entidad_id, accion, realizado_por_usuario_id, fecha
   FROM auditoria_cambios
   WHERE fecha > '2026-10-25T12:00:00Z'
   ORDER BY fecha ASC;
   ```
3. Exportar las filas delta de inventario, usuarios y cambios de estado generadas durante ese lapso.
4. Diseñar y ejecutar un script controlado de reconciliación que inserte/actualice dichos registros en `fireassets_recovered_20261025`.
5. Si no existen registros de auditoría suficientes para ciertas transacciones, documentar las transacciones pendientes para comunicación operativa a las dotaciones de bomberos afectadas.

### 3.6 Cambio Controlado de Tráfico (Switchover)
Una vez verificada la base restaurada y completado el rescate de escrituras:
1. Actualizar la variable `DATABASE_URL` en la configuración de la aplicación (o archivo `.env` del servidor):
   ```bash
   DATABASE_URL="postgresql+asyncpg://fireops_app:SECRETO@localhost:5432/fireassets_recovered_20261025"
   ```
2. Iniciar el servicio web FastAPI.
3. Consultar `/health/ready` para confirmar que la aplicación reconoce la base y la marca como operativa:
   ```bash
   curl -s http://localhost:8000/health/ready
   # {"status": "ready", "database": "connected"}
   ```
4. Reabrir el tráfico en el balanceador de carga hacia la nueva base restaurada.

### 3.7 Plan de Reversión Operativa ante Fallos
Si durante el cambio de tráfico se detectan anomalías funcionales en `fireassets_recovered_20261025`:
1. Desviar inmediatamente el tráfico de vuelta a la página de mantenimiento.
2. Mantener la base original aislada (sin modificar) y la base recuperada para diagnóstico forense.
3. Repetir la restauración en una nueva base temporal para aislar problemas de datos o inconsistencias de secuencias.

### 3.8 Prohibición Expresa de `alembic downgrade` como Rollback en Producción
> [!CAUTION]
> **PROHIBICIÓN ESTRICTA:** Queda expresamente prohibido el uso de `alembic downgrade` como mecanismo automatizado o rutinario de reversión (*rollback*) en producción.

**Justificación Técnica:**
- Los downgrades de base de datos son operaciones destructivas que típicamente ejecutan `DROP COLUMN`, `DROP TABLE` o eliminación de constraints.
- Si una migración agregó una columna y los usuarios ya guardaron datos en ella, un `downgrade` destruirá irreversiblemente esos datos sin posibilidad de recuperación por software.
- Si una migración falló a mitad de camino o dejó un esquema incompatible, la estrategia aprobada de rollback consiste en:
  1. Mantener el código anterior en ejecución.
  2. Restaurar el backup fuera de lugar tomado antes de iniciar la migración.
  3. Apuntar el tráfico a la base restaurada.
  4. Analizar la migración en un entorno de pruebas aislado antes de reintentar.

---

## 4. Seguridad y Continuidad Operativa

### 4.1 Principio de Privilegios Mínimos
La base de datos PostgreSQL debe contar con segregación estricta de roles:
- **`fireops_app` (Rol de Aplicación):** Conexión de FastAPI en tiempo de ejecución. Permisos exclusivos de `SELECT`, `INSERT`, `UPDATE`, `DELETE` en tablas públicas. Sin permisos DDL ni acceso al catálogo de administración.
- **`fireops_migrator` (Rol de Migración):** Utilizado exclusivamente durante el preflight y la ejecución de `alembic upgrade`. Permisos DDL acotados sobre el esquema `public`. Sin privilegios de superusuario.
- **`postgres` / DBA:** Utilizado únicamente para tareas de backup, creación de bases efímeras o restauración fuera de lugar.

### 4.2 Protección del Ciclo de Vida de `PGPASSWORD`
1. Ningún script ni comando operativo debe aceptar o transmitir contraseñas como argumentos de línea de comandos (evitando su exposición en `ps aux`, `/proc` o trazas de auditoría del sistema operativo).
2. Las variables `PGPASSWORD` exportadas en subprocesos deben tener un ámbito de vida efímero y ser desasignadas (`unset PGPASSWORD`) inmediatamente después de concluir la invocación del comando cliente de PostgreSQL.
3. Los scripts de backup y restore utilizan tuberías de streaming seguras (vía `sys.stdin` delimitadas por `NUL` en Python) para transformar cadenas `DATABASE_URL` en variables de entorno sin exponerlas en logs de shell ni archivos temporales.

### 4.3 Autenticidad de Backups y Límites del SHA-256
> [!IMPORTANT]
> El archivo `.sha256` garantiza **integridad** (detección de corrupción accidental por disco, red o volcados truncados), **NO autenticidad criptográfica ni no-repudio**.
>
> Un hash SHA-256 no impide que un atacante con acceso al sistema de archivos modifique el volcado `.dump` y regenere un nuevo archivo `.sha256` coincidente.

**Evolución hacia Autenticación Criptográfica:**
En fases futuras, los artefactos de backup deberán ser firmados digitalmente mediante claves asimétricas (GPG / ed25519) o sellados mediante mecanismos de custodia de claves gestionados (KMS / HashiCorp Vault) antes de su transferencia a almacenamiento secundario.

### 4.4 Estrategia de Almacenamiento Externo y Resiliencia
- **Almacenamiento Local Efímero:** Los volcados generados por `scripts/backup_db.sh` residen inicialmente en el directorio `backups/` del host local con permisos restrictivos (`chmod 600` para volcados, `chmod 700` para el directorio).
- **Estrategia Futura Offsite:** Para mitigar la pérdida total del servidor o centro de datos, se debe implementar una sincronización hacia almacenamiento de objetos inmutable con política WORM (*Write Once, Read Many*) y bloqueo de retención (ejemplo: AWS S3 Object Lock o GCS Bucket Retention Policy).
- **Declaración de Estado Actual:** A la fecha de este runbook, el almacenamiento offsite inmutable **no está implementado ni autorizado**. No se debe asumir la existencia de réplicas externas ni recuperación geográfica hasta que la infraestructura correspondiente sea aprovisionada y validada.

### 4.5 Objetivos de Recuperación: RPO y RTO (Descargo Operativo)
- **RPO Objetivo (Recovery Point Objective):** < 1 hora (mediante backups programados periódicos o replicación WAL continua en fases futuras).
- **RTO Objetivo (Recovery Time Objective):** < 30 minutos (para bases de datos de escala operativa habitual de cuarteles de bomberos, < 500 MB).

> [!CAUTION]
> **DESCARGO DE RESPONSABILIDAD (DISCLAIMER):**
> Los tiempos de backup (ej. ~150 ms) y restauración (ej. ~250 ms) registrados durante los simulacros corresponden a **bases sintéticas efímeras de prueba**.
>
> **Bajo ninguna circunstancia estos tiempos constituyen una garantía de SLA de producción.** El RTO y RPO reales en producción dependerán de:
> 1. El volumen real de la base de datos (gigabytes vs megabytes).
> 2. El rendimiento de I/O del disco y almacenamiento subyacente.
> 3. El tiempo de transferencia de red si el backup proviene de un repositorio externo.
> 4. El tiempo humano de diagnóstico forense y rescate de escrituras posteriores (*post-backup writes*).

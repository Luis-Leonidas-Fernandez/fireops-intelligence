# Diagnosticar el acceso con Google sin migrar la base equivocada

**Objetivo de la clase:** hacer que la aplicación ya funcional use la base local correcta, `fireassets_test`, y volver a probar Google antes de atribuirle el fallo a OAuth. Cada integrante conserva su checkout y su rama: Git comparte los archivos de migración, pero no las tablas ni los datos de PostgreSQL.

> **Regla de seguridad:** los pasos de diagnóstico de esta guía son de solo lectura. Ejecutar `alembic upgrade head` únicamente después de confirmar `fireassets_test` en el archivo, en la configuración efectiva **y en la conexión real**. Si alguna comprobación difiere, detenerse. No ejecutar estos pasos sobre `fireassets` ni una base remota.

## Checklist para la clase: conservar lo que ya funciona

1. **Detener el Uvicorn anterior** (`Ctrl+C`). No usar su respuesta para diagnosticar el nuevo intento: puede conservar otra configuración.
2. **Confirmar el checkout actual**, sin cambiar de rama: desde la raíz, ejecutar `git status -sb`, `git log -1 --oneline` y listar `migrations/versions/` (`ls migrations/versions/` en macOS; `Get-ChildItem migrations/versions/` en PowerShell). Comparar la versión esperada para la clase y comprobar que están las cuatro migraciones descritas abajo. Si no coinciden, consultar al docente antes de continuar; no hacer `pull`, `reset` ni `clean` como parte de este diagnóstico.
3. **Inspeccionar `.env.test` sin mostrar secretos**: verificar que ya existe, que su `DATABASE_URL` apunta a PostgreSQL local y termina en `/fireassets_test`, y que las claves de Google y el URI de retorno están configurados. No pegar ni capturar el archivo. Confirmar que `.venv` y PostgreSQL local siguen disponibles; no recrearlos si ya funcionan.
4. **Ejecutar el preflight de solo lectura** de esta guía. Debe informar `Base conectada: fireassets_test` y mostrar la revisión y las tablas. Si falla o apunta a otra base, detenerse.
5. **Migrar solo si `fireassets_test` está atrasada** y todas las comprobaciones anteriores coinciden. Si ya está en la revisión final, no ejecutar `upgrade`.
6. **Arrancar con `test-up`**, sin un `DATABASE_URL` heredado; repetir un intento nuevo de Google y correlacionar su `attempt_id` con los eventos `google_oauth`.

No hace falta reclonar, borrar `fireassets`, recrear `.env.test` ni crear otra base para seguir esta ruta. Si falta alguno de esos componentes, salir de la ruta de diagnóstico y consultar las guías de instalación al final de la sección siguiente.

## 1. Separar rama, base local y flujo de Google

| Capa | Qué confirma | Qué no confirma |
|---|---|---|
| Git | La rama y el commit contienen el código y las migraciones esperadas. Los compañeros pueden trabajar en ramas distintas sin hacer push a `main`. | No dice qué base local usa el proceso ni aplica migraciones. |
| PostgreSQL | El preflight confirma la conexión efectiva a `fireassets_test`, su esquema y revisión Alembic. | No demuestra que un Uvicorn anterior usara esa misma base. |
| Google OAuth | Los eventos de un `attempt_id` muestran si falló el inicio, callback, token, identidad o cuenta. | Un fallo tras el consentimiento no prueba por sí solo que falten tablas. |

| Elemento | Comportamiento comprobado en el repositorio |
|---|---|
| `.env` | Es el archivo predeterminado de `Settings` cuando no existe `ENV_FILE`. El ejemplo `.env.example` apunta a **`fireassets`**, no a la base de pruebas. |
| `.env.test` | Es el archivo privado previsto para la clase, con `DATABASE_URL` apuntando a **`fireassets_test`**. Copiar `.env.example` no cambia automáticamente el nombre de la base: hay que editarlo. |
| `ENV_FILE` | Selecciona el archivo de `Settings`; `migrations/env.py` usa esa misma configuración para Alembic. Una variable de entorno del proceso como `DATABASE_URL` puede prevalecer sobre el valor del archivo; por eso no basta con leer `.env.test`. |
| `scripts/test-up.sh` / `scripts/test-up.ps1` | Seleccionan `.env.test`, comprueban **el nombre escrito en ese archivo** y arrancan Uvicorn en `127.0.0.1:8000`. No crean bases ni aplican migraciones. La comprobación del script no reemplaza el preflight de configuración efectiva y conexión. |
| Servidor iniciado manualmente | Sin `ENV_FILE=.env.test` puede leer `.env`. Además, el motor de SQLAlchemy se crea al importar el módulo: después de corregir variables o migraciones, detener y reiniciar el servidor. |

Referencias: [`settings.py`](../../app/config/settings.py), [`migrations/env.py`](../../migrations/env.py), [`session.py`](../../app/infrastructure/database/session.py), [`test-up.sh`](../../scripts/test-up.sh), [`test-up.ps1`](../../scripts/test-up.ps1) y [`.env.example`](../../.env.example). No mostrar ni compartir los valores reales de `.env` o `.env.test`.

En el checkout existente, **inspeccionar** `.env.test`; no reemplazarlo con `.env.example`. Para Google, el servidor necesita `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` y `GOOGLE_REDIRECT_URI`; este último debe ser exactamente `http://127.0.0.1:8000/auth/google/callback` si se usa el arranque documentado. No escribir valores reales en comandos, capturas o Git. Si falta `.env.test`, `.venv` o la base local, detener esta ruta: la configuración inicial está en [macOS](macos.md), [Windows](windows.md) y [Google OAuth](google-oauth.md).

## 2. Preflight obligatorio: comprobar el destino real, sin escribir

Ejecutar **desde la raíz del repositorio**. Estos comandos leen la configuración efectiva, conectan con PostgreSQL y hacen solo consultas `SELECT`. Exigen una conexión local y `fireassets_test`; si fallan, **no migrar**. Si se usa otro host/puerto local por decisión del equipo, revisarlo con el docente antes de modificar la comprobación.

### macOS (Terminal)

```bash
env -u DATABASE_URL ENV_FILE=.env.test ./.venv/bin/python - <<'PY'
import asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from app.config.settings import get_settings

settings = get_settings()
url = make_url(settings.database_url)
if url.database != "fireassets_test" or url.host not in {"localhost", "127.0.0.1", "::1"}:
    raise SystemExit("ALTO: la configuración efectiva no apunta a fireassets_test local")
print(f"Destino configurado: {url.host}:{url.port or 5432}/{url.database}")

async def check():
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.connect() as connection:
            actual = await connection.scalar(text("SELECT current_database()"))
            if actual != "fireassets_test":
                raise SystemExit("ALTO: la conexión real no usa fireassets_test")
            print(f"Base conectada: {actual}")
            for table in ("alembic_version", "categorias", "bienes", "usuarios"):
                present = await connection.scalar(
                    text("SELECT to_regclass(:name)"), {"name": f"public.{table}"}
                )
                print(f"{table}: {'presente' if present else 'ausente'}")
            version_table = await connection.scalar(text("SELECT to_regclass('public.alembic_version')"))
            if version_table:
                version = await connection.scalar(text("SELECT version_num FROM alembic_version"))
                print(f"Revisión aplicada: {version or 'sin registro'}")
            users_table = await connection.scalar(text("SELECT to_regclass('public.usuarios')"))
            if users_table:
                rows = await connection.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name='usuarios' "
                    "AND column_name IN ('email','password_hash','google_sub','display_name') "
                    "ORDER BY column_name"
                ))
                print("Columnas de usuarios:", ", ".join(rows.scalars()) or "ninguna")
    finally:
        await engine.dispose()

asyncio.run(check())
PY
```

### Windows (PowerShell)

El mismo diagnóstico, con `ENV_FILE` limitado a este bloque y restaurado al terminar:

```powershell
$previousEnvFile = $env:ENV_FILE
$previousDatabaseUrl = $env:DATABASE_URL
try {
    $env:ENV_FILE = ".env.test"
    Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    @'
import asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from app.config.settings import get_settings

settings = get_settings()
url = make_url(settings.database_url)
if url.database != "fireassets_test" or url.host not in {"localhost", "127.0.0.1", "::1"}:
    raise SystemExit("ALTO: la configuración efectiva no apunta a fireassets_test local")
print(f"Destino configurado: {url.host}:{url.port or 5432}/{url.database}")

async def check():
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.connect() as connection:
            actual = await connection.scalar(text("SELECT current_database()"))
            if actual != "fireassets_test":
                raise SystemExit("ALTO: la conexión real no usa fireassets_test")
            print(f"Base conectada: {actual}")
            for table in ("alembic_version", "categorias", "bienes", "usuarios"):
                present = await connection.scalar(
                    text("SELECT to_regclass(:name)"), {"name": f"public.{table}"}
                )
                print(f"{table}: {'presente' if present else 'ausente'}")
            version_table = await connection.scalar(text("SELECT to_regclass('public.alembic_version')"))
            if version_table:
                version = await connection.scalar(text("SELECT version_num FROM alembic_version"))
                print(f"Revisión aplicada: {version or 'sin registro'}")
            users_table = await connection.scalar(text("SELECT to_regclass('public.usuarios')"))
            if users_table:
                rows = await connection.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name='usuarios' "
                    "AND column_name IN ('email','password_hash','google_sub','display_name') "
                    "ORDER BY column_name"
                ))
                print("Columnas de usuarios:", ", ".join(rows.scalars()) or "ninguna")
    finally:
        await engine.dispose()

asyncio.run(check())
'@ | & .\.venv\Scripts\python.exe -
    if ($LASTEXITCODE -ne 0) { throw "Preflight fallido: no ejecutar migraciones." }
}
finally {
    if ($null -eq $previousEnvFile) {
        Remove-Item Env:ENV_FILE -ErrorAction SilentlyContinue
    } else {
        $env:ENV_FILE = $previousEnvFile
    }
    if ($null -eq $previousDatabaseUrl) {
        Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    } else {
        $env:DATABASE_URL = $previousDatabaseUrl
    }
}
```

**Interpretación:** la revisión final de este repositorio es `d8b6e2f1940a`; la secuencia es `0374d9a573a1` (crea `categorias` y `bienes`), `b70e8e0479aa` (crea `usuarios`), `c4e9f1d2a7b3` (agrega `google_sub` y permite `password_hash` nulo) y `d8b6e2f1940a` (agrega `display_name`). Una base nueva puede no tener `alembic_version`; una revisión antigua o columnas ausentes indican migraciones pendientes. Si Alembic declara la revisión final pero faltan tablas o columnas, **no** usar `stamp`, `downgrade` ni recrear nada: hay una inconsistencia que debe revisar el docente. Referencias: [`migrations/versions`](../../migrations/versions/) y [`User`](../../app/modules/auth/models.py).

## 3. Aplicar migraciones solo a `fireassets_test`

Hacerlo **únicamente** si el preflight terminó sin error, mostró `Base conectada: fireassets_test` y esa base necesita revisiones. Es una operación que modifica el esquema; no forma parte del diagnóstico de solo lectura. No usar `alembic init`: el proyecto ya contiene Alembic. Los comandos siguientes eliminan `DATABASE_URL` **solo del proceso hijo** para que una variable heredada no prevalezca sobre `.env.test`, igual que el preflight. Si `.env.test` cambió desde el preflight, repetirlo antes de migrar.

**macOS:**

```bash
env -u DATABASE_URL ENV_FILE=.env.test ./.venv/bin/python -m alembic current
env -u DATABASE_URL ENV_FILE=.env.test ./.venv/bin/python -m alembic upgrade head
env -u DATABASE_URL ENV_FILE=.env.test ./.venv/bin/python -m alembic current
```

**Windows (PowerShell):**

```powershell
$previousEnvFile = $env:ENV_FILE
$previousDatabaseUrl = $env:DATABASE_URL
try {
    $env:ENV_FILE = ".env.test"
    Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    & .\.venv\Scripts\python.exe -m alembic current
    if ($LASTEXITCODE -ne 0) { throw "No se pudo leer la revisión." }
    & .\.venv\Scripts\python.exe -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw "La migración falló." }
    & .\.venv\Scripts\python.exe -m alembic current
    if ($LASTEXITCODE -ne 0) { throw "No se pudo comprobar la revisión final." }
}
finally {
    if ($null -eq $previousEnvFile) {
        Remove-Item Env:ENV_FILE -ErrorAction SilentlyContinue
    } else {
        $env:ENV_FILE = $previousEnvFile
    }
    if ($null -eq $previousDatabaseUrl) {
        Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    } else {
        $env:DATABASE_URL = $previousDatabaseUrl
    }
}
```

**Resultado esperado:** `alembic current` termina en `d8b6e2f1940a`; al repetir el preflight, `usuarios` existe con `email`, `password_hash`, `google_sub` y `display_name`. Si la migración falla, conservar el error **sin credenciales** y detenerse; no ejecutar un segundo comando contra otra base “para probar”. Las instrucciones generales de instalación están en [macOS](macos.md) y [Windows](windows.md).

### Comprobar que el servidor usa esa misma base

El preflight abre **otro proceso Python**: no prueba qué configuración cargó un Uvicorn que ya estaba ejecutándose. Detener cualquier servidor anterior (normalmente con `Ctrl+C`) y repetir el preflight. Después, arrancar **un proceso nuevo** con el script del proyecto, sin un `DATABASE_URL` heredado que prevalezca sobre `.env.test`. Si el puerto 8000 ya está ocupado, identificar y detener el proceso anterior; no interpretar su respuesta como la del servidor nuevo.

En macOS:

```bash
env -u DATABASE_URL ./scripts/test-up.sh
```

En Windows PowerShell:

```powershell
$previousDatabaseUrl = $env:DATABASE_URL
try {
    Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    .\scripts\test-up.ps1
}
finally {
    if ($null -eq $previousDatabaseUrl) {
        Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    } else {
        $env:DATABASE_URL = $previousDatabaseUrl
    }
}
```

Ambos scripts fijan `ENV_FILE=.env.test` para el nuevo servidor y verifican el nombre escrito en ese archivo. El preflight verifica la conexión efectiva; el reinicio sin `DATABASE_URL` heredado evita que un proceso antiguo o una variable externa cambien el destino. No imprimir el valor de `DATABASE_URL` ni credenciales para hacer esta comprobación.

## 4. Localizar la etapa que falló después del consentimiento

Abrir `http://127.0.0.1:8000/iniciar-sesion` e iniciar **un** intento nuevo. La aplicación usa `GET /auth/google/start` y Google vuelve a `GET /auth/google/callback`. El callback valida la cookie temporal (5 minutos) y `state`, intercambia el código, verifica ID token/correo/`nonce`, y por último consulta o crea la cuenta en `usuarios`. El servidor redirige con `auth_error=...` cuando produce un error controlado. Referencias: [`router.py`](../../app/modules/auth/router.py), [`google_oauth.py`](../../app/modules/auth/google_oauth.py), [`google_service.py`](../../app/modules/auth/google_service.py).

En la terminal del servidor, buscar los eventos JSON con `"event":"google_oauth"` y seguir **un mismo** `attempt_id` por `start`, `callback`, `token_exchange`, `identity` y `account`. Los scripts `test-up` usan `--no-access-log` para no imprimir la URL del callback, que contiene `code` y `state`. No compartir URLs completas del callback, cookies, tokens, correos, `.env`, ni trazas crudas. Compartir solo etapa, resultado, razón permitida, código HTTP y revisión de Alembic, sin datos personales.

| Evidencia observada | Qué comprobar a continuación |
|---|---|
| `start/rejected`, `not_configured` | Faltan `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` o `GOOGLE_REDIRECT_URI` en el entorno **del servidor en marcha**. Corregir el archivo seleccionado y reiniciar. |
| No vuelve al callback, o Google muestra un bloqueo antes del retorno | Verificar en la configuración del cliente OAuth web que el URI autorizado coincida exactamente con `http://127.0.0.1:8000/auth/google/callback`; si la pantalla está en modo de prueba, verificar la cuenta de prueba autorizada. No es evidencia de una tabla ausente. |
| `callback/rejected` con `missing_flow`, `invalid_flow` o `invalid_state` | Revisar que el intento se completó en el mismo navegador, host y sesión, sin superar los cinco minutos ni reutilizar una URL antigua. `localhost` y `127.0.0.1` no son el mismo host para la cookie. |
| `token_exchange/failed`, quizá `provider_http_error` | Revisar cliente, secreto y URI en el entorno activo; HTTP 400 por sí solo **no identifica** el valor incorrecto. |
| `identity/rejected` o `identity/failed` | Falló la verificación del token, del correo o del `nonce`; revisar la razón segura del evento, no el token. |
| `identity/succeeded` y después `account/failed` | La identidad se verificó, pero la regla de cuenta impidió entrar o vincular. `GOOGLE_LINK_REQUIRED` exige iniciar primero con contraseña y usar **Vincular Google**; `GOOGLE_ACCOUNT_CONFLICT` y `GOOGLE_EMAIL_MISMATCH` son distintos de un problema de migración. |
| `identity/succeeded`, pero no hay `account/succeeded`; aparecen errores SQL o respuesta 500 | **Hipótesis, no diagnóstico definitivo:** la consulta a `usuarios` puede fallar por tabla o columna ausente. Comprobar preflight y revisión Alembic en la base del servidor. `google_service.py` solo traduce conflictos de integridad a error OAuth; una tabla/columna inexistente puede llegar al manejador de error inesperado. |
| `callback/succeeded` y `account/succeeded` | El flujo local terminó; si la página sigue sin sesión, revisar cookies y que se regrese al mismo origen local. |

Para una cuenta ya existente con contraseña, el sistema **no** la vincula automáticamente por correo: entrar con contraseña y elegir **Vincular Google** desde el perfil. Si una persona entra y otra no, comparar **etapas y entornos**, no inferir que todos comparten la misma causa. El código y las migraciones viajan con Git; cada integrante debe preparar su propia base.

## Comprobación final de la clase

- [ ] El preflight imprime `fireassets_test` como destino configurado y base conectada; el host es local.
- [ ] `alembic current` informa `d8b6e2f1940a`, y el preflight ve `usuarios.google_sub` y `usuarios.display_name`.
- [ ] El servidor se inició con `test-up`, no con un proceso anterior que conserva otra configuración.
- [ ] Un intento nuevo termina en `callback/succeeded` o proporciona un `attempt_id` y una etapa segura para continuar el diagnóstico.

**No confirmado por esta guía:** cuál de estas causas afectó a cada integrante. Para concluirlo hacen falta la revisión y la base efectiva de *su* servidor, más los eventos del intento concreto; no se requieren ni deben compartirse secretos.

## Si es necesario revisar `fireassets`

Esta comprobación es secundaria; para probar Google, seguir primero la ruta de `fireassets_test`. Si hay dudas sobre el estado de `fireassets`, detener nuevas escrituras en esa base y comprobar su esquema y revisión mediante consultas de solo lectura. No usar `reset`, `drop`, `downgrade` ni `stamp` sin un diagnóstico. Preservar un respaldo y acordar cualquier cambio con el responsable de la base.

Para inspeccionar **sin modificar** esa base, usar una conexión `psql` explícita en macOS o PowerShell. Sustituir usuario, host y puerto por los de la instalación local; dejar que `psql` solicite la contraseña, sin escribirla en el comando ni en registros:

```text
psql -h localhost -p 5432 -U YOUR_DB_USER -d fireassets -X -v ON_ERROR_STOP=1 -c "SELECT current_database() AS database_name, to_regclass('public.alembic_version') AS alembic_version_table, to_regclass('public.usuarios') AS usuarios, to_regclass('public.categorias') AS categorias, to_regclass('public.bienes') AS bienes;"
```

Confirmar que `database_name` dice `fireassets`. **Solo si** `alembic_version_table` aparece presente, leer su revisión, también en modo de solo lectura:

```text
psql -h localhost -p 5432 -U YOUR_DB_USER -d fireassets -X -v ON_ERROR_STOP=1 -c "SELECT version_num FROM public.alembic_version;"
```

Comparar esos resultados con el preflight anterior para `fireassets_test`. Si difieren, registrar la diferencia y consultar al responsable antes de modificar `fireassets`. Para diagnosticar Google, correlacionar la base efectiva del servidor con los eventos del intento.

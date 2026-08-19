# Task 01 — Verificar la conexión existente con PostgreSQL

En esta tarea vamos a comprobar que la conexión a PostgreSQL ya implementada en el proyecto funciona correctamente.

> No tenés que crear código de conexión. Esa parte ya existe en el proyecto.

## Objetivo

Entender qué archivos participan en la conexión y verificar que tu computadora puede usarla.

## Archivos que vamos a leer

```text
app/config/settings.py
app/infrastructure/database/base.py
app/infrastructure/database/session.py
app/infrastructure/database/metadata.py
```

## Qué hace cada archivo

| Archivo | Para qué sirve |
|---|---|
| `app/config/settings.py` | Lee variables desde `.env`, especialmente `DATABASE_URL` |
| `app/infrastructure/database/base.py` | Define la clase base para los modelos de SQLAlchemy |
| `app/infrastructure/database/session.py` | Crea el engine y las sesiones para hablar con PostgreSQL |
| `app/infrastructure/database/metadata.py` | Reserva un lugar para centralizar metadata/imports de modelos |

## Flujo existente

```text
.env
  ↓
settings.py lee DATABASE_URL
  ↓
session.py crea el engine
  ↓
session.py prepara sesiones async
  ↓
los endpoints podrán pedir una sesión de base de datos
```

## Antes de empezar

Antes de tocar código, creá o activá tu rama siguiendo:

```text
GIT_WORKFLOW.md
```

No trabajes directo sobre `main`.

---

# Paso 1 — Verificar `.env`

El archivo `.env` debe tener una línea como esta en Windows:

```env
DATABASE_URL=postgresql+asyncpg://postgres:TU_PASSWORD@localhost:5432/fireassets
```

Reemplazá `TU_PASSWORD` por la contraseña real del usuario `postgres`.

No dejes `TU_PASSWORD` escrito literal.

## Cómo leer esta URL

```text
postgresql       → tipo de base de datos
asyncpg          → driver async de Python
postgres         → usuario de PostgreSQL en Windows
TU_PASSWORD      → contraseña real del usuario postgres
localhost        → la base está en tu computadora
5432             → puerto de PostgreSQL
fireassets       → nombre de la base de datos
```

> Importante: no uses `postgresql+asyncpg://TU_PASSWORD@localhost:5432/fireassets`. Eso es incorrecto porque pone la contraseña en el lugar del usuario.

---

# Paso 2 — Confirmar que PostgreSQL está corriendo

En PowerShell, ejecutar:

```powershell
Get-Service *postgres*
```

Resultado esperado:

```text
Running
```

Si aparece `Stopped`, pedí ayuda antes de seguir.

---

# Paso 3 — Confirmar que existe la base `fireassets`

Ejecutar:

```powershell
psql -U postgres -d fireassets
```

Si entra correctamente, deberías ver:

```text
fireassets=#
```

Salir con:

```sql
\q
```

---

# Paso 4 — Verificar que Python lee la configuración

Desde la raíz del proyecto, con `.venv` activo, ejecutar:

```powershell
python -c "from app.config.settings import get_settings; print(get_settings().database_url)"
```

Resultado esperado:

```text
postgresql+asyncpg://postgres:...
```

No hace falta que muestres tu contraseña completa en clase.

Si aparece un error sobre `database_url` o `secret_key`, revisá tu archivo `.env`.

---

# Paso 5 — Verificar que SQLAlchemy crea el engine

Ejecutar:

```powershell
python -c "from app.infrastructure.database.session import engine; print(type(engine).__name__)"
```

Resultado esperado:

```text
AsyncEngine
```

Eso significa que Python pudo cargar la configuración y preparar el objeto de conexión.

---

# Paso 6 — Verificar que el proyecto sigue importando bien

Ejecutar:

```powershell
python -c "from app.main import app; print(app.title)"
```

Resultado esperado:

```text
Fire Control
```

Si esto falla, copiá el error completo y pedí ayuda.

---

# Paso 7 — Revisar estado de Git

Ejecutar:

```powershell
git status
```

En esta tarea probablemente no tengas cambios de código.

Si aparecen archivos como `.env`, `.venv` o `__pycache__`, no los subas.

---

# Uso de `print()` para aprender

En esta tarea no vamos a agregar `print()` dentro del código del proyecto.

Vamos a usar `print()` desde comandos cortos de Python para mirar qué está cargando la aplicación.

## Ver nombre de la aplicación

Ejecutar:

```powershell
python -c "from app.config.settings import get_settings; settings = get_settings(); print('App name:', settings.app_name)"
```

Resultado esperado:

```text
App name: FireOps Intelligence
```

## Ver ambiente

Ejecutar:

```powershell
python -c "from app.config.settings import get_settings; settings = get_settings(); print('Environment:', settings.environment)"
```

Resultado esperado:

```text
Environment: development
```

## Ver tipo de engine

Ejecutar:

```powershell
python -c "from app.infrastructure.database.session import engine; print('Engine type:', type(engine).__name__)"
```

Resultado esperado:

```text
Engine type: AsyncEngine
```

## Regla importante

Estos `print()` viven sólo en la terminal.

No modifican archivos del proyecto.

Por eso no hace falta borrarlos antes del commit.

Pero si agregaste prints manualmente en archivos `.py`, revisalos con:

```powershell
git diff
```

y borralos si eran sólo para practicar.

---

# Qué entregar

Entregá estos resultados:

1. Confirmación de que PostgreSQL está `Running`.
2. Confirmación de que pudiste entrar a `fireassets`.
3. Resultado de:

```powershell
python -c "from app.infrastructure.database.session import engine; print(type(engine).__name__)"
```

4. Una explicación corta con tus palabras:

```text
La conexión ya está implementada. settings.py lee la URL de la base, session.py prepara SQLAlchemy para conectarse y los endpoints podrán usar esa sesión más adelante.
```

---

# Qué aprendiste

La conexión a PostgreSQL ya existe.

En esta tarea no escribiste la conexión: aprendiste a verificarla.

La próxima tarea será crear la primera tabla real: `bienes`.

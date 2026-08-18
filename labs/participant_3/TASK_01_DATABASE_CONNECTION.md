# Task 01 — Entender y verificar la conexión con PostgreSQL

En esta tarea vamos a revisar la conexión a base de datos que ya existe en el proyecto.

No vamos a crear estos archivos desde cero. Ya están creados.

## Archivos existentes

```text
app/config/__init__.py
app/config/settings.py
app/infrastructure/database/__init__.py
app/infrastructure/database/base.py
app/infrastructure/database/session.py
app/infrastructure/database/metadata.py
```

## Objetivo

Entender qué hace cada archivo y verificar que Python puede crear la conexión con PostgreSQL.

## Flujo existente

```text
.env
  ↓
settings.py lee DATABASE_URL
  ↓
session.py crea engine
  ↓
AsyncSessionLocal crea sesiones
  ↓
get_database_session entrega una sesión a FastAPI
```

## Rama sugerida

```powershell
git checkout main
git pull
git checkout -b participant-X/task-01-verify-database-connection
```

Reemplazá `participant-X` por tu número.

---

# Paso 1 — Verificar `.env`

El archivo `.env` debe tener algo como:

```env
APP_NAME=FireOps Intelligence
ENVIRONMENT=development
DATABASE_URL=postgresql+asyncpg://postgres:YOUR_PASSWORD@localhost:5432/fireassets
SECRET_KEY=replace-this-value
```

En Windows, reemplazá `YOUR_PASSWORD` por tu contraseña real de PostgreSQL.

No dejes `YOUR_PASSWORD` escrito literal.

En Mac puede verse distinto, por ejemplo:

```env
DATABASE_URL=postgresql+asyncpg://luis@localhost:5432/fireassets
```

Eso está bien si PostgreSQL local permite conectarse con ese usuario.

---

# Paso 2 — Leer `settings.py`

Abrir:

```text
app/config/settings.py
```

Deberías ver una clase parecida a esta:

```python
class Settings(BaseSettings):
    app_name: str = "FireOps Intelligence"
    environment: str = "development"
    database_url: str
    secret_key: str
```

## Qué hace

Este archivo lee variables desde `.env`.

La más importante para la base de datos es:

```text
DATABASE_URL
```

En Python se usa como:

```python
settings.database_url
```

---

# Paso 3 — Leer `base.py`

Abrir:

```text
app/infrastructure/database/base.py
```

Deberías ver:

```python
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase


class Base(AsyncAttrs, DeclarativeBase):
    pass
```

## Qué hace

`Base` es la clase madre de los modelos de base de datos.

Después vamos a crear modelos así:

```python
class Asset(Base):
    ...
```

Eso le permite a SQLAlchemy saber que `Asset` representa una tabla.

---

# Paso 4 — Leer `session.py`

Abrir:

```text
app/infrastructure/database/session.py
```

Buscá estas partes:

```python
engine = create_async_engine(...)
```

```python
AsyncSessionLocal = async_sessionmaker(...)
```

```python
async def get_database_session(...):
```

## Qué hace cada cosa

| Pieza | Significado |
|---|---|
| `engine` | puente principal hacia PostgreSQL |
| `AsyncSessionLocal` | fábrica de sesiones |
| `get_database_session` | función que entrega una sesión a un endpoint |

---

# Paso 5 — Verificar que Python lee `.env`

Desde la raíz del proyecto, con `.venv` activo, ejecutar:

```powershell
python -c "from app.config.settings import get_settings; print(get_settings().database_url)"
```

Resultado esperado:

```text
postgresql+asyncpg://...
```

Si aparece un error sobre `database_url` o `secret_key`, revisá tu `.env`.

---

# Paso 6 — Verificar que Python crea el engine

Ejecutar:

```powershell
python -c "from app.infrastructure.database.session import engine; print(type(engine).__name__)"
```

Resultado esperado:

```text
AsyncEngine
```

Eso confirma que SQLAlchemy pudo crear el objeto de conexión.

---

# Paso 7 — Verificar que PostgreSQL está disponible

Ejecutar:

```powershell
psql -U postgres -d fireassets
```

Si entra, deberías ver:

```text
fireassets=#
```

Salir:

```sql
\q
```

---

# Paso 8 — Revisar estado de Git

```powershell
git status
```

En esta tarea quizás no tengas que modificar código.

Si sólo verificaste y leíste archivos, puede estar limpio.

---

# Qué entregar

Entregá:

1. Resultado de:

```powershell
python -c "from app.config.settings import get_settings; print(get_settings().database_url)"
```

2. Resultado de:

```powershell
python -c "from app.infrastructure.database.session import engine; print(type(engine).__name__)"
```

3. Confirmación de que pudiste entrar a `fireassets` con `psql`.

4. Una explicación corta con tus palabras:

```text
settings.py lee la configuración, base.py define la clase madre de los modelos y session.py prepara las sesiones para conectarse a PostgreSQL.
```

---

# Qué aprendiste

La conexión ya existe en el proyecto.

Todavía falta crear modelos, migraciones y endpoints que usen esa conexión.

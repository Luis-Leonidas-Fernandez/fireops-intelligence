# Task 02 — Crear la tabla de bienes

En esta tarea vamos a crear el primer modelo de inventario y una migración para que PostgreSQL tenga una tabla real llamada `bienes`.

## Objetivo

Crear o modificar:

```text
app/modules/inventory/shared/models.py
migrations/env.py
migrations/versions/<revision>_create_bienes_table.py
```

## Flujo

```text
modelo SQLAlchemy
  ↓
Base.metadata
  ↓
Alembic detecta metadata
  ↓
migración crea tabla
  ↓
PostgreSQL tiene tabla bienes
```

## Rama sugerida

```powershell
git checkout main
git pull
git checkout -b participant-X/task-02-create-asset-table
```

---

# Paso 1 — Crear el modelo Asset

Abrir:

```text
app/modules/inventory/shared/models.py
```

Copiar:

```python
from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class Asset(Base):
    __tablename__ = "bienes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    codigo_interno: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    categoria_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
```

## Qué hace

Esta clase representa la tabla `bienes`.

Cada atributo representa una columna.

---

# Paso 2 — Conectar metadata con Alembic

Abrir:

```text
migrations/env.py
```

Buscar:

```python
target_metadata = None
```

Reemplazar por:

```python
from app.infrastructure.database.base import Base
from app.modules.inventory.shared import models  # noqa: F401

target_metadata = Base.metadata
```

## Qué hace

Alembic necesita ver `Base.metadata` para saber qué tablas existen en Python.

El import de `models` fuerza a Python a cargar el modelo `Asset`.

---

# Paso 3 — Crear migración

Ejecutar:

```powershell
alembic revision --autogenerate -m "create bienes table"
```

Esto debe crear un archivo en:

```text
migrations/versions/
```

Abrilo y verificá que aparezca algo como:

```python
op.create_table(
    "bienes",
    ...
)
```

---

# Paso 4 — Aplicar migración

Ejecutar:

```powershell
alembic upgrade head
```

Resultado esperado: no debe mostrar error.

---

# Paso 5 — Verificar en PostgreSQL

Entrar:

```powershell
psql -U postgres -d fireassets
```

Listar tablas:

```sql
\dt
```

Deberías ver:

```text
bienes
```

Salir:

```sql
\q
```

---

# Qué entregar

- Archivo de modelo creado.
- Archivo de migración creado.
- Resultado de `alembic upgrade head`.
- Captura o texto mostrando `\dt` con la tabla `bienes`.

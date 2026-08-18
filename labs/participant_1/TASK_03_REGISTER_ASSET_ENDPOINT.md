# Task 03 — Registrar un bien usando la base de datos

En esta tarea vamos a crear el endpoint `POST /inventory/assets` para guardar un bien real en PostgreSQL.

## Objetivo

Crear o modificar:

```text
app/modules/inventory/register_asset/schemas.py
app/modules/inventory/register_asset/router.py
app/main.py
```

## Flujo

```text
JSON del usuario
  ↓
RegisterAssetRequest
  ↓
endpoint register_asset
  ↓
Asset(...)
  ↓
session.add
  ↓
commit
  ↓
refresh
  ↓
RegisterAssetResponse
```

## Rama sugerida

```powershell
git checkout main
git pull
git checkout -b participant-X/task-03-register-asset-endpoint
```

---

# Paso 1 — Crear schemas

Crear:

```text
app/modules/inventory/register_asset/schemas.py
```

Copiar:

```python
from pydantic import BaseModel, Field


class RegisterAssetRequest(BaseModel):
    internal_code: str = Field(min_length=3, max_length=30)
    name: str = Field(min_length=3, max_length=150)
    category_id: int = Field(gt=0)


class RegisterAssetResponse(BaseModel):
    id: int
    internal_code: str
    name: str
    category_id: int
```

---

# Paso 2 — Crear router con DB

Crear:

```text
app/modules/inventory/register_asset/router.py
```

Copiar:

```python
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_database_session
from app.modules.inventory.register_asset.schemas import (
    RegisterAssetRequest,
    RegisterAssetResponse,
)
from app.modules.inventory.shared.models import Asset

router = APIRouter(prefix="/inventory/assets", tags=["Inventory"])

DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]


@router.post("", response_model=RegisterAssetResponse, status_code=status.HTTP_201_CREATED)
async def register_asset(
    request: RegisterAssetRequest,
    session: DatabaseSession,
) -> RegisterAssetResponse:
    asset = Asset(
        codigo_interno=request.internal_code,
        nombre=request.name,
        categoria_id=request.category_id,
    )

    session.add(asset)
    await session.commit()
    await session.refresh(asset)

    return RegisterAssetResponse(
        id=asset.id,
        internal_code=asset.codigo_interno,
        name=asset.nombre,
        category_id=asset.categoria_id,
    )
```

## Qué hace

- Recibe datos.
- Crea un objeto `Asset`.
- Lo agrega a la sesión.
- Hace `commit` para guardar.
- Hace `refresh` para obtener el `id` generado.
- Devuelve la respuesta.

---

# Paso 3 — Conectar router en `app/main.py`

Abrir:

```text
app/main.py
```

Agregar import:

```python
from app.modules.inventory.register_asset.router import router as register_asset_router
```

Después de crear `app`, agregar:

```python
app.include_router(register_asset_router)
```

---

# Paso 4 — Probar manualmente

Levantar servidor:

```powershell
python -m uvicorn app.main:app --reload
```

Abrir:

```text
http://127.0.0.1:8000/docs
```

Probar `POST /inventory/assets` con:

```json
{
  "internal_code": "BOM-001",
  "name": "Manguera forestal",
  "category_id": 1
}
```

Respuesta esperada:

```json
{
  "id": 1,
  "internal_code": "BOM-001",
  "name": "Manguera forestal",
  "category_id": 1
}
```

El `id` puede ser otro número.

---

# Paso 5 — Verificar en PostgreSQL

Entrar:

```powershell
psql -U postgres -d fireassets
```

Consultar:

```sql
SELECT id, codigo_interno, nombre, categoria_id FROM bienes;
```

Deberías ver el bien registrado.

Salir:

```sql
\q
```

---

# Qué entregar

- Captura o texto de `/docs` funcionando.
- Resultado del `SELECT` en PostgreSQL.
- Explicación breve de qué hacen `session.add`, `commit` y `refresh`.

# Task 04 — Endpoints de categorías

La **Task 03 ya está completada** y no se modifica en esta tarea. El endpoint de bienes existente es:

```text
POST /inventory/assets
```

---

## Requisito previo obligatorio

Antes de comenzar esta tarea, hay que completar la guía de herramientas de Visual Studio Code y PostgreSQL:

```text
vscode-tools.md
```

No empieces a crear código hasta verificar estos puntos:

- [ ] SQLTools está instalado y habilitado.
- [ ] SQLTools PostgreSQL/Cockroach Driver está instalado y habilitado.
- [ ] La conexión `FireAssets` está creada.
- [ ] La conexión apunta a la base `fireassets`.
- [ ] PostgreSQL está ejecutándose.
- [ ] Las tablas `categorias` y `bienes` existen.
- [ ] Esta consulta devuelve `fireassets`:

```sql
SELECT current_database(), current_user;
```

- [ ] SQLTools permite consultar la base sin mostrar `sql_learning`.

Si alguno de estos puntos falla, primero corregí la configuración siguiendo `vscode-tools.md`. La Task 04 comienza únicamente cuando la conexión y las tablas están verificadas.

En esta tarea vamos a trabajar únicamente en lo que falta: administrar categorías desde la API.

## Objetivo

Crear estos dos endpoints:

| Método | Endpoint | Función |
|---|---|---|
| `POST` | `/inventory/categories` | Crear una categoría. |
| `GET` | `/inventory/categories` | Listar categorías. |

El endpoint de bienes usará después el `id` de una categoría existente, pero **no vamos a modificarlo en esta tarea**.

---

## Archivos que faltan crear

Crear solamente estos archivos:

```text
app/modules/inventory/register_category/__init__.py
app/modules/inventory/register_category/schemas.py
app/modules/inventory/register_category/router.py
```

El modelo ya existe y no se debe modificar:

```text
app/modules/inventory/shared/models.py
```

El endpoint de bienes ya existe y tampoco se debe modificar:

```text
app/modules/inventory/register_asset/router.py
```

---

# Paso 1 — Crear la carpeta y los archivos

### Windows / PowerShell

```powershell
New-Item -ItemType Directory -Force app/modules/inventory/register_category
New-Item -ItemType File -Force app/modules/inventory/register_category/__init__.py
New-Item -ItemType File -Force app/modules/inventory/register_category/schemas.py
New-Item -ItemType File -Force app/modules/inventory/register_category/router.py
```

### macOS o Linux

```bash
mkdir -p app/modules/inventory/register_category
touch app/modules/inventory/register_category/__init__.py
touch app/modules/inventory/register_category/schemas.py
touch app/modules/inventory/register_category/router.py
```

Si los archivos ya existen, no los reemplaces: abrilos y completalos.

---

# Paso 2 — Crear los schemas

Abrir:

```text
app/modules/inventory/register_category/schemas.py
```

Copiar:

```python
from pydantic import BaseModel, Field


class CreateCategoryRequest(BaseModel):
    name: str = Field(min_length=3, max_length=100)


class CategoryResponse(BaseModel):
    id: int
    name: str
```

## Qué hace cada schema

- `CreateCategoryRequest`: valida los datos que llegan.
- `name`: exige entre 3 y 100 caracteres.
- `CategoryResponse`: define los datos que devuelve la API.

La API usa `name`, pero el modelo de PostgreSQL usa `nombre`. El router hará esa conversión.

---

# Paso 3 — Crear los endpoints

Abrir:

```text
app/modules/inventory/register_category/router.py
```

Copiar:

```python
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_database_session
from app.modules.inventory.register_category.schemas import (
    CategoryResponse,
    CreateCategoryRequest,
)
from app.modules.inventory.shared.models import Category

router = APIRouter(prefix="/inventory/categories", tags=["Inventory"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def register_category(
    request: CreateCategoryRequest,
    session: DatabaseSession,
) -> CategoryResponse:
    category = Category(nombre=request.name)
    session.add(category)

    try:
        await session.commit()
        await session.refresh(category)
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The category already exists.",
        ) from error

    return CategoryResponse(id=category.id, name=category.nombre)


@router.get("", response_model=list[CategoryResponse])
async def list_categories(
    session: DatabaseSession,
) -> list[CategoryResponse]:
    result = await session.execute(select(Category).order_by(Category.id))
    categories = result.scalars().all()

    return [
        CategoryResponse(id=category.id, name=category.nombre)
        for category in categories
    ]
```

## Qué hace `POST /inventory/categories`

1. Recibe el nombre.
2. Valida el schema.
3. Crea un objeto `Category`.
4. Lo agrega a la sesión.
5. Guarda con `commit()`.
6. Obtiene el `id` con `refresh()`.
7. Devuelve la categoría creada.

Si el nombre ya existe, PostgreSQL produce un error de integridad y la API responde `409 Conflict`.

## Qué hace `GET /inventory/categories`

1. Consulta la tabla `categorias`.
2. Ordena por `id`.
3. Obtiene todas las filas.
4. Devuelve una lista JSON.

Si no hay categorías, devuelve una lista vacía:

```json
[]
```

---

# Paso 4 — Registrar el router

Abrir:

```text
app/main.py
```

Agregar el import:

```python
from app.modules.inventory.register_category.router import (
    router as register_category_router,
)
```

Agregar junto a la inclusión del router de bienes:

```python
app.include_router(register_category_router)
```

No modificar el router de bienes. Solo agregar el nuevo import y la nueva inclusión.

---

# Paso 5 — Probar los endpoints

Levantar la aplicación:

```bash
python -m uvicorn app.main:app --reload
```

Abrir:

```text
http://127.0.0.1:8000/docs
```

## Crear una categoría

Usar `POST /inventory/categories`:

```json
{
  "name": "Mangueras"
}
```

Resultado esperado:

```text
201 Created
```

## Listar categorías

Usar `GET /inventory/categories`.

Resultado esperado:

```json
[
  {
    "id": 1,
    "name": "Mangueras"
  }
]
```

El `id` obtenido será el que se use cuando se cree un bien en el endpoint ya terminado de la Task 03.

---

# Paso 6 — Verificar en SQLTools

Conectarse a la conexión `FireAssets`, cuya base debe ser `fireassets`, y ejecutar:

```sql
SELECT * FROM categorias ORDER BY id;
```

No ejecutar esta consulta si SQLTools muestra `sql_learning`.

---

# Paso 7 — Comprobar errores

## Nombre demasiado corto

```json
{
  "name": "AB"
}
```

Resultado esperado:

```text
422 Unprocessable Entity
```

## Categoría duplicada

Enviar dos veces el mismo nombre:

```json
{
  "name": "Mangueras"
}
```

La segunda solicitud debe responder:

```text
409 Conflict
```

---

# Checklist de la Task 04

- [ ] Se creó `register_category/__init__.py`.
- [ ] Se creó `register_category/schemas.py`.
- [ ] Se creó `register_category/router.py`.
- [ ] Existe `POST /inventory/categories`.
- [ ] Existe `GET /inventory/categories`.
- [ ] El router fue incluido en `main.py`.
- [ ] Ambos endpoints aparecen en Swagger.
- [ ] Se creó una categoría correctamente.
- [ ] Se listaron las categorías correctamente.
- [ ] Se verificó la tabla `categorias` en SQLTools.
- [ ] Se probó el error `422`.
- [ ] Se probó el error `409`.
- [ ] No se modificó el endpoint ya terminado `POST /inventory/assets`.
- [ ] No se subieron `.env`, `.venv` ni `__pycache__`.

## Resultado final

La Task 04 queda limitada a lo que faltaba:

```text
POST /inventory/categories
GET  /inventory/categories
```

El endpoint `POST /inventory/assets` queda únicamente como dependencia ya terminada.

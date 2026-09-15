# Task 04 — Test del registro de bienes

En esta tarea vamos a crear una prueba automática para el endpoint que registra bienes.

## Objetivo

Crear:

```text
tests/modules/inventory/test_register_asset.py
```

## Importante

Este test llama al endpoint real.

Como el endpoint guarda en PostgreSQL, la base de datos debe estar configurada y las tablas `categorias` y `bienes` deben existir.

## Antes de empezar

Antes de tocar código, creá o activá tu rama siguiendo:

```text
GIT_WORKFLOW.md
```

No trabajes directo sobre `main`.

---

# Paso 1 — Crear carpeta de tests

Crear si no existe:

```text
tests/modules/inventory/
```

---

# Paso 2 — Crear test

Crear:

```text
tests/modules/inventory/test_register_asset.py
```

Copiar:

```python
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.infrastructure.database.session import AsyncSessionLocal
from app.main import app


async def get_or_create_test_category() -> int:
    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                """
                INSERT INTO categorias (nombre)
                VALUES ('Mangueras')
                ON CONFLICT (nombre) DO NOTHING
                """
            )
        )
        result = await session.execute(
            text("SELECT id FROM categorias WHERE nombre = 'Mangueras'")
        )
        await session.commit()
        return int(result.scalar_one())


@pytest.mark.asyncio
async def test_register_asset_creates_asset() -> None:
    category_id = await get_or_create_test_category()
    internal_code = f"BOM-{uuid4().hex[:8]}"

    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/inventory/assets",
            json={
                "internal_code": internal_code,
                "name": "Manguera forestal",
                "category_id": category_id,
            },
        )

    assert response.status_code == 201

    data = response.json()

    print("Category ID used in test:", category_id)
    print("Response JSON:", data)

    assert isinstance(data["id"], int)
    assert data["internal_code"] == internal_code
    assert data["name"] == "Manguera forestal"
    assert data["category_id"] == category_id
```

## Qué significan los imports del test

| Import | Para qué sirve |
|---|---|
| `uuid4` | Genera un código distinto para cada test y evita repetir `codigo_interno`. |
| `pytest` | Framework que ejecuta las pruebas automáticas. |
| `ASGITransport` | Permite probar la app FastAPI sin levantar un servidor real con Uvicorn. |
| `AsyncClient` | Cliente HTTP async usado para llamar al endpoint desde el test. |
| `text` | Permite ejecutar SQL manual cuando necesitamos preparar datos de prueba. |
| `AsyncSessionLocal` | Crea una sesión de base de datos para preparar la categoría de prueba. |
| `app` | Es la aplicación FastAPI real que vamos a probar. |

Idea clave:

```text
El test importa la app real, crea datos mínimos en PostgreSQL y llama al endpoint como si fuera un cliente.
```

## Por qué el test crea o busca una categoría

El bien necesita una `categoria_id` válida.

Por eso el test primero se asegura de que exista la categoría `Mangueras` y usa su `id` real.

Así evitamos depender de que la categoría tenga siempre `id = 1`.

## Por qué usamos `uuid4`

La tabla `bienes` exige que `codigo_interno` sea único.

Si el test usara siempre `BOM-001`, la segunda ejecución podría fallar porque ese código ya existe.

Con `uuid4`, generamos un código distinto cada vez.

---

# Paso 3 — Ejecutar test

```powershell
python -m pytest -v
```

Resultado esperado:

```text
1 passed
```

---

# Paso 4 — Revisar cambios

```powershell
git status
```

No subas `.env`, `.venv`, `__pycache__` ni archivos temporales.

---

# Uso de `print()` para aprender

En el test agregamos estos `print()`:

```python
print("Category ID used in test:", category_id)
print("Response JSON:", data)
```

Sirven para ver:

- qué categoría usó el test;
- qué respondió la API.

Para ver los prints al ejecutar pytest, usá:

```powershell
python -m pytest -v -s
```

La opción `-s` permite que pytest muestre los `print()` en la consola.

## Regla importante

Estos `print()` son para aprender durante la clase.

Antes de hacer commit y subir tu Pull Request, borralos del test si el responsable lo pide.

Si quedan en el test, deben aportar información útil. Si sólo eran para mirar mientras aprendías, se eliminan.

---

# Qué entregar

- Resultado de `python -m pytest -v`.
- Explicación breve de qué prueba el test.
- Si falla, copiar el error completo.

---

# Qué aprendiste

Un test automático permite comprobar que el endpoint async sigue funcionando sin probar todo manualmente desde `/docs`.

# Task 05 — Probar todos los endpoints de la API

En esta tarea vamos a crear tests automáticos para comprobar que los endpoints de la API funcionan correctamente y que siguen comunicándose con PostgreSQL.

La Task 05 no crea endpoints nuevos. Solo verifica los endpoints que ya existen.

## Orden obligatorio de trabajo

Vamos a avanzar en dos etapas:

1. **Categorías**: crear, listar y validar categorías.
2. **Bienes**: crear un bien utilizando el `id` de una categoría válida.

La base ya contiene la categoría `Mangueras` con `id = 1`. La usaremos para observar la base, pero los tests crearán categorías con nombres únicos para no depender de ese dato fijo. Cuando probemos bienes, el test obtendrá el `id` de la categoría que acaba de crear y lo enviará como `category_id`.

El flujo será:

```text
Crear categoría → obtener category_id → crear bien con ese category_id
```

## Por qué hacemos testing

Probar manualmente desde Swagger sirve para aprender y hacer una primera comprobación, pero no alcanza para un proyecto real. Un test automático permite repetir la misma comprobación cada vez que cambiamos el código.

Los tests nos ayudan a detectar:

- rutas que dejaron de responder;
- respuestas con códigos HTTP incorrectos;
- cambios en el formato JSON;
- errores de validación;
- problemas al guardar o leer datos de PostgreSQL;
- errores que aparecen cuando otra persona modifica el proyecto.

La idea es esta:

```text
Código de la API
      ↓
Test automático
      ↓
Resultado: pasa o falla
```

---

## Paso 0 — Crear una base de datos exclusiva para tests

Antes de ejecutar esta tarea, creá una base separada para que los datos de prueba no aparezcan en el frontend ni se mezclen con `fireassets`.

La base principal queda así:

```text
fireassets       → desarrollo y datos de la aplicación
fireassets_test  → datos creados por los tests
```

### Crear la base desde `psql`

Conectate como un usuario con permisos para crear bases de datos:

```bash
psql -U postgres
```

En la consola de PostgreSQL ejecutá:

```sql
CREATE DATABASE fireassets_test;
```

Comprobá que fue creada:

```sql
\l
```

También podés conectarte directamente:

```bash
psql -U postgres -d fireassets_test
```

Y verificar el nombre de la base actual:

```sql
SELECT current_database();
```

El resultado esperado es:

```text
fireassets_test
```

### Crear las tablas en la base de tests

La base nueva comienza vacía. Antes de ejecutar los tests, aplicá allí las migraciones:

```bash
python -m alembic upgrade head
```

> Importante: este comando usa la `DATABASE_URL` configurada en el entorno. Para no aplicar la migración por accidente sobre `fireassets`, configurá temporalmente la URL apuntando a `fireassets_test` y verificá la base antes de continuar.

Los tests deben conectarse a `fireassets_test`, no a `fireassets`.

### Configurar `.env` y `.env.test`

El proyecto usa `.env` por defecto. Para los tests vamos a crear un archivo separado llamado `.env.test`.

`.env`:

```env
DATABASE_URL=postgresql+asyncpg://postgres:TU_PASSWORD@localhost:5432/fireassets
SECRET_KEY=tu-clave-local
```

`.env.test`:

```env
DATABASE_URL=postgresql+asyncpg://postgres:TU_PASSWORD@localhost:5432/fireassets_test
SECRET_KEY=tu-clave-local-para-tests
```

No subas ninguno de estos archivos a GitHub. Deben estar incluidos en `.gitignore` porque contienen credenciales locales.

La configuración de `app/config/settings.py` usa `.env` para la aplicación normal y los scripts seleccionan `.env.test` automáticamente para los tests.

### Ejecutar la Task 05 sin configurar variables manualmente

Como ya existe `.env.test`, usamos scripts que seleccionan automáticamente esa configuración, aplican las migraciones y ejecutan los tests.

Windows PowerShell:

```powershell
.\scripts\task05_run_tests_windows.ps1
```

macOS/Linux:

```bash
./scripts/task05_run_tests_mac.sh
```

Los scripts verifican que `.env.test` exista y trabajan sobre `fireassets_test`. No modifican `.env` ni la base `fireassets`.

Los archivos son:

- `scripts/task05_run_tests_windows.ps1`
- `scripts/task05_run_tests_mac.sh`

## Requisito previo obligatorio

Antes de comenzar, completá:

```text
vscode-tools.md
```

También deben estar funcionando:

- PostgreSQL;
- la base `fireassets_test`;
- las tablas `categorias` y `bienes` dentro de `fireassets_test`;
- el entorno virtual;
- las dependencias del proyecto;
- los endpoints implementados.

Si todavía no instalaste las dependencias, hacelo desde la raíz del proyecto:

```bash
python -m pip install -r requirements.txt
```

Ese archivo debe incluir `pytest` y `pytest-asyncio`, porque los tests usan `pytest` y funciones `async`.

Verificá la base con:

```sql
SELECT current_database(), current_user;
```

El resultado debe indicar `fireassets`.

---

# 1. Endpoints que vamos a probar

### Etapa 1 — Categorías

| Método | Endpoint | Qué comprobaremos |
|---|---|---|
| `GET` | `/` | Que la API esté funcionando. |
| `GET` | `/health` | Que el servicio responda correctamente. |
| `POST` | `/inventory/categories` | Que una categoría pueda guardarse. |
| `GET` | `/inventory/categories` | Que las categorías puedan consultarse. |
| `POST` | `/inventory/assets` | **Etapa 2:** que un bien pueda guardarse usando una categoría válida. |

### Etapa 2 — Bienes

El endpoint de bienes se prueba solamente después de completar los tests de categorías.

También probaremos errores esperados:

- datos inválidos → `422`;
- categoría duplicada → `409`;
- código interno de bien duplicado → `409`.

---

# 2. Crear la estructura de tests

Crear estos archivos:

```text
tests/test_main_endpoints.py
tests/modules/inventory/test_category_endpoints.py
tests/modules/inventory/test_asset_endpoints.py
```

## Windows / PowerShell

```powershell
New-Item -ItemType Directory -Force tests/modules/inventory
New-Item -ItemType File -Force tests/test_main_endpoints.py
New-Item -ItemType File -Force tests/modules/inventory/test_category_endpoints.py
New-Item -ItemType File -Force tests/modules/inventory/test_asset_endpoints.py
```

## macOS o Linux

```bash
mkdir -p tests/modules/inventory
touch tests/test_main_endpoints.py
touch tests/modules/inventory/test_category_endpoints.py
touch tests/modules/inventory/test_asset_endpoints.py
```

Si las carpetas o archivos ya existen, no los reemplaces. Abrilos y agregá los tests correspondientes.

---

# 3. Test de los endpoints principales

Abrir:

```text
tests/test_main_endpoints.py
```

Copiar:

```python
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_root_endpoint() -> None:
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "message": "Fire Control API",
        "status": "running",
    }


@pytest.mark.asyncio
async def test_health_endpoint() -> None:
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

## Explicación de los imports

| Import | Significado |
|---|---|
| `pytest` | Ejecuta los tests y proporciona el marcador `asyncio`. |
| `ASGITransport` | Permite llamar a FastAPI directamente sin levantar Uvicorn. |
| `AsyncClient` | Simula un cliente HTTP que hace solicitudes a la API. |
| `app` | Es la aplicación FastAPI real que estamos probando. |

## Explicación de variables y funciones

- `test_root_endpoint`: función que verifica la ruta `/`.
- `test_health_endpoint`: función que verifica la ruta `/health`.
- `transport`: conecta el cliente HTTP de prueba con la aplicación FastAPI.
- `client`: representa al cliente que realiza las solicitudes.
- `response`: contiene el código HTTP y el JSON devuelto.
- `status_code`: indica si la operación fue exitosa.
- `response.json()`: convierte la respuesta en un diccionario Python.

No usamos un servidor real porque `ASGITransport` ejecuta la aplicación dentro del test.

---

# 4. Test de crear y listar categorías

Abrir:

```text
tests/modules/inventory/test_category_endpoints.py
```

Copiar:

```python
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


def unique_category_name() -> str:
    return f"Categoria-{uuid4().hex[:8]}"


@pytest.mark.asyncio
async def test_create_category() -> None:
    category_name = unique_category_name()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/inventory/categories",
            json={"name": category_name},
        )

    assert response.status_code == 201

    data = response.json()

    assert isinstance(data["id"], int)
    assert data["name"] == category_name


@pytest.mark.asyncio
async def test_list_categories() -> None:
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/inventory/categories")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_create_category_with_invalid_name() -> None:
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/inventory/categories",
            json={"name": "AB"},
        )

    assert response.status_code == 422
```

## Explicación de los imports

| Import | Significado |
|---|---|
| `uuid4` | Genera nombres diferentes para evitar duplicados entre ejecuciones. |
| `pytest` | Ejecuta las funciones de prueba. |
| `ASGITransport` | Conecta el test con FastAPI sin iniciar un servidor externo. |
| `AsyncClient` | Envía solicitudes HTTP asincrónicas. |
| `app` | Aplicación FastAPI real. |

## Explicación de funciones y variables

- `unique_category_name`: crea un nombre único para cada test.
- `category_name`: guarda el nombre que enviaremos a la API.
- `test_create_category`: comprueba que una categoría se guarda correctamente.
- `test_list_categories`: comprueba que el endpoint devuelve una lista.
- `test_create_category_with_invalid_name`: comprueba la validación de Pydantic.
- `data`: contiene el JSON de la categoría creada.

Usamos nombres únicos porque la columna `nombre` tiene una restricción `unique=True`.

---

# 5. Test de guardar bienes

Abrir:

```text
tests/modules/inventory/test_asset_endpoints.py
```

Copiar:

```python
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.infrastructure.database.session import AsyncSessionLocal
from app.main import app


async def create_test_category() -> int:
    async with AsyncSessionLocal() as session:
        category_name = f"Categoria-test-{uuid4().hex[:8]}"

        result = await session.execute(
            text(
                """
                INSERT INTO categorias (nombre)
                VALUES (:category_name)
                RETURNING id
                """
            ),
            {"category_name": category_name},
        )
        category_id = result.scalar_one()
        await session.commit()

        return int(category_id)


@pytest.mark.asyncio
async def test_create_asset() -> None:
    category_id = await create_test_category()
    internal_code = f"TEST-{uuid4().hex[:8]}"
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/inventory/assets",
            json={
                "internal_code": internal_code,
                "name": "Manguera de prueba",
                "category_id": category_id,
            },
        )

    assert response.status_code == 201

    data = response.json()

    assert isinstance(data["id"], int)
    assert data["internal_code"] == internal_code
    assert data["name"] == "Manguera de prueba"
    assert data["category_id"] == category_id
```

## Explicación de los imports

| Import | Significado |
|---|---|
| `uuid4` | Genera códigos y nombres únicos. |
| `pytest` | Ejecuta el test asincrónico. |
| `ASGITransport` | Permite probar FastAPI directamente. |
| `AsyncClient` | Simula un cliente HTTP. |
| `text` | Permite ejecutar una consulta SQL preparada. |
| `AsyncSessionLocal` | Abre una sesión asincrónica contra PostgreSQL. |
| `app` | Aplicación FastAPI real. |

## Explicación de funciones y variables

- `create_test_category`: crea una categoría temporal y devuelve su `id`.
- `session`: sesión que permite ejecutar SQL contra PostgreSQL.
- `category_name`: nombre único de la categoría de prueba.
- `result`: resultado devuelto por PostgreSQL.
- `category_id`: identificador necesario para crear el bien.
- `test_create_asset`: comprueba el endpoint de bienes.
- `internal_code`: código único del bien.
- `data`: respuesta JSON devuelta por la API.

El test crea primero una categoría porque el bien necesita una clave foránea válida.

---

# 6. Por qué usamos `async` y `await`

La aplicación usa SQLAlchemy asíncrono. Por eso los tests deben respetar el mismo modelo.

```python
async def test_create_asset() -> None:
    response = await client.post(...)
```

- `async def`: define una función que puede trabajar de forma asincrónica.
- `await`: espera el resultado de una operación asincrónica.

Si se elimina `await`, Python no ejecuta correctamente la solicitud y devuelve una corrutina en lugar del resultado.

---

# 7. Ejecutar todos los tests

Desde la raíz del proyecto y con el entorno virtual activo:

### Windows

```powershell
python -m pytest -v -s
```

### macOS o Linux

```bash
python -m pytest -v -s
```

- `-m pytest`: ejecuta pytest usando el Python actual.
- `-v`: muestra el nombre de cada test.
- `-s`: muestra los `print()` de la consola.

Para ejecutar un archivo específico:

```bash
python -m pytest tests/test_main_endpoints.py -v -s
python -m pytest tests/modules/inventory/test_category_endpoints.py -v -s
python -m pytest tests/modules/inventory/test_asset_endpoints.py -v -s
```

Resultado esperado aproximado:

```text
6 passed
```

La cantidad exacta puede variar si agregamos más casos.

---

# 8. Cómo interpretar un fallo

| Resultado | Significado |
|---|---|
| `PASSED` | El comportamiento esperado funcionó. |
| `FAILED` | El resultado real no coincide con el esperado. |
| `422` | Los datos no cumplen las validaciones. |
| `409` | Hay un conflicto, normalmente un valor duplicado. |
| `500` | Ocurrió un error inesperado en la aplicación o la base. |
| Error de conexión | PostgreSQL o la URL de conexión no están disponibles. |

No borres el error cuando un test falla. Copialo completo para analizarlo.

---

# 9. Regla sobre los `print()`

Los `print()` pueden utilizarse durante la clase para observar:

- el `category_id`;
- el JSON recibido;
- el resultado de una consulta;
- el flujo de una función.

Antes de hacer commit:

- eliminá los `print()` temporales; o
- dejalos solo si aportan información permanente y útil.

---

# 10. Checklist final

- [ ] Se creó el test de `/`.
- [ ] Se creó el test de `/health`.
- [ ] Se creó el test de `POST /inventory/categories`.
- [ ] Se creó el test de `GET /inventory/categories`.
- [ ] Se creó el test de `POST /inventory/assets`.
- [ ] Se probó una validación `422`.
- [ ] Se verificó que PostgreSQL sea `fireassets`.
- [ ] Todos los tests pasan.
- [ ] Se revisaron los errores sin ocultarlos.
- [ ] Se eliminaron los `print()` temporales.
- [ ] No se subieron `.env`, `.venv` ni `__pycache__`.
- [ ] Se creó una rama de trabajo.
- [ ] Se hizo commit con un mensaje claro.
- [ ] Se subió la rama para crear el Pull Request.

## Resultado final

Al terminar, tendremos evidencia automática de que la aplicación responde, que las categorías se pueden crear y listar, y que los bienes se guardan correctamente en PostgreSQL.

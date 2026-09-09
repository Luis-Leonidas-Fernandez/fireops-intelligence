# Task 03 — Registrar un bien usando la base de datos

En esta tarea vamos a crear el endpoint `POST /inventory/assets` para guardar un bien real en PostgreSQL.

## Objetivo

Crear o modificar:

```text
app/modules/inventory/register_asset/schemas.py
app/modules/inventory/register_asset/router.py
app/main.py
```

## Mapa de archivos y orden de implementación

Esta tarea se escribe en tres lugares distintos. No copies todo en un solo archivo. Cada pieza tiene una responsabilidad.

| Orden | Archivo | Qué se escribe ahí | Por qué va ahí |
|---|---|---|---|
| 1 | `app/modules/inventory/register_asset/schemas.py` | Clases `RegisterAssetRequest` y `RegisterAssetResponse` | Define la forma de los datos que entran y salen del endpoint |
| 2 | `app/modules/inventory/register_asset/router.py` | Función `register_asset` y router `POST /inventory/assets` | Define la ruta HTTP y la lógica mínima para guardar el bien |
| 3 | `app/main.py` | `app.include_router(register_asset_router)` | Conecta el router nuevo con la aplicación principal |

El orden importa:

```text
primero schemas.py
  ↓
después router.py
  ↓
por último main.py
  ↓
recién ahí probar en /docs
```

Si intentás crear el router antes de los schemas, Python no va a encontrar `RegisterAssetRequest` ni `RegisterAssetResponse`.
Si olvidás conectar el router en `main.py`, el endpoint no va a aparecer en `/docs`.


## Diagrama simple del flujo de datos de un endpoint

Este diagrama sirve para entender cualquier endpoint que creemos en el proyecto.


![Diagrama visual del flujo de datos de un endpoint](../assets/endpoint-data-flow-nodes.png)


### Lectura guiada del diagrama

Leé la imagen de izquierda a derecha y después bajá hacia la base de datos. Este flujo muestra qué ocurre desde que alguien envía datos hasta que PostgreSQL los guarda y la API responde.

## 1. Cliente

El cliente es quien llama al endpoint. Puede ser:

- Swagger docs, desde `http://127.0.0.1:8000/docs`;
- un frontend;
- Postman o Insomnia;
- un test automatizado.

El cliente envía un JSON parecido a este:

```json
{
  "internal_code": "BOM-001",
  "name": "Manguera forestal",
  "category_id": 1
}
```

Ese JSON todavía no es confiable. Puede venir incompleto, con campos mal escritos o con valores inválidos.

## 2. Schema Request y validaciones de entrada

El `Schema Request` valida lo que entra antes de que la función trabaje con esos datos. En esta tarea usamos:

```python
RegisterAssetRequest
```

Este schema revisa reglas como:

```python
internal_code: str = Field(min_length=3, max_length=30)
name: str = Field(min_length=3, max_length=150)
category_id: int = Field(gt=0)
```

Eso significa:

| Campo | Validación | Por qué importa |
|---|---|---|
| `internal_code` | texto entre 3 y 30 caracteres | evita códigos vacíos o demasiado largos |
| `name` | texto entre 3 y 150 caracteres | evita nombres vacíos o absurdamente largos |
| `category_id` | número mayor que 0 | evita IDs negativos o inválidos |

Si el JSON no cumple estas reglas, FastAPI corta el flujo y responde un error `422`.

Importante:

```text
Si falla la validación del Request, no se llega al router, no se crea el modelo y no se guarda nada en PostgreSQL.
```

## 3. Router y función del endpoint

El `Router` define la URL y la función que se ejecuta. En esta tarea es:

```python
@router.post("")
async def register_asset(...):
```

La función `register_asset()` es el punto donde empieza la acción real.

Su responsabilidad mínima es:

1. recibir un `RegisterAssetRequest` ya validado;
2. crear un objeto `Asset`;
3. pedirle a SQLAlchemy que lo guarde;
4. devolver un `RegisterAssetResponse`.

El router NO representa una tabla. El router representa una acción HTTP.

## 4. Modelo de base de datos

El modelo `Asset` representa la tabla `bienes`.

Cuando hacemos:

```python
asset = Asset(
    codigo_interno=request.internal_code,
    nombre=request.name,
    categoria_id=request.category_id,
)
```

creamos un objeto Python que SQLAlchemy sabe convertir en una fila de PostgreSQL.

Pero ojo:

```text
Crear Asset(...) NO guarda nada todavía.
Sólo crea un objeto en memoria.
```

## 5. Session de SQLAlchemy

La `session` es el puente entre Python y PostgreSQL.

Pensala como una mesa de trabajo temporal. Primero colocamos cambios sobre esa mesa y después decidimos si los confirmamos o no.

En esta tarea usamos:

```python
session.add(asset)
await session.commit()
await session.refresh(asset)
```

Qué hace cada línea:

| Código | Qué hace | Todavía puede fallar |
|---|---|---|
| `session.add(asset)` | prepara el objeto para guardarlo | sí, todavía no está confirmado |
| `await session.commit()` | confirma y guarda en PostgreSQL | sí, puede fallar por restricciones de la DB |
| `await session.refresh(asset)` | vuelve a leer el objeto desde la DB | sí, pero normalmente se usa para obtener el `id` generado |

Ejemplo importante:

```text
Asset(...) crea el objeto.
session.add(asset) lo pone en la operación pendiente.
commit() confirma la operación.
refresh() trae datos generados por PostgreSQL, como el id.
```

¿Por qué no guardamos directo?

Porque la session permite trabajar con transacciones. Una transacción es una operación que debe completarse entera o no completarse.

Ejemplo futuro:

```text
crear bien
crear movimiento inicial
crear registro de auditoría
```

Si una parte falla, podemos cancelar todo para no dejar datos a medias.

## 6. Validaciones de base de datos

Además de las validaciones del schema, PostgreSQL también valida reglas propias de la tabla.

Ejemplos:

| Regla | Dónde se define | Qué evita |
|---|---|---|
| `nullable=False` | modelo / migración | evita guardar campos obligatorios vacíos |
| `unique=True` | modelo / migración | evita repetir `codigo_interno` |
| `ForeignKey("categorias.id")` | modelo / migración | evita crear bienes con una categoría inexistente |

Esto es clave:

```text
El schema valida la forma de los datos antes de entrar.
La base de datos protege la consistencia final de los datos guardados.
```

Por ejemplo, aunque `category_id = 999` sea un número válido para Pydantic, PostgreSQL puede rechazarlo si no existe una categoría con `id = 999`.

## 7. PostgreSQL

PostgreSQL guarda el registro en la tabla `bienes`.

Si todo sale bien, genera un `id` para el nuevo bien. Ese `id` no lo inventa FastAPI. Lo genera la base de datos.

Por eso después del `commit()` hacemos:

```python
await session.refresh(asset)
```

Así el objeto `asset` queda actualizado con el `id` real.

## 8. Schema Response

El `Schema Response` define qué datos devolvemos al cliente. En esta tarea usamos:

```python
RegisterAssetResponse
```

No siempre devolvemos todo lo que existe en la tabla. Devolvemos sólo lo que queremos exponer hacia afuera.

Ejemplo:

```json
{
  "id": 1,
  "internal_code": "BOM-001",
  "name": "Manguera forestal",
  "category_id": 1
}
```

## Resumen mental

```text
Request valida lo que entra.
Router ejecuta la acción.
Modelo representa lo que se quiere guardar.
Session administra la operación contra PostgreSQL.
PostgreSQL aplica reglas finales y guarda.
Response define lo que vuelve al cliente.
```

No memorices el dibujo. Entendé el recorrido. Cada endpoint nuevo va a repetir una versión parecida de este flujo.

```text
Cliente / navegador / Swagger docs
        │
        │ envía JSON
        ▼
Schema de entrada
RegisterAssetRequest
        │
        │ valida los datos
        ▼
Router / endpoint
register_asset()
        │
        │ ejecuta la acción solicitada
        ▼
Modelo de base de datos
Asset
        │
        │ se agrega a la sesión
        ▼
SQLAlchemy Session
session.add()
session.commit()
session.refresh()
        │
        │ guarda en PostgreSQL
        ▼
Tabla bienes
PostgreSQL
        │
        │ devuelve el registro creado
        ▼
Schema de salida
RegisterAssetResponse
        │
        │ responde JSON
        ▼
Cliente / navegador / Swagger docs
```

## Cómo leer este diagrama

| Parte | Qué significa | En qué archivo suele estar |
|---|---|---|
| Cliente | Quien llama al endpoint | Navegador, Swagger docs, frontend o test |
| Schema de entrada | Define qué datos se aceptan | `schemas.py` |
| Router / endpoint | Define la URL y la función que se ejecuta | `router.py` |
| Modelo | Representa la tabla de la base de datos | `models.py` |
| Session | Es el puente entre Python y PostgreSQL | `app/infrastructure/database/session.py` |
| Tabla | Lugar donde quedan guardados los datos | PostgreSQL |
| Schema de salida | Define qué JSON se responde | `schemas.py` |

La idea importante es esta:

```text
El endpoint no es sólo una función.
Es un recorrido completo desde un JSON de entrada hasta un JSON de respuesta.
```

## Flujo específico de este endpoint

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

## Antes de empezar

Antes de tocar código, creá o activá tu rama siguiendo:

```text
GIT_WORKFLOW.md
```

No trabajes directo sobre `main`.

---


# Paso 0 — Crear archivos `__init__.py` vacíos

Antes de crear `schemas.py` y `router.py`, vamos a preparar las carpetas para que Python las pueda importar de forma clara.

## Qué archivos crear

Verificá o creá estos archivos vacíos:

```text
app/modules/__init__.py
app/modules/inventory/__init__.py
app/modules/inventory/register_asset/__init__.py
app/modules/inventory/shared/__init__.py
```

Si también existe la carpeta `get_asset`, creá este archivo:

```text
app/modules/inventory/get_asset/__init__.py
```

## Cómo crearlos en Windows

Desde PowerShell, parado en la raíz del proyecto:

```powershell
New-Item -ItemType File -Force app/modules/__init__.py
New-Item -ItemType File -Force app/modules/inventory/__init__.py
New-Item -ItemType File -Force app/modules/inventory/register_asset/__init__.py
New-Item -ItemType File -Force app/modules/inventory/shared/__init__.py
New-Item -ItemType File -Force app/modules/inventory/get_asset/__init__.py
```

## Qué contenido llevan

Por ahora pueden quedar vacíos.

```python
# Este archivo puede quedar vacío.
# Le indica a Python que esta carpeta forma parte de un paquete importable.
```

Más adelante podrían usarse para exponer imports más cómodos, pero ahora NO hace falta.

## Para qué sirve `__init__.py`

Un archivo `__init__.py` sirve para marcar una carpeta como parte de un paquete Python.

Un paquete es una carpeta desde donde Python puede importar código.

Por ejemplo, si queremos hacer este import:

```python
from app.modules.inventory.register_asset.router import router as register_asset_router
```

Python tiene que poder recorrer este camino:

```text
app
  ↓
modules
  ↓
inventory
  ↓
register_asset
  ↓
router.py
```

Cada carpeta de ese camino forma parte del import.

Aunque en Python moderno algunos imports pueden funcionar sin `__init__.py`, en este proyecto vamos a usar una regla simple para aprender bien:

```text
Si una carpeta contiene código Python que vamos a importar, esa carpeta debe tener __init__.py.
```

Esto nos ayuda a evitar magia innecesaria y hace que la estructura sea más fácil de entender.

## Por qué los creamos ahora

Los creamos antes de `schemas.py` y `router.py` porque después vamos a importar código desde estas carpetas.

Si las carpetas están preparadas desde el principio, el camino del import queda más claro para todos.

---

# Paso 1 — Crear schemas

Crear:

```text
app/modules/inventory/register_asset/schemas.py
```

Copiar:

```python
# Archivo donde va este código:
# app/modules/inventory/register_asset/schemas.py
#
# Este archivo NO guarda datos en la base.
# Sólo define qué datos espera recibir y qué datos va a responder el endpoint.

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
# Archivo donde va este código:
# app/modules/inventory/register_asset/router.py
#
# Acá definimos la ruta POST /inventory/assets.
# Esta es la función que recibe el JSON, crea el Asset y lo guarda en PostgreSQL.

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


# Esta función pertenece al router de registrar bienes.
# No va en main.py. No va en models.py.
# Va en app/modules/inventory/register_asset/router.py.
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

    print("Asset before save:", asset.codigo_interno, asset.nombre, asset.categoria_id)

    session.add(asset)
    await session.commit()
    await session.refresh(asset)

    print("Asset created with ID:", asset.id)

    return RegisterAssetResponse(
        id=asset.id,
        internal_code=asset.codigo_interno,
        name=asset.nombre,
        category_id=asset.categoria_id,
    )
```

## Qué hace la función `register_asset`

La función `register_asset` vive en:

```text
app/modules/inventory/register_asset/router.py
```

Hace este recorrido:

1. Recibe el JSON que llega desde `/docs` o desde un cliente HTTP.
2. FastAPI lo convierte en `RegisterAssetRequest`.
3. Crea un objeto `Asset` usando el modelo de `app/modules/inventory/shared/models.py`.
4. Lo agrega a la sesión con `session.add(asset)`.
5. Guarda definitivamente con `await session.commit()`.
6. Recarga el objeto con `await session.refresh(asset)` para obtener el `id`.
7. Devuelve un `RegisterAssetResponse`.

Pensalo así:

```text
schemas.py = define la forma de los datos
router.py  = define qué hacer cuando llaman al endpoint
main.py    = conecta el endpoint con la app
```

---

# Paso 3 — Conectar router en `app/main.py`

Abrir:

```text
app/main.py
```

Agregar import:

```python
# Archivo donde va este import:
# app/main.py
#
# Este import trae el router que creamos en:
# app/modules/inventory/register_asset/router.py
from app.modules.inventory.register_asset.router import router as register_asset_router
```

Después de crear `app`, agregar:

```python
# Archivo donde va esta línea:
# app/main.py
#
# Sin esta línea, FastAPI no muestra POST /inventory/assets en /docs.
app.include_router(register_asset_router)
```

---

# Checklist de orientación antes de probar

Antes de levantar el servidor, verificá esto:

- [ ] Existe la carpeta `app/modules/inventory/register_asset/`.
- [ ] Existen los archivos `__init__.py` indicados en el Paso 0.
- [ ] Existe `app/modules/inventory/register_asset/schemas.py`.
- [ ] Existe `app/modules/inventory/register_asset/router.py`.
- [ ] La función `register_asset` está en `router.py`, no en `main.py`.
- [ ] `main.py` importa `register_asset_router`.
- [ ] `main.py` tiene `app.include_router(register_asset_router)`.
- [ ] Las tablas `categorias` y `bienes` ya existen en PostgreSQL.

Si falta cualquiera de estos puntos, no pruebes todavía. Primero corregí la ubicación del código.

---

# Paso 4 — Preparar una categoría de prueba

Antes de registrar un bien, debe existir una categoría.

Entrar a PostgreSQL:

```powershell
psql -U postgres -d fireassets
```

Crear una categoría de prueba:

```sql
INSERT INTO categorias (nombre)
VALUES ('Mangueras')
ON CONFLICT (nombre) DO NOTHING;
```

Buscar el `id` de esa categoría:

```sql
SELECT id, nombre FROM categorias WHERE nombre = 'Mangueras';
```

Anotá el valor de `id`.

Ejemplo:

```text
id | nombre
1  | Mangueras
```

Salir:

```sql
\q
```

> Importante: en el próximo paso usá el `id` real que te devolvió PostgreSQL. Puede ser `1`, pero también puede ser otro número.

---

# Paso 5 — Probar manualmente

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

Si tu categoría tiene otro `id`, reemplazá `1` por el número real.

Respuesta esperada:

```json
{
  "id": 1,
  "internal_code": "BOM-001",
  "name": "Manguera forestal",
  "category_id": 1
}
```

El `id` del bien puede ser otro número.

> Si ya existe un bien con `BOM-001`, usá otro código, por ejemplo `BOM-002`.

---

# Paso 6 — Verificar en PostgreSQL

Entrar:

```powershell
psql -U postgres -d fireassets
```

Consultar:

```sql
SELECT id, codigo_interno, nombre, categoria_id FROM bienes;
```

Deberías ver el bien registrado.

También podés ver el bien junto con su categoría:

```sql
SELECT
    bienes.id,
    bienes.codigo_interno,
    bienes.nombre AS bien,
    categorias.nombre AS categoria
FROM bienes
JOIN categorias ON categorias.id = bienes.categoria_id;
```

Salir:

```sql
\q
```

---

# Uso de `print()` para aprender

En el código del endpoint agregamos estos `print()`:

```python
print("Asset before save:", asset.codigo_interno, asset.nombre, asset.categoria_id)
print("Asset created with ID:", asset.id)
```

Sirven para ver en la terminal qué pasa antes y después de guardar el bien.

Cuando levantes el servidor y pruebes el endpoint desde `/docs`, mirá la terminal donde corre Uvicorn.

Deberías ver mensajes parecidos a:

```text
Asset before save: BOM-001 Manguera forestal 1
Asset created with ID: 1
```

## Regla importante

Estos `print()` son para aprender durante la clase.

Antes de hacer commit y subir tu Pull Request, borralos del endpoint.

El código final no debe quedar con prints de práctica.

---

# Qué entregar

- Captura o texto de `/docs` funcionando.
- Resultado del `SELECT` en PostgreSQL.
- Explicación breve de qué hacen `session.add`, `commit` y `refresh`.

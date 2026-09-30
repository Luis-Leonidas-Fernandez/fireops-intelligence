# Tarea 06: listar activos y consultar por ID

Esta guía define el alcance de implementación y verificación de la Tarea 06; no implementa los endpoints. El repositorio ya permite registrar activos y consultar categorías, pero todavía no cuenta con rutas GET para activos.

## Objetivo

Implementar y probar únicamente estos dos endpoints de lectura: listar todos los activos y consultar un activo por su ID. Reutilizar los esquemas de respuesta y la dependencia de base de datos existentes. Cada prueba debe preparar su propio estado y no depender del orden de ejecución, de filas preexistentes ni de identificadores fijos.

## Estado relevante del repositorio

- `app/modules/inventory/register_asset/router.py` define `POST /inventory/assets`, recibe una `AsyncSession` mediante `get_database_session`, escribe en `bienes` y devuelve `RegisterAssetResponse`.
- `app/modules/inventory/register_asset/schemas.py` define `RegisterAssetResponse` con `id`, `internal_code`, `name` y `category_id`.
- `app/modules/inventory/shared/models.py` mapea `Asset` a `bienes` y `Category` a `categorias`; `Asset.categoria_id` referencia `Category.id`.
- `app/modules/inventory/register_category/router.py` define `POST /inventory/categories` y `GET /inventory/categories`; utiliza `select` de SQLAlchemy y ordena las categorías por ID.
- `app/infrastructure/database/session.py` proporciona `AsyncSessionLocal` y `get_database_session`. Esta dependencia abre una sesión nueva; no aísla ni limpia por sí sola los datos de prueba.
- `app/main.py` incluye actualmente las rutas de registro de activos y categorías. Aún no hay rutas GET para activos registradas.
- Las pruebas actuales de inventario usan `pytest.mark.asyncio`, `HTTPX AsyncClient` con `ASGITransport` y nombres de categoría únicos. La prueba de activos inserta y confirma una categoría mediante `AsyncSessionLocal` y SQL antes de registrar un activo. No hay un `conftest.py` compartido, una sobreescritura de la dependencia para pruebas, una fixture de rollback ni un mecanismo de limpieza por prueba.
- `pyproject.toml` configura fixtures y bucles de prueba de pytest-asyncio con alcance de sesión. `Makefile` ofrece `make test` (`pytest -v`), `make lint` y `make format`.
- Los scripts `scripts/task05_run_tests_mac.sh` y `scripts/task05_run_tests_windows.ps1` seleccionan `.env.test`, ejecutan `alembic upgrade head` y luego `python -m pytest -v -s`. Los scripts `scripts/test-up.sh` y `scripts/test-up.ps1` inician la aplicación contra `fireassets_test`; sirven para pruebas manuales de API, no para aislar pruebas automatizadas.

## Endpoints y comportamiento esperado

| Método y ruta | Resultado requerido |
|---|---|
| `GET /inventory/assets/` | `200 OK`; todos los activos ordenados por `Asset.id` ascendente; arreglo JSON. Debe devolver `[]` únicamente cuando la prueba haya establecido un contexto sin activos. |
| `GET /inventory/assets/{asset_id}` | `200 OK` y el activo solicitado si existe. |
| `GET /inventory/assets/{asset_id}` con un ID entero inexistente | `404 Not Found`. |

FastAPI puede atender la ruta de colección sin la barra final mediante su redirección habitual. Las pruebas y ejemplos deben usar la ruta canónica con barra final. Un parámetro de ruta que no sea un entero debe producir la respuesta de validación `422` de FastAPI.

- Reutilizar `RegisterAssetResponse`; no crear otro esquema. Cada objeto expone `id`, `internal_code`, `name` y `category_id`.
- Consultar mediante SQLAlchemy y el modelo `Asset`. Aplicar el orden ascendente por ID en la consulta, no después de recuperar las filas.
- La colección incluye todas las filas visibles para la sesión. Una lista vacía no implica que una base de pruebas compartida esté globalmente vacía: verificar `[]` solo cuando el mecanismo de aislamiento garantice un estado inicial sin activos.
- El endpoint de detalle debe buscar por clave primaria y devolver `404` con un mensaje claro si no existe el activo. El texto exacto debe coincidir entre implementación y prueba; por ejemplo: `Asset not found.`
- No exponer en la respuesta los nombres internos del ORM (`codigo_interno`, `nombre`, `categoria_id`).

## Archivos previstos para la implementación

```text
app/modules/inventory/get_asset/router.py   # nueva ruta de lectura
app/main.py                                  # registrar la ruta sin quitar las existentes
tests/modules/inventory/test_get_asset_endpoint.py
```

Ya existe `app/modules/inventory/get_asset/__init__.py`; no recrearlo ni reemplazarlo. Reutilizar estos componentes:

```text
app/modules/inventory/shared/models.py
app/modules/inventory/register_asset/schemas.py
app/infrastructure/database/session.py
```

No se necesita una migración: ambas tablas ya existen y esta tarea solo agrega consultas.

## Crear los archivos que faltan

Ejecutá los comandos desde la raíz del repositorio. En el estado actual faltan `router.py` y el archivo nuevo de tests. `app/main.py`, el directorio de tests y `get_asset/__init__.py` ya existen: **no los crees ni reemplaces**. La fixture `isolated_asset_session` se agregará dentro del archivo de tests.

### Windows — PowerShell

```powershell
New-Item -ItemType File -Path app/modules/inventory/get_asset/router.py
New-Item -ItemType File -Path tests/modules/inventory/test_get_asset_endpoint.py
```

`New-Item` se usa sin `-Force` para no reemplazar archivos existentes. Si alguno ya existe en tu copia, no ejecutes su comando: editá el archivo existente.

### macOS o Linux — Terminal

```bash
touch app/modules/inventory/get_asset/router.py
touch tests/modules/inventory/test_get_asset_endpoint.py
```

`touch` crea los archivos si no existen y conserva su contenido si ya existen. Si alguno ya está creado, podés continuar editándolo sin volver a ejecutar el comando correspondiente.

## Reutilización y datos de prueba

- Seguir las convenciones existentes: `APIRouter(prefix="/inventory/assets", tags=["Inventory"])` y `Annotated[AsyncSession, Depends(get_database_session)]`.
- Reutilizar `Asset`, `RegisterAssetResponse` y la dependencia de base de datos compartida. No duplicar modelos, esquemas ni configuración de sesiones.
- Reutilizar las convenciones existentes de pytest, HTTPX y SQLAlchemy asíncrono. Actualmente no hay `conftest.py` ni fixtures compartidas; definir la fixture `isolated_asset_session` en `tests/modules/inventory/test_get_asset_endpoint.py` para mantenerla acotada a los tests de esta tarea. No crear una segunda configuración de base de datos.
- Obtener explícitamente el ID de categoría: crear una categoría con nombre único mediante el endpoint existente o insertar una `Category` única desde la sesión de base de datos de la fixture. Elegir una categoría semánticamente adecuada para cada activo (por ejemplo, una categoría de mangueras para una manguera y una de cascos para un casco); buscarla o crearla explícitamente si no existe. Nunca asumir que `category_id=1` ni ningún otro ID fijo.

## Aislamiento de pruebas

La suite actual no tiene una fixture compartida. Además, `get_database_session` abre una sesión nueva mediante `AsyncSessionLocal`, y los endpoints `POST` de bienes y categorías llaman a `session.commit()`. Si los tests usan esa dependencia sin sobrescribirla, cada petición abre su propia sesión y puede dejar los datos confirmados en `fireassets_test`; un rollback de otra sesión no los revierte. La solución elegida es **una transacción externa por test, compartida con la aplicación mediante un override de FastAPI, y rollback automático al terminar**.

### Idea general

Queremos que cada test pueda preparar datos y probar la API sin dejar cambios para el siguiente:

```text
Fixture de pytest       controla la preparación y el cierre de cada test
        ↓
Override de FastAPI     hace que el endpoint use la sesión del test
        ↓
Transacción externa     contiene todos los cambios de esa sesión
        ↓
SAVEPOINT               permite que session.commit() no confirme la transacción externa
        ↓
ROLLBACK                revierte los cambios al terminar el test
```

La fixture también verifica que esté conectada a `fireassets_test` y establece un estado inicial sin bienes dentro de la transacción. Por eso, el borrado de datos antiguos se revierte junto con los cambios creados por la prueba.

### Mecanismo elegido: una fixture transaccional por test

Implementá `isolated_asset_session` en `tests/modules/inventory/test_get_asset_endpoint.py`. La fixture debe hacer lo siguiente, en este orden:

1. **Abrir una conexión y la transacción externa.** Usá el `engine` real de `app.infrastructure.database.session` para abrir un `AsyncConnection` y comenzá una transacción explícita con `await connection.begin()`.
2. **Proteger la base de datos.** Dentro de esa transacción, consultá `SELECT current_database()` y continuá solo si el resultado es exactamente `fireassets_test`. Si el nombre no coincide, abortá la fixture antes de cualquier escritura. Las pruebas deben iniciarse mediante los scripts de la Task 05, que cargan `.env.test` antes de importar la aplicación.
3. **Crear la sesión vinculada a la transacción.** Instanciá una `AsyncSession` enlazada a esa misma conexión y configurá `join_transaction_mode="create_savepoint"`:

   ```python
   test_session = AsyncSession(
       bind=connection,
       join_transaction_mode="create_savepoint",
   )
   ```

   El parámetro es esencial: hace que las operaciones de la sesión usen un SAVEPOINT dentro de la transacción externa, en lugar de tomar control de ella.
4. **Establecer un estado conocido antes de cada prueba.** Una transacción con rollback revierte los cambios del test, pero no oculta filas que ya estaban confirmadas antes de abrirla. Por eso, después de verificar el nombre de la base, eliminá los activos existentes con `delete(Asset)` usando `test_session`, sin confirmar la transacción externa. Esta eliminación ocurre solo durante la preparación, dentro de la transacción que luego se revierte; así, la prueba comienza sin activos y el estado previo de la base se restaura al final. No borres categorías: cada test debe crear las categorías únicas que necesite y conservar los IDs devueltos.
5. **Sobrescribir la dependencia exacta de FastAPI.** Guardá si ya había un override para `get_database_session` y su valor. Asigná a `app.dependency_overrides[get_database_session]` una dependencia asíncrona que haga `yield test_session`. Así, los endpoints reciben **la misma instancia de `AsyncSession` y la misma conexión/transacción externa** que preparó la fixture; no usan `AsyncSessionLocal` durante ese test.
6. **Ejecutar el test normalmente.** Usá `test_session` para preparar las categorías y los bienes propios del caso y el `AsyncClient`/`ASGITransport` existente para llamar la API. Hacé las peticiones de forma secuencial: una instancia de `AsyncSession` no debe compartirse entre tareas concurrentes.
7. **Restaurar el estado en un bloque `finally`.** Al terminar o fallar el test, restaurá el override anterior; si no existía, quitá la clave `get_database_session` de `app.dependency_overrides`. Después cerrá `test_session`, ejecutá `await outer_transaction.rollback()` si la transacción sigue activa y cerrá la conexión. El rollback debe ejecutarse aunque falle la preparación o una aserción.

### Qué ocurre con `session.commit()`

El endpoint puede seguir haciendo `await session.commit()` como parte de su comportamiento normal. Con `join_transaction_mode="create_savepoint"`, SQLAlchemy 2.x ejecuta el commit de la sesión sobre su SAVEPOINT; no confirma la transacción externa iniciada por la fixture. Por eso, al final del test, el rollback de la transacción externa revierte también los datos que un endpoint llegó a confirmar en su SAVEPOINT. No uses el modo predeterminado `conditional_savepoint`: en una conexión que solo tiene la transacción externa, puede usar `rollback_only`, lo que no proporciona el mismo ciclo explícito de SAVEPOINT para commits de sesión.

Este patrón está documentado por SQLAlchemy para integrar sesiones en transacciones externas de suites de prueba. El proyecto fija `SQLAlchemy>=2.0,<2.1`, y PostgreSQL/asyncpg debe soportar SAVEPOINT. Referencia: [SQLAlchemy — Joining a Session into an External Transaction](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#joining-a-session-into-an-external-transaction-such-as-for-test-suites).

### Comprobación pedagógica del aislamiento

Verificá explícitamente este flujo con los tests de la tarea:

1. **Test A:** crea una categoría y uno o varios bienes; consulta el endpoint y comprueba que esos bienes existen dentro del test.
2. **Fin de Test A:** la fixture restaura el override, cierra la sesión y revierte la transacción externa. Los bienes creados por A ya no quedan visibles como datos confirmados por el test.
3. **Test B:** comienza su propia fixture; esta establece un contexto sin activos y verifica que la base sea `fireassets_test`. Llama `GET /inventory/assets/` y recibe `200` con `[]`, sin borrar manualmente los bienes de A.

La eliminación de activos de la preparación no es la limpieza entre tests: se ejecuta dentro de la transacción para neutralizar datos viejos y el rollback automático revierte tanto esa preparación como todo cambio del test.

## Casos de prueba

Cada caso usa la fixture centralizada de aislamiento y la base `fireassets_test`:

1. **Colección vacía:** estado conocido sin activos → `GET /inventory/assets/` devuelve `200` y exactamente `[]`.
2. **Colección con filas:** crear al menos dos activos con categorías creadas explícitamente y semánticamente adecuadas → la respuesta es `200`, incluye cada activo sembrado exactamente una vez con los cuatro campos públicos y los IDs en orden ascendente.
3. **Activo existente:** crear una categoría y un activo → solicitar el ID devuelto para ese activo; verificar `200`, los valores exactos y el esquema.
4. **Activo inexistente:** elegir un ID entero cuya ausencia confirme la fixture aislada (sin asumir un valor mágico) → verificar `404` y el detalle acordado.
5. **ID malformado:** solicitar una ruta con un segmento no numérico, por ejemplo `/inventory/assets/not-an-id` → verificar `422`.

Crear categorías con nombres únicos generados y conservar los IDs devueltos por la inserción o la API. Sembrar activos con códigos internos únicos. Antes de usar un ID de categoría, buscar la categoría adecuada o crearla explícitamente.

## Criterios de aceptación

- [ ] `GET /inventory/assets/` devuelve `200`, todos los activos visibles en el contexto de prueba, con los campos de `RegisterAssetResponse` y orden ascendente por ID.
- [ ] La respuesta vacía `[]` se verifica solo después de que la fixture garantice que no hay activos en ese contexto.
- [ ] Los IDs existentes devuelven `200` con el esquema y los valores correctos; los IDs enteros inexistentes devuelven `404` con el detalle acordado; los IDs no enteros devuelven `422`.
- [ ] Las pruebas crean sus propias categorías y activos, y no dependen del orden, de datos preexistentes, de IDs fijos ni de preparación manual.
- [ ] La fixture `isolated_asset_session` abre una transacción externa, verifica que la base sea `fireassets_test`, enlaza la aplicación a la misma sesión con `join_transaction_mode="create_savepoint"`, restaura el override y revierte al finalizar, incluso si hay fallos.
- [ ] La comprobación Test A / Test B demuestra que los bienes de A no aparecen en B y que B obtiene `200` con `[]` sin limpieza manual posterior.
- [ ] Los tests deben producir el mismo resultado al ejecutarse individualmente, en conjunto y en distinto orden.
- [ ] El nuevo router se registra en `app/main.py` y se conservan los routers actuales.
- [ ] No se agregan migraciones ni comportamientos ajenos al alcance.
- [ ] El script integral de pruebas de la Tarea 05 y las pruebas enfocadas de la Tarea 06 se ejecutan de forma segura contra `fireassets_test`.

## Fuera de alcance

No agregar operaciones de actualización o eliminación de activos, filtros por categoría, búsqueda, paginación, cambios de esquemas o modelos, migraciones, refactorizaciones amplias ni cambios en pruebas o infraestructura no relacionadas. Esta tarea se limita a listar activos y consultarlos por ID, además de sus pruebas específicas.

## Guía de implementación

Seguí estas etapas en orden. **No agregues código de producción hasta tener resuelto el aislamiento de las pruebas.**

### Etapa 1 — Confirmar el entorno y los componentes existentes

Desde la raíz del repositorio:

- Verificá que `.env.test` apunte a `fireassets_test`.
- Revisá `Asset`, `RegisterAssetResponse`, `get_database_session` y los tests de inventario existentes.
- Reutilizá esos componentes; no crees modelos, schemas ni configuración de base de datos paralelos.

### Etapa 2 — Preparar el aislamiento de las pruebas

Implementá `isolated_asset_session` siguiendo paso a paso el [Mecanismo elegido](#mecanismo-elegido-una-fixture-transaccional-por-test). Esta fixture debe estar lista antes de escribir los handlers: permite crear datos, hacer peticiones y verificar resultados con el mismo contexto transaccional, y revierte todo al terminar cada caso.

Antes de avanzar, comprobá que la fixture rechace una base cuyo nombre no sea `fireassets_test` y que una escritura de prueba desaparezca después del rollback. No agregues una estrategia alternativa de limpieza.

### Etapa 3 — Implementar las consultas

Agregá ambos handlers en `app/modules/inventory/get_asset/router.py`, usando el `APIRouter` y la dependencia de sesión existentes.

**Listado `GET /inventory/assets/`**

- Consultá `Asset` con SQLAlchemy y ordená por `Asset.id` ascendente en la consulta.
- Convertí los resultados al schema `RegisterAssetResponse` existente.
- Devolvé una lista; cuando no haya filas en el contexto aislado, devolvé `[]`.

**Detalle `GET /inventory/assets/{asset_id}`**

- Buscá un único `Asset` por su clave primaria.
- Si existe, devolvelo con `RegisterAssetResponse`.
- Si no existe, respondé `404 Not Found` con el detalle acordado.

### Etapa 4 — Registrar el router

En `app/main.py`, incluí el router nuevo sin quitar ni reemplazar los routers ya registrados.

### Etapa 5 — Escribir los tests

En `tests/modules/inventory/test_get_asset_endpoint.py`, agregá los casos de la sección [Casos de prueba](#casos-de-prueba). Todos deben usar la fixture de aislamiento, crear sus propios datos y usar los IDs devueltos por la base de datos; no dependas de datos de ejecución manual ni de que otro test haya corrido antes.

### Etapa 6 — Verificar

- Ejecutá los comandos de la sección [Comandos de prueba](#comandos-de-prueba) para tu sistema operativo.
- Confirmá que pasan tanto los tests de Task 06 como la suite existente.
- Revisá el diff: la implementación debe limitarse a los archivos previstos en esta tarea y a la fixture de tests necesaria para el aislamiento.

## Comandos de prueba

Ejecutar desde la raíz del repositorio. Los scripts de la Tarea 05 seleccionan `.env.test`, aplican las migraciones a la base configurada y ejecutan la suite completa. Además, restauran el valor anterior de `ENV_FILE` (o lo eliminan si no estaba definido), por lo que no es necesario dejar esa variable configurada manualmente.

**macOS / Linux — suite completa:**

```bash
./scripts/task05_run_tests_mac.sh
```

**Windows PowerShell — suite completa:**

```powershell
.\scripts\task05_run_tests_windows.ps1
```

No se prescribe aquí un comando enfocado: `pytest` directo y `make test` no seleccionan `.env.test`, y dejar `ENV_FILE` configurado manualmente podría dirigir comandos posteriores a otra base. Usar para la verificación integral los scripts de la Tarea 05. No hace falta iniciar manualmente el servidor ni ejecutar migraciones aparte para las pruebas automatizadas.

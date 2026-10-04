# ADR-004 — Aislamiento transaccional para pruebas de inventario

- **Estado:** propuesto para Task 06; el patrón ya está implementado solo en la suite de autenticación.
- **Fecha de registro:** 2026-10-03.
- **Alcance inicial:** tests de lectura de bienes de la Task 06. Extender a los tests existentes requerirá trabajo adicional.

## Contexto

Los tests de inventario existentes llaman a la API con `ASGITransport` y crean registros en `fireassets_test`. `get_database_session` abre sesiones nuevas y los endpoints hacen `session.commit()`, de modo que pueden quedar filas confirmadas. Por eso, un test que espera `GET /inventory/assets/` igual a `[]` no puede depender de que la base esté vacía ni del orden de ejecución.

## Estrategia propuesta

Antes de cada test de Task 06, una fixture debe abrir una conexión y una transacción externa. Primero debe comprobar `SELECT current_database()` y abortar si no es exactamente `fireassets_test`. La fixture creará una `AsyncSession` ligada a esa conexión con `join_transaction_mode="create_savepoint"`, y sobrescribirá `app.dependency_overrides[get_database_session]` para que el endpoint y el test utilicen **la misma sesión y transacción**.

Dentro de esa transacción se puede establecer un estado inicial sin bienes para el caso de lista vacía; esa preparación no es una limpieza permanente. Tras cada test, incluso si falla, la fixture restaura el override previo, cierra la sesión y revierte la transacción externa. El `session.commit()` del endpoint confirma su SAVEPOINT, **no** la transacción externa; el rollback final revierte los cambios del test. Los tests deben crear sus categorías y bienes propios sin IDs fijos.

## Alternativas consideradas

- **Borrado manual al final de cada test:** frágil ante fallos y orden de ejecución; no es el mecanismo principal elegido.
- **Rollback de una sesión distinta de la que usa FastAPI:** insuficiente, porque no revierte commits efectuados por la sesión del endpoint.
- **Usar siempre una base recién creada:** no garantiza independencia cuando se ejecutan tests juntos o de forma individual.

## Consecuencias y aceptación

La fixture futura de Task 06 debe verificar aislamiento ejecutando tests individualmente, en conjunto y en otro orden. Un Test A crea bienes y los consulta; al terminar, Test B solicita la lista y obtiene `200` y `[]` sin borrado manual posterior. **Estas garantías aún no existen para los tests de inventario.** Como referencia implementada, `tests/modules/auth/conftest.py` ya comprueba `fireassets_test`, comparte una sesión con FastAPI mediante `dependency_overrides`, usa `join_transaction_mode="create_savepoint"` y revierte la transacción exterior por test; no limpia las filas antiguas de inventario ni sustituye la fixture pendiente de Task 06. La implementación pedagógica y los casos exactos están en [Task 06](../../../labs/TASK_06_GET_ASSET_BY_ID.md).

## Evidencia

`app/infrastructure/database/session.py`, `tests/modules/inventory/test_asset_endpoints.py`, `tests/modules/inventory/test_category_endpoints.py`, `tests/modules/auth/conftest.py` y `labs/TASK_06_GET_ASSET_BY_ID.md`. Actualmente `tests/modules/inventory/test_get_asset_endpoint.py` está vacío.

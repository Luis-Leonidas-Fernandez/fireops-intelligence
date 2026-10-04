# Arquitectura actual del backend

El backend actual es una aplicación FastAPI que registra dos routers de inventario y sirve la web de demostración. Esta página describe **cómo funciona hoy**; [ADR-001](../adr/ADR-001-backend-architecture.md) explica la decisión de mantener esa estructura.

## Flujo de una petición de inventario

```text
HTTP → FastAPI (`app/main.py`) → router de inventario
     → schema Pydantic → `get_database_session`
     → `AsyncSession` / modelo SQLAlchemy → PostgreSQL
```

No hay una capa `service` ni `repository` implementada para estas rutas. Los routers de alta ejecutan la persistencia directamente. La sesión se crea en `app/infrastructure/database/session.py` a partir de la URL cargada por `app/config/settings.py`.

## Rutas registradas

| Método y ruta | Módulo | Respuesta principal |
|---|---|---|
| `POST /inventory/categories` | `register_category` | `201`, `CategoryResponse` |
| `GET /inventory/categories` | `register_category` | `200`, lista de `CategoryResponse` ordenada por ID |
| `POST /inventory/assets` | `register_asset` | `201`, `RegisterAssetResponse` |
| `GET /health` | `app/main.py` | `200`, `{"status":"ok"}` |

Los schemas de petición usan nombres públicos en inglés (`name`, `internal_code`, `category_id`); los modelos almacenan columnas `nombre`, `codigo_interno` y `categoria_id`. Los routers transforman entre ambos. Al crear un bien, `category_id` debe referir a una categoría existente.

## Errores y límites

- FastAPI/Pydantic devuelve `422` para cuerpos inválidos.
- Los routers existentes capturan `IntegrityError`, hacen rollback y devuelven `409` con `HTTPException`.
- `app/shared/errors/` define `ApplicationError` y handlers centralizados, pero los routers de inventario actuales no usan ese formato para sus conflictos. No se debe prometer un contrato de error uniforme.
- `app/modules/inventory/get_asset/router.py` y su archivo de tests están vacíos. Los `GET` de bienes de [Task 06](../../../labs/TASK_06_GET_ASSET_BY_ID.md) siguen pendientes y no aparecen en Swagger.

## Persistencia y pruebas

`migrations/versions/0374d9a573a1_create_categories_and_assets_tables.py` crea `categorias` y `bienes` con clave foránea. Las pruebas actuales de escritura hacen `commit()` y pueden dejar datos en `fireassets_test`; la propuesta de aislamiento de Task 06 está en [ADR-004](../adr/ADR-004-testing-database-isolation.md) y aún no se implementó. Véase [ADR-002](../adr/ADR-002-database-persistence.md) para el motivo de PostgreSQL y sesiones asíncronas.

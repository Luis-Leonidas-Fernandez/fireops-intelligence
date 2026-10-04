# ADR-001 — Arquitectura actual del backend de inventario

- **Estado:** aceptado como registro retrospectivo de la implementación actual.
- **Fecha de registro:** 2026-10-03.
- **Alcance:** API de inventario existente. No aprueba módulos futuros.

## Contexto

El equipo necesita ubicar con facilidad el código de cada operación del inventario y probar sus contratos HTTP. El proyecto ya ejecuta FastAPI con routers por operación y modelos compartidos. No existen capas `service` o `repository` para estos endpoints.

## Decisión registrada

Se mantiene por ahora un backend FastAPI dentro de un monolito modular, con carpetas de inventario organizadas por operación (`register_asset`, `register_category`) y componentes de dominio compartidos en `inventory/shared`. `app/main.py` registra los routers implementados. Las operaciones actuales validan entrada/salida mediante schemas Pydantic y acceden a PostgreSQL con la dependencia `get_database_session` y `AsyncSession` de SQLAlchemy.

| Ruta implementada | Archivo principal | Resultado principal |
|---|---|---|
| `POST /inventory/categories` | `register_category/router.py` | `201`; categoría creada |
| `GET /inventory/categories` | `register_category/router.py` | `200`; lista ordenada por ID |
| `POST /inventory/assets` | `register_asset/router.py` | `201`; bien creado |

Los endpoints de categorías y bienes usan `HTTPException` para conflictos de integridad (`409`) y FastAPI/Pydantic para validación (`422`). Existe una jerarquía `ApplicationError` con manejadores centralizados, pero **estos endpoints no la usan de forma uniforme**. No se documenta un contrato único de error que el código todavía no cumple.

## Alternativas consideradas

- **Capas `service` y `repository` obligatorias para cada ruta:** pospuestas; hoy añadirían abstracciones sin comportamiento compartido comprobado.
- **Un único router y schema para todo inventario:** descartado para la implementación actual porque oculta las operaciones y su responsabilidad.

## Consecuencias

La ruta HTTP y la persistencia están próximas y son fáciles de seguir en clase. Si aparecen reglas de negocio reutilizadas o consultas complejas, habrá que evaluar extraer servicios o repositorios sin fingir que ya existen. Los endpoints de lectura de bienes de la [Task 06](../../../labs/TASK_06_GET_ASSET_BY_ID.md) **no están implementados**: su router y test están vacíos y no hay `include_router` para ellos.

## Evidencia

`app/main.py`, `app/modules/inventory/register_asset/`, `app/modules/inventory/register_category/`, `app/modules/inventory/shared/` y `app/shared/errors/`. Véase el [mapa del backend](../backend/backend-architecture.md).

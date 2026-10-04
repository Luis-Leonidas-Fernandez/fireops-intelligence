# ADR-002 — Persistencia relacional y sesiones asíncronas

- **Estado:** aceptado como registro retrospectivo de la implementación actual.
- **Fecha de registro:** 2026-10-03.
- **Alcance:** esquema y acceso a datos que hoy existen, no el modelo propuesto para fases posteriores.

## Contexto

Una categoría debe existir antes de registrar un bien, y el código interno del bien debe ser único. El proyecto necesita cambios de esquema reproducibles en las bases locales de cada integrante.

## Decisión registrada

PostgreSQL es el almacenamiento actual. SQLAlchemy 2 usa un motor asíncrono con `asyncpg`; `get_database_session` entrega una `AsyncSession` por dependencia de FastAPI. Alembic aplica las migraciones mediante la URL cargada por `Settings` desde `.env` o desde el archivo indicado por `ENV_FILE`.

La migración `0374d9a573a1` crea `categorias` (`id`, `nombre` único) y `bienes` (`id`, `codigo_interno` único, `nombre`, `categoria_id` obligatorio con clave foránea a `categorias.id`). El endpoint de creación confirma con `session.commit()` y refresca la instancia antes de responder; en error de integridad realiza rollback y devuelve `409`.

## Alternativas y límites

- **Crear tablas automáticamente al iniciar:** no es el mecanismo del proyecto; se usa Alembic para versionar el esquema.
- **Persistencia síncrona:** no corresponde al motor y las rutas asíncronas actuales.
- **Modelo relacional + JSONB:** aparece en los Word de `architecture-history` como propuesta histórica. **La migración actual no incluye JSONB**, definiciones de campos dinámicos ni las demás tablas de ese diseño. Su adopción requeriría una decisión e implementación posteriores.

## Consecuencias

Cada máquina necesita su propia base y migraciones aplicadas; Git solo distribuye código y migraciones. Las pruebas deben seleccionar explícitamente `fireassets_test` para evitar escrituras en otra base. Un `commit()` dentro de un endpoint puede dejar datos persistidos si el test no comparte una transacción controlada; la estrategia pendiente está descrita en [ADR-004](ADR-004-testing-database-isolation.md).

## Evidencia

`app/config/settings.py`, `app/infrastructure/database/session.py`, `app/modules/inventory/shared/models.py`, `migrations/env.py`, `migrations/versions/0374d9a573a1_create_categories_and_assets_tables.py`.

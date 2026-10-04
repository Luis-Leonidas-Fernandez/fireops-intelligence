# Arquitectura actual del backend

El backend actual es una aplicación FastAPI que registra dos routers de inventario y uno de autenticación, y sirve la web en el mismo origen. Esta página describe **cómo funciona hoy**; [ADR-001](../adr/ADR-001-backend-architecture.md) explica la organización inicial del inventario y [ADR-005](../adr/ADR-005-email-password-authentication.md) la autenticación.

## Flujo de una petición de inventario

```text
HTTP → FastAPI (`app/main.py`) → router de inventario
     → schema Pydantic → `get_database_session`
     → `AsyncSession` / modelo SQLAlchemy → PostgreSQL
```

No hay una capa `service` ni `repository` implementada para estas rutas. Los routers de alta ejecutan la persistencia directamente. La sesión se crea en `app/infrastructure/database/session.py` a partir de la URL cargada por `app/config/settings.py`.

La autenticación sí separa router (`app/modules/auth/router.py`), reglas de registro/login (`service.py`), schemas (`schemas.py`), modelo `User` (`models.py`) y validadores reutilizables (`validations/`). Hash Argon2 y verificación se ejecutan en threadpool. Alembic crea la tabla `usuarios`; ningún dato de PostgreSQL llega mediante `git pull`.

## Rutas registradas

| Método y ruta | Módulo | Respuesta principal |
|---|---|---|
| `POST /inventory/categories` | `register_category` | `201`, `CategoryResponse` |
| `GET /inventory/categories` | `register_category` | `200`, lista de `CategoryResponse` ordenada por ID |
| `POST /inventory/assets` | `register_asset` | `201`, `RegisterAssetResponse` |
| `POST /auth/register` | `auth/router.py` | `201`, `message` y `user`; establece cookie de sesión |
| `POST /auth/login` | `auth/router.py` | `200`, `message` y `user`; establece cookie de sesión |
| `POST /auth/logout` | `auth/router.py` | `204`; elimina cookie del navegador |
| `GET /` | `app/main.py` | Dashboard con token válido; si no, `303` a `/iniciar-sesion` |
| `GET /health` | `app/main.py` | `200`, `{"status":"ok"}` |

Los schemas de petición usan nombres públicos en inglés (`name`, `internal_code`, `category_id`); los modelos almacenan columnas `nombre`, `codigo_interno` y `categoria_id`. Los routers transforman entre ambos. Al crear un bien, `category_id` debe referir a una categoría existente.

`POST /auth/register` y `/auth/login` reciben `{"email":"persona@ejemplo.com","password":"ClaveSegura123"}`. Se normaliza el correo; el registro exige contraseña de 8 a 128 caracteres con letras y números. La respuesta exitosa no incluye la contraseña ni el JWT. El JWT HS256 dura 30 minutos y viaja en una cookie `fire_control_access` HttpOnly, SameSite=Lax (`Secure` en `ENVIRONMENT=production`). `SECRET_KEY` debe tener al menos 32 caracteres.

## Errores y límites

- FastAPI/Pydantic devuelve `422` para cuerpos inválidos; el handler global lo presenta con `error.code = VALIDATION_ERROR` y `error.details.fields`.
- Los routers de inventario existentes capturan `IntegrityError`, hacen rollback y elevan `HTTPException(409)`; el handler global serializa esa excepción como `HTTP_409`. No es el mismo código de error de los servicios de autenticación.
- `app/shared/errors/` centraliza `{"error":{"code":"...","message":"...","details":{...}}}`. Auth usa `ApplicationError`: correo repetido `EMAIL_ALREADY_REGISTERED` (`409`), credenciales incorrectas `INVALID_CREDENTIALS` (`401`). Los errores inesperados devuelven `500` con mensaje controlado.
- `app/modules/inventory/get_asset/router.py` y su archivo de tests están vacíos. Los `GET` de bienes de [Task 06](../../../labs/TASK_06_GET_ASSET_BY_ID.md) siguen pendientes y no aparecen en Swagger.
- La cookie solo protege la página `/`; **los endpoints de inventario y `/docs` siguen públicos**. No hay OAuth de Google, limitación de intentos de login ni revocación server-side de JWT emitidos.

## Persistencia y pruebas

`migrations/versions/0374d9a573a1_create_categories_and_assets_tables.py` crea `categorias` y `bienes` con clave foránea; `migrations/versions/b70e8e0479aa_create_auth_users.py` crea `usuarios`. La fixture `tests/modules/auth/conftest.py` verifica `fireassets_test` y comparte una `AsyncSession` con los endpoints dentro de una transacción exterior/SAVEPOINT; el rollback final aísla las pruebas de auth incluso ante `commit()` interno. Los tests antiguos de inventario pueden dejar datos; la extensión a Task 06 está en [ADR-004](../adr/ADR-004-testing-database-isolation.md). Véase [ADR-002](../adr/ADR-002-database-persistence.md) para PostgreSQL y sesiones asíncronas.

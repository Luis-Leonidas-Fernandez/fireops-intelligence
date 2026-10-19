# Arquitectura actual del backend

El backend actual es una aplicación FastAPI que registra los routers de inventario y autenticación, y sirve la web en el mismo origen. Esta página describe **cómo funciona hoy**; [ADR-001](../adr/ADR-001-backend-architecture.md) explica la organización inicial del inventario y [ADR-005](../adr/ADR-005-email-password-authentication.md) la autenticación.

## Flujo de una petición de inventario

```text
HTTP → FastAPI (`app/main.py`) → router de inventario
     → `require_authenticated_user` → schema Pydantic → `get_database_session`
     → servicio de alta o edición de bienes (si corresponde)
     → `AsyncSession` / modelo SQLAlchemy → PostgreSQL
```

El alta de bienes usa `register_asset/service.py` para resolver la categoría y persistir bien y categoría en una sola transacción. La edición usa `update_asset/service.py` para bloquear el bien y confirmar el cambio junto con una fila de auditoría. Los routers conservan el mapeo HTTP. Las otras rutas de inventario mantienen su organización actual, sin una capa `repository` general. La sesión se crea en `app/infrastructure/database/session.py` a partir de la URL cargada por `app/config/settings.py`.

Los seis routers de inventario declaran la misma dependencia `app/modules/auth/dependencies.py::require_authenticated_user`, aplicada a sus once endpoints. El helper valida la cookie local de 30 minutos y confirma que el usuario todavía existe mediante la misma `AsyncSession` de la petición; una sesión ausente, inválida, expirada o perteneciente a un usuario eliminado devuelve `401` con `error.code = AUTH_REQUIRED`. Para continuar exige `usuarios.activo = true` y un rol activo cuyo nombre sea `ADMINISTRADOR` o `SUPERVISOR`. Una cuenta autenticada sin rol, inactiva o con un rol no permitido recibe `403` con `error.code = INVENTORY_ACCESS_DENIED`. Ambos roles tienen acceso completo a las rutas de inventario actuales. El traslado y la edición reciben además el usuario autorizado para atribuir el cambio, sin repetir la consulta gracias al caché de dependencias de FastAPI.

La autenticación sí separa router (`app/modules/auth/router.py`), reglas de registro/login (`service.py`), schemas (`schemas.py`), modelo `User` (`models.py`) y validadores reutilizables (`validations/`). Las invitaciones separan emisión HTTP, ciclo de vida y adaptación Gmail en `app/modules/auth/invitations/`. Hash Argon2 y verificación se ejecutan en threadpool. Alembic crea las tablas; ningún dato de PostgreSQL llega mediante `git pull`.

### Estructura implementada: rol y estado del usuario

El [modelo físico](../../Phase_01/data-modeling/guie.md#3-tabla-roles) incluye el catálogo `roles` y los campos `usuarios.rol_id` y `usuarios.activo`. La revisión `e7d4c2f9a621` y el modelo `User` incorporan esta estructura. Cada integrante debe confirmar su base de destino antes de aplicar la migración.

| Elemento implementado | Transición compatible |
|---|---|
| `roles` | Catálogo con `id`, `nombre` único, `descripcion`, `activo`, `created_at` y `updated_at`. La migración siembra únicamente `ADMINISTRADOR` y `SUPERVISOR`; sembrar el catálogo no asigna privilegios a ninguna cuenta. |
| `usuarios.rol_id` | Clave foránea nullable a `roles.id`. Las cuentas existentes conservaron su valor durante la migración; las cuentas nuevas reciben el rol de su invitación consumida. No existe rol predeterminado implícito. |
| `usuarios.activo` | Booleano no nulo con valor predeterminado `true`, para conservar activas las cuentas existentes durante la migración. |
| `usuarios.password_hash` | Permanece nullable: las cuentas creadas solo con Google no tienen contraseña local. |

El guard de inventario ya comprueba `rol_id` y `activo`. El registro abierto quedó cerrado: una cuenta nueva debe consumir una invitación válida y obtiene su rol en la misma transacción que el alta. Las cuentas existentes siguen iniciando sesión con sus datos anteriores. En la base de prueba local se asignaron manualmente los dos usuarios elegidos por el responsable del proyecto; esta asignación de datos no viaja mediante Git.

El requisito RNF-SEG-02 menciona además la función de carga; queda pendiente de revisión para una fase posterior. Por decisión actual del equipo, el catálogo inicial contiene solo `ADMINISTRADOR` y `SUPERVISOR`.

Google agrega `google_oauth.py` para el proveedor, `google_service.py` para las reglas de cuentas y `validations/google_flow.py` para el estado efímero firmado. El flujo es código de autorización en el servidor; JavaScript no recibe tokens Google. Véase [ADR-006](../adr/ADR-006-google-oauth-identity.md).
`google_observability.py` registra eventos JSON con `attempt_id`, etapa, resultado y motivo controlado, sin secretos ni datos de identidad. Los scripts de desarrollo ejecutan Uvicorn con `--no-access-log`, porque la URL del callback contiene `code` y `state`; SQLAlchemy también evita imprimir parámetros. Véase la [guía de diagnóstico](../../getting-started/google-oauth.md#diagnóstico-seguro-en-la-terminal).

## Rutas registradas

| Método y ruta | Módulo | Respuesta principal |
|---|---|---|
| `POST /inventory/categories` | `register_category` | `201`, `CategoryResponse` |
| `GET /inventory/categories` | `register_category` | `200`, lista de `CategoryResponse` ordenada por ID |
| `POST /inventory/assets` | `register_asset` | `201`, `RegisterAssetResponse` |
| `GET /inventory/assets/` | `get_asset` | `200`, lista de bienes ordenada por ID |
| `GET /inventory/assets/{asset_id}` | `get_asset` | `200` con el bien o `404` |
| `PATCH /inventory/assets/{asset_id}` | `update_asset` | `200` con el bien editado, `404` si no existe |
| `POST /inventory/assets/{asset_id}/transfers` | `transfer_asset` | `201`, traslado registrado |
| `GET /inventory/assets/{asset_id}/transfers` | `transfer_asset` | `200`, historial de traslados |
| `POST /inventory/locations` | `register_location` | `201`, `LocationResponse` |
| `GET /inventory/locations` | `register_location` | `200`, lista de ubicaciones ordenada por ID |
| `GET /inventory/locations/{location_id}` | `register_location` | `200` con la ubicación o `404` |
| `POST /auth/register` | `auth/router.py` | `201`, `message` y `user`; establece cookie de sesión |
| `POST /auth/invitations` | `auth/invitations/router.py` | `201` tras enviar; solo `ADMINISTRADOR` activo |
| `POST /auth/login` | `auth/router.py` | `200`, `message` y `user`; establece cookie de sesión |
| `POST /auth/logout` | `auth/router.py` | `204`; elimina cookie del navegador |
| `GET /auth/me` | `auth/router.py` | `200`, perfil de la sesión actual (`id`, correo y nombre opcional); `401` sin sesión |
| `GET/POST /auth/google/start` | `auth/router.py` | `303` a Google con estado, PKCE y nonce; `POST` transporta la invitación en el cuerpo |
| `GET /auth/google/callback` | `auth/router.py` | Verifica identidad y redirige con sesión local o error controlado |
| `GET /` | `app/main.py` | Dashboard con token válido; si no, `303` a `/iniciar-sesion` |
| `GET /health` | `app/main.py` | `200`, `{"status":"ok"}` |

Los schemas de petición usan nombres públicos en inglés (`name`, `internal_code`, `category_id`, `new_category_name`, `location_id`); los modelos almacenan columnas `nombre`, `codigo_interno`, `categoria_id` y `ubicacion_id`. Al crear un bien se proporciona **exactamente uno** de `category_id` (categoría existente) o `new_category_name` (3–100 caracteres). En el segundo caso, el servicio reutiliza una categoría con ese nombre exacto o la crea y registra el bien antes de confirmar una única transacción. Si falla el registro del bien, la categoría nueva también se revierte. `location_id` es opcional y, si se envía, debe apuntar a una ubicación activa.

Todas las operaciones `/inventory/...` de la tabla requieren iniciar sesión antes de probarlas en `/docs`; la cookie se obtiene con `POST /auth/login` o con el flujo Google en el mismo navegador.

Ejemplo de alta que también crea o reutiliza una categoría:

```json
{"internal_code":"CASCO-001","name":"Casco estructural","new_category_name":"Cascos"}
```

Para corregir un bien, `PATCH /inventory/assets/{asset_id}` acepta uno o más de `internal_code`, `name` y `category_id`, además de `reason` obligatorio y no vacío. Rechaza `location_id` y campos desconocidos (`422`): la ubicación cambia solo mediante traslados. Una categoría inexistente o un código duplicado devuelve `409`. La respuesta reutiliza `RegisterAssetResponse`. El servicio bloquea el bien y, en una transacción, escribe el cambio y una fila `CORRECCION`/`BIEN` en `auditoria_cambios`, con actor de la sesión, motivo, fecha, `operacion_id` y snapshots JSONB completos. Si alguna escritura falla, se revierten ambas. No agrega un movimiento. Ejemplo: `{"name":"Casco estructural corregido","reason":"Corrección de carga"}`.

`ubicaciones` representa lugares físicos o vehículos contenedores. Sus campos son `id`, `bien_contenedor_id` opcional, `nombre`, `tipo_ubicacion`, `descripcion` opcional, `activa`, `created_at` y `updated_at`. `tipo_ubicacion` admite `FISICA` sin bien contenedor o `VEHICULO` con un bien contenedor existente y único. Varios bienes pueden estar en una ubicación; un bien puede representar, como máximo, una ubicación vehicular. La base impide la autoubicación y los ciclos de contención. Un bien antiguo mantiene `ubicacion_id = NULL` tras la migración.

Un traslado requiere una sesión local válida. `POST /inventory/assets/{asset_id}/transfers` recibe `destination_location_id` y, opcionalmente, `reason` y `observations`. No acepta el usuario ni el origen desde el cliente: obtiene al actor de la cookie y el origen del estado actual del bien. En una sola transacción actualiza `bienes.ubicacion_id` y agrega un registro `TRASLADO` a `movimientos`. Rechaza un destino inexistente, inactivo, idéntico al origen o que forme un ciclo; si falla, no cambia el bien ni guarda el movimiento. `GET /inventory/assets/{asset_id}/transfers` devuelve el historial ordenado por fecha e ID.

Ejemplo de cuerpo para trasladar un bien existente a una ubicación activa cuyo ID se obtuvo de `GET /inventory/locations`:

```json
{"destination_location_id": 2, "reason": "Asignación operativa", "observations": "Equipo revisado"}
```

El `2` es ilustrativo: cada integrante debe usar un ID real de su propia base de prueba. El endpoint está disponible en `/docs` tras iniciar sesión en el mismo navegador.

`POST /auth/register` y `/auth/login` reciben correo y contraseña; el registro exige también `invitation_token` y admite `display_name` opcional (1–120 caracteres normalizados). Se normaliza el correo; el registro exige contraseña de 8 a 128 caracteres con letras y números. La respuesta exitosa no incluye la contraseña ni el JWT. La invitación tiene un token aleatorio cuyo SHA-256 único se almacena en `auth_invitations` con correo, rol, vencimiento y uso; el endpoint bloquea la fila antes de consumirse. Una alta Google nueva usa el hash en el estado OAuth firmado y también consume la invitación, mientras el login de una cuenta Google vinculada no necesita otra. `GET /auth/me` obtiene el perfil mediante esa misma sesión y el dashboard muestra `display_name` o, si falta, el correo. El JWT HS256 dura 30 minutos y viaja en una cookie `fire_control_access` HttpOnly, SameSite=Lax (`Secure` en `ENVIRONMENT=production`). `SECRET_KEY` debe tener al menos 32 caracteres. Véase la [guía de invitaciones](../../getting-started/gmail-invitations.md).

## Errores y límites

- FastAPI/Pydantic devuelve `422` para cuerpos inválidos; el handler global lo presenta con `error.code = VALIDATION_ERROR` y `error.details.fields`.
- Los routers de inventario existentes capturan `IntegrityError`, hacen rollback y elevan `HTTPException(409)`; el handler global serializa esa excepción como `HTTP_409`. No es el mismo código de error de los servicios de autenticación.
- `app/shared/errors/` centraliza `{"error":{"code":"...","message":"...","details":{...}}}`. Auth usa `ApplicationError`: correo repetido `EMAIL_ALREADY_REGISTERED` (`409`), credenciales incorrectas `INVALID_CREDENTIALS` (`401`). Los errores inesperados devuelven `500` con mensaje controlado.
- Los `GET` de bienes de [Task 06](../../../labs/TASK_06_GET_ASSET_BY_ID.md) ya están implementados. Las rutas de ubicaciones permiten alta y consulta; el traslado se realiza desde la ruta del bien. No se implementaron edición ni baja de ubicaciones, ni otros tipos de movimiento.
- La cookie protege la página `/` y todos los endpoints de inventario. `/docs` sigue visible sin sesión, pero llamar esas rutas sin una cookie válida devuelve `401`; con cookie válida pero sin un rol activo permitido devuelve `403`. El envío de invitaciones exige `ADMINISTRADOR` activo. No hay limitación de intentos de login ni revocación server-side de JWT emitidos. Las cuentas nuevas, tanto por contraseña como por Google, requieren invitación.

## Persistencia y pruebas

`migrations/versions/0374d9a573a1_create_categories_and_assets_tables.py` crea `categorias` y `bienes` con clave foránea; `migrations/versions/b70e8e0479aa_create_auth_users.py` crea `usuarios`; `migrations/versions/c4e9f1d2a7b3_add_google_identity.py` permite cuentas solo-Google y agrega `google_sub` único; `migrations/versions/d8b6e2f1940a_add_user_display_name.py` añade `display_name` nullable. `migrations/versions/e42c7910b6af_add_inventory_locations.py` crea `ubicaciones`, agrega `bienes.ubicacion_id` nullable, sus claves e índices y los triggers que rechazan ciclos. `migrations/versions/a6a239f7b4dc_add_inventory_movements.py` crea `movimientos` con claves foráneas a bien, usuario y ubicaciones, tipo controlado e índice para consultar el historial por bien y fecha. `migrations/versions/c15b4e3d9a20_add_audit_changes.py` crea `auditoria_cambios` con claves, restricciones e índices del modelo físico 1.1. Estas tres revisiones de inventario se aplicaron solo a `fireassets_test` local; cada integrante debe confirmar su destino real antes de migrar.

`migrations/versions/f09a6e2112b4_add_auth_invitations.py` agrega `auth_invitations` con claves a `roles` y `usuarios`, hash único, expiración y marca de consumo. Se aplicó solo a `fireassets_test` local tras verificar URL efectiva y `SELECT current_database()`; cada integrante debe migrar su base de prueba por separado.

Las fixtures transaccionales de autenticación e inventario comparten una `AsyncSession` con FastAPI mediante un override y revierten la transacción externa después de cada prueba, incluso si el endpoint ejecuta `commit()`. La fixture común y el cliente autenticado de inventario residen en `tests/modules/inventory/conftest.py`; las pruebas de bienes, categorías, ubicaciones y traslados la reutilizan. Véase [ADR-004](../adr/ADR-004-testing-database-isolation.md) para el aislamiento y [ADR-002](../adr/ADR-002-database-persistence.md) para PostgreSQL y sesiones asíncronas.

## Registration approval (current)

A public request creates only an `auth_registration_requests` row and sends a review notification to the configured admin recipient. The notification links to `/solicitudes`, where authenticated `ADMINISTRADOR` users perform POST approve/reject actions; opening the email performs no mutation. Approval creates an `auth_invitations` token for active `SUPERVISOR`, sends the hash-only token’s plaintext link to the applicant, and commits review plus invitation only after Gmail accepts the send. Password and first-time Google signup atomically consume that token. The earlier admin-issued invitation endpoint is superseded.

Registration-request coordination now lives in `invitations/workflows.py`, used by both the public password endpoint and the verified Google callback. The HTTP routers retain request/response schemas and delegate authorization to `invitations/policy.py`. `invitations/requests.py` owns the pending-list query; `invitations/links.py` validates `PUBLIC_BASE_URL` when constructing review and signup links. `app/main.py` composes the two auth routers, so neither router imports the other. Each request still receives its own `AsyncSession` through `get_database_session`; no session is shared globally. Invalid public-link configuration raises a transport-independent error in `invitations/errors.py`; the invitation router maps it to the existing JSON error contract, while the Google callback maps it to a controlled redirect. The existing Gmail adapter still emits `ApplicationError`, which remains a compatibility boundary and is not changed in this refactor.

The ordering is intentionally unchanged: a public request commits before attempting its best-effort administrator notice; approval sends the applicant email before committing and rolls back on delivery failure. A successful email followed by a failed database commit can therefore deliver an unusable link. Resolving that risk would require a separate transactional delivery design, outside this refactor.

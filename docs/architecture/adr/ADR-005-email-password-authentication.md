# ADR-005 — Autenticación local con correo y contraseña

- **Estado:** aceptado; implementado en la rama de autenticación.
- **Fecha de registro:** 2026-10-04.
- **Alcance:** registro, inicio/cierre de sesión y perfil local para la página `/`. No incluye autorización de la API de inventario ni el flujo de acceso con Google, documentado en ADR-006.

## Contexto

Las pantallas de registro e inicio de sesión eran demostraciones: sus botones abrían el dashboard sin comprobar credenciales. La web se sirve desde FastAPI en el mismo origen, y ya existe PostgreSQL con SQLAlchemy asíncrono y Alembic.

## Decisión

1. `app/modules/auth/` separa el modelo `User`, los schemas Pydantic, la lógica de registro/login, el router y las validaciones de credenciales, contraseñas y tokens. El correo se normaliza a minúsculas; `usuarios.email` es único. El hash se obtiene con Argon2 mediante `pwdlib`; no se guarda ni devuelve la contraseña.
2. `POST /auth/register` y `POST /auth/login` generan un JWT HS256 de acceso de 30 minutos con `sub`, `type`, `iat` y `exp`, firmado con `SECRET_KEY` (mínimo 32 caracteres). Se entrega en la cookie `fire_control_access`, `HttpOnly`, `SameSite=Lax`; `Secure` se activa cuando `ENVIRONMENT=production`. El JSON de éxito contiene `message` y `user` (`id`, `email`, `display_name` opcional), no el token. Registro acepta un nombre para mostrar opcional.
3. `GET /` valida la cookie y redirige con `303` a `/iniciar-sesion` si falta o no es válida. `GET /auth/me` usa la misma cookie para devolver el perfil autenticado (`401` sin sesión); el app bar muestra `display_name` o el correo si el nombre falta. `POST /auth/logout` elimina la cookie en el navegador y responde `204`. No hay lista de revocación: un token firmado previamente sigue criptográficamente válido hasta su vencimiento aunque se borre la cookie del navegador.
4. Los errores de aplicación, validación HTTP (`422`), HTTP genéricos y errores inesperados se serializan como `{"error":{"code":"...","message":"...","details":{...}}}`. `app/shared/errors/` centraliza este contrato; las rutas de inventario conservan sus excepciones existentes, aunque ahora pasan por los handlers globales.
5. `frontend/js/validations/credentials.js` valida antes de enviar; `frontend/js/auth-form.js` comparte envío, estado de carga, feedback y modal. La validación del servidor sigue siendo la autoridad. En la implementación original de este ADR, el botón de Google aún no estaba disponible; su implementación posterior se registra en [ADR-006](ADR-006-google-oauth-identity.md).

## Alternativas y consecuencias

- **Token en `localStorage`:** no elegido; el frontend no necesita leer el JWT y la cookie HttpOnly reduce su exposición a JavaScript.
- **Sesión del servidor:** no elegida para este primer flujo; JWT evita un almacén de sesiones, a cambio de no permitir revocación inmediata del token ya emitido.
- **Autorización global de toda la API:** fuera de este cambio. Proteger la página `/` **no** protege los endpoints de inventario, `/docs` ni los recursos estáticos; esos límites deben resolverse antes de producción.
- **OAuth de Google:** fuera del alcance de esta decisión; se implementó posteriormente según [ADR-006](ADR-006-google-oauth-identity.md).

## Verificación y evidencia

La migración `b70e8e0479aa` crea `usuarios`; la revisión posterior `d8b6e2f1940a` agrega `display_name` nullable sin alterar las cuentas existentes. `tests/modules/auth/conftest.py` vincula cada test a una transacción externa en `fireassets_test`, con SAVEPOINT para tolerar el `commit()` del registro; al finalizar hace rollback y restaura el override de FastAPI. `tests/modules/auth/` cubre registro, login, perfil, hash, token y logout. `frontend/tests/auth-form.test.cjs` y `frontend/tests/dashboard-profile.test.cjs` comprueban formularios y nombre en el app bar.

Archivos principales: `app/modules/auth/`, `app/main.py`, `app/shared/errors/`, `frontend/js/auth-form.js`, `frontend/js/validations/credentials.js` y `migrations/versions/b70e8e0479aa_create_auth_users.py`.

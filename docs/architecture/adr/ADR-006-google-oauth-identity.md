# ADR-006 — Identidad Google vinculada a cuentas locales

- **Estado:** aceptado; implementado.
- **Fecha:** 2026-10-04.
- **Alcance:** acceso y vinculación de Google; no autorización de inventario ni invitaciones.

## Contexto

Ya existen cuentas locales con contraseña, correo único y una cookie JWT de 30 minutos. Google usa un identificador estable (`sub`), mientras que el correo puede cambiar. Vincular automáticamente por correo permitiría asociar identidades sin una acción explícita del titular de la cuenta local.

## Decisión

Usar el flujo OAuth de código de autorización en FastAPI, con `state`, PKCE y `nonce`. El servidor intercambia el código, verifica el ID token (firma, audiencia, emisor, vencimiento, correo verificado y `nonce`) y emite la cookie local existente. No guarda tokens del proveedor.

`usuarios.google_sub` es único y opcional; `password_hash` es opcional para usuarios creados solo con Google. Un `sub` ya vinculado identifica a la cuenta aunque el correo Google cambie. Un correo nuevo y verificado puede registrarse mientras el registro abierto siga vigente. Si el correo ya pertenece a una cuenta local, se exige iniciar sesión con contraseña y elegir **Vincular Google** en el perfil; la vinculación exige que ambos correos normalizados coincidan.

El flujo solicita `openid profile email`. Si el ID token verificado incluye un nombre válido, se guarda en `usuarios.display_name` al crear o vincular la cuenta; una cuenta Google previa sin nombre puede completarlo al volver a iniciar sesión. Nunca se sobrescribe un nombre local ya guardado. El app bar consulta `GET /auth/me` y usa el correo como respaldo cuando no hay nombre; JavaScript no recibe tokens Google.

## Consecuencias

- Una migración Alembic conserva las cuentas existentes y amplía el esquema. No puede revertirse de forma segura mientras haya usuarios sin contraseña.
- Los secretos Google quedan en `.env`/`.env.test`, nunca en el repositorio; las variables pueden omitirse sin bloquear el acceso con contraseña.
- Los fallos del proveedor retornan a una página local con un código de error controlado, nunca con tokens ni mensajes crudos.
- Los eventos estructurados `google_oauth` correlacionan cada intento mediante `attempt_id` sin incluir correos, códigos ni tokens. Los lanzadores desactivan el access log de Uvicorn para que la URL del callback no exponga `code` o `state` en la terminal; SQLAlchemy no imprime parámetros de consultas.
- Continúan pendientes las invitaciones, protección de la API de inventario y revocación inmediata de JWT.

## Evidencia

`app/modules/auth/google_oauth.py`, `app/modules/auth/google_service.py`, `app/modules/auth/validations/google_flow.py`, `migrations/versions/c4e9f1d2a7b3_add_google_identity.py`, `migrations/versions/d8b6e2f1940a_add_user_display_name.py` y `tests/modules/auth/test_google_oauth.py`.

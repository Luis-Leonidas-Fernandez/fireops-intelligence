# Superseded guide

This administrator-issued invitation workflow has been replaced by applicant-initiated registration approval. Follow [Registration approval](registration-approval.md) instead. The historical material below describes the superseded staged candidate and must not be used for current setup.

# Invitaciones por Gmail

El registro de cuentas nuevas requiere una invitación individual. Solo una cuenta activa con rol `ADMINISTRADOR` puede enviarla desde `POST /auth/invitations` en `/docs`. La invitación es un correo de texto simple con un enlace válido por 48 horas; el destinatario elige contraseña o Google y recibe el rol indicado.

## Preparación privada

1. En Google Cloud, habilitá **Gmail API** para el proyecto del cliente OAuth web que ya usa el inicio de sesión.
2. Autorizá **una casilla remitente** para el alcance `https://www.googleapis.com/auth/gmail.send` y obtené un **refresh token offline**. Esta autorización es distinta de `openid profile email`; no cambies los alcances del login. El Client ID y Client Secret deben corresponder al cliente con el que autorizaste esa casilla. Google puede exigir configurar el consentimiento y agregar la casilla como usuario de prueba.
3. Guardá la casilla y el refresh token **solo** en `.env.test` para la demo y en `.env` únicamente si ese entorno enviará invitaciones. No los pegues en Git, `.env.example`, capturas ni mensajes.

```dotenv
GOOGLE_CLIENT_ID=<cliente OAuth web>
GOOGLE_CLIENT_SECRET=<secreto del mismo cliente>
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/auth/google/callback
GMAIL_SENDER_EMAIL=<casilla autorizada>
GMAIL_REFRESH_TOKEN=<refresh token con gmail.send>
```

La casilla remitente y el refresh token son obligatorios **solo para enviar invitaciones**. Si faltan o Gmail falla, el endpoint devuelve `503` y `INVITATION_DELIVERY_UNAVAILABLE`; no informa falsamente que el correo se envió. El acceso de cuentas existentes con contraseña o Google sigue funcionando.

## Migración y uso

Verificá primero que la URL efectiva y `SELECT current_database()` apunten a `fireassets_test`. Recién entonces ejecutá `ENV_FILE=.env.test .venv/bin/python -m alembic upgrade head` en macOS/Linux, o el equivalente con `.venv\Scripts\python.exe` y `ENV_FILE` en PowerShell. La revisión `f09a6e2112b4` crea `auth_invitations`; **Git no crea esta tabla en la base de cada compañero**.

Entrá como administrador y abrí `/docs` en el mismo navegador. En `POST /auth/invitations` enviá, por ejemplo:

```json
{"email":"persona@ejemplo.com","role":"SUPERVISOR"}
```

Los únicos roles admitidos son `SUPERVISOR` y `ADMINISTRADOR`. El endpoint responde `201` y `{"message":"Invitación enviada."}` solo tras aceptar Gmail el mensaje y confirmar la invitación. El correo contiene un enlace a `/registro#invite=...`; el token no aparece en el JSON, se almacena solo como hash y se consume al crear la cuenta. Si la persona ya está registrada, usará el inicio de sesión habitual; el endpoint no envía una invitación nueva a ese correo.

## Seguridad y pruebas

- No agregues `gmail.send` al OAuth de inicio de sesión. El backend usa el refresh token del remitente exclusivamente para Gmail API y no guarda los access tokens resultantes.
- El enlace usa un fragmento `#invite=`, que no viaja al servidor en el `GET /registro`. El registro por contraseña lo envía en el cuerpo JSON; el botón Google inicia el flujo con `POST`, también en el cuerpo, y guarda únicamente el hash en el estado firmado del flujo.
- Un token vencido, reutilizado o destinado a otro correo devuelve `INVITATION_INVALID`. Una cuenta Google ya vinculada puede iniciar sesión sin invitación nueva.
- Las pruebas automatizadas sustituyen el adaptador Gmail: **no envían correos reales**. La comprobación manual de envío queda pendiente hasta autorizar la casilla y generar su refresh token.

Referencia oficial: [alcances de Gmail API](https://developers.google.com/workspace/gmail/api/auth/scopes) y [envío de mensajes](https://developers.google.com/workspace/gmail/api/guides/sending).

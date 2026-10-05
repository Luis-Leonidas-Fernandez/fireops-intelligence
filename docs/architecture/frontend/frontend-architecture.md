# Arquitectura actual del frontend

La web usa HTML/CSS/JavaScript sin framework ni compilación. FastAPI la sirve en el mismo origen que la API. El dashboard contiene datos de demostración, pero el registro y el acceso con correo/contraseña están conectados al backend. [ADR-003](../adr/ADR-003-frontend-architecture.md) explica la elección tecnológica provisional; [ADR-005](../adr/ADR-005-email-password-authentication.md) documenta la autenticación.

## Páginas y recursos

| Ruta | Archivo | Responsabilidad |
|---|---|---|
| `/` | `frontend/index.html` | Dashboard de demostración, servido solo con cookie válida |
| `/registro` | `frontend/pages/registro/index.html` | Registro con correo/contraseña, nombre opcional o Google |
| `/iniciar-sesion` | `frontend/pages/iniciar-sesion/index.html` | Acceso con correo/contraseña o Google |
| `/css/*`, `/js/*` | `frontend/css/`, `frontend/js/` | Estilos y comportamiento |

`frontend/js/data.js` contiene métricas ilustrativas; `render.js` las dibuja; `app.js` conecta los controles, el CSV de demostración, el cambio claro/oscuro y el indicador de API. `GET /health` y `GET /inventory/categories` alimentan ese indicador y el conteo de categorías. `frontend/js/profile.js` consulta `GET /auth/me` con la cookie local para mostrar el nombre del usuario autenticado, o su correo si no hay nombre; el avatar deriva sus iniciales. El resto de tarjetas, movimientos y alertas no consulta bienes reales.

## Navegación y seguridad

`frontend/js/validations/credentials.js` normaliza y valida correo, contraseña y nombre opcional en registro antes del envío. `frontend/js/auth-form.js` reutiliza el flujo de ambos formularios: errores de campo, botón deshabilitado y animación durante la petición, mensaje de éxito o modal con `error.code` y `error.message` del backend. Registro llama a `POST /auth/register`; login a `POST /auth/login`, ambos con `credentials: "same-origin"`. Tras éxito redirigen a `/`; un error no redirige. El servidor vuelve a validar y establece la cookie HttpOnly, que JavaScript no lee. El botón Google navega a `/auth/google/start`; el servidor completa el flujo y devuelve códigos de error controlados a los formularios.

El dashboard ofrece **Vincular Google** en el menú del perfil. Esa acción requiere una sesión local y la coincidencia de correos. El frontend solo muestra el resultado; no lee ni almacena tokens Google. La verificación y el vínculo pertenecen al backend.

`frontend/js/app.js` llama a `POST /auth/logout` y después navega a `/iniciar-sesion`. Si falta una cookie válida, el servidor responde `303` en `/`. Esto protege la página, **no autoriza** los endpoints de inventario. Cuando la petición de logout llega al servidor, la respuesta elimina la cookie; si falla la red, el frontend igualmente navega al inicio de sesión y no puede garantizar que la cookie se haya eliminado. Un JWT previamente copiado no se revoca antes de vencer.

El botón de brillo cambia `html[data-theme]` entre oscuro y claro mientras la página está abierta. La elección no se guarda tras recargar. Hay CSS adaptativo para escritorio y móvil; las etiquetas del sidebar siguen siendo vistas ilustrativas, no rutas adicionales implementadas.

## Entrega local y caché

`app/main.py` sirve la web y la API en `127.0.0.1:8000`. Las respuestas de HTML/CSS/JS y `/auth/*` usan `Cache-Control: no-store`; el dashboard enlaza assets versionados para evitar copias antiguas en Brave. `scripts/test-up.sh` y `scripts/test-up.ps1` levantan el servidor con `fireassets_test` y `--no-access-log`, pero no ejecutan migraciones. Desde la raíz, `node --test` descubre los tests del formulario y del perfil sin instalar un framework JS.

Véase [guía del frontend](../../../frontend/README.md) y [estado del proyecto](../../PROGRESS.md).

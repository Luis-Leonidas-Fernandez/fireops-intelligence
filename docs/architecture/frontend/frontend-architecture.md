# Arquitectura actual del frontend

La web actual es una demostración en HTML/CSS/JavaScript sin framework ni compilación. FastAPI la sirve en el mismo origen que la API. [ADR-003](../adr/ADR-003-frontend-architecture.md) explica esta elección provisional.

## Páginas y recursos

| Ruta | Archivo | Responsabilidad |
|---|---|---|
| `/` | `frontend/index.html` | Dashboard de demostración |
| `/registro` | `frontend/pages/registro/index.html` | Formulario visual de registro |
| `/iniciar-sesion` | `frontend/pages/iniciar-sesion/index.html` | Formulario visual de acceso |
| `/css/*`, `/js/*` | `frontend/css/`, `frontend/js/` | Estilos y comportamiento |

`frontend/js/data.js` contiene métricas ilustrativas; `render.js` las dibuja; `app.js` conecta los controles, el CSV de demostración, el cambio claro/oscuro y el indicador de API. Solo `GET /health` y `GET /inventory/categories` alimentan ese indicador y el conteo de categorías. El resto de tarjetas, movimientos y alertas no consulta bienes reales.

## Navegación y seguridad

Registro e inicio de sesión navegan a `/` al enviar el formulario o pulsar Google, sin petición de autenticación ni validación de credenciales. «Cerrar sesión» navega a `/iniciar-sesion`; no existe sesión de usuario que cerrar. La ruta `/` sigue accesible directamente. **La navegación no equivale a autorización.**

El botón de brillo cambia `html[data-theme]` entre oscuro y claro mientras la página está abierta. La elección no se guarda tras recargar. Hay CSS adaptativo para escritorio y móvil; las etiquetas del sidebar siguen siendo vistas ilustrativas, no rutas adicionales implementadas.

## Entrega local y caché

`app/main.py` sirve la web y la API en `127.0.0.1:8000`. Las respuestas de HTML/CSS/JS del frontend usan `Cache-Control: no-store` y el dashboard enlaza assets versionados para evitar copias antiguas en Brave. `scripts/test-up.sh` y `scripts/test-up.ps1` levantan el servidor con `fireassets_test`, pero no ejecutan migraciones.

Véase [guía del frontend](../../../frontend/README.md) y [estado del proyecto](../../PROGRESS.md).

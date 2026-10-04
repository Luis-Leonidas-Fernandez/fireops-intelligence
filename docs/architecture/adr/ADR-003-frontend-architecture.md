# ADR-003 — Frontend de demostración servido por FastAPI

- **Estado:** aceptado como registro retrospectivo de la implementación actual.
- **Fecha de registro:** 2026-10-03.
- **Alcance:** interfaz local de demostración; no es una decisión definitiva para el cliente operativo.
- **Origen:** traslado y revisión del antiguo `docs/frontend-decision.md`, que proponía React + Vite + TypeScript. Esa ruta ya no existe.

## Contexto

El equipo ya dispone de endpoints FastAPI y necesita visualizar el proyecto sin introducir un segundo servidor ni un proceso de compilación de JavaScript. La propuesta previa recomendaba React, pero el código en ejecución es HTML, CSS y JavaScript sin framework.

## Decisión registrada

Se conserva la interfaz actual en `frontend/` y FastAPI la sirve junto con la API desde `127.0.0.1:8000`: dashboard en `/`, registro en `/registro` e inicio de sesión en `/iniciar-sesion`. Los archivos CSS y JS se sirven desde `/css/*` y `/js/*`. El dashboard consulta `GET /health` y `GET /inventory/categories` para el indicador de conexión y el conteo de categorías. Las demás cifras, tablas, alertas, movimientos y exportación CSV son ilustrativos.

Registro e inicio de sesión ahora comparten el controlador `frontend/js/auth-form.js` y las reglas cliente de `frontend/js/validations/credentials.js`. Envían credenciales a la API del mismo origen, muestran carga, feedback o errores y solo redirigen tras éxito. FastAPI exige una cookie de acceso válida antes de servir `/`; [ADR-005](ADR-005-email-password-authentication.md) registra el mecanismo y sus límites.

Para evitar que Brave combine HTML nuevo con scripts antiguos, las respuestas HTML/CSS/JS del frontend y `/auth/*` usan `Cache-Control: no-store`; el dashboard referencia además sus assets con una versión en la URL. Hay estilos responsive y un control de modo oscuro/claro en la página actual; la preferencia no se persiste.

## Alternativas consideradas

| Opción | Situación |
|---|---|
| React + Vite + TypeScript | Propuesta diferida para una futura interfaz operativa más compleja; no existe en este repositorio. Los formularios actuales funcionan con JavaScript sin framework. |
| Segundo servidor estático local | Innecesario para la demo actual porque FastAPI ya sirve ambos lados en el mismo origen. |
| Astro o Flutter | No seleccionados para esta interfaz local. |

## Consecuencias y límites

Hay autenticación local por correo y contraseña. El botón de Google sigue visible pero **no implementa OAuth**: muestra un aviso y no abre el dashboard. «Cerrar sesión» solicita `/auth/logout` para borrar la cookie; el frontend redirige aunque la petición falle, por lo que ese borrado no está garantizado en caso de error de red. La ruta `/` exige token válido, pero la API de inventario y `/docs` todavía no exigen autorización; el JWT no tiene revocación inmediata del lado del servidor. Las métricas del dashboard siguen siendo demostrativas.

## Evidencia

`app/main.py`, `frontend/index.html`, `frontend/pages/`, `frontend/css/`, `frontend/js/` y [descripción de la arquitectura actual](../frontend/frontend-architecture.md).

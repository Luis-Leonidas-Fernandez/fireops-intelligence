# ADR-003 — Frontend de demostración servido por FastAPI

- **Estado:** aceptado como registro retrospectivo de la implementación actual.
- **Fecha de registro:** 2026-10-03.
- **Alcance:** interfaz local de demostración; no es una decisión definitiva para el cliente operativo.
- **Origen:** traslado y revisión del antiguo `docs/frontend-decision.md`, que proponía React + Vite + TypeScript. Esa ruta ya no existe.

## Contexto

El equipo ya dispone de endpoints FastAPI y necesita visualizar el proyecto sin introducir un segundo servidor ni un proceso de compilación de JavaScript. La propuesta previa recomendaba React, pero el código en ejecución es HTML, CSS y JavaScript sin framework.

## Decisión registrada

Se conserva la interfaz actual en `frontend/` y FastAPI la sirve junto con la API desde `127.0.0.1:8000`: dashboard en `/`, registro en `/registro` e inicio de sesión en `/iniciar-sesion`. Los archivos CSS y JS se sirven desde `/css/*` y `/js/*`. El dashboard consulta `GET /health` y `GET /inventory/categories` para el indicador de conexión y el conteo de categorías. Las demás cifras, tablas, alertas, movimientos y exportación CSV son ilustrativos.

Para evitar que Brave combine HTML nuevo con scripts antiguos, las respuestas HTML/CSS/JS del frontend usan `Cache-Control: no-store`; el dashboard referencia además sus assets con una versión en la URL. Hay estilos responsive y un control de modo oscuro/claro en la página actual; la preferencia no se persiste.

## Alternativas consideradas

| Opción | Situación |
|---|---|
| React + Vite + TypeScript | Propuesta diferida para una futura interfaz operativa con estado, formularios y rutas reales; no existe en este repositorio. |
| Segundo servidor estático local | Innecesario para la demo actual porque FastAPI ya sirve ambos lados en el mismo origen. |
| Astro o Flutter | No seleccionados para esta interfaz local. |

## Consecuencias y límites

No hay autenticación. Los formularios y el botón de Google navegan al dashboard sin enviar ni validar credenciales; «Cerrar sesión» navega a `/iniciar-sesion` sin invalidar una sesión. El dashboard puede abrirse directamente en `/`. Estas pantallas no protegen datos ni implementan OAuth. La decisión sobre un frontend operativo debe revisarse cuando existan requisitos y contratos API reales para reemplazar los datos ficticios.

## Evidencia

`app/main.py`, `frontend/index.html`, `frontend/pages/`, `frontend/css/`, `frontend/js/` y [descripción de la arquitectura actual](../frontend/frontend-architecture.md).

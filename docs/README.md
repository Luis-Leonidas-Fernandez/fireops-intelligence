# Mapa de documentación

Esta carpeta separa **cómo iniciar el proyecto**, **cómo está construido hoy**, **por qué se eligieron ciertas decisiones** y **qué se estudió en la fase inicial**. Empezar por [progreso](PROGRESS.md) para distinguir trabajo terminado de tareas pendientes.

| Necesidad | Leer |
|---|---|
| Preparar el entorno | [macOS](getting-started/macos.md) o [Windows](getting-started/windows.md) |
| Configurar acceso con Google | [Guía Google OAuth](getting-started/google-oauth.md) |
| Entender el backend actual | [Arquitectura del backend](architecture/backend/backend-architecture.md) |
| Entender la web actual | [Arquitectura del frontend](architecture/frontend/frontend-architecture.md) |
| Comprender registro, login y sus límites | [ADR-005: autenticación](architecture/adr/ADR-005-email-password-authentication.md) |
| Configurar el nombre de perfil y el app bar | [Arquitectura del frontend](architecture/frontend/frontend-architecture.md) y [backend](architecture/backend/backend-architecture.md) |
| Revisar decisiones y propuestas | [Índice de ADR](architecture/adr/README.md) |
| Conocer el alcance y los pendientes | [Progreso](PROGRESS.md) y [Task 06](../labs/TASK_06_GET_ASSET_BY_ID.md) |

## Cómo está organizada la carpeta

- `getting-started/`: guías de instalación y material de configuración/clases para Windows en Markdown y Word.
- `architecture/`: descripción del sistema actual, ADR y futuros diagramas. Un ADR explica **por qué** se tomó o propuso una decisión; un documento de arquitectura explica **cómo** funciona el código vigente.
- `architecture/history/architecture-history/`: dos informes históricos con propuestas de diseño en Markdown. No son una especificación implementada; el modelo JSONB que describen aún no existe en las migraciones.
- `Phase_01/`: requisitos, análisis del desajuste objeto-relacional y modelos conceptual, lógico y físico de la fase inicial. Se conserva como material de análisis, no como descripción del esquema desplegado.
- `PROGRESS.md`: bitácora y estado actual del equipo.

El [README principal](../README.md) ofrece el resumen del repositorio. Las guías de clase terminadas están en `labs/completed/`; la Task 06 sigue en `labs/` porque está pendiente.

**Estado de acceso:** registro/login por correo y contraseña y Google OAuth funcionan con la configuración correspondiente; `/` exige una cookie de sesión válida. `GET /auth/me` proporciona el nombre o correo autenticado al app bar. La autorización de los endpoints de inventario no está implementada. Las cifras del dashboard continúan siendo ilustrativas. Consulte [progreso](PROGRESS.md) para distinguir el estado del código de la aplicación de las propuestas históricas.

## Documentos Word convertidos

Las versiones Markdown permiten leer el contenido directamente en GitHub. Los `.docx` que aún se conservan permiten consultar el formato original.

- Inicio: [Configuración en Windows](getting-started/guia-configuracion-git-github-postgresql-codex-windows.md) y [Plan de clases](getting-started/plan-clases-fireops-windows.md).
- Historia de arquitectura: [Decisión 1.0](architecture/history/architecture-history/desicion_1.0_docx.md) y [Decisión 1.1](architecture/history/architecture-history/desicion_1.1_.md).
- Fase 01: [Desajuste objeto-relacional](Phase_01/data-modeling/desajuste-objeto-relacicional/Desajuste_objeto_relacional_Inventario_Bomberos.md), [Guía del modelo físico](Phase_01/data-modeling/guie.md), [Cambios sugeridos al modelo físico](Phase_01/data-modeling/modelado/Cambios_sugeridos_modelo_fisico_inventario_bomberos.md) y [Requisitos no funcionales](Phase_01/requirements/Requisitos_no_funcionales_Inventario_Bomberos.md).

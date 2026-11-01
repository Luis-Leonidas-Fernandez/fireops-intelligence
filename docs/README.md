# Mapa de documentación

Esta carpeta separa **cómo iniciar el proyecto**, **cómo está construido hoy**, **por qué se eligieron ciertas decisiones**, **procedimientos operativos** y **qué se estudió en la fase inicial**. Empezar por [progreso](PROGRESS.md) para distinguir trabajo terminado de tareas pendientes.

| Necesidad | Leer |
|---|---|
| Preparar el entorno | [macOS](getting-started/macos.md) o [Windows](getting-started/windows.md) |
| Configurar acceso con Google | [Guía Google OAuth](getting-started/google-oauth.md) |
| Entender el backend actual (inventario, vehículos, contratos API y diagramas) | [Arquitectura del backend](architecture/backend/backend-architecture.md) |
| Entender la web actual (Ubicaciones, Categorías, Vehículos, Nuevo bien y Mover bien) | [Arquitectura del frontend](architecture/frontend/frontend-architecture.md) |
| Comprender registro, login, invitaciones y sus límites | [ADR-005: autenticación](architecture/adr/ADR-005-email-password-authentication.md) y [Aprobación de registro](getting-started/registration-approval.md) |
| Comprender contenedores móviles automáticos para vehículos | [ADR-007: contenedores vehiculares automáticos](architecture/adr/ADR-007-automatic-vehicle-containers.md) |
| Revisar decisiones arquitectónicas | [Índice de ADR](architecture/adr/README.md) |
| Operación, preflight de migraciones y recuperación | [Runbook de preflight](migration_preflight_runbook.md) y [Runbook de producción](production_operations_runbook.md) |
| Conocer el alcance, validaciones y pendientes | [Progreso](PROGRESS.md) |

## Cómo está organizada la carpeta

- `getting-started/`: guías de instalación, Google OAuth, invitaciones por Gmail, aprobación de registro y material de configuración/clases.
- `architecture/`: descripción del sistema actual ([backend](architecture/backend/backend-architecture.md) y [frontend](architecture/frontend/frontend-architecture.md)) e [índice de ADR](architecture/adr/README.md). Un ADR explica **por qué** se tomó una decisión; un documento de arquitectura explica **cómo** funciona el código vigente.
- `architecture/history/architecture-history/`: dos informes históricos con propuestas de diseño inicial en Markdown. Se conservan como antecedentes de diseño; el modelo JSONB completo que describen aún no existe en las migraciones.
- `Phase_01/`: requisitos, análisis del desajuste objeto-relacional y modelos conceptual, lógico y físico de la fase inicial. Se conserva como material de análisis inicial.
- `PROGRESS.md`: bitácora cronológica y estado actual del proyecto.

El [README principal](../README.md) ofrece el resumen general del repositorio.

**Estado actual del sistema:** el inicio de sesión por correo/contraseña, Google OAuth y el flujo de solicitudes/invitaciones están operativos; `/` y las doce rutas de `/inventory/...` exigen una sesión válida con rol activo `ADMINISTRADOR` o `SUPERVISOR`. El frontend consulta datos reales de PostgreSQL para las vistas de `Bienes`, `Categorías`, `Ubicaciones`, `Vehículos` y `Movimientos`, incluyendo la habilitación automática y transaccional de vehículos como contenedores móviles al registrar o trasladar bienes. Consulte [progreso](PROGRESS.md) para el detalle completo y las limitaciones conocidas.

## Documentos Word convertidos

Las versiones Markdown permiten leer el contenido directamente en GitHub. Los `.docx` que aún se conservan permiten consultar el formato original.

- Inicio: [Configuración en Windows](getting-started/guia-configuracion-git-github-postgresql-codex-windows.md) y [Plan de clases](getting-started/plan-clases-fireops-windows.md).
- Historia de arquitectura: [Decisión 1.0](architecture/history/architecture-history/desicion_1.0_docx.md) y [Decisión 1.1](architecture/history/architecture-history/desicion_1.1_.md).
- Fase 01: [Desajuste objeto-relacional](Phase_01/data-modeling/desajuste-objeto-relacicional/Desajuste_objeto_relacional_Inventario_Bomberos.md), [Guía del modelo físico](Phase_01/data-modeling/guie.md), [Cambios sugeridos al modelo físico](Phase_01/data-modeling/modelado/Cambios_sugeridos_modelo_fisico_inventario_bomberos.md) y [Requisitos no funcionales](Phase_01/requirements/Requisitos_no_funcionales_Inventario_Bomberos.md).

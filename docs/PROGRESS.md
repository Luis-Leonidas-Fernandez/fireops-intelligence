# Progreso del proyecto

Este archivo registra el trabajo realizado en cada jornada. Está versionado junto con el repositorio para que todo el equipo pueda consultar el avance desde GitHub.

## Cómo actualizar este archivo

Al finalizar una jornada, decime `cerramos la jornada`. Se agregará una nueva fecha con las tareas completadas, los archivos modificados, los descubrimientos, los pendientes y el próximo paso recomendado.

## Estado actual

- La migración `0374d9a573a1` define `categorias` y `bienes`, con clave foránea de bien a categoría. Cada integrante debe aplicarla en su propia base; este archivo no confirma el estado de cada PostgreSQL local.
- Están implementados `POST /inventory/assets`, `POST /inventory/categories` y `GET /inventory/categories`. La Task 05 fue completada y el equipo confirmó sus pruebas en sus entornos en septiembre.
- La **Task 06 sigue pendiente**: `app/modules/inventory/get_asset/router.py` y `tests/modules/inventory/test_get_asset_endpoint.py` están vacíos, y el router no está registrado. `GET /inventory/assets` y `GET /inventory/assets/{asset_id}` todavía no existen.
- FastAPI sirve un dashboard HTML/CSS/JS en `/`, registro en `/registro` e inicio de sesión en `/iniciar-sesion`. No hay autenticación real ni protección del dashboard.
- Dashboard: diseño responsive, acento rojo, modo claro/oscuro, datos ilustrativos y conteo real de categorías. Las cifras, movimientos, alertas y CSV son demostraciones; no representan el inventario de PostgreSQL.
- Los formularios y el botón de Google solo navegan a `/`. «Cerrar sesión» navega a `/iniciar-sesion`, sin invalidar sesión alguna.
- `scripts/test-up.sh` y `scripts/test-up.ps1` inician API y web con `.venv` y `.env.test`, verificando que la URL apunte a `fireassets_test`; no crean la base ni ejecutan migraciones.
- La guía de SQLTools sigue en `vscode-tools.md`. `docs/README.md` organiza las guías, la arquitectura actual y los ADR; el ADR-004 de aislamiento de tests está propuesto, no implementado.

## Registro de jornadas

### 2026-10-03

#### Completado

- Se incorporó a FastAPI el frontend local: dashboard y páginas separadas de registro e inicio de sesión.
- Se refinó el dashboard para el contexto de bomberos: tarjetas adaptables, sidebar, icono de fuego, paleta roja y barra de estado segmentada por porcentaje. Los contenidos estadísticos continúan siendo ficticios.
- Se agregó el cambio visual entre modo oscuro y claro desde el app bar.
- Se conectó «Cerrar sesión» con `/iniciar-sesion`; el resto de los botones de acceso siguen siendo navegación simulada.
- Se evitó la mezcla de HTML nuevo con JavaScript cacheado en Brave mediante `Cache-Control: no-store` y URLs versionadas para recursos del dashboard.
- Se actualizaron README, ADR, guías de inicio y esta bitácora para separar funcionalidades reales, demostraciones y pendientes.
- Se reorganizó `docs/`: Word de configuración/clases en `getting-started/`, arquitectura actual en `architecture/backend/` y `architecture/frontend/`, y cuatro ADR en `architecture/adr/`. `Phase_01/` y `architecture-history/` conservan sus archivos originales.
- Verificación de esta actualización: `python -m pytest -q tests/test_main_endpoints.py` → 8 pruebas correctas; no se ejecutó aquí la suite completa contra PostgreSQL.

#### Pendiente

- Implementar y probar la Task 06 (listar bienes y obtener un bien por ID, con aislamiento de tests).
- Decidir e implementar el flujo de entrada por inicio de sesión: actualmente el enlace de Uvicorn abre `/`, que sirve el dashboard.
- Diseñar autenticación/autorización real antes de usar las pantallas de acceso para proteger datos.
- Sustituir métricas ficticias por endpoints y contratos de datos reales cuando ese alcance se apruebe.

#### Próximo paso recomendado

Implementar Task 06 en una rama de trabajo y mantener el frontend claramente rotulado como demostración hasta contar con datos reales y autenticación.

### 2026-09-30

#### Completado

- Se creó `labs/TASK_06_GET_ASSET_BY_ID.md` para especificar el endpoint de consulta de un bien individual y sus pruebas.
- Se creó `labs/completed/` y se archivaron allí las guías de Tasks 01–05, consideradas terminadas por el equipo.
- Se actualizó el estado de las Tasks 03–06 y la recomendación de secuencia de trabajo.
- Se agregaron scripts cortos para iniciar la API con `fireassets_test` en macOS y Windows, con validación de la base antes de ejecutar Uvicorn.

#### Decisiones importantes

- Nota histórica: inicialmente se describió Task 06 como consulta individual. La guía actual también incluye listado de bienes; prevalece `labs/TASK_06_GET_ASSET_BY_ID.md`.
- Los tests de la Task 06 deben usar `fireassets_test` y no depender de registros manuales ni de IDs fijos.
- Los scripts `scripts/test-up.sh` y `scripts/test-up.ps1` usan `.venv`, cargan `.env.test` y se niegan a iniciar si la URL no apunta a `fireassets_test`.
- Una guía se considera terminada para archivarla cuando el equipo confirma que la implementación correspondiente quedó integrada en `main`.

#### Pendiente

- Implementar y probar el listado y la consulta por ID de bienes en la Task 06.

#### Próximo paso recomendado

El equipo confirmó que la Task 05 pasa en todas las máquinas; iniciar la implementación de la Task 06 en ramas individuales.

### 2026-09-19

#### Completado

- Se reorganizó la Task 04 para no repetir el trabajo terminado del endpoint de bienes de la Task 03.
- Se documentó el flujo de endpoints de categorías para Windows y macOS.
- Se creó el documento Word de la Task 04:
  - `labs/completed/TASK_04_ENDPOINTS_CATEGORIAS.docx`
- Se amplió la guía de SQLTools y PostgreSQL:
  - `vscode-tools.md`
- Se habilitó y seleccionó Material Icon Theme en VS Code.
- Se creó esta bitácora de progreso.

#### Decisiones importantes

- El proyecto utiliza SQLTools junto con el driver PostgreSQL/CockroachDB para trabajar visualmente con la base de datos.
- `fireassets` es la base del proyecto; `sql_learning` pertenece a otra conexión y no debe utilizarse para este repositorio.
- El trabajo terminado de la Task 03 no debe mezclarse con la Task 04.
- El progreso del equipo se registra en este archivo Markdown versionado.

#### Pendiente en ese momento

- Implementar `POST /inventory/categories`.
- Implementar `GET /inventory/categories`.
- Registrar el router de categorías en `app/main.py`.
- Probar ambos endpoints desde Swagger y SQLTools.

#### Próximo paso recomendado

Implementar la carpeta `register_category`, sus schemas y su router siguiendo la Task 04. (Este pendiente histórico se resolvió después.)

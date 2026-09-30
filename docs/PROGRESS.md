# Progreso del proyecto

Este archivo registra el trabajo realizado en cada jornada. Está versionado junto con el repositorio para que todo el equipo pueda consultar el avance desde GitHub.

## Cómo actualizar este archivo

Al finalizar una jornada, decime `cerramos la jornada`. Se agregará una nueva fecha con las tareas completadas, los archivos modificados, los descubrimientos, los pendientes y el próximo paso recomendado.

## Estado actual

- PostgreSQL está conectado a la base de datos `fireassets`.
- Existen las tablas iniciales `categorias` y `bienes`.
- El endpoint `POST /inventory/assets` fue implementado en la Task 03.
- Las Tasks 03 y 04 ya implementaron:
  - `POST /inventory/assets`
  - `POST /inventory/categories`
  - `GET /inventory/categories`
- La Task 05 está completada y el equipo confirmó que sus pruebas pasan en todos los entornos.
- La Task 06 agrega `GET /inventory/assets` para listar bienes y `GET /inventory/assets/{asset_id}` para consultar uno por ID; contempla respuestas `200`, `404` y `422`.
- La guía de SQLTools está en `vscode-tools.md`.
- Material Icon Theme está habilitado y seleccionado en el espacio de trabajo local de VS Code.

## Registro de jornadas

### 2026-09-30

#### Completado

- Se creó `labs/TASK_06_GET_ASSET_BY_ID.md` para especificar el endpoint de consulta de un bien individual y sus pruebas.
- Se creó `labs/completed/` y se archivaron allí las guías de Tasks 01–05, consideradas terminadas por el equipo.
- Se actualizó el estado de las Tasks 03–06 y la recomendación de secuencia de trabajo.
- Se agregaron scripts cortos para iniciar la API con `fireassets_test` en macOS y Windows, con validación de la base antes de ejecutar Uvicorn.

#### Decisiones importantes

- La Task 06 no crea una migración ni lista todos los bienes: consulta un único bien por su ID.
- Los tests de la Task 06 deben usar `fireassets_test` y no depender de registros manuales ni de IDs fijos.
- Los scripts `scripts/test-up.sh` y `scripts/test-up.ps1` usan `.venv`, cargan `.env.test` y se niegan a iniciar si la URL no apunta a `fireassets_test`.
- Una guía se considera terminada para archivarla cuando el equipo confirma que la implementación correspondiente quedó integrada en `main`.

#### Pendiente

- Implementar y probar `GET /inventory/assets/{asset_id}` en la Task 06.

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

# Progreso del proyecto

Este archivo registra el trabajo realizado en cada jornada. Está versionado junto con el repositorio para que todo el equipo pueda consultar el avance desde GitHub.

## Cómo actualizar este archivo

Al finalizar una jornada, decime `cerramos la jornada`. Se agregará una nueva fecha con las tareas completadas, los archivos modificados, los descubrimientos, los pendientes y el próximo paso recomendado.

## Estado actual

- PostgreSQL está conectado a la base de datos `fireassets`.
- Existen las tablas iniciales `categorias` y `bienes`.
- El endpoint `POST /inventory/assets` fue implementado en la Task 03.
- La Task 04 está enfocada únicamente en los endpoints pendientes de categorías:
  - `POST /inventory/categories`
  - `GET /inventory/categories`
- La guía de SQLTools está en `vscode-tools.md`.
- Material Icon Theme está habilitado y seleccionado en el espacio de trabajo local de VS Code.

## Registro de jornadas

### 2026-09-19

#### Completado

- Se reorganizó la Task 04 para no repetir el trabajo terminado del endpoint de bienes de la Task 03.
- Se documentó el flujo de endpoints de categorías para Windows y macOS.
- Se creó el documento Word de la Task 04:
  - `labs/TASK_04_ENDPOINTS_CATEGORIAS.docx`
- Se amplió la guía de SQLTools y PostgreSQL:
  - `vscode-tools.md`
- Se habilitó y seleccionó Material Icon Theme en VS Code.
- Se creó esta bitácora de progreso.

#### Decisiones importantes

- El proyecto utiliza SQLTools junto con el driver PostgreSQL/CockroachDB para trabajar visualmente con la base de datos.
- `fireassets` es la base del proyecto; `sql_learning` pertenece a otra conexión y no debe utilizarse para este repositorio.
- El trabajo terminado de la Task 03 no debe mezclarse con la Task 04.
- El progreso del equipo se registra en este archivo Markdown versionado.

#### Pendiente

- Implementar `POST /inventory/categories`.
- Implementar `GET /inventory/categories`.
- Registrar el router de categorías en `app/main.py`.
- Probar ambos endpoints desde Swagger y SQLTools.
- Comitear la documentación actualizada y este archivo de progreso.

#### Próximo paso recomendado

Implementar la carpeta `register_category`, sus schemas y su router siguiendo la Task 04.

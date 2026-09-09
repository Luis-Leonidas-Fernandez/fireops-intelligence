# Labs de aprendizaje — FireOps Intelligence

Esta carpeta contiene la ruta de clase para que los participantes aprendan a trabajar con FastAPI, PostgreSQL, SQLAlchemy, Alembic, tests y Git sin tocar `main` directamente.

## Herramientas obligatorias antes de codificar

Antes de empezar con código, cada participante debe tener funcionando:

```text
Git
GitHub Desktop o GitHub CLI
Python
PostgreSQL
Visual Studio Code
Extensiones de VS Code para Python, Ruff y PostgreSQL
Dependencias instaladas desde requirements.txt
Codex como asistente de aprendizaje opcional
```

Codex se puede usar para instalar, diagnosticar y explicar errores. No se debe usar para entregar código que el participante no pueda explicar.

## Cómo se trabaja en clase

Todos los participantes hacen la misma tarea al mismo tiempo.

Cada participante trabaja en su propia rama y sube una Pull Request para revisión.

El responsable del proyecto decide qué versión se mergea a `main`.

## Carpetas

```text
labs/
├── participant_1/
├── participant_2/
├── participant_3/
└── participant_4/
```

Cada carpeta contiene:

```text
README.md
GIT_WORKFLOW.md
DATABASE_SETUP_WINDOWS.md
TASK_01_DATABASE_CONNECTION.md
TASK_02_CREATE_ASSET_TABLE.md
TASK_03_REGISTER_ASSET_ENDPOINT.md
TASK_04_TEST_REGISTER_ASSET.md
```

## Ruta de clase

1. **Task 01 — Entender y verificar la conexión con PostgreSQL**
   - `.env`
   - `settings.py` existente
   - `Base` existente
   - `engine` existente
   - `AsyncSession` existente
   - `get_database_session` existente

2. **Task 02 — Crear categorías y bienes**
   - modelo `Category`
   - modelo `Asset`
   - tablas `categorias` y `bienes`
   - Alembic
   - migración
   - `alembic upgrade head`

3. **Task 03 — Registrar bien usando DB**
   - schema de entrada
   - schema de respuesta
   - router
   - sesión de base de datos
   - insert
   - commit
   - refresh

4. **Task 04 — Test de registro**
   - `TestClient`
   - petición `POST`
   - validación de respuesta
   - verificación automática

## Regla principal

Nadie trabaja directo sobre `main`.

Cada participante crea su rama, completa la tarea, sube su rama y crea una Pull Request.

## Guías de soporte

- `GIT_WORKFLOW.md`: explica cómo crear rama, hacer commit, subir cambios y abrir PR.
- `DATABASE_SETUP_WINDOWS.md`: explica cómo instalar/verificar PostgreSQL en Windows y configurar `.env`.

## Qué hacer si algo falla

No improvisar comandos.

Enviar:

```text
Paso donde falló:
Comando ejecutado:
Resultado esperado:
Error completo:
Captura si aplica:
```


## Diagrama visual de endpoints

La Task 03 usa este diagrama para explicar el flujo de datos de cualquier endpoint:

```text
labs/assets/endpoint-data-flow-nodes.png
```

Lectura esperada:

```text
Cliente → Schema Request → Router → Modelo → Session → PostgreSQL → Schema Response → Cliente
```

La idea central es que un endpoint no es sólo una función. Es un recorrido completo desde un JSON de entrada hasta un JSON de respuesta.

## Decisión frontend para más adelante

Cuando llegue el momento de construir la web, la opción recomendada para la aplicación interna es:

```text
React + Vite + TypeScript
```

Motivo:

- enseña separación clara entre frontend y backend;
- permite consumir FastAPI por HTTP;
- es más simple para principiantes que Next.js;
- encaja bien con formularios, tablas, filtros y pantallas administrativas.

Astro puede quedar para documentación o landing pública. Flutter puede quedar para una futura app móvil o tablet.

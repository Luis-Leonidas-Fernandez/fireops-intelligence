# Ruta de clase del participante

Esta carpeta contiene tu ruta de aprendizaje para trabajar en FireOps Intelligence.

Vas a construir, paso a paso, un flujo real para registrar bienes en PostgreSQL usando FastAPI.

## Antes de empezar

Leé estos archivos en orden:

1. [`DATABASE_SETUP_WINDOWS.md`](./DATABASE_SETUP_WINDOWS.md) — preparar PostgreSQL y `.env` en Windows.
2. [`GIT_WORKFLOW.md`](./GIT_WORKFLOW.md) — crear rama, subir cambios y abrir PR.
3. [`TASK_01_DATABASE_CONNECTION.md`](./TASK_01_DATABASE_CONNECTION.md) — primera tarea de clase.

## Cómo vamos a trabajar

Todos hacemos la misma tarea al mismo tiempo.

Cada participante trabaja en una rama propia.

Ejemplo:

```text
participant-1/task-01-database-connection
participant-2/task-01-database-connection
participant-3/task-01-database-connection
participant-4/task-01-database-connection
```

El objetivo no es correr. El objetivo es entender.

## Tareas

| Orden | Archivo | Objetivo |
|---|---|---|
| 1 | `TASK_01_DATABASE_CONNECTION.md` | Entender y verificar la conexión existente con PostgreSQL |
| 2 | `TASK_02_CREATE_ASSET_TABLE.md` | Crear `categorias` y `bienes` |
| 3 | `TASK_03_REGISTER_ASSET_ENDPOINT.md` | Guardar un bien desde la API |
| 4 | `TASK_04_TEST_REGISTER_ASSET.md` | Probar el endpoint automáticamente |

## Flujo final que vamos a construir

```text
Usuario
  ↓
manda JSON
  ↓
FastAPI recibe la petición
  ↓
Pydantic valida los datos
  ↓
SQLAlchemy crea un registro
  ↓
PostgreSQL guarda el bien
  ↓
FastAPI devuelve el bien guardado
```

## Regla importante

Si algo falla, no sigas tirando comandos.

Copiá el error completo y pedí ayuda.

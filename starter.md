# Starter — iniciar Fire Control con la base de prueba

La forma corta de levantar API y web **en un solo servidor** es:

```bash
# macOS / Linux, desde la raíz del repositorio
./scripts/test-up.sh
```

```powershell
# Windows PowerShell, desde la raíz del repositorio
.\scripts\test-up.ps1
```

Los scripts usan el Python de `.venv` sin activación manual, seleccionan `.env.test`, comprueban que `DATABASE_URL` apunte a `fireassets_test` e inician Uvicorn en `127.0.0.1:8000`. Detené el servidor con `Ctrl+C`. **No** instalan dependencias, inician PostgreSQL, crean la base ni aplican migraciones.

## Antes del primer arranque

1. Instalá Python, PostgreSQL y las dependencias en `.venv`.
2. Creá la base local `fireassets_test` si no existe. Git no transporta bases de datos.
3. Creá `.env.test` con `DATABASE_URL` terminado en `/fireassets_test`. No lo subas a Git.
4. Aplicá la migración `0374d9a573a1` a esa base.

Seguí la guía completa para [macOS](docs/getting-started/macos.md) o [Windows](docs/getting-started/windows.md) para los comandos de primera instalación.

## URLs que vas a encontrar

| URL | Qué muestra hoy |
|---|---|
| `http://127.0.0.1:8000/` | Dashboard de demostración; es el enlace que ofrece Uvicorn |
| `http://127.0.0.1:8000/iniciar-sesion` | Página visual de inicio de sesión |
| `http://127.0.0.1:8000/registro` | Página visual de registro |
| `http://127.0.0.1:8000/docs` | Swagger UI con endpoints implementados |
| `http://127.0.0.1:8000/health` | Respuesta `{"status":"ok"}` |

**Importante:** todavía no hay autenticación. Los formularios y el icono de Google navegan al dashboard sin validar credenciales; «Cerrar sesión» vuelve a `/iniciar-sesion` sin destruir ninguna sesión. `/` se puede abrir directamente. El cambio para abrir la pantalla de inicio al hacer clic en el enlace de Uvicorn sigue pendiente.

## Endpoints disponibles y próximo trabajo

Swagger debe mostrar `POST /inventory/categories`, `GET /inventory/categories` y `POST /inventory/assets`. El listado y la consulta individual de bienes son parte de la [Task 06](labs/TASK_06_GET_ASSET_BY_ID.md) y **aún no están implementados**.

El dashboard muestra cifras ficticias. Solo consulta salud de la API y cantidad de categorías desde PostgreSQL. Para más detalles, leé [README](README.md), [frontend](frontend/README.md) y [progreso](docs/PROGRESS.md).

# FireOps Intelligence

FireOps Intelligence is a learning project for a fire-department inventory API. **Fire Control** is the name shown by its current web demo. The backend uses FastAPI, SQLAlchemy and PostgreSQL; FastAPI also serves a small HTML/CSS/JavaScript interface.

## Current state

| Available now | Not implemented yet |
|---|---|
| `POST /inventory/categories`, `GET /inventory/categories`, `POST /inventory/assets` | Listing assets and getting an asset by ID (Task 06) |
| PostgreSQL migration for `categorias` and `bienes` | Real registration, sign-in, Google OAuth or authorization |
| Dashboard, registration and sign-in **visual demos** | Live dashboard metrics, movements, alerts, CSV from real inventory data |

The dashboard's figures are illustrative. Its API indicator and category count read `GET /health` and `GET /inventory/categories`; they do not turn the other widgets into live data. Registration/sign-in buttons navigate to the dashboard **without validating or storing credentials**. “Cerrar sesión” returns to the sign-in page; it does not invalidate a session. Do not use these screens as access control.

## Quick start with the test database

Prerequisites: Python and PostgreSQL installed, a local `.venv` with dependencies from `requirements.txt`, and a private `.env.test` whose `DATABASE_URL` points to the existing `fireassets_test` database. Apply the committed Alembic migration to that database before using inventory endpoints. The startup scripts do **not** create the database or run migrations.

```bash
# macOS / Linux, from the repository root
./scripts/test-up.sh
```

```powershell
# Windows PowerShell, from the repository root
.\scripts\test-up.ps1
```

These scripts use the Python interpreter in `.venv`, set `ENV_FILE=.env.test` for the server process, reject a database name other than `fireassets_test`, and start Uvicorn at `http://127.0.0.1:8000`. Stop with `Ctrl+C`.

| URL | What it currently serves |
|---|---|
| `/` | Dashboard demo (the server link opens this page) |
| `/iniciar-sesion` | Sign-in visual demo |
| `/registro` | Registration visual demo |
| `/docs` | Swagger UI for implemented API endpoints |
| `/health` | `{"status":"ok"}` |

**Important:** `/` still opens the dashboard directly; the sign-in screen does not protect it. Opening the server link at sign-in instead is a separate pending routing change.

For first-time setup, including creation and migration of `fireassets_test`, see [macOS](docs/getting-started/macos.md) or [Windows](docs/getting-started/windows.md). Never commit `.env` or `.env.test`.

## API and data model

| Method and path | Result |
|---|---|
| `POST /inventory/categories` | Create a category; `201` on success |
| `GET /inventory/categories` | List categories ordered by ID; `200`, including `[]` |
| `POST /inventory/assets` | Create an asset linked to an existing category; `201` on success |

The `categorias` table has a unique name. The `bienes` table has a unique internal code and a required foreign key to `categorias.id`. The single committed migration is `0374d9a573a1`. See [Task 06](labs/TASK_06_GET_ASSET_BY_ID.md) for the **planned**, not yet implemented, read endpoints.

## Repository map

| Path | Purpose |
|---|---|
| `app/main.py` | FastAPI app, routes and static frontend serving |
| `app/modules/inventory/` | Inventory routers, schemas and SQLAlchemy models |
| `app/infrastructure/database/` | Async database engine and session dependency |
| `migrations/` | Alembic schema migration |
| `frontend/` | Vanilla HTML/CSS/JS dashboard and account-page demos |
| `scripts/` | Test-database startup and Task 05 test scripts |
| `tests/` | API tests; Task 06 test file is currently empty |
| `labs/` | Current and completed classroom tasks |
| `docs/` | Progress, setup guides and architecture decisions |

Start with the [documentation map](docs/README.md), then see [frontend usage](frontend/README.md), the [ADR index](docs/architecture/adr/README.md) and [project progress](docs/PROGRESS.md). The Word files under `docs/architecture-history/` are historical proposals, not the current runtime specification.

## Tests and limitations

With `.venv` active and `.env.test` pointing to `fireassets_test`, the Task 05 scripts run Alembic and pytest:

```bash
./scripts/task05_run_tests_mac.sh
```

```powershell
.\scripts\task05_run_tests_windows.ps1
```

These Task 05 scripts use the **current** `python` executable and do not independently verify the database name. Check the active environment and `.env.test` before running them. The frontend/static-route checks can be run separately with `python -m pytest -q tests/test_main_endpoints.py`.

The current interface is a prototype, not an authenticated application or a live operational inventory. React + Vite + TypeScript was proposed for a future internal frontend but is **not** the implementation in this repository today.

## Longer-term direction

The project aims to add reliable asset lifecycle tracking, responsibility and location records, movements, audit history and eventually operational analytics. Predictive maintenance or other AI features remain future possibilities, not current capabilities; they depend on trustworthy operational data first.

## License

No license has been selected yet.

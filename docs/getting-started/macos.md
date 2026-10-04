# Run FireOps Intelligence on macOS

This guide starts the current FastAPI API and Fire Control frontend against **`fireassets_test`**. The root URL currently shows the dashboard demo; sign-in is a separate, unprotected visual page at `/iniciar-sesion`.

## Prerequisites

Install Python 3.14, Git and PostgreSQL. Verify from Terminal:

```bash
python3 --version
git --version
psql --version
```

Homebrew is one possible installation method, not a runtime requirement. If PostgreSQL was installed through Homebrew, check/start the actual installed service with `brew services list` and `brew services start postgresql@18` (adjust the version to your installation). Confirm that `psql -d postgres -c 'SELECT current_user;'` connects before continuing.

## First-time setup

From the repository root (the folder containing `app/`, `requirements.txt` and `scripts/`):

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env.test
```

Edit `.env.test`. Keep `APP_NAME`, `ENVIRONMENT` and `SECRET_KEY` appropriate for your local installation, and set `DATABASE_URL` to your PostgreSQL user/host **and database `fireassets_test`**. Example shape (replace the placeholder):

```env
DATABASE_URL=postgresql+asyncpg://YOUR_USER:YOUR_PASSWORD@localhost:5432/fireassets_test
```

A local installation may use passwordless authentication or a different username. Do not commit `.env.test`; it is ignored by Git. If you also need a normal `.env`, keep it separate and do not use it for these test-database commands.

Check whether the test database exists:

```bash
psql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='fireassets_test';"
```

If the output is empty, create it with `createdb fireassets_test` (add the appropriate `-U`/`-h` flags for your PostgreSQL setup). The output `1` means it already exists. Each teammate creates the database on their own machine; Git does not transfer PostgreSQL databases.

**Before migrations**, confirm the `DATABASE_URL` in `.env.test` ends in `/fireassets_test`. Then apply the committed migration with that file selected for this command:

```bash
ENV_FILE=.env.test ./.venv/bin/python -m alembic upgrade head
```

Do **not** run `alembic init`: this repository already contains `alembic.ini`, `migrations/env.py` and migration `0374d9a573a1` for `categorias` and `bienes`.

## Daily start

```bash
./scripts/test-up.sh
```

The script uses `.venv` automatically, checks that `.env.test` names `fireassets_test`, and starts Uvicorn on `127.0.0.1:8000`. It does **not** install dependencies, start PostgreSQL, create the database or apply migrations. Stop with `Ctrl+C`.

| Address | Purpose |
|---|---|
| `http://127.0.0.1:8000/` | Dashboard demo; this is the clickable Uvicorn address |
| `http://127.0.0.1:8000/iniciar-sesion` | Sign-in visual demo |
| `http://127.0.0.1:8000/registro` | Registration visual demo |
| `http://127.0.0.1:8000/docs` | Implemented API endpoints in Swagger UI |
| `http://127.0.0.1:8000/health` | Health response |

The account-page buttons navigate to `/` without credential validation. “Cerrar sesión” returns to `/iniciar-sesion`, but no real session exists.

## Tests

With `.venv` activated (`source .venv/bin/activate`) and `.env.test` verified, `./scripts/task05_run_tests_mac.sh` applies migrations and runs pytest. This older test script uses the current `python` command and does **not** independently reject a wrong database name; check `.env.test` first. The Task 06 listing/get-by-ID implementation and its tests are still pending.

## Troubleshooting

- `No module named alembic`: install requirements into `.venv` and use `./.venv/bin/python` (not the system Python).
- Connection refused: start PostgreSQL and confirm host/port in `.env.test`.
- Authentication failed: confirm PostgreSQL user/password and URL encoding for reserved password characters.
- Port 8000 in use: stop the other Uvicorn process before running `test-up.sh`.
- Dashboard looks stale in Brave: reload the page. FastAPI sends `Cache-Control: no-store` for frontend HTML/CSS/JS, and dashboard assets use versioned URLs.

See [project README](../../README.md), [frontend details](../../frontend/README.md) and [progress](../PROGRESS.md).

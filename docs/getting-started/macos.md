# Run FireOps Intelligence on macOS

This guide starts the FastAPI API and Fire Control frontend against **`fireassets_test`**. Without a valid session, `/` redirects to `/iniciar-sesion`.

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

Replace the example `SECRET_KEY` with a **different, random value of at least 32 characters** in every environment. Generate one locally with `./.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))'`; copy its output into `.env.test` as `SECRET_KEY=...`. Never commit the value or share it with the team. A short key now prevents settings validation.

A local installation may use passwordless authentication or a different username. Do not commit `.env.test`; it is ignored by Git. If you also need a normal `.env`, keep it separate and do not use it for these test-database commands.

Check whether the test database exists:

```bash
psql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='fireassets_test';"
```

If the output is empty, create it with `createdb fireassets_test` (add the appropriate `-U`/`-h` flags for your PostgreSQL setup). The output `1` means it already exists. Each teammate creates the database on their own machine; Git does not transfer PostgreSQL databases.

**Before migrations**, confirm the `DATABASE_URL` in `.env.test` ends in `/fireassets_test`. Then apply the repository migrations with that file selected for this command:

```bash
ENV_FILE=.env.test ./.venv/bin/python -m alembic upgrade head
```

Do **not** run `alembic init`: this repository already contains Alembic configuration. `upgrade head` applies every missing revision, including inventory (`0374d9a573a1`), users (`b70e8e0479aa`), Google identity (`c4e9f1d2a7b3`) and optional display name (`d8b6e2f1940a`); no database content travels through Git.

## Daily start

```bash
./scripts/test-up.sh
```

The script uses `.venv` automatically, checks that `.env.test` names `fireassets_test`, and starts Uvicorn on `127.0.0.1:8000`. It does **not** install dependencies, start PostgreSQL, create the database or apply migrations. Stop with `Ctrl+C`.

| Address | Purpose |
|---|---|
| `http://127.0.0.1:8000/` | Dashboard demo; redirects to sign-in without a valid cookie |
| `http://127.0.0.1:8000/iniciar-sesion` | Sign in with email/password or configured Google OAuth |
| `http://127.0.0.1:8000/registro` | Create an account; display name is optional |
| `http://127.0.0.1:8000/auth/me` | Authenticated profile (`id`, email, optional display name) |
| `http://127.0.0.1:8000/docs` | Implemented API endpoints in Swagger UI |
| `http://127.0.0.1:8000/health` | Health response |

Registration and sign-in set an HttpOnly session cookie; the browser sends it automatically. “Cerrar sesión” calls `POST /auth/logout`, clears that cookie and returns to sign-in. Google sign-in and explicit account linking are available after the additional setup in the [Google OAuth guide](google-oauth.md). The inventory API is not yet authorization-protected.

## Tests

After verifying `.env.test` targets `fireassets_test` and applying migrations, run:

```bash
ENV_FILE=.env.test ./.venv/bin/python -m pytest -q
node --test
```

Node.js is needed only for the frontend tests. The backend auth fixture checks `SELECT current_database()` and rejects any database other than `fireassets_test`; other project tests may have different safeguards. `./scripts/task05_run_tests_mac.sh` remains available for its older class exercise, but uses the active `python` and does not independently validate the database name. Task 06 listing/get-by-ID remains pending.

## Troubleshooting

- `No module named alembic`: install requirements into `.venv` and use `./.venv/bin/python` (not the system Python).
- Connection refused: start PostgreSQL and confirm host/port in `.env.test`.
- Authentication failed: confirm PostgreSQL user/password and URL encoding for reserved password characters.
- `SECRET_KEY` validation error: replace the example value with a random key of at least 32 characters.
- Port 8000 in use: stop the other Uvicorn process before running `test-up.sh`.
- Dashboard looks stale in Brave: reload the page. FastAPI sends `Cache-Control: no-store` for frontend HTML/CSS/JS, and dashboard assets use versioned URLs.

See [project README](../../README.md), [frontend details](../../frontend/README.md) and [progress](../PROGRESS.md).

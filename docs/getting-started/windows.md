# Run FireOps Intelligence on Windows

Use **PowerShell** for these commands. The current FastAPI app serves the API and Fire Control demo from one local address; the safe classroom setup points to **`fireassets_test`**.

## Prerequisites

Install Python 3.14, Git and PostgreSQL (including command-line tools). Check:

```powershell
python --version
git --version
psql --version
Get-Service *postgres*
```

The PostgreSQL service should say `Running`. If `psql` is not recognized, add the installation's `bin` directory (for example `C:\Program Files\PostgreSQL\18\bin`) to your Windows `Path`, then reopen PowerShell. Keep your PostgreSQL username, password and port available; do not paste a password alone into the shell, because PowerShell will treat it as a command.

## First-time setup

From the repository root (the folder containing `app`, `requirements.txt` and `scripts`):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env.test
```

Edit `.env.test` and set `DATABASE_URL` for your PostgreSQL user/host and **`fireassets_test`**. Example shape (replace the placeholder):

```env
DATABASE_URL=postgresql+asyncpg://postgres:YOUR_PASSWORD@localhost:5432/fireassets_test
```

If the password has URL-reserved characters, URL-encode them. Do not commit `.env.test`; Git ignores it. The normal `.env`, if used, is separate and may name a different database.

Replace the example `SECRET_KEY` with a **different, random value of at least 32 characters** in each environment. Generate one locally with `& .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"`; copy its output into `.env.test` as `SECRET_KEY=...`. Do not commit or share the key. A short value fails settings validation.

Check whether the test database already exists. This is a PowerShell command; do not type raw SQL at the `PS>` prompt:

```powershell
psql -U postgres -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='fireassets_test';"
```

If the output is empty, create it with `createdb -U postgres fireassets_test` (supply `-h`/`-p` if your installation needs them). Output `1` means the database already exists. Each teammate needs their **own local** database.

Before migrating, confirm `.env.test` ends in `/fireassets_test`. Set `ENV_FILE` only for this PowerShell block and restore its previous value afterward:

```powershell
$previousEnvFile = $env:ENV_FILE
try {
    $env:ENV_FILE = ".env.test"
    & .\.venv\Scripts\python.exe -m alembic upgrade head
}
finally {
    if ($null -eq $previousEnvFile) {
        Remove-Item Env:ENV_FILE -ErrorAction SilentlyContinue
    } else {
        $env:ENV_FILE = $previousEnvFile
    }
}
```

Do **not** run `alembic init`: this repository already includes Alembic. `upgrade head` applies missing revisions for inventory (`0374d9a573a1`), users (`b70e8e0479aa`), Google identity (`c4e9f1d2a7b3`) and optional display name (`d8b6e2f1940a`). Git does not transfer database tables or rows.

## Daily start

```powershell
.\scripts\test-up.ps1
```

The script uses `.venv` without manual activation, checks that `.env.test` names `fireassets_test`, and starts Uvicorn on `127.0.0.1:8000`. It does **not** install dependencies, start PostgreSQL, create the database or apply migrations. Stop with `Ctrl+C`.

If PowerShell blocks local scripts, use a session-scoped policy and run the command again:

```powershell
Set-ExecutionPolicy -Scope Process RemoteSigned
.\scripts\test-up.ps1
```

| Address | Purpose |
|---|---|
| `http://127.0.0.1:8000/` | Dashboard demo; redirects to sign-in without a valid cookie |
| `http://127.0.0.1:8000/iniciar-sesion` | Sign in with email/password or configured Google OAuth |
| `http://127.0.0.1:8000/registro` | Create an account; display name is optional |
| `http://127.0.0.1:8000/auth/me` | Authenticated profile (`id`, email, optional display name) |
| `http://127.0.0.1:8000/docs` | Implemented API endpoints in Swagger UI |
| `http://127.0.0.1:8000/health` | Health response |

Registration and sign-in set an HttpOnly session cookie; the browser sends it automatically. “Cerrar sesión” calls `POST /auth/logout`, clears the cookie and returns to sign-in. Google sign-in and explicit account linking are available after the additional setup in the [Google OAuth guide](google-oauth.md). The inventory API is not yet authorization-protected.

## Tests

After verifying `.env.test` targets `fireassets_test` and applying migrations, run the backend tests with the environment variable scoped to this block:

```powershell
$previousEnvFile = $env:ENV_FILE
try {
    $env:ENV_FILE = ".env.test"
    & .\.venv\Scripts\python.exe -m pytest -q
}
finally {
    if ($null -eq $previousEnvFile) {
        Remove-Item Env:ENV_FILE -ErrorAction SilentlyContinue
    } else {
        $env:ENV_FILE = $previousEnvFile
    }
}
node --test
```

Node.js is needed only for the frontend tests. The backend auth fixture checks `SELECT current_database()` and rejects any database other than `fireassets_test`; other tests may have different safeguards. `.\scripts\task05_run_tests_windows.ps1` remains for the older class exercise but uses the active `python` and does not independently validate the database name. Task 06 listing/get-by-ID remains pending.

## Troubleshooting

- `No module named alembic`: install requirements into `.venv` and use its `python.exe`.
- Connection refused: check `Get-Service *postgres*`, host and port.
- Password authentication failed: use the PostgreSQL password for the configured user; do not type it as a standalone PowerShell command.
- `SECRET_KEY` validation error: replace the example with a random key of at least 32 characters.
- `psql` not found: use the full path to `psql.exe` or fix `Path`, then reopen PowerShell.
- Port 8000 in use: stop the other Uvicorn process before starting `test-up.ps1`.
- Browser shows an old dashboard: reload; FastAPI sends `Cache-Control: no-store` for frontend HTML/CSS/JS and uses versioned dashboard assets.

See [project README](../../README.md), [frontend details](../../frontend/README.md) and [progress](../PROGRESS.md).

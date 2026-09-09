# Running FireOps Intelligence on Windows

This guide explains how to prepare a Windows machine to run the FireOps Intelligence project locally.

It is written for beginners. Follow the steps in order and do not skip ahead.

> If a command fails, stop and ask for help. Do not try random commands.

---

## What you will prepare

By the end of this guide, your computer should have:

```text
Python installed
Git installed
PostgreSQL installed and running
the fireassets database created
the project cloned or opened
a virtual environment created
project dependencies installed
.env configured
FastAPI running locally
```

The full flow is:

```text
Windows
  ↓
Python + Git + PostgreSQL
  ↓
project folder
  ↓
.venv virtual environment
  ↓
requirements installed
  ↓
fireassets database
  ↓
.env configuration
  ↓
FastAPI server
```

---

## Before you begin

Use **PowerShell** for the commands in this guide.

To open PowerShell:

1. Open the Windows Start menu.
2. Search for `PowerShell`.
3. Open it.

Some commands may require **PowerShell as Administrator**. The guide will say when that is needed.

---

# 1. Check installed tools

Run:

```powershell
python --version
git --version
psql --version
```

If `python` does not work, try:

```powershell
py --version
```

Expected examples:

```text
Python 3.14.x
git version 2.x.x
psql (PostgreSQL) 18.x
```

If one command is not found, install that tool before continuing.

---

# 2. Install Python

Download Python from:

```text
https://www.python.org/downloads/
```

During installation, enable:

```text
Add Python to PATH
```

After installing, close and reopen PowerShell.

Verify:

```powershell
python --version
```

If that does not work, try:

```powershell
py --version
```

---

# 3. Install Git

Download Git for Windows from:

```text
https://git-scm.com/download/win
```

After installing, close and reopen PowerShell.

Verify:

```powershell
git --version
```

---

# 4. Install PostgreSQL

Download PostgreSQL for Windows from:

```text
https://www.postgresql.org/download/windows/
```

During installation, keep these components enabled:

```text
PostgreSQL Server
pgAdmin 4
Command Line Tools
```

Recommended values:

| Setting | Value |
|---|---|
| User | `postgres` |
| Port | `5432` |
| Database | `fireassets` |

PostgreSQL will ask you to choose a password for the `postgres` user.

Write that password down. You will need it later for `.env`.

> For local learning, use a simple password without symbols like `@`, `#`, `:`, `/`, or `%`. Example: `postgres123`.

After installing, close and reopen PowerShell.

Verify:

```powershell
psql --version
```

---

# 5. If `psql` is not recognized

If this command fails:

```powershell
psql --version
```

Windows probably does not know where PostgreSQL is installed.

The PostgreSQL command-line tools are usually here:

```text
C:\Program Files\PostgreSQL\18\bin
```

The version number may be different.

## Temporary check

Try:

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" --version
```

If that works, PostgreSQL is installed but missing from PATH.

Ask for help adding this folder to the Windows PATH:

```text
C:\Program Files\PostgreSQL\18\bin
```

After updating PATH, close and reopen PowerShell.

---

# 5.1. Add PostgreSQL to PATH correctly

If Windows shows two sections in Environment Variables, use **User variables** first.

Add this folder to the existing `Path` variable:

```text
C:\Program Files\PostgreSQL\18\bin
```

Do not create a new variable called `postgresql` and expect `psql` to work. Windows looks for commands inside `Path`.

Correct:

```text
User variables → Path → Edit → New → C:\Program Files\PostgreSQL\18\bin
```

Incorrect:

```text
User variables → New → postgresql = C:\Program Files\PostgreSQL\18\bin
```

After changing `Path`, close PowerShell and open it again. Then run:

```powershell
psql --version
```

---

# 6. Check that PostgreSQL is running

Run:

```powershell
Get-Service *postgres*
```

Expected example:

```text
Status   Name                DisplayName
------   ----                -----------
Running  postgresql-x64-18   postgresql-x64-18
```

The important word is:

```text
Running
```

If it says `Stopped`, open PowerShell as Administrator and run:

```powershell
Start-Service postgresql-x64-18
```

If your service has a different name, use the name shown by `Get-Service *postgres*`.

---

# 7. Connect to PostgreSQL

Run:

```powershell
psql -U postgres
```

PostgreSQL will ask for the password you created during installation.

Expected prompt:

```text
postgres=#
```

That means you are inside PostgreSQL.

---

# 8. Create the `fireassets` database

Inside PostgreSQL, list databases:

```sql
\l
```

Look for:

```text
fireassets
```

If it does not exist, create it:

```sql
CREATE DATABASE fireassets;
```

Expected result:

```text
CREATE DATABASE
```

Connect to it:

```sql
\c fireassets
```

Expected prompt:

```text
fireassets=#
```

Exit PostgreSQL:

```sql
\q
```

---

# 9. Clone or open the project

If you do not have the project yet, clone it:

```powershell
git clone <REPOSITORY_URL>
cd fire-control
```

Replace `<REPOSITORY_URL>` with the real repository URL.

If you already have the project, enter the folder:

```powershell
cd C:\path\to\fire-control
```

Verify your location:

```powershell
Get-Location
```

Verify project files:

```powershell
Get-ChildItem -Force
```

You should see files like:

```text
app
requirements.txt
README.md
alembic.ini
```

---

# 10. Create the virtual environment

From the project root, run:

```powershell
python -m venv .venv
```

If `python` does not work, use:

```powershell
py -m venv .venv
```

This creates a local Python environment for the project.

---

# 11. Activate the virtual environment

Run:

```powershell
.venv\Scripts\Activate.ps1
```

Expected prompt example:

```text
(.venv) PS C:\path\to\fire-control>
```

The `(.venv)` part means the environment is active.

## If PowerShell blocks activation

Run:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Confirm the change.

Then activate again:

```powershell
.venv\Scripts\Activate.ps1
```

---

# 12. Install project dependencies

With `.venv` active, run:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

This installs project tools such as:

```text
FastAPI
SQLAlchemy
asyncpg
Alembic
Pydantic Settings
pytest
ruff
mypy
```

Verify key packages:

```powershell
python -c "import fastapi, sqlalchemy, asyncpg, alembic; print('Environment ready')"
```

Expected result:

```text
Environment ready
```

---

# 13. Configure `.env`

Create `.env` from `.env.example`:

```powershell
Copy-Item .env.example .env
```

Open `.env` and add or update:

```env
APP_NAME=FireOps Intelligence
ENVIRONMENT=development
DATABASE_URL=postgresql+asyncpg://postgres:TU_PASSWORD@localhost:5432/fireassets
SECRET_KEY=replace-this-value
```

Replace:

```text
TU_PASSWORD
```

with the real password you chose for the PostgreSQL `postgres` user.

> Important: do not use `postgresql+asyncpg://TU_PASSWORD@localhost:5432/fireassets`. That puts the password where the user should be. On Windows, use `postgres:TU_PASSWORD`.

Example:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres123@localhost:5432/fireassets
```

Important:

```text
Do not leave TU_PASSWORD literally in the file.
```

Also important:

```text
Never commit .env to Git.
```

---

# 14. About database migrations

The project uses Alembic for database migrations.

For now, do **not** run:

```powershell
alembic init
```

Why?

Because the project already contains Alembic files:

```text
alembic.ini
migrations/
```

Running `alembic init` again can overwrite or duplicate project configuration.

When the project has real SQLAlchemy models and migrations ready, the normal command will be:

```powershell
alembic upgrade head
```

If this fails right now, stop and ask for help. The database layer may still be under construction.

---

# 15. Start the API

With `.venv` active, run:

```powershell
python -m uvicorn app.main:app --reload
```

Expected output includes something like:

```text
Uvicorn running on http://127.0.0.1:8000
```

Open in the browser:

```text
http://127.0.0.1:8000/docs
```

Health check:

```text
http://127.0.0.1:8000/health
```

Expected response:

```json
{
  "status": "ok"
}
```

From another PowerShell window, you can test:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

---

# 16. Run tests

With `.venv` active, run:

```powershell
python -m pytest -v
```

If there are no tests yet, you may see:

```text
no tests ran
```

That means the test suite has not been created yet.

Once tests exist, the expected result should look like:

```text
1 passed
```

or more passed tests.

---

# 17. Run code checks

Format/lint check:

```powershell
python -m ruff check .
```

Type check:

```powershell
python -m mypy app
```

If these fail, copy the full output and ask for help.

---

# 18. Stop the server

If Uvicorn is running, stop it with:

```text
Ctrl + C
```

Deactivate the virtual environment:

```powershell
deactivate
```

---

# Daily development workflow

After the first setup, the normal workflow is shorter:

```powershell
cd C:\path\to\fire-control
.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload
```

To run tests:

```powershell
python -m pytest -v
```

To stop:

```powershell
Ctrl + C
deactivate
```

---

# How to report problems

If something fails, send this information:

```text
Step where it failed:
Command I ran:
What I expected:
Error message:
Screenshot or copied terminal output:
```

Example:

```text
Step where it failed: 7. Connect to PostgreSQL
Command I ran: psql -U postgres
What I expected: postgres=#
Error message: password authentication failed for user "postgres"
```

This helps the project lead debug quickly.

---

# Common problems

## `python` command not found

Try:

```powershell
py --version
```

If `py` works, use `py` instead of `python` for creating `.venv`.

If neither works, reinstall Python and enable:

```text
Add Python to PATH
```

---

## `psql` command not found

Check this path:

```text
C:\Program Files\PostgreSQL\18\bin
```

Try:

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" --version
```

If that works, PostgreSQL must be added to PATH.

---

## PostgreSQL service is stopped

Check:

```powershell
Get-Service *postgres*
```

Start it from PowerShell as Administrator:

```powershell
Start-Service postgresql-x64-18
```

Use the real service name shown on your machine.

---

## PostgreSQL password authentication failed

Check that your `.env` uses the same password you set during PostgreSQL installation:

```env
DATABASE_URL=postgresql+asyncpg://postgres:TU_PASSWORD@localhost:5432/fireassets
```

If your password contains symbols like `@`, `#`, `:`, `/`, or `%`, ask for help. Those characters may need URL encoding.

---

## PowerShell cannot activate `.venv`

Run:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Then:

```powershell
.venv\Scripts\Activate.ps1
```

---

## Port 8000 is already in use

Run the server on another port:

```powershell
python -m uvicorn app.main:app --reload --port 8001
```

Then open:

```text
http://127.0.0.1:8001/docs
```

---

# Final checklist

Before coding, confirm:

- [ ] `python --version` or `py --version` works.
- [ ] `git --version` works.
- [ ] `psql --version` works.
- [ ] `Get-Service *postgres*` shows PostgreSQL as `Running`.
- [ ] You can connect with `psql -U postgres`.
- [ ] The `fireassets` database exists.
- [ ] `.venv` exists and activates.
- [ ] `python -m pip install -r requirements.txt` completed.
- [ ] `.env` exists and has `DATABASE_URL`.
- [ ] `python -m uvicorn app.main:app --reload` starts the API.
- [ ] `http://127.0.0.1:8000/health` returns `{ "status": "ok" }`.


---

# 19. Using Codex during setup

Codex may be used to speed up setup and debugging. Use it for:

- explaining command errors;
- checking whether PostgreSQL, Git, or Python are installed;
- diagnosing `.env` mistakes;
- understanding why a command failed.

Do not use Codex to submit code you cannot explain.

Useful prompt:

```text
I am learning programming. Guide me step by step. Explain what each command does before I run it. If something fails, help me understand the cause instead of giving me a random list of commands.
```

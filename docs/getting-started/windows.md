
Running FireAssets on Windows

This guide explains how to install the required tools, configure PostgreSQL, create the project database, and run FireAssets on Windows from scratch.

Requirements

FireAssets requires:

Python 3.11 or later

PostgreSQL

Git

PowerShell

Check which tools are already installed:

python --version
git --version
psql --version

If python is not recognized, try:

py --version

If a command is not found, follow the corresponding installation section below.

1. Install Python

Download and install Python 3.11 or later from the official Python website.

During installation, enable:

Add Python to PATH

After installation, close and reopen PowerShell.

Verify:

python --version

If python is still unavailable, try:

py --version

2. Install Git

Download and install Git for Windows.

After installation, close and reopen PowerShell.

Verify:

git --version

3. Install PostgreSQL

Download the PostgreSQL installer for Windows.

During installation, keep these components selected:

PostgreSQL Server

pgAdmin 4

Command Line Tools

The installer will ask for:

installation directory;

PostgreSQL data directory;

password for the postgres user;

port;

locale.

Recommended values:

User: postgres
Port: 5432

Choose and remember a password for the postgres user.

After the installation finishes, close and reopen PowerShell.

Verify PostgreSQL:

psql --version

If psql is not recognized, continue with the section Add PostgreSQL to PATH below.

4. Add PostgreSQL to PATH

The PostgreSQL command-line tools are normally installed in a directory similar to:

C:\Program Files\PostgreSQL\18\bin

The version number may be different.

To add PostgreSQL to PATH:

Open the Windows Start menu.

Search for Environment Variables.

Open Edit the system environment variables.

Select Environment Variables.

Under User variables or System variables, select Path.

Select Edit.

Add the PostgreSQL bin directory.

Confirm all dialogs.

Close and reopen PowerShell.

Verify again:

psql --version

You can also execute PostgreSQL using the full path:

& "C:\Program Files\PostgreSQL\18\bin\psql.exe" --version

Adjust the version number if necessary.

5. Verify that PostgreSQL is running

PostgreSQL is usually installed as a Windows service.

Open the Services window:

Win + R
services.msc

Look for a service similar to:

postgresql-x64-18

Its status should be:

Running

You can also check it from PowerShell:

Get-Service *postgres*

To start it from an administrator PowerShell terminal:

Start-Service postgresql-x64-18

Adjust the service name if your version is different.

6. Connect to PostgreSQL

Open PowerShell and run:

psql -U postgres

PostgreSQL will ask for the password created during installation.

A successful connection shows:

postgres=#

If you need to specify the host and port:

psql -U postgres -h localhost -p 5432

7. Create the FireAssets database

Inside the PostgreSQL console, run:

CREATE DATABASE fireassets;

Expected result:

CREATE DATABASE

To list all databases, use:

\l

The backslash is required.

You should see a row similar to:

fireassets | postgres | UTF8

To connect to the new database from the PostgreSQL console:

\c fireassets

The prompt should change to:

fireassets=#

To exit PostgreSQL:

\q

You can also create the database directly from PowerShell:

createdb -U postgres fireassets

List databases from PowerShell:

psql -U postgres -l

Connect directly to the database:

psql -U postgres -d fireassets

8. Clone or open the project

Clone the repository:

git clone <REPOSITORY_URL>
cd fire-control

If the project already exists locally:

cd C:\path\to\fire-control

Verify the current directory:

Get-Location

List the project files:

Get-ChildItem -Force

9. Create the virtual environment

From the project root:

python -m venv .venv

If your installation uses the Python launcher:

py -m venv .venv

Activate it in PowerShell:

.venv\Scripts\Activate.ps1

When the environment is active, the prompt should look similar to:

(.venv) PS C:\Users\YourName\fire-control>

Verify the Python version:

python --version

10. Fix PowerShell activation errors

If PowerShell blocks the activation script, run:

Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

Confirm the change and activate again:

.venv\Scripts\Activate.ps1

You can also activate the environment from Command Prompt:

.venv\Scripts\activate.bat

11. Upgrade pip

python -m pip install --upgrade pip

12. Install project dependencies

Confirm that the dependency file exists:

Get-Item requirements.txt

Install the dependencies:

pip install -r requirements.txt

If you see:

Could not open requirements file

check the filename.

The correct spelling is:

requirements.txt

Rename an incorrectly named file:

Rename-Item requeriments.txt requirements.txt

Verify the main packages:

python -c "import fastapi, sqlalchemy, asyncpg, alembic; print('Environment ready')"

13. Configure environment variables

Copy the example file:

Copy-Item .env.example .env

Open .env and add:

APP_NAME=FireAssets
ENVIRONMENT=development
DATABASE_URL=postgresql+asyncpg://postgres:your_password@localhost:5432/fireassets
SECRET_KEY=replace-this-value

Replace your_password with the password selected during PostgreSQL installation.

Example:

DATABASE_URL=postgresql+asyncpg://postgres:MySecurePassword@localhost:5432/fireassets

If the password contains characters such as @, :, /, #, or %, URL-encode them before using them in DATABASE_URL.

Do not commit .env to Git.

The .gitignore file should include:

.env
.venv/
__pycache__/
*.pyc
.DS_Store
Thumbs.db

14. Initialize Alembic

Only run this step if Alembic has not already been configured.

If migrations\ and alembic.ini exist only as empty placeholders, remove them first:

Remove-Item alembic.ini
Remove-Item migrations -Recurse -Force

Initialize Alembic using the asynchronous template:

alembic init -t async migrations

This creates:

migrations\
├── versions\
├── env.py
├── README
└── script.py.mako

alembic.ini

Do not run this command again after real migration files or custom configuration have been added.

15. Run database migrations

After Alembic and the SQLAlchemy metadata are configured:

alembic upgrade head

This applies all pending database schema changes.

Check the current migration:

alembic current

View the migration history:

alembic history

16. Start the API

Run the application from the project root:

uvicorn app.main:app --reload

The API should be available at:

http://127.0.0.1:8000

Interactive API documentation:

http://127.0.0.1:8000/docs

Alternative documentation:

http://127.0.0.1:8000/redoc

17. Check the health endpoint

Open:

http://127.0.0.1:8000/health

Expected response:

{
  "status": "ok"
}

From PowerShell:

Invoke-RestMethod http://127.0.0.1:8000/health

You can also use:

curl http://127.0.0.1:8000/health

18. Run tests

pytest

For detailed output:

pytest -v

19. Run code checks

Check code quality:

ruff check .

Check Python types:

mypy app

20. Stop the application

Press:

Control + C

21. Deactivate the virtual environment

deactivate

Common problems

python command not found

Try:

py --version

Create the virtual environment with:

py -m venv .venv

Reinstall Python and enable:

Add Python to PATH

psql command not found

Add the PostgreSQL bin directory to PATH.

Typical path:

C:\Program Files\PostgreSQL\18\bin

Or run:

& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres

PostgreSQL connection refused

Check the Windows service:

Get-Service *postgres*

Start it from an administrator PowerShell terminal:

Start-Service postgresql-x64-18

Adjust the service name if necessary.

PostgreSQL password authentication failed

Verify the username and password:

psql -U postgres -h localhost -p 5432

Check .env:

DATABASE_URL=postgresql+asyncpg://postgres:your_password@localhost:5432/fireassets

If the password contains special characters, URL-encode them.

PostgreSQL shows postgres-#

The prompt:

postgres-#

means PostgreSQL is waiting for the rest of an unfinished SQL statement.

Cancel it with:

Control + C

The normal prompt should return:

postgres=#

Meta-commands require a backslash.

Correct:

\l

Incorrect:

l

The database already exists

If this command:

CREATE DATABASE fireassets;

reports that the database already exists, list all databases:

\l

Then connect:

psql -U postgres -d fireassets

requirements.txt is not found

Check the current directory:

Get-Location
Get-ChildItem -Force

Check the filename:

Get-Item requirements.txt

Rename it if necessary:

Rename-Item requeriments.txt requirements.txt

PowerShell cannot activate .venv

Run:

Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

Then:

.venv\Scripts\Activate.ps1

Alembic configuration is empty

If alembic.ini is empty and migrations\ contains only placeholders:

Remove-Item alembic.ini
Remove-Item migrations -Recurse -Force
alembic init -t async migrations

Only do this before creating real migration files.

Port 8000 is already in use

Use another port:

uvicorn app.main:app --reload --port 8001

uvicorn command not found

Confirm that .venv is active:

.venv\Scripts\Activate.ps1

Reinstall dependencies:

pip install -r requirements.txt

You can also run Uvicorn through Python:

python -m uvicorn app.main:app --reload

Daily development workflow

From the project root:

.venv\Scripts\Activate.ps1
alembic upgrade head
uvicorn app.main:app --reload

At the end:

deactivate

PostgreSQL can remain running as a Windows background service.
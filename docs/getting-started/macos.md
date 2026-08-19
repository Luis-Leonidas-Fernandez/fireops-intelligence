
Running FireAssets on macOS

This guide explains how to install the required tools, configure PostgreSQL, create the project database, and run FireAssets on macOS.

Requirements

FireAssets requires:

Python 3.11 or later

PostgreSQL

Git

Homebrew

Check which tools are already installed:

python3 --version
git --version
brew --version
psql --version

If a command is not found, follow the corresponding installation section below.

1. Install Homebrew

Check whether Homebrew is installed:

brew --version

If the command is not found, install Homebrew:

/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

On Apple Silicon Macs, Homebrew is normally installed in:

/opt/homebrew

At the end of the installation, Homebrew may display commands that must be added to the shell configuration. Run the commands shown by the installer.

Then verify:

brew --version

2. Install Python

Check the installed version:

python3 --version

FireAssets can run with Python 3.11 or later.

If Python is not installed, install it with Homebrew:

brew install python

Verify again:

python3 --version

3. Install Git

Check whether Git is installed:

git --version

If it is not installed:

brew install git

4. Install PostgreSQL

Check whether PostgreSQL is installed:

psql --version

If the command is not found, install PostgreSQL with Homebrew:

brew install postgresql

Start PostgreSQL as a background service:

brew services start postgresql

Depending on the installed formula, the service name may include a version:

brew services start postgresql@18

Check the installed services:

brew services list

Verify PostgreSQL:

psql --version

A successful result should look similar to:

psql (PostgreSQL) 18.x

5. Verify the local PostgreSQL user

Homebrew commonly configures PostgreSQL so the current macOS user can connect without a password.

Check the current macOS username:

whoami

Example:

luis

Test the PostgreSQL connection:

psql postgres

A successful connection shows a prompt similar to:

postgres=#

If PostgreSQL asks for a password or rejects the connection, review the troubleshooting section.

6. Create the FireAssets database

Inside the PostgreSQL console, run:

CREATE DATABASE fireassets;

Expected result:

CREATE DATABASE

To list all databases, use the PostgreSQL meta-command:

\l

The backslash is required.

You should see a row similar to:

fireassets | luis | UTF8

To exit PostgreSQL:

\q

You can also create the database directly from the macOS terminal:

createdb fireassets

To list databases from the terminal:

psql -l

To connect directly to the new database:

psql fireassets

A successful connection shows:

fireassets=#

Exit with:

\q

7. Clone or open the project

Clone the repository:

git clone <REPOSITORY_URL>
cd fire-control

If the project already exists locally:

cd /path/to/fire-control

Verify the current directory:

pwd

List the project files:

ls -la

8. Create the virtual environment

From the project root:

python3 -m venv .venv

Activate it:

source .venv/bin/activate

When the environment is active, the terminal should look similar to:

(.venv) user@MacBook fire-control %

Verify the Python version used by the environment:

python --version

9. Upgrade pip

python -m pip install --upgrade pip

Warnings related to pip cache deserialization can normally be ignored if the installation finishes successfully.

10. Install project dependencies

Confirm that the dependency file exists:

ls -la requirements.txt

Install the dependencies:

pip install -r requirements.txt

If you see this error:

Could not open requirements file

check the filename. The correct spelling is:

requirements.txt

For example, rename an incorrectly named file:

mv requeriments.txt requirements.txt

Verify the main packages:

python -c "import fastapi, sqlalchemy, asyncpg, alembic; print('Environment ready')"

11. Configure environment variables

Copy the example environment file:

cp .env.example .env

For a typical Homebrew PostgreSQL installation using the current macOS user without a password:

APP_NAME=FireAssets
ENVIRONMENT=development
DATABASE_URL=postgresql+asyncpg://luis@localhost:5432/fireassets
SECRET_KEY=replace-this-value

Replace luis with the result of:

whoami

If PostgreSQL was configured with a dedicated user and password, use:

DATABASE_URL=postgresql+asyncpg://postgres:TU_PASSWORD@localhost:5432/fireassets

Do not commit .env to Git.

The .gitignore file should include:

.env
.venv/
__pycache__/
*.pyc
.DS_Store

12. Initialize Alembic

Only run this command if Alembic has not been initialized yet:

alembic init migrations

This creates:

migrations/
├── versions/
├── env.py
├── README
└── script.py.mako

It also creates or updates:

alembic.ini

Do not run alembic init migrations if the folder already contains a configured Alembic project.

13. Run database migrations

After Alembic and the SQLAlchemy metadata are configured:

alembic upgrade head

This applies all pending database schema changes.

Check the current migration:

alembic current

View the migration history:

alembic history



14. Start the API

Run the FastAPI application from the project root:

uvicorn app.main:app --reload

The API should be available at:

http://127.0.0.1:8000

Interactive API documentation:

http://127.0.0.1:8000/docs

Alternative documentation:

http://127.0.0.1:8000/redoc

15. Check the health endpoint

Open:

http://127.0.0.1:8000/health

Expected response:

{
  "status": "ok"
}

From the terminal:

curl http://127.0.0.1:8000/health

16. Run tests

pytest

For detailed output:

pytest -v

17. Run code checks

Check code quality:

ruff check .

Check Python types:

mypy app

18. Stop the application

Press:

Control + C

19. Deactivate the virtual environment

deactivate

Common problems

PostgreSQL is not installed

Install it with Homebrew:

brew install postgresql
brew services start postgresql

Verify:

psql --version

PostgreSQL connection refused

Check whether PostgreSQL is running:

brew services list

Start it:

brew services start postgresql

Or use the versioned service name:

brew services start postgresql@18

psql or createdb command not found

Find the installed PostgreSQL formula:

brew list | grep postgresql

Check Homebrew information:

brew info postgresql

If a versioned formula was installed, link it:

brew link postgresql@18 --force

Then restart the terminal.

PostgreSQL shows postgres-#

The prompt:

postgres-#

means PostgreSQL is waiting for the rest of an unfinished SQL statement.

Cancel it with:

Control + C

The normal prompt should return:

postgres=#

PostgreSQL meta-commands require a backslash.

Correct:

\l

Incorrect:

l

The database already exists

If this command:

CREATE DATABASE fireassets;

returns an error saying the database already exists, list the databases:

\l

Then connect to it:

psql fireassets

requirements.txt is not found

Check the current directory:

pwd
ls -la

Confirm the filename:

ls -la requirements.txt

The correct spelling is requirements, not requeriments.

Rename it if necessary:

mv requeriments.txt requirements.txt

python command not found

Outside the virtual environment, use:

python3

Create the environment:

python3 -m venv .venv

After activation, this should work:

python --version

Alembic configuration is empty

If alembic.ini is an empty file and Alembic has not been initialized, remove the empty placeholders and initialize it:

rm alembic.ini
rm -rf migrations
alembic init migrations

Only do this before creating real migration files.

Port 8000 is already in use

Use another port:

uvicorn app.main:app --reload --port 8001

Daily development workflow

From the project root:

source .venv/bin/activate
brew services start postgresql
alembic upgrade head
uvicorn app.main:app --reload

At the end:

deactivate

PostgreSQL can remain running as a Homebrew background service.
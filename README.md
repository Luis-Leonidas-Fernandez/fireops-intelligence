<p align="center">
  <img src="asset/profile.png" alt="FireOps Intelligence banner" width="100%">
</p>

# FireOps Intelligence

**FireOps Intelligence** is a modular platform for fire departments, designed to manage assets, improve operational traceability, and support future data science and artificial intelligence capabilities.

The project starts with a solid inventory-management foundation and is designed to evolve toward operational analytics, predictive insights, intelligent reporting, and decision-support tools.

---

## Project goals

FireOps Intelligence aims to help fire departments:

- centralize equipment and asset records;
- track asset status, location, responsibility, and lifecycle;
- preserve an auditable history of changes;
- reduce duplicated, incomplete, or outdated information;
- prepare clean operational data for future analytics and AI models;
- support safer and more informed operational decisions.

---

## Current scope

The current phase focuses on **asset and inventory management**.

Planned capabilities include:

- asset registration;
- asset search and retrieval;
- inventory listing and filtering;
- asset updates;
- assignment to responsible personnel or departments;
- asset transfers;
- deactivation and lifecycle tracking;
- file attachment support;
- audit history;
- identity and access management.

---

## Future data science and AI roadmap

As the project collects reliable operational data, future phases may include:

- inventory dashboards and descriptive analytics;
- equipment availability and readiness indicators;
- maintenance and replacement forecasting;
- anomaly detection in inventory movements;
- asset failure-risk estimation;
- demand forecasting for critical supplies;
- document classification and information extraction;
- intelligent search and natural-language reporting;
- predictive decision-support tools for fire departments.

> The AI layer will be introduced only after the operational data model, traceability, and data quality are stable.

---

## Architecture

The project follows a combination of:

- **Modular Monolith**
- **Vertical Slice Architecture**
- **Centralized Exception Handling**
- **Custom Exception Hierarchy**
- **Single Responsibility Principle**
- **Explicit separation between business rules and infrastructure**

High-level structure:

```text
fire-control/
├── app/
│   ├── config/
│   ├── infrastructure/
│   ├── modules/
│   │   ├── audit/
│   │   ├── files/
│   │   ├── identity/
│   │   └── inventory/
│   ├── shared/
│   │   └── errors/
│   └── main.py
├── asset/
│   └── profile.png
├── docs/
├── migrations/
├── scripts/
├── tests/
├── .env.example
├── .gitignore
├── alembic.ini
├── Makefile
├── pyproject.toml
├── README.md
└── requirements.txt
```

### Main architectural responsibilities

| Area | Responsibility |
|---|---|
| `app/config/` | Environment and application settings |
| `app/infrastructure/` | Database, persistence, storage, and external integrations |
| `app/modules/` | Business modules and vertical slices |
| `app/shared/` | Cross-cutting reusable application components |
| `docs/` | Requirements, architecture, and technical decisions |
| `migrations/` | Versioned PostgreSQL schema changes |
| `tests/` | Unit, integration, API, and architecture tests |

---

## Technology stack

| Category | Technology |
|---|---|
| Language | Python 3.14 |
| API framework | FastAPI |
| ASGI server | Uvicorn |
| Validation | Pydantic |
| Configuration | Pydantic Settings |
| Database | PostgreSQL |
| ORM | SQLAlchemy 2 |
| Migrations | Alembic |
| PostgreSQL driver | asyncpg |
| Authentication | PyJWT |
| Password hashing | pwdlib with Argon2 |
| Testing | pytest, pytest-asyncio, HTTPX |
| Linting and formatting | Ruff |
| Static typing | mypy |

---

## Requirements

Before running the project, install:

- Python 3.14
- PostgreSQL
- Git
- Make

Check the installed versions:

```bash
python --version
psql --version
git --version
make --version
```

---

## Local setup

### 1. Clone the repository

```bash
git clone <REPOSITORY_URL>
cd fire-control
```

### 2. Select Python 3.14 with pyenv

```bash
pyenv local 3.14.4
python --version
```

Expected output:

```text
Python 3.14.4
```

### 3. Create the virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

Verify the interpreter:

```bash
python -c "import sys; print(sys.executable)"
```

### 4. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 5. Create the PostgreSQL database

Open PostgreSQL:

```bash
psql postgres
```

Create the database:

```sql
CREATE DATABASE fireassets;
```

List databases:

```text
\l
```

Exit:

```text
\q
```

### 6. Configure environment variables

Copy the example file:

```bash
cp .env.example .env
```

Example local configuration:

```env
APP_NAME=FireOps Intelligence
ENVIRONMENT=development
DATABASE_URL=postgresql+asyncpg://postgres:TU_PASSWORD@localhost:5432/fireassets
SECRET_KEY=replace-this-value
```

On macOS with a local PostgreSQL user matching your system user, the URL may look like:

```env
DATABASE_URL=postgresql+asyncpg://luis@localhost:5432/fireassets
```

Never commit `.env`.

### 7. Run database migrations

After Alembic and the SQLAlchemy metadata are configured:

```bash
alembic upgrade head
```

### 8. Start the application

```bash
make run
```

The API will be available at:

```text
http://127.0.0.1:8000
```

---

## API documentation

FastAPI automatically provides interactive documentation.

Swagger UI:

```text
http://127.0.0.1:8000/docs
```

ReDoc:

```text
http://127.0.0.1:8000/redoc
```

Health endpoint:

```text
http://127.0.0.1:8000/health
```

Expected response:

```json
{
  "status": "ok"
}
```

---

## Development commands

The project includes a `Makefile` to simplify common tasks.

### Start the API

```bash
make run
```

### Run tests

```bash
make test
```

### Check code quality

```bash
make lint
```

### Format the codebase

```bash
make format
```

### Apply automatic fixes

```bash
make fix
```

---

## Error handling

The project uses centralized exception handling with a custom exception hierarchy.

```text
Exception
└── ApplicationError
    ├── BusinessRuleError
    ├── ConflictError
    └── NotFoundError
```

This allows the business logic to raise application-specific errors without depending directly on FastAPI response classes.

Example response:

```json
{
  "error": {
    "code": "ASSET_NOT_FOUND",
    "message": "The requested asset was not found.",
    "details": {
      "asset_id": "asset-001"
    }
  }
}
```

---

## Business domain

The main domain concepts include:

- assets;
- equipment;
- vehicles;
- responsible personnel;
- departments;
- inventory status;
- transfers;
- deactivation;
- audit records;
- attached files.

Examples of business rules:

- an asset code must be unique;
- a deactivated asset cannot be transferred;
- every transfer must identify the previous and new responsible party;
- critical changes must create an audit record;
- only authorized users may perform restricted operations.

---

## Testing

Run the complete test suite:

```bash
pytest -v
```

Suggested testing levels:

- unit tests for business rules;
- slice-level tests for use cases;
- repository integration tests;
- FastAPI endpoint tests;
- migration tests;
- architecture-boundary tests.

---

## Documentation

Project documentation is stored under:

```text
docs/
```

Recommended sections:

```text
docs/
├── architecture/
├── architecture-history/
├── getting-started/
├── phase_01/
└── technical-decisions/
```

Technical documents should preferably be stored in Markdown for GitHub readability. Formal `.docx` documents may also be included when necessary.

---

## Project status

**Current stage:** foundation and architecture setup.

Completed:

- Python 3.14 environment;
- FastAPI application bootstrap;
- PostgreSQL local database;
- Alembic initialization;
- project structure;
- centralized error handling;
- development commands with Make;
- automatic API documentation;
- Ruff formatting and linting setup.

Next milestone:

- implement the first real inventory vertical slice;
- define the initial asset data model;
- create the first SQLAlchemy models and Alembic migration;
- add integration tests;
- expose the first production-ready inventory endpoint.

---

## Vision

FireOps Intelligence is intended to become more than an inventory application.

The long-term goal is to build a reliable operational data foundation that can later support analytics, machine learning, predictive maintenance, resource planning, and AI-assisted decision making for fire departments.

The priority is to create trustworthy software, preserve data quality, and solve real operational problems before introducing advanced AI features.

---

## Author

Developed as an early data science and artificial intelligence portfolio project focused on public-service impact, operational traceability, and responsible AI adoption.

---


## License

A license has not yet been selected.

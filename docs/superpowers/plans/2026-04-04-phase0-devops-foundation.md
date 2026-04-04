# Phase 0: DevOps Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the complete project structure, Docker environment, CI pipeline, pre-commit hooks, and Makefile so all future phases have a solid foundation to build on.

**Architecture:** A Python package (`trace`) managed by uv with pyproject.toml. Local dev runs in Docker Compose (Postgres 17 + pgvector, app container). GitHub Actions CI runs linting (ruff, mypy) and pytest with coverage gating at 60%. Pre-commit hooks enforce formatting and type checking locally.

**Tech Stack:** Python 3.12, uv, Docker + Docker Compose, PostgreSQL 17 + pgvector, Alembic, SQLAlchemy, sentence-transformers, ruff, mypy, pytest, GitHub Actions

---

## File Structure

```
trace/
├── src/
│   └── trace/
│       ├── __init__.py              # package init, version
│       ├── config.py                # Pydantic settings from env vars
│       ├── connectors/
│       │   └── __init__.py
│       ├── processing/
│       │   └── __init__.py
│       ├── storage/
│       │   ├── __init__.py
│       │   ├── database.py          # SQLAlchemy engine/session factory
│       │   └── models.py            # SQLAlchemy ORM models (rules, edges, dead_letters)
│       ├── graph/
│       │   └── __init__.py
│       ├── agent/
│       │   └── __init__.py
│       └── frontend/
│           └── __init__.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py                  # shared fixtures
│   ├── unit/
│   │   ├── __init__.py
│   │   └── test_config.py
│   └── integration/
│       ├── __init__.py
│       └── test_database.py
├── migrations/
│   ├── env.py                       # Alembic environment
│   ├── script.py.mako               # migration template
│   └── versions/                    # auto-generated migrations
├── docs/
│   └── adr/
│       └── 001-postgres-over-graph-db.md
├── .github/
│   └── workflows/
│       └── ci.yml
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── .pre-commit-config.yaml
├── .env.example
├── Makefile
├── alembic.ini
└── README.md
```

---

### Task 1: Initialize Python Package with uv

**Files:**
- Create: `pyproject.toml`
- Create: `src/trace/__init__.py`
- Create: `src/trace/connectors/__init__.py`
- Create: `src/trace/processing/__init__.py`
- Create: `src/trace/storage/__init__.py`
- Create: `src/trace/graph/__init__.py`
- Create: `src/trace/agent/__init__.py`
- Create: `src/trace/frontend/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/integration/__init__.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "trace"
version = "0.1.0"
description = "Tracking Regulatory Actors, Capture, and Erasure"
readme = "README.md"
license = "MPL-2.0"
requires-python = ">=3.12,<3.14"

dependencies = [
    "sqlalchemy>=2.0,<3.0",
    "alembic>=1.13,<2.0",
    "psycopg[binary]>=3.1,<4.0",
    "pgvector>=0.3,<1.0",
    "pydantic>=2.0,<3.0",
    "pydantic-settings>=2.0,<3.0",
    "structlog>=24.0",
    "sentence-transformers>=3.0,<4.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0,<9.0",
    "pytest-cov>=5.0,<6.0",
    "ruff>=0.4,<1.0",
    "mypy>=1.10,<2.0",
    "pre-commit>=3.7,<4.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/trace"]

[tool.ruff]
target-version = "py312"
src = ["src"]
line-length = 99

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "SIM", "TCH"]

[tool.mypy]
python_version = "3.12"
strict = true
plugins = ["pydantic.mypy"]

[[tool.mypy.overrides]]
module = ["pgvector.*", "sentence_transformers.*"]
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--strict-markers -v"
markers = [
    "integration: marks tests requiring database (deselect with '-m \"not integration\"')",
]
```

- [ ] **Step 2: Create package init files**

`src/trace/__init__.py`:
```python
"""TRACE: Tracking Regulatory Actors, Capture, and Erasure."""

__version__ = "0.1.0"
```

All other `__init__.py` files (connectors, processing, storage, graph, agent, frontend, tests, tests/unit, tests/integration) should be empty files.

- [ ] **Step 3: Pin Python 3.12 and sync dependencies**

Run:
```bash
cd /c/Projects/trace
uv python pin 3.12
uv sync --all-extras
```

Expected: `.python-version` file created, `uv.lock` generated, virtual environment created at `.venv/`.

- [ ] **Step 4: Verify the package imports**

Run:
```bash
cd /c/Projects/trace
uv run python -c "import trace; print(trace.__version__)"
```

Expected: `0.1.0`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock .python-version src/ tests/__init__.py tests/unit/__init__.py tests/integration/__init__.py
git commit -m "$(cat <<'EOF'
chore: initialize Python package with uv

Set up src/trace package layout with pyproject.toml, pinned to
Python 3.12. Includes SQLAlchemy, Alembic, Pydantic, structlog
as core deps and ruff/mypy/pytest as dev deps.
EOF
)"
```

---

### Task 2: Configuration Module with Pydantic Settings

**Files:**
- Create: `src/trace/config.py`
- Create: `tests/unit/test_config.py`
- Create: `.env.example`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_config.py`:
```python
import os

from trace.config import Settings


def test_settings_loads_from_env(monkeypatch: object) -> None:
    """Settings should load DATABASE_URL from environment."""
    import pytest

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/trace")  # type: ignore[attr-defined]
    settings = Settings()  # type: ignore[call-arg]
    assert str(settings.database_url) == "postgresql+psycopg://user:pass@localhost:5432/trace"


def test_settings_default_values(monkeypatch: object) -> None:
    """Settings should have sensible defaults for optional fields."""
    import pytest

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/trace")  # type: ignore[attr-defined]
    settings = Settings()  # type: ignore[call-arg]
    assert settings.log_level == "INFO"
    assert settings.embedding_model == "all-MiniLM-L6-v2"
    assert settings.embedding_dimension == 384
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/Projects/trace && uv run pytest tests/unit/test_config.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'trace.config'`

- [ ] **Step 3: Write minimal implementation**

`src/trace/config.py`:
```python
"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings, loaded from environment variables."""

    database_url: str
    log_level: str = "INFO"
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dimension: int = 384

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /c/Projects/trace && uv run pytest tests/unit/test_config.py -v`

Expected: 2 passed

- [ ] **Step 5: Create .env.example**

`.env.example`:
```bash
# Database connection string (required)
DATABASE_URL=postgresql+psycopg://trace:trace@localhost:5432/trace

# Logging level (default: INFO)
LOG_LEVEL=INFO

# Sentence-transformers embedding model (default: all-MiniLM-L6-v2)
EMBEDDING_MODEL=all-MiniLM-L6-v2

# Embedding vector dimension — must match model output (default: 384)
EMBEDDING_DIMENSION=384
```

- [ ] **Step 6: Commit**

```bash
git add src/trace/config.py tests/unit/test_config.py .env.example
git commit -m "$(cat <<'EOF'
feat: add Pydantic settings configuration module

Loads DATABASE_URL and optional settings from environment/.env.
Includes .env.example documenting all variables.
EOF
)"
```

---

### Task 3: Database Engine and Session Factory

**Files:**
- Create: `src/trace/storage/database.py`
- Create: `tests/unit/test_database.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_database.py`:
```python
from unittest.mock import patch

from trace.storage.database import build_engine, build_session_factory


def test_build_engine_returns_engine() -> None:
    """build_engine should return a SQLAlchemy Engine."""
    from sqlalchemy import Engine

    engine = build_engine("sqlite:///")
    assert isinstance(engine, Engine)


def test_build_session_factory_returns_callable() -> None:
    """build_session_factory should return a sessionmaker."""
    engine = build_engine("sqlite:///")
    session_factory = build_session_factory(engine)
    session = session_factory()
    assert session is not None
    session.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/Projects/trace && uv run pytest tests/unit/test_database.py -v`

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

`src/trace/storage/database.py`:
```python
"""Database engine and session factory."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def build_engine(database_url: str) -> Engine:
    """Create a SQLAlchemy engine from a database URL."""
    return create_engine(database_url, echo=False)


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory bound to the given engine."""
    return sessionmaker(bind=engine, expire_on_commit=False)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /c/Projects/trace && uv run pytest tests/unit/test_database.py -v`

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/trace/storage/database.py tests/unit/test_database.py
git commit -m "$(cat <<'EOF'
feat: add database engine and session factory

Provides build_engine() and build_session_factory() for
SQLAlchemy database connections.
EOF
)"
```

---

### Task 4: SQLAlchemy ORM Models

**Files:**
- Create: `src/trace/storage/models.py`
- Create: `tests/unit/test_models.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_models.py`:
```python
import uuid
from datetime import date, datetime

from trace.storage.models import Base, DeadLetter, Edge, Rule


def test_rule_model_has_expected_columns() -> None:
    """Rule model should define all columns from the schema."""
    columns = {c.name for c in Rule.__table__.columns}
    expected = {
        "rule_id",
        "title",
        "abstract",
        "full_text",
        "publication_date",
        "effective_date",
        "agency",
        "document_type",
        "cfr_sections",
        "administration",
        "fr_url",
        "embedding",
        "ingested_at",
        "content_hash",
    }
    assert expected == columns


def test_edge_model_has_expected_columns() -> None:
    """Edge model should define all columns from the schema."""
    columns = {c.name for c in Edge.__table__.columns}
    expected = {
        "edge_id",
        "rule_id_source",
        "rule_id_target",
        "relationship_type",
        "confidence_score",
        "extraction_method",
        "created_at",
    }
    assert expected == columns


def test_dead_letter_model_has_expected_columns() -> None:
    """DeadLetter model should capture failed documents."""
    columns = {c.name for c in DeadLetter.__table__.columns}
    expected = {
        "dead_letter_id",
        "source_url",
        "raw_payload",
        "error_message",
        "failed_at",
    }
    assert expected == columns


def test_rule_table_name() -> None:
    assert Rule.__tablename__ == "rules"


def test_edge_table_name() -> None:
    assert Edge.__tablename__ == "edges"


def test_base_is_declarative_base() -> None:
    from sqlalchemy.orm import DeclarativeBase

    assert issubclass(Base, DeclarativeBase)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/Projects/trace && uv run pytest tests/unit/test_models.py -v`

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

`src/trace/storage/models.py`:
```python
"""SQLAlchemy ORM models for TRACE."""

import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Date, DateTime, Float, String, Text, Uuid
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all ORM models."""


class Rule(Base):
    __tablename__ = "rules"

    rule_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_text: Mapped[str] = mapped_column(Text, nullable=False)
    publication_date: Mapped[date] = mapped_column(Date, nullable=False)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    agency: Mapped[str] = mapped_column(Text, nullable=False)
    document_type: Mapped[str] = mapped_column(Text, nullable=False)
    cfr_sections: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True
    )
    administration: Mapped[str] = mapped_column(Text, nullable=False)
    fr_url: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(384), nullable=True
    )
    ingested_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    content_hash: Mapped[str | None] = mapped_column(
        Text, unique=True, nullable=True
    )


class Edge(Base):
    __tablename__ = "edges"

    edge_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    rule_id_source: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True
    )
    rule_id_target: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True
    )
    relationship_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    extraction_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )


class DeadLetter(Base):
    __tablename__ = "dead_letters"

    dead_letter_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /c/Projects/trace && uv run pytest tests/unit/test_models.py -v`

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/trace/storage/models.py tests/unit/test_models.py
git commit -m "$(cat <<'EOF'
feat: add SQLAlchemy ORM models for rules, edges, dead_letters

Defines Rule, Edge, and DeadLetter tables matching the TRACE schema.
Uses pgvector for embedding column, ARRAY(String) for cfr_sections.
EOF
)"
```

---

### Task 5: Alembic Migration Setup

**Files:**
- Create: `alembic.ini`
- Create: `migrations/env.py`
- Create: `migrations/script.py.mako`
- Create: `migrations/versions/` (directory)

- [ ] **Step 1: Create alembic.ini**

`alembic.ini`:
```ini
[alembic]
script_location = migrations
prepend_sys_path = src

sqlalchemy.url = postgresql+psycopg://trace:trace@localhost:5432/trace

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 2: Create migrations/env.py**

`migrations/env.py`:
```python
"""Alembic environment configuration."""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from trace.storage.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    """Get database URL from environment or alembic.ini."""
    return os.environ.get("DATABASE_URL", config.get_main_option("sqlalchemy.url", ""))


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = create_engine(get_url())
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 3: Create migrations/script.py.mako**

`migrations/script.py.mako`:
```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 4: Create empty versions directory**

Run:
```bash
mkdir -p /c/Projects/trace/migrations/versions
touch /c/Projects/trace/migrations/versions/.gitkeep
```

- [ ] **Step 5: Verify alembic loads correctly**

Run:
```bash
cd /c/Projects/trace
uv run alembic --help | head -5
```

Expected: Alembic usage text (confirms the module is importable and config is parseable).

- [ ] **Step 6: Commit**

```bash
git add alembic.ini migrations/
git commit -m "$(cat <<'EOF'
chore: set up Alembic migration scaffolding

Configures Alembic to use trace.storage.models.Base metadata.
Reads DATABASE_URL from env with fallback to alembic.ini.
EOF
)"
```

---

### Task 6: Dockerfile

**Files:**
- Create: `Dockerfile`

- [ ] **Step 1: Create Dockerfile**

`Dockerfile`:
```dockerfile
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ src/
COPY migrations/ migrations/
COPY alembic.ini .

RUN uv sync --frozen --no-dev

CMD ["uv", "run", "python", "-m", "trace"]
```

- [ ] **Step 2: Verify Dockerfile syntax**

Run:
```bash
cd /c/Projects/trace
# Just check the file exists and has the expected FROM line
head -1 Dockerfile
```

Expected: `FROM python:3.12-slim AS base`

- [ ] **Step 3: Commit**

```bash
git add Dockerfile
git commit -m "$(cat <<'EOF'
chore: add Dockerfile with uv-based build

Multi-stage friendly Python 3.12-slim image. Installs deps via
uv sync from locked requirements before copying source.
EOF
)"
```

---

### Task 7: Docker Compose

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Create docker-compose.yml**

`docker-compose.yml`:
```yaml
services:
  postgres:
    image: pgvector/pgvector:pg17
    environment:
      POSTGRES_USER: trace
      POSTGRES_PASSWORD: trace
      POSTGRES_DB: trace
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U trace"]
      interval: 5s
      timeout: 5s
      retries: 5

  app:
    build: .
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql+psycopg://trace:trace@postgres:5432/trace
    env_file:
      - .env
    ports:
      - "8501:8501"

volumes:
  pgdata:
```

- [ ] **Step 2: Commit**

```bash
git add docker-compose.yml
git commit -m "$(cat <<'EOF'
chore: add Docker Compose with Postgres 16 + pgvector

Postgres runs with healthcheck; app container depends on healthy
database. Volume persists data across restarts.
EOF
)"
```

---

### Task 8: Makefile

**Files:**
- Create: `Makefile`

- [ ] **Step 1: Create Makefile**

`Makefile`:
```makefile
.PHONY: up down test lint migrate ingest fmt check

up:
	docker compose up -d

down:
	docker compose down

test:
	uv run pytest --cov=trace --cov-report=term-missing

lint:
	uv run ruff check src/ tests/
	uv run ruff format --check src/ tests/
	uv run mypy src/

fmt:
	uv run ruff check --fix src/ tests/
	uv run ruff format src/ tests/

migrate:
	uv run alembic upgrade head

ingest:
	uv run python -m trace.connectors.ferc

check: lint test
```

**Note:** Makefile rules require actual tab characters for indentation, not spaces.

- [ ] **Step 2: Verify Makefile parses**

Run:
```bash
cd /c/Projects/trace
make --dry-run test
```

Expected: Shows the `uv run pytest ...` command it would execute (dry run, doesn't actually run).

- [ ] **Step 3: Commit**

```bash
git add Makefile
git commit -m "$(cat <<'EOF'
chore: add Makefile with dev workflow commands

Provides make up/down/test/lint/fmt/migrate/ingest/check targets
for common development tasks.
EOF
)"
```

---

### Task 9: Pre-commit Configuration

**Files:**
- Create: `.pre-commit-config.yaml`

- [ ] **Step 1: Create .pre-commit-config.yaml**

`.pre-commit-config.yaml`:
```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.8
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks:
      - id: mypy
        additional_dependencies:
          - pydantic>=2.0
          - pydantic-settings>=2.0
          - sqlalchemy>=2.0
          - types-psycopg2
        args: [--config-file=pyproject.toml]
        pass_filenames: false

  - repo: https://github.com/pycqa/isort
    rev: 5.13.2
    hooks:
      - id: isort
```

- [ ] **Step 2: Add isort config to pyproject.toml**

Append to `pyproject.toml`:
```toml
[tool.isort]
profile = "black"
src_paths = ["src", "tests"]
line_length = 99
```

- [ ] **Step 3: Install pre-commit hooks**

Run:
```bash
cd /c/Projects/trace
uv run pre-commit install
```

Expected: `pre-commit installed at .git/hooks/pre-commit`

- [ ] **Step 4: Verify hooks run**

Run:
```bash
cd /c/Projects/trace
uv run pre-commit run --all-files
```

Expected: All hooks pass (or show minor auto-fixes). Fix any issues before proceeding.

- [ ] **Step 5: Commit**

```bash
git add .pre-commit-config.yaml pyproject.toml
git commit -m "$(cat <<'EOF'
chore: add pre-commit hooks for ruff, mypy, isort

Enforces linting, formatting, type checking, and import ordering
on every commit via pre-commit framework.
EOF
)"
```

---

### Task 10: GitHub Actions CI

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create CI workflow**

`.github/workflows/ci.yml`:
```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          version: "latest"

      - name: Set up Python
        run: uv python install 3.12

      - name: Install dependencies
        run: uv sync --all-extras

      - name: Ruff check
        run: uv run ruff check src/ tests/

      - name: Ruff format check
        run: uv run ruff format --check src/ tests/

      - name: Mypy
        run: uv run mypy src/

  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg17
        env:
          POSTGRES_USER: trace
          POSTGRES_PASSWORD: trace
          POSTGRES_DB: trace
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U trace"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          version: "latest"

      - name: Set up Python
        run: uv python install 3.12

      - name: Install dependencies
        run: uv sync --all-extras

      - name: Run tests
        env:
          DATABASE_URL: postgresql+psycopg://trace:trace@localhost:5432/trace
        run: uv run pytest --cov=trace --cov-report=term-missing --cov-fail-under=60
```

- [ ] **Step 2: Commit**

```bash
mkdir -p /c/Projects/trace/.github/workflows
git add .github/workflows/ci.yml
git commit -m "$(cat <<'EOF'
ci: add GitHub Actions workflow for lint and test

Runs ruff, mypy on lint job. Runs pytest with pgvector postgres
service container and 80% coverage gate on test job.
EOF
)"
```

---

### Task 11: Shared Test Fixtures

**Files:**
- Create: `tests/conftest.py`

- [ ] **Step 1: Create conftest.py with database fixtures**

`tests/conftest.py`:
```python
"""Shared test fixtures."""

import os

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from trace.storage.models import Base


@pytest.fixture
def sqlite_engine() -> Engine:
    """In-memory SQLite engine for unit tests."""
    engine = create_engine("sqlite:///")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def sqlite_session(sqlite_engine: Engine) -> Session:
    """SQLite session for unit tests. Rolls back after each test."""
    session_factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
    session = session_factory()
    yield session  # type: ignore[misc]
    session.rollback()
    session.close()


@pytest.fixture
def pg_engine() -> Engine:
    """Postgres engine for integration tests. Requires running database."""
    url = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://trace:trace@localhost:5432/trace"
    )
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def pg_session(pg_engine: Engine) -> Session:
    """Postgres session for integration tests. Rolls back after each test."""
    session_factory = sessionmaker(bind=pg_engine, expire_on_commit=False)
    session = session_factory()
    yield session  # type: ignore[misc]
    session.rollback()
    session.close()
```

- [ ] **Step 2: Verify existing tests still pass**

Run:
```bash
cd /c/Projects/trace
uv run pytest tests/unit/ -v
```

Expected: All previously written unit tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "$(cat <<'EOF'
test: add shared conftest with SQLite and Postgres fixtures

SQLite fixtures for fast unit tests, Postgres fixtures for
integration tests. Both roll back after each test.
EOF
)"
```

---

### Task 12: Integration Test — Models Against Postgres

**Files:**
- Create: `tests/integration/__init__.py` (already exists from Task 1)
- Create: `tests/integration/test_database.py`

- [ ] **Step 1: Write the integration test**

`tests/integration/test_database.py`:
```python
"""Integration tests that require a running Postgres with pgvector."""

import uuid
from datetime import date, datetime

import pytest
from sqlalchemy.orm import Session

from trace.storage.models import DeadLetter, Edge, Rule

pytestmark = pytest.mark.integration


def test_insert_and_read_rule(pg_session: Session) -> None:
    """Should round-trip a Rule through Postgres."""
    rule = Rule(
        rule_id=uuid.uuid4(),
        title="Test Rule",
        full_text="Full text of the test rule.",
        publication_date=date(2024, 1, 15),
        agency="FERC",
        document_type="Rule",
        administration="Biden",
        fr_url="https://federalregister.gov/d/2024-00001",
        content_hash="abc123",
    )
    pg_session.add(rule)
    pg_session.flush()

    result = pg_session.get(Rule, rule.rule_id)
    assert result is not None
    assert result.title == "Test Rule"
    assert result.agency == "FERC"
    assert result.administration == "Biden"
    assert result.content_hash == "abc123"


def test_insert_and_read_edge(pg_session: Session) -> None:
    """Should round-trip an Edge through Postgres."""
    source_id = uuid.uuid4()
    target_id = uuid.uuid4()

    edge = Edge(
        edge_id=uuid.uuid4(),
        rule_id_source=source_id,
        rule_id_target=target_id,
        relationship_type="cites",
        confidence_score=0.95,
        extraction_method="regex",
        created_at=datetime(2024, 6, 1, 12, 0, 0),
    )
    pg_session.add(edge)
    pg_session.flush()

    result = pg_session.get(Edge, edge.edge_id)
    assert result is not None
    assert result.relationship_type == "cites"
    assert result.confidence_score == pytest.approx(0.95)


def test_insert_and_read_dead_letter(pg_session: Session) -> None:
    """Should round-trip a DeadLetter through Postgres."""
    dl = DeadLetter(
        dead_letter_id=uuid.uuid4(),
        source_url="https://example.com/fail",
        raw_payload='{"bad": "data"}',
        error_message="Validation failed: missing title",
        failed_at=datetime(2024, 6, 1, 12, 0, 0),
    )
    pg_session.add(dl)
    pg_session.flush()

    result = pg_session.get(DeadLetter, dl.dead_letter_id)
    assert result is not None
    assert result.error_message == "Validation failed: missing title"


def test_content_hash_uniqueness(pg_session: Session) -> None:
    """Duplicate content_hash should raise IntegrityError."""
    from sqlalchemy.exc import IntegrityError

    rule1 = Rule(
        rule_id=uuid.uuid4(),
        title="Rule 1",
        full_text="Text 1",
        publication_date=date(2024, 1, 1),
        agency="FERC",
        document_type="Rule",
        administration="Biden",
        fr_url="https://federalregister.gov/d/2024-00001",
        content_hash="duplicate_hash",
    )
    rule2 = Rule(
        rule_id=uuid.uuid4(),
        title="Rule 2",
        full_text="Text 2",
        publication_date=date(2024, 2, 1),
        agency="FERC",
        document_type="Rule",
        administration="Biden",
        fr_url="https://federalregister.gov/d/2024-00002",
        content_hash="duplicate_hash",
    )
    pg_session.add(rule1)
    pg_session.flush()

    pg_session.add(rule2)
    with pytest.raises(IntegrityError):
        pg_session.flush()
```

- [ ] **Step 2: Run unit tests (should still pass without Postgres)**

Run:
```bash
cd /c/Projects/trace
uv run pytest tests/unit/ -v
```

Expected: All unit tests pass.

- [ ] **Step 3: Run integration tests (requires Postgres)**

Run:
```bash
cd /c/Projects/trace
# Start postgres first:
# docker compose up -d postgres
# Then:
uv run pytest tests/integration/ -v -m integration
```

Expected: 4 passed (only if Postgres is running; otherwise skip this verification until Docker is available).

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_database.py
git commit -m "$(cat <<'EOF'
test: add integration tests for ORM models against Postgres

Tests round-trip insert/read for Rule, Edge, DeadLetter and
verifies content_hash uniqueness constraint.
EOF
)"
```

---

### Task 13: ADR — Why Postgres Over a Graph Database

**Files:**
- Create: `docs/adr/001-postgres-over-graph-db.md`

- [ ] **Step 1: Create the ADR**

`docs/adr/001-postgres-over-graph-db.md`:
```markdown
# ADR 001: Postgres Over a Graph Database

## Status

Accepted

## Context

TRACE builds a citation graph between regulatory documents. Graph databases
(Neo4j, Amazon Neptune) are purpose-built for graph traversal. However, our
data also requires full-text search, vector similarity search (pgvector),
relational queries with aggregation, and transactional writes.

## Decision

Use PostgreSQL 16 with pgvector. Model graph edges as a relational table with
foreign keys to the rules table. Use NetworkX for in-memory graph analytics
(PageRank, path finding) by loading the edge table on demand.

## Consequences

- **Pro:** Single database for relational, vector, and graph-edge storage.
  Simpler ops, backups, and migrations.
- **Pro:** pgvector enables semantic search without a separate vector store.
- **Pro:** NetworkX handles analytics workloads at our expected scale
  (thousands to low tens of thousands of rules).
- **Con:** Multi-hop traversals are slower than a native graph DB. Acceptable
  at our scale; revisit if we exceed ~100k edges.
- **Con:** No native graph query language (Cypher). Graph queries go through
  SQLAlchemy + NetworkX instead.
```

- [ ] **Step 2: Commit**

```bash
mkdir -p /c/Projects/trace/docs/adr
git add docs/adr/001-postgres-over-graph-db.md
git commit -m "$(cat <<'EOF'
docs: add ADR 001 — Postgres over graph database

Documents the decision to use Postgres + pgvector + NetworkX
instead of a dedicated graph database.
EOF
)"
```

---

### Task 14: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace README content**

`README.md`:
```markdown
# TRACE

**Tracking Regulatory Actors, Capture, and Erasure**

A modular regulatory intelligence platform with administration-level comparison,
cross-document citation graph, and natural language querying. Initial module:
FERC rulemaking from the Federal Register.

## Quick Start

```bash
# Clone and install
git clone <repo-url> && cd trace
uv sync --all-extras

# Copy environment config
cp .env.example .env
# Edit .env with your DATABASE_URL and OPENAI_API_KEY

# Start database
docker compose up -d postgres

# Run migrations
make migrate

# Run tests
make test

# Lint and type check
make lint
```

## Development

```bash
make up        # Start all Docker services
make down      # Stop all Docker services
make test      # Run pytest with coverage
make lint      # Run ruff + mypy
make fmt       # Auto-format with ruff
make migrate   # Run Alembic migrations
make ingest    # Run FERC ingestion
make check     # Lint + test
```

## Architecture

- **Python 3.12** with uv for dependency management
- **PostgreSQL 17 + pgvector** for relational, vector, and graph-edge storage
- **SQLAlchemy + Alembic** for ORM and migrations
- **Pydantic v2** for data validation
- **structlog** for structured JSON logging

See `docs/adr/` for architecture decision records.

## Project Structure

```
src/trace/
├── config.py           # Pydantic settings from env vars
├── connectors/         # Source-specific ingestion (FERC, etc.)
├── processing/         # Shared processing pipeline
├── storage/            # DB models, engine, session factory
├── graph/              # Edge extraction, NetworkX analytics
├── agent/              # LangGraph query agent
└── frontend/           # Streamlit UI
```

## License

MPL-2.0
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "$(cat <<'EOF'
docs: update README with architecture and quick start

Adds quick start guide, development commands, architecture
overview, and project structure documentation.
EOF
)"
```

---

### Task 15: Final Verification

- [ ] **Step 1: Run full lint suite**

Run:
```bash
cd /c/Projects/trace
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
```

Expected: No errors.

- [ ] **Step 2: Run mypy**

Run:
```bash
cd /c/Projects/trace
uv run mypy src/
```

Expected: `Success: no issues found`

- [ ] **Step 3: Run unit tests with coverage**

Run:
```bash
cd /c/Projects/trace
uv run pytest tests/unit/ --cov=trace --cov-report=term-missing -v
```

Expected: All tests pass. Coverage above 80% for the modules created so far.

- [ ] **Step 4: Fix any issues found**

If any lint, type, or test failures: fix them, then re-run the failing check.

- [ ] **Step 5: Final commit (if any fixes were needed)**

```bash
git add -u
git commit -m "fix: resolve lint/type/test issues from final verification"
```

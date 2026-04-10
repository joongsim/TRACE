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
# Edit .env with your DATABASE_URL

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
- **sentence-transformers** (`bge-small-en-v1.5`, 384d) for local embeddings
- **structlog** for structured JSON logging

See `docs/adr/` for architecture decision records.

## Project Structure

```
src/trace_app/
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

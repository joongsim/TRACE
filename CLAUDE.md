# TRACE

Regulatory intelligence platform. FERC rulemaking from the Federal Register, with administration-level comparison and citation graph.

## Rules for this file

- Keep CLAUDE.md lean. No tutorials, no explanations of tools, no obvious statements.
- Add only what changes Claude's behavior. If Claude would do it by default, don't write it down.
- Prefer deleting stale entries over updating them.

## Code style

- Prefer simple code over clever code. If two approaches work, choose the more readable one.
- No speculative abstractions. Build what the task requires, nothing more.
- No defensive error handling for scenarios that can't happen.
- No comments unless the logic is genuinely non-obvious.

## Stack

- Python 3.12, uv (not pip, not poetry)
- PostgreSQL 17 + pgvector
- SQLAlchemy + Alembic, Pydantic v2, structlog
- sentence-transformers (`all-MiniLM-L6-v2`, 384d) for embeddings
- Prefect for orchestration, LangGraph for agent, Streamlit for UI
- Plotly for graph visualization (not Pyvis)

## Commands

```
uv sync --all-extras     # install deps
make test                # pytest with coverage
make lint                # ruff + mypy
make fmt                 # auto-format
make migrate             # alembic upgrade head
make up / make down      # docker compose
```

## Worktrees

Use `.worktrees/` for git worktrees.

## Testing

- pytest, TDD — write the failing test first
- Unit tests use SQLite in-memory. Integration tests (marked `@pytest.mark.integration`) require Postgres.
- 60% coverage minimum enforced in CI. Focus coverage on connectors, processing, storage, and graph — not config/boilerplate.

## Migrations

Always use Alembic. Never modify the database schema directly. Never edit existing migration files.

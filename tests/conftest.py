"""Shared test fixtures."""

import os
from collections.abc import Generator
from contextlib import suppress

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import CompileError
from sqlalchemy.orm import Session, sessionmaker

from trace_app.storage.models import Base


def _create_sqlite_tables(engine: Engine) -> None:
    """Create tables in SQLite, skipping PG-specific column types per table.

    Tables that fail entirely (e.g. rules, due to Vector/ARRAY) are created
    via raw SQL with those columns omitted.
    """
    for table in Base.metadata.sorted_tables:
        with suppress(CompileError):
            table.create(engine)

    # rules fails because of Vector(384) and ARRAY — create a SQLite-compatible
    # version with those columns stored as TEXT so ORM inserts still work.
    with engine.connect() as conn:
        try:
            conn.execute(text("SELECT 1 FROM rules LIMIT 1"))
        except Exception:
            conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS rules (
                    rule_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    abstract TEXT,
                    full_text TEXT NOT NULL,
                    publication_date TEXT NOT NULL,
                    effective_date TEXT,
                    agency TEXT NOT NULL,
                    document_type TEXT NOT NULL,
                    cfr_sections TEXT,
                    administration TEXT NOT NULL,
                    fr_url TEXT NOT NULL,
                    embedding TEXT,
                    ingested_at TEXT,
                    content_hash TEXT UNIQUE,
                    fr_document_number TEXT,
                    text_source TEXT NOT NULL DEFAULT 'html_fallback'
                )
            """)
            )
            conn.commit()


@pytest.fixture
def sqlite_engine() -> Engine:
    """In-memory SQLite engine for unit tests.

    Tables with Postgres-specific column types (Vector, ARRAY) are skipped —
    use pg_session for tests that require those models.
    """
    engine = create_engine("sqlite:///:memory:")
    _create_sqlite_tables(engine)
    return engine


@pytest.fixture
def sqlite_session(
    sqlite_engine: Engine,
) -> Generator[Session, None, None]:
    """SQLite session for unit tests. Rolls back after each test."""
    session_factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
    session = session_factory()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def pg_engine() -> Engine:
    """Postgres engine for integration tests. Requires running database."""
    url = os.environ.get("DATABASE_URL", "postgresql+psycopg://trace:trace@localhost:5433/trace")
    engine = create_engine(url)
    with engine.connect() as conn:
        conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(engine)
    with engine.connect() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(sa.text(f"TRUNCATE TABLE {table.name} CASCADE"))
        conn.commit()
    return engine


@pytest.fixture
def pg_session(pg_engine: Engine) -> Generator[Session, None, None]:
    """Postgres session for integration tests. Rolls back after each test."""
    session_factory = sessionmaker(bind=pg_engine, expire_on_commit=False)
    session = session_factory()
    yield session
    session.rollback()
    session.close()

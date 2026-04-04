"""Shared test fixtures."""

import os
from collections.abc import Generator
from contextlib import suppress

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from trace_app.storage.models import Base


@pytest.fixture
def sqlite_engine() -> Engine:
    """In-memory SQLite engine for unit tests."""
    engine = create_engine("sqlite:///:memory:")
    with suppress(Exception):
        Base.metadata.create_all(engine)
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
    url = os.environ.get("DATABASE_URL", "postgresql+psycopg://trace:trace@localhost:5432/trace")
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def pg_session(pg_engine: Engine) -> Generator[Session, None, None]:
    """Postgres session for integration tests. Rolls back after each test."""
    session_factory = sessionmaker(bind=pg_engine, expire_on_commit=False)
    session = session_factory()
    yield session
    session.rollback()
    session.close()

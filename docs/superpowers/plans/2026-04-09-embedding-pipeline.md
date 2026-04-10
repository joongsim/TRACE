# Embedding Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate and store 384d sentence embeddings for all `Rule` records using `bge-small-en-v1.5`, with a standalone Prefect flow that also runs as a subflow after ingestion.

**Architecture:** Pure embedding logic lives in `processing/embeddings.py` (no I/O); a Prefect flow in `connectors/embed.py` queries null-embedding rows, batches them, and writes vectors back via a new `save_embeddings` storage helper. `ingest_fr` calls `embed_rules()` as a subflow at the end. An Alembic migration adds the ivfflat index after first ingest.

**Tech Stack:** sentence-transformers (`bge-small-en-v1.5`), pgvector, SQLAlchemy `update()`, Prefect 3.x flows/subflows, Alembic.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `src/trace_app/processing/embeddings.py` | Pure functions: text prep, model loading, batch encode |
| Create | `src/trace_app/connectors/embed.py` | Prefect flow: query → batch → embed → save |
| Create | `tests/unit/test_embeddings_processing.py` | Unit tests for processing functions |
| Create | `tests/unit/test_embed_connector.py` | Unit tests for flow orchestration logic |
| Create | `tests/integration/test_embed.py` | Integration tests: real model + Postgres, ANN query |
| Create | `migrations/versions/<hash>_add_embedding_ivfflat_index.py` | ivfflat index with dynamic lists param |
| Modify | `src/trace_app/config.py` | Add `embedding_batch_size: int = 64` |
| Modify | `src/trace_app/storage/ingest.py` | Add `save_embeddings()` |
| Modify | `src/trace_app/connectors/ingest.py` | Call `embed_rules()` as subflow at end of `ingest_fr` |
| Modify | `tests/unit/test_config.py` | Test new `embedding_batch_size` default |

---

## Task 1: Add `embedding_batch_size` to Settings

**Files:**
- Modify: `src/trace_app/config.py`
- Modify: `tests/unit/test_config.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_config.py`:

```python
def test_settings_embedding_batch_size_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/trace")
    settings = Settings()  # ty: ignore[missing-argument]
    assert settings.embedding_batch_size == 64
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_config.py::test_settings_embedding_batch_size_default -v
```

Expected: `FAILED` — `AttributeError: 'Settings' object has no attribute 'embedding_batch_size'`

- [ ] **Step 3: Add the field to Settings**

In `src/trace_app/config.py`, add after `embedding_dimension`:

```python
embedding_batch_size: int = 64
```

Full updated file:

```python
"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings, loaded from environment variables."""

    database_url: str
    log_level: str = "INFO"
    embedding_model: str = "bge-small-en-v1.5"
    embedding_dimension: int = 384
    embedding_batch_size: int = 64
    docling_url: str | None = None

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/test_config.py -v
```

Expected: all config tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/trace_app/config.py tests/unit/test_config.py
git commit -m "feat: add embedding_batch_size to Settings"
```

---

## Task 2: Pure embedding functions in `processing/embeddings.py`

**Files:**
- Create: `src/trace_app/processing/embeddings.py`
- Create: `tests/unit/test_embeddings_processing.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_embeddings_processing.py`:

```python
"""Unit tests for processing/embeddings.py."""

import uuid
from datetime import date
from unittest.mock import MagicMock

import numpy as np

from trace_app.processing.embeddings import build_embed_text, embed_batch
from trace_app.storage.models import Rule


def _make_rule(**kwargs) -> Rule:
    defaults = dict(
        rule_id=uuid.uuid4(),
        title="Test Rule Title",
        abstract="Abstract text.",
        full_text="a" * 3000,
        publication_date=date(2024, 1, 1),
        agency="FERC",
        document_type="RULE",
        administration="Biden",
        fr_url="https://www.federalregister.gov/documents/2024/01/01/test",
        text_source="html_fallback",
    )
    defaults.update(kwargs)
    return Rule(**defaults)


def test_build_embed_text_contains_title_and_abstract():
    rule = _make_rule(title="My Title", abstract="My Abstract", full_text="body " * 600)
    text = build_embed_text(rule)
    assert "My Title" in text
    assert "My Abstract" in text


def test_build_embed_text_truncates_full_text_to_2048():
    rule = _make_rule(full_text="x" * 3000)
    text = build_embed_text(rule)
    # full_text section should be exactly 2048 chars
    parts = text.split("\n\n")
    assert len(parts[2]) == 2048


def test_build_embed_text_handles_null_abstract():
    rule = _make_rule(abstract=None, full_text="short")
    text = build_embed_text(rule)
    # Should not raise; empty abstract becomes empty string
    assert "Test Rule Title" in text
    assert "short" in text


def test_embed_batch_returns_list_of_float_lists():
    model = MagicMock()
    model.encode.return_value = np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
    result = embed_batch(model, ["text one", "text two"])
    assert result == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]


def test_embed_batch_passes_texts_to_encode():
    model = MagicMock()
    model.encode.return_value = np.array([[0.1]])
    embed_batch(model, ["hello world"])
    model.encode.assert_called_once_with(["hello world"], convert_to_numpy=True)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_embeddings_processing.py -v
```

Expected: `ERROR` — `ModuleNotFoundError: No module named 'trace_app.processing.embeddings'`

- [ ] **Step 3: Create `processing/embeddings.py`**

Create `src/trace_app/processing/embeddings.py`:

```python
"""Pure functions for generating rule embeddings."""

from sentence_transformers import SentenceTransformer

from trace_app.storage.models import Rule


def build_embed_text(rule: Rule) -> str:
    return f"{rule.title}\n\n{rule.abstract or ''}\n\n{rule.full_text[:2048]}"


def load_model(name: str) -> SentenceTransformer:
    return SentenceTransformer(name)


def embed_batch(model: SentenceTransformer, texts: list[str]) -> list[list[float]]:
    return model.encode(texts, convert_to_numpy=True).tolist()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_embeddings_processing.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/trace_app/processing/embeddings.py tests/unit/test_embeddings_processing.py
git commit -m "feat: add pure embedding functions to processing/embeddings"
```

---

## Task 3: `save_embeddings` storage helper

**Files:**
- Modify: `src/trace_app/storage/ingest.py`
- Modify: `tests/integration/test_embed.py` (create file, add first test)

- [ ] **Step 1: Write the failing integration test**

Create `tests/integration/test_embed.py`:

```python
"""Integration tests for the embedding pipeline (requires Postgres)."""

import uuid
from datetime import date

import pytest

from trace_app.storage.ingest import save_embeddings
from trace_app.storage.models import Rule


def _make_rule(**kwargs) -> Rule:
    defaults = dict(
        title="Test Rule",
        abstract="Abstract.",
        full_text="Full text content.",
        publication_date=date(2024, 1, 1),
        agency="FERC",
        document_type="RULE",
        administration="Biden",
        fr_url="https://www.federalregister.gov/documents/2024/01/01/test",
        fr_document_number=str(uuid.uuid4()),
        content_hash=str(uuid.uuid4()),
        text_source="html_fallback",
    )
    defaults.update(kwargs)
    return Rule(**defaults)


@pytest.mark.integration
def test_save_embeddings_sets_embedding_on_rules(pg_session):
    r1 = _make_rule()
    r2 = _make_rule()
    pg_session.add_all([r1, r2])
    pg_session.flush()

    vectors = [[0.1] * 384, [0.2] * 384]
    save_embeddings(pg_session, [r1.rule_id, r2.rule_id], vectors)
    pg_session.flush()

    from sqlalchemy import select
    rows = pg_session.execute(select(Rule)).scalars().all()
    embeddings = {str(r.rule_id): r.embedding for r in rows}

    assert embeddings[str(r1.rule_id)] is not None
    assert len(embeddings[str(r1.rule_id)]) == 384
    assert embeddings[str(r2.rule_id)] is not None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/integration/test_embed.py::test_save_embeddings_sets_embedding_on_rules -v -m integration
```

Expected: `FAILED` — `ImportError: cannot import name 'save_embeddings' from 'trace_app.storage.ingest'`

- [ ] **Step 3: Add `save_embeddings` to `storage/ingest.py`**

Add these imports at the top of `src/trace_app/storage/ingest.py`:

```python
import uuid

from sqlalchemy import update
```

Then add at the bottom of `src/trace_app/storage/ingest.py`:

```python
def save_embeddings(
    session: Session,
    rule_ids: list[uuid.UUID],
    vectors: list[list[float]],
) -> None:
    """Bulk-update embedding on a batch of rules."""
    for rule_id, vector in zip(rule_ids, vectors):
        session.execute(
            update(Rule).where(Rule.rule_id == rule_id).values(embedding=vector)
        )
    session.flush()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/integration/test_embed.py::test_save_embeddings_sets_embedding_on_rules -v -m integration
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/trace_app/storage/ingest.py tests/integration/test_embed.py
git commit -m "feat: add save_embeddings storage helper"
```

---

## Task 4: `embed_rules` Prefect flow

**Files:**
- Create: `src/trace_app/connectors/embed.py`
- Create: `tests/unit/test_embed_connector.py`

- [ ] **Step 1: Write the failing unit tests**

Create `tests/unit/test_embed_connector.py`:

```python
"""Unit tests for the embed_rules Prefect flow."""

import uuid
from datetime import date
from unittest.mock import MagicMock, patch

from trace_app.storage.models import Rule


def _make_rule(**kwargs) -> Rule:
    defaults = dict(
        rule_id=uuid.uuid4(),
        title="Test Rule",
        abstract="Abstract.",
        full_text="a" * 3000,
        publication_date=date(2024, 1, 1),
        agency="FERC",
        document_type="RULE",
        administration="Biden",
        fr_url="https://example.com",
        fr_document_number=str(uuid.uuid4()),
        text_source="html_fallback",
    )
    defaults.update(kwargs)
    return Rule(**defaults)


def _mock_session(rules: list[Rule]) -> MagicMock:
    session = MagicMock()
    session.execute.return_value.scalars.return_value.all.return_value = rules
    return session


def test_embed_rules_skips_when_no_null_embedding_rows():
    session = _mock_session([])

    with (
        patch("trace_app.connectors.embed.Settings", return_value=MagicMock(
            embedding_model="bge-small-en-v1.5", embedding_batch_size=64
        )),
        patch("trace_app.connectors.embed.build_engine"),
        patch("trace_app.connectors.embed.build_session_factory", return_value=lambda: session),
        patch("trace_app.connectors.embed.load_model"),
        patch("trace_app.connectors.embed.embed_batch") as mock_embed,
        patch("trace_app.connectors.embed.save_embeddings"),
    ):
        from trace_app.connectors.embed import embed_rules
        embed_rules()

    mock_embed.assert_not_called()


def test_embed_rules_calls_save_embeddings_with_correct_rule_ids():
    rules = [_make_rule(), _make_rule()]
    session = _mock_session(rules)
    fake_vectors = [[0.1] * 384, [0.2] * 384]

    with (
        patch("trace_app.connectors.embed.Settings", return_value=MagicMock(
            embedding_model="bge-small-en-v1.5", embedding_batch_size=64
        )),
        patch("trace_app.connectors.embed.build_engine"),
        patch("trace_app.connectors.embed.build_session_factory", return_value=lambda: session),
        patch("trace_app.connectors.embed.load_model"),
        patch("trace_app.connectors.embed.embed_batch", return_value=fake_vectors),
        patch("trace_app.connectors.embed.save_embeddings") as mock_save,
    ):
        from trace_app.connectors.embed import embed_rules
        embed_rules()

    mock_save.assert_called_once()
    _, rule_ids, vectors = mock_save.call_args[0]
    assert set(rule_ids) == {r.rule_id for r in rules}
    assert vectors == fake_vectors


def test_embed_rules_batches_by_batch_size():
    rules = [_make_rule() for _ in range(5)]
    session = _mock_session(rules)

    with (
        patch("trace_app.connectors.embed.Settings", return_value=MagicMock(
            embedding_model="bge-small-en-v1.5", embedding_batch_size=2
        )),
        patch("trace_app.connectors.embed.build_engine"),
        patch("trace_app.connectors.embed.build_session_factory", return_value=lambda: session),
        patch("trace_app.connectors.embed.load_model"),
        patch(
            "trace_app.connectors.embed.embed_batch",
            side_effect=lambda m, texts: [[0.1] * 384] * len(texts),
        ) as mock_embed,
        patch("trace_app.connectors.embed.save_embeddings"),
    ):
        from trace_app.connectors.embed import embed_rules
        embed_rules()

    # 5 rules at batch_size=2 → 3 calls: [2, 2, 1]
    assert mock_embed.call_count == 3


def test_embed_rules_loads_model_once_regardless_of_batch_count():
    rules = [_make_rule() for _ in range(4)]
    session = _mock_session(rules)

    with (
        patch("trace_app.connectors.embed.Settings", return_value=MagicMock(
            embedding_model="bge-small-en-v1.5", embedding_batch_size=2
        )),
        patch("trace_app.connectors.embed.build_engine"),
        patch("trace_app.connectors.embed.build_session_factory", return_value=lambda: session),
        patch("trace_app.connectors.embed.load_model") as mock_load,
        patch(
            "trace_app.connectors.embed.embed_batch",
            side_effect=lambda m, texts: [[0.1] * 384] * len(texts),
        ),
        patch("trace_app.connectors.embed.save_embeddings"),
    ):
        from trace_app.connectors.embed import embed_rules
        embed_rules()

    mock_load.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_embed_connector.py -v
```

Expected: `ERROR` — `ModuleNotFoundError: No module named 'trace_app.connectors.embed'`

- [ ] **Step 3: Create `connectors/embed.py`**

Create `src/trace_app/connectors/embed.py`:

```python
"""Prefect flow for generating and storing rule embeddings."""

from prefect import flow
from sqlalchemy import select

from trace_app.config import Settings
from trace_app.processing.embeddings import build_embed_text, embed_batch, load_model
from trace_app.storage.database import build_engine, build_session_factory
from trace_app.storage.ingest import save_embeddings
from trace_app.storage.models import Rule


@flow(name="embed_rules", log_prints=True)
def embed_rules(batch_size: int | None = None) -> None:
    """Embed all rules where embedding IS NULL. Safe to re-run."""
    settings = Settings()  # ty: ignore[missing-argument]
    effective_batch_size = batch_size if batch_size is not None else settings.embedding_batch_size

    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    model = load_model(settings.embedding_model)

    session = session_factory()
    try:
        rules = session.execute(
            select(Rule).where(Rule.embedding.is_(None))
        ).scalars().all()

        total = len(rules)
        embedded = 0

        for i in range(0, total, effective_batch_size):
            batch = rules[i : i + effective_batch_size]
            texts = [build_embed_text(r) for r in batch]
            vectors = embed_batch(model, texts)
            save_embeddings(session, [r.rule_id for r in batch], vectors)
            session.commit()
            embedded += len(batch)
            print(f"embedded {embedded}/{total}")
    finally:
        session.close()

    print(f"done: {embedded} rules embedded")


if __name__ == "__main__":
    embed_rules()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_embed_connector.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/trace_app/connectors/embed.py tests/unit/test_embed_connector.py
git commit -m "feat: add embed_rules Prefect flow"
```

---

## Task 5: Wire `embed_rules` as subflow in `ingest_fr`

**Files:**
- Modify: `src/trace_app/connectors/ingest.py`

- [ ] **Step 1: Add the subflow call at the end of `ingest_fr`**

In `src/trace_app/connectors/ingest.py`, add the import at the top (after the existing imports):

```python
from trace_app.connectors.embed import embed_rules
```

Then at the end of `ingest_fr`, after the `print(f"ingest complete: ...")` line, add:

```python
    try:
        embed_rules()
    except Exception as exc:
        print(f"embedding failed (ingestion still succeeded): {exc}")
```

Full updated `ingest_fr` end section (the `finally` block through end of function):

```python
    finally:
        session.close()

    print(f"ingest complete: inserted={inserted} updated={updated} failed={failed}")

    try:
        embed_rules()
    except Exception as exc:
        print(f"embedding failed (ingestion still succeeded): {exc}")
```

- [ ] **Step 2: Run existing ingest tests to verify nothing broke**

```bash
uv run pytest tests/unit/ -v
```

Expected: all unit tests PASS.

- [ ] **Step 3: Commit**

```bash
git add src/trace_app/connectors/ingest.py
git commit -m "feat: call embed_rules as subflow at end of ingest_fr"
```

---

## Task 6: Alembic migration — ivfflat index

**Files:**
- Create: `migrations/versions/<hash>_add_embedding_ivfflat_index.py`

- [ ] **Step 1: Generate the migration stub**

```bash
uv run alembic revision -m "add_embedding_ivfflat_index"
```

This creates `migrations/versions/<hash>_add_embedding_ivfflat_index.py`. Note the generated hash.

- [ ] **Step 2: Fill in the migration**

Open the generated file and replace the `upgrade` and `downgrade` functions. The full file should look like this (preserving the generated `revision` and `down_revision` values):

```python
"""add_embedding_ivfflat_index

Revision ID: <generated-hash>
Revises: e7f8a9b0
Create Date: <generated-date>
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "<generated-hash>"
down_revision: str | None = "e7f8a9b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(text("SELECT COUNT(*) FROM rules WHERE embedding IS NOT NULL"))
    count = result.scalar() or 0
    lists = max(1, count // 1000) if count > 0 else 100
    op.execute(
        f"CREATE INDEX IF NOT EXISTS rules_embedding_ivfflat_idx "
        f"ON rules USING ivfflat (embedding vector_cosine_ops) "
        f"WITH (lists = {lists})"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS rules_embedding_ivfflat_idx")
```

- [ ] **Step 3: Verify migration runs cleanly**

```bash
uv run alembic upgrade head
```

Expected: migration applies with no errors. If the table is empty, `lists=100` is used.

- [ ] **Step 4: Verify downgrade works**

```bash
uv run alembic downgrade -1
uv run alembic upgrade head
```

Expected: both commands succeed.

- [ ] **Step 5: Commit**

```bash
git add migrations/versions/
git commit -m "feat: add ivfflat index migration for rules.embedding"
```

---

## Task 7: End-to-end integration test (full flow + ANN query)

**Files:**
- Modify: `tests/integration/test_embed.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/integration/test_embed.py` (after the existing `test_save_embeddings_sets_embedding_on_rules` test):

```python
@pytest.mark.integration
def test_embed_rules_flow_embeds_all_null_rows(pg_engine):
    """Full embed_rules flow run against Postgres with real model."""
    import os
    from sqlalchemy.orm import sessionmaker
    from trace_app.connectors.embed import embed_rules

    session_factory = sessionmaker(bind=pg_engine, expire_on_commit=False)
    session = session_factory()

    # Seed two rules with null embeddings
    r1 = _make_rule(title="FERC rate case order", abstract="Electric rate proceedings.")
    r2 = _make_rule(title="Natural gas pipeline certificate", abstract="Pipeline expansion.")
    session.add_all([r1, r2])
    session.commit()
    session.close()

    # Run the flow (loads real model, embeds, writes back)
    with patch("trace_app.connectors.embed.Settings", return_value=MagicMock(
        database_url=os.environ.get(
            "DATABASE_URL", "postgresql+psycopg://trace:trace@localhost:5433/trace"
        ),
        embedding_model="bge-small-en-v1.5",
        embedding_batch_size=64,
    )):
        embed_rules()

    session = session_factory()
    from sqlalchemy import select
    rows = session.execute(select(Rule)).scalars().all()
    session.close()

    assert all(r.embedding is not None for r in rows)
    assert all(len(r.embedding) == 384 for r in rows)


@pytest.mark.integration
def test_ann_query_returns_semantically_relevant_results(pg_engine):
    """ANN query via ivfflat index returns the most relevant rule."""
    import os
    from sentence_transformers import SentenceTransformer
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import text

    session_factory = sessionmaker(bind=pg_engine, expire_on_commit=False)
    session = session_factory()

    model = SentenceTransformer("bge-small-en-v1.5")

    r1 = _make_rule(title="FERC electric rate case", abstract="Rate proceedings for electricity.")
    r2 = _make_rule(title="Natural gas pipeline expansion", abstract="New pipeline certificate.")
    session.add_all([r1, r2])
    session.flush()

    from trace_app.storage.ingest import save_embeddings
    from trace_app.processing.embeddings import build_embed_text, embed_batch
    vectors = embed_batch(model, [build_embed_text(r1), build_embed_text(r2)])
    save_embeddings(session, [r1.rule_id, r2.rule_id], vectors)
    session.commit()

    # Query with a phrase semantically close to r1
    query_vec = model.encode("electricity rate order", convert_to_numpy=True).tolist()
    query_str = "[" + ",".join(f"{v}" for v in query_vec) + "]"

    results = session.execute(
        text(
            "SELECT rule_id, title, embedding <=> CAST(:vec AS vector) AS dist "
            "FROM rules ORDER BY dist LIMIT 1"
        ),
        {"vec": query_str},
    ).fetchall()
    session.close()

    assert len(results) == 1
    assert results[0].title == "FERC electric rate case"
```

Add this import at the top of the file:

```python
from unittest.mock import MagicMock, patch
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/integration/test_embed.py -v -m integration
```

Expected: `test_embed_rules_flow_embeds_all_null_rows` FAILS — model not found or DB error (confirms test is live).

- [ ] **Step 3: Run tests with Docker Compose up**

```bash
make up
uv run pytest tests/integration/test_embed.py -v -m integration
```

Expected: both integration tests PASS. The ANN query test may require the ivfflat index to exist (`make migrate` first).

- [ ] **Step 4: Run full test suite to verify nothing regressed**

```bash
uv run pytest -v
```

Expected: all unit tests pass; integration tests pass with `make up`.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_embed.py
git commit -m "test: add integration tests for embed_rules flow and ANN query"
```

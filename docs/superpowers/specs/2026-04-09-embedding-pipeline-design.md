# Embedding Pipeline Design

**Date:** 2026-04-09  
**Issue:** [#2 Phase 2: Embedding Pipeline](https://github.com/joongsim/TRACE/issues/2)

## Goal

Generate and store semantic embeddings for all `Rule` records using a local sentence-transformers model. Embeddings enable ANN (approximate nearest-neighbour) search over ingested rules.

## Decisions

- Model: `bge-small-en-v1.5` via sentence-transformers, 384d, runs locally (no API calls)
- Text input: `f"{rule.title}\n\n{rule.abstract or ''}\n\n{rule.full_text[:2048]}"`
- Only embed rows where `embedding IS NULL` — idempotent, safe to re-run
- Batch size configurable via `Settings.embedding_batch_size` (default: 64)
- Embedding and ingestion are decoupled — ingestion does not fail if embedding fails

## Architecture

### `processing/embeddings.py` — pure functions, no I/O

```python
build_embed_text(rule: Rule) -> str
load_model(name: str) -> SentenceTransformer
embed_batch(model: SentenceTransformer, texts: list[str]) -> list[list[float]]
```

No database access, no Prefect. Fully unit-testable.

### `connectors/embed.py` — Prefect flow

```python
@flow(name="embed_rules")
def embed_rules(batch_size: int | None = None) -> None
```

- Loads model once per flow run
- Queries all rules where `embedding IS NULL`
- Processes in batches; each batch commits independently
- Runnable standalone: `python -m trace_app.connectors.embed`

### `storage/ingest.py` — new helper

```python
save_embeddings(session: Session, rule_ids: list[uuid.UUID], vectors: list[list[float]]) -> None
```

Bulk-updates `embedding` on matched rule IDs.

### `connectors/ingest.py` — subflow call

`ingest_fr` calls `embed_rules()` as a subflow at the end. Embedding failure does not fail ingestion.

## Data Flow

```
embed_rules()
  │
  ├── load_model(settings.embedding_model)          # once
  ├── SELECT * FROM rules WHERE embedding IS NULL
  └── for each batch:
        texts   = [build_embed_text(r) for r in batch]
        vectors = embed_batch(model, texts)
        save_embeddings(session, rule_ids, vectors)
        session.commit()
```

## Migration: ivfflat Index

A new Alembic migration creates an `ivfflat` index on `rules.embedding`:

```sql
SELECT COUNT(*) FROM rules;
-- lists = max(1, count // 1000), fallback 100 if table empty
CREATE INDEX IF NOT EXISTS rules_embedding_ivfflat_idx
  ON rules USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = <computed>);
```

Run manually after first full ingest via `make migrate`. Tracked in Alembic history — no schema drift.

## Testing

| File | Type | What it tests |
|------|------|---------------|
| `tests/unit/test_embeddings_processing.py` | unit | `build_embed_text` output, `embed_batch` with mocked model |
| `tests/unit/test_embed_connector.py` | unit | flow logic on SQLite: seeds null-embedding rules, mocks `embed_batch`, asserts writes; verifies re-run skips embedded rows |
| `tests/integration/test_embed.py` | integration | full run on Postgres with real model; asserts non-null embeddings; ANN query returns semantically relevant results |

Real model only loaded in integration tests.

## Acceptance Criteria

- [ ] All ingested rules have non-null embeddings after pipeline run
- [ ] pgvector ANN query returns semantically relevant results
- [ ] Re-running pipeline only embeds new/null rows

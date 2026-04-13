"""Integration tests for the embedding pipeline (requires Postgres)."""

import uuid
from datetime import date
from unittest.mock import MagicMock, patch

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
    with patch(
        "trace_app.connectors.embed.Settings",
        return_value=MagicMock(
            database_url=os.environ.get(
                "DATABASE_URL", "postgresql+psycopg://trace:trace@localhost:5433/trace"
            ),
            embedding_model="all-MiniLM-L6-v2",
            embedding_batch_size=64,
        ),
    ):
        embed_rules()

    session = session_factory()
    from sqlalchemy import select

    rows = session.execute(select(Rule)).scalars().all()
    session.close()

    assert all(r.embedding is not None for r in rows)
    assert all(len(r.embedding) == 384 for r in rows if r.embedding is not None)


@pytest.mark.integration
def test_ann_query_returns_semantically_relevant_results(pg_engine):
    """ANN query via ivfflat index returns the most relevant rule."""
    from sentence_transformers import SentenceTransformer
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    from trace_app.processing.embeddings import build_embed_text, embed_batch

    session_factory = sessionmaker(bind=pg_engine, expire_on_commit=False)
    session = session_factory()

    model = SentenceTransformer("all-MiniLM-L6-v2")

    r1 = _make_rule(title="FERC electric rate case", abstract="Rate proceedings for electricity.")
    r2 = _make_rule(title="Natural gas pipeline expansion", abstract="New pipeline certificate.")
    session.add_all([r1, r2])
    session.flush()

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

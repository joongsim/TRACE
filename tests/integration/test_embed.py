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

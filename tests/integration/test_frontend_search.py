"""Integration tests for hybrid search (requires Postgres + pgvector)."""

import uuid
from datetime import UTC, date, datetime

import pytest
from sentence_transformers import SentenceTransformer

from trace_app.frontend.search import search_rules_hybrid
from trace_app.storage.models import Rule

model = SentenceTransformer("all-MiniLM-L6-v2")


def _embed(text: str) -> list[float]:
    return model.encode(text).tolist()


def _make_rule(**overrides) -> Rule:
    defaults = dict(
        rule_id=uuid.uuid4(),
        title="Test Rule",
        abstract="An abstract about electricity markets.",
        full_text="Full body text about FERC regulations.",
        publication_date=date(2021, 6, 1),
        agency="FERC",
        document_type="RULE",
        administration="Biden",
        fr_url="https://www.federalregister.gov/documents/2021/06/01/2021-11111/test",
        fr_document_number=f"2021-{uuid.uuid4().hex[:5]}",
        content_hash=uuid.uuid4().hex,
        ingested_at=datetime.now(UTC),
        text_source="html_fallback",
    )
    defaults.update(overrides)
    return Rule(**defaults)


@pytest.mark.integration
def test_hybrid_search_finds_semantic_match(pg_session):
    rule = _make_rule(
        title="Natural Gas Pipeline Safety Standards",
        abstract="Regulations governing the safety of interstate natural gas pipelines.",
        embedding=_embed("Natural Gas Pipeline Safety Standards"),
    )
    pg_session.add(rule)
    pg_session.flush()

    results = search_rules_hybrid(
        pg_session,
        query="pipeline safety regulations",
        filters={},
        embed_fn=_embed,
    )
    assert len(results) >= 1
    assert results[0]["title"] == "Natural Gas Pipeline Safety Standards"


@pytest.mark.integration
def test_hybrid_search_dedupes_keyword_and_semantic(pg_session):
    rule = _make_rule(
        title="Pipeline Safety Standards",
        abstract="Safety standards for natural gas pipelines.",
        embedding=_embed("Pipeline Safety Standards"),
    )
    pg_session.add(rule)
    pg_session.flush()

    results = search_rules_hybrid(
        pg_session,
        query="pipeline safety",
        filters={},
        embed_fn=_embed,
    )
    rule_ids = [r["rule_id"] for r in results]
    assert len(rule_ids) == len(set(rule_ids))

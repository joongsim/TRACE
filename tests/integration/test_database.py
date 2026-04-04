"""Integration tests that require a running Postgres with pgvector."""

import uuid
from datetime import date, datetime

import pytest
from sqlalchemy.orm import Session

from trace_app.storage.models import DeadLetter, Edge, Rule

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

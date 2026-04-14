"""Unit tests for administration comparison functions (SQLite)."""

import uuid
from datetime import UTC, date, datetime

from trace_app.storage.models import Rule


def _make_rule(**overrides) -> Rule:
    defaults = dict(
        rule_id=uuid.uuid4(),
        title="Test Rule",
        abstract="Abstract text.",
        full_text="Full body text.",
        publication_date=date(2021, 6, 1),
        agency="FERC",
        document_type="RULE",
        administration="Biden",
        fr_url="https://www.federalregister.gov/documents/2021/06/01/2021-11111/test",
        fr_document_number="2021-11111",
        content_hash="abc123",
        ingested_at=datetime.now(UTC),
        text_source="html_fallback",
    )
    defaults.update(overrides)
    return Rule(**defaults)


def test_get_admin_comparison_empty_db(sqlite_session):
    from trace_app.frontend.comparison import get_admin_comparison

    result = get_admin_comparison(sqlite_session)
    assert result["counts_by_admin"] == {}
    assert result["counts_by_admin_type"] == {}


def test_get_admin_comparison_counts_by_admin(sqlite_session):
    r1 = _make_rule(
        administration="Biden",
        fr_document_number="2021-11111",
        content_hash="h1",
    )
    r2 = _make_rule(
        administration="Biden",
        fr_document_number="2021-22222",
        content_hash="h2",
        document_type="NOTICE",
    )
    r3 = _make_rule(
        administration="Trump 1",
        fr_document_number="2019-33333",
        content_hash="h3",
    )
    sqlite_session.add_all([r1, r2, r3])
    sqlite_session.flush()

    from trace_app.frontend.comparison import get_admin_comparison

    result = get_admin_comparison(sqlite_session)
    assert result["counts_by_admin"]["Biden"] == 2
    assert result["counts_by_admin"]["Trump 1"] == 1


def test_get_admin_comparison_counts_by_admin_type(sqlite_session):
    r1 = _make_rule(
        administration="Biden",
        document_type="RULE",
        fr_document_number="2021-11111",
        content_hash="h1",
    )
    r2 = _make_rule(
        administration="Biden",
        document_type="NOTICE",
        fr_document_number="2021-22222",
        content_hash="h2",
    )
    sqlite_session.add_all([r1, r2])
    sqlite_session.flush()

    from trace_app.frontend.comparison import get_admin_comparison

    result = get_admin_comparison(sqlite_session)
    assert result["counts_by_admin_type"][("Biden", "RULE")] == 1
    assert result["counts_by_admin_type"][("Biden", "NOTICE")] == 1


def test_get_admin_comparison_includes_admin_spans(sqlite_session):
    from trace_app.frontend.comparison import get_admin_comparison

    result = get_admin_comparison(sqlite_session)
    spans = result["admin_spans"]
    assert len(spans) == 4
    assert spans[0]["name"] == "Obama"
    assert spans[-1]["name"] == "Trump 2"

"""Unit tests for frontend search functions (SQLite)."""

import uuid
from datetime import UTC, date, datetime

from trace_app.storage.models import Rule


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
        fr_document_number="2021-11111",
        content_hash="abc123",
        ingested_at=datetime.now(UTC),
        text_source="html_fallback",
    )
    defaults.update(overrides)
    return Rule(**defaults)


def test_get_rule_returns_matching_rule(sqlite_session):
    rule = _make_rule()
    sqlite_session.add(rule)
    sqlite_session.flush()

    from trace_app.frontend.search import get_rule

    result = get_rule(sqlite_session, rule.rule_id)
    assert result is not None
    assert result["title"] == "Test Rule"
    assert result["rule_id"] == rule.rule_id


def test_get_rule_returns_none_for_missing_id(sqlite_session):
    from trace_app.frontend.search import get_rule

    result = get_rule(sqlite_session, uuid.uuid4())
    assert result is None


def test_search_rules_keyword_matches_title(sqlite_session):
    rule = _make_rule(title="Electricity Transmission Rates")
    sqlite_session.add(rule)
    sqlite_session.flush()

    from trace_app.frontend.search import search_rules

    results = search_rules(sqlite_session, query="transmission", filters={})
    assert len(results) == 1
    assert results[0]["title"] == "Electricity Transmission Rates"


def test_search_rules_keyword_matches_abstract(sqlite_session):
    rule = _make_rule(abstract="Wholesale electricity market reform")
    sqlite_session.add(rule)
    sqlite_session.flush()

    from trace_app.frontend.search import search_rules

    results = search_rules(sqlite_session, query="wholesale", filters={})
    assert len(results) == 1


def test_search_rules_no_match_returns_empty(sqlite_session):
    rule = _make_rule()
    sqlite_session.add(rule)
    sqlite_session.flush()

    from trace_app.frontend.search import search_rules

    results = search_rules(sqlite_session, query="nonexistent_xyz", filters={})
    assert results == []


def test_search_rules_filters_by_administration(sqlite_session):
    r1 = _make_rule(
        administration="Biden",
        fr_document_number="2021-11111",
        content_hash="hash1",
    )
    r2 = _make_rule(
        administration="Trump 1",
        fr_document_number="2019-22222",
        content_hash="hash2",
        title="Another Rule",
    )
    sqlite_session.add_all([r1, r2])
    sqlite_session.flush()

    from trace_app.frontend.search import search_rules

    results = search_rules(
        sqlite_session,
        query="rule",
        filters={"administration": ["Biden"]},
    )
    assert len(results) == 1
    assert results[0]["administration"] == "Biden"


def test_search_rules_filters_by_document_type(sqlite_session):
    r1 = _make_rule(
        document_type="RULE",
        fr_document_number="2021-11111",
        content_hash="hash1",
    )
    r2 = _make_rule(
        document_type="NOTICE",
        fr_document_number="2021-22222",
        content_hash="hash2",
        title="A Notice",
    )
    sqlite_session.add_all([r1, r2])
    sqlite_session.flush()

    from trace_app.frontend.search import search_rules

    results = search_rules(
        sqlite_session,
        query="",
        filters={"document_type": ["RULE"]},
    )
    assert len(results) == 1
    assert results[0]["document_type"] == "RULE"


def test_search_rules_empty_query_returns_all(sqlite_session):
    r1 = _make_rule(fr_document_number="2021-11111", content_hash="hash1")
    r2 = _make_rule(
        fr_document_number="2021-22222",
        content_hash="hash2",
        title="Second Rule",
    )
    sqlite_session.add_all([r1, r2])
    sqlite_session.flush()

    from trace_app.frontend.search import search_rules

    results = search_rules(sqlite_session, query="", filters={})
    assert len(results) == 2

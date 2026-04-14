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

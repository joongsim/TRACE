"""Unit tests for storage helpers (SQLite — skips PG-specific columns)."""

from datetime import UTC, date, datetime

from trace_app.storage.ingest import save_dead_letter, save_rule
from trace_app.storage.models import DeadLetter, Rule


def _make_rule(**overrides) -> Rule:
    defaults = dict(
        title="Test Rule",
        full_text="Full body text.",
        publication_date=date(2021, 6, 1),
        agency="FERC",
        document_type="RULE",
        administration="Biden",
        fr_url="https://www.federalregister.gov/documents/2021/06/01/2021-11111/test",
        fr_document_number="2021-11111",
        content_hash="abc123",
        ingested_at=datetime.now(UTC),
    )
    defaults.update(overrides)
    return Rule(**defaults)


def test_save_rule_returns_true_on_insert(sqlite_session):
    rule = _make_rule()
    result = save_rule(sqlite_session, rule)
    assert result is True


def test_save_rule_returns_false_on_duplicate_hash(sqlite_session):
    rule1 = _make_rule(content_hash="unique-hash-xyz")
    rule2 = _make_rule(content_hash="unique-hash-xyz", fr_document_number="2021-22222")
    save_rule(sqlite_session, rule1)
    result = save_rule(sqlite_session, rule2)
    assert result is False


def test_save_dead_letter_persists(sqlite_session):
    save_dead_letter(
        sqlite_session,
        source_url="https://www.federalregister.gov/documents/bad",
        raw_payload='{"document_number": "2021-99999"}',
        error_message="Connection timeout",
    )
    sqlite_session.flush()
    dead = sqlite_session.query(DeadLetter).first()
    assert dead is not None
    assert dead.error_message == "Connection timeout"
    assert dead.failed_at is not None

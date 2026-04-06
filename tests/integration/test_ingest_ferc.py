"""Integration tests for the FERC ingestion flow against real Postgres."""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from trace_app.connectors.ferc import ingest_ferc
from trace_app.storage.models import DeadLetter, Rule

SAMPLE_DOCS = [
    {
        "document_number": "2021-11111",
        "title": "Electric Transmission Incentives Policy",
        "abstract": "FERC proposes new transmission incentive policy.",
        "html_url": "https://www.federalregister.gov/documents/2021/06/01/2021-11111/test",
        "body_html_url": "https://www.federalregister.gov/documents/2021/06/01/2021-11111/test/body.html",
        "publication_date": "2021-06-01",
        "effective_on": "2021-07-01",
        "type": "Rule",
        "agencies": [{"name": "Federal Energy Regulatory Commission", "id": 172}],
        "cfr_references": [{"title": 18, "part": 35}],
    },
]


@pytest.mark.integration
def test_ingest_ferc_inserts_rules(pg_session):
    with (
        patch(
            "trace_app.connectors.ferc.FederalRegisterClient.iter_pages",
            return_value=iter([SAMPLE_DOCS]),
        ),
        patch(
            "trace_app.connectors.ferc.fetch_full_texts_concurrent",
            new=AsyncMock(return_value={"2021-11111": "Full text of the rule."}),
        ),
        patch(
            "trace_app.connectors.ferc.build_engine",
            return_value=pg_session.get_bind(),
        ),
    ):
        ingest_ferc(start_date=date(2021, 1, 1), end_date=date(2021, 12, 31))

    rules = pg_session.query(Rule).all()
    assert len(rules) == 1
    assert rules[0].fr_document_number == "2021-11111"
    assert rules[0].administration == "Biden"


@pytest.mark.integration
def test_ingest_ferc_deduplicates(pg_session):
    for _ in range(2):
        with (
            patch(
                "trace_app.connectors.ferc.FederalRegisterClient.iter_pages",
                return_value=iter([SAMPLE_DOCS]),
            ),
            patch(
                "trace_app.connectors.ferc.fetch_full_texts_concurrent",
                new=AsyncMock(return_value={"2021-11111": "Full text of the rule."}),
            ),
            patch(
                "trace_app.connectors.ferc.build_engine",
                return_value=pg_session.get_bind(),
            ),
        ):
            ingest_ferc(start_date=date(2021, 1, 1), end_date=date(2021, 12, 31))

    rules = pg_session.query(Rule).all()
    assert len(rules) == 1


@pytest.mark.integration
def test_ingest_ferc_writes_dead_letter_on_error(pg_session):
    with (
        patch(
            "trace_app.connectors.ferc.FederalRegisterClient.iter_pages",
            return_value=iter([SAMPLE_DOCS]),
        ),
        patch(
            "trace_app.connectors.ferc.fetch_full_texts_concurrent",
            new=AsyncMock(return_value={"2021-11111": Exception("Connection timeout")}),
        ),
        patch(
            "trace_app.connectors.ferc.build_engine",
            return_value=pg_session.get_bind(),
        ),
    ):
        ingest_ferc(start_date=date(2021, 1, 1), end_date=date(2021, 12, 31))

    rules = pg_session.query(Rule).all()
    dead = pg_session.query(DeadLetter).all()
    assert len(rules) == 0
    assert len(dead) == 1
    assert "Connection timeout" in dead[0].error_message


@pytest.mark.integration
def test_ingest_ferc_concurrent_inserts_rules(pg_session):
    with (
        patch(
            "trace_app.connectors.ferc.FederalRegisterClient.iter_pages",
            return_value=iter([SAMPLE_DOCS]),
        ),
        patch(
            "trace_app.connectors.ferc.fetch_full_texts_concurrent",
            new=AsyncMock(return_value={"2021-11111": "Full text of the rule."}),
        ),
        patch(
            "trace_app.connectors.ferc.build_engine",
            return_value=pg_session.get_bind(),
        ),
    ):
        ingest_ferc(start_date=date(2021, 1, 1), end_date=date(2021, 12, 31), concurrency=5)

    rules = pg_session.query(Rule).all()
    assert len(rules) == 1
    assert rules[0].fr_document_number == "2021-11111"
    assert rules[0].administration == "Biden"

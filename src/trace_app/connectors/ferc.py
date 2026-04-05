"""Prefect flow for ingesting FERC documents from the Federal Register."""

import json
from datetime import date

import structlog
from prefect import flow

from trace_app.config import Settings
from trace_app.connectors.federal_register import FederalRegisterClient
from trace_app.processing.rules import parse_fr_document
from trace_app.storage.database import build_engine, build_session_factory
from trace_app.storage.ingest import save_dead_letter, save_rule

logger = structlog.get_logger()


@flow(name="ingest_ferc", log_prints=True)
def ingest_ferc(
    start_date: date = date(2017, 1, 20),
    end_date: date | None = None,
) -> None:
    """Ingest FERC documents from the Federal Register for the given date range."""
    if end_date is None:
        end_date = date.today()
    settings = Settings()  # ty: ignore[missing-argument]
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    client = FederalRegisterClient()

    inserted = 0
    skipped = 0
    failed = 0

    session = session_factory()
    try:
        for doc in client.iter_documents(start_date, end_date):
            doc_number = doc.get("document_number", "unknown")
            try:
                body_html_url = doc.get("body_html_url")
                if not body_html_url:
                    raise ValueError(f"No body_html_url for document {doc_number}")
                full_text = client.fetch_full_text(body_html_url)
                rule = parse_fr_document(doc, full_text)
                if save_rule(session, rule):
                    inserted += 1
                    logger.info("rule.inserted", document_number=doc_number)
                else:
                    skipped += 1
                    logger.debug("rule.duplicate", document_number=doc_number)
                session.commit()
            except Exception as exc:
                logger.warning("rule.failed", document_number=doc_number, error=str(exc))
                save_dead_letter(
                    session,
                    source_url=doc.get("html_url", ""),
                    raw_payload=json.dumps(doc),
                    error_message=str(exc),
                )
                session.commit()
                failed += 1
    finally:
        session.close()

    logger.info("ingest.complete", inserted=inserted, skipped=skipped, failed=failed)


if __name__ == "__main__":
    ingest_ferc()

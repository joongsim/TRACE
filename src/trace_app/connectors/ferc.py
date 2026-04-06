"""Prefect flow for ingesting FERC documents from the Federal Register."""

import asyncio
import json
from datetime import date

from prefect import flow

from trace_app.config import Settings
from trace_app.connectors.federal_register import (
    FederalRegisterClient,
    fetch_full_texts_concurrent,
)
from trace_app.processing.rules import parse_fr_document
from trace_app.storage.database import build_engine, build_session_factory
from trace_app.storage.ingest import save_dead_letter, save_rule


@flow(name="ingest_ferc", log_prints=True)
def ingest_ferc(
    start_date: date = date(2025, 1, 1),
    end_date: date | None = None,
    concurrency: int = 10,
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
        for page_docs in client.iter_pages(start_date, end_date):
            results = asyncio.run(fetch_full_texts_concurrent(page_docs, concurrency))
            for doc in page_docs:
                doc_number = doc.get("document_number", "unknown")
                print(
                    f"processing {doc_number} "
                    f"(inserted={inserted} skipped={skipped} failed={failed})"
                )
                full_text = results.get(doc_number)
                if isinstance(full_text, BaseException):
                    print(f"  failed {doc_number}: {full_text}")
                    save_dead_letter(
                        session,
                        source_url=doc.get("html_url", ""),
                        raw_payload=json.dumps(doc),
                        error_message=str(full_text),
                    )
                    session.commit()
                    failed += 1
                else:
                    try:
                        rule = parse_fr_document(doc, full_text or "")
                        if save_rule(session, rule):
                            inserted += 1
                            print(f"  inserted {doc_number}")
                        else:
                            skipped += 1
                        session.commit()
                    except Exception as exc:
                        print(f"  failed {doc_number}: {exc}")
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

    print(f"ingest complete: inserted={inserted} skipped={skipped} failed={failed}")


if __name__ == "__main__":
    ingest_ferc()

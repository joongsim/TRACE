"""Prefect flow for ingesting Federal Register documents."""

import asyncio
import json
from datetime import date

from prefect import flow

from trace_app.config import Settings
from trace_app.connectors.federal_register import (
    DOE,
    FERC,
    AgencyConfig,
    FederalRegisterClient,
    fetch_full_texts_concurrent,
)
from trace_app.processing.rules import parse_fr_document
from trace_app.storage.database import build_engine, build_session_factory
from trace_app.storage.ingest import save_dead_letter, save_rule


@flow(name="ingest_fr", log_prints=True)
def ingest_fr(
    config: AgencyConfig = FERC,
    start_date: date = date(2025, 1, 1),
    end_date: date | None = None,
    concurrency: int = 10,
) -> None:
    """Ingest Federal Register documents for the given agency config and date range."""
    if end_date is None:
        end_date = date.today()
    settings = Settings()  # ty: ignore[missing-argument]
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    client = FederalRegisterClient()

    inserted = 0
    updated = 0
    failed = 0

    session = session_factory()
    try:
        for page_docs in client.iter_pages(config, start_date, end_date):
            results = asyncio.run(fetch_full_texts_concurrent(page_docs, concurrency))
            for doc in page_docs:
                doc_number = doc.get("document_number", "unknown")
                print(
                    f"processing {doc_number} "
                    f"(inserted={inserted} updated={updated} failed={failed})"
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
                        assert isinstance(full_text, str)
                        rule = parse_fr_document(doc, full_text)
                        if save_rule(session, rule):
                            inserted += 1
                            print(f"  inserted {doc_number}")
                        else:
                            updated += 1
                            print(f"  updated {doc_number}")
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

    print(f"ingest complete: inserted={inserted} updated={updated} failed={failed}")


if __name__ == "__main__":
    import argparse

    _PRESETS = {"FERC": FERC, "DOE": DOE}
    parser = argparse.ArgumentParser()
    parser.add_argument("--agency", choices=_PRESETS, default="FERC")
    args = parser.parse_args()
    ingest_fr(config=_PRESETS[args.agency])

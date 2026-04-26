"""Prefect flow for ingesting Federal Register documents."""

import asyncio
import json
from datetime import date

from prefect import flow

from trace_app.config import Settings
from trace_app.connectors.embed import embed_rules
from trace_app.connectors.federal_register import (
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
            results = asyncio.run(
                fetch_full_texts_concurrent(
                    page_docs,
                    concurrency,
                    docling_url=settings.docling_url,
                )
            )
            for doc in page_docs:
                doc_number = doc.get("document_number", "unknown")
                print(
                    f"processing {doc_number} "
                    f"(inserted={inserted} updated={updated} failed={failed})"
                )
                result = results.get(doc_number)
                if not isinstance(result, tuple):
                    err: BaseException = (
                        result
                        if isinstance(result, BaseException)
                        else RuntimeError(f"no result for {doc_number}")
                    )
                    print(f"  failed {doc_number}: {err}")
                    save_dead_letter(
                        session,
                        source_url=doc.get("html_url", ""),
                        raw_payload=json.dumps(doc),
                        error_message=str(err),
                    )
                    session.commit()
                    failed += 1
                else:
                    try:
                        full_text, text_source = result
                        rule = parse_fr_document(doc, full_text, text_source, agency=config.name)
                        if save_rule(session, rule):
                            inserted += 1
                            print(f"  inserted {doc_number} ({text_source})")
                        else:
                            updated += 1
                            print(f"  updated {doc_number} ({text_source})")
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

    try:
        embed_rules()
    except Exception as exc:
        print(f"embedding failed (ingestion still succeeded): {exc}")


if __name__ == "__main__":
    import argparse
    import inspect

    import trace_app.connectors.federal_register as _fr

    _PRESETS = {
        name: obj for name, obj in inspect.getmembers(_fr) if isinstance(obj, AgencyConfig)
    }
    parser = argparse.ArgumentParser()
    parser.add_argument("--agency", choices=_PRESETS, default="FERC")
    args = parser.parse_args()
    ingest_fr(config=_PRESETS[args.agency])

"""Prefect flow to backfill existing rules with PDF text via docling-serve."""

import asyncio

from prefect import flow
from sqlalchemy import select

from trace_app.config import Settings
from trace_app.connectors.federal_register import (
    FederalRegisterClient,
    fetch_full_texts_concurrent,
)
from trace_app.storage.database import build_engine, build_session_factory
from trace_app.storage.ingest import save_dead_letter, update_rule_text
from trace_app.storage.models import Rule


@flow(name="backfill_fr", log_prints=True)
def backfill_fr(
    docling_url: str | None = None,
    concurrency: int = 10,
    batch_size: int = 50,
) -> None:
    """Re-fetch full text for rules not yet converted via docling."""
    settings = Settings()  # ty: ignore[missing-argument]
    if docling_url is None:
        docling_url = settings.docling_url
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    client = FederalRegisterClient()

    updated = 0
    failed = 0

    session = session_factory()
    try:
        rules = (
            session.execute(
                select(Rule)
                .where(Rule.text_source != "pdf_docling")
                .where(Rule.fr_document_number.isnot(None))
            )
            .scalars()
            .all()
        )
        print(f"found {len(rules)} rules to backfill")

        for i in range(0, len(rules), batch_size):
            batch = rules[i : i + batch_size]
            doc_numbers = [r.fr_document_number for r in batch if r.fr_document_number]

            try:
                docs = client.fetch_documents_by_numbers(doc_numbers)
            except Exception as exc:
                print(f"  failed to fetch batch {i}–{i + len(batch)}: {exc}")
                failed += len(batch)
                continue

            results = asyncio.run(
                fetch_full_texts_concurrent(docs, concurrency, docling_url=docling_url)
            )

            for doc in docs:
                doc_number = doc.get("document_number", "unknown")
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
                        raw_payload=doc_number,
                        error_message=str(err),
                    )
                    session.commit()
                    failed += 1
                else:
                    full_text, text_source = result
                    update_rule_text(session, doc_number, full_text, text_source)
                    session.commit()
                    updated += 1
                    print(f"  updated {doc_number} ({text_source})")
    finally:
        session.close()

    print(f"backfill complete: updated={updated} failed={failed}")


if __name__ == "__main__":
    backfill_fr()

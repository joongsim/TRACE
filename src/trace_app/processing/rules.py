"""Parsing and processing logic for Federal Register documents."""

import hashlib
from datetime import UTC, date, datetime

from trace_app.storage.models import Rule

ADMINISTRATION_RANGES: list[tuple[date, str]] = [
    (date(2009, 1, 20), "Obama"),
    (date(2017, 1, 20), "Trump 1"),
    (date(2021, 1, 20), "Biden"),
    (date(2025, 1, 20), "Trump 2"),
]


def get_administration(pub_date: date) -> str:
    """Return the US administration name for a given publication date."""
    admin = "Unknown"
    for start_date, name in ADMINISTRATION_RANGES:
        if pub_date >= start_date:
            admin = name
        else:
            break
    return admin


def compute_content_hash(fr_document_number: str, full_text: str) -> str:
    """SHA-256 of document number concatenated with full text."""
    return hashlib.sha256((fr_document_number + full_text).encode()).hexdigest()


def parse_fr_document(doc: dict, full_text: str, text_source: str = "html_fallback") -> Rule:
    """Parse a Federal Register API document dict into a Rule ORM instance."""
    pub_date = date.fromisoformat(doc["publication_date"])
    effective_date = date.fromisoformat(doc["effective_on"]) if doc.get("effective_on") else None

    cfr_refs = doc.get("cfr_references", [])
    cfr_sections = [f"{ref['title']} C.F.R. § {ref['part']}" for ref in cfr_refs] or None

    doc_number = doc["document_number"]

    return Rule(
        title=doc["title"],
        abstract=doc.get("abstract"),
        full_text=full_text,
        publication_date=pub_date,
        effective_date=effective_date,
        agency="FERC",
        document_type=doc["type"].upper().replace(" ", "_"),
        cfr_sections=cfr_sections,
        administration=get_administration(pub_date),
        fr_url=doc["html_url"],
        fr_document_number=doc_number,
        content_hash=compute_content_hash(doc_number, full_text),
        ingested_at=datetime.now(UTC),
        text_source=text_source,
    )

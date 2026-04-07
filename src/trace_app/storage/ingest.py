"""Storage helpers for rule ingestion."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from trace_app.storage.models import DeadLetter, Rule


def save_rule(session: Session, rule: Rule) -> bool:
    """Upsert a Rule by fr_document_number. Returns True if inserted, False if updated."""
    existing = session.execute(
        select(Rule).where(Rule.fr_document_number == rule.fr_document_number)
    ).scalar_one_or_none()

    if existing is None:
        session.add(rule)
        session.flush()
        return True

    existing.full_text = rule.full_text
    existing.content_hash = rule.content_hash
    existing.abstract = rule.abstract
    existing.ingested_at = rule.ingested_at
    existing.text_source = rule.text_source
    session.flush()
    return False


def save_dead_letter(
    session: Session,
    source_url: str,
    raw_payload: str,
    error_message: str,
) -> None:
    """Persist a failed ingestion record to dead_letters."""
    dead = DeadLetter(
        source_url=source_url,
        raw_payload=raw_payload,
        error_message=error_message,
        failed_at=datetime.now(UTC),
    )
    session.add(dead)
    session.flush()

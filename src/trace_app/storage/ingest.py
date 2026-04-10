"""Storage helpers for rule ingestion."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
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


def update_rule_text(
    session: Session,
    fr_document_number: str,
    full_text: str,
    text_source: str,
) -> None:
    """Update full_text, text_source, and content_hash on an existing rule."""
    from trace_app.processing.rules import compute_content_hash

    rule = session.execute(
        select(Rule).where(Rule.fr_document_number == fr_document_number)
    ).scalar_one()
    rule.full_text = full_text
    rule.text_source = text_source
    rule.content_hash = compute_content_hash(fr_document_number, full_text)
    rule.ingested_at = datetime.now(UTC)
    session.flush()


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


def save_embeddings(
    session: Session,
    rule_ids: list[uuid.UUID],
    vectors: list[list[float]],
) -> None:
    """Bulk-update embedding on a batch of rules."""
    for rule_id, vector in zip(rule_ids, vectors, strict=True):
        session.execute(update(Rule).where(Rule.rule_id == rule_id).values(embedding=vector))
    session.flush()

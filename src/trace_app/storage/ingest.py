"""Storage helpers for rule ingestion."""

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from trace_app.storage.models import DeadLetter, Rule


def save_rule(session: Session, rule: Rule) -> bool:
    """Persist a Rule, skipping duplicates by content_hash. Returns True if inserted."""
    try:
        session.begin_nested()
        session.add(rule)
        session.flush()
        return True
    except IntegrityError:
        session.rollback()
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

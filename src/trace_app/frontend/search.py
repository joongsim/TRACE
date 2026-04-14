"""Search and rule retrieval — framework-agnostic, no Streamlit imports."""

import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from trace_app.storage.models import Rule


def _rule_to_dict(rule: Rule) -> dict:
    return {
        "rule_id": rule.rule_id,
        "title": rule.title,
        "abstract": rule.abstract,
        "full_text": rule.full_text,
        "publication_date": rule.publication_date,
        "effective_date": rule.effective_date,
        "agency": rule.agency,
        "document_type": rule.document_type,
        "cfr_sections": rule.cfr_sections,
        "administration": rule.administration,
        "fr_url": rule.fr_url,
        "fr_document_number": rule.fr_document_number,
        "text_source": rule.text_source,
    }


def get_rule(session: Session, rule_id: uuid.UUID) -> dict | None:
    """Fetch a single rule by ID. Returns dict or None."""
    rule = session.execute(select(Rule).where(Rule.rule_id == rule_id)).scalar_one_or_none()
    if rule is None:
        return None
    return _rule_to_dict(rule)


def search_rules(
    session: Session,
    query: str,
    filters: dict,
    limit: int = 20,
) -> list[dict]:
    """Keyword search on title+abstract with optional filters."""
    stmt = select(Rule)

    if query.strip():
        pattern = f"%{query.strip()}%"
        stmt = stmt.where(
            or_(
                Rule.title.ilike(pattern),
                Rule.abstract.ilike(pattern),
            )
        )

    if admins := filters.get("administration"):
        stmt = stmt.where(Rule.administration.in_(admins))

    if doc_types := filters.get("document_type"):
        stmt = stmt.where(Rule.document_type.in_(doc_types))

    if date_from := filters.get("date_from"):
        stmt = stmt.where(Rule.publication_date >= date_from)

    if date_to := filters.get("date_to"):
        stmt = stmt.where(Rule.publication_date <= date_to)

    stmt = stmt.order_by(Rule.publication_date.desc()).limit(limit)
    rules = session.execute(stmt).scalars().all()
    return [_rule_to_dict(r) for r in rules]

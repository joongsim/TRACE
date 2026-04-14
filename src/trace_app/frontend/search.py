"""Search and rule retrieval — framework-agnostic, no Streamlit imports."""

import uuid

from sqlalchemy import select
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

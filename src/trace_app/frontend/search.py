"""Search and rule retrieval — framework-agnostic, no Streamlit imports."""

import uuid
from collections.abc import Callable

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


def search_rules_hybrid(
    session: Session,
    query: str,
    filters: dict,
    embed_fn: Callable[[str], list[float]],
    limit: int = 20,
) -> list[dict]:
    """Hybrid search: union of keyword ILIKE + pgvector cosine similarity.

    Results are deduped by rule_id, keeping the higher-ranked occurrence.
    """
    keyword_results = search_rules(session, query, filters, limit=limit)

    semantic_results: list[dict] = []
    if query.strip():
        query_embedding = embed_fn(query.strip())
        stmt = select(Rule).where(Rule.embedding.isnot(None))

        if admins := filters.get("administration"):
            stmt = stmt.where(Rule.administration.in_(admins))
        if doc_types := filters.get("document_type"):
            stmt = stmt.where(Rule.document_type.in_(doc_types))
        if date_from := filters.get("date_from"):
            stmt = stmt.where(Rule.publication_date >= date_from)
        if date_to := filters.get("date_to"):
            stmt = stmt.where(Rule.publication_date <= date_to)

        stmt = stmt.order_by(Rule.embedding.cosine_distance(query_embedding)).limit(limit)

        rules = session.execute(stmt).scalars().all()
        semantic_results = [_rule_to_dict(r) for r in rules]

    # Union + dedupe: keyword results first, then semantic results for new rule_ids
    seen_ids = set()
    merged = []
    for r in keyword_results + semantic_results:
        if r["rule_id"] not in seen_ids:
            seen_ids.add(r["rule_id"])
            merged.append(r)

    return merged[:limit]

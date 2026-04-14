"""Administration comparison queries — framework-agnostic, no Streamlit imports."""

from collections import defaultdict
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from trace_app.storage.models import Rule

ADMIN_SPANS = [
    {"name": "Obama", "start": date(2009, 1, 20), "end": date(2017, 1, 19)},
    {"name": "Trump 1", "start": date(2017, 1, 20), "end": date(2021, 1, 19)},
    {"name": "Biden", "start": date(2021, 1, 20), "end": date(2025, 1, 19)},
    {"name": "Trump 2", "start": date(2025, 1, 20), "end": date(2029, 1, 19)},
]


def get_admin_comparison(session: Session) -> dict:
    """Return rule counts and breakdowns by administration.

    Returns:
        {
            "counts_by_admin": {"Biden": 42, ...},
            "counts_by_admin_type": {("Biden", "RULE"): 30, ...},
            "admin_spans": [{"name": ..., "start": ..., "end": ...}, ...],
        }
    """
    rows = session.execute(
        select(
            Rule.administration,
            Rule.document_type,
            func.count().label("cnt"),
        ).group_by(Rule.administration, Rule.document_type)
    ).all()

    counts_by_admin: dict[str, int] = defaultdict(int)
    counts_by_admin_type: dict[tuple[str, str], int] = {}

    for admin, doc_type, cnt in rows:
        counts_by_admin[admin] += cnt
        counts_by_admin_type[(admin, doc_type)] = cnt

    return {
        "counts_by_admin": dict(counts_by_admin),
        "counts_by_admin_type": counts_by_admin_type,
        "admin_spans": ADMIN_SPANS,
    }

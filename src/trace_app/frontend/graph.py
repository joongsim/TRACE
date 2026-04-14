"""Citation graph queries — stubs pending citation graph implementation."""

import uuid

from sqlalchemy.orm import Session


def get_citation_subgraph(session: Session, rule_id: uuid.UUID) -> dict:
    """Return 1-hop citation subgraph for a rule. Stub."""
    return {"stub": True}


def get_full_graph(session: Session) -> dict:
    """Return the full citation graph. Stub."""
    return {"stub": True}

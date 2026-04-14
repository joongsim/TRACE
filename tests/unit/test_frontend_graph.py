"""Unit tests for graph stubs."""

import uuid


def test_get_citation_subgraph_returns_stub(sqlite_session):
    from trace_app.frontend.graph import get_citation_subgraph

    result = get_citation_subgraph(sqlite_session, uuid.uuid4())
    assert result == {"stub": True}


def test_get_full_graph_returns_stub(sqlite_session):
    from trace_app.frontend.graph import get_full_graph

    result = get_full_graph(sqlite_session)
    assert result == {"stub": True}

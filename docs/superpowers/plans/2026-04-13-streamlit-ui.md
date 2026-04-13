# Streamlit UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a browser interface for searching FERC rules, viewing rule details, and comparing administrations. Citation graph views are stubbed.

**Architecture:** Framework-agnostic data layer in `src/trace_app/frontend/` (no Streamlit imports) with a thin Streamlit rendering shell in `app.py`. All DB access through SQLAlchemy sessions. Plotly for charts.

**Tech Stack:** Streamlit, Plotly, SQLAlchemy, pgvector, sentence-transformers (`all-MiniLM-L6-v2`)

---

### Task 1: Add Streamlit and Plotly dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add dependencies to pyproject.toml**

Add `streamlit` and `plotly` to the `dependencies` list in `pyproject.toml`:

```toml
"plotly>=6.0,<7.0",
"streamlit>=1.40,<2.0",
```

Add them after the existing `prefect` line, keeping alphabetical order within the block.

- [ ] **Step 2: Sync the environment**

Run:
```bash
uv sync --all-extras
```
Expected: resolves and installs streamlit, plotly, and their transitive deps without conflicts.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add streamlit and plotly dependencies"
```

---

### Task 2: Implement `frontend/search.py` — `get_rule()`

**Files:**
- Create: `src/trace_app/frontend/search.py`
- Create: `tests/unit/test_frontend_search.py`

- [ ] **Step 1: Create test file with helper and first test**

Create `tests/unit/test_frontend_search.py`:

```python
"""Unit tests for frontend search functions (SQLite)."""

import uuid
from datetime import UTC, date, datetime

from trace_app.storage.models import Rule


def _make_rule(**overrides) -> Rule:
    defaults = dict(
        rule_id=uuid.uuid4(),
        title="Test Rule",
        abstract="An abstract about electricity markets.",
        full_text="Full body text about FERC regulations.",
        publication_date=date(2021, 6, 1),
        agency="FERC",
        document_type="RULE",
        administration="Biden",
        fr_url="https://www.federalregister.gov/documents/2021/06/01/2021-11111/test",
        fr_document_number="2021-11111",
        content_hash="abc123",
        ingested_at=datetime.now(UTC),
        text_source="html_fallback",
    )
    defaults.update(overrides)
    return Rule(**defaults)


def test_get_rule_returns_matching_rule(sqlite_session):
    rule = _make_rule()
    sqlite_session.add(rule)
    sqlite_session.flush()

    from trace_app.frontend.search import get_rule

    result = get_rule(sqlite_session, rule.rule_id)
    assert result is not None
    assert result["title"] == "Test Rule"
    assert result["rule_id"] == rule.rule_id


def test_get_rule_returns_none_for_missing_id(sqlite_session):
    from trace_app.frontend.search import get_rule

    result = get_rule(sqlite_session, uuid.uuid4())
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_frontend_search.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trace_app.frontend.search'`

- [ ] **Step 3: Implement `get_rule`**

Create `src/trace_app/frontend/search.py`:

```python
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
    rule = session.execute(
        select(Rule).where(Rule.rule_id == rule_id)
    ).scalar_one_or_none()
    if rule is None:
        return None
    return _rule_to_dict(rule)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_frontend_search.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/trace_app/frontend/search.py tests/unit/test_frontend_search.py
git commit -m "feat: add get_rule() to frontend search module"
```

---

### Task 3: Implement `frontend/search.py` — `search_rules()`

**Files:**
- Modify: `src/trace_app/frontend/search.py`
- Modify: `tests/unit/test_frontend_search.py`

This task implements keyword search only (ILIKE on title+abstract). The pgvector cosine similarity path requires Postgres and is added in Task 7 (integration test).

- [ ] **Step 1: Add tests for keyword search**

Append to `tests/unit/test_frontend_search.py`:

```python
def test_search_rules_keyword_matches_title(sqlite_session):
    rule = _make_rule(title="Electricity Transmission Rates")
    sqlite_session.add(rule)
    sqlite_session.flush()

    from trace_app.frontend.search import search_rules

    results = search_rules(sqlite_session, query="transmission", filters={})
    assert len(results) == 1
    assert results[0]["title"] == "Electricity Transmission Rates"


def test_search_rules_keyword_matches_abstract(sqlite_session):
    rule = _make_rule(abstract="Wholesale electricity market reform")
    sqlite_session.add(rule)
    sqlite_session.flush()

    from trace_app.frontend.search import search_rules

    results = search_rules(sqlite_session, query="wholesale", filters={})
    assert len(results) == 1


def test_search_rules_no_match_returns_empty(sqlite_session):
    rule = _make_rule()
    sqlite_session.add(rule)
    sqlite_session.flush()

    from trace_app.frontend.search import search_rules

    results = search_rules(sqlite_session, query="nonexistent_xyz", filters={})
    assert results == []


def test_search_rules_filters_by_administration(sqlite_session):
    r1 = _make_rule(
        administration="Biden",
        fr_document_number="2021-11111",
        content_hash="hash1",
    )
    r2 = _make_rule(
        administration="Trump 1",
        fr_document_number="2019-22222",
        content_hash="hash2",
        title="Another Rule",
    )
    sqlite_session.add_all([r1, r2])
    sqlite_session.flush()

    from trace_app.frontend.search import search_rules

    results = search_rules(
        sqlite_session,
        query="rule",
        filters={"administration": ["Biden"]},
    )
    assert len(results) == 1
    assert results[0]["administration"] == "Biden"


def test_search_rules_filters_by_document_type(sqlite_session):
    r1 = _make_rule(
        document_type="RULE",
        fr_document_number="2021-11111",
        content_hash="hash1",
    )
    r2 = _make_rule(
        document_type="NOTICE",
        fr_document_number="2021-22222",
        content_hash="hash2",
        title="A Notice",
    )
    sqlite_session.add_all([r1, r2])
    sqlite_session.flush()

    from trace_app.frontend.search import search_rules

    results = search_rules(
        sqlite_session,
        query="",
        filters={"document_type": ["RULE"]},
    )
    assert len(results) == 1
    assert results[0]["document_type"] == "RULE"


def test_search_rules_empty_query_returns_all(sqlite_session):
    r1 = _make_rule(fr_document_number="2021-11111", content_hash="hash1")
    r2 = _make_rule(
        fr_document_number="2021-22222",
        content_hash="hash2",
        title="Second Rule",
    )
    sqlite_session.add_all([r1, r2])
    sqlite_session.flush()

    from trace_app.frontend.search import search_rules

    results = search_rules(sqlite_session, query="", filters={})
    assert len(results) == 2
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `uv run pytest tests/unit/test_frontend_search.py -v`
Expected: new tests FAIL with `ImportError` or `AttributeError` (search_rules not defined)

- [ ] **Step 3: Implement `search_rules`**

Add to `src/trace_app/frontend/search.py`:

```python
from sqlalchemy import or_


def search_rules(
    session: Session,
    query: str,
    filters: dict,
    limit: int = 20,
) -> list[dict]:
    """Keyword search on title+abstract with optional filters.

    Semantic search (pgvector cosine similarity) is added when an embed_fn
    is provided — see search_rules_hybrid() for the full hybrid path.
    """
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_frontend_search.py -v`
Expected: all 8 passed

- [ ] **Step 5: Commit**

```bash
git add src/trace_app/frontend/search.py tests/unit/test_frontend_search.py
git commit -m "feat: add search_rules() with keyword search and filters"
```

---

### Task 4: Implement `frontend/comparison.py`

**Files:**
- Create: `src/trace_app/frontend/comparison.py`
- Create: `tests/unit/test_frontend_comparison.py`

- [ ] **Step 1: Write tests**

Create `tests/unit/test_frontend_comparison.py`:

```python
"""Unit tests for administration comparison functions (SQLite)."""

import uuid
from datetime import UTC, date, datetime

from trace_app.storage.models import Rule


def _make_rule(**overrides) -> Rule:
    defaults = dict(
        rule_id=uuid.uuid4(),
        title="Test Rule",
        abstract="Abstract text.",
        full_text="Full body text.",
        publication_date=date(2021, 6, 1),
        agency="FERC",
        document_type="RULE",
        administration="Biden",
        fr_url="https://www.federalregister.gov/documents/2021/06/01/2021-11111/test",
        fr_document_number="2021-11111",
        content_hash="abc123",
        ingested_at=datetime.now(UTC),
        text_source="html_fallback",
    )
    defaults.update(overrides)
    return Rule(**defaults)


def test_get_admin_comparison_empty_db(sqlite_session):
    from trace_app.frontend.comparison import get_admin_comparison

    result = get_admin_comparison(sqlite_session)
    assert result["counts_by_admin"] == {}
    assert result["counts_by_admin_type"] == {}


def test_get_admin_comparison_counts_by_admin(sqlite_session):
    r1 = _make_rule(
        administration="Biden",
        fr_document_number="2021-11111",
        content_hash="h1",
    )
    r2 = _make_rule(
        administration="Biden",
        fr_document_number="2021-22222",
        content_hash="h2",
        document_type="NOTICE",
    )
    r3 = _make_rule(
        administration="Trump 1",
        fr_document_number="2019-33333",
        content_hash="h3",
    )
    sqlite_session.add_all([r1, r2, r3])
    sqlite_session.flush()

    from trace_app.frontend.comparison import get_admin_comparison

    result = get_admin_comparison(sqlite_session)
    assert result["counts_by_admin"]["Biden"] == 2
    assert result["counts_by_admin"]["Trump 1"] == 1


def test_get_admin_comparison_counts_by_admin_type(sqlite_session):
    r1 = _make_rule(
        administration="Biden",
        document_type="RULE",
        fr_document_number="2021-11111",
        content_hash="h1",
    )
    r2 = _make_rule(
        administration="Biden",
        document_type="NOTICE",
        fr_document_number="2021-22222",
        content_hash="h2",
    )
    sqlite_session.add_all([r1, r2])
    sqlite_session.flush()

    from trace_app.frontend.comparison import get_admin_comparison

    result = get_admin_comparison(sqlite_session)
    assert result["counts_by_admin_type"][("Biden", "RULE")] == 1
    assert result["counts_by_admin_type"][("Biden", "NOTICE")] == 1


def test_get_admin_comparison_includes_admin_spans(sqlite_session):
    from trace_app.frontend.comparison import get_admin_comparison

    result = get_admin_comparison(sqlite_session)
    spans = result["admin_spans"]
    assert len(spans) == 4
    assert spans[0]["name"] == "Obama"
    assert spans[-1]["name"] == "Trump 2"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_frontend_comparison.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `get_admin_comparison`**

Create `src/trace_app/frontend/comparison.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_frontend_comparison.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/trace_app/frontend/comparison.py tests/unit/test_frontend_comparison.py
git commit -m "feat: add get_admin_comparison() for administration comparison view"
```

---

### Task 5: Implement `frontend/graph.py` — stubs

**Files:**
- Create: `src/trace_app/frontend/graph.py`
- Create: `tests/unit/test_frontend_graph.py`

- [ ] **Step 1: Write tests**

Create `tests/unit/test_frontend_graph.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_frontend_graph.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement stubs**

Create `src/trace_app/frontend/graph.py`:

```python
"""Citation graph queries — stubs pending citation graph implementation."""

import uuid

from sqlalchemy.orm import Session


def get_citation_subgraph(session: Session, rule_id: uuid.UUID) -> dict:
    """Return 1-hop citation subgraph for a rule. Stub."""
    return {"stub": True}


def get_full_graph(session: Session) -> dict:
    """Return the full citation graph. Stub."""
    return {"stub": True}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_frontend_graph.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/trace_app/frontend/graph.py tests/unit/test_frontend_graph.py
git commit -m "feat: add stubbed citation graph functions"
```

---

### Task 6: Build `app.py` — Streamlit rendering shell

**Files:**
- Create: `app.py` (project root)

This is the Streamlit entry point. It imports the `frontend/` data layer functions and renders results using `st.*` calls. No unit tests — this is pure rendering.

- [ ] **Step 1: Create `app.py`**

Create `app.py` at the project root:

```python
"""TRACE — Streamlit UI shell. All data logic lives in trace_app.frontend."""

import uuid

import plotly.graph_objects as go
import streamlit as st
from sentence_transformers import SentenceTransformer
from sqlalchemy.orm import Session

from trace_app.config import Settings
from trace_app.frontend.comparison import get_admin_comparison
from trace_app.frontend.graph import get_citation_subgraph, get_full_graph
from trace_app.frontend.search import get_rule, search_rules
from trace_app.storage.database import build_engine, build_session_factory

ADMIN_COLORS = {
    "Obama": "#89b4fa",
    "Trump 1": "#fab387",
    "Biden": "#a6e3a1",
    "Trump 2": "#f38ba8",
}

DOC_TYPE_COLORS = {
    "RULE": "#89b4fa",
    "PROPOSED_RULE": "#a6e3a1",
    "NOTICE": "#f9e2af",
}


@st.cache_resource
def _get_session_factory():
    settings = Settings()
    engine = build_engine(settings.database_url)
    return build_session_factory(engine)


@st.cache_resource
def _get_embed_model():
    settings = Settings()
    return SentenceTransformer(settings.embedding_model)


def _get_session() -> Session:
    factory = _get_session_factory()
    return factory()


# --- Sidebar navigation ---

st.set_page_config(page_title="TRACE", layout="wide")

view = st.sidebar.radio(
    "Navigation",
    ["Search", "Rule Detail", "Administration Comparison", "Graph Explorer"],
    index=0,
)

# --- Search view ---

if view == "Search":
    st.title("Search FERC Rules")

    query = st.text_input("Search", placeholder="e.g. electricity transmission rates")

    with st.expander("Filters"):
        col1, col2 = st.columns(2)
        with col1:
            admin_filter = st.multiselect(
                "Administration",
                ["Obama", "Trump 1", "Biden", "Trump 2"],
            )
            doc_type_filter = st.multiselect(
                "Document Type",
                ["RULE", "PROPOSED_RULE", "NOTICE"],
            )
        with col2:
            date_from = st.date_input("From date", value=None)
            date_to = st.date_input("To date", value=None)

    filters: dict = {}
    if admin_filter:
        filters["administration"] = admin_filter
    if doc_type_filter:
        filters["document_type"] = doc_type_filter
    if date_from:
        filters["date_from"] = date_from
    if date_to:
        filters["date_to"] = date_to

    if st.button("Search") or query:
        session = _get_session()
        try:
            results = search_rules(session, query=query, filters=filters)
        finally:
            session.close()

        if not results:
            st.info("No results found.")
        else:
            st.caption(f"{len(results)} results")
            for r in results:
                admin_color = ADMIN_COLORS.get(r["administration"], "#6c7086")
                doc_color = DOC_TYPE_COLORS.get(r["document_type"], "#6c7086")
                with st.container(border=True):
                    col_title, col_badges = st.columns([4, 1])
                    with col_title:
                        if st.button(r["title"], key=str(r["rule_id"])):
                            st.session_state["selected_rule_id"] = str(r["rule_id"])
                            st.session_state["nav_to_detail"] = True
                            st.rerun()
                    with col_badges:
                        st.markdown(
                            f"<span style='background:{admin_color};color:#1e1e2e;"
                            f"padding:2px 8px;border-radius:4px;font-size:0.8em'>"
                            f"{r['administration']}</span> "
                            f"<span style='background:{doc_color};color:#1e1e2e;"
                            f"padding:2px 8px;border-radius:4px;font-size:0.8em'>"
                            f"{r['document_type']}</span>",
                            unsafe_allow_html=True,
                        )
                    if r.get("abstract"):
                        st.caption(r["abstract"][:200] + ("..." if len(r["abstract"] or "") > 200 else ""))
                    meta_parts = [str(r["publication_date"])]
                    if r.get("cfr_sections"):
                        meta_parts.append(" · ".join(r["cfr_sections"]))
                    st.caption(" · ".join(meta_parts))

# --- Rule Detail view ---

elif view == "Rule Detail":
    st.title("Rule Detail")

    rule_id_str = st.session_state.get("selected_rule_id")
    if not rule_id_str:
        st.info("Select a rule from the Search view to see its details.")
    else:
        session = _get_session()
        try:
            rule = get_rule(session, uuid.UUID(rule_id_str))
        finally:
            session.close()

        if rule is None:
            st.error("Rule not found.")
        else:
            st.header(rule["title"])

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Date", str(rule["publication_date"]))
            col2.metric("Administration", rule["administration"])
            col3.metric("Type", rule["document_type"])
            col4.markdown(f"[Federal Register]({rule['fr_url']})")

            if rule.get("cfr_sections"):
                st.markdown("**CFR Sections:** " + ", ".join(rule["cfr_sections"]))

            if rule.get("abstract"):
                st.subheader("Abstract")
                st.write(rule["abstract"])

            with st.expander("Full Text"):
                st.write(rule["full_text"])

            st.subheader("Citation Graph")
            st.info("Citation graph coming soon — pending citation extraction implementation.")

# --- Administration Comparison view ---

elif view == "Administration Comparison":
    st.title("Administration Comparison")

    session = _get_session()
    try:
        data = get_admin_comparison(session)
    finally:
        session.close()

    if not data["counts_by_admin"]:
        st.info("No rules in the database yet.")
    else:
        # Metric cards
        cols = st.columns(len(data["admin_spans"]))
        for i, span in enumerate(data["admin_spans"]):
            count = data["counts_by_admin"].get(span["name"], 0)
            cols[i].metric(span["name"], count)

        # Stacked bar chart
        admin_names = [s["name"] for s in data["admin_spans"]]
        doc_types = sorted({dt for _, dt in data["counts_by_admin_type"]})

        fig = go.Figure()
        for dt in doc_types:
            counts = [
                data["counts_by_admin_type"].get((admin, dt), 0)
                for admin in admin_names
            ]
            fig.update_layout(barmode="stack")
            fig.add_trace(go.Bar(
                name=dt,
                x=admin_names,
                y=counts,
                marker_color=DOC_TYPE_COLORS.get(dt, "#6c7086"),
            ))
        fig.update_layout(
            title="Rules by Type per Administration",
            barmode="stack",
            xaxis_title="Administration",
            yaxis_title="Count",
        )
        st.plotly_chart(fig, use_container_width=True)

        # Timeline
        fig_timeline = go.Figure()
        for span in data["admin_spans"]:
            count = data["counts_by_admin"].get(span["name"], 0)
            fig_timeline.add_trace(go.Bar(
                name=span["name"],
                x=[(span["end"] - span["start"]).days],
                y=[span["name"]],
                orientation="h",
                marker_color=ADMIN_COLORS.get(span["name"], "#6c7086"),
                text=[f"{count} rules"],
                textposition="inside",
            ))
        fig_timeline.update_layout(
            title="Administration Timeline",
            showlegend=False,
            barmode="stack",
            xaxis_title="Days in Office",
        )
        st.plotly_chart(fig_timeline, use_container_width=True)

        # Topic drift stub
        st.subheader("Topic Drift")
        st.info("Topic drift analysis coming soon — pending embedding centroid computation.")

# --- Graph Explorer view ---

elif view == "Graph Explorer":
    st.title("Graph Explorer")
    st.info(
        "Citation graph coming soon — this view will show the full FERC rule citation "
        "network, filterable by administration and document type."
    )

# --- Handle nav-to-detail redirect ---

if st.session_state.get("nav_to_detail"):
    st.session_state["nav_to_detail"] = False
```

- [ ] **Step 2: Smoke test the app**

Run:
```bash
uv run streamlit run app.py
```

Open the browser URL. Verify:
- Sidebar shows 4 navigation options
- Search view renders with search bar and filter expander
- Administration Comparison shows charts (if DB has data) or "No rules" message
- Rule Detail shows "Select a rule" prompt
- Graph Explorer shows "coming soon" stub

Stop the server with `Ctrl+C`.

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: add Streamlit UI shell with all 4 views"
```

---

### Task 7: Add hybrid search with pgvector (integration test)

**Files:**
- Modify: `src/trace_app/frontend/search.py`
- Create: `tests/integration/test_frontend_search.py`

Keyword search works on SQLite. This task adds the semantic (cosine similarity) path that only works on Postgres+pgvector, behind an optional `embed_fn` parameter.

- [ ] **Step 1: Write integration test**

Create `tests/integration/test_frontend_search.py`:

```python
"""Integration tests for hybrid search (requires Postgres + pgvector)."""

import uuid
from datetime import UTC, date, datetime

import pytest
from sentence_transformers import SentenceTransformer

from trace_app.frontend.search import search_rules_hybrid
from trace_app.storage.models import Rule

model = SentenceTransformer("all-MiniLM-L6-v2")


def _embed(text: str) -> list[float]:
    return model.encode(text).tolist()


def _make_rule(**overrides) -> Rule:
    defaults = dict(
        rule_id=uuid.uuid4(),
        title="Test Rule",
        abstract="An abstract about electricity markets.",
        full_text="Full body text about FERC regulations.",
        publication_date=date(2021, 6, 1),
        agency="FERC",
        document_type="RULE",
        administration="Biden",
        fr_url="https://www.federalregister.gov/documents/2021/06/01/2021-11111/test",
        fr_document_number=f"2021-{uuid.uuid4().hex[:5]}",
        content_hash=uuid.uuid4().hex,
        ingested_at=datetime.now(UTC),
        text_source="html_fallback",
    )
    defaults.update(overrides)
    return Rule(**defaults)


@pytest.mark.integration
def test_hybrid_search_finds_semantic_match(pg_session):
    rule = _make_rule(
        title="Natural Gas Pipeline Safety Standards",
        abstract="Regulations governing the safety of interstate natural gas pipelines.",
        embedding=_embed("Natural Gas Pipeline Safety Standards"),
    )
    pg_session.add(rule)
    pg_session.flush()

    results = search_rules_hybrid(
        pg_session,
        query="pipeline safety regulations",
        filters={},
        embed_fn=_embed,
    )
    assert len(results) >= 1
    assert results[0]["title"] == "Natural Gas Pipeline Safety Standards"


@pytest.mark.integration
def test_hybrid_search_dedupes_keyword_and_semantic(pg_session):
    rule = _make_rule(
        title="Pipeline Safety Standards",
        abstract="Safety standards for natural gas pipelines.",
        embedding=_embed("Pipeline Safety Standards"),
    )
    pg_session.add(rule)
    pg_session.flush()

    results = search_rules_hybrid(
        pg_session,
        query="pipeline safety",
        filters={},
        embed_fn=_embed,
    )
    rule_ids = [r["rule_id"] for r in results]
    assert len(rule_ids) == len(set(rule_ids))
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/integration/test_frontend_search.py -v -m integration`
Expected: FAIL — `ImportError: cannot import name 'search_rules_hybrid'`

- [ ] **Step 3: Implement `search_rules_hybrid`**

Add to `src/trace_app/frontend/search.py`. First, add `Callable` to the imports at the top of the file:

```python
from collections.abc import Callable
```

Then add the function:

```python
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

        stmt = stmt.order_by(
            Rule.embedding.cosine_distance(query_embedding)
        ).limit(limit)

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
```

- [ ] **Step 4: Update `app.py` to use hybrid search**

In `app.py`, update the search section. Replace:

```python
            results = search_rules(session, query=query, filters=filters)
```

With:

```python
            embed_model = _get_embed_model()
            results = search_rules_hybrid(
                session,
                query=query,
                filters=filters,
                embed_fn=lambda text: embed_model.encode(text).tolist(),
            )
```

And update the import at the top of `app.py`:

```python
from trace_app.frontend.search import get_rule, search_rules_hybrid
```

(Remove `search_rules` from the import since `app.py` no longer calls it directly.)

- [ ] **Step 5: Run integration tests**

Run: `uv run pytest tests/integration/test_frontend_search.py -v -m integration`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add src/trace_app/frontend/search.py tests/integration/test_frontend_search.py app.py
git commit -m "feat: add hybrid search with pgvector cosine similarity"
```

---

### Task 8: Update roadmap and final verification

**Files:**
- Modify: `docs/roadmap.md`

- [ ] **Step 1: Update roadmap to reflect phase reordering**

In `docs/roadmap.md`, renumber the phases:
- Phase 3 → Streamlit UI (was Phase 4)
- Phase 4 → Citation Graph (was Phase 3)
- Phase 5 → LangGraph Agent (unchanged)

Mark Phase 3 (Streamlit UI) with ✅.

- [ ] **Step 2: Run full test suite**

Run:
```bash
uv run pytest tests/unit/ -v
```
Expected: all unit tests pass (existing + new).

- [ ] **Step 3: Run linting**

Run:
```bash
uv run ruff check src/ tests/ app.py
uv run ruff format src/ tests/ app.py
```
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add docs/roadmap.md
git commit -m "docs: reorder roadmap phases, mark Streamlit UI complete"
```

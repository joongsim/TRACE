# Streamlit UI Design

## Goal

Browser interface for search, rule detail, citation graph (stubbed), and administration comparison over the FERC rule corpus.

## Architecture

**Entry point:** `app.py` at the project root — thin Streamlit rendering shell, zero business logic.

**Data layer:** `src/trace_app/frontend/` — framework-agnostic query functions returning plain Python dicts/lists. **No Streamlit imports allowed.** This constraint ensures the data layer can be reused with FastHTML, React+FastAPI, or any other frontend.

**DB access:** Single `SessionFactory` via `@st.cache_resource` in `app.py`, passed into frontend functions.

### File layout

```
app.py
src/trace_app/frontend/
  __init__.py
  search.py        # search_rules(), get_rule()
  comparison.py    # get_admin_comparison()
  graph.py         # stub — get_citation_subgraph(), get_full_graph()
```

## Views

### Navigation

Sidebar (`st.sidebar`) with radio selection across 4 views. Persistent left panel.

### Search (default landing page)

- Search bar + button at top
- Collapsible filter expander below bar: agency, document type (multiselect), administration (multiselect), date range
- Hybrid query: keyword `ILIKE` on title+abstract + pgvector cosine similarity on query embedding, results merged and deduped by `rule_id`, top 20
- Results: vertical stack of cards — title, administration badge (color-coded per era), document type badge, date, CFR sections, highlighted abstract snippet
- Clicking a result navigates to Rule Detail via `st.session_state`

### Rule Detail

- Navigated from Search (rule_id in session state) or directly via sidebar
- Title, metadata row (date, administration, document type, CFR sections, FR link)
- Full abstract, full text in expander
- Citation subgraph: **stubbed** — "Citation graph coming soon" placeholder

### Administration Comparison

- Stacked bar chart (Plotly) — rule count by document type per administration
- Row of 4 metric cards — total rule count per administration, color-coded per era
- Topic drift: **stubbed** — "Topic drift analysis coming soon" placeholder
- Timeline: Plotly bar showing each administration's span and rule volume

### Graph Explorer

- Fully **stubbed** — "Citation graph coming soon" placeholder

## Data Layer

### `search.py`

- `search_rules(session, query, filters) -> list[dict]` — ILIKE on title+abstract, pgvector cosine similarity on query embedding, union both result sets, dedupe by `rule_id` keeping the higher-ranked occurrence, return top 20 ordered by combined relevance
- `get_rule(session, rule_id) -> dict` — single rule by ID

### `comparison.py`

- `get_admin_comparison(session) -> dict` — rule counts grouped by administration + document type, plus administration date spans for timeline

### `graph.py`

- `get_citation_subgraph(session, rule_id) -> dict` — stub, returns `{"stub": True}`
- `get_full_graph(session) -> dict` — stub, returns `{"stub": True}`

### Embedding

Query string embedded at search time using `all-MiniLM-L6-v2`, model loaded once via `@st.cache_resource`.

## Key decisions

- Plotly only (no Pyvis) — per CLAUDE.md
- All DB access through SQLAlchemy sessions; no raw SQL in UI layer
- No authentication — internal tool
- `frontend/` module has zero Streamlit imports — pure data/query layer for framework portability
- Citation graph views stubbed pending Phase 3 implementation

## Testing

- Unit tests for all `frontend/` functions using SQLite in-memory
- Test cases: search with no results, keyword-only match, search with filters, `get_rule` valid/missing ID, `get_admin_comparison` with empty DB
- No Streamlit rendering tested — `app.py` is not unit tested
- Integration tests (`@pytest.mark.integration`) for hybrid search against Postgres+pgvector

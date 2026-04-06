# TRACE Roadmap

Regulatory intelligence platform for FERC rulemaking. Ingests the Federal Register, builds a citation graph, and exposes administration-level comparison and natural language querying.

---

## Phases

### Phase 0 — DevOps Foundation ✅
Python package, Docker + Postgres 17/pgvector, Alembic, CI, pre-commit, ORM models (`Rule`, `Edge`, `DeadLetter`).

---

### Phase 1 — Federal Register Connector
**Goal:** Pull FERC documents from the Federal Register API into Postgres with dedup and error resilience.

**Scope:**
- FR API client: paginated fetch by agency (`FERC`) and document type (`RULE`, `PROPOSED_RULE`, `NOTICE`)
- Parse FR JSON → `Rule` ORM instances; map `administration` from publication date ranges
- Dedup via SHA-256 `content_hash` on `(fr_document_number, full_text)`
- Failed records → `DeadLetter` with raw payload and error message
- Prefect flow: `ingest_ferc` with configurable date range, idempotent re-runs
- `make ingest` triggers the flow locally

**Key decisions:**
- Administration date ranges are hardcoded constants (not a DB table) — they change infrequently and need no UI
- `full_text` stores the extracted plain text from FR HTML; abstract stores the FR-provided abstract field

---

### Phase 2 — Embedding Pipeline
**Goal:** Generate and store semantic embeddings for all `Rule` records.

**Scope:**
- `bge-small-en-v1.5` via sentence-transformers, 384d, runs locally (no API calls)
- Embed `title + abstract + full_text[:2048]` — truncated to keep inference fast
- Batch processing: embed rules where `embedding IS NULL`
- Prefect task: runs after ingestion in the same flow
- pgvector `ivfflat` index on `rules.embedding` for ANN search

**Key decisions:**
- Embedding field is nullable so ingestion and embedding are decoupled — connector failures don't block embeddings
- Index created in a migration after first full ingest (requires `lists` parameter tuned to row count)

---

### Phase 3 — Citation Graph
**Goal:** Populate `edges` by extracting rule-to-rule citations from full text.

**Scope:**
- Regex extraction: CFR section references (`18 C.F.R. § 35.28`), FR document numbers (`88 FR 12345`), docket numbers (`RM22-14`)
- Resolve extracted references to `rule_id` values in the DB
- `extraction_method`: `"regex"` or `"llm"` (LLM pass deferred to Phase 6)
- `confidence_score`: 1.0 for exact FR doc number matches, 0.7 for CFR section heuristic
- Prefect task: runs after embedding in the same flow
- NetworkX used for graph analytics (degree centrality, connected components) — computed on read, not stored

**Key decisions:**
- Edges are directional: source cites target
- Unresolved citations are dropped (not stored as dangling edges) — keeps the graph clean

---

### Phase 4 — Streamlit UI
**Goal:** Browser interface for search, rule detail, citation graph, and administration comparison.

**Views:**

1. **Search** — hybrid: keyword (`ILIKE`) + semantic (cosine similarity via pgvector). Filters: agency, document type, administration, date range. Results show title, date, administration badge.

2. **Rule detail** — full text with CFR sections, metadata, 1-hop citation subgraph rendered with Plotly (`go.Scatter` on a force-directed layout via NetworkX spring layout).

3. **Administration comparison** — side-by-side: rule count by type per administration, topic drift via embedding centroid shift, timeline of major rulemakings.

4. **Graph explorer** — full citation graph with Plotly, filterable by administration and document type.

**Key decisions:**
- Plotly only (no Pyvis) — see CLAUDE.md
- All DB access through SQLAlchemy sessions; no raw SQL in UI layer
- No authentication — internal tool

---

### Phase 5 — LangGraph Agent
**Goal:** Natural language querying over the rule corpus via a chat interface in Streamlit.

**Tools available to the agent:**
- `semantic_search(query, k, filters)` — pgvector ANN search
- `get_rule(rule_id)` — fetch full rule text and metadata
- `get_citations(rule_id, direction)` — fetch edges for a rule
- `compare_administrations(topic)` — embedding-based topic comparison across administrations
- `graph_path(source_id, target_id)` — shortest citation path between two rules

**Architecture:**
- LangGraph `StateGraph` with a single `agent` node and tool nodes
- Model: Claude (via Anthropic API) — model ID configured via env var
- State: `messages`, `retrieved_rules`, `graph_context`
- Streamlit `st.chat_message` renders the conversation; tool calls shown as expanders

**Key decisions:**
- Agent has read-only tool access — no mutations
- Context window managed by truncating `full_text` in tool responses to 4096 chars

---

## Data Model Notes

```
rules           — one row per unique FERC document
  administration — derived from publication_date at ingest time
  content_hash   — SHA-256(fr_document_number + full_text), unique constraint

edges           — directed citation graph
  rule_id_source → rule_id_target
  relationship_type: "cites" | "amends" | "supersedes"
  extraction_method: "regex" | "llm"

dead_letters    — failed ingestion attempts for replay/debugging
```

---

## Out of Scope (v1)

- Agencies beyond FERC
- Public comments ingestion
- User accounts / saved searches
- Real-time FR webhooks (polling is sufficient)
- LLM-based citation extraction (Phase 3 uses regex only)

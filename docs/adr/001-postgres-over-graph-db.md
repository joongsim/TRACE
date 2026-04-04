# ADR 001: Postgres Over a Graph Database

## Status

Accepted

## Context

TRACE builds a citation graph between regulatory documents. Graph databases
(Neo4j, Amazon Neptune) are purpose-built for graph traversal. However, our
data also requires full-text search, vector similarity search (pgvector),
relational queries with aggregation, and transactional writes.

## Decision

Use PostgreSQL 17 with pgvector. Model graph edges as a relational table with
foreign keys to the rules table. Use NetworkX for in-memory graph analytics
(PageRank, path finding) by loading the edge table on demand.

## Consequences

- **Pro:** Single database for relational, vector, and graph-edge storage.
  Simpler ops, backups, and migrations.
- **Pro:** pgvector enables semantic search without a separate vector store.
- **Pro:** NetworkX handles analytics workloads at our expected scale
  (thousands to low tens of thousands of rules).
- **Con:** Multi-hop traversals are slower than a native graph DB. Acceptable
  at our scale; revisit if we exceed ~100k edges.
- **Con:** No native graph query language (Cypher). Graph queries go through
  SQLAlchemy + NetworkX instead.

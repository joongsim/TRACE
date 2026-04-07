# Docling PDF-to-Markdown Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace HTML-stripping text extraction with PDF→Markdown via docling-serve, with HTML fallback and a `text_source` column to track which path was used.

**Architecture:** `_fetch_one` and `fetch_full_text` gain a PDF→docling-serve path that runs first; on failure or when `docling_url` is unset, they fall back to the existing BeautifulSoup HTML path. Return type changes from bare `str` to `(text, text_source)` tuple. All call sites are updated to unpack the tuple.

**Tech Stack:** httpx (async + sync), BeautifulSoup (fallback), docling-serve REST API (`POST /v1/convert/source`), SQLAlchemy, Alembic, pytest.

---

## File Structure

| File | Change |
|---|---|
| `src/trace_app/config.py` | Add `docling_url: str \| None = None` |
| `src/trace_app/storage/models.py` | Add `text_source` column |
| `migrations/versions/e7f8a9b0_add_text_source_to_rules.py` | New migration |
| `src/trace_app/connectors/federal_register.py` | Add `pdf_url` field; rewrite fetch methods |
| `src/trace_app/processing/rules.py` | Add `text_source` param to `parse_fr_document` |
| `src/trace_app/storage/ingest.py` | Update `save_rule` to persist `text_source` on upsert |
| `src/trace_app/connectors/ingest.py` | Pass `docling_url`; unpack `(text, text_source)` tuples |
| `docker-compose.yml` | Add docling-serve service |
| `tests/conftest.py` | Add `text_source` to SQLite rules CREATE TABLE |
| `tests/unit/test_federal_register.py` | New docling tests; update broken return-type tests |
| `tests/unit/test_rules_processing.py` | Add `text_source` tests |
| `tests/unit/test_ingest_storage.py` | Add `text_source` upsert test |

---

### Task 1: Add `text_source` column to model, conftest, and migration

**Files:**
- Modify: `src/trace_app/storage/models.py`
- Modify: `tests/conftest.py`
- Create: `migrations/versions/e7f8a9b0_add_text_source_to_rules.py`
- Test: `tests/unit/test_ingest_storage.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_ingest_storage.py`:

```python
def test_save_rule_upsert_updates_text_source(sqlite_session):
    save_rule(sqlite_session, _make_rule(text_source="html_fallback", content_hash="hash-v1"))
    save_rule(sqlite_session, _make_rule(text_source="pdf_docling", content_hash="hash-v2"))
    from sqlalchemy import select
    rows = sqlite_session.execute(select(Rule)).scalars().all()
    assert len(rows) == 1
    assert rows[0].text_source == "pdf_docling"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_ingest_storage.py::test_save_rule_upsert_updates_text_source -v
```

Expected: `FAILED` — `TypeError: unexpected keyword argument 'text_source'`

- [ ] **Step 3: Add `text_source` to the ORM model**

In `src/trace_app/storage/models.py`, add after the `fr_document_number` line:

```python
text_source: Mapped[str] = mapped_column(Text, nullable=False, server_default="html_fallback", default="html_fallback")
```

The full `Rule` class should now end with:

```python
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    fr_document_number: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    text_source: Mapped[str] = mapped_column(Text, nullable=False, server_default="html_fallback", default="html_fallback")
```

- [ ] **Step 4: Update the SQLite conftest CREATE TABLE**

In `tests/conftest.py`, update the raw SQL in `_create_sqlite_tables` to include `text_source`. Replace the `CREATE TABLE IF NOT EXISTS rules` block with:

```python
            conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS rules (
                    rule_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    abstract TEXT,
                    full_text TEXT NOT NULL,
                    publication_date TEXT NOT NULL,
                    effective_date TEXT,
                    agency TEXT NOT NULL,
                    document_type TEXT NOT NULL,
                    cfr_sections TEXT,
                    administration TEXT NOT NULL,
                    fr_url TEXT NOT NULL,
                    embedding TEXT,
                    ingested_at TEXT,
                    content_hash TEXT UNIQUE,
                    fr_document_number TEXT,
                    text_source TEXT NOT NULL DEFAULT 'html_fallback'
                )
            """)
            )
```

- [ ] **Step 5: Create the Alembic migration**

Create `migrations/versions/e7f8a9b0_add_text_source_to_rules.py`:

```python
"""add text_source to rules

Revision ID: e7f8a9b0
Revises: c3f1a2b4
Create Date: 2026-04-06 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7f8a9b0"
down_revision: str | None = "c3f1a2b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rules",
        sa.Column("text_source", sa.Text(), nullable=False, server_default="html_fallback"),
    )


def downgrade() -> None:
    op.drop_column("rules", "text_source")
```

- [ ] **Step 6: Run the test to verify it passes**

```bash
uv run pytest tests/unit/test_ingest_storage.py -v
```

Expected: all `PASSED`

- [ ] **Step 7: Commit**

```bash
git add src/trace_app/storage/models.py tests/conftest.py migrations/versions/e7f8a9b0_add_text_source_to_rules.py tests/unit/test_ingest_storage.py
git commit -m "feat: add text_source column to rules"
```

---

### Task 2: Add `docling_url` to Settings

**Files:**
- Modify: `src/trace_app/config.py`
- Test: `tests/unit/test_config.py`

- [ ] **Step 1: Write the failing test**

Open `tests/unit/test_config.py` and add:

```python
def test_settings_docling_url_defaults_to_none(monkeypatch):
    monkeypatch.delenv("DOCLING_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://trace:trace@localhost/trace")
    from trace_app.config import Settings
    settings = Settings()
    assert settings.docling_url is None


def test_settings_docling_url_loaded_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://trace:trace@localhost/trace")
    monkeypatch.setenv("DOCLING_URL", "http://docling:5001")
    from trace_app.config import Settings
    settings = Settings()
    assert settings.docling_url == "http://docling:5001"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_config.py::test_settings_docling_url_defaults_to_none tests/unit/test_config.py::test_settings_docling_url_loaded_from_env -v
```

Expected: `FAILED` — `ValidationError` or `AttributeError`

- [ ] **Step 3: Add `docling_url` to Settings**

In `src/trace_app/config.py`, add after `embedding_dimension`:

```python
    docling_url: str | None = None
```

Full file after edit:

```python
"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings, loaded from environment variables."""

    database_url: str
    log_level: str = "INFO"
    embedding_model: str = "bge-small-en-v1.5"
    embedding_dimension: int = 384
    docling_url: str | None = None

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_config.py -v
```

Expected: all `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/trace_app/config.py tests/unit/test_config.py
git commit -m "feat: add docling_url to Settings"
```

---

### Task 3: Add `pdf_url` to FR API request

**Files:**
- Modify: `src/trace_app/connectors/federal_register.py`
- Test: `tests/unit/test_federal_register.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_federal_register.py`:

```python
def test_fetch_documents_page_includes_pdf_url():
    mock_response = MagicMock()
    mock_response.json.return_value = SAMPLE_PAGE_RESPONSE
    mock_response.raise_for_status.return_value = None

    with patch("httpx.get", return_value=mock_response) as mock_get:
        client = FederalRegisterClient()
        client.fetch_documents_page(FERC, start_date=date(2021, 1, 1), end_date=date(2021, 12, 31))

    call_args = mock_get.call_args
    params = call_args.kwargs.get("params") or call_args.args[1]
    field_values = [v for k, v in params if k == "fields[]"]
    assert "pdf_url" in field_values
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_federal_register.py::test_fetch_documents_page_includes_pdf_url -v
```

Expected: `FAILED` — `AssertionError: assert 'pdf_url' in [...]`

- [ ] **Step 3: Add `pdf_url` to the params list**

In `src/trace_app/connectors/federal_register.py`, in `fetch_documents_page`, add `("fields[]", "pdf_url")` after the `body_html_url` entry:

```python
            ("fields[]", "html_url"),
            ("fields[]", "body_html_url"),
            ("fields[]", "pdf_url"),
            ("fields[]", "publication_date"),
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/test_federal_register.py::test_fetch_documents_page_includes_pdf_url -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/trace_app/connectors/federal_register.py tests/unit/test_federal_register.py
git commit -m "feat: request pdf_url field from FR API"
```

---

### Task 4: Update `parse_fr_document` to accept and set `text_source`

**Files:**
- Modify: `src/trace_app/processing/rules.py`
- Test: `tests/unit/test_rules_processing.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_rules_processing.py`:

```python
def test_parse_fr_document_default_text_source():
    rule = parse_fr_document(SAMPLE_DOC, SAMPLE_FULL_TEXT)
    assert rule.text_source == "html_fallback"


def test_parse_fr_document_sets_pdf_docling_source():
    rule = parse_fr_document(SAMPLE_DOC, SAMPLE_FULL_TEXT, text_source="pdf_docling")
    assert rule.text_source == "pdf_docling"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_rules_processing.py::test_parse_fr_document_default_text_source tests/unit/test_rules_processing.py::test_parse_fr_document_sets_pdf_docling_source -v
```

Expected: `FAILED` — `TypeError: parse_fr_document() got an unexpected keyword argument 'text_source'`

- [ ] **Step 3: Update `parse_fr_document`**

Replace the function signature and `Rule(...)` call in `src/trace_app/processing/rules.py`:

```python
def parse_fr_document(doc: dict, full_text: str, text_source: str = "html_fallback") -> Rule:
    """Parse a Federal Register API document dict into a Rule ORM instance."""
    pub_date = date.fromisoformat(doc["publication_date"])
    effective_date = date.fromisoformat(doc["effective_on"]) if doc.get("effective_on") else None

    cfr_refs = doc.get("cfr_references", [])
    cfr_sections = [f"{ref['title']} C.F.R. § {ref['part']}" for ref in cfr_refs] or None

    doc_number = doc["document_number"]

    return Rule(
        title=doc["title"],
        abstract=doc.get("abstract"),
        full_text=full_text,
        publication_date=pub_date,
        effective_date=effective_date,
        agency="FERC",
        document_type=doc["type"].upper().replace(" ", "_"),
        cfr_sections=cfr_sections,
        administration=get_administration(pub_date),
        fr_url=doc["html_url"],
        fr_document_number=doc_number,
        content_hash=compute_content_hash(doc_number, full_text),
        ingested_at=datetime.now(UTC),
        text_source=text_source,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_rules_processing.py -v
```

Expected: all `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/trace_app/processing/rules.py tests/unit/test_rules_processing.py
git commit -m "feat: add text_source param to parse_fr_document"
```

---

### Task 5: Update `save_rule` to persist `text_source` on upsert

**Files:**
- Modify: `src/trace_app/storage/ingest.py`
- Test: `tests/unit/test_ingest_storage.py` (test already written in Task 1)

- [ ] **Step 1: Verify the test from Task 1 still fails (it should, `save_rule` not yet updated)**

```bash
uv run pytest tests/unit/test_ingest_storage.py::test_save_rule_upsert_updates_text_source -v
```

Expected: `FAILED` — `assert rows[0].text_source == "pdf_docling"` fails (value is still `"html_fallback"`)

- [ ] **Step 2: Update `save_rule` to copy `text_source` on upsert**

In `src/trace_app/storage/ingest.py`, in the `save_rule` function, add `existing.text_source = rule.text_source` after `existing.ingested_at`:

```python
def save_rule(session: Session, rule: Rule) -> bool:
    """Upsert a Rule by fr_document_number. Returns True if inserted, False if updated."""
    existing = session.execute(
        select(Rule).where(Rule.fr_document_number == rule.fr_document_number)
    ).scalar_one_or_none()

    if existing is None:
        session.add(rule)
        session.flush()
        return True

    existing.full_text = rule.full_text
    existing.content_hash = rule.content_hash
    existing.abstract = rule.abstract
    existing.ingested_at = rule.ingested_at
    existing.text_source = rule.text_source
    session.flush()
    return False
```

- [ ] **Step 3: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_ingest_storage.py -v
```

Expected: all `PASSED`

- [ ] **Step 4: Commit**

```bash
git add src/trace_app/storage/ingest.py
git commit -m "feat: persist text_source on save_rule upsert"
```

---

### Task 6: Rewrite fetch layer with PDF→docling path and HTML fallback

This is the core change. Updates sync `fetch_full_text`, async `_fetch_one`, and `fetch_full_texts_concurrent`.

**Files:**
- Modify: `src/trace_app/connectors/federal_register.py`
- Test: `tests/unit/test_federal_register.py`

- [ ] **Step 1: Write failing tests for the sync `fetch_full_text` method**

In `tests/unit/test_federal_register.py`, **replace** `test_fetch_full_text_strips_html` with the updated version, and add three new tests:

```python
def test_fetch_full_text_strips_html():
    html_content = "<html><body><p>Rule text here.</p><p>More text.</p></body></html>"
    mock_response = MagicMock()
    mock_response.text = html_content
    mock_response.raise_for_status.return_value = None

    with patch("httpx.get", return_value=mock_response):
        client = FederalRegisterClient()
        text, source = client.fetch_full_text("https://example.com/body.html")

    assert "Rule text here." in text
    assert "<p>" not in text
    assert source == "html_fallback"


def test_fetch_full_text_uses_docling_when_configured():
    docling_response = MagicMock()
    docling_response.json.return_value = {"document": {"md_content": "# Rule\n\nMarkdown content."}}
    docling_response.raise_for_status.return_value = None

    with patch("httpx.post", return_value=docling_response):
        client = FederalRegisterClient()
        text, source = client.fetch_full_text(
            body_html_url="https://example.com/body.html",
            pdf_url="https://example.com/doc.pdf",
            docling_url="http://localhost:5001",
        )

    assert source == "pdf_docling"
    assert "# Rule" in text


def test_fetch_full_text_falls_back_to_html_when_docling_fails():
    html_content = "<html><body><p>Rule text here.</p></body></html>"
    mock_html = MagicMock()
    mock_html.text = html_content
    mock_html.raise_for_status.return_value = None

    with patch("httpx.post", side_effect=Exception("connection refused")):
        with patch("httpx.get", return_value=mock_html):
            client = FederalRegisterClient()
            text, source = client.fetch_full_text(
                body_html_url="https://example.com/body.html",
                pdf_url="https://example.com/doc.pdf",
                docling_url="http://localhost:5001",
            )

    assert source == "html_fallback"
    assert "Rule text here." in text


def test_fetch_full_text_skips_docling_when_url_none():
    html_content = "<html><body><p>Rule text here.</p></body></html>"
    mock_html = MagicMock()
    mock_html.text = html_content
    mock_html.raise_for_status.return_value = None

    with patch("httpx.post") as mock_post:
        with patch("httpx.get", return_value=mock_html):
            client = FederalRegisterClient()
            text, source = client.fetch_full_text(
                body_html_url="https://example.com/body.html",
                pdf_url="https://example.com/doc.pdf",
                docling_url=None,
            )

    mock_post.assert_not_called()
    assert source == "html_fallback"
```

- [ ] **Step 2: Write failing tests for `fetch_full_texts_concurrent`**

In `tests/unit/test_federal_register.py`, **replace** `test_fetch_full_texts_concurrent_returns_texts` with the updated version, update `test_fetch_full_texts_concurrent_retries_on_429`, and add three new tests:

```python
def test_fetch_full_texts_concurrent_returns_texts():
    docs = [
        {"document_number": "2021-11111", "body_html_url": "https://example.com/1.html", "pdf_url": ""},
        {"document_number": "2021-22222", "body_html_url": "https://example.com/2.html", "pdf_url": ""},
    ]
    html = "<html><body><p>Rule text.</p></body></html>"

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = html
    mock_response.raise_for_status = MagicMock()

    with patch("trace_app.connectors.federal_register.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = asyncio.run(fetch_full_texts_concurrent(docs))

    text, source = result["2021-11111"]
    assert "Rule text." in text
    assert source == "html_fallback"
    assert isinstance(result["2021-22222"], tuple)


def test_fetch_full_texts_concurrent_retries_on_429():
    docs = [{"document_number": "2021-11111", "body_html_url": "https://example.com/1.html", "pdf_url": ""}]
    html = "<html><body><p>Rule text.</p></body></html>"

    response_429 = MagicMock()
    response_429.status_code = 429
    response_429.raise_for_status.side_effect = httpx.HTTPStatusError(
        "429", request=MagicMock(), response=response_429
    )

    response_200 = MagicMock()
    response_200.status_code = 200
    response_200.text = html
    response_200.raise_for_status = MagicMock()

    with (
        patch("trace_app.connectors.federal_register.httpx.AsyncClient") as mock_cls,
        patch("trace_app.connectors.federal_register.asyncio.sleep", new_callable=AsyncMock),
    ):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[response_429, response_200])
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = asyncio.run(fetch_full_texts_concurrent(docs))

    text, source = result["2021-11111"]
    assert "Rule text." in text
    assert source == "html_fallback"


def test_fetch_full_texts_concurrent_uses_docling_when_configured():
    docs = [
        {
            "document_number": "2021-11111",
            "body_html_url": "https://example.com/1.html",
            "pdf_url": "https://example.com/1.pdf",
        }
    ]
    docling_response = MagicMock()
    docling_response.status_code = 200
    docling_response.json.return_value = {"document": {"md_content": "# Rule\n\nMarkdown."}}
    docling_response.raise_for_status = MagicMock()

    with patch("trace_app.connectors.federal_register.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=docling_response)
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = asyncio.run(fetch_full_texts_concurrent(docs, docling_url="http://localhost:5001"))

    text, source = result["2021-11111"]
    assert source == "pdf_docling"
    assert "# Rule" in text


def test_fetch_full_texts_concurrent_falls_back_on_docling_failure():
    docs = [
        {
            "document_number": "2021-11111",
            "body_html_url": "https://example.com/1.html",
            "pdf_url": "https://example.com/1.pdf",
        }
    ]
    html = "<html><body><p>Rule text.</p></body></html>"
    html_response = MagicMock()
    html_response.status_code = 200
    html_response.text = html
    html_response.raise_for_status = MagicMock()

    with patch("trace_app.connectors.federal_register.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("docling unavailable"))
        mock_client.get = AsyncMock(return_value=html_response)
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = asyncio.run(fetch_full_texts_concurrent(docs, docling_url="http://localhost:5001"))

    text, source = result["2021-11111"]
    assert source == "html_fallback"
    assert "Rule text." in text
```

- [ ] **Step 3: Run all federal_register tests to see the failures**

```bash
uv run pytest tests/unit/test_federal_register.py -v
```

Expected: several `FAILED` — the new tests fail, and the updated existing tests fail because the return type is still `str` not `(str, str)`.

- [ ] **Step 4: Rewrite the fetch layer in `federal_register.py`**

Replace the entire file with:

```python
"""Federal Register API client."""

import asyncio
from dataclasses import dataclass, field
from datetime import date

import httpx
from bs4 import BeautifulSoup

FR_API_BASE = "https://www.federalregister.gov/api/v1"


@dataclass(frozen=True)
class AgencyConfig:
    agency: str
    doc_types: list[str]
    name: str
    topics: list[str] = field(default_factory=list)


FERC = AgencyConfig(
    agency="federal-energy-regulatory-commission",
    doc_types=["RULE", "PRORULE", "NOTICE", "PRESDOCU"],
    topics=[],
    name="FERC",
)

DOE = AgencyConfig(
    agency="energy-department",
    doc_types=["RULE"],
    topics=["energy-conservation"],
    name="DOE",
)

DOL = AgencyConfig(
    agency="labor-department",
    doc_types=["RULE", "PRORULE", "NOTICE", "PRESDOCU"],
    topics=[],
    name="DOL",
)


class FederalRegisterClient:
    def __init__(self, base_url: str = FR_API_BASE):
        self._base_url = base_url

    def fetch_documents_page(
        self,
        config: AgencyConfig,
        start_date: date,
        end_date: date,
        page: int = 1,
        per_page: int = 100,
    ) -> dict:
        """Fetch one page of documents from the FR API for the given agency config."""
        params: list[tuple[str, str | int | float | None]] = [
            ("conditions[agencies][]", config.agency),
            ("per_page", per_page),
            ("page", page),
            ("order", "newest"),
            ("conditions[publication_date][gte]", start_date.isoformat()),
            ("conditions[publication_date][lte]", end_date.isoformat()),
            ("fields[]", "document_number"),
            ("fields[]", "title"),
            ("fields[]", "abstract"),
            ("fields[]", "html_url"),
            ("fields[]", "body_html_url"),
            ("fields[]", "pdf_url"),
            ("fields[]", "publication_date"),
            ("fields[]", "effective_on"),
            ("fields[]", "type"),
            ("fields[]", "agencies"),
            ("fields[]", "cfr_references"),
        ]
        for doc_type in config.doc_types:
            params.append(("conditions[type][]", doc_type))
        for topic in config.topics:
            params.append(("conditions[topics][]", topic))

        response = httpx.get(f"{self._base_url}/documents.json", params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    def fetch_full_text(
        self,
        body_html_url: str,
        pdf_url: str = "",
        docling_url: str | None = None,
    ) -> tuple[str, str]:
        """Fetch document text. Tries PDF via docling-serve first, falls back to HTML.

        Returns (text, text_source) where text_source is 'pdf_docling' or 'html_fallback'.
        """
        if docling_url and pdf_url:
            try:
                response = httpx.post(
                    f"{docling_url}/v1/convert/source",
                    json={"http_source": {"url": pdf_url}, "options": {"to_formats": ["md"]}},
                    timeout=120,
                )
                response.raise_for_status()
                return response.json()["document"]["md_content"], "pdf_docling"
            except Exception:
                pass

        response = httpx.get(body_html_url, timeout=60)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        return soup.get_text(separator="\n", strip=True), "html_fallback"

    def iter_pages(
        self,
        config: AgencyConfig,
        start_date: date,
        end_date: date,
        per_page: int = 100,
    ):
        """Yield each API page's results as a list of document dicts."""
        page = 1
        while True:
            data = self.fetch_documents_page(config, start_date, end_date, page, per_page)
            yield data.get("results", [])
            if page >= data.get("total_pages", page):
                break
            page += 1

    def iter_documents(
        self,
        config: AgencyConfig,
        start_date: date,
        end_date: date,
        per_page: int = 100,
    ):
        """Yield all document dicts for the given date range, paginating automatically."""
        for page in self.iter_pages(config, start_date, end_date, per_page):
            yield from page


_RETRY_DELAYS = [1, 2]


async def _fetch_one(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    doc_number: str,
    body_html_url: str,
    pdf_url: str = "",
    docling_url: str | None = None,
) -> tuple[str, str, str] | tuple[str, BaseException]:
    async with semaphore:
        if docling_url and pdf_url:
            try:
                response = await client.post(
                    f"{docling_url}/v1/convert/source",
                    json={"http_source": {"url": pdf_url}, "options": {"to_formats": ["md"]}},
                    timeout=120,
                )
                response.raise_for_status()
                return doc_number, response.json()["document"]["md_content"], "pdf_docling"
            except Exception:
                pass  # fall through to HTML fallback

        for attempt in range(3):
            try:
                response = await client.get(body_html_url, timeout=60)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "lxml")
                return doc_number, soup.get_text(separator="\n", strip=True), "html_fallback"
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429 and attempt < 2:
                    await asyncio.sleep(_RETRY_DELAYS[attempt])
                    continue
                return doc_number, exc
            except Exception as exc:
                return doc_number, exc
    return doc_number, RuntimeError("max retries exceeded")  # unreachable


async def fetch_full_texts_concurrent(
    docs: list[dict],
    concurrency: int = 10,
    docling_url: str | None = None,
) -> dict[str, tuple[str, str] | BaseException]:
    """Fetch full text for a batch of documents concurrently with 429 retry.

    Returns a dict mapping doc_number to (text, text_source) on success,
    or a BaseException on failure.
    """
    semaphore = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient() as client:
        pairs = await asyncio.gather(
            *[
                _fetch_one(
                    client,
                    semaphore,
                    doc.get("document_number", "unknown"),
                    doc.get("body_html_url", ""),
                    pdf_url=doc.get("pdf_url", ""),
                    docling_url=docling_url,
                )
                for doc in docs
            ]
        )
    result: dict[str, tuple[str, str] | BaseException] = {}
    for pair in pairs:
        if len(pair) == 3:
            doc_number, text, source = pair
            result[doc_number] = (text, source)
        else:
            doc_number, exc = pair
            result[doc_number] = exc
    return result
```

- [ ] **Step 5: Run all federal_register tests to verify they pass**

```bash
uv run pytest tests/unit/test_federal_register.py -v
```

Expected: all `PASSED`

- [ ] **Step 6: Run full test suite to check for regressions**

```bash
uv run pytest tests/unit/ -v
```

Expected: all `PASSED`

- [ ] **Step 7: Commit**

```bash
git add src/trace_app/connectors/federal_register.py tests/unit/test_federal_register.py
git commit -m "feat: add PDF→docling fetch path with HTML fallback"
```

---

### Task 7: Wire `docling_url` in the ingestion flow

**Files:**
- Modify: `src/trace_app/connectors/ingest.py`

No new unit tests — the flow is tested end-to-end via integration tests. All unit pieces are already covered.

- [ ] **Step 1: Update `ingest_fr` to pass `docling_url` and unpack `(text, text_source)` tuples**

Replace `src/trace_app/connectors/ingest.py` with:

```python
"""Prefect flow for ingesting Federal Register documents."""

import asyncio
import json
from datetime import date

from prefect import flow

from trace_app.config import Settings
from trace_app.connectors.federal_register import (
    FERC,
    AgencyConfig,
    FederalRegisterClient,
    fetch_full_texts_concurrent,
)
from trace_app.processing.rules import parse_fr_document
from trace_app.storage.database import build_engine, build_session_factory
from trace_app.storage.ingest import save_dead_letter, save_rule


@flow(name="ingest_fr", log_prints=True)
def ingest_fr(
    config: AgencyConfig = FERC,
    start_date: date = date(2025, 1, 1),
    end_date: date | None = None,
    concurrency: int = 10,
) -> None:
    """Ingest Federal Register documents for the given agency config and date range."""
    if end_date is None:
        end_date = date.today()
    settings = Settings()  # ty: ignore[missing-argument]
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    client = FederalRegisterClient()

    inserted = 0
    updated = 0
    failed = 0

    session = session_factory()
    try:
        for page_docs in client.iter_pages(config, start_date, end_date):
            results = asyncio.run(
                fetch_full_texts_concurrent(
                    page_docs,
                    concurrency,
                    docling_url=settings.docling_url,
                )
            )
            for doc in page_docs:
                doc_number = doc.get("document_number", "unknown")
                print(
                    f"processing {doc_number} "
                    f"(inserted={inserted} updated={updated} failed={failed})"
                )
                result = results.get(doc_number)
                if isinstance(result, BaseException):
                    print(f"  failed {doc_number}: {result}")
                    save_dead_letter(
                        session,
                        source_url=doc.get("html_url", ""),
                        raw_payload=json.dumps(doc),
                        error_message=str(result),
                    )
                    session.commit()
                    failed += 1
                else:
                    try:
                        full_text, text_source = result
                        rule = parse_fr_document(doc, full_text, text_source)
                        if save_rule(session, rule):
                            inserted += 1
                            print(f"  inserted {doc_number} ({text_source})")
                        else:
                            updated += 1
                            print(f"  updated {doc_number} ({text_source})")
                        session.commit()
                    except Exception as exc:
                        print(f"  failed {doc_number}: {exc}")
                        save_dead_letter(
                            session,
                            source_url=doc.get("html_url", ""),
                            raw_payload=json.dumps(doc),
                            error_message=str(exc),
                        )
                        session.commit()
                        failed += 1
    finally:
        session.close()

    print(f"ingest complete: inserted={inserted} updated={updated} failed={failed}")


if __name__ == "__main__":
    import argparse
    import inspect

    import trace_app.connectors.federal_register as _fr

    _PRESETS = {
        name: obj for name, obj in inspect.getmembers(_fr) if isinstance(obj, AgencyConfig)
    }
    parser = argparse.ArgumentParser()
    parser.add_argument("--agency", choices=_PRESETS, default="FERC")
    args = parser.parse_args()
    ingest_fr(config=_PRESETS[args.agency])
```

- [ ] **Step 2: Run all unit tests**

```bash
uv run pytest tests/unit/ -v
```

Expected: all `PASSED`

- [ ] **Step 3: Commit**

```bash
git add src/trace_app/connectors/ingest.py
git commit -m "feat: wire docling_url through ingest_fr flow"
```

---

### Task 8: Add docling-serve to docker-compose

**Files:**
- Modify: `docker-compose.yml`

No automated test for this task — verify manually by running `make up`.

- [ ] **Step 1: Add docling-serve service and `DOCLING_URL` env var to docker-compose.yml**

Replace `docker-compose.yml` with:

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg17
    environment:
      POSTGRES_USER: trace
      POSTGRES_PASSWORD: trace
      POSTGRES_DB: trace
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U trace"]
      interval: 5s
      timeout: 5s
      retries: 5

  docling:
    image: ds4sd/docling-serve:latest
    ports:
      - "5001:5001"
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:5001/health || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 5

  app:
    build: .
    depends_on:
      postgres:
        condition: service_healthy
      docling:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql+psycopg://trace:trace@postgres:5432/trace
      DOCLING_URL: http://docling:5001
    env_file:
      - .env
    ports:
      - "8501:8501"

volumes:
  pgdata:
```

- [ ] **Step 2: Run the full unit test suite one final time**

```bash
uv run pytest tests/unit/ -v
```

Expected: all `PASSED`

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "chore: add docling-serve to docker-compose"
```

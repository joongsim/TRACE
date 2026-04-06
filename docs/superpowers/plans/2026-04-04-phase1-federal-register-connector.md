# Phase 1: Federal Register Connector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pull FERC documents from the Federal Register API into Postgres with dedup via SHA-256 content hash and dead-letter capture for failed records.

**Architecture:** A layered pipeline — `FederalRegisterClient` (HTTP + HTML parsing) → `parse_fr_document` (JSON → ORM) → `save_rule` / `save_dead_letter` (storage) — orchestrated by a Prefect flow in `connectors/ferc.py` that is also the `__main__` entry point for `make ingest`.

**Tech Stack:** Python 3.12, httpx, BeautifulSoup4/lxml, Prefect, SQLAlchemy 2, Alembic, structlog, pytest

---

## File Structure

```
src/trace_app/
├── connectors/
│   ├── __init__.py                  (exists, untouched)
│   ├── federal_register.py          CREATE — FR API client, HTML→text extraction
│   └── ferc.py                      CREATE — Prefect flow + __main__ entry
├── processing/
│   ├── __init__.py                  (exists, untouched)
│   └── rules.py                     CREATE — administration mapping, hash, FR JSON→Rule
├── storage/
│   ├── models.py                    MODIFY — add fr_document_number to Rule
│   ├── database.py                  (exists, untouched)
│   ├── __init__.py                  (exists, untouched)
│   └── ingest.py                    CREATE — save_rule, save_dead_letter helpers
migrations/versions/
│   └── <hash>_add_fr_document_number_to_rules.py   CREATE via alembic autogenerate
tests/
├── unit/
│   ├── test_rules_processing.py     CREATE — administration mapping, hash, parsing
│   ├── test_federal_register.py     CREATE — FR client with mocked httpx
│   └── test_ingest_storage.py       CREATE — storage helpers against SQLite
├── integration/
│   └── test_ingest_ferc.py          CREATE — end-to-end flow against real Postgres
```

---

### Task 1: Add dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add runtime deps to pyproject.toml**

Replace the `dependencies` list:

```toml
dependencies = [
    "sqlalchemy>=2.0,<3.0",
    "alembic>=1.13,<2.0",
    "psycopg[binary]>=3.1,<4.0",
    "pgvector>=0.3,<1.0",
    "pydantic>=2.0,<3.0",
    "pydantic-settings>=2.0,<3.0",
    "structlog>=24.0,<27.0",
    "sentence-transformers>=3.0,<4.0",
    "httpx>=0.27,<1.0",
    "beautifulsoup4>=4.12,<5.0",
    "lxml>=5.0,<6.0",
    "prefect>=3.0,<4.0",
]
```

- [ ] **Step 2: Install dependencies**

```bash
uv sync --all-extras
```

Expected: resolves and installs without errors.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add httpx, beautifulsoup4, lxml, prefect deps"
```

---

### Task 2: Add fr_document_number to Rule model + migration

**Files:**
- Modify: `src/trace_app/storage/models.py`
- Create: migration via `alembic revision --autogenerate`

- [ ] **Step 1: Write the failing test**

In `tests/unit/test_models.py` (check if it exists; create or append):

```python
from datetime import date
from trace_app.storage.models import Rule


def test_rule_has_fr_document_number():
    rule = Rule(
        title="Test",
        full_text="body",
        publication_date=date(2021, 6, 1),
        agency="FERC",
        document_type="RULE",
        administration="Biden",
        fr_url="https://www.federalregister.gov/documents/2021/06/01/2021-11111/test",
        fr_document_number="2021-11111",
    )
    assert rule.fr_document_number == "2021-11111"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_models.py -v -k test_rule_has_fr_document_number
```

Expected: FAIL — `Rule` has no attribute `fr_document_number`.

- [ ] **Step 3: Add fr_document_number to Rule model**

In `src/trace_app/storage/models.py`, add after the `content_hash` line:

```python
fr_document_number: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
```

Full updated `Rule` class for reference:

```python
class Rule(Base):
    __tablename__ = "rules"

    rule_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_text: Mapped[str] = mapped_column(Text, nullable=False)
    publication_date: Mapped[date] = mapped_column(Date, nullable=False)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    agency: Mapped[str] = mapped_column(Text, nullable=False)
    document_type: Mapped[str] = mapped_column(Text, nullable=False)
    cfr_sections: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    administration: Mapped[str] = mapped_column(Text, nullable=False)
    fr_url: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True)
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    fr_document_number: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/test_models.py -v -k test_rule_has_fr_document_number
```

Expected: PASS.

- [ ] **Step 5: Generate migration**

```bash
uv run alembic revision --autogenerate -m "add fr_document_number to rules"
```

Expected: creates a new file in `migrations/versions/`. Inspect it to confirm it adds the `fr_document_number` column with an index.

- [ ] **Step 6: Apply migration**

```bash
make migrate
```

Expected: `Running upgrade ... -> <rev>, add fr_document_number to rules`

- [ ] **Step 7: Commit**

```bash
git add src/trace_app/storage/models.py migrations/versions/ tests/unit/test_models.py
git commit -m "feat: add fr_document_number to Rule model with migration"
```

---

### Task 3: Administration date range mapping

**Files:**
- Create: `src/trace_app/processing/rules.py`
- Create: `tests/unit/test_rules_processing.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_rules_processing.py`:

```python
from datetime import date

from trace_app.processing.rules import get_administration


def test_obama_era():
    assert get_administration(date(2016, 6, 15)) == "Obama"


def test_trump1_era():
    assert get_administration(date(2018, 3, 10)) == "Trump 1"


def test_biden_era():
    assert get_administration(date(2022, 11, 1)) == "Biden"


def test_trump2_era():
    assert get_administration(date(2025, 3, 1)) == "Trump 2"


def test_administration_boundary_jan_20_2017():
    assert get_administration(date(2017, 1, 19)) == "Obama"
    assert get_administration(date(2017, 1, 20)) == "Trump 1"


def test_administration_boundary_jan_20_2021():
    assert get_administration(date(2021, 1, 19)) == "Trump 1"
    assert get_administration(date(2021, 1, 20)) == "Biden"


def test_administration_boundary_jan_20_2025():
    assert get_administration(date(2025, 1, 19)) == "Biden"
    assert get_administration(date(2025, 1, 20)) == "Trump 2"


def test_before_obama_returns_unknown():
    assert get_administration(date(2000, 1, 1)) == "Unknown"
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest tests/unit/test_rules_processing.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'trace_app.processing.rules'`

- [ ] **Step 3: Implement get_administration**

Create `src/trace_app/processing/rules.py`:

```python
"""Parsing and processing logic for Federal Register documents."""

from datetime import date

ADMINISTRATION_RANGES: list[tuple[date, str]] = [
    (date(2009, 1, 20), "Obama"),
    (date(2017, 1, 20), "Trump 1"),
    (date(2021, 1, 20), "Biden"),
    (date(2025, 1, 20), "Trump 2"),
]


def get_administration(pub_date: date) -> str:
    """Return the US administration name for a given publication date."""
    admin = "Unknown"
    for start_date, name in ADMINISTRATION_RANGES:
        if pub_date >= start_date:
            admin = name
        else:
            break
    return admin
```

- [ ] **Step 4: Run to verify it passes**

```bash
uv run pytest tests/unit/test_rules_processing.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/trace_app/processing/rules.py tests/unit/test_rules_processing.py
git commit -m "feat: add administration date range mapping"
```

---

### Task 4: Content hash

**Files:**
- Modify: `src/trace_app/processing/rules.py`
- Modify: `tests/unit/test_rules_processing.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_rules_processing.py`:

```python
import hashlib

from trace_app.processing.rules import compute_content_hash


def test_content_hash_is_sha256():
    doc_number = "2021-11111"
    full_text = "This is the full text of the rule."
    expected = hashlib.sha256((doc_number + full_text).encode()).hexdigest()
    assert compute_content_hash(doc_number, full_text) == expected


def test_content_hash_differs_on_different_text():
    h1 = compute_content_hash("2021-11111", "text A")
    h2 = compute_content_hash("2021-11111", "text B")
    assert h1 != h2


def test_content_hash_differs_on_different_doc_number():
    h1 = compute_content_hash("2021-11111", "same text")
    h2 = compute_content_hash("2021-22222", "same text")
    assert h1 != h2
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest tests/unit/test_rules_processing.py -v -k "hash"
```

Expected: FAIL — `ImportError: cannot import name 'compute_content_hash'`

- [ ] **Step 3: Implement compute_content_hash**

Add `import hashlib` to the top of `src/trace_app/processing/rules.py`, then add after `get_administration`:

```python
def compute_content_hash(fr_document_number: str, full_text: str) -> str:
    """SHA-256 of document number concatenated with full text."""
    return hashlib.sha256((fr_document_number + full_text).encode()).hexdigest()
```

- [ ] **Step 4: Run to verify it passes**

```bash
uv run pytest tests/unit/test_rules_processing.py -v -k "hash"
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/trace_app/processing/rules.py tests/unit/test_rules_processing.py
git commit -m "feat: add SHA-256 content hash computation"
```

---

### Task 5: FR JSON → Rule parser

**Files:**
- Modify: `src/trace_app/processing/rules.py`
- Modify: `tests/unit/test_rules_processing.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_rules_processing.py`:

```python
from trace_app.processing.rules import parse_fr_document
from trace_app.storage.models import Rule

SAMPLE_DOC = {
    "document_number": "2021-11111",
    "title": "Electric Transmission Incentives Policy",
    "abstract": "FERC proposes new transmission incentive policy.",
    "html_url": "https://www.federalregister.gov/documents/2021/06/01/2021-11111/test",
    "body_html_url": "https://www.federalregister.gov/documents/2021/06/01/2021-11111/test/body.html",
    "publication_date": "2021-06-01",
    "effective_on": "2021-07-01",
    "type": "Rule",
    "agencies": [{"name": "Federal Energy Regulatory Commission", "id": 172}],
    "cfr_references": [{"title": 18, "part": 35}, {"title": 18, "part": 36}],
}
SAMPLE_FULL_TEXT = "This is the full text of the rule."


def test_parse_fr_document_returns_rule():
    rule = parse_fr_document(SAMPLE_DOC, SAMPLE_FULL_TEXT)
    assert isinstance(rule, Rule)


def test_parse_fr_document_maps_fields():
    rule = parse_fr_document(SAMPLE_DOC, SAMPLE_FULL_TEXT)
    assert rule.title == "Electric Transmission Incentives Policy"
    assert rule.abstract == "FERC proposes new transmission incentive policy."
    assert rule.full_text == SAMPLE_FULL_TEXT
    assert rule.publication_date == date(2021, 6, 1)
    assert rule.effective_date == date(2021, 7, 1)
    assert rule.agency == "FERC"
    assert rule.document_type == "RULE"
    assert rule.fr_url == SAMPLE_DOC["html_url"]
    assert rule.fr_document_number == "2021-11111"


def test_parse_fr_document_maps_administration():
    rule = parse_fr_document(SAMPLE_DOC, SAMPLE_FULL_TEXT)
    assert rule.administration == "Biden"


def test_parse_fr_document_maps_cfr_sections():
    rule = parse_fr_document(SAMPLE_DOC, SAMPLE_FULL_TEXT)
    assert "18 C.F.R. § 35" in rule.cfr_sections
    assert "18 C.F.R. § 36" in rule.cfr_sections


def test_parse_fr_document_sets_content_hash():
    rule = parse_fr_document(SAMPLE_DOC, SAMPLE_FULL_TEXT)
    expected = compute_content_hash("2021-11111", SAMPLE_FULL_TEXT)
    assert rule.content_hash == expected


def test_parse_fr_document_no_effective_date():
    doc = {**SAMPLE_DOC, "effective_on": None}
    rule = parse_fr_document(doc, SAMPLE_FULL_TEXT)
    assert rule.effective_date is None


def test_parse_fr_document_no_cfr_references():
    doc = {**SAMPLE_DOC, "cfr_references": []}
    rule = parse_fr_document(doc, SAMPLE_FULL_TEXT)
    assert rule.cfr_sections is None


def test_parse_fr_document_sets_ingested_at():
    rule = parse_fr_document(SAMPLE_DOC, SAMPLE_FULL_TEXT)
    assert rule.ingested_at is not None
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest tests/unit/test_rules_processing.py -v -k "parse"
```

Expected: FAIL — `ImportError: cannot import name 'parse_fr_document'`

- [ ] **Step 3: Implement parse_fr_document**

Full updated `src/trace_app/processing/rules.py`:

```python
"""Parsing and processing logic for Federal Register documents."""

import hashlib
from datetime import date, datetime

from trace_app.storage.models import Rule

ADMINISTRATION_RANGES: list[tuple[date, str]] = [
    (date(2009, 1, 20), "Obama"),
    (date(2017, 1, 20), "Trump 1"),
    (date(2021, 1, 20), "Biden"),
    (date(2025, 1, 20), "Trump 2"),
]


def get_administration(pub_date: date) -> str:
    """Return the US administration name for a given publication date."""
    admin = "Unknown"
    for start_date, name in ADMINISTRATION_RANGES:
        if pub_date >= start_date:
            admin = name
        else:
            break
    return admin


def compute_content_hash(fr_document_number: str, full_text: str) -> str:
    """SHA-256 of document number concatenated with full text."""
    return hashlib.sha256((fr_document_number + full_text).encode()).hexdigest()


def parse_fr_document(doc: dict, full_text: str) -> Rule:
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
        ingested_at=datetime.utcnow(),
    )
```

- [ ] **Step 4: Run to verify it passes**

```bash
uv run pytest tests/unit/test_rules_processing.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/trace_app/processing/rules.py tests/unit/test_rules_processing.py
git commit -m "feat: add FR JSON to Rule parser with admin mapping and content hash"
```

---

### Task 6: Federal Register API client

**Files:**
- Create: `src/trace_app/connectors/federal_register.py`
- Create: `tests/unit/test_federal_register.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_federal_register.py`:

```python
"""Unit tests for the Federal Register API client (httpx calls are mocked)."""

from datetime import date
from unittest.mock import MagicMock, patch

from trace_app.connectors.federal_register import FederalRegisterClient


SAMPLE_PAGE_RESPONSE = {
    "count": 2,
    "total_pages": 1,
    "results": [
        {
            "document_number": "2021-11111",
            "title": "Test Rule",
            "abstract": "Abstract text.",
            "html_url": "https://www.federalregister.gov/documents/2021/06/01/2021-11111/test",
            "body_html_url": "https://www.federalregister.gov/documents/2021/06/01/2021-11111/test/body.html",
            "publication_date": "2021-06-01",
            "effective_on": "2021-07-01",
            "type": "Rule",
            "agencies": [{"name": "Federal Energy Regulatory Commission", "id": 172}],
            "cfr_references": [{"title": 18, "part": 35}],
        },
        {
            "document_number": "2021-22222",
            "title": "Test Notice",
            "abstract": None,
            "html_url": "https://www.federalregister.gov/documents/2021/07/01/2021-22222/notice",
            "body_html_url": "https://www.federalregister.gov/documents/2021/07/01/2021-22222/notice/body.html",
            "publication_date": "2021-07-01",
            "effective_on": None,
            "type": "Notice",
            "agencies": [{"name": "Federal Energy Regulatory Commission", "id": 172}],
            "cfr_references": [],
        },
    ],
}


def test_fetch_documents_page_calls_correct_url():
    mock_response = MagicMock()
    mock_response.json.return_value = SAMPLE_PAGE_RESPONSE
    mock_response.raise_for_status.return_value = None

    with patch("httpx.get", return_value=mock_response) as mock_get:
        client = FederalRegisterClient()
        result = client.fetch_documents_page(
            start_date=date(2021, 1, 1),
            end_date=date(2021, 12, 31),
            page=1,
        )

    mock_get.assert_called_once()
    call_args = mock_get.call_args
    assert "documents.json" in call_args.args[0]
    assert result["total_pages"] == 1
    assert len(result["results"]) == 2


def test_fetch_full_text_strips_html():
    html_content = "<html><body><p>Rule text here.</p><p>More text.</p></body></html>"
    mock_response = MagicMock()
    mock_response.text = html_content
    mock_response.raise_for_status.return_value = None

    with patch("httpx.get", return_value=mock_response):
        client = FederalRegisterClient()
        text = client.fetch_full_text("https://example.com/body.html")

    assert "Rule text here." in text
    assert "<p>" not in text


def test_iter_documents_yields_all_results_single_page():
    mock_response = MagicMock()
    mock_response.json.return_value = SAMPLE_PAGE_RESPONSE
    mock_response.raise_for_status.return_value = None

    with patch("httpx.get", return_value=mock_response):
        client = FederalRegisterClient()
        docs = list(client.iter_documents(date(2021, 1, 1), date(2021, 12, 31)))

    assert len(docs) == 2
    assert docs[0]["document_number"] == "2021-11111"


def test_iter_documents_paginates():
    page1 = {"count": 2, "total_pages": 2, "results": [{"document_number": "2021-00001"}]}
    page2 = {"count": 2, "total_pages": 2, "results": [{"document_number": "2021-00002"}]}

    responses = [MagicMock(), MagicMock()]
    responses[0].json.return_value = page1
    responses[0].raise_for_status.return_value = None
    responses[1].json.return_value = page2
    responses[1].raise_for_status.return_value = None

    with patch("httpx.get", side_effect=responses):
        client = FederalRegisterClient()
        docs = list(client.iter_documents(date(2021, 1, 1), date(2021, 12, 31)))

    assert len(docs) == 2
    assert docs[0]["document_number"] == "2021-00001"
    assert docs[1]["document_number"] == "2021-00002"


def test_iter_documents_handles_zero_results():
    empty_response = {"count": 0, "total_pages": 0, "results": []}
    mock_response = MagicMock()
    mock_response.json.return_value = empty_response
    mock_response.raise_for_status.return_value = None

    with patch("httpx.get", return_value=mock_response):
        client = FederalRegisterClient()
        docs = list(client.iter_documents(date(2021, 1, 1), date(2021, 12, 31)))

    assert docs == []
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest tests/unit/test_federal_register.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'trace_app.connectors.federal_register'`

- [ ] **Step 3: Implement FederalRegisterClient**

Create `src/trace_app/connectors/federal_register.py`:

```python
"""Federal Register API client."""

from datetime import date

import httpx
from bs4 import BeautifulSoup

FR_API_BASE = "https://www.federalregister.gov/api/v1"
FERC_AGENCY = "federal-energy-regulatory-commission-ferc"
FERC_DOC_TYPES = ["RULE", "PROPOSED_RULE", "NOTICE"]


class FederalRegisterClient:
    def __init__(self, base_url: str = FR_API_BASE):
        self._base_url = base_url

    def fetch_documents_page(
        self,
        start_date: date,
        end_date: date,
        page: int = 1,
        per_page: int = 100,
    ) -> dict:
        """Fetch one page of FERC documents from the FR API."""
        params: list[tuple[str, str | int]] = [
            ("conditions[agencies][]", FERC_AGENCY),
            ("per_page", per_page),
            ("page", page),
            ("conditions[publication_date][gte]", start_date.isoformat()),
            ("conditions[publication_date][lte]", end_date.isoformat()),
            ("fields[]", "document_number"),
            ("fields[]", "title"),
            ("fields[]", "abstract"),
            ("fields[]", "html_url"),
            ("fields[]", "body_html_url"),
            ("fields[]", "publication_date"),
            ("fields[]", "effective_on"),
            ("fields[]", "type"),
            ("fields[]", "agencies"),
            ("fields[]", "cfr_references"),
        ]
        for doc_type in FERC_DOC_TYPES:
            params.append(("conditions[type][]", doc_type))

        response = httpx.get(f"{self._base_url}/documents.json", params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    def fetch_full_text(self, body_html_url: str) -> str:
        """Fetch the HTML body of a document and return plain text."""
        response = httpx.get(body_html_url, timeout=60)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        return soup.get_text(separator="\n", strip=True)

    def iter_documents(self, start_date: date, end_date: date, per_page: int = 100):
        """Yield all document dicts for the given date range, paginating automatically."""
        page = 1
        while True:
            data = self.fetch_documents_page(start_date, end_date, page, per_page)
            yield from data["results"]
            if page >= data["total_pages"]:
                break
            page += 1
```

- [ ] **Step 4: Run to verify it passes**

```bash
uv run pytest tests/unit/test_federal_register.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/trace_app/connectors/federal_register.py tests/unit/test_federal_register.py
git commit -m "feat: add Federal Register API client with pagination and HTML extraction"
```

---

### Task 7: Storage helpers — save_rule and save_dead_letter

**Files:**
- Create: `src/trace_app/storage/ingest.py`
- Create: `tests/unit/test_ingest_storage.py`

- [ ] **Step 1: Write the failing unit tests**

Create `tests/unit/test_ingest_storage.py`:

```python
"""Unit tests for storage helpers (SQLite — skips PG-specific columns)."""

from datetime import date, datetime

from trace_app.storage.ingest import save_dead_letter, save_rule
from trace_app.storage.models import DeadLetter, Rule


def _make_rule(**overrides) -> Rule:
    defaults = dict(
        title="Test Rule",
        full_text="Full body text.",
        publication_date=date(2021, 6, 1),
        agency="FERC",
        document_type="RULE",
        administration="Biden",
        fr_url="https://www.federalregister.gov/documents/2021/06/01/2021-11111/test",
        fr_document_number="2021-11111",
        content_hash="abc123",
        ingested_at=datetime.utcnow(),
    )
    defaults.update(overrides)
    return Rule(**defaults)


def test_save_rule_returns_true_on_insert(sqlite_session):
    rule = _make_rule()
    result = save_rule(sqlite_session, rule)
    assert result is True


def test_save_rule_returns_false_on_duplicate_hash(sqlite_session):
    rule1 = _make_rule(content_hash="unique-hash-xyz")
    rule2 = _make_rule(content_hash="unique-hash-xyz", fr_document_number="2021-22222")
    save_rule(sqlite_session, rule1)
    result = save_rule(sqlite_session, rule2)
    assert result is False


def test_save_dead_letter_persists(sqlite_session):
    save_dead_letter(
        sqlite_session,
        source_url="https://www.federalregister.gov/documents/bad",
        raw_payload='{"document_number": "2021-99999"}',
        error_message="Connection timeout",
    )
    sqlite_session.flush()
    dead = sqlite_session.query(DeadLetter).first()
    assert dead is not None
    assert dead.error_message == "Connection timeout"
    assert dead.failed_at is not None
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest tests/unit/test_ingest_storage.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'trace_app.storage.ingest'`

- [ ] **Step 3: Implement save_rule and save_dead_letter**

Create `src/trace_app/storage/ingest.py`:

```python
"""Storage helpers for rule ingestion."""

from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from trace_app.storage.models import DeadLetter, Rule


def save_rule(session: Session, rule: Rule) -> bool:
    """Persist a Rule, skipping duplicates by content_hash. Returns True if inserted."""
    try:
        session.begin_nested()
        session.add(rule)
        session.flush()
        return True
    except IntegrityError:
        session.rollback()
        return False


def save_dead_letter(
    session: Session,
    source_url: str,
    raw_payload: str,
    error_message: str,
) -> None:
    """Persist a failed ingestion record to dead_letters."""
    dead = DeadLetter(
        source_url=source_url,
        raw_payload=raw_payload,
        error_message=error_message,
        failed_at=datetime.utcnow(),
    )
    session.add(dead)
    session.flush()
```

- [ ] **Step 4: Run to verify it passes**

```bash
uv run pytest tests/unit/test_ingest_storage.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/trace_app/storage/ingest.py tests/unit/test_ingest_storage.py
git commit -m "feat: add save_rule and save_dead_letter storage helpers"
```

---

### Task 8: Prefect flow + __main__ entry

**Files:**
- Create: `src/trace_app/connectors/ferc.py`
- Create: `tests/integration/test_ingest_ferc.py`

- [ ] **Step 1: Write the failing integration tests**

Create `tests/integration/test_ingest_ferc.py`:

```python
"""Integration tests for the FERC ingestion flow against real Postgres."""

from datetime import date
from unittest.mock import patch

import pytest

from trace_app.connectors.ferc import ingest_ferc
from trace_app.storage.models import DeadLetter, Rule


SAMPLE_DOCS = [
    {
        "document_number": "2021-11111",
        "title": "Electric Transmission Incentives Policy",
        "abstract": "FERC proposes new transmission incentive policy.",
        "html_url": "https://www.federalregister.gov/documents/2021/06/01/2021-11111/test",
        "body_html_url": "https://www.federalregister.gov/documents/2021/06/01/2021-11111/test/body.html",
        "publication_date": "2021-06-01",
        "effective_on": "2021-07-01",
        "type": "Rule",
        "agencies": [{"name": "Federal Energy Regulatory Commission", "id": 172}],
        "cfr_references": [{"title": 18, "part": 35}],
    },
]


@pytest.mark.integration
def test_ingest_ferc_inserts_rules(pg_session):
    with (
        patch(
            "trace_app.connectors.ferc.FederalRegisterClient.iter_documents",
            return_value=iter(SAMPLE_DOCS),
        ),
        patch(
            "trace_app.connectors.ferc.FederalRegisterClient.fetch_full_text",
            return_value="Full text of the rule.",
        ),
        patch(
            "trace_app.connectors.ferc.build_engine",
            return_value=pg_session.get_bind(),
        ),
    ):
        ingest_ferc(start_date=date(2021, 1, 1), end_date=date(2021, 12, 31))

    rules = pg_session.query(Rule).all()
    assert len(rules) == 1
    assert rules[0].fr_document_number == "2021-11111"
    assert rules[0].administration == "Biden"


@pytest.mark.integration
def test_ingest_ferc_deduplicates(pg_session):
    for _ in range(2):
        with (
            patch(
                "trace_app.connectors.ferc.FederalRegisterClient.iter_documents",
                return_value=iter(SAMPLE_DOCS),
            ),
            patch(
                "trace_app.connectors.ferc.FederalRegisterClient.fetch_full_text",
                return_value="Full text of the rule.",
            ),
            patch(
                "trace_app.connectors.ferc.build_engine",
                return_value=pg_session.get_bind(),
            ),
        ):
            ingest_ferc(start_date=date(2021, 1, 1), end_date=date(2021, 12, 31))

    rules = pg_session.query(Rule).all()
    assert len(rules) == 1


@pytest.mark.integration
def test_ingest_ferc_writes_dead_letter_on_error(pg_session):
    with (
        patch(
            "trace_app.connectors.ferc.FederalRegisterClient.iter_documents",
            return_value=iter(SAMPLE_DOCS),
        ),
        patch(
            "trace_app.connectors.ferc.FederalRegisterClient.fetch_full_text",
            side_effect=Exception("Connection timeout"),
        ),
        patch(
            "trace_app.connectors.ferc.build_engine",
            return_value=pg_session.get_bind(),
        ),
    ):
        ingest_ferc(start_date=date(2021, 1, 1), end_date=date(2021, 12, 31))

    rules = pg_session.query(Rule).all()
    dead = pg_session.query(DeadLetter).all()
    assert len(rules) == 0
    assert len(dead) == 1
    assert "Connection timeout" in dead[0].error_message
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest tests/integration/test_ingest_ferc.py -v -m integration
```

Expected: FAIL — `ModuleNotFoundError: No module named 'trace_app.connectors.ferc'`

- [ ] **Step 3: Implement the Prefect flow**

Create `src/trace_app/connectors/ferc.py`:

```python
"""Prefect flow for ingesting FERC documents from the Federal Register."""

import json
from datetime import date

import structlog
from prefect import flow

from trace_app.config import Settings
from trace_app.connectors.federal_register import FederalRegisterClient
from trace_app.processing.rules import parse_fr_document
from trace_app.storage.database import build_engine, build_session_factory
from trace_app.storage.ingest import save_dead_letter, save_rule

logger = structlog.get_logger()


@flow(name="ingest_ferc", log_prints=True)
def ingest_ferc(
    start_date: date = date(2017, 1, 20),
    end_date: date = date.today(),
) -> None:
    """Ingest FERC documents from the Federal Register for the given date range."""
    settings = Settings()
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    client = FederalRegisterClient()

    inserted = 0
    skipped = 0
    failed = 0

    session = session_factory()
    try:
        for doc in client.iter_documents(start_date, end_date):
            doc_number = doc.get("document_number", "unknown")
            try:
                full_text = client.fetch_full_text(doc["body_html_url"])
                rule = parse_fr_document(doc, full_text)
                if save_rule(session, rule):
                    inserted += 1
                    logger.info("rule.inserted", document_number=doc_number)
                else:
                    skipped += 1
                    logger.debug("rule.duplicate", document_number=doc_number)
                session.commit()
            except Exception as exc:
                logger.warning("rule.failed", document_number=doc_number, error=str(exc))
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

    logger.info("ingest.complete", inserted=inserted, skipped=skipped, failed=failed)


if __name__ == "__main__":
    ingest_ferc()
```

- [ ] **Step 4: Run unit tests to verify nothing is broken**

```bash
uv run pytest tests/unit/ -v
```

Expected: all PASS.

- [ ] **Step 5: Run integration tests**

```bash
uv run pytest tests/integration/test_ingest_ferc.py -v -m integration
```

Expected: all three integration tests PASS.

- [ ] **Step 6: Run full test suite**

```bash
make test
```

Expected: all tests PASS, coverage ≥ 60%.

- [ ] **Step 7: Commit**

```bash
git add src/trace_app/connectors/ferc.py tests/integration/test_ingest_ferc.py
git commit -m "feat: add ingest_ferc Prefect flow with dedup and dead-letter capture"
```

---

### Task 9: Smoke-test make ingest (manual)

**Files:** none changed

- [ ] **Step 1: Verify Docker is up and migrated**

```bash
make up && make migrate
```

Expected: containers start; migration applies cleanly.

- [ ] **Step 2: Run ingest for the default date range**

Ensure `.env` contains `DATABASE_URL=postgresql+psycopg://trace:trace@localhost:5433/trace`, then:

```bash
make ingest
```

Expected: structlog output with `rule.inserted` and/or `rule.duplicate` lines. No unhandled exceptions.

- [ ] **Step 3: Verify rows landed in Postgres**

```bash
docker exec -it trace-db-1 psql -U trace -c "SELECT count(*) FROM rules;"
```

Expected: count > 0.

- [ ] **Step 4: Commit .env.example if updated**

If `.env.example` was updated to document the `DATABASE_URL` var:

```bash
git add .env.example
git commit -m "chore: document DATABASE_URL in .env.example"
```

---

## Self-Review

**Spec coverage:**

| Requirement | Task |
|---|---|
| FR API client: paginated fetch by agency + doc types | Task 6 |
| Parse FR JSON → Rule ORM; map administration from date ranges | Tasks 3, 4, 5 |
| Dedup via SHA-256 content_hash on (fr_document_number, full_text) | Tasks 4, 7 |
| Failed records → DeadLetter with raw payload and error message | Tasks 7, 8 |
| Prefect flow: ingest_ferc with configurable date range, idempotent | Task 8 |
| `make ingest` triggers the flow locally | Task 9 (Makefile already correct) |
| Administration date ranges hardcoded constants | Task 3 |
| full_text from FR HTML; abstract from FR abstract field | Task 5 |

**Placeholder scan:** No TBD, TODO, or vague steps.

**Type consistency:** `parse_fr_document(doc: dict, full_text: str) -> Rule` consistent across Tasks 5 and 8. `save_rule(session, rule) -> bool` and `save_dead_letter(session, source_url, raw_payload, error_message)` consistent across Tasks 7 and 8. `FederalRegisterClient.iter_documents` / `fetch_full_text` names match between Tasks 6 and 8.

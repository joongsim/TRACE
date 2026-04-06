# Async Concurrent Full Text Fetching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace sequential `fetch_full_text` calls with concurrent async fetching, achieving 10x+ throughput on full-text ingestion.

**Architecture:** Add `iter_pages` to `FederalRegisterClient` for per-page batching, add a module-level async function `fetch_full_texts_concurrent` in `federal_register.py`, and update `ingest_ferc` to iterate pages and call the async fetcher via `asyncio.run` per page.

**Tech Stack:** Python `asyncio`, `httpx.AsyncClient`, `unittest.mock.AsyncMock` for testing.

---

## File Map

| File | Change |
|---|---|
| `src/trace_app/connectors/federal_register.py` | Add `iter_pages` method; refactor `iter_documents` to delegate; add `_fetch_one` and `fetch_full_texts_concurrent` async functions |
| `src/trace_app/connectors/ferc.py` | Add `concurrency: int = 10` param; switch from `iter_documents` to `iter_pages`; call `fetch_full_texts_concurrent` via `asyncio.run` |
| `tests/unit/test_federal_register.py` | Add tests for `iter_pages` and `fetch_full_texts_concurrent` |
| `tests/integration/test_ingest_ferc.py` | Add integration test for concurrent flow |

---

## Task 1: Add `iter_pages` and refactor `iter_documents`

**Files:**
- Modify: `src/trace_app/connectors/federal_register.py`
- Test: `tests/unit/test_federal_register.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_federal_register.py`:

```python
def test_iter_pages_yields_per_page_list():
    page1 = {"count": 2, "total_pages": 2, "results": [{"document_number": "2021-00001"}]}
    page2 = {"count": 2, "total_pages": 2, "results": [{"document_number": "2021-00002"}]}

    responses = [MagicMock(), MagicMock()]
    responses[0].json.return_value = page1
    responses[0].raise_for_status.return_value = None
    responses[1].json.return_value = page2
    responses[1].raise_for_status.return_value = None

    with patch("httpx.get", side_effect=responses):
        client = FederalRegisterClient()
        pages = list(client.iter_pages(date(2021, 1, 1), date(2021, 12, 31)))

    assert len(pages) == 2
    assert pages[0] == [{"document_number": "2021-00001"}]
    assert pages[1] == [{"document_number": "2021-00002"}]
```

- [ ] **Step 2: Run the test to verify it fails**

```
pytest tests/unit/test_federal_register.py::test_iter_pages_yields_per_page_list -v
```

Expected: `FAILED` — `AttributeError: 'FederalRegisterClient' object has no attribute 'iter_pages'`

- [ ] **Step 3: Add `iter_pages` and refactor `iter_documents`**

Replace the `iter_documents` method in `src/trace_app/connectors/federal_register.py` with:

```python
def iter_pages(self, start_date: date, end_date: date, per_page: int = 100):
    """Yield each API page's results as a list of document dicts."""
    page = 1
    while True:
        data = self.fetch_documents_page(start_date, end_date, page, per_page)
        yield data.get("results", [])
        if page >= data.get("total_pages", page):
            break
        page += 1

def iter_documents(self, start_date: date, end_date: date, per_page: int = 100):
    """Yield all document dicts for the given date range, paginating automatically."""
    for page in self.iter_pages(start_date, end_date, per_page):
        yield from page
```

- [ ] **Step 4: Run all federal register unit tests**

```
pytest tests/unit/test_federal_register.py -v
```

Expected: All tests pass, including the four pre-existing tests.

- [ ] **Step 5: Commit**

```bash
git add src/trace_app/connectors/federal_register.py tests/unit/test_federal_register.py
git commit -m "feat: add iter_pages to FederalRegisterClient, delegate iter_documents"
```

---

## Task 2: Add `fetch_full_texts_concurrent` async function

**Files:**
- Modify: `src/trace_app/connectors/federal_register.py`
- Test: `tests/unit/test_federal_register.py`

- [ ] **Step 1: Write the three failing tests**

Add to `tests/unit/test_federal_register.py`:

```python
import asyncio
from unittest.mock import AsyncMock

import httpx

from trace_app.connectors.federal_register import fetch_full_texts_concurrent


def test_fetch_full_texts_concurrent_returns_texts():
    docs = [
        {"document_number": "2021-11111", "body_html_url": "https://example.com/1.html"},
        {"document_number": "2021-22222", "body_html_url": "https://example.com/2.html"},
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

    assert isinstance(result["2021-11111"], str)
    assert "Rule text." in result["2021-11111"]
    assert isinstance(result["2021-22222"], str)


def test_fetch_full_texts_concurrent_retries_on_429():
    docs = [{"document_number": "2021-11111", "body_html_url": "https://example.com/1.html"}]
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

    assert isinstance(result["2021-11111"], str)
    assert "Rule text." in result["2021-11111"]


def test_fetch_full_texts_concurrent_returns_exception_on_failure():
    docs = [{"document_number": "2021-11111", "body_html_url": "https://example.com/1.html"}]

    with patch("trace_app.connectors.federal_register.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection failed"))
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = asyncio.run(fetch_full_texts_concurrent(docs))

    assert isinstance(result["2021-11111"], BaseException)
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/unit/test_federal_register.py::test_fetch_full_texts_concurrent_returns_texts tests/unit/test_federal_register.py::test_fetch_full_texts_concurrent_retries_on_429 tests/unit/test_federal_register.py::test_fetch_full_texts_concurrent_returns_exception_on_failure -v
```

Expected: `FAILED` — `ImportError: cannot import name 'fetch_full_texts_concurrent'`

- [ ] **Step 3: Implement `_fetch_one` and `fetch_full_texts_concurrent`**

Add `import asyncio` to the imports at the top of `src/trace_app/connectors/federal_register.py`. Then add these two functions after the class definition:

```python
_RETRY_DELAYS = [1, 2]


async def _fetch_one(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    doc_number: str,
    url: str,
) -> tuple[str, str | BaseException]:
    async with semaphore:
        for attempt in range(3):
            try:
                response = await client.get(url, timeout=60)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "lxml")
                return doc_number, soup.get_text(separator="\n", strip=True)
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
) -> dict[str, str | BaseException]:
    """Fetch full text for a batch of documents concurrently with 429 retry."""
    semaphore = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient() as client:
        pairs = await asyncio.gather(
            *[
                _fetch_one(
                    client,
                    semaphore,
                    doc.get("document_number", "unknown"),
                    doc.get("body_html_url", ""),
                )
                for doc in docs
            ]
        )
    return dict(pairs)
```

- [ ] **Step 4: Run all federal register unit tests**

```
pytest tests/unit/test_federal_register.py -v
```

Expected: All 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/trace_app/connectors/federal_register.py tests/unit/test_federal_register.py
git commit -m "feat: add fetch_full_texts_concurrent with semaphore and 429 retry"
```

---

## Task 3: Update `ingest_ferc` flow

**Files:**
- Modify: `src/trace_app/connectors/ferc.py`
- Test: `tests/integration/test_ingest_ferc.py`

- [ ] **Step 1: Write the failing integration test**

Add to `tests/integration/test_ingest_ferc.py`:

```python
from unittest.mock import AsyncMock

@pytest.mark.integration
def test_ingest_ferc_concurrent_inserts_rules(pg_session):
    with (
        patch(
            "trace_app.connectors.ferc.FederalRegisterClient.iter_pages",
            return_value=iter([SAMPLE_DOCS]),
        ),
        patch(
            "trace_app.connectors.ferc.fetch_full_texts_concurrent",
            new=AsyncMock(return_value={"2021-11111": "Full text of the rule."}),
        ),
        patch(
            "trace_app.connectors.ferc.build_engine",
            return_value=pg_session.get_bind(),
        ),
    ):
        ingest_ferc(start_date=date(2021, 1, 1), end_date=date(2021, 12, 31), concurrency=5)

    rules = pg_session.query(Rule).all()
    assert len(rules) == 1
    assert rules[0].fr_document_number == "2021-11111"
    assert rules[0].administration == "Biden"
```

- [ ] **Step 2: Run the test to verify it fails**

```
pytest tests/integration/test_ingest_ferc.py::test_ingest_ferc_concurrent_inserts_rules -v -m integration
```

Expected: `FAILED` — `TypeError: ingest_ferc() got an unexpected keyword argument 'concurrency'`

- [ ] **Step 3: Rewrite `ferc.py`**

Replace the full contents of `src/trace_app/connectors/ferc.py`:

```python
"""Prefect flow for ingesting FERC documents from the Federal Register."""

import asyncio
import json
from datetime import date

from prefect import flow

from trace_app.config import Settings
from trace_app.connectors.federal_register import FederalRegisterClient, fetch_full_texts_concurrent
from trace_app.processing.rules import parse_fr_document
from trace_app.storage.database import build_engine, build_session_factory
from trace_app.storage.ingest import save_dead_letter, save_rule


@flow(name="ingest_ferc", log_prints=True)
def ingest_ferc(
    start_date: date = date(2025, 1, 1),
    end_date: date | None = None,
    concurrency: int = 10,
) -> None:
    """Ingest FERC documents from the Federal Register for the given date range."""
    if end_date is None:
        end_date = date.today()
    settings = Settings()  # ty: ignore[missing-argument]
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    client = FederalRegisterClient()

    inserted = 0
    skipped = 0
    failed = 0

    session = session_factory()
    try:
        for page_docs in client.iter_pages(start_date, end_date):
            results = asyncio.run(fetch_full_texts_concurrent(page_docs, concurrency))
            for doc in page_docs:
                doc_number = doc.get("document_number", "unknown")
                print(
                    f"processing {doc_number} (inserted={inserted} skipped={skipped} failed={failed})"
                )
                full_text = results.get(doc_number)
                if isinstance(full_text, BaseException):
                    print(f"  failed {doc_number}: {full_text}")
                    save_dead_letter(
                        session,
                        source_url=doc.get("html_url", ""),
                        raw_payload=json.dumps(doc),
                        error_message=str(full_text),
                    )
                    session.commit()
                    failed += 1
                else:
                    try:
                        rule = parse_fr_document(doc, full_text)
                        if save_rule(session, rule):
                            inserted += 1
                            print(f"  inserted {doc_number}")
                        else:
                            skipped += 1
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

    print(f"ingest complete: inserted={inserted} skipped={skipped} failed={failed}")


if __name__ == "__main__":
    ingest_ferc()
```

- [ ] **Step 4: Run the full test suite**

```
pytest tests/ -v
```

Expected: All tests pass. The three existing integration tests (`test_ingest_ferc_inserts_rules`, `test_ingest_ferc_deduplicates`, `test_ingest_ferc_writes_dead_letter_on_error`) may fail if they still patch `fetch_full_text` on the old code path — update them if so (see Step 5).

- [ ] **Step 5: Fix existing integration tests if needed**

The three existing integration tests patch `FederalRegisterClient.iter_documents` and `fetch_full_text` (sync). The new flow uses `iter_pages` and `fetch_full_texts_concurrent` instead. Update each test.

Add `from unittest.mock import AsyncMock` to the imports in `tests/integration/test_ingest_ferc.py`.

**`test_ingest_ferc_inserts_rules` and `test_ingest_ferc_deduplicates`** — replace both patches with:
```python
patch(
    "trace_app.connectors.ferc.FederalRegisterClient.iter_pages",
    return_value=iter([SAMPLE_DOCS]),
),
patch(
    "trace_app.connectors.ferc.fetch_full_texts_concurrent",
    new=AsyncMock(return_value={"2021-11111": "Full text of the rule."}),
),
patch(
    "trace_app.connectors.ferc.build_engine",
    return_value=pg_session.get_bind(),
),
```

**`test_ingest_ferc_writes_dead_letter_on_error`** — the original mock used `side_effect=Exception("Connection timeout")` to simulate a fetch failure. In the new flow, a fetch failure is a `BaseException` value in the results dict. Replace both patches with:
```python
patch(
    "trace_app.connectors.ferc.FederalRegisterClient.iter_pages",
    return_value=iter([SAMPLE_DOCS]),
),
patch(
    "trace_app.connectors.ferc.fetch_full_texts_concurrent",
    new=AsyncMock(return_value={"2021-11111": Exception("Connection timeout")}),
),
patch(
    "trace_app.connectors.ferc.build_engine",
    return_value=pg_session.get_bind(),
),
```

- [ ] **Step 6: Run the full test suite again**

```
pytest tests/ -v
```

Expected: All tests pass including coverage check.

- [ ] **Step 7: Run lint**

```
make lint
```

Expected: No errors.

- [ ] **Step 8: Commit**

```bash
git add src/trace_app/connectors/ferc.py tests/integration/test_ingest_ferc.py
git commit -m "feat: concurrent full text fetching in ingest_ferc (issue #7)"
```

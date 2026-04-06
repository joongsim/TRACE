# Async Concurrent Full Text Fetching

**Issue:** [#7](https://github.com/joongsim/TRACE/issues/7)
**Date:** 2026-04-05

## Problem

`fetch_full_text` makes one blocking HTTP request per document sequentially. For a large backfill (2017–present) this is the primary bottleneck — each request takes 5–60s depending on document size, meaning thousands of sequential requests.

## Approach

Standalone async function `fetch_full_texts_concurrent` in `federal_register.py`, called per-page from the `ingest_ferc` flow via `asyncio.run`. The flow stays synchronous; only the HTTP fetching layer is async.

Per-page batching was chosen over all-docs-upfront for fault tolerance: each page is committed to the DB before the next begins, so a crash mid-run preserves prior pages.

## Changes

### `federal_register.py`

**New method: `FederalRegisterClient.iter_pages`**

Yields each API page as a `list[dict]`. Extracts pagination logic that currently lives inline in `iter_documents`. `iter_documents` is updated to delegate to `iter_pages` — no behavior change.

**New function: `fetch_full_texts_concurrent`**

```python
async def fetch_full_texts_concurrent(
    docs: list[dict],
    concurrency: int = 10,
) -> dict[str, str | BaseException]:
```

- Opens one `httpx.AsyncClient` for the batch
- Uses `asyncio.Semaphore(concurrency)` to cap parallel in-flight requests
- Per-URL coroutine: on HTTP 429, sleeps with exponential backoff (1s, 2s) for up to 3 attempts before raising
- Uses `asyncio.gather(..., return_exceptions=True)` so one failed doc does not abort the batch
- Returns `{doc_number: full_text}` on success, `{doc_number: exception}` on failure

### `ferc.py`

`ingest_ferc` gains `concurrency: int = 10` parameter.

Inner loop changes from streaming individual docs to iterating pages:

```python
for page_docs in client.iter_pages(start_date, end_date):
    results = asyncio.run(
        fetch_full_texts_concurrent(page_docs, concurrency)
    )
    for doc in page_docs:
        doc_number = doc.get("document_number", "unknown")
        result = results.get(doc_number)
        if isinstance(result, BaseException):
            # dead-letter path (unchanged)
        else:
            # parse/save/dedup path (unchanged)
```

Per-doc error handling (dead letters, dedup) is unchanged — the concurrency change is transparent to that logic.

## Testing

### Unit tests (`test_federal_register.py`)

| Test | What it verifies |
|---|---|
| `test_iter_pages_yields_per_page_list` | `iter_pages` yields `list[dict]` per page and paginates correctly |
| `test_fetch_full_texts_concurrent_returns_texts` | All docs returned when all succeed |
| `test_fetch_full_texts_concurrent_retries_on_429` | 429 then 200 → retry succeeds, result is text not exception |
| `test_fetch_full_texts_concurrent_returns_exception_on_failure` | Non-429 error → exception in result dict, not raised |

### Integration tests (`test_ingest_ferc.py`)

Existing tests continue to patch `fetch_full_text` (sync) — no changes needed.

Add `test_ingest_ferc_concurrent_inserts_rules`: patches `fetch_full_texts_concurrent` to return `{doc_number: "Full text"}`, verifies correct DB insertion and that the `concurrency` parameter flows through to the function call.

## Expected Impact

10x+ throughput improvement on full text ingestion. A page of 100 documents fetched at concurrency=10 takes ~10% of the sequential time (bottleneck shifts from network wait to the semaphore limit).

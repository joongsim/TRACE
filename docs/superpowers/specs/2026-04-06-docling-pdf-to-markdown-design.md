# PDF to Markdown via Docling-Serve

## Problem

FERC rules contain tables, multi-column layouts, and cross-references that BeautifulSoup HTML stripping mangles. The current pipeline fetches `body_html_url` and strips tags, losing structural information that matters for citation extraction and administration-level comparison.

## Solution

Replace the primary text extraction path with PDF-based conversion via docling-serve. Fetch `pdf_url` from the FR API, POST PDF bytes to a docling-serve instance, and store the resulting Markdown as `full_text`. Fall back to HTML + BeautifulSoup when PDF conversion is unavailable, and track which path was used.

## Architecture: Swap at the Fetch Layer

Modify the internals of `_fetch_one` and `fetch_full_text` to attempt PDF conversion first, falling back to HTML. No new abstractions — a simple if/else at the fetch boundary.

### Config

Add `docling_url: str | None = None` to `Settings`. When `None`, the PDF path is skipped entirely (HTML fallback only). When set, PDF conversion is attempted first.

### FR API Fields

Add `("fields[]", "pdf_url")` to the params in `fetch_documents_page`, alongside the existing `body_html_url` field.

### Fetch Layer

`_fetch_one` gains an optional `docling_url` parameter:

1. If `docling_url` is set and the doc has a `pdf_url`: download PDF bytes, POST to `{docling_url}/v1/convert`, extract Markdown. Return `(doc_number, text, "pdf_docling")`.
2. If that fails, or `docling_url` is `None`, or `pdf_url` is missing: fetch `body_html_url`, strip with BeautifulSoup. Return `(doc_number, text, "html_fallback")`.

`fetch_full_texts_concurrent` passes `docling_url` through. Return type changes from `dict[str, str | BaseException]` to `dict[str, tuple[str, str] | BaseException]` where the tuple is `(text, text_source)`.

`FederalRegisterClient.fetch_full_text` (sync) gets the same dual-path treatment.

### Data Model

Add to `Rule`:

```python
text_source: Mapped[str] = mapped_column(Text, nullable=False, server_default="html_fallback")
```

Values: `"pdf_docling"` or `"html_fallback"`. The `server_default` backfills existing rows accurately.

New Alembic migration adds the column.

### Ingestion Flow

In `ingest_fr`:

- Read `docling_url` from `Settings`
- Pass to `fetch_full_texts_concurrent`
- Unpack `(text, text_source)` tuples from results
- Pass `text_source` through `parse_fr_document` (new parameter, default `"html_fallback"`) to set on the `Rule`

### Docker Compose

Add docling-serve service:

```yaml
docling:
  image: ds4sd/docling-serve:latest
  ports:
    - "5001:5001"
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:5001/health"]
    interval: 10s
    timeout: 5s
    retries: 5
```

Add `DOCLING_URL: http://docling:5001` to the `app` service environment.

### Testing

- Unit tests for `_fetch_one`: PDF success path, PDF failure falls back to HTML, `docling_url=None` goes straight to HTML.
- Unit tests for `fetch_full_texts_concurrent`: verify tuple return shape.
- Update existing tests for new `(text, text_source)` return type.
- Unit test for `parse_fr_document`: verify `text_source` is set on the `Rule`.
- Integration test (`@pytest.mark.integration`): hits real docling-serve if available.

## Files Changed

- `src/trace_app/config.py` — add `docling_url`
- `src/trace_app/connectors/federal_register.py` — fetch layer changes, `pdf_url` field
- `src/trace_app/connectors/ingest.py` — pass `docling_url`, unpack tuples
- `src/trace_app/processing/rules.py` — `text_source` parameter
- `src/trace_app/storage/models.py` — `text_source` column
- `migrations/` — new Alembic migration
- `docker-compose.yml` — docling-serve service
- `tests/unit/test_federal_register.py` — new and updated tests
- `tests/unit/test_rules_processing.py` — `text_source` test

# Multi-Agency Federal Register Connector

**Date:** 2026-04-05

## Problem

`FederalRegisterClient` hardcodes FERC-specific constants (`FERC_AGENCY`, `FERC_DOC_TYPES`), and the Prefect flow lives in `ferc.py` as `ingest_ferc`. Adding a second agency requires duplicating both files. The platform should support any Federal Register agency via named presets.

## Approach

Add `AgencyConfig` dataclass and named presets (`FERC`, `DOE`) to `federal_register.py`. Pass config through the client methods. Rename `ferc.py` → `ingest.py` and `ingest_ferc` → `ingest_fr` with `config: AgencyConfig = FERC`.

## Changes

### `federal_register.py`

Add `AgencyConfig` frozen dataclass and two presets after the existing imports:

```python
from dataclasses import dataclass, field

@dataclass(frozen=True)
class AgencyConfig:
    agency: str                        # FR API agency slug
    doc_types: list[str]               # FR API document type filters
    name: str                          # human-readable label for logging
    topics: list[str] = field(default_factory=list)  # FR API topic filters

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
```

Remove module-level `FERC_AGENCY` and `FERC_DOC_TYPES` constants.

Update `fetch_documents_page`, `iter_pages`, and `iter_documents` to accept `config: AgencyConfig` as their first parameter (after `self`). The method builds FR API params from `config.agency`, `config.doc_types`, and `config.topics` instead of the deleted constants.

### `ingest.py` (new, replaces `ferc.py`)

```python
@flow(name="ingest_fr", log_prints=True)
def ingest_fr(
    config: AgencyConfig = FERC,
    start_date: date = date(2025, 1, 1),
    end_date: date | None = None,
    concurrency: int = 10,
) -> None:
```

- `ferc.py` is deleted
- Flow name changes from `"ingest_ferc"` to `"ingest_fr"` — Prefect treats it as a new flow
- `config` defaults to `FERC` so existing invocations (e.g. `make ingest`) continue to work
- All internal logic is identical to `ferc.py` — `iter_pages(config, start_date, end_date)` replaces `iter_pages(start_date, end_date)`

### Tests

**`tests/unit/test_federal_register.py`:**
- Pass `FERC` (or `DOE`) to all `fetch_documents_page`, `iter_pages`, `iter_documents` calls
- Add `test_fetch_documents_page_uses_config_agency`: verify that passing `DOE` config builds params with `"energy-department"` agency and `"energy-conservation"` topic

**`tests/integration/test_ingest_ferc.py` → `tests/integration/test_ingest_fr.py`:**
- Rename file
- Update all imports: `from trace_app.connectors.ingest import ingest_fr`
- Update all patches: `"trace_app.connectors.ferc.*"` → `"trace_app.connectors.ingest.*"`
- Pass `config=FERC` (or assert it uses the default) in each test
- No new test cases — behavior is unchanged

## Adding a New Agency

```python
# In federal_register.py
EPA = AgencyConfig(
    agency="environmental-protection-agency",
    doc_types=["RULE", "PRORULE"],
    topics=[],
    name="EPA",
)
```

Then call `ingest_fr(config=EPA, ...)`. One dict, no other changes.

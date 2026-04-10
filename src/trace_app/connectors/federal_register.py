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
                    json={
                        "sources": [{"kind": "http", "url": pdf_url}],
                        "options": {"to_formats": ["md"]},
                    },
                    timeout=120,
                )
                response.raise_for_status()
                return response.json()["document"]["md_content"], "pdf_docling"
            except Exception as exc:
                print(f"  docling failed for {pdf_url}: {exc!r}, falling back to HTML")

        response = httpx.get(body_html_url, timeout=60)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        return soup.get_text(separator="\n", strip=True), "html_fallback"

    def fetch_documents_by_numbers(self, doc_numbers: list[str]) -> list[dict]:
        """Fetch pdf_url and body_html_url for a list of document numbers."""
        if not doc_numbers:
            return []
        response = httpx.get(
            f"{self._base_url}/documents/{','.join(doc_numbers)}.json",
            params=[
                ("fields[]", "document_number"),
                ("fields[]", "html_url"),
                ("fields[]", "body_html_url"),
                ("fields[]", "pdf_url"),
            ],
            timeout=30,
        )
        response.raise_for_status()
        return response.json().get("results", [])

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
) -> tuple[str, str | BaseException, str | None]:
    async with semaphore:
        if docling_url and pdf_url:
            try:
                response = await client.post(
                    f"{docling_url}/v1/convert/source",
                    json={
                        "sources": [{"kind": "http", "url": pdf_url}],
                        "options": {"to_formats": ["md"]},
                    },
                    timeout=120,
                )
                response.raise_for_status()
                return (
                    doc_number,
                    response.json()["document"]["md_content"],
                    "pdf_docling",
                )
            except Exception as exc:
                print(f"  docling failed for {doc_number}: {exc!r}, falling back to HTML")

        for attempt in range(3):
            try:
                response = await client.get(body_html_url, timeout=60)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "lxml")
                return (
                    doc_number,
                    soup.get_text(separator="\n", strip=True),
                    "html_fallback",
                )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429 and attempt < 2:
                    await asyncio.sleep(_RETRY_DELAYS[attempt])
                    continue
                return doc_number, exc, None
            except Exception as exc:
                return doc_number, exc, None
    return doc_number, RuntimeError("max retries exceeded"), None  # unreachable


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
    for doc_number, text_or_exc, source in pairs:
        if isinstance(text_or_exc, BaseException):
            result[doc_number] = text_or_exc
        else:
            assert source is not None
            result[doc_number] = (text_or_exc, source)
    return result

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

    def fetch_full_text(self, body_html_url: str) -> str:
        """Fetch the HTML body of a document and return plain text."""
        response = httpx.get(body_html_url, timeout=60)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        return soup.get_text(separator="\n", strip=True)

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

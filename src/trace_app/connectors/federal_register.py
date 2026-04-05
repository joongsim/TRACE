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
        params: list[tuple[str, str | int | float | None]] = [
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
            yield from data.get("results", [])
            if page >= data.get("total_pages", page):
                break
            page += 1

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

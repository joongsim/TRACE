"""Unit tests for the Federal Register API client (httpx calls are mocked)."""

import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from trace_app.connectors.federal_register import (
    DOE,
    FERC,
    FederalRegisterClient,
    fetch_full_texts_concurrent,
)

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
            "agencies": [{"name": "Department of Energy", "id": 86}],
            "cfr_references": [{"title": 10, "part": 430}],
        },
        {
            "document_number": "2021-22222",
            "title": "Test Rule 2",
            "abstract": None,
            "html_url": "https://www.federalregister.gov/documents/2021/07/01/2021-22222/rule2",
            "body_html_url": "https://www.federalregister.gov/documents/2021/07/01/2021-22222/rule2/body.html",
            "publication_date": "2021-07-01",
            "effective_on": None,
            "type": "Rule",
            "agencies": [{"name": "Department of Energy", "id": 86}],
            "cfr_references": [],
        },
    ],
}


def test_agency_config_ferc_preset():
    assert FERC.agency == "federal-energy-regulatory-commission"
    assert "RULE" in FERC.doc_types
    assert FERC.name == "FERC"


def test_agency_config_doe_preset():
    assert DOE.agency == "energy-department"
    assert "RULE" in DOE.doc_types
    assert DOE.name == "DOE"


def test_fetch_documents_page_calls_correct_url():
    mock_response = MagicMock()
    mock_response.json.return_value = SAMPLE_PAGE_RESPONSE
    mock_response.raise_for_status.return_value = None

    with patch("httpx.get", return_value=mock_response) as mock_get:
        client = FederalRegisterClient()
        result = client.fetch_documents_page(
            FERC,
            start_date=date(2021, 1, 1),
            end_date=date(2021, 12, 31),
            page=1,
        )

    mock_get.assert_called_once()
    call_args = mock_get.call_args
    assert "documents.json" in call_args.args[0]
    assert result["total_pages"] == 1
    assert len(result["results"]) == 2


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


def test_fetch_documents_page_uses_config_agency():
    mock_response = MagicMock()
    mock_response.json.return_value = SAMPLE_PAGE_RESPONSE
    mock_response.raise_for_status.return_value = None

    with patch("httpx.get", return_value=mock_response) as mock_get:
        client = FederalRegisterClient()
        client.fetch_documents_page(
            DOE,
            start_date=date(2021, 1, 1),
            end_date=date(2021, 12, 31),
        )

    call_args = mock_get.call_args
    params = (
        call_args.kwargs.get("params") or call_args.args[1]
        if len(call_args.args) > 1
        else call_args.kwargs["params"]
    )
    param_dict = dict(params) if isinstance(params, dict) else {k: v for k, v in params}
    assert param_dict.get("conditions[agencies][]") == "energy-department"


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
        docs = list(client.iter_documents(FERC, date(2021, 1, 1), date(2021, 12, 31)))

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
        docs = list(client.iter_documents(FERC, date(2021, 1, 1), date(2021, 12, 31)))

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
        docs = list(client.iter_documents(FERC, date(2021, 1, 1), date(2021, 12, 31)))

    assert docs == []


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
        pages = list(client.iter_pages(FERC, date(2021, 1, 1), date(2021, 12, 31)))

    assert len(pages) == 2
    assert pages[0] == [{"document_number": "2021-00001"}]
    assert pages[1] == [{"document_number": "2021-00002"}]


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


def test_fetch_full_texts_concurrent_exhausts_retries_on_persistent_429():
    docs = [{"document_number": "2021-11111", "body_html_url": "https://example.com/1.html"}]

    response_429 = MagicMock()
    response_429.status_code = 429
    response_429.raise_for_status.side_effect = httpx.HTTPStatusError(
        "429", request=MagicMock(), response=response_429
    )

    with (
        patch("trace_app.connectors.federal_register.httpx.AsyncClient") as mock_cls,
        patch("trace_app.connectors.federal_register.asyncio.sleep", new_callable=AsyncMock),
    ):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=response_429)
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = asyncio.run(fetch_full_texts_concurrent(docs))

    assert isinstance(result["2021-11111"], BaseException)

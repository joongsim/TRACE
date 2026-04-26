"""Unit tests for RAG answer generation."""

import uuid
from unittest.mock import MagicMock

from trace_app.agent.rag import _build_context, generate_answer

SAMPLE_DOCS = [
    {
        "rule_id": uuid.uuid4(),
        "title": "Electricity Transmission Rate Reform",
        "abstract": "This rule establishes new transmission pricing standards.",
        "full_text": "The Commission hereby establishes " + ("detailed standards " * 200),
        "publication_date": "2021-03-15",
        "administration": "Biden",
        "agency": "FERC",
        "document_type": "RULE",
        "fr_url": "https://federalregister.gov/doc/1",
        "cfr_sections": ["18 CFR 35"],
        "effective_date": None,
        "fr_document_number": "2021-001",
        "text_source": "html_fallback",
    },
    {
        "rule_id": uuid.uuid4(),
        "title": "Proposed Transmission Interconnection Policy",
        "abstract": "Proposed changes to interconnection queue reform.",
        "full_text": "The Commission proposes " + ("interconnection changes " * 200),
        "publication_date": "2022-07-01",
        "administration": "Biden",
        "agency": "FERC",
        "document_type": "PROPOSED_RULE",
        "fr_url": "https://federalregister.gov/doc/2",
        "cfr_sections": ["18 CFR 36"],
        "effective_date": None,
        "fr_document_number": "2022-001",
        "text_source": "html_fallback",
    },
]


def test_build_context_truncates_full_text():
    context = _build_context(SAMPLE_DOCS[:1])
    assert len(context) < 5000
    assert "Electricity Transmission Rate Reform" in context
    assert "Biden" in context


def test_build_context_includes_all_docs():
    context = _build_context(SAMPLE_DOCS)
    assert "Electricity Transmission Rate Reform" in context
    assert "Proposed Transmission Interconnection Policy" in context


def test_generate_answer_calls_openrouter():
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Transmission rates were reformed in 2021."
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

    answer = generate_answer(
        query="What changes were made to transmission rates?",
        docs=SAMPLE_DOCS,
        client=mock_client,
    )

    assert answer == "Transmission rates were reformed in 2021."
    mock_client.chat.completions.create.assert_called_once()
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "anthropic/claude-sonnet-4-6"
    user_content = call_kwargs["messages"][-1]["content"]
    assert "transmission" in user_content.lower()


def test_generate_answer_returns_empty_string_for_no_docs():
    mock_client = MagicMock()
    answer = generate_answer(
        query="What changes were made to transmission rates?",
        docs=[],
        client=mock_client,
    )
    assert answer == ""
    mock_client.chat.completions.create.assert_not_called()


def test_generate_answer_limits_to_top_5_docs():
    many_docs = SAMPLE_DOCS * 5  # 10 docs
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Answer."
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

    generate_answer(query="transmission", docs=many_docs, client=mock_client)

    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    user_content = call_kwargs["messages"][-1]["content"]
    assert user_content.count("## Document") <= 5

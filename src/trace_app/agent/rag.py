"""RAG answer generation via OpenRouter (OpenAI-compatible API)."""

from __future__ import annotations

import openai

_FULL_TEXT_LIMIT = 2000
_MAX_DOCS = 5
_MODEL = "anthropic/claude-sonnet-4-6"

_SYSTEM_PROMPT = (
    "You are a regulatory analyst assistant helping users understand federal rulemaking. "
    "Answer questions based only on the provided regulatory documents. "
    "Be concise and precise. If the documents do not contain enough information to answer, "
    "say so clearly. Do not speculate beyond the provided context."
)


def _build_context(docs: list[dict]) -> str:
    parts = []
    for i, doc in enumerate(docs[:_MAX_DOCS], start=1):
        full_text = doc.get("full_text") or ""
        if len(full_text) > _FULL_TEXT_LIMIT:
            full_text = full_text[:_FULL_TEXT_LIMIT] + "..."
        parts.append(
            f"## Document {i}: {doc['title']}\n"
            f"Agency: {doc['agency']} | Administration: {doc['administration']} | "
            f"Date: {doc['publication_date']} | Type: {doc['document_type']}\n"
            f"Abstract: {doc.get('abstract') or 'N/A'}\n\n"
            f"{full_text}"
        )
    return "\n\n---\n\n".join(parts)


def generate_answer(
    query: str,
    docs: list[dict],
    client: openai.OpenAI,
) -> str:
    """Generate an LLM answer grounded in retrieved docs. Returns empty string if no docs."""
    if not docs:
        return ""

    context = _build_context(docs)
    response = client.chat.completions.create(
        model=_MODEL,
        max_tokens=1024,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"Question: {query}\n\n{context}"},
        ],
    )
    return response.choices[0].message.content or ""

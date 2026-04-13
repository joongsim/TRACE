"""Unit tests for processing/embeddings.py."""

import uuid
from datetime import date
from unittest.mock import MagicMock

import numpy as np

from trace_app.processing.embeddings import build_embed_text, embed_batch
from trace_app.storage.models import Rule


def _make_rule(**kwargs) -> Rule:
    defaults = dict(
        rule_id=uuid.uuid4(),
        title="Test Rule Title",
        abstract="Abstract text.",
        full_text="a" * 3000,
        publication_date=date(2024, 1, 1),
        agency="FERC",
        document_type="RULE",
        administration="Biden",
        fr_url="https://www.federalregister.gov/documents/2024/01/01/test",
        text_source="html_fallback",
    )
    defaults.update(kwargs)
    return Rule(**defaults)


def test_build_embed_text_contains_title_and_abstract():
    rule = _make_rule(title="My Title", abstract="My Abstract", full_text="body " * 600)
    text = build_embed_text(rule)
    assert "My Title" in text
    assert "My Abstract" in text


def test_build_embed_text_truncates_full_text_to_2048():
    rule = _make_rule(full_text="x" * 3000)
    text = build_embed_text(rule)
    # full_text section should be exactly 2048 chars
    parts = text.split("\n\n")
    assert len(parts[2]) == 2048


def test_build_embed_text_handles_null_abstract():
    rule = _make_rule(abstract=None, full_text="short")
    text = build_embed_text(rule)
    # Should not raise; empty abstract becomes empty string
    assert "Test Rule Title" in text
    assert "short" in text


def test_embed_batch_returns_list_of_float_lists():
    model = MagicMock()
    model.encode.return_value = np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
    result = embed_batch(model, ["text one", "text two"])
    assert result == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]


def test_embed_batch_passes_texts_to_encode():
    model = MagicMock()
    model.encode.return_value = np.array([[0.1]])
    embed_batch(model, ["hello world"])
    model.encode.assert_called_once_with(["hello world"], convert_to_numpy=True)

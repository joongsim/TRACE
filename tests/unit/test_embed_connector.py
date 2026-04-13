"""Unit tests for the embed_rules Prefect flow."""

import uuid
from datetime import date
from unittest.mock import MagicMock, patch

from trace_app.storage.models import Rule


def _make_rule(**kwargs) -> Rule:
    defaults = dict(
        rule_id=uuid.uuid4(),
        title="Test Rule",
        abstract="Abstract.",
        full_text="a" * 3000,
        publication_date=date(2024, 1, 1),
        agency="FERC",
        document_type="RULE",
        administration="Biden",
        fr_url="https://example.com",
        fr_document_number=str(uuid.uuid4()),
        text_source="html_fallback",
    )
    defaults.update(kwargs)
    return Rule(**defaults)


def _mock_session(rules: list[Rule]) -> MagicMock:
    session = MagicMock()
    session.execute.return_value.scalars.return_value.all.return_value = rules
    return session


def test_embed_rules_skips_when_no_null_embedding_rows():
    session = _mock_session([])

    with (
        patch(
            "trace_app.connectors.embed.Settings",
            return_value=MagicMock(embedding_model="bge-small-en-v1.5", embedding_batch_size=64),
        ),
        patch("trace_app.connectors.embed.build_engine"),
        patch("trace_app.connectors.embed.build_session_factory", return_value=lambda: session),
        patch("trace_app.connectors.embed.load_model"),
        patch("trace_app.connectors.embed.embed_batch") as mock_embed,
        patch("trace_app.connectors.embed.save_embeddings"),
    ):
        from trace_app.connectors.embed import embed_rules

        embed_rules()

    mock_embed.assert_not_called()


def test_embed_rules_calls_save_embeddings_with_correct_rule_ids():
    rules = [_make_rule(), _make_rule()]
    session = _mock_session(rules)
    fake_vectors = [[0.1] * 384, [0.2] * 384]

    with (
        patch(
            "trace_app.connectors.embed.Settings",
            return_value=MagicMock(embedding_model="bge-small-en-v1.5", embedding_batch_size=64),
        ),
        patch("trace_app.connectors.embed.build_engine"),
        patch("trace_app.connectors.embed.build_session_factory", return_value=lambda: session),
        patch("trace_app.connectors.embed.load_model"),
        patch("trace_app.connectors.embed.embed_batch", return_value=fake_vectors),
        patch("trace_app.connectors.embed.save_embeddings") as mock_save,
    ):
        from trace_app.connectors.embed import embed_rules

        embed_rules()

    mock_save.assert_called_once()
    _, rule_ids, vectors = mock_save.call_args[0]
    assert set(rule_ids) == {r.rule_id for r in rules}
    assert vectors == fake_vectors


def test_embed_rules_batches_by_batch_size():
    rules = [_make_rule() for _ in range(5)]
    session = _mock_session(rules)

    with (
        patch(
            "trace_app.connectors.embed.Settings",
            return_value=MagicMock(embedding_model="bge-small-en-v1.5", embedding_batch_size=2),
        ),
        patch("trace_app.connectors.embed.build_engine"),
        patch("trace_app.connectors.embed.build_session_factory", return_value=lambda: session),
        patch("trace_app.connectors.embed.load_model"),
        patch(
            "trace_app.connectors.embed.embed_batch",
            side_effect=lambda m, texts: [[0.1] * 384] * len(texts),
        ) as mock_embed,
        patch("trace_app.connectors.embed.save_embeddings"),
    ):
        from trace_app.connectors.embed import embed_rules

        embed_rules()

    # 5 rules at batch_size=2 → 3 calls: [2, 2, 1]
    assert mock_embed.call_count == 3


def test_embed_rules_loads_model_once_regardless_of_batch_count():
    rules = [_make_rule() for _ in range(4)]
    session = _mock_session(rules)

    with (
        patch(
            "trace_app.connectors.embed.Settings",
            return_value=MagicMock(embedding_model="bge-small-en-v1.5", embedding_batch_size=2),
        ),
        patch("trace_app.connectors.embed.build_engine"),
        patch("trace_app.connectors.embed.build_session_factory", return_value=lambda: session),
        patch("trace_app.connectors.embed.load_model") as mock_load,
        patch(
            "trace_app.connectors.embed.embed_batch",
            side_effect=lambda m, texts: [[0.1] * 384] * len(texts),
        ),
        patch("trace_app.connectors.embed.save_embeddings"),
    ):
        from trace_app.connectors.embed import embed_rules

        embed_rules()

    mock_load.assert_called_once()

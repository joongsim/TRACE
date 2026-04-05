from trace_app.storage.models import Base, DeadLetter, Edge, Rule


def test_rule_model_has_expected_columns() -> None:
    """Rule model should define all columns from the schema."""
    columns = {c.name for c in Rule.__table__.columns}
    expected = {
        "rule_id",
        "title",
        "abstract",
        "full_text",
        "publication_date",
        "effective_date",
        "agency",
        "document_type",
        "cfr_sections",
        "administration",
        "fr_url",
        "embedding",
        "ingested_at",
        "content_hash",
        "fr_document_number",
    }
    assert expected == columns


def test_edge_model_has_expected_columns() -> None:
    """Edge model should define all columns from the schema."""
    columns = {c.name for c in Edge.__table__.columns}
    expected = {
        "edge_id",
        "rule_id_source",
        "rule_id_target",
        "relationship_type",
        "confidence_score",
        "extraction_method",
        "created_at",
    }
    assert expected == columns


def test_dead_letter_model_has_expected_columns() -> None:
    """DeadLetter model should capture failed documents."""
    columns = {c.name for c in DeadLetter.__table__.columns}
    expected = {
        "dead_letter_id",
        "source_url",
        "raw_payload",
        "error_message",
        "failed_at",
    }
    assert expected == columns


def test_rule_table_name() -> None:
    assert Rule.__tablename__ == "rules"


def test_edge_table_name() -> None:
    assert Edge.__tablename__ == "edges"


def test_base_is_declarative_base() -> None:
    from sqlalchemy.orm import DeclarativeBase

    assert issubclass(Base, DeclarativeBase)


def test_rule_has_fr_document_number():
    from datetime import date

    rule = Rule(
        title="Test",
        full_text="body",
        publication_date=date(2021, 6, 1),
        agency="FERC",
        document_type="RULE",
        administration="Biden",
        fr_url="https://www.federalregister.gov/documents/2021/06/01/2021-11111/test",
        fr_document_number="2021-11111",
    )
    assert rule.fr_document_number == "2021-11111"

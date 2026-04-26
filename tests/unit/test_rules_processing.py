import hashlib
from datetime import date

from trace_app.processing.rules import compute_content_hash, get_administration, parse_fr_document
from trace_app.storage.models import Rule


def test_obama_era():
    assert get_administration(date(2016, 6, 15)) == "Obama"


def test_trump1_era():
    assert get_administration(date(2018, 3, 10)) == "Trump 1"


def test_biden_era():
    assert get_administration(date(2022, 11, 1)) == "Biden"


def test_trump2_era():
    assert get_administration(date(2025, 3, 1)) == "Trump 2"


def test_administration_boundary_jan_20_2017():
    assert get_administration(date(2017, 1, 19)) == "Obama"
    assert get_administration(date(2017, 1, 20)) == "Trump 1"


def test_administration_boundary_jan_20_2021():
    assert get_administration(date(2021, 1, 19)) == "Trump 1"
    assert get_administration(date(2021, 1, 20)) == "Biden"


def test_administration_boundary_jan_20_2025():
    assert get_administration(date(2025, 1, 19)) == "Biden"
    assert get_administration(date(2025, 1, 20)) == "Trump 2"


def test_before_obama_returns_unknown():
    assert get_administration(date(2000, 1, 1)) == "Unknown"


def test_content_hash_is_sha256():
    doc_number = "2021-11111"
    full_text = "This is the full text of the rule."
    expected = hashlib.sha256((doc_number + full_text).encode()).hexdigest()
    assert compute_content_hash(doc_number, full_text) == expected


def test_content_hash_differs_on_different_text():
    h1 = compute_content_hash("2021-11111", "text A")
    h2 = compute_content_hash("2021-11111", "text B")
    assert h1 != h2


def test_content_hash_differs_on_different_doc_number():
    h1 = compute_content_hash("2021-11111", "same text")
    h2 = compute_content_hash("2021-22222", "same text")
    assert h1 != h2


SAMPLE_DOC = {
    "document_number": "2021-11111",
    "title": "Electric Transmission Incentives Policy",
    "abstract": "FERC proposes new transmission incentive policy.",
    "html_url": "https://www.federalregister.gov/documents/2021/06/01/2021-11111/test",
    "body_html_url": "https://www.federalregister.gov/documents/2021/06/01/2021-11111/test/body.html",
    "publication_date": "2021-06-01",
    "effective_on": "2021-07-01",
    "type": "Rule",
    "agencies": [{"name": "Federal Energy Regulatory Commission", "id": 172}],
    "cfr_references": [{"title": 18, "part": 35}, {"title": 18, "part": 36}],
}
SAMPLE_FULL_TEXT = "This is the full text of the rule."


def test_parse_fr_document_returns_rule():
    rule = parse_fr_document(SAMPLE_DOC, SAMPLE_FULL_TEXT)
    assert isinstance(rule, Rule)


def test_parse_fr_document_maps_fields():
    rule = parse_fr_document(SAMPLE_DOC, SAMPLE_FULL_TEXT)
    assert rule.title == "Electric Transmission Incentives Policy"
    assert rule.abstract == "FERC proposes new transmission incentive policy."
    assert rule.full_text == SAMPLE_FULL_TEXT
    assert rule.publication_date == date(2021, 6, 1)
    assert rule.effective_date == date(2021, 7, 1)
    assert rule.agency == "FERC"
    assert rule.document_type == "RULE"
    assert rule.fr_url == SAMPLE_DOC["html_url"]
    assert rule.fr_document_number == "2021-11111"


def test_parse_fr_document_maps_administration():
    rule = parse_fr_document(SAMPLE_DOC, SAMPLE_FULL_TEXT)
    assert rule.administration == "Biden"


def test_parse_fr_document_maps_cfr_sections():
    rule = parse_fr_document(SAMPLE_DOC, SAMPLE_FULL_TEXT)
    assert rule.cfr_sections is not None
    assert "18 C.F.R. § 35" in rule.cfr_sections
    assert "18 C.F.R. § 36" in rule.cfr_sections


def test_parse_fr_document_sets_content_hash():
    rule = parse_fr_document(SAMPLE_DOC, SAMPLE_FULL_TEXT)
    expected = compute_content_hash("2021-11111", SAMPLE_FULL_TEXT)
    assert rule.content_hash == expected


def test_parse_fr_document_no_effective_date():
    doc = {**SAMPLE_DOC, "effective_on": None}
    rule = parse_fr_document(doc, SAMPLE_FULL_TEXT)
    assert rule.effective_date is None


def test_parse_fr_document_no_cfr_references():
    doc = {**SAMPLE_DOC, "cfr_references": []}
    rule = parse_fr_document(doc, SAMPLE_FULL_TEXT)
    assert rule.cfr_sections is None


def test_parse_fr_document_sets_ingested_at():
    rule = parse_fr_document(SAMPLE_DOC, SAMPLE_FULL_TEXT)
    assert rule.ingested_at is not None


def test_parse_fr_document_normalizes_proposed_rule():
    doc = {**SAMPLE_DOC, "type": "Proposed Rule"}
    rule = parse_fr_document(doc, SAMPLE_FULL_TEXT)
    assert rule.document_type == "PROPOSED_RULE"


def test_parse_fr_document_default_text_source():
    rule = parse_fr_document(SAMPLE_DOC, SAMPLE_FULL_TEXT)
    assert rule.text_source == "html_fallback"


def test_parse_fr_document_sets_pdf_docling_source():
    rule = parse_fr_document(SAMPLE_DOC, SAMPLE_FULL_TEXT, text_source="pdf_docling")
    assert rule.text_source == "pdf_docling"


def test_parse_fr_document_respects_agency_param():
    rule = parse_fr_document(SAMPLE_DOC, SAMPLE_FULL_TEXT, agency="DOL")
    assert rule.agency == "DOL"

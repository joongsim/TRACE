import hashlib
from datetime import date

from trace_app.processing.rules import compute_content_hash, get_administration


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

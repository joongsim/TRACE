from datetime import date

from trace_app.processing.rules import get_administration


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

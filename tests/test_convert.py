import pytest

from tagger.convert import convert_value, parse_date


@pytest.mark.parametrize("raw,exp", [
    ("1.234,56 €", "EUR1234.56"), ("EUR 12", "EUR12.00"), ("12.50", "EUR12.50"),
    (12.5, "EUR12.50"), ("1.234", "EUR1234.00"), ("12,5", "EUR12.50"),
    ("abc", None), ("", None), (None, None),
])
def test_monetary(raw, exp):
    assert convert_value("monetary", raw) == exp


@pytest.mark.parametrize("raw,exp", [
    ("2026-03-05", "2026-03-05"), ("05.03.2026", "2026-03-05"), ("2026-13-01", None),
])
def test_date(raw, exp):
    assert convert_value("date", raw) == exp
    assert parse_date(raw) == exp


def test_integer_float_boolean_string():
    assert convert_value("integer", "42") == 42
    assert convert_value("integer", "4.2") is None
    assert convert_value("float", "3,5") == 3.5
    assert convert_value("boolean", True) is True
    assert convert_value("boolean", "ja") is None
    assert convert_value("boolean", "false") is False
    assert convert_value("string", "  x ") == "x"
    assert convert_value("string", "") is None


def test_select():
    opts = [{"id": "a1", "label": "Privat"}]
    assert convert_value("select", "Privat", select_options=opts) == "a1"
    assert convert_value("select", "privat", select_options=opts) == "a1"
    assert convert_value("select", "Firma", select_options=opts) is None


def test_unknown_type():
    assert convert_value("documentlink", "x") is None

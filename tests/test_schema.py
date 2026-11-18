from tagger.schema import build_response_schema
from tagger.vocab import CustomField, Vocabulary


def make_vocab():
    return Vocabulary(
        tags={"pkv-anna": 1, "ai-review": 9},
        correspondents={"Telekom": 5, "AOK": 6},
        document_types={"Rechnung": 2},
        custom_fields=[
            CustomField(4, "Rechnungsbetrag", "monetary", []),
            CustomField(5, "Link", "documentlink", []),
            CustomField(6, "Art", "select", [{"id": "a1", "label": "Privat"}, {"id": "a2", "label": "Firma"}]),
        ],
    )


def test_schema_enums_are_existing_names():
    s = build_response_schema(make_vocab(), {"ai-review"})
    assert s["properties"]["tags"]["items"]["enum"] == ["pkv-anna"]
    enum = s["properties"]["correspondent"]["enum"]
    assert set(enum) == {"Telekom", "AOK", None}
    assert set(s["required"]) == {"title", "created", "correspondent", "document_type", "tags", "custom_fields"}


def test_schema_custom_fields_by_name():
    props = build_response_schema(make_vocab(), set())["properties"]["custom_fields"]["properties"]
    assert "Rechnungsbetrag" in props
    assert "Link" not in props
    assert props["Art"]["enum"] == ["Privat", "Firma"]


def test_lookup_case_insensitive():
    v = make_vocab()
    assert v.lookup("tags", "pkv-anna") == 1
    assert v.lookup("tags", "PKV-Anna") == 1
    assert v.lookup("tags", "nope") is None

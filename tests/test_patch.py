from tagger.patch import build_patch
from tagger.vocab import CustomField, Vocabulary

VOCAB = Vocabulary(
    tags={"pkv-anna": 1, "inbox": 5, "ai-review": 9},
    correspondents={"Telekom": 5},
    document_types={"Rechnung": 8},
    custom_fields=[CustomField(4, "Rechnungsbetrag", "monetary", [])],
)


def doc(**kw):
    base = {"title": "T", "created": "2026-01-01", "correspondent": None,
            "document_type": None, "tags": [5], "custom_fields": []}
    base.update(kw)
    return base


def ans(**kw):
    base = {"title": None, "created": None, "correspondent": None,
            "document_type": None, "tags": [], "custom_fields": {}}
    base.update(kw)
    return base


def run(d, a, edited=False, add=(), remove=()):
    return build_patch(d, a, VOCAB, user_edited=edited, add_tag_ids=list(add),
                       remove_tag_ids=list(remove), currency="EUR")


def test_untouched_overwrites():
    p, _ = run(doc(correspondent=3), ans(correspondent="Telekom"))
    assert p["correspondent"] == 5


def test_user_edited_keeps_existing_fills_empty():
    p, _ = run(doc(correspondent=3), ans(correspondent="Telekom", document_type="Rechnung"), edited=True)
    assert "correspondent" not in p
    assert p["document_type"] == 8


def test_null_answer_keeps_value():
    for t in (None, ""):
        p, _ = run(doc(), ans(title=t))
        assert "title" not in p


def test_unknown_names_dropped():
    p, notes = run(doc(), ans(tags=["pkv-anna", "made-up"], correspondent="Nobody"))
    assert 1 in p["tags"] and len(p["tags"]) == 2
    assert "correspondent" not in p
    assert any("made-up" in n for n in notes)


def test_tags_add_review_remove_inbox():
    p, _ = run(doc(tags=[7, 5]), ans(tags=["pkv-anna"]), add=[9], remove=[5])
    assert sorted(p["tags"]) == [1, 7, 9]


def test_model_suggested_inbox_cannot_survive():
    p, _ = run(doc(tags=[7, 5]), ans(tags=["inbox"]), add=[9], remove=[5])
    assert 5 not in p["tags"]


def test_custom_fields_merged():
    d = doc(custom_fields=[{"field": 2, "value": "x"}])
    p, _ = run(d, ans(custom_fields={"Rechnungsbetrag": "1.234,56 €"}))
    assert {"field": 2, "value": "x"} in p["custom_fields"]
    assert {"field": 4, "value": "EUR1234.56"} in p["custom_fields"]


def test_invalid_custom_value_not_attached():
    p, _ = run(doc(), ans(custom_fields={"Rechnungsbetrag": "n/a"}))
    assert "custom_fields" not in p


def test_user_edited_keeps_existing_custom_value():
    d = doc(custom_fields=[{"field": 4, "value": "EUR1.00"}])
    p, _ = run(d, ans(custom_fields={"Rechnungsbetrag": "5"}), edited=True)
    assert "custom_fields" not in p


def test_created_parsed():
    p, _ = run(doc(created=None), ans(created="05.03.2026"))
    assert p["created"] == "2026-03-05"

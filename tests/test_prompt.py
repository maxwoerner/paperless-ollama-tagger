from tagger.prompt import build_messages
from tagger.vocab import CustomField, Vocabulary


def test_prompt_contains_rules_and_truncates():
    vocab = Vocabulary({"a": 1}, {"Telekom": 2}, {"Rechnung": 3}, [CustomField(4, "Betrag", "monetary", [])])
    text = "x" * 6000 + "Y" + "z" * 3999
    msgs = build_messages("For invoices…", vocab, set(), text, 6000)
    assert [m["role"] for m in msgs] == ["system", "user"]
    assert "For invoices…" in msgs[0]["content"]
    assert "x" * 6000 in msgs[1]["content"]
    assert "Y" not in msgs[1]["content"]
    assert "Telekom" in msgs[1]["content"] and "Betrag" in msgs[1]["content"]


def test_prompt_hides_marker_tags():
    vocab = Vocabulary({"a": 1, "inbox": 2}, {}, {}, [])
    msgs = build_messages("", vocab, {"inbox"}, "t", 100)
    assert "inbox" not in msgs[1]["content"]

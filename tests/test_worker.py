import pytest

from tagger.config import Settings
from tagger.ollama import OllamaTimeout, OllamaUnavailable
from tagger.vocab import Vocabulary
from tagger.worker import RunResult, run_once

TAGS = {"inbox": 5, "ai-review": 9, "ai-error": 10, "pkv": 1}
VOCAB = Vocabulary(TAGS, {"Telekom": 5, "Other": 6}, {}, [])
IDS = {"inbox": 5, "review": 9, "error": 10}
ANSWER = {"title": None, "created": None, "correspondent": "Telekom",
          "document_type": None, "tags": [], "custom_fields": {}}


def mk_doc(i, content="text", **kw):
    d = {"id": i, "title": f"d{i}", "content": content, "created": "2026-01-01",
         "correspondent": None, "document_type": None, "tags": [5], "custom_fields": []}
    d.update(kw)
    return d


class FakePaperless:
    def __init__(self, docs, edited=False):
        self.docs, self.edited, self.patches = docs, edited, []

    def load_vocabulary(self):
        return VOCAB

    def pending_documents(self, inbox, error):
        yield from self.docs

    def user_edited(self, doc_id, own):
        return self.edited

    def patch_document(self, doc_id, body):
        self.patches.append((doc_id, body))


class FakeOllama:
    def __init__(self, *outcomes):
        self.outcomes, self.calls = list(outcomes), 0
        self.last_messages = self.last_schema = None

    def chat_json(self, messages, schema):
        self.calls += 1
        self.last_messages, self.last_schema = messages, schema
        o = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(o, Exception):
            raise o
        return o


@pytest.fixture
def settings(tmp_path, monkeypatch):
    rules = tmp_path / "rules.md"
    rules.write_text("rules")
    monkeypatch.setenv("PAPERLESS_URL", "http://p")
    monkeypatch.setenv("PAPERLESS_TOKEN", "t")
    monkeypatch.setenv("OLLAMA_MODEL", "m")
    monkeypatch.setenv("RULES_PATH", str(rules))
    monkeypatch.delenv("DRY_RUN", raising=False)
    return Settings(_env_file=None)


def run(settings, p, o):
    return run_once(settings, p, o, 7, IDS)


def test_happy_path_swaps_inbox_for_review(settings):
    p, o = FakePaperless([mk_doc(1)]), FakeOllama(ANSWER)
    assert run(settings, p, o) == RunResult(1, 0, False)
    (_, body), = p.patches
    assert 9 in body["tags"] and 5 not in body["tags"]
    assert body["correspondent"] == 5


def test_empty_text_skips_model(settings):
    p, o = FakePaperless([mk_doc(1, content="  ")]), FakeOllama(ANSWER)
    r = run(settings, p, o)
    assert o.calls == 0 and r.errors == 1
    (_, body), = p.patches
    assert 10 in body["tags"] and 5 in body["tags"]


def test_timeout_marks_error_and_continues(settings):
    p = FakePaperless([mk_doc(1), mk_doc(2)])
    o = FakeOllama(OllamaTimeout("t"), ANSWER)
    r = run(settings, p, o)
    assert len(p.patches) == 2 and r.errors == 1 and r.processed == 1
    assert p.patches[0][1] == {"tags": [5, 10]}


def test_unavailable_aborts_without_touching(settings):
    p, o = FakePaperless([mk_doc(1), mk_doc(2)]), FakeOllama(OllamaUnavailable("x"))
    r = run(settings, p, o)
    assert p.patches == [] and r.aborted is True


def test_history_none_treated_as_edited(settings):
    p = FakePaperless([mk_doc(1, correspondent=3)])
    p.user_edited = lambda *a: None
    run(settings, p, FakeOllama({**ANSWER, "correspondent": "Other"}))
    assert "correspondent" not in p.patches[0][1]


def test_dry_run_no_patch(settings):
    settings.dry_run = True
    p = FakePaperless([mk_doc(1)])
    r = run(settings, p, FakeOllama(ANSWER))
    assert p.patches == [] and r.processed == 1


def test_missing_rules_file_still_runs(settings, tmp_path):
    settings.rules_path = tmp_path / "nope.md"
    p = FakePaperless([mk_doc(1)])
    assert run(settings, p, FakeOllama(ANSWER)).processed == 1


def test_warns_when_prompt_exceeds_num_ctx(settings, caplog):
    import logging
    settings.num_ctx = 50
    p = FakePaperless([mk_doc(1, content="x" * 2000)])
    with caplog.at_level(logging.WARNING, logger="tagger"):
        r = run(settings, p, FakeOllama(ANSWER))
    assert r.processed == 1  # still processed, only warned
    assert any("num_ctx" in m for m in caplog.messages)


def test_no_context_warning_when_prompt_fits(settings, caplog):
    import logging
    with caplog.at_level(logging.WARNING, logger="tagger"):
        run(settings, FakePaperless([mk_doc(1)]), FakeOllama(ANSWER))
    assert not any("num_ctx" in m for m in caplog.messages)


def test_custom_trigger_tag_is_hidden_from_model_and_removed(settings, monkeypatch):
    global VOCAB
    settings.tag_inbox = "ai-analyze"
    custom = Vocabulary({**TAGS, "ai-analyze": 5}, VOCAB.correspondents, {}, [])
    monkeypatch.setitem(globals(), "VOCAB", custom)
    p, o = FakePaperless([mk_doc(1)]), FakeOllama(ANSWER)
    p.load_vocabulary = lambda: custom
    assert run(settings, p, o).processed == 1
    assert "ai-analyze" not in o.last_schema["properties"]["tags"]["items"]["enum"]
    assert "ai-analyze" not in o.last_messages[1]["content"]
    assert 5 not in p.patches[0][1]["tags"]

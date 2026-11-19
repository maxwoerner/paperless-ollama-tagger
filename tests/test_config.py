import pytest
from pydantic import ValidationError

from tagger.config import Settings

ENV = {"PAPERLESS_URL": "http://p:8000/", "PAPERLESS_TOKEN": "t", "OLLAMA_MODEL": "m"}


def make(monkeypatch, env):
    for k in list(__import__("os").environ):
        if k.upper() in {n.upper() for n in Settings.model_fields}:
            monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return Settings(_env_file=None)


def test_requires_token(monkeypatch):
    env = {k: v for k, v in ENV.items() if k != "PAPERLESS_TOKEN"}
    with pytest.raises(ValidationError):
        make(monkeypatch, env)


def test_defaults_and_parsing(monkeypatch):
    s = make(monkeypatch, ENV)
    assert s.paperless_url == "http://p:8000"
    assert s.tag_inbox == "inbox"
    assert s.max_chars == 6000
    assert s.dry_run is False
    assert s.tag_review == "ai-review"


def test_dry_run_true(monkeypatch):
    assert make(monkeypatch, {**ENV, "DRY_RUN": "true"}).dry_run is True


def test_tag_inbox_configurable(monkeypatch):
    s = make(monkeypatch, {**ENV, "TAG_INBOX": "ai-analyze"})
    assert s.tag_inbox == "ai-analyze"


@pytest.mark.parametrize("env", [
    {"TAG_INBOX": "x", "TAG_REVIEW": "x"},
    {"TAG_INBOX": "x", "TAG_ERROR": "x"},
    {"TAG_REVIEW": "same", "TAG_ERROR": "same"},
    {"TAG_INBOX": ""},
])
def test_marker_tag_names_must_be_distinct_and_non_empty(monkeypatch, env):
    with pytest.raises(ValidationError):
        make(monkeypatch, {**ENV, **env})

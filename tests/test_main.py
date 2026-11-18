from datetime import datetime

import pytest

from tagger.config import Settings
from tagger.main import next_delay, startup


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("PAPERLESS_URL", "http://p")
    monkeypatch.setenv("PAPERLESS_TOKEN", "t")
    monkeypatch.setenv("OLLAMA_MODEL", "m")
    monkeypatch.delenv("SCHEDULE_CRON", raising=False)
    return Settings(_env_file=None)


class FP:
    def __init__(self, version="2.14.0", tags=("inbox",)):
        self._v, self.tags, self.ensured = version, set(tags), None

    def version(self):
        return self._v

    def own_user_id(self):
        return 7

    def load_vocabulary(self):
        from tagger.vocab import Vocabulary
        return Vocabulary({t: i for i, t in enumerate(sorted(self.tags), 1)}, {}, {}, [])

    def ensure_tags(self, names):
        self.ensured = names
        return {n: 100 + i for i, n in enumerate(names)}


class FO:
    def __init__(self, v="0.5.7"):
        self._v = v

    def version(self):
        return self._v


def test_startup_rejects_old_ollama(settings):
    with pytest.raises(SystemExit) as e:
        startup(settings, FP(), FO("0.4.2"))
    assert e.value.code == 2


def test_startup_rejects_paperless_1x(settings):
    with pytest.raises(SystemExit) as e:
        startup(settings, FP("1.17.4"), FO())
    assert e.value.code == 2


def test_startup_ensures_marker_tags(settings):
    p = FP()
    uid, ids = startup(settings, p, FO())
    assert uid == 7
    assert p.ensured == ["ai-review", "ai-error"]
    assert set(ids) == {"inbox", "review", "error"}


def test_startup_missing_inbox_exits(settings):
    with pytest.raises(SystemExit) as e:
        startup(settings, FP(tags=("other",)), FO())
    assert e.value.code == 2


def test_next_delay_cron(settings):
    settings.schedule_cron = "0 2 * * *"
    assert next_delay(settings, datetime(2026, 11, 18, 1, 30)) == 1800


def test_next_delay_interval(settings):
    assert next_delay(settings, datetime(2026, 11, 18, 1, 30)) == 300

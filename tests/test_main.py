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

    probe = 200

    def history_probe(self):
        return self.probe

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


def test_startup_waits_for_services_to_come_up(settings):
    from tagger.paperless import PaperlessError
    from tagger.ollama import OllamaUnavailable

    class Flaky(FP):
        n = 0

        def version(self):
            Flaky.n += 1
            if Flaky.n < 3:
                raise PaperlessError("connection refused")
            return super().version()

    class FlakyO(FO):
        n = 0

        def version(self):
            FlakyO.n += 1
            if FlakyO.n < 2:
                raise OllamaUnavailable("down")
            return super().version()

    sleeps = []
    uid, ids = startup(settings, Flaky(), FlakyO(), sleep=sleeps.append)
    assert uid == 7 and "inbox" in ids
    assert len(sleeps) >= 2 and all(0 < s <= 60 for s in sleeps)


def test_startup_version_failure_does_not_retry(settings):
    sleeps = []
    with pytest.raises(SystemExit) as e:
        startup(settings, FP("1.17.4"), FO(), sleep=sleeps.append)
    assert e.value.code == 2 and sleeps == []


def test_startup_incompatible_api_exits(settings):
    from tagger.paperless import PaperlessIncompatible

    class Old(FP):
        def version(self):
            raise PaperlessIncompatible("server supports no API version >= 7")

    sleeps = []
    with pytest.raises(SystemExit) as e:
        startup(settings, Old(), FO(), sleep=sleeps.append)
    assert e.value.code == 2 and sleeps == []


@pytest.mark.parametrize("status,needle", [(400, "audit"), (403, "permission")])
def test_startup_warns_when_history_unavailable(settings, caplog, status, needle):
    import logging
    p = FP()
    p.probe = status
    with caplog.at_level(logging.WARNING, logger="tagger"):
        startup(settings, p, FO())
    msgs = " ".join(caplog.messages).lower()
    assert "user-edited" in msgs and needle in msgs


def test_startup_no_history_warning_when_ok(settings, caplog):
    import logging
    with caplog.at_level(logging.WARNING, logger="tagger"):
        startup(settings, FP(), FO())
    assert not any("history" in m.lower() for m in caplog.messages)

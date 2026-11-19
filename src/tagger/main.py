"""Entrypoint: startup checks and the scheduler loop."""
import logging
import re
import sys
import time
from datetime import datetime

from croniter import croniter

from tagger.config import Settings
from tagger.ollama import OllamaClient, OllamaUnavailable, version_at_least
from tagger.paperless import PaperlessClient, PaperlessError
from tagger.worker import run_once

log = logging.getLogger("tagger")
MIN_OLLAMA = (0, 5, 0)
MIN_PAPERLESS_MAJOR = 2


def startup(
    settings: Settings, paperless, ollama, sleep=time.sleep
) -> tuple[int, dict[str, int]]:
    """Run startup checks. Unreachable services are retried with backoff (they may
    still be booting); version and missing-inbox failures exit with code 2."""
    delay = 5.0
    while True:
        try:
            return _startup_once(settings, paperless, ollama)
        except (PaperlessError, OllamaUnavailable) as e:
            log.warning("services not reachable yet (%s); retrying in %.0fs", e, delay)
            sleep(delay)
            delay = min(delay * 2, 60.0)


def _startup_once(settings: Settings, paperless, ollama) -> tuple[int, dict[str, int]]:
    pv = paperless.version()
    ov = ollama.version()
    m = re.match(r"\d+", pv)
    if not m or int(m.group()) < MIN_PAPERLESS_MAJOR:
        log.error("Paperless-ngx %s is too old (need major >= %d)", pv, MIN_PAPERLESS_MAJOR)
        raise SystemExit(2)
    if not version_at_least(ov, MIN_OLLAMA):
        log.error("Ollama %s is too old (need >= %s)", ov, ".".join(map(str, MIN_OLLAMA)))
        raise SystemExit(2)
    user_id = paperless.own_user_id()
    inbox = paperless.load_vocabulary().tags.get(settings.tag_inbox)
    if inbox is None:
        log.error("tag %r does not exist in Paperless; create it first", settings.tag_inbox)
        raise SystemExit(2)
    markers = paperless.ensure_tags([settings.tag_review, settings.tag_error])
    return user_id, {
        "inbox": inbox,
        "review": markers[settings.tag_review],
        "error": markers[settings.tag_error],
    }


def next_delay(settings: Settings, now: datetime) -> float:
    if settings.schedule_cron:
        nxt = croniter(settings.schedule_cron, now).get_next(datetime)
        return (nxt - now).total_seconds()
    return float(settings.poll_interval_seconds)


def main() -> None:
    settings = Settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    timeout = settings.request_timeout_seconds
    paperless = PaperlessClient(settings.paperless_url, settings.paperless_token, timeout)
    ollama = OllamaClient(settings.ollama_url, settings.ollama_model, settings.num_ctx, timeout)
    user_id, tag_ids = startup(settings, paperless, ollama)
    while True:
        try:
            r = run_once(settings, paperless, ollama, user_id, tag_ids)
            log.info("run finished: processed=%d errors=%d aborted=%s", r.processed, r.errors, r.aborted)
        except Exception:  # noqa: BLE001 - the loop must survive anything
            log.exception("unexpected error during run")
        time.sleep(next_delay(settings, datetime.now()))


if __name__ == "__main__":
    main()

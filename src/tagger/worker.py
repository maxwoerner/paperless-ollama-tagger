"""One processing run: orchestration and error policy."""
import logging
from dataclasses import dataclass

from tagger.config import Settings
from tagger.ollama import OllamaBadOutput, OllamaClient, OllamaTimeout, OllamaUnavailable
from tagger.paperless import PaperlessClient, PaperlessError
from tagger.patch import build_patch
from tagger.prompt import build_messages, estimate_tokens
from tagger.schema import build_response_schema

log = logging.getLogger("tagger")


@dataclass
class RunResult:
    processed: int
    errors: int
    aborted: bool


def _read_rules(settings: Settings) -> str:
    try:
        return settings.rules_path.read_text(encoding="utf-8")
    except OSError as e:
        log.warning("cannot read rules file %s (%s); continuing with empty rules", settings.rules_path, e)
        return ""


def _mark_error(settings, paperless, doc, tag_ids, reason: str) -> None:
    tags = list(doc.get("tags") or [])
    if tag_ids["error"] not in tags:
        tags.append(tag_ids["error"])
    log.error("doc %s '%s': %s", doc["id"], doc.get("title"), reason)
    if not settings.dry_run:
        paperless.patch_document(doc["id"], {"tags": tags})


def run_once(
    settings: Settings,
    paperless: PaperlessClient,
    ollama: OllamaClient,
    own_user_id: int,
    tag_ids: dict[str, int],
) -> RunResult:
    result = RunResult(0, 0, False)
    markers = {settings.tag_inbox, settings.tag_review, settings.tag_error}
    warned_history = False
    try:
        rules = _read_rules(settings)
        vocab = paperless.load_vocabulary()
        schema = build_response_schema(vocab, markers)
        for doc in paperless.pending_documents(tag_ids["inbox"], tag_ids["error"]):
            text = doc.get("content") or ""
            if not text.strip():
                _mark_error(settings, paperless, doc, tag_ids, "no text")
                result.errors += 1
                continue

            edited = paperless.user_edited(doc["id"], own_user_id)
            if edited is None:
                edited = True
                if not warned_history:
                    log.warning("document history unavailable (audit log disabled?); "
                                "treating documents as user-edited")
                    warned_history = True

            messages = build_messages(rules, vocab, markers, text, settings.max_chars)
            est = estimate_tokens(messages, schema)
            if est > settings.num_ctx:
                log.warning(
                    "doc %s: prompt is ~%d tokens but num_ctx is %d; Ollama will cut off the "
                    "start of the prompt (the rules!). Raise NUM_CTX, lower MAX_CHARS, or "
                    "shrink the tag/correspondent lists.",
                    doc["id"], est, settings.num_ctx,
                )
            try:
                answer = ollama.chat_json(messages, schema)
            except (OllamaTimeout, OllamaBadOutput) as e:
                _mark_error(settings, paperless, doc, tag_ids, f"model failed: {type(e).__name__}: {e}")
                result.errors += 1
                continue

            body, notes = build_patch(
                doc, answer, vocab,
                user_edited=edited,
                add_tag_ids=[tag_ids["review"]],
                remove_tag_ids=[tag_ids["inbox"]],
                currency=settings.default_currency,
            )
            if settings.dry_run:
                log.info("DRY RUN doc %s patch: %s", doc["id"], body)
            else:
                paperless.patch_document(doc["id"], body)
            log.info("doc %s '%s': %s", doc["id"], doc.get("title"), "; ".join(notes) or "no changes")
            result.processed += 1
    except (OllamaUnavailable, PaperlessError) as e:
        log.error("run aborted: %s", e)
        result.aborted = True
    return result

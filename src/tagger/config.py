from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    paperless_url: str
    paperless_token: str
    ollama_url: str = "http://ollama:11434"
    ollama_model: str
    schedule_cron: str | None = None
    poll_interval_seconds: int = 300
    max_chars: int = 6000
    num_ctx: int = 8192
    request_timeout_seconds: int = 600
    rules_path: Path = Path("/config/rules.md")
    tag_inbox: str = "inbox"
    tag_review: str = "ai-review"
    tag_error: str = "ai-error"
    default_currency: str = "EUR"
    dry_run: bool = False
    log_level: str = "INFO"

    @field_validator("paperless_url", "ollama_url")
    @classmethod
    def _strip_slash(cls, v: str) -> str:
        return v.rstrip("/")

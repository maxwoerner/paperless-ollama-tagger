# Paperless Ollama Tagger

A small worker that, on a schedule, finds new Paperless-ngx documents (tagged `inbox`), asks a **local** Ollama model for their metadata under your own rules, and writes the result back to Paperless. Processed documents lose `inbox` and gain `ai-review` so you can check them.

It only ever uses tags, correspondents and document types that already exist (it creates just its own `ai-review` / `ai-error` markers). Requires Paperless-ngx ≥ 2 (the tool negotiates the newest REST API version your server supports, at least v7) and Ollama ≥ 0.5.0.

## Setup

1. **Create a dedicated Paperless user** for the tool and generate an API token for it.
   User-edit detection compares the document history's actors against the tool's own user. If you use your personal token, your manual edits look like the tool's and are overwritten.
   The history endpoint is only readable by a user who has the **audit log view permission** (`auditlog | log entry | Can view`) and who either owns the document or is a superuser. Without that, the tool cannot see who edited a document; it logs a warning at startup and treats every document as user-edited.
2. Make sure the audit log is enabled (it is by default) and that an `inbox` tag exists. If the history is unavailable, every document is treated as user-edited (only empty fields are filled).
3. Pull a small multilingual model with good JSON adherence in Ollama. Candidates to try: `qwen3:4b`, `gemma3:4b`, `llama3.2:3b`.
4. Copy `rules.example.md` to `rules.md` and write your rules; copy `docker-compose.example.yml` and fill in URL, token and model. The rules file is re-read on every run.
5. Start with `DRY_RUN=true` (logs what would be written, changes nothing). When the log looks right, set it to `false`.

```bash
docker compose -f docker-compose.example.yml up --build
```

## Behaviour

- Work queue: documents tagged `inbox` and not `ai-error`, oldest first. The **first run works through the whole current inbox** and may take hours on small hardware.
- Success: metadata written, `inbox` removed, `ai-review` added. All other tags are kept.
- Failure (no text, model timeout, unusable answer): `ai-error` added, `inbox` kept.
- To reprocess a document, add `inbox` back. To retry a failed one, remove `ai-error`.
- Values the model returns that are not in your Paperless vocabulary are dropped and logged, never written.
- If Ollama or Paperless is unreachable, the run stops and is retried at the next schedule.

Configuration is via environment variables; see `docker-compose.example.yml`.

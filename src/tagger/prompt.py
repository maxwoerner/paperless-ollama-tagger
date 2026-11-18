"""Chat messages for Ollama (pure)."""
from tagger.vocab import Vocabulary, assignable_tags

SYSTEM = """You extract metadata from scanned documents for a document management system.
The document text may be in German (OCR text, possibly noisy).
Fill the JSON fields from the document. Use ONLY values from the allowed lists given
by the user; if nothing fits, use null (or omit the custom field). Never invent names.
Dates: ISO YYYY-MM-DD. Title: short and descriptive.

Owner rules (follow them):
"""


def build_messages(
    rules: str, vocab: Vocabulary, marker_names: set[str], text: str, max_chars: int
) -> list[dict]:
    fields = "\n".join(f"- {f.name} ({f.data_type})" for f in vocab.fillable_fields()) or "(none)"
    user = (
        "Allowed correspondents: " + "; ".join(vocab.correspondents) + "\n"
        "Allowed document types: " + "; ".join(vocab.document_types) + "\n"
        "Allowed tags: " + "; ".join(assignable_tags(vocab, marker_names)) + "\n"
        "Custom fields:\n" + fields + "\n\n"
        "Document text:\n" + text[:max_chars]
    )
    return [
        {"role": "system", "content": SYSTEM + rules},
        {"role": "user", "content": user},
    ]

"""JSON schema constraining the model answer to existing vocabulary (pure)."""
from tagger.vocab import Vocabulary, assignable_tags


def build_response_schema(vocab: Vocabulary, marker_names: set[str]) -> dict:
    fields: dict[str, dict] = {}
    for f in vocab.fillable_fields():
        if f.data_type == "select":
            if not f.select_options:
                continue
            fields[f.name] = {"enum": [o["label"] for o in f.select_options]}
        elif f.data_type == "boolean":
            fields[f.name] = {"type": "boolean"}
        elif f.data_type == "integer":
            fields[f.name] = {"type": "integer"}
        else:
            fields[f.name] = {"type": "string"}
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "created": {"type": ["string", "null"]},
            "correspondent": {"enum": [*vocab.correspondents, None]},
            "document_type": {"enum": [*vocab.document_types, None]},
            "tags": {"type": "array", "items": {"enum": assignable_tags(vocab, marker_names)}},
            "custom_fields": {"type": "object", "properties": fields},
        },
        "required": ["title", "created", "correspondent", "document_type", "tags", "custom_fields"],
    }

"""Write policy: build a PATCH body from a document and a model answer (pure)."""
from tagger.convert import convert_value, parse_date
from tagger.vocab import Vocabulary


def _empty(v: object) -> bool:
    return v is None or v == ""


def build_patch(
    doc: dict,
    answer: dict,
    vocab: Vocabulary,
    *,
    user_edited: bool,
    add_tag_ids: list[int],
    remove_tag_ids: list[int],
    currency: str,
) -> tuple[dict, list[str]]:
    patch: dict = {}
    notes: list[str] = []

    def may_set(current: object) -> bool:
        return not (user_edited and not _empty(current))

    # title
    title = answer.get("title")
    if isinstance(title, str) and title.strip() and may_set(doc.get("title")):
        title = title.strip()
        if title != doc.get("title"):
            patch["title"] = title
            notes.append(f"title: {doc.get('title')!r}→{title!r}")

    # created
    created = parse_date(answer.get("created"))
    if created and may_set(doc.get("created")):
        current = str(doc.get("created") or "")[:10]
        if created != current:
            patch["created"] = created
            notes.append(f"created: {current or None}→{created}")

    # correspondent / document_type
    for key, kind in (("correspondent", "correspondents"), ("document_type", "document_types")):
        name = answer.get(key)
        if _empty(name):
            continue
        ident = vocab.lookup(kind, name)
        if ident is None:
            notes.append(f"dropped {key} {name!r} (unknown)")
            continue
        if may_set(doc.get(key)) and ident != doc.get(key):
            patch[key] = ident
            notes.append(f"{key}: {doc.get(key)}→{name}")

    # tags
    tags = list(doc.get("tags") or [])
    for name in answer.get("tags") or []:
        ident = vocab.lookup("tags", name)
        if ident is None:
            notes.append(f"dropped tag {name!r} (unknown)")
        elif ident not in tags:
            tags.append(ident)
            notes.append(f"tag +{name}")
    for ident in add_tag_ids:
        if ident not in tags:
            tags.append(ident)
    tags = [t for t in tags if t not in set(remove_tag_ids)]
    patch["tags"] = tags

    # custom fields
    existing = {cf["field"]: cf.get("value") for cf in doc.get("custom_fields") or []}
    merged = dict(existing)
    by_name = {f.name: f for f in vocab.fillable_fields()}
    raw_fields = answer.get("custom_fields") or {}
    for name, raw in raw_fields.items():
        f = by_name.get(name)
        if f is None:
            notes.append(f"dropped custom field {name!r} (unknown)")
            continue
        val = convert_value(f.data_type, raw, currency=currency, select_options=f.select_options)
        if val is None:
            if not _empty(raw):
                notes.append(f"dropped custom field {name!r} (invalid value {raw!r})")
            continue
        if not may_set(existing.get(f.id)):
            continue
        if existing.get(f.id) != val:
            merged[f.id] = val
            notes.append(f"{name}: {existing.get(f.id)}→{val}")
    if merged != existing:
        patch["custom_fields"] = [
            {"field": fid, "value": v} for fid, v in merged.items() if v is not None
        ]
    return patch, notes


def describe_patch(doc: dict, answer: dict, body: dict, vocab: Vocabulary) -> list[str]:
    """Human-readable per-field report of what a patch writes and what it skips (dry run)."""
    names = {
        kind: {v: k for k, v in getattr(vocab, kind).items()}
        for kind in ("tags", "correspondents", "document_types")
    }

    def status(key: str, current: object, suggested: object, shown_cur: object, shown_new: object) -> str:
        if key in body:
            return f"WRITE {shown_cur!r} -> {shown_new!r}"
        if _empty(suggested):
            return f"no suggestion (current {shown_cur!r})"
        if suggested == current:
            return f"unchanged ({shown_cur!r})"
        return f"SKIP, keeping {shown_cur!r}; model suggested {suggested!r}"

    lines = []
    title = answer.get("title")
    title = title.strip() if isinstance(title, str) else title
    lines.append("title: " + status("title", doc.get("title"), title, doc.get("title"), body.get("title")))

    created = parse_date(answer.get("created"))
    current = str(doc.get("created") or "")[:10] or None
    lines.append("created: " + status("created", current, created, current, body.get("created")))

    for key, kind in (("correspondent", "correspondents"), ("document_type", "document_types")):
        suggested = answer.get(key)
        ident = vocab.lookup(kind, suggested) if not _empty(suggested) else None
        if not _empty(suggested) and ident is None:
            lines.append(f"{key}: DROP unknown {suggested!r}")
            continue
        cur = names[kind].get(doc.get(key))
        new = names[kind].get(body.get(key))
        lines.append(f"{key}: " + status(key, doc.get(key), ident, cur, new))

    before = [names["tags"].get(t, t) for t in doc.get("tags") or []]
    after = [names["tags"].get(t, t) for t in body.get("tags", [])]
    lines.append(f"tags: {before} -> {after}")

    existing = {cf["field"]: cf.get("value") for cf in doc.get("custom_fields") or []}
    written = {cf["field"]: cf["value"] for cf in body.get("custom_fields", [])}
    for name, raw in (answer.get("custom_fields") or {}).items():
        f = next((f for f in vocab.fillable_fields() if f.name == name), None)
        if f is None:
            lines.append(f"custom field {name!r}: DROP unknown")
        elif f.id in written and written[f.id] != existing.get(f.id):
            lines.append(f"custom field {name!r}: WRITE {existing.get(f.id)!r} -> {written[f.id]!r}")
        else:
            lines.append(f"custom field {name!r}: SKIP/unchanged; model suggested {raw!r}, "
                         f"current {existing.get(f.id)!r}")
    return lines

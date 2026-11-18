"""Pure converters: model answer values -> Paperless custom-field values."""
import math
import re
from datetime import date, datetime

Value = str | int | float | bool | None

SUPPORTED_TYPES = frozenset(
    {"string", "longtext", "url", "date", "boolean", "integer", "float", "monetary", "select"}
)

_DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y", "%d/%m/%Y")


def parse_date(raw: object) -> str | None:
    if isinstance(raw, datetime):
        return raw.date().isoformat()
    if isinstance(raw, date):
        return raw.isoformat()
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _parse_number(raw: object, *, dot_thousands: bool) -> float | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw) if math.isfinite(raw) else None
    if not isinstance(raw, str):
        return None
    s = re.sub(r"[^\d.,\-]", "", raw)
    if not re.search(r"\d", s):
        return None
    neg = s.startswith("-")
    s = s.replace("-", "")
    if "." in s and "," in s:
        dec = "." if s.rfind(".") > s.rfind(",") else ","
        thou = "," if dec == "." else "."
        s = s.replace(thou, "").replace(dec, ".")
    elif "," in s:
        s = s.replace(",", ".")
    elif "." in s and dot_thousands and re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    if s.count(".") > 1:
        return None
    try:
        val = float(s)
    except ValueError:
        return None
    return -val if neg else val


def _select(raw: object, options: list[dict] | None) -> str | None:
    if not isinstance(raw, str) or not options:
        return None
    want = raw.strip()
    for o in options:
        if o.get("label") == want:
            return o["id"]
    for o in options:
        if str(o.get("label", "")).casefold() == want.casefold():
            return o["id"]
    return None


def convert_value(
    data_type: str,
    raw: object,
    *,
    currency: str = "EUR",
    select_options: list[dict] | None = None,
) -> Value:
    if data_type not in SUPPORTED_TYPES or raw is None:
        return None
    if data_type in ("string", "longtext"):
        if not isinstance(raw, str):
            return None
        return raw.strip() or None
    if data_type == "url":
        if not isinstance(raw, str):
            return None
        s = raw.strip()
        return s if re.match(r"https?://\S+$", s) else None
    if data_type == "date":
        return parse_date(raw)
    if data_type == "boolean":
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str) and raw.strip().lower() in ("true", "false"):
            return raw.strip().lower() == "true"
        return None
    if data_type == "integer":
        if isinstance(raw, bool):
            return None
        if isinstance(raw, int):
            return raw
        if isinstance(raw, str) and re.fullmatch(r"-?\d+", raw.strip()):
            return int(raw.strip())
        return None
    if data_type == "float":
        return _parse_number(raw, dot_thousands=False)
    if data_type == "monetary":
        val = _parse_number(raw, dot_thousands=True)
        return None if val is None else f"{currency}{val:.2f}"
    return _select(raw, select_options)

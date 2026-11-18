"""Vocabulary dataclasses and name<->id lookups (pure)."""
from dataclasses import dataclass, field
from typing import Literal

from tagger.convert import SUPPORTED_TYPES

Kind = Literal["tags", "correspondents", "document_types"]


@dataclass(frozen=True)
class CustomField:
    id: int
    name: str
    data_type: str
    select_options: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class Vocabulary:
    tags: dict[str, int]
    correspondents: dict[str, int]
    document_types: dict[str, int]
    custom_fields: list[CustomField]

    def lookup(self, kind: Kind, name: str) -> int | None:
        if not isinstance(name, str):
            return None
        table: dict[str, int] = getattr(self, kind)
        if name in table:
            return table[name]
        folded = name.strip().casefold()
        for k, v in table.items():
            if k.casefold() == folded:
                return v
        return None

    def fillable_fields(self) -> list[CustomField]:
        return [f for f in self.custom_fields if f.data_type in SUPPORTED_TYPES]


def assignable_tags(vocab: Vocabulary, marker_names: set[str]) -> list[str]:
    return [n for n in vocab.tags if n not in marker_names]

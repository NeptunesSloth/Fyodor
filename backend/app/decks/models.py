from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.textutil import clean_text

Section = Literal["commander", "companion", "main", "sideboard", "maybeboard", "tokens", "attractions", "stickers"]
DeckFormat = Literal["commander"]  # Fyodor is Commander-only; older "constructed"/"sandbox" decks read as Commander decks
Finish = Literal["nonfoil", "foil", "etched"]


def _as_commander(v: object) -> object:
    """Decks from before Constructed and Sandbox were removed (exports, packages, older clients) open as Commander decks."""
    return "commander" if v in ("constructed", "sandbox") else v


# How a printing was chosen for an entry (see docs/ARCHIDEKT_COMPATIBILITY.md §4).
Resolution = Literal["exact", "set", "fallback", "name", "manual", "unresolved"]


def _clean_labels(values: list[str], limit: int = 40) -> list[str]:
    out: list[str] = []
    for v in values:
        cleaned = clean_text(v, limit)
        if cleaned and cleaned not in out:
            out.append(cleaned)
    return out[:20]


class Requested(BaseModel):
    """What the deck source asked for, kept when it differs from what was resolved."""

    name: str | None = Field(default=None, max_length=200)
    set_code: str | None = Field(default=None, max_length=10)
    collector_number: str | None = Field(default=None, max_length=12)
    printing_id: str | None = Field(default=None, max_length=64)


class DeckEntry(BaseModel):
    section: Section = "main"
    quantity: int = Field(ge=1, le=999)
    name: str = Field(min_length=1, max_length=200)
    printing_id: str | None = Field(default=None, max_length=64)
    oracle_id: str | None = Field(default=None, max_length=64)
    set_code: str | None = Field(default=None, max_length=10)
    collector_number: str | None = Field(default=None, max_length=12)
    finish: Finish = "nonfoil"
    categories: list[str] = Field(default_factory=list, max_length=20)
    tags: list[str] = Field(default_factory=list, max_length=20)
    resolution: Resolution | None = None
    requested: Requested | None = None

    @field_validator("name")
    @classmethod
    def _clean_name(cls, v: str) -> str:
        return clean_text(v, 200)

    @field_validator("categories", "tags")
    @classmethod
    def _clean_lists(cls, v: list[str]) -> list[str]:
        return _clean_labels(v)


class DeckCategory(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    included_in_deck: bool = True
    premier: bool = False

    @field_validator("name")
    @classmethod
    def _clean(cls, v: str) -> str:
        return clean_text(v, 40) or "Category"


class DeckSource(BaseModel):
    kind: Literal["archidekt", "text", "file"] = "archidekt"
    id: str | None = Field(default=None, max_length=40)
    url: str | None = Field(default=None, max_length=300)
    name: str | None = Field(default=None, max_length=200)
    updated_at: str | None = Field(default=None, max_length=40)
    imported_at: str | None = Field(default=None, max_length=40)


class DeckIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    format: DeckFormat = "commander"
    notes: str = Field(default="", max_length=10_000)
    entries: list[DeckEntry] = Field(default_factory=list, max_length=1000)
    categories: list[DeckCategory] = Field(default_factory=list, max_length=100)

    @field_validator("format", mode="before")
    @classmethod
    def _commander_only(cls, v: object) -> object:
        return _as_commander(v)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, v: str) -> str:
        cleaned = clean_text(v, 120)
        if not cleaned:
            raise ValueError("name must not be blank")
        return cleaned

    @field_validator("notes")
    @classmethod
    def _clean_notes(cls, v: str) -> str:
        return clean_text(v, 10_000, multiline=True)


class Deck(DeckIn):
    id: str
    created_at: str
    updated_at: str
    folder: str = ""  # the shelf folder it sits in ('' = none); set on its own, so saving a list never moves a deck
    source: DeckSource | None = None
    # Normalized entries as last imported/acknowledged from the source (for "check source" diffs).
    source_snapshot: list[DeckEntry] | None = None


class Warning(BaseModel):
    level: Literal["info", "warning", "error"]
    message: str
    card: str | None = None


class UnresolvedLine(BaseModel):
    name: str
    section: str
    quantity: int
    suggestions: list[str]


class DeckImportRequest(BaseModel):
    text: str = Field(default="", max_length=200_000)
    archidekt: str | None = Field(default=None, max_length=300)  # URL or numeric deck id
    json_data: str | None = Field(default=None, max_length=5_000_000, alias="json")  # saved Archidekt deck JSON
    name: str | None = Field(default=None, max_length=120)
    format: DeckFormat | None = None
    mode: Literal["replace", "append"] = "replace"

    @field_validator("format", mode="before")
    @classmethod
    def _commander_only(cls, v: object) -> object:
        return _as_commander(v)

    model_config = {"populate_by_name": True}

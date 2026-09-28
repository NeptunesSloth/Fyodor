from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.textutil import clean_text

Section = Literal["commander", "companion", "main", "sideboard", "maybeboard", "tokens"]
DeckFormat = Literal["commander", "constructed", "sandbox"]


class DeckEntry(BaseModel):
    section: Section = "main"
    quantity: int = Field(ge=1, le=999)
    name: str = Field(min_length=1, max_length=200)
    printing_id: str | None = Field(default=None, max_length=64)
    set_code: str | None = Field(default=None, max_length=10)
    collector_number: str | None = Field(default=None, max_length=12)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, v: str) -> str:
        return clean_text(v, 200)


class DeckIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    format: DeckFormat = "commander"
    notes: str = Field(default="", max_length=10_000)
    entries: list[DeckEntry] = Field(default_factory=list, max_length=1000)

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
    text: str = Field(max_length=200_000)
    name: str | None = Field(default=None, max_length=120)
    format: DeckFormat | None = None
    mode: Literal["replace", "append"] = "replace"

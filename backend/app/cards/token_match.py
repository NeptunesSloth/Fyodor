"""-- engine token art -- which token printing of the card database pictures a token the rules engine made from its own description
("create a 3/3 colorless Robot artifact creature token"): the engine's token has no printing (its name, P/T, colours, types and
text are the engine's, ``TokenDef``), so it was drawn as a plain proxy. The printing found here is only its picture
(``TokenDef.art_id``): nothing reads characteristics from it.

A printing matches when its name (or, on a double-faced token printing, one face's name) is the token's, ignoring case, and its type
line, power, toughness and colours are the token's too. The source card's own Scryfall related tokens are looked at first (Mr. House's
Robot and Treasure), then every token printing of that name, newest first; among matches one whose picture is here (the cache, art
folders, or another printing of the same token) wins. An emblem ("Ajani, Adversary of Tyrants Emblem") matches by name and an
``Emblem`` type line.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from typing import Any

MAX_FALLBACK = 120  # token printings of the name looked at beyond the source's related tokens

_DASHES = re.compile(r"\s*[—–-]+\s*")
_SPACES = re.compile(r"\s+")


def norm_type(type_line: str | None) -> str:
    t = _SPACES.sub(" ", (type_line or "").strip().casefold())
    return _DASHES.sub(" — ", t)


Wanted = tuple[str, str, str | None, str | None, tuple[str, ...]]  # name, type line (normalized), power, toughness, colours


def wanted(name: str, type_line: str, power: str | None, toughness: str | None, colors: Iterable[str]) -> Wanted:
    return (name.strip().casefold(), norm_type(type_line), power, toughness, tuple(sorted(set(colors))))


def _face_matches(face: dict[str, Any], card: dict[str, Any], want: Wanted) -> bool:
    name, type_line, power, toughness, colors = want
    if str(face.get("name") or "").strip().casefold() != name:
        return False
    printed = norm_type(face.get("type_line") or card.get("type_line"))
    if type_line == "emblem":
        return printed.startswith("emblem")
    face_colors = face.get("colors")
    if face_colors is None:
        face_colors = card.get("colors") or []
    return printed == type_line and face.get("power") == power and face.get("toughness") == toughness \
        and tuple(sorted(set(face_colors))) == colors


def match_face(card: dict[str, Any] | None, want: Wanted) -> int | None:
    """The picture face of ``card`` (a token printing, as ``CardRepository.rules_card`` reads it) that is the wanted token, or None."""
    if not card or not card.get("is_token"):
        return None
    faces = card.get("faces") or []
    if len(faces) > 1:
        for f in faces:
            if _face_matches(f, card, want):
                return int(f.get("image_face") or 0)
        return None
    return 0 if _face_matches(card, card, want) else None


def choose(candidates: Iterable[str], card: Callable[[str], dict[str, Any] | None], want: Wanted,
           has_art: Callable[[str, int], bool]) -> tuple[str, int] | None:
    """The first matching candidate with a picture here, else the first matching one (None: none matches)."""
    first: tuple[str, int] | None = None
    for cid in candidates:
        face = match_face(card(cid), want)
        if face is None:
            continue
        if has_art(cid, face):
            return cid, face
        first = first or (cid, face)
    return first

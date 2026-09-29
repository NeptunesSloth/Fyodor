"""Archidekt deck import/export.

URL import uses Archidekt's public deck JSON (``/api/decks/{id}/``), the same endpoint
Archidekt's web app uses. It isn't officially documented, so parsing is defensive and
text/file import remains the fallback (docs/ARCHIDEKT_COMPATIBILITY.md §2). The network is
only touched when the user explicitly imports or checks a deck.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from app.decks.parser import MAX_QUANTITY, ParsedDeck, ParsedEntry, section_for_categories

log = logging.getLogger(__name__)

API_BASE = "https://archidekt.com/api/decks"
DECK_URL = "https://archidekt.com/decks/{id}"
MAX_JSON_BYTES = 5_000_000
_ID_PATTERNS = (
    re.compile(r"^\s*(\d{1,12})\s*$"),
    re.compile(r"archidekt\.com/(?:api/)?decks/(\d{1,12})", re.IGNORECASE),
)
FINISHES = {"normal": "nonfoil", "foil": "foil", "etched": "etched"}
FORMATS = {3: "commander"}  # Archidekt deckFormat codes; others map to constructed


class ArchidektError(RuntimeError):
    """Archidekt could not be reached or returned something unusable."""


def extract_deck_id(value: str) -> str | None:
    """Accept ``https://archidekt.com/decks/123/name``, ``archidekt.com/decks/123`` or ``123``."""
    for pattern in _ID_PATTERNS:
        match = pattern.search(value or "")
        if match:
            return match.group(1)
    return None


def fetch_deck(deck_id: str, *, user_agent: str, client: httpx.Client | None = None, timeout: float = 20.0) -> dict[str, Any]:
    """Fetch a public deck's JSON. Raises ``ArchidektError`` with a user-readable message."""
    own = client is None
    http = client or httpx.Client(timeout=timeout, headers={"User-Agent": user_agent, "Accept": "application/json"})
    try:
        res = http.get(f"{API_BASE}/{deck_id}/")
    except httpx.HTTPError as exc:
        raise ArchidektError(f"Could not reach Archidekt ({exc.__class__.__name__}). Paste the deck's text export instead.") from exc
    finally:
        if own:
            http.close()
    if res.status_code == 404:
        raise ArchidektError("Archidekt says this deck doesn't exist (or it is private).")
    if res.status_code in (401, 403):
        raise ArchidektError("This Archidekt deck is private. Make it public or paste its text export.")
    if res.status_code != 200:
        raise ArchidektError(f"Archidekt returned HTTP {res.status_code}. Try again later or paste the text export.")
    if len(res.content) > MAX_JSON_BYTES:
        raise ArchidektError("Archidekt returned an unexpectedly large response.")
    try:
        data = res.json()
    except ValueError as exc:
        raise ArchidektError("Archidekt returned data Fyodor could not read.") from exc
    if not isinstance(data, dict) or not isinstance(data.get("cards"), list):
        raise ArchidektError("Archidekt's response did not contain a deck. Their API may have changed; paste the text export.")
    return data


def load_json_text(text: str) -> dict[str, Any]:
    """Parse an uploaded Archidekt deck JSON file."""
    if len(text) > MAX_JSON_BYTES:
        raise ArchidektError("File is too large")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ArchidektError(f"Not valid JSON: {exc.msg}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("cards"), list):
        raise ArchidektError("This JSON file is not an Archidekt deck.")
    return data


def _get(obj: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def parse_deck_json(data: dict[str, Any]) -> ParsedDeck:
    """Convert Archidekt deck JSON into a ParsedDeck (sections, categories, exact printings)."""
    deck = ParsedDeck(name=str(data.get("name") or "").strip()[:120] or None, source_kind="archidekt")
    premier: set[str] = set()
    excluded: set[str] = set()
    for cat in data.get("categories") or []:
        if not isinstance(cat, dict) or not cat.get("name"):
            continue
        name = str(cat["name"])[:40]
        included = bool(cat.get("includedInDeck", True))
        is_premier = bool(cat.get("isPremier", False))
        deck.note_category(name, included=included, premier=is_premier)
        if is_premier:
            premier.add(name.lower())
        if not included:
            excluded.add(name.lower())

    for index, item in enumerate(data.get("cards") or []):
        if not isinstance(item, dict) or item.get("deletedAt"):
            continue
        raw_card = item.get("card")
        card: dict[str, Any] = raw_card if isinstance(raw_card, dict) else {}
        name = _get(card, "oracleCard", "name") or card.get("displayName") or _get(card, "name")
        if not name:
            deck.errors.append(f"Card #{index + 1}: no name in Archidekt data")
            continue
        categories = [str(c)[:40] for c in (item.get("categories") or []) if c]
        for c in categories:
            if c.lower() not in deck.categories:
                deck.note_category(c)
        try:
            quantity = int(item.get("quantity") or 1)
        except (TypeError, ValueError):
            quantity = 1
        section = section_for_categories(categories, premier=premier, excluded=excluded, companion=bool(item.get("companion")))
        deck.entries.append(
            ParsedEntry(
                quantity=max(1, min(quantity, MAX_QUANTITY)),
                name=str(name),
                section=section,
                set_code=(str(_get(card, "edition", "editioncode") or "").lower() or None),
                collector_number=(str(card.get("collectorNumber")) if card.get("collectorNumber") else None),
                finish=FINISHES.get(str(item.get("modifier") or "Normal").lower(), "nonfoil"),
                categories=categories,
                tags=[str(item["label"]).split(",")[0][:40]] if item.get("label") else [],
                printing_id=str(card["uid"]) if card.get("uid") else None,
                oracle_id=str(_get(card, "oracleCard", "uid")) if _get(card, "oracleCard", "uid") else None,
                line=index + 1,
            )
        )
    for custom in data.get("customCards") or []:
        if isinstance(custom, dict) and custom.get("name"):
            deck.entries.append(ParsedEntry(quantity=int(custom.get("quantity") or 1), name=str(custom["name"])[:200]))
            deck.notes.append(f"Custom card “{custom['name']}” has no Scryfall data; it is kept as an unresolved entry.")
    return deck


def deck_format(data: dict[str, Any]) -> str:
    try:
        return FORMATS.get(int(data.get("deckFormat") or 0), "constructed")
    except (TypeError, ValueError):
        return "constructed"


# ---------------------------------------------------------------------------- export

SECTION_CATEGORY = {"commander": "Commander", "sideboard": "Sideboard", "maybeboard": "Maybeboard", "companion": "Companion"}
FINISH_FLAG = {"foil": " *F*", "etched": " *E*"}


def format_archidekt_text(entries: list[dict[str, Any]]) -> str:
    """Archidekt-importable text: ``1x Name (set) number *F* [Category{flags},Other]``.

    Commander uses the premier ``{top}`` flag; sideboard/maybeboard are excluded from the
    deck with ``{noDeck}`` (and maybeboard from pricing with ``{noPrice}``), matching
    Archidekt's own export so a round trip keeps sections and categories.
    """
    order = {"commander": 0, "companion": 1, "main": 2, "sideboard": 3, "maybeboard": 4, "tokens": 5}
    lines: list[str] = []
    for e in sorted(entries, key=lambda x: order.get(str(x["section"]), 9)):
        if e["section"] == "tokens":
            continue
        line = f"{e['quantity']}x {e['name']}"
        if e.get("set_code"):
            line += f" ({e['set_code']})"
            if e.get("collector_number"):
                line += f" {e['collector_number']}"
        line += FINISH_FLAG.get(str(e.get("finish") or ""), "")
        cats = [str(c) for c in (e.get("categories") or [])]
        section_cat = SECTION_CATEGORY.get(str(e["section"]))
        if section_cat:
            cats = [c for c in cats if c.lower() != section_cat.lower()]
            flag = {"commander": "{top}", "sideboard": "{noDeck}", "maybeboard": "{noDeck}{noPrice}", "companion": ""}[
                str(e["section"])
            ]
            cats = [section_cat + flag, *cats]
        if cats:
            line += " [" + ",".join(c.replace("]", "").replace(",", " ") for c in cats) + "]"
        lines.append(line)
    return "\n".join(lines) + "\n"

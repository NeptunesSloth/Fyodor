"""Deck import/resolution and advisory validation (never enforced)."""

from __future__ import annotations

from collections import Counter
from typing import Any

from app.cards.repository import CardRepository
from app.decks.models import Deck, DeckEntry, UnresolvedLine, Warning
from app.decks.parser import ParsedDeck, parse_deck_text

COLOR_ORDER = "WUBRG"


def is_basic_or_unlimited(card: dict[str, Any] | None) -> bool:
    if not card:
        return False
    text = (card.get("oracle_text") or "").lower()
    return "Basic" in (card.get("type_line") or "") or "a deck can have any number of cards named" in text


def resolve_parsed(parsed: ParsedDeck, cards: CardRepository) -> tuple[list[DeckEntry], list[UnresolvedLine]]:
    entries: list[DeckEntry] = []
    unresolved: list[UnresolvedLine] = []
    merged: dict[tuple[str, str], DeckEntry] = {}
    for item in parsed.entries:
        card = cards.resolve(item.name, item.set_code, item.collector_number, prefer_tokens=item.section == "tokens")
        if card is None:
            unresolved.append(
                UnresolvedLine(name=item.name, section=item.section, quantity=item.quantity, suggestions=cards.suggest(item.name))
            )
            entries.append(DeckEntry(section=item.section, quantity=item.quantity, name=item.name,
                                     set_code=item.set_code, collector_number=item.collector_number))
            continue
        key = (item.section, card["id"])
        if key in merged:
            merged[key].quantity = min(999, merged[key].quantity + item.quantity)
            continue
        entry = DeckEntry(
            section=item.section,
            quantity=item.quantity,
            name=card["name"],
            printing_id=card["id"],
            set_code=card["set_code"],
            collector_number=card["collector_number"],
        )
        merged[key] = entry
        entries.append(entry)
    return entries, unresolved


def import_text(text: str, cards: CardRepository) -> tuple[ParsedDeck, list[DeckEntry], list[UnresolvedLine]]:
    parsed = parse_deck_text(text)
    entries, unresolved = resolve_parsed(parsed, cards)
    return parsed, entries, unresolved


def resolve_entries(entries: list[DeckEntry], cards: CardRepository) -> list[DeckEntry]:
    """Fill in printing ids for entries edited by hand (name only)."""
    out = []
    for entry in entries:
        if entry.printing_id and cards.get(entry.printing_id):
            out.append(entry)
            continue
        card = cards.resolve(entry.name, entry.set_code, entry.collector_number)
        if card:
            entry = entry.model_copy(update={"printing_id": card["id"], "name": card["name"],
                                             "set_code": card["set_code"], "collector_number": card["collector_number"]})
        else:
            entry = entry.model_copy(update={"printing_id": None})
        out.append(entry)
    return out


def deck_cards(deck: Deck, cards: CardRepository) -> dict[str, dict[str, Any]]:
    return cards.get_many([e.printing_id for e in deck.entries if e.printing_id])


def validate(deck: Deck, cards: CardRepository, card_data: dict[str, dict[str, Any]] | None = None) -> list[Warning]:
    """Advisory checks only. The table never refuses to start a game because of these."""
    data = card_data if card_data is not None else deck_cards(deck, cards)
    warnings: list[Warning] = []
    count = Counter[str]()
    for e in deck.entries:
        count[e.section] += e.quantity
        if not e.printing_id or e.printing_id not in data:
            warnings.append(Warning(level="error", message=f"Card not found in local database: {e.name}", card=e.name))

    playing = [e for e in deck.entries if e.section in ("main", "commander")]
    if deck.format == "commander":
        commanders = [e for e in deck.entries if e.section == "commander"]
        total = count["main"] + count["commander"]
        if not commanders:
            warnings.append(Warning(level="warning", message="No commander chosen."))
        elif count["commander"] > 2:
            warnings.append(Warning(level="warning", message=f"{count['commander']} commanders (usually 1, or 2 with partner)."))
        if total != 100:
            warnings.append(Warning(level="warning", message=f"Deck has {total} cards including commanders (Commander decks have 100)."))
        identity = {c for e in commanders if e.printing_id in data for c in data[e.printing_id]["color_identity"]}
        if commanders:
            for e in playing:
                card = data.get(e.printing_id or "")
                if card and e.section != "commander":
                    outside = set(card["color_identity"]) - identity
                    if outside:
                        colors = "".join(c for c in COLOR_ORDER if c in outside)
                        warnings.append(Warning(level="warning", message=f"{e.name} is outside the commander's color identity ({colors}).", card=e.name))
        per_name = Counter[str]()
        for e in playing:
            per_name[e.name] += e.quantity
        for name, qty in per_name.items():
            entry = next(x for x in playing if x.name == name)
            if qty > 1 and not is_basic_or_unlimited(data.get(entry.printing_id or "")):
                warnings.append(Warning(level="warning", message=f"{qty} copies of {name} (Commander is singleton).", card=name))
        for e in playing:
            card = data.get(e.printing_id or "")
            if card and card.get("commander_legal") == "banned":
                warnings.append(Warning(level="info", message=f"{e.name} is on the Commander banned list.", card=e.name))
    elif deck.format == "constructed":
        if count["main"] < 60:
            warnings.append(Warning(level="warning", message=f"Main deck has {count['main']} cards (minimum 60)."))
        if count["sideboard"] > 15:
            warnings.append(Warning(level="warning", message=f"Sideboard has {count['sideboard']} cards (maximum 15)."))
        per_name = Counter[str]()
        for e in deck.entries:
            if e.section in ("main", "sideboard"):
                per_name[e.name] += e.quantity
        for name, qty in per_name.items():
            entry = next(x for x in deck.entries if x.name == name)
            if qty > 4 and not is_basic_or_unlimited(data.get(entry.printing_id or "")):
                warnings.append(Warning(level="warning", message=f"{qty} copies of {name} (maximum 4).", card=name))
    return warnings


def summarize(deck: Deck, data: dict[str, dict[str, Any]]) -> dict[str, Any]:
    counts = Counter[str]()
    for e in deck.entries:
        counts[e.section] += e.quantity
    commanders = [e for e in deck.entries if e.section == "commander"]
    identity: set[str] = set()
    for e in commanders or [e for e in deck.entries if e.section == "main"]:
        card = data.get(e.printing_id or "")
        if card:
            identity.update(card["color_identity"])
    cover = next((e.printing_id for e in commanders if e.printing_id), None) or next(
        (e.printing_id for e in deck.entries if e.printing_id and e.section == "main"), None
    )
    return {
        "id": deck.id,
        "name": deck.name,
        "format": deck.format,
        "updated_at": deck.updated_at,
        "counts": dict(counts),
        "commanders": [e.name for e in commanders],
        "color_identity": [c for c in COLOR_ORDER if c in identity],
        "cover_id": cover,
        "unresolved": sum(1 for e in deck.entries if not e.printing_id),
    }

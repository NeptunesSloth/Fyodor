"""Deck import/resolution and advisory validation (never enforced)."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast

from app.cards.names import normalize_name
from app.cards.repository import CardRepository
from app.decks import archidekt
from app.decks.models import (
    Deck,
    DeckCategory,
    DeckEntry,
    DeckImportRequest,
    DeckIn,
    DeckSource,
    Finish,
    Requested,
    Resolution,
    Section,
    UnresolvedLine,
    Warning,
)
from app.decks.parser import ParsedDeck, ParsedEntry, parse_deck_text, section_for_categories
from app.rules import commander as cmdr

COLOR_ORDER = "WUBRG"


def is_basic_or_unlimited(card: dict[str, Any] | None) -> bool:
    if not card:
        return False
    text = (card.get("oracle_text") or "").lower()
    return "Basic" in (card.get("type_line") or "") or "a deck can have any number of cards named" in text


@dataclass
class ImportReport:
    """What an import found; shown in the preview before saving."""

    source_kind: str = "text"
    cards_total: int = 0  # quantity sum, excluding the maybeboard
    entries: int = 0
    resolved: int = 0  # quantity sum of cards resolved by name/identity
    exact_printings: int = 0
    fallbacks: list[dict[str, Any]] = field(default_factory=list)
    unresolved: list[UnresolvedLine] = field(default_factory=list)
    commanders: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    sections: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_kind": self.source_kind,
            "cards_total": self.cards_total,
            "entries": self.entries,
            "resolved": self.resolved,
            "exact_printings": self.exact_printings,
            "fallbacks": self.fallbacks,
            "unresolved": [u.model_dump() for u in self.unresolved],
            "commanders": self.commanders,
            "categories": self.categories,
            "sections": self.sections,
            "errors": self.errors,
            "notes": self.notes,
        }


def _requested(item: ParsedEntry, card: dict[str, Any] | None) -> Requested | None:
    asked = Requested(name=item.name, set_code=item.set_code, collector_number=item.collector_number, printing_id=item.printing_id)
    if card is None:
        return asked
    same_name = normalize_name(item.name) in {normalize_name(card["name"]), *(normalize_name(f["name"]) for f in card["faces"])}
    same_print = (
        (not item.printing_id or item.printing_id == card["id"])
        and (not item.set_code or item.set_code == card["set_code"])
        and (not item.collector_number or item.collector_number == card["collector_number"])
    )
    return None if same_name and same_print else asked


def resolve_parsed(parsed: ParsedDeck, cards: CardRepository) -> tuple[list[DeckEntry], ImportReport]:
    report = ImportReport(source_kind=parsed.source_kind, errors=list(parsed.errors), notes=list(parsed.notes))
    entries: list[DeckEntry] = []
    merged: dict[tuple[Any, ...], DeckEntry] = {}
    for item in parsed.entries:
        if item.bracket_token:
            token = item.bracket_token
            if cards.has_set(token):
                item.set_code = token.lower()
            else:
                item.categories = [token, *item.categories]
                parsed.note_category(token)
                if item.section == "main":
                    item.section = section_for_categories(item.categories)
            item.bracket_token = None
        card, resolution = cards.resolve_detailed(
            item.name,
            item.set_code,
            item.collector_number,
            printing_id=item.printing_id,
            oracle_id=item.oracle_id,
            prefer_tokens=item.section == "tokens",
        )
        section = cast(Section, item.section)
        if card is None:
            report.unresolved.append(
                UnresolvedLine(name=item.name, section=item.section, quantity=item.quantity, suggestions=cards.suggest(item.name))
            )
            entries.append(DeckEntry(section=section, quantity=item.quantity, name=item.name, set_code=item.set_code,
                                     collector_number=item.collector_number, finish=cast(Finish, item.finish),
                                     categories=item.categories, tags=item.tags, resolution="unresolved",
                                     requested=_requested(item, None), oracle_id=item.oracle_id))
            continue
        if resolution in ("set", "fallback"):
            wanted = " ".join(x for x in [
                (item.set_code or "").upper(), f"#{item.collector_number}" if item.collector_number else "",
            ] if x) or "the requested printing"
            report.fallbacks.append({
                "name": card["name"],
                "requested": wanted,
                "used": f"{card['set_code'].upper()} #{card['collector_number']}",
                "resolution": resolution,
            })
        key = (section, card["id"], item.finish, tuple(item.categories))
        if key in merged:
            merged[key].quantity = min(999, merged[key].quantity + item.quantity)
            continue
        entry = DeckEntry(
            section=section,
            quantity=item.quantity,
            name=card["name"],
            printing_id=card["id"],
            oracle_id=card["oracle_id"],
            set_code=card["set_code"],
            collector_number=card["collector_number"],
            finish=cast(Finish, item.finish),
            categories=item.categories,
            tags=item.tags,
            resolution=cast(Resolution, resolution),
            requested=_requested(item, card),
        )
        merged[key] = entry
        entries.append(entry)

    for e in entries:
        report.sections[e.section] = report.sections.get(e.section, 0) + e.quantity
        if e.section != "maybeboard":
            report.cards_total += e.quantity
        if e.printing_id:
            report.resolved += e.quantity
            if e.resolution == "exact":
                report.exact_printings += e.quantity
        if e.section == "commander":
            report.commanders.append(e.name)
    report.entries = len(entries)
    report.categories = [c.name for c in parsed.categories.values()]
    return entries, report


def deck_categories(parsed: ParsedDeck) -> list[DeckCategory]:
    return [DeckCategory(name=c.name, included_in_deck=c.included_in_deck, premier=c.premier) for c in parsed.categories.values()]


@dataclass
class ImportResult:
    parsed: ParsedDeck
    entries: list[DeckEntry]
    report: ImportReport
    source: DeckSource | None
    format: str | None


Fetcher = Callable[[str], dict[str, Any]]


def import_any(req: DeckImportRequest, cards: CardRepository, *, fetch: Fetcher | None = None) -> ImportResult:
    """Import from an Archidekt URL/id, an Archidekt JSON file, or deck text (any supported format)."""
    now = datetime.now(UTC).isoformat(timespec="seconds")
    if req.archidekt:
        deck_id = archidekt.extract_deck_id(req.archidekt)
        if deck_id is None:
            raise archidekt.ArchidektError("That doesn't look like an Archidekt deck URL (https://archidekt.com/decks/12345/…).")
        if fetch is None:
            raise archidekt.ArchidektError("Archidekt URL import is not available")
        data = fetch(deck_id)
        parsed = archidekt.parse_deck_json(data)
        entries, report = resolve_parsed(parsed, cards)
        source = DeckSource(kind="archidekt", id=deck_id, url=archidekt.DECK_URL.format(id=deck_id), name=parsed.name,
                            updated_at=str(data.get("updatedAt") or "") or None, imported_at=now)
        return ImportResult(parsed, entries, report, source, archidekt.deck_format(data))
    raw = req.json_data if req.json_data is not None else req.text
    if raw.lstrip().startswith("{"):
        data = archidekt.load_json_text(raw)
        parsed = archidekt.parse_deck_json(data)
        entries, report = resolve_parsed(parsed, cards)
        deck_id = str(data.get("id")) if data.get("id") else None
        source = DeckSource(kind="archidekt", id=deck_id, url=archidekt.DECK_URL.format(id=deck_id) if deck_id else None,
                            name=parsed.name, updated_at=str(data.get("updatedAt") or "") or None, imported_at=now)
        return ImportResult(parsed, entries, report, source, archidekt.deck_format(data))
    parsed = parse_deck_text(raw)
    entries, report = resolve_parsed(parsed, cards)
    return ImportResult(parsed, entries, report, None, None)


def import_text(text: str, cards: CardRepository) -> tuple[ParsedDeck, list[DeckEntry], list[UnresolvedLine]]:
    parsed = parse_deck_text(text)
    entries, report = resolve_parsed(parsed, cards)
    return parsed, entries, report.unresolved


def resolve_entries(entries: list[DeckEntry], cards: CardRepository) -> list[DeckEntry]:
    """Fill in printing/oracle ids for entries edited by hand or left behind by a card-DB update."""
    return reconcile_entries(entries, cards)[0]


def reconcile_entries(entries: list[DeckEntry], cards: CardRepository) -> tuple[list[DeckEntry], list[str]]:
    """Repair entries whose printing is missing from the local DB (e.g. after a Scryfall update).

    Stable identities are tried in order (printing id → set/number → oracle id → name), so a
    changed or removed printing never breaks a deck. Returns the entries and a note per repair.
    """
    known = cards.get_many([e.printing_id for e in entries if e.printing_id]) if cards.available else {}
    out: list[DeckEntry] = []
    notes: list[str] = []
    for entry in entries:
        card = known.get(entry.printing_id or "")
        if card is not None:
            if entry.oracle_id != card["oracle_id"]:
                entry = entry.model_copy(update={"oracle_id": card["oracle_id"]})
            out.append(entry)
            continue
        if not cards.available:
            out.append(entry)
            continue
        found, resolution = cards.resolve_detailed(entry.name, entry.set_code, entry.collector_number, oracle_id=entry.oracle_id)
        if found is None:
            out.append(entry.model_copy(update={"printing_id": None, "resolution": "unresolved"}))
            continue
        if entry.printing_id:
            notes.append(f"{entry.name}: printing {entry.printing_id[:8]}… is no longer in the card database; using "
                         f"{found['set_code'].upper()} #{found['collector_number']}.")
        out.append(entry.model_copy(update={
            "printing_id": found["id"], "oracle_id": found["oracle_id"], "name": found["name"],
            "set_code": found["set_code"], "collector_number": found["collector_number"],
            "resolution": entry.resolution if entry.resolution == "manual" else resolution,
        }))
    return out, notes


# ---------------------------------------------------------------------------- source diff


def _key(e: DeckEntry) -> tuple[str, str]:
    return (e.oracle_id or normalize_name(e.name), "maybe" if e.section == "maybeboard" else ("side" if e.section == "sideboard" else "deck"))


def _index(entries: list[DeckEntry]) -> dict[tuple[str, str], DeckEntry]:
    out: dict[tuple[str, str], DeckEntry] = {}
    for e in entries:
        k = _key(e)
        if k in out:
            out[k] = out[k].model_copy(update={"quantity": out[k].quantity + e.quantity,
                                               "categories": list(dict.fromkeys(out[k].categories + e.categories))})
        else:
            out[k] = e
    return out


def diff_entries(old: list[DeckEntry], new: list[DeckEntry]) -> dict[str, Any]:
    """Differences between two entry lists, keyed by stable card identity and board."""
    a, b = _index(old), _index(new)
    added, removed, printing, categories, sections = [], [], [], [], []
    for k, e in b.items():
        before = a.get(k)
        if before is None:
            added.append({"name": e.name, "quantity": e.quantity, "section": e.section})
            continue
        if e.quantity > before.quantity:
            added.append({"name": e.name, "quantity": e.quantity - before.quantity, "section": e.section})
        elif e.quantity < before.quantity:
            removed.append({"name": e.name, "quantity": before.quantity - e.quantity, "section": e.section})
        if e.printing_id and before.printing_id and e.printing_id != before.printing_id:
            printing.append({"name": e.name, "from": f"{(before.set_code or '').upper()} #{before.collector_number}",
                             "to": f"{(e.set_code or '').upper()} #{e.collector_number}"})
        if sorted(e.categories) != sorted(before.categories):
            categories.append({"name": e.name, "from": before.categories, "to": e.categories})
        if e.section != before.section:
            sections.append({"name": e.name, "from": before.section, "to": e.section})
    for k, e in a.items():
        if k not in b:
            removed.append({"name": e.name, "quantity": e.quantity, "section": e.section})
    changed = bool(added or removed or printing or categories or sections)
    return {"changed": changed, "added": added, "removed": removed, "printing_changed": printing,
            "category_changed": categories, "section_changed": sections}


def merge_source(local: list[DeckEntry], snapshot: list[DeckEntry], remote: list[DeckEntry]) -> tuple[list[DeckEntry], list[str]]:
    """Three-way merge: apply remote changes since ``snapshot`` without losing local edits.

    For each card: unchanged locally → take the remote version; edited locally → keep the
    local version (reported as a conflict); new remotely → add; removed remotely and
    unchanged locally → remove.
    """
    loc, snap, rem = _index(local), _index(snapshot), _index(remote)
    conflicts: list[str] = []
    result: dict[tuple[str, str], DeckEntry] = {}
    for k in dict.fromkeys([*loc, *rem]):
        l_e, s_e, r_e = loc.get(k), snap.get(k), rem.get(k)
        local_unchanged = (l_e is None and s_e is None) or (
            l_e is not None and s_e is not None and l_e.quantity == s_e.quantity and l_e.printing_id == s_e.printing_id
            and l_e.section == s_e.section
        )
        if local_unchanged:
            if r_e is not None:
                result[k] = r_e
        elif l_e is None and s_e is not None:
            if r_e is not None and (r_e.quantity != s_e.quantity or r_e.printing_id != s_e.printing_id):
                conflicts.append(f"{r_e.name}: removed locally but changed on Archidekt; kept removed")
        elif l_e is not None:
            result[k] = l_e
            if r_e is not None and s_e is not None and (r_e.quantity != s_e.quantity or r_e.printing_id != s_e.printing_id):
                conflicts.append(f"{l_e.name}: edited both locally and on Archidekt; kept the local version")
            elif r_e is None and s_e is not None:
                conflicts.append(f"{l_e.name}: removed on Archidekt but edited locally; kept")
    order = {k: i for i, k in enumerate([*loc, *rem])}
    return [result[k] for k in sorted(result, key=lambda k: order[k])], conflicts


def deck_cards(deck: DeckIn, cards: CardRepository) -> dict[str, dict[str, Any]]:
    return cards.get_many([e.printing_id for e in deck.entries if e.printing_id])


def validate(deck: DeckIn, cards: CardRepository, card_data: dict[str, dict[str, Any]] | None = None) -> list[Warning]:
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
        warnings += _commander_checks(deck, data, count, playing)
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


def _commander_checks(deck: DeckIn, data: dict[str, dict[str, Any]], count: Counter[str], playing: list[Any]) -> list[Warning]:
    """Commander deck construction (CR 903.3–903.5, 903.12e, 702.124), via ``app.rules.commander``:
    one color-identity implementation for deck checks and the rules engine."""
    warnings: list[Warning] = []
    commanders = [e for e in deck.entries if e.section == "commander"]
    commander_cards = [data[e.printing_id] for e in commanders if e.printing_id in data]
    total = count["main"] + count["commander"]
    if not commanders:
        warnings.append(Warning(level="warning", message="No commander chosen."))
    for problem in cmdr.configuration_problems(commander_cards):
        warnings.append(Warning(level="warning", message=problem + "."))
    if total != 100:
        warnings.append(Warning(level="warning", message=f"Deck has {total} cards including commanders (Commander decks have 100)."))
    identity = set(cmdr.deck_identity(commander_cards))
    land_types: set[str] = set()
    if commanders:
        for e in playing:
            card = data.get(e.printing_id or "")
            if not card or e.section == "commander":
                continue
            outside = set(cmdr.color_identity(card)) - identity
            if outside:
                colors = "".join(c for c in COLOR_ORDER if c in outside)
                warnings.append(Warning(level="warning", message=f"{e.name} is outside the commander's color identity ({colors}).", card=e.name))
                continue
            produces = cmdr.basic_land_mana(card)
            if produces and not identity and "Basic" in (card.get("type_line") or ""):
                land_types |= produces  # 903.12e: a colorless commander may run basics of one type
            elif produces - identity:
                colors = "".join(c for c in COLOR_ORDER if c in produces - identity)
                warnings.append(Warning(level="warning", message=f"{e.name} has a basic land type producing {colors}, outside the commander's color identity.", card=e.name))
        if len(land_types) > 1:
            warnings.append(Warning(level="warning", message="A colorless commander allows basic lands of only one basic land type."))
    per_name = Counter[str]()
    for e in playing:
        per_name[e.name] += e.quantity
    for name, qty in per_name.items():
        entry = next(x for x in playing if x.name == name)
        if qty > 1 and not is_basic_or_unlimited(data.get(entry.printing_id or "")):
            warnings.append(Warning(level="warning", message=f"{qty} copies of {name} (Commander is singleton).", card=name))
    for e in playing:
        card = data.get(e.printing_id or "")
        if not card:
            continue
        status = cmdr.legality(card)
        if status == "banned":
            warnings.append(Warning(level="info", message=f"{e.name} is on the Commander banned list.", card=e.name))
        elif status != "legal":
            warnings.append(Warning(level="info", message=f"{e.name} isn't legal in Commander.", card=e.name))
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
            identity.update(cmdr.color_identity(card))
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

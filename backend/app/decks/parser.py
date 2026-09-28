"""Tolerant plain-text decklist parser.

Handles the common export styles of Moxfield, Archidekt, MTGGoldfish, MTG Arena/MTGO and
hand-written lists. Parsing is purely textual; resolving names to cards happens later
against the local card database. Deck text is only ever treated as data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MAX_DECK_TEXT = 200_000
MAX_LINES = 2_000
MAX_QUANTITY = 999

SECTIONS = ("commander", "companion", "main", "sideboard", "maybeboard", "tokens")

_HEADER_ALIASES = {
    "commander": "commander",
    "commanders": "commander",
    "command zone": "commander",
    "companion": "companion",
    "companions": "companion",
    "deck": "main",
    "main": "main",
    "maindeck": "main",
    "main deck": "main",
    "mainboard": "main",
    "creatures": "main",
    "creature": "main",
    "lands": "main",
    "land": "main",
    "spells": "main",
    "instants": "main",
    "sorceries": "main",
    "artifacts": "main",
    "enchantments": "main",
    "planeswalkers": "main",
    "battles": "main",
    "other": "main",
    "sideboard": "sideboard",
    "side": "sideboard",
    "sb": "sideboard",
    "maybeboard": "maybeboard",
    "maybe": "maybeboard",
    "considering": "maybeboard",
    "tokens": "tokens",
    "token": "tokens",
}

_QTY = re.compile(r"^(?P<qty>\d{1,4})\s*[xX]?\s+(?P<rest>.+)$")
_QTY_SUFFIX = re.compile(r"^(?P<rest>.+?)\s+[xX](?P<qty>\d{1,4})$")
_SET_NUM = re.compile(
    r"\s+[\(\[](?P<set>[A-Za-z0-9]{2,6})[\)\]](?:\s+(?P<num>[A-Za-z0-9★†\-]{1,10}))?(?=\s|$)"
)
_CATEGORY = re.compile(r"\s+\[(?P<cats>[^\]]*)\]\s*$")
_CARET_TAG = re.compile(r"\s+\^[^^]*\^\s*$")
_FLAGS = re.compile(r"\s+\*(?P<flag>[A-Za-z]+)\*")
_HASH_TAG = re.compile(r"\s+#\s*!?\s*(?P<tag>[A-Za-z][\w ]*)$")
_ARENA_ABOUT = re.compile(r"^name\s+(?P<name>.+)$", re.IGNORECASE)


@dataclass
class ParsedEntry:
    quantity: int
    name: str
    section: str = "main"
    set_code: str | None = None
    collector_number: str | None = None
    finish: str = "nonfoil"
    line: int = 0
    categories: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    # "[XYZ]" with a single token could be a set code or an Archidekt category; the resolver
    # decides (known set code -> set, otherwise category).
    bracket_token: str | None = None
    printing_id: str | None = None  # exact Scryfall printing (Archidekt JSON)
    oracle_id: str | None = None  # Scryfall oracle id (Archidekt JSON)

    @property
    def foil(self) -> bool:
        return self.finish != "nonfoil"


@dataclass
class CategoryInfo:
    name: str
    included_in_deck: bool = True
    premier: bool = False


@dataclass
class ParsedDeck:
    name: str | None = None
    entries: list[ParsedEntry] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    categories: dict[str, CategoryInfo] = field(default_factory=dict)
    source_kind: str = "text"

    def count(self, section: str) -> int:
        return sum(e.quantity for e in self.entries if e.section == section)

    def note_category(self, name: str, *, included: bool | None = None, premier: bool | None = None) -> None:
        info = self.categories.get(name.lower())
        if info is None:
            info = self.categories[name.lower()] = CategoryInfo(name=name)
        if included is not None:
            info.included_in_deck = included
        if premier is not None:
            info.premier = premier


class DeckTextTooLarge(ValueError):
    pass


def _header_section(line: str) -> str | None:
    text = line.strip().strip("/#").strip()
    text = re.sub(r"\s*\(\d+\)\s*$", "", text)  # "Creatures (24)"
    text = text.rstrip(":").strip().lower()
    return _HEADER_ALIASES.get(text)


_CATEGORY_FLAG = re.compile(r"\{([^}]*)\}")
COMMANDER_NAMES = {"commander", "commanders"}
SIDEBOARD_NAMES = {"sideboard", "side"}
MAYBE_NAMES = {"maybeboard", "maybe", "considering"}


def split_category(raw: str) -> tuple[str, set[str]]:
    """``"Maybeboard{noDeck}{noPrice}"`` -> ``("Maybeboard", {"nodeck", "noprice"})``."""
    flags = {f.strip().lower() for f in _CATEGORY_FLAG.findall(raw)}
    return _CATEGORY_FLAG.sub("", raw).strip(), flags


def section_for_categories(
    categories: list[str], *, premier: set[str] | None = None, excluded: set[str] | None = None, companion: bool = False
) -> str:
    """Map Archidekt categories to a deck section (docs/ARCHIDEKT_COMPATIBILITY.md §3)."""
    lowered = [c.lower() for c in categories]
    premier = premier or set()
    excluded = excluded or set()
    if companion or "companion" in lowered:
        return "companion"
    if lowered and (lowered[0] in COMMANDER_NAMES or lowered[0] in premier):
        return "commander"
    if any(c in COMMANDER_NAMES for c in lowered):
        return "commander"
    if any(c in SIDEBOARD_NAMES for c in lowered):
        return "sideboard"
    if any(c in MAYBE_NAMES for c in lowered) or (lowered and lowered[0] in excluded):
        return "maybeboard"
    return "main"


def parse_line(raw: str, deck: ParsedDeck | None = None) -> ParsedEntry | None:
    """Parse one card line. Returns None when the line holds no card.

    ``deck`` (optional) collects category flags such as ``{top}`` / ``{noDeck}``.
    """
    text = raw.strip()
    if not text:
        return None
    section: str | None = None
    if re.match(r"^sb:\s*", text, re.IGNORECASE):
        section = "sideboard"
        text = re.sub(r"^sb:\s*", "", text, flags=re.IGNORECASE)

    quantity = 1
    match = _QTY.match(text)
    if match:
        quantity, text = int(match.group("qty")), match.group("rest")
    else:
        suffix = _QTY_SUFFIX.match(text)
        if suffix:
            quantity, text = int(suffix.group("qty")), suffix.group("rest")

    finish = "nonfoil"
    tags: list[str] = []
    caret = _CARET_TAG.search(text)
    if caret:
        for part in caret.group(0).strip().strip("^").split(","):
            part = part.strip()
            if part and not re.fullmatch(r"#[0-9a-fA-F]{3,8}", part):
                tags.append(part)
        text = text[: caret.start()]

    raw_categories: list[str] = []
    bracket_token: str | None = None
    cat_match = _CATEGORY.search(text)
    if cat_match:
        inner = cat_match.group("cats").strip()
        has_set_before = _SET_NUM.search(text[: cat_match.start()]) is not None
        if not has_set_before and re.fullmatch(r"[A-Za-z0-9]{2,6}", inner):
            bracket_token = inner  # set code or single category; decided by the resolver
        else:
            raw_categories = [c.strip() for c in re.split(r"[,;]", inner) if c.strip()]
        text = text[: cat_match.start()]

    for flag in _FLAGS.findall(text):
        f = flag.upper()
        if f in ("F", "FOIL"):
            finish = "foil"
        elif f in ("E", "ETCHED"):
            finish = "etched"
        elif f in ("CMDR", "COMMANDER"):
            section = "commander"
    text = _FLAGS.sub("", text)

    tag = _HASH_TAG.search(text)
    if tag:
        if "commander" in tag.group("tag").lower():
            section = "commander"
        text = text[: tag.start()]

    set_code = number = None
    set_match = _SET_NUM.search(text)
    if set_match:
        set_code = set_match.group("set").lower()
        number = set_match.group("num")
        text = text[: set_match.start()] + text[set_match.end() :]

    categories: list[str] = []
    premier: set[str] = set()
    excluded: set[str] = set()
    for raw_cat in raw_categories:
        name, flags = split_category(raw_cat)
        if not name:
            continue
        categories.append(name)
        if "top" in flags:
            premier.add(name.lower())
        if "nodeck" in flags:
            excluded.add(name.lower())
        if deck is not None:
            deck.note_category(
                name,
                included=False if "nodeck" in flags else None,
                premier=True if "top" in flags else None,
            )
    if categories and section is None:
        mapped = section_for_categories(categories, premier=premier, excluded=excluded)
        section = mapped if mapped != "main" else None

    name = re.sub(r"\s+", " ", text).strip().strip("\"'")
    if not name or not re.search(r"[A-Za-z]", name):
        return None
    return ParsedEntry(
        quantity=max(1, min(quantity, MAX_QUANTITY)),
        name=name,
        section=section or "main",
        set_code=set_code,
        collector_number=number,
        finish=finish,
        categories=categories,
        tags=tags,
        bracket_token=bracket_token,
    )


def parse_deck_text(text: str) -> ParsedDeck:
    if len(text) > MAX_DECK_TEXT:
        raise DeckTextTooLarge(f"Deck text is too large (max {MAX_DECK_TEXT:,} characters)")
    deck = ParsedDeck()
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if len(lines) > MAX_LINES:
        raise DeckTextTooLarge(f"Deck text has too many lines (max {MAX_LINES:,})")

    current: str | None = None
    saw_header = False
    blocks: list[list[ParsedEntry]] = [[]]
    in_about = False
    for lineno, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line:
            if blocks[-1]:
                blocks.append([])
            in_about = False
            continue
        if line.lower().rstrip(":") == "about":
            in_about = True
            continue
        if in_about:
            about = _ARENA_ABOUT.match(line)
            if about:
                deck.name = about.group("name").strip()[:120]
            continue
        header = _header_section(line)
        if header and not _QTY.match(line):
            current, saw_header = header, True
            if blocks[-1]:
                blocks.append([])
            continue
        if line.startswith(("//", "#")):
            continue
        entry = parse_line(line, deck)
        if entry is None:
            deck.errors.append(f"Line {lineno}: could not read {line[:60]!r}")
            continue
        entry.line = lineno
        if entry.section == "main" and current:
            entry.section = current
        deck.entries.append(entry)
        blocks[-1].append(entry)

    if not saw_header:
        _apply_layout_heuristics(deck, [b for b in blocks if b])
    return deck


def _apply_layout_heuristics(deck: ParsedDeck, blocks: list[list[ParsedEntry]]) -> None:
    """Infer commander / sideboard sections from blank-line layout when no headers exist."""
    if len(blocks) < 2 or any(e.section != "main" for e in deck.entries):
        return
    qty = [sum(e.quantity for e in b) for b in blocks]
    total = sum(qty)
    first, last = blocks[0], blocks[-1]
    if len(blocks) == 2 and qty[-1] <= 2 and 98 <= total <= 101:
        _move(last, "commander")
        deck.notes.append(f"Treated {', '.join(e.name for e in last)} as commander (short final block).")
    elif qty[0] <= 2 and 98 <= total <= 101:
        _move(first, "commander")
        deck.notes.append(f"Treated {', '.join(e.name for e in first)} as commander (short first block).")
    elif len(blocks) == 2 and qty[0] >= 40 and qty[1] <= 15:
        _move(last, "sideboard")
        deck.notes.append("Treated the final block as the sideboard.")


def _move(entries: list[ParsedEntry], section: str) -> None:
    for entry in entries:
        entry.section = section


def format_deck_text(entries: list[dict[str, object]]) -> str:
    """Export a deck as plain text with section headers (round-trips through the parser)."""
    out: list[str] = []
    for section in SECTIONS:
        rows = [e for e in entries if e["section"] == section]
        if not rows:
            continue
        out.append({"main": "Deck"}.get(section, section.capitalize()))
        for e in rows:
            suffix = ""
            if e.get("set_code"):
                suffix = f" ({str(e['set_code']).upper()})"
                if e.get("collector_number"):
                    suffix += f" {e['collector_number']}"
            out.append(f"{e['quantity']} {e['name']}{suffix}")
        out.append("")
    return "\n".join(out).strip() + "\n"

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
    foil: bool = False
    line: int = 0


@dataclass
class ParsedDeck:
    name: str | None = None
    entries: list[ParsedEntry] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def count(self, section: str) -> int:
        return sum(e.quantity for e in self.entries if e.section == section)


class DeckTextTooLarge(ValueError):
    pass


def _header_section(line: str) -> str | None:
    text = line.strip().strip("/#").strip()
    text = re.sub(r"\s*\(\d+\)\s*$", "", text)  # "Creatures (24)"
    text = text.rstrip(":").strip().lower()
    return _HEADER_ALIASES.get(text)


def parse_line(raw: str) -> ParsedEntry | None:
    """Parse one card line. Returns None when the line holds no card."""
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

    foil = False
    text = _CARET_TAG.sub("", text)
    categories: list[str] = []
    cat_match = _CATEGORY.search(text)
    # A trailing [..] after a set/number (or containing a comma / non-set text) is an Archidekt category.
    if cat_match and (_SET_NUM.search(text[: cat_match.start()]) or not re.fullmatch(r"[A-Za-z0-9]{2,6}", cat_match.group("cats"))):
        categories = [c.strip() for c in re.split(r"[,;]", cat_match.group("cats")) if c.strip()]
        text = text[: cat_match.start()]

    for flag in _FLAGS.findall(text):
        f = flag.upper()
        if f in ("F", "E", "FOIL", "ETCHED"):
            foil = True
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

    for cat in categories:
        name = re.sub(r"\{.*?\}", "", cat).strip().lower()
        if name in ("commander", "commanders"):
            section = "commander"
        elif name in ("maybeboard", "maybe", "considering"):
            section = section or "maybeboard"
        elif name in ("sideboard", "side"):
            section = section or "sideboard"
        elif name == "companion":
            section = section or "companion"

    name = re.sub(r"\s+", " ", text).strip().strip("\"'")
    if not name or not re.search(r"[A-Za-z]", name):
        return None
    return ParsedEntry(
        quantity=max(1, min(quantity, MAX_QUANTITY)),
        name=name,
        section=section or "main",
        set_code=set_code,
        collector_number=number,
        foil=foil,
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
        entry = parse_line(line)
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

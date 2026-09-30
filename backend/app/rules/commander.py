"""Commander card rules: color identity, who can be a commander, and commander pairings.

One implementation, used by deck checks, the lobby, the rules engine and the coverage reports.
Researched against the Comprehensive Rules effective 2026-09-25 (``data/rules``):

* 903.3: a commander is a **legendary** card that is a creature card, a Vehicle card, or a
  Spacecraft card with power/toughness; 903.3a: or a card that says it can be your commander.
* 903.4: color identity = colors of mana symbols in the mana cost and rules text (reminder text
  ignored, 903.4c), colors from characteristic-defining abilities and color indicators, both
  faces of double-faced cards (903.4d) and alternative characteristics such as adventures
  (903.4e).
* 702.124: partner abilities (partner, partner—[text], partner with [name], choose a
  Background, Doctor's companion); different partner abilities can't be combined, and never
  more than two commanders.

``legal_in_commander`` (a card may be in a Commander deck) and ``can_be_commander`` are separate
questions: many legal cards can't lead a deck, and a Background can only lead next to a
"choose a Background" commander.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.rules.oracle import strip_reminders

COLORS = ("W", "U", "B", "R", "G")
_SYMBOL = re.compile(r"\{([^}]+)\}")
_COLOR_WORDS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_COLOR_LIST = r"(?:white|blue|black|red|green)(?:(?:, | and |, and )(?:white|blue|black|red|green))*"


def _cda_colors(text: str, name: str) -> set[str]:
    """Color-setting characteristic-defining abilities about the card itself (604.3): "~ is all
    colors." / "~ is blue and red." (a line of its own, naming the card)."""
    out: set[str] = set()
    names = {n for n in (name, name.split(",")[0], "this card") if n}
    for line in text.splitlines():
        line = line.strip()
        for n in names:
            if line.lower() == f"{n.lower()} is all colors.":
                out |= set(COLORS)
            m = re.fullmatch(re.escape(n) + rf" is (?P<c>{_COLOR_LIST})\.", line, re.I)
            if m:
                out |= {_COLOR_WORDS[w.lower()] for w in re.findall(r"white|blue|black|red|green", m.group("c"), re.I)}
    return out


def _faces(data: dict[str, Any]) -> list[dict[str, Any]]:
    return list(data.get("faces") or data.get("card_faces") or [])


def _symbol_colors(text: str) -> set[str]:
    out: set[str] = set()
    for sym in _SYMBOL.findall(text or ""):
        for part in sym.split("/"):
            if part in COLORS:
                out.add(part)
    return out


def _rules_text(text: str | None) -> str:
    return "\n".join(strip_reminders(line) for line in (text or "").splitlines())


def color_identity(data: dict[str, Any]) -> tuple[str, ...]:
    """903.4: a card's color identity, from its printed data (all faces)."""
    colors: set[str] = set()
    parts = [data, *_faces(data)]
    for part in parts:
        cost = _symbol_colors(str(part.get("mana_cost") or ""))
        colors |= cost
        text = _rules_text(part.get("oracle_text"))  # reminder text doesn't count (903.4c)
        colors |= _symbol_colors(text)
        if "doesn't affect its color identity" in text or "doesn’t affect its color identity" in text:
            continue  # e.g. Fallaji Wayfarer: "… is all colors. This ability doesn't affect its color identity."
        colors |= _cda_colors(text, str(part.get("name") or data.get("name") or ""))
        # A color indicator (204): colors the card has that its mana cost doesn't explain. (A
        # multi-face card's combined colors are checked face by face.)
        if part is not data or not _faces(data):
            colors |= {c for c in (part.get("colors") or []) if c in COLORS} - cost if not _devoid(text) else set()
    return tuple(c for c in COLORS if c in colors)


def _devoid(text: str) -> bool:
    return any(line.strip().lower().startswith("devoid") for line in text.splitlines())


BASIC_TYPES = {"Plains": "W", "Island": "U", "Swamp": "B", "Mountain": "R", "Forest": "G"}


def basic_land_mana(data: dict[str, Any]) -> set[str]:
    """903.5d: colors of mana a card's basic land types let it produce (checked separately from
    color identity when building a deck)."""
    out: set[str] = set()
    for part in [data, *_faces(data)]:
        type_line = str(part.get("type_line") or "")
        if "Land" not in type_line or "—" not in type_line:
            continue
        subtypes = type_line.split("—", 1)[1].split()
        out |= {BASIC_TYPES[t] for t in subtypes if t in BASIC_TYPES}
    return out


# Objects that are never deck cards, whatever a legality field says: sticker sheets (CR 123.1 —
# stickers are not cards; the sheets stay outside the game), emblems, tokens, dungeons, planes,
# phenomena, schemes, Vanguard, conspiracies and Theros hero cards. (Attractions *are* cards:
# they are legal in Commander and live in the Attraction deck.)
NON_DECK_TYPES = frozenset({"Stickers", "Emblem", "Token", "Dungeon", "Plane", "Phenomenon", "Scheme", "Vanguard",
                            "Conspiracy", "Hero"})

# Set types whose cards aren't sanctioned paper Magic unless a printing proves it (Alchemy
# rebalances and Arena-only designs, Un-sets, memorabilia such as gold-bordered tournament decks,
# tokens and minigames). Used only when the card data lacks Scryfall's legalities.
UNSANCTIONED_SET_TYPES = frozenset({"alchemy", "funny", "memorabilia", "token", "minigame"})

# The Commander banned list (2026-09-28 card data), for card data that lacks legalities. When
# legalities are stored they win, so a stale copy here can't unban or ban anything in the DB.
COMMANDER_BANNED = frozenset({
    "Adriana's Valor", "Advantageous Proclamation", "Amulet of Quoz", "Ancestral Recall", "Assemble the Rank and Vile",
    "Backup Plan", "Balance", "Black Lotus", "Brago's Favor", "Bronze Tablet", "Channel", "Chaos Orb", "Cleanse",
    "Contract from Below", "Crusade", "Darkpact", "Demonic Attorney", "Dockside Extortionist", "Double Stroke",
    "Echoing Boon", "Emissary's Ploy", "Emrakul, the Aeons Torn", "Erayo, Soratami Ascendant", "Falling Star",
    "Fastbond", "Flash", "Golos, Tireless Pilgrim", "Griselbrand", "Hired Heist", "Hold the Perimeter", "Hullbreacher",
    "Hymn of the Wilds", "Immediate Action", "Imprison", "Incendiary Dissent", "Invoke Prejudice",
    "Iona, Shield of Emeria", "Iterative Analysis", "Jeweled Bird", "Jeweled Lotus", "Jihad", "Karakas",
    "Leovold, Emissary of Trest", "Library of Alexandria", "Limited Resources", "Mana Crypt", "Mox Emerald", "Mox Jet",
    "Mox Pearl", "Mox Ruby", "Mox Sapphire", "Muzzio's Preparations", "Nadu, Winged Wisdom", "Natural Unity",
    "Paradox Engine", "Power Play", "Pradesh Gypsies", "Primeval Titan", "Prophet of Kruphix", "Rebirth",
    "Recurring Nightmare", "Rofellos, Llanowar Emissary", "Secret Summoning", "Secrets of Paradise",
    "Sentinel Dispatch", "Shahrazad", "Sovereign's Realm", "Stone-Throwing Devils", "Summoner's Bond",
    "Sundering Titan", "Sylvan Primordial", "Tempest Efreet", "Time Vault", "Time Walk", "Timmerian Fiends", "Tinker",
    "Tolarian Academy", "Trade Secrets", "Unexpected Potential", "Upheaval", "Weight Advantage", "Worldknit",
    "Yawgmoth's Bargain",
})

_DIGITAL_GAMES = frozenset({"arena", "mtgo"})


def _is_non_deck_object(data: dict[str, Any]) -> bool:
    for part in [data, *_faces(data)]:
        type_line = str(part.get("type_line") or "")
        supertypes = type_line.split("—", 1)[0].split("//", 1)[0].split()
        if any(t in NON_DECK_TYPES for t in supertypes):
            return True
    return False


def _inferred_legality(data: dict[str, Any]) -> str:
    """Commander legality from a printing's other Scryfall fields, for card data without
    ``legalities``: the banned list, digital-only printings (Arena/MTGO only), Alchemy rebalanced
    "A-" cards, unsanctioned set types (Un-sets count only with the oval eternal-legal stamp),
    acorn-stamped, silver- and gold-bordered cards."""
    name = str(data.get("name") or "")
    if name in COMMANDER_BANNED or name.split(" // ", 1)[0] in COMMANDER_BANNED:
        return "banned"
    if name.startswith("A-") or any(str(f.get("name") or "").startswith("A-") for f in _faces(data)):
        return "not_legal"
    if data.get("security_stamp") == "acorn" or data.get("border_color") in ("silver", "gold"):
        return "not_legal"
    if data.get("digital"):
        games = {str(g) for g in (data.get("games") or [])}
        if not games or games <= _DIGITAL_GAMES:
            return "not_legal"
    set_type = str(data.get("set_type") or "")
    if set_type in UNSANCTIONED_SET_TYPES:
        if set_type == "funny" and data.get("security_stamp") == "oval":
            return "legal"  # Unfinity's eternal-legal cards carry the oval stamp; acorn ones don't
        return "not_legal"
    return "legal"


def legality(data: dict[str, Any]) -> str:
    """"legal", "banned" or "not_legal" in Commander.

    Follows the card data: the stored Scryfall ``legalities.commander`` decides when it is there
    (any other status, e.g. "restricted", is "not_legal"). Objects that can't be deck cards at all
    (``NON_DECK_TYPES``, e.g. Unfinity sticker sheets, which the bulk data marks "legal") are never
    legal. Without stored legalities, ``_inferred_legality`` uses the printing's other fields."""
    if "commander_legal" in data:
        return str(data.get("commander_legal") or "not_legal")
    legal = data.get("legalities")
    if isinstance(legal, dict) and "commander" in legal:
        status = str(legal.get("commander") or "not_legal")
        status = status if status in ("legal", "banned") else "not_legal"
    else:
        status = _inferred_legality(data)
    if status == "legal" and _is_non_deck_object(data):
        return "not_legal"  # a stored "banned" (e.g. conspiracies) is kept as the data says
    return status


def legal_in_commander(data: dict[str, Any]) -> bool:
    return legality(data) == "legal"


def _front(data: dict[str, Any]) -> dict[str, Any]:
    faces = _faces(data)
    if faces and data.get("layout") in ("transform", "modal_dfc", "flip", "meld", "reversible_card"):
        return faces[0]
    return data


@dataclass(frozen=True)
class Pairing:
    """How a card may share the command zone (702.124). ``kind``: "partner", "partner_text",
    "partner_with", "choose_background", "background", "doctors_companion", "time_lord_doctor"."""

    kind: str
    detail: str = ""  # the partner—[text] text, or the partner-with name


def pairings(data: dict[str, Any]) -> list[Pairing]:
    out: list[Pairing] = []
    front = _front(data)
    text = _rules_text(front.get("oracle_text") or data.get("oracle_text"))
    type_line = str(front.get("type_line") or data.get("type_line") or "")
    for line in text.splitlines():
        line = line.strip()
        if m := re.fullmatch(r"Partner with (?P<name>.+?)\s*", line):
            out.append(Pairing("partner_with", m.group("name").strip()))
        elif m := re.fullmatch(r"Partner—(?P<text>.+?)\s*", line):
            out.append(Pairing("partner_text", m.group("text").strip()))
        elif line == "Partner":
            out.append(Pairing("partner"))
        elif line.lower() == "choose a background":
            out.append(Pairing("choose_background"))
        elif line.lower() == "doctor’s companion" or line.lower() == "doctor's companion":
            out.append(Pairing("doctors_companion"))
    if "Legendary" in type_line and "Enchantment" in type_line and "Background" in type_line:
        out.append(Pairing("background"))
    if "Legendary" in type_line and "Creature" in type_line and re.search(r"—\s*Time Lord Doctor\s*$", type_line):
        out.append(Pairing("time_lord_doctor"))
    return out


def can_be_commander(data: dict[str, Any]) -> bool:
    """903.3 / 903.3a: may this card be (one of) a deck's commander(s)? Backgrounds count, but only
    next to a "choose a Background" commander (checked by ``pair_problem``)."""
    front = _front(data)
    type_line = str(front.get("type_line") or data.get("type_line") or "")
    if "can be your commander" in _rules_text(front.get("oracle_text") or data.get("oracle_text")):
        return True
    if "Legendary" not in type_line:
        return False
    if "Creature" in type_line or re.search(r"\bVehicle\b", type_line):
        return True
    if re.search(r"\bSpacecraft\b", type_line) and front.get("power") is not None and front.get("toughness") is not None:
        return True
    return any(p.kind == "background" for p in pairings(data))


def pair_problem(a: dict[str, Any], b: dict[str, Any]) -> str | None:
    """Why these two cards can't be designated together as commanders (None if they can)."""
    pa, pb = pairings(a), pairings(b)
    name_a, name_b = str(a.get("name") or ""), str(b.get("name") or "")
    kinds_a, kinds_b = {p.kind for p in pa}, {p.kind for p in pb}
    if "partner" in kinds_a and "partner" in kinds_b:
        return None
    texts_a = {p.detail for p in pa if p.kind == "partner_text"}
    if texts_a & {p.detail for p in pb if p.kind == "partner_text"}:
        return None
    if any(p.kind == "partner_with" and p.detail == name_b for p in pa) and \
            any(p.kind == "partner_with" and p.detail == name_a for p in pb):
        return None
    if ("choose_background" in kinds_a and "background" in kinds_b) or ("choose_background" in kinds_b and "background" in kinds_a):
        return None
    if ("doctors_companion" in kinds_a and "time_lord_doctor" in kinds_b) or \
            ("doctors_companion" in kinds_b and "time_lord_doctor" in kinds_a):
        return None
    if not (pa or pb):
        return f"{name_a} and {name_b} have no partner ability"
    return f"{name_a} and {name_b} can't be commanders together (their partner abilities don't match)"


def configuration_problems(commanders: list[dict[str, Any]]) -> list[str]:
    """Advisory checks for a deck's commander designation (never blocks a game)."""
    problems = []
    if len(commanders) > 2:
        problems.append(f"{len(commanders)} commanders: at most two (with a partner ability)")
    for c in commanders:
        if not can_be_commander(c):
            problems.append(f"{c.get('name')} can't be a commander (it isn't a legendary creature, Vehicle or Spacecraft)")
        elif len(commanders) == 1 and any(p.kind == "background" for p in pairings(c)) and \
                "can be your commander" not in str(c.get("oracle_text") or ""):
            problems.append(f"{c.get('name')} is a Background: it needs a commander with “Choose a Background”")
    if len(commanders) == 2:
        problem = pair_problem(commanders[0], commanders[1])
        if problem:
            problems.append(problem)
    return problems


def deck_identity(commanders: list[dict[str, Any]]) -> tuple[str, ...]:
    """The combined color identity of a deck's commanders (702.124c)."""
    colors = {c for card in commanders for c in color_identity(card)}
    return tuple(c for c in COLORS if c in colors)

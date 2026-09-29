"""Oracle text → a list of classified ability lines.

This is *parsing as data*: it never evaluates anything. The classification feeds coverage
(which parts of a card the engine automates) and gives every ability a stable index, so a client
can say ``activate_ability(card, 2)``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

AbilityKind = Literal["keywords", "mana", "activated", "loyalty", "triggered", "static", "spell"]

_REMINDER = re.compile(r"\s*\([^()]*\)")
_MANA_SYMBOL = r"\{(?:[WUBRGCS]|\d+)\}"
# "{T}: Add {G}." / "{T}: Add {R} or {G}." / "{T}: Add {C}{C}." / "{T}: Add one mana of any color."
_MANA_ABILITY = re.compile(
    rf"^\{{T\}}: Add (?:{_MANA_SYMBOL}(?:{_MANA_SYMBOL})*(?:(?:, | or |, or ){_MANA_SYMBOL})*|one mana of any color)\.$"
)
_LOYALTY = re.compile(r"^[+−-]?\d+: |^[+−-]X: ")
_TRIGGER = re.compile(r"^(?:[A-Z][A-Za-z' ]+ — )?(When|Whenever|At) ")  # an ability word ("Landfall — ") may lead
_COST_START = re.compile(
    r"^(\{[^}]+\}|Sacrifice|Tap|Untap|Discard|Pay|Remove|Exile|Return|Put|Reveal|Mill|Collect|Forage|[Ee]quip|Crew|"
    r"Channel|Cycling|Ninjutsu|Boast|Exhaust)"
)

# Keyword *abilities* a line may consist of (lower case, parameters stripped). Keyword actions
# (scry, surveil, proliferate…) and ability words are deliberately absent: in a spell they are the
# effect. Being listed only means "recognised"; whether it's automated is up to coverage.
KEYWORDS = frozenset({
    "flying", "reach", "vigilance", "trample", "deathtouch", "lifelink", "first strike", "double strike", "haste",
    "defender", "menace", "hexproof", "indestructible", "flash", "shroud", "fear", "intimidate", "skulk", "prowess",
    "protection", "ward", "equip", "enchant", "cycling", "kicker", "flashback", "convoke", "delve", "cascade",
    "affinity", "storm", "partner", "partner with", "changeling", "landwalk", "islandwalk", "swampwalk",
    "forestwalk", "mountainwalk", "plainswalk", "exalted", "undying", "persist", "wither", "infect", "toxic",
    "annihilator", "evolve", "extort", "unearth", "embalm", "eternalize", "afflict", "riot", "escape", "mutate",
    "companion", "foretell", "disturb", "daybound", "nightbound", "training", "casualty", "blitz", "backup",
    "bargain", "craft", "disguise", "offspring", "saddle", "crew", "ninjutsu", "morph", "megamorph", "suspend",
    "rebound", "overload", "surge", "emerge", "madness", "miracle", "dash", "evoke", "bestow", "outlast", "dethrone",
    "fabricate", "improvise", "ascend", "mentor", "jump-start", "spectacle", "encore", "boast", "sneak",
    "horsemanship", "shadow", "banding", "rampage", "flanking", "bushido", "provoke", "fading", "vanishing", "echo",
    "cumulative upkeep", "buyback", "entwine", "splice", "retrace", "replicate", "soulbond", "unleash", "battle cry",
    "living weapon", "totem armor", "umbra armor", "fortify", "reconfigure", "for mirrodin!", "prototype",
    "read ahead", "ravenous", "squad", "enlist", "decayed", "cleave", "compleated", "demonstrate", "hideaway",
    "myriad", "melee", "friends forever", "choose a background", "doctor's companion", "space sculptor", "gift",
    "impending", "plot", "spree", "freerunning", "start your engines!", "station", "warp", "job select", "tiered",
    "firebending", "mobilize", "harmonize", "renew",
})

_PARAM = re.compile(r"(\{[^}]*\}|\d+|—.*$|\bfrom\b.*$| with .*$|walk$)")


@dataclass(frozen=True)
class AbilityText:
    index: int
    text: str
    kind: AbilityKind
    keywords: tuple[str, ...] = ()  # for "keywords" lines: the normalised keyword names
    cost: str | None = None  # for activated/loyalty abilities: the text before the colon
    intrinsic: bool = False  # granted by a basic land type rather than printed


def strip_reminders(text: str) -> str:
    previous = None
    while previous != text:  # nested parentheses are rare but exist
        previous, text = text, _REMINDER.sub("", text)
    return text


_TYPECYCLING = re.compile(r"^((?:basic )?[a-z]+cycling)(?: \{|$)")


def keyword_name(piece: str) -> str | None:
    """"Protection from red" → "protection"; "Ward {2}" → "ward"; "Equip {1}" → "equip"."""
    raw = piece.strip().rstrip(".").lower()
    if not raw:
        return None
    if raw in KEYWORDS:
        return raw
    base = _PARAM.sub("", raw).strip(" —-")
    if base in KEYWORDS:
        return base
    first_two = " ".join(raw.split()[:2])
    if first_two in KEYWORDS:
        return first_two
    first = raw.split()[0]
    if first in KEYWORDS:
        return first
    typecycling = _TYPECYCLING.match(raw)  # "Swampcycling {2}", "Basic landcycling {1}{G}", "Wizardcycling {3}"
    return typecycling[1] if typecycling else None


def _keywords_line(line: str) -> tuple[str, ...] | None:
    pieces = [p for p in re.split(r"[,;]\s*", line) if p.strip()]
    names = [keyword_name(p) for p in pieces]
    if names and all(names):
        return tuple(n for n in names if n)
    return None


_ADD_MANA = re.compile(r"^(?P<cost>[^:]+): Add ")


def classify(line: str, *, spell: bool) -> tuple[AbilityKind, tuple[str, ...], str | None]:
    if _MANA_ABILITY.match(line):
        return "mana", (), "{T}"
    m = _ADD_MANA.match(line)
    if m and not _LOYALTY.match(line) and "target" not in line:
        return "mana", (), m.group("cost")
    kws = _keywords_line(line)
    if kws is not None and ":" not in line:
        return "keywords", kws, None
    if _LOYALTY.match(line):
        return "loyalty", (), line.split(":", 1)[0]
    if _TRIGGER.match(line):
        return "triggered", (), None
    if ":" in line:
        cost = line.split(":", 1)[0]
        if _COST_START.match(cost) and len(cost) < 120:
            return "activated", (), cost
    if kws is not None:  # keyword with a cost after a colon, e.g. "Equip: {2}" style oddities
        return "keywords", kws, None
    return ("spell" if spell else "static"), (), None


def parse_abilities(oracle_text: str | None, *, spell: bool = False) -> list[AbilityText]:
    """Split Oracle text into classified ability lines (reminder text removed).

    ``spell`` is true for instants and sorceries: their non-keyword lines are the spell's effect."""
    if not oracle_text:
        return []
    out: list[AbilityText] = []
    for raw in strip_reminders(oracle_text).split("\n"):
        line = raw.strip()
        if not line:
            continue
        kind, kws, cost = classify(line, spell=spell)
        out.append(AbilityText(index=len(out), text=line, kind=kind, keywords=kws, cost=cost))
    return out

"""Protection (CR 702.16): DEBT — damage, enchanting/equipping, blocking and targeting.

A permanent with protection from a quality can't be Damaged by sources with that quality (the
damage is prevented), Enchanted or Equipped by such permanents (they fall off as a state-based
action), Blocked by such creatures, or Targeted by such spells and abilities. Only the qualities
parsed here count; a wording we don't understand (“protection from the chosen player”) leaves
the keyword unsupported so the card stays PARTIAL instead of being enforced wrongly.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from app.rules.characteristics import Characteristics
from app.rules.creature_types import CREATURE_TYPES

Quality = Callable[[Characteristics], bool]

COLORS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
CARD_TYPES = {"artifacts": "Artifact", "creatures": "Creature", "enchantments": "Enchantment", "instants": "Instant",
              "sorceries": "Sorcery", "planeswalkers": "Planeswalker", "lands": "Land", "battles": "Battle",
              "kindreds": "Kindred"}  # (kindreds: wave 42C, "the card type of your choice")
# Irregular plurals of creature types that appear after "protection from".
_PLURALS = {"elves": "Elf", "dwarves": "Dwarf", "wolves": "Wolf", "werewolves": "Werewolf", "thieves": "Thief",
            "mice": "Mouse", "fungi": "Fungus", "sphinxes": "Sphinx", "foxes": "Fox", "djinn": "Djinn"}

_LINE = re.compile(r"^protection (from .+)$")
_PIECE = re.compile(r"\s*(?:,\s*)?(?:and\s+)?from\s+")


def _one(word: str, recipient: Characteristics | None = None) -> Quality | None:
    from app.rules import source_qualities

    raw = word.strip().rstrip(".")
    if (bound := source_qualities.predicate(raw if raw.lower().startswith("card name ") else raw.lower())) is not None:
        return bound
    word = raw.lower()
    if word in COLORS:
        c = COLORS[word]
        return lambda ch: c in ch.colors
    if word == "multicolored":
        return lambda ch: len(ch.colors) > 1
    if word == "monocolored":
        return lambda ch: len(ch.colors) == 1
    if word in ("each color", "all colors"):
        return lambda ch: bool(ch.colors)
    if word == "everything":
        return lambda ch: True
    if player_match := re.fullmatch(r'player[: ]([\w-]+)', word):
        player = player_match[1]
        return lambda ch: (ch.targeting_controller or ch.object_controller or ch.object_owner) == player

    if m := re.fullmatch(r"permanents with ([a-z][a-z -]*) counters on them", word):
        kind = m[1]
        return lambda ch: ch.on_battlefield and kind in ch.object_counters
    if word == "creatures your opponents control":
        player = (recipient.object_controller or recipient.object_owner) if recipient is not None else None
        return lambda ch: bool(player and "Creature" in ch.types and (controller := ch.object_controller or ch.object_owner)
                               and controller != player)
    if word in ("instant spells", "sorcery spells"):
        kind = "Instant" if word == "instant spells" else "Sorcery"
        return lambda ch: ch.is_spell and kind in ch.types
    if m := re.fullmatch(r"creatures controlled by player ([\w-]+)", word):
        player = m[1]
        return lambda ch: "Creature" in ch.types and (ch.object_controller or ch.object_owner) == player
    if word in CARD_TYPES:
        t = CARD_TYPES[word]
        return lambda ch: t in ch.types
    if word == "ring-bearers":
        return lambda ch: ch.object_ring_bearer
    if word == "colorless":
        return lambda ch: not ch.colors
    # -- keywords (wave 15E) -- "God creatures", "non-Spirit creatures", "legendary creatures", "mana value 3 or greater" (702.16a)
    m = re.fullmatch(r"(non-)?([a-z]+(?:[ -][a-z]+)*) creatures", word)  # (wave 53B: a type of two words, "Time Lord creatures": the type a permanent chose, chosen.protection_line)
    if m and m[2] == "legendary" and not m[1]:
        return lambda ch: "Legendary" in ch.supertypes and "Creature" in ch.types
    if m and m[2] not in CARD_TYPES and (m[2].title() in CREATURE_TYPES):
        sub, neg = m[2].title(), bool(m[1])
        return lambda ch: "Creature" in ch.types and ((sub in ch.subtypes) != neg)
    m = re.fullmatch(r"mana value (\d+) or (greater|less)", word)
    if m:
        n, more = int(m[1]), m[2] == "greater"
        return lambda ch: (ch.mana_value >= n) if more else (ch.mana_value <= n)
    if word == "snow":
        return lambda ch: "Snow" in ch.supertypes
    if word == "arcane":
        return lambda ch: "Arcane" in ch.subtypes
    sub = _PLURALS.get(word) or (word[:-1] if word.endswith("s") else word).capitalize()
    if sub in CREATURE_TYPES:  # "Goblins", "Dragons", "Elves" (CR 205.3m)
        return lambda ch: sub in ch.subtypes
    return None


def parse(line: str, recipient: Characteristics | None = None) -> list[Quality] | None:
    """The qualities of one “Protection from …” keyword piece, or None if not understood."""
    m = _LINE.match(line.strip().rstrip(".").lower())
    if not m:
        return None
    words = [w for w in _PIECE.split(m[1]) if w.strip()]
    if recipient is not None and recipient.lost:  # -- wave 110F -- "loses protection from black" (Cephalid Snitch): only that quality goes (613.1f)
        words = [w for w in words if f"protection from {w.strip().rstrip('.')}" not in recipient.lost]
    out = [_one(w, recipient) for w in words]
    return [q for q in out if q is not None] if out and all(out) else None


def hexproof(line: str, recipient: Characteristics | None = None) -> list[Quality] | None:
    """-- keywords (wave 44D) -- the qualities of "hexproof from white and from black" / "… from artifacts, creatures, and enchantments" (702.11d, 702.11f: one
    ability for each quality), or None if one isn't understood."""
    m = re.search(r"hexproof from (.+)$", line.strip().rstrip(".").lower())
    if m and m[1] == "activated and triggered abilities":
        return [lambda source: source.is_ability]
    out = [_one(w, recipient) for w in re.split(r",\s*(?:and\s+)?(?:from\s+)?|\s+and\s+(?:from\s+)?", m[1])] if m else []
    return [q for q in out if q is not None] if out and all(out) else None


def hexproof_from(ch: Characteristics, source: Characteristics | None) -> bool:
    """-- keywords (wave 44D) -- 702.11d: does ``ch`` have hexproof from a quality ``source`` (the spell, or the source of the ability) has? An effect that makes it
    lose hexproof loses these too (702.11e)."""
    if source is None or "hexproof from" not in ch.keywords or "hexproof" in ch.lost:
        return False
    return any(q(source) for ab in ch.abilities if ab.kind == "keywords" and "hexproof from" in ab.keywords for q in hexproof(ab.text, ch) or [])


def _pieces(line: str) -> list[str]:
    """The protection pieces of a keyword line ("Flying, protection from red" → ["protection from red"])."""
    return [p.strip() for p in re.split(r",(?!\s*(?:and\s+)?from\b)|;", line) if p.strip().lower().startswith("protection")]  # (wave 50H: "from blue, from black, and from red" is one keyword's qualities)


def qualities(ch: Characteristics, exempt: Callable[[str], bool] | None = None) -> list[Quality]:
    """Everything this object has protection from (its printed protection keyword lines). ``exempt``: -- attached events (wave 25D) --
    702.16n, "This effect doesn't remove this Aura": skips the instances whose ``keeps`` it accepts."""
    if "protection" not in ch.keywords:
        return []
    out: list[Quality] = []
    for ab in ch.abilities:
        if ab.kind == "keywords" and "protection" in ab.keywords and not (exempt and ab.keeps and exempt(ab.keeps)):
            for piece in _pieces(ab.text):
                out += parse(piece, ch) or []
    return out


def supported(line: str) -> bool:
    """Is every protection piece on this keyword line one the engine enforces?"""
    pieces = _pieces(line)
    return bool(pieces) and all(parse(p) is not None for p in pieces)


def protected_from(ch: Characteristics, source: Characteristics | None, exempt: Callable[[str], bool] | None = None) -> bool:
    """Does ``ch`` have protection from ``source`` (a spell, ability source, creature or attachment)?"""
    if source is None:
        return False
    return any(q(source) for q in qualities(ch, exempt))

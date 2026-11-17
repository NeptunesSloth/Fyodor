"""-- rulebreaker -- a commander's "Rulebreaker —" line bends Commander deck construction (Mystery Booster 2 commanders: The
Everforger, Seluma, Arvad, Valko, Hadran, Daxiver, Whtz, Grizzlegom, Maular, Tolabow, The Unluckiest Planeswalker).

Three wordings are read; anything else is ignored (the deck check then stays the plain 903.4 one):

* "A deck with this commander can have <cards> of any color identity[ and any basic land cards]." and
  "If ~ is your Commander, you may include <cards> of any color in your deck regardless of color identity." —
  ``<cards>`` is a list joined by "and" of type words, subtypes and an optional "of power N or greater" /
  "with mana value N or greater".
* "A deck with this commander can have any land cards." / "… has no maximum deck size."
* Tolabow: "the color identity of instant and sorcery cards in your deck can include one color of your choice not in your
  commander's color identity" — one extra color, the same for every such card.

Deck construction only (advisory, like every deck check): nothing here changes the game.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

CARD_TYPES = {"artifact", "creature", "enchantment", "instant", "sorcery", "land", "planeswalker", "battle", "kindred", "tribal"}
PERMANENT_TYPES = {"Artifact", "Creature", "Enchantment", "Land", "Planeswalker", "Battle"}

_ANY_IDENTITY = re.compile(r"can have (?P<what>.+?) of any color identity", re.I)
_REGARDLESS = re.compile(r"you may include (?P<what>.+?)(?: of any color)? in your deck regardless of color identity", re.I)
_EXTRA_COLOR = re.compile(r"the color identity of (?P<what>.+?) cards in your deck can include one color of your choice", re.I)

Predicate = Callable[[dict[str, Any]], bool]


@dataclass
class Allowance:
    """What a deck's commanders' Rulebreaker lines allow."""

    any_identity: list[Predicate] = field(default_factory=list)  # cards that may be of any color identity
    one_extra_color: list[Predicate] = field(default_factory=list)  # cards whose identity may add one shared color
    any_basics: bool = False
    any_lands: bool = False
    no_max_size: bool = False

    def free(self, card: dict[str, Any]) -> bool:
        """A card that may ignore the commander's color identity."""
        types = _types(card)
        if self.any_lands and "Land" in types[0]:
            return True
        if self.any_basics and "Land" in types[0] and "Basic" in types[2]:
            return True
        return any(p(card) for p in self.any_identity)

    def extra(self, card: dict[str, Any]) -> bool:
        return any(p(card) for p in self.one_extra_color)


def _types(card: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    """(card types, subtypes, supertypes) of every face."""
    types: set[str] = set()
    subtypes: set[str] = set()
    supers: set[str] = set()
    for half in str(card.get("type_line") or "").split("//"):
        left, _, right = half.partition("—")
        for word in left.split():
            (types if word.lower() in CARD_TYPES else supers).add(word)
        subtypes.update(right.split())
    return types, subtypes, supers


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _item(text: str) -> Predicate | None:
    """One "<words>[ of power N or greater| with mana value N or greater]" item."""
    text = re.sub(r"^(all|each)\s+", "", text.strip(), flags=re.I)
    limit: tuple[str, int] | None = None
    m = re.search(r"\s+(?:of power (\d+) or greater|with mana value (\d+) or greater)$", text, re.I)
    if m:
        limit = ("power", int(m.group(1))) if m.group(1) else ("cmc", int(m.group(2)))
        text = text[: m.start()]
    permanent = bool(re.search(r"permanents?$", text, re.I))
    text = re.sub(r"\s+(cards|permanents)$", "", text, flags=re.I)
    need_types: set[str] = set()
    need_sub: set[str] = set()
    need_super: set[str] = set()
    for word in text.split():
        bare = re.sub(r"s$", "", word) if word.lower().rstrip("s") in CARD_TYPES else word
        if bare.lower() in CARD_TYPES:
            need_types.add(bare.capitalize())
        elif bare.lower() == "legendary":
            need_super.add("Legendary")
        elif bare.lower() in ("permanent", "permanents"):
            permanent = True
        elif bare[:1].isupper():
            need_sub.add(re.sub(r"s$", "", bare) if bare not in ("Phyrexian",) else bare)
        else:
            return None  # a word this reading doesn't know: no allowance from it
    if not (need_types or need_sub or need_super):
        return None

    def ok(card: dict[str, Any]) -> bool:
        types, subtypes, supers = _types(card)
        if not need_types <= types or not need_super <= supers:
            return False
        if need_sub and not need_sub <= subtypes:
            return False
        if permanent and not types & PERMANENT_TYPES:
            return False
        if limit is not None:
            value = _number(card.get(limit[0]))
            if limit[0] == "power" and value is None:
                faces = card.get("faces") or []
                value = _number(faces[0].get("power")) if faces else None
            if value is None or value < limit[1]:
                return False
        return True

    return ok


def _list(text: str) -> list[Predicate] | None:
    # "artifact creature and Equipment" → two items; "instant and sorcery" → two items
    items = [_item(part) for part in re.split(r"\s+and\s+|,\s*", text) if part.strip()]
    return None if any(i is None for i in items) else [i for i in items if i is not None]


def allowance(commanders: list[dict[str, Any]]) -> Allowance:
    """What the commanders' Rulebreaker lines allow (empty when none has one)."""
    allow = Allowance()
    for card in commanders:
        for line in str(card.get("oracle_text") or "").split("\n"):
            if not line.lower().startswith("rulebreaker"):
                continue
            body = line.split("—", 1)[-1].strip()
            if re.search(r"can have any land cards\.", body, re.I):
                allow.any_lands = True
            if re.search(r"has no maximum deck size\.", body, re.I):
                allow.no_max_size = True
            if re.search(r"any basic land cards", body, re.I):
                allow.any_basics = True
            for pattern, into in ((_ANY_IDENTITY, allow.any_identity), (_REGARDLESS, allow.any_identity), (_EXTRA_COLOR, allow.one_extra_color)):
                m = pattern.search(body)
                if m:
                    preds = _list(m.group("what"))
                    if preds:
                        into.extend(preds)
    return allow

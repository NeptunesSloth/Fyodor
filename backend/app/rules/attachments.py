"""Auras and Equipment (CR 303.4, 301.5, 702.5, 702.6, 701.3).

* **Enchant** (702.5a) restricts what an Aura spell can target (303.4a) and what the Aura can
  enchant. The Aura spell targets as it's cast; as it resolves it enters attached to that object
  (303.4f). If the target is illegal by then, the spell doesn't resolve (608.2b) and goes to its
  owner's graveyard (303.4g). Only the "Enchant …" wordings mapped below are automated; any other
  wording ("Enchant player", "Enchant creature card in a graveyard") stays manual.
* **Equip** (702.6a): "[Cost]: Attach this permanent to target creature you control. Activate
  only as a sorcery." Only equip abilities with a plain mana cost are automated. An Equipment
  that's also a creature can't equip (301.5c).
* Leaving an illegal host is a state-based action (704.5m / 704.5n, app/rules/sba.py).
"""

from __future__ import annotations

import re

from app.rules.characteristics import Characteristics

# "Enchant …" → the target selector (app/rules/targets.py) the Aura spell uses.
ENCHANT_SELECTORS = {
    "creature": "creature",
    "creature you control": "creature_you_control",
    "creature an opponent controls": "creature_opponent_controls",
    "creature you don't control": "creature_opponent_controls",
    "land": "land",
    "land you control": "land_you_control",
    "artifact": "artifact",
    "artifact you control": "artifact_you_control",
    "enchantment": "enchantment",
    "permanent": "permanent",
    "nonland permanent": "nonland_permanent",
    "planeswalker": "planeswalker",
    "creature or planeswalker": "creature_or_planeswalker",
    "artifact or creature": "artifact_or_creature",
}

_ENCHANT = re.compile(r"^enchant (?P<what>.+?)\.?$", re.IGNORECASE)
EQUIP = re.compile(r"^equip (?P<cost>(?:\{[^}]+\})+)\.?$", re.IGNORECASE)


def enchant_lines(ch: Characteristics) -> list[str]:
    return [ab.text for ab in ch.abilities if ab.kind == "keywords" and "enchant" in ab.keywords]


def enchant_selector_of(line: str) -> str | None:
    m = _ENCHANT.match(line.strip())
    return ENCHANT_SELECTORS.get(m["what"].strip().lower().replace("’", "'")) if m else None


def enchant_selector(ch: Characteristics) -> str | None:
    """The selector an Aura spell targets with, or None if its enchant ability isn't automated
    (several different enchant abilities must all apply, 702.5c: left manual)."""
    lines = enchant_lines(ch)
    if not lines or "Aura" not in ch.subtypes:
        return None
    found = {enchant_selector_of(line) for line in lines}
    return found.pop() if len(found) == 1 and None not in found else None


def equip_cost(ch: Characteristics, index: int) -> str | None:
    """The mana cost of the equip ability on ability line ``index`` (702.6a), or None."""
    for ab in ch.abilities:
        if ab.index == index and ab.kind == "keywords" and "equip" in ab.keywords:
            m = EQUIP.match(ab.text.strip())
            return m["cost"] if m else None
    return None


def supported_keyword(kw: str, line: str) -> bool:
    if kw == "enchant":
        return enchant_selector_of(line) is not None
    if kw == "equip":
        return EQUIP.match(line.strip()) is not None
    return False

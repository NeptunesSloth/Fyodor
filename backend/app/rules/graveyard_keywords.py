"""-- keywords (wave 15E) -- keywords that are activated abilities working from a graveyard (113.6m), carried out as the
activated ability the Comprehensive Rules (2026-09-25) says each one is:

* 702.128a embalm — "[Cost], Exile this card from your graveyard: Create a token that's a copy of this card, except it's white, it
  has no mana cost, and it's a Zombie in addition to its other types. Activate only as a sorcery."
* 702.129a eternalize — "…, except it's black, it's 4/4, it has no mana cost, and it's a Zombie in addition to its other types.
  Activate only as a sorcery."

The keyword line becomes a synthetic ``AbilityText`` (kind "activated") that the activation path (casting.activate_ability and
the list of what can be activated) uses for a card in its owner's graveyard; its definition is the ordinary grammar's reading of
the sentence (scripts.define: the token copy with its exceptions, copying.parse_excepts).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.rules.oracle import AbilityText

if TYPE_CHECKING:
    from app.rules.characteristics import Characteristics

_LINE = re.compile(r"^(?P<kw>embalm|eternalize|encore)(?: |—)(?P<cost>(?:\{[^}]+\})+(?:, Discard a card)?)$", re.IGNORECASE)  # (wave 49C: "Eternalize—{2}{W}{W}, Discard a card." — 702.129a, a cost of two parts; the discard comes from the hand, not the card itself, which is in the graveyard)
_EFFECT = {
    "embalm": "Create a token that's a copy of the card exiled to activate this ability, except it's white, it has no mana cost, and it's a Zombie in addition to its "
              "other types. Activate only as a sorcery.",
    # -- casting extras (wave 18E) -- 702.141a encore (the tokens: scripts._encore_copies; "They" are the tokens just made)
    "encore": "For each opponent, create a token that's a copy of the card exiled to activate this ability that attacks that opponent this turn "
              "if able. They gain haste. Sacrifice them at the beginning of the next end step. Activate only as a sorcery.",
    "eternalize": "Create a token that's a copy of the card exiled to activate this ability, except it's black, it's 4/4, it has no mana cost, and it's a Zombie in addition "
                  "to its other types. Activate only as a sorcery.",
}


def parse(line: str) -> tuple[str, str] | None:
    m = _LINE.fullmatch(re.sub(r"\s*\(.*?\)", "", line).strip().rstrip("."))
    return (m["kw"].lower(), m["cost"]) if m else None


def ability(ch: Characteristics, index: int) -> AbilityText | None:
    """The activated ability the embalm / eternalize keyword on ability line ``index`` is, or None."""
    for ab in ch.abilities:
        if ab.index == index and ab.kind == "keywords" and ab.keywords and ab.keywords[0] in _EFFECT and len(ab.keywords) == 1:
            found = parse(ab.text)
            if found is None:
                return None
            kw, cost = found
            return AbilityText(index=index, kind="activated", cost=f"{cost}, Exile this card from your graveyard",
                               text=f"{cost}, Exile this card from your graveyard: {_EFFECT[kw]}")
    return None


def supported(kw: str, line: str) -> bool:
    from app.rules import scripts
    from app.rules.characteristics import Characteristics

    found = parse(line)
    if found is None or found[0] != kw:
        return False
    ab = AbilityText(index=0, kind="activated", cost=f"{found[1]}, Exile this card from your graveyard",
                     text=f"{found[1]}, Exile this card from your graveyard: {_EFFECT[kw]}")
    probe = Characteristics(name="\u0000", abilities=(ab,), types=frozenset({"Creature"}))
    return scripts.define(ab, probe) is not None

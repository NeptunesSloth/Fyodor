"""-- casting extras (wave 18E) -- prototype (CR 702.160, 718), researched against the stored Comprehensive Rules (2026-09-25).

* 702.160a / 718.3 — as the card is cast the player chooses to cast it normally or prototyped (``CastSpell.prototype``).
* 718.3a-b — a prototyped spell, and the permanent it becomes, have only the alternative mana cost, power and toughness (and so the
  colors of that cost and its mana value); every other characteristic is the card's own (718.5). :func:`overlay` is applied by
  ``layers`` to an object whose payment record says ``prototyped`` (the record follows the spell onto the battlefield: engine.resolve)
  and by ``casting.cast_spell`` before the spell is cast (718.3a: the cost, to see whether it can be cast).
* 718.4 — in every other zone, and on the stack or battlefield when not cast prototyped, only the normal characteristics.
* 718.2a / 718.3c-d — the alternative values are copiable: ``copying.recipe_of`` marks the recipe of a prototyped object ``prototyped``
  and ``copying._base`` applies :func:`overlay`, so a token copy, a clone or a copy of the spell is prototyped too.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import TYPE_CHECKING

from app.rules.characteristics import mana_value

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import Characteristics

_LINE = re.compile(r"^prototype (?P<cost>(?:\{[^}X]+\})+) [—-] (?P<p>\d+)/(?P<t>\d+)$", re.IGNORECASE)
_COLORS = re.compile(r"\{([WUBRG])\}")


def parse(ch: Characteristics) -> tuple[str, str, str] | None:
    """(mana cost, power, toughness) of the card's one prototype line, or None."""
    lines = [a for a in ch.abilities if a.kind == "keywords" and "prototype" in a.keywords]
    m = _LINE.fullmatch(re.sub(r"\s*\(.*?\)", "", lines[0].text).strip().rstrip(".")) if len(lines) == 1 else None
    return (m["cost"], m["p"], m["t"]) if m else None


def overlay(ch: Characteristics) -> Characteristics:
    """The prototyped characteristics (718.3b): the alternative mana cost (and its colors, mana value), power and toughness."""
    found = parse(ch)
    if found is None:
        return ch
    cost, power, toughness = found
    colors = frozenset(_COLORS.findall(cost.upper()))
    return replace(ch, mana_cost=cost, mana_value=mana_value(cost), colors=colors, power=power, toughness=toughness)


def is_prototyped(state: GameState, card: CardInstance) -> bool:
    r = state.rules
    if r is None or not r.payments:
        return False
    record = r.payments.get(r.object_id(card.id))
    return record is not None and record.prototyped

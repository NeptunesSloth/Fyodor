"""-- counters (wave 7C) -- power-up (CR 2026-09-25, 702.193).

702.193a: "Power-up — [Cost]: [Effect]" means "[Cost]: [Effect]. If this permanent entered this turn, this ability's
cost is reduced by this permanent's mana cost. Activate this ability only once." The "only once" is per object (an
exhaust-like limit: restrictions.py, ``per_game``); the reduction is read when the cost is determined (601.2f, 602.2b).
702.193b / 118.7: generic mana in the permanent's mana cost reduces generic mana in the activation cost; colored and
colorless mana reduce mana of the same type, and any excess reduces generic mana. A mana component reduced to nothing
is {0}. Not read (manual): a hybrid or Phyrexian symbol in either cost (118.7e/f ask the player to choose).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.rules import mana as M

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import Characteristics

PREFIX = "Power-up — "


def readable(ch: Characteristics, mana: str | None) -> bool:
    """Can its reduction be worked out? (No hybrid / Phyrexian / X / unsupported symbol in the permanent's mana cost or
    in the activation cost.)"""
    own, cost = M.parse_cost(ch.mana_cost), M.parse_cost(mana)
    return not (own.hybrid or own.phyrexian or own.x or own.unsupported or cost.hybrid or cost.phyrexian or cost.unsupported)


def entered_this_turn(state: GameState, card: CardInstance) -> bool:
    r = state.rules
    if r is None or r.turn_log.turn != state.turn.number:
        return False
    oid = r.object_id(card.id)
    return any(e.object_id == oid for e in r.turn_log.entered)


def reduced(state: GameState, card: CardInstance, ch: Characteristics, mana: str | None) -> str | None:
    """The activation cost after the reduction of 702.193a (itself when the permanent didn't enter this turn)."""
    if not mana or not entered_this_turn(state, card) or not readable(ch, mana):
        return mana
    own, cost = M.parse_cost(ch.mana_cost), M.parse_cost(mana)
    colored = list(cost.colored)
    generic = max(0, cost.generic - own.generic)
    for c in own.colored:  # 118.7b/c/d: the same type, any excess reduces generic mana
        if c in colored:
            colored.remove(c)
        else:
            generic = max(0, generic - 1)
    return M.ManaCost(generic, tuple(colored)).text()

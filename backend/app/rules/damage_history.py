"""-- damage history (wave 6B) -- objects that were dealt damage, or dealt damage, this turn. Researched against
CR 2026-09-25.

"Destroy target creature that was dealt damage this turn" (Rooftop Assassin), "Destroy target creature that dealt
damage this turn" (Avenging Arrow), "Exile target creature that dealt damage to you this turn" (Reciprocate),
"Return each creature that dealt damage this turn to its owner's hand" (Restore the Peace): selector qualifiers
(app/rules/selectors.py, block marked wave 6B) read from this turn's log (app/rules/history.py, 608.2i).

* Damage is dealt only when it isn't prevented (615.1; 120.3: the results of damage dealt); the log records the
  damage events the engine applied, so prevented damage never counts, and an amount of 0 is no damage (120.8).
* The object is the one that was dealt (or dealt) the damage: a permanent that left the battlefield and came back
  is a new object (400.7) and was dealt no damage this turn. The log keeps rules object ids, so it reads that way.
* "dealt damage to you": a player recipient (the log's "damage" facts, ``player`` the recipient, ``object_id`` the
  source); "dealt damage" alone: to any player or permanent (120.1).
"""

from __future__ import annotations

from typing import Any

from app.rules.plan import Plan

WAS_DEALT = "was_dealt_damage"  # the object was dealt damage this turn
DEALT = "dealt_damage"  # the object dealt damage this turn (to anything)
DEALT_YOU = "dealt_damage_you"  # the object dealt damage to "you" this turn
BY_SOURCE = "dealt_damage_by_source"  # -- wave 19E -- the object was dealt damage this turn by the selector's source ("dealt damage by ~")
EXTRAS = (WAS_DEALT, DEALT, DEALT_YOU, BY_SOURCE)


def matches(plan: Plan, card: Any, extra: str, you: str | None, source: str | None = None) -> bool:
    """Whether ``card`` (as the object it is now) meets the history qualifier ``extra`` this turn."""
    from app.rules.history import log_for

    if plan.rules is None:
        return False
    oid = plan.oid(card)
    # (recipient object, recipient player, source object) of each damage event this turn; log_for includes those not yet
    # recorded — dealt earlier in the same resolution ("~ deals 1 damage to target creature. Then destroy each
    # creature … that was dealt damage this turn", Swift Demise; 608.2c: the instructions in order)
    dealt: list[tuple[str | None, str | None, str | None]] = []
    for f in log_for(plan, False).facts:
        if f.kind == "damaged" and f.amount > 0:
            dealt.append((f.object_id, None, f.source))
        elif f.kind == "damage" and f.amount > 0:
            dealt.append((None, f.player, f.object_id))
    if extra == WAS_DEALT:
        return any(to == oid for to, _, _ in dealt)
    if extra == BY_SOURCE:
        src_card = plan.state.cards.get(source or "")
        return src_card is not None and any(to == oid and src == plan.oid(src_card) for to, _, src in dealt)
    if extra == DEALT_YOU:
        return any(src == oid and player is not None and player == you for _, player, src in dealt)
    return any(src == oid for _, _, src in dealt)

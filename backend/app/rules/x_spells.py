"""-- X sized by a count (wave 4K) -- what X-sized spells need beyond the value grammar (app/rules/values.py).

* "Shuffle Blue Sun's Zenith into its owner's library." (the Zenith cycle): the spell's own last instruction moves it
  from the stack into its owner's library, which is then shuffled (701.24a). It is no longer on the stack when its
  resolution ends, so it isn't put into a graveyard (608.2n: only a spell still there is); engine.leave_stack leaves
  it where it went. A copy of the spell isn't a card: it doesn't go anywhere (707.10, 704.5e) — the library is
  shuffled all the same (701.24c).

The other parts of the family live where their grammar does, each block marked "X sized by a count (wave 4K)":
"pay X life" (costs.py, casting.life_x_problem; 107.3a, 601.2b, 119.4), "X target …" (language.target_group,
targets.group_limits; 601.2c), "an X/X … token" and "twice X" / "half X, rounded up" tokens (token_grammar.py,
effects.create_token; 111.3, 107.1a), "gain trample and get +X/+X" (language.py; 608.2h, 611.2c).
"""

from __future__ import annotations

from typing import Any

from app.rules.plan import Plan

SHUFFLE_SELF = {"do": "to_library", "who": "self", "place": "shuffle"}


def spell_effects(effects: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """A spell's effects with a final "Shuffle ~ into its owner's library." read as ``shuffle_self``; None when the
    spell moves itself anywhere else, or earlier (what an effect does to the resolving spell isn't otherwise read)."""
    moves = [i for i, e in enumerate(effects) if e.get("who") == "self"]
    if not moves:
        return effects
    if moves != [len(effects) - 1] or {k: v for k, v in effects[-1].items() if k != "as"} != SHUFFLE_SELF:
        return None
    return [*effects[:-1], {"do": "shuffle_self"}]


def shuffle_self(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    card = plan.state.cards.get(ctx.get("stack_id") or "")  # (the resolving spell itself)
    if card is None or card.zone != "stack":
        return True  # (not on the stack any more: nothing to move)
    if not card.is_token:  # (a copy of the spell: 707.10, it ceases to exist as it leaves the stack)
        plan.rules.payments.pop(plan.oid(card), None)  # (the spell's record: the card in the library is a new object, 400.7)
        plan.do({"type": "move", "card_ids": [card.id], "to": {"player": card.owner, "zone": "library"}}, actor=ctx["controller"])
    plan.do({"type": "shuffle", "player": card.owner, "zone": "library"}, actor=card.owner)
    return True


def left_stack_itself(plan: Plan, card_id: str) -> bool:
    """Did the spell's own instruction move it off the stack (engine.leave_stack: nothing left to do)?"""
    card = plan.state.cards.get(card_id)
    return card is not None and card.zone.endswith(":library")


PRIMITIVES = {"shuffle_self": shuffle_self}

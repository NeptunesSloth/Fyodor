"""-- wave 110E -- Uvilda, Dean of Perfection: "{T}: You may exile an instant or sorcery card from your hand and put three refine counters on it. It gains
[upkeep tick] and [last-counter cast]."

CR 113.6 / 611.2: the granted abilities are a permanent layer-6 grant that works only in exile (ability_zone). 702.62-like clock: the owner's upkeep removes a
refine counter; the last removal triggers (603.2) and "if it's exiled" is the intervening if (603.4). The cast is a paid cast as the trigger resolves (608.2g),
for its mana cost less {4} (601.2f: a reduction of generic mana only, never below {0}); sorcery timing is waived (608.2g).
"""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.plan import Plan

TEXT = ('{T}: You may exile an instant or sorcery card from your hand and put three refine counters on it. It gains "At the beginning of your upkeep, if this card '
        'is exiled, remove a refine counter from it" and "When the last refine counter is removed from this card, if it\'s exiled, you may cast it. It costs {4} less '
        'to cast this way."')
TICK = "At the beginning of your upkeep, if this card is exiled, remove a refine counter from it"
LAST = "When the last refine counter is removed from this card, if it's exiled, you may cast it. It costs {4} less to cast this way."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = ability.text.strip()
    if text == TEXT:
        d = scripts.define(replace(ability, text="{T}: You may exile an instant or sorcery card from your hand."), ch)
        if d is None or d.get("kind") != "activated":
            return None
        return {**d, "effects": [*d["effects"], {"do": "only_if", "cond": {"succeeded": "pay0"}, "skip": 1}, {"do": "refine110e"}]}
    if text.rstrip(".") == TICK:
        return {"kind": "triggered", "trigger": "step:upkeep:you", "exiled_step": True, "optional": False, "target": None,
                "effects": [{"do": "tick110e"}]}
    if text == LAST:
        return {"kind": "triggered", "trigger": "event", "optional": False, "target": None,
                "cond": {"event": "counters_removed", "subject": "self", "counter": "refine", "last": True, "exiled": True},
                "effects": [{"do": "found110e"}, {"do": "free_cast", "zone": "found", "filter": None, "optional": True, "n": 1, "paid": True, "less": 4}]}
    return None


def refine(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, layers
    from app.rules import replace as rep

    cards = [c for c in effects._cards(plan, ctx, "ref:pay0") if c in plan.state.cards and plan.state.cards[c].zone.endswith(":exile")]
    for cid in cards:
        layers.add_effect(plan, affected=[plan.oid(cid)], layer="6", source=ctx.get("source_object"), controller=ctx["controller"], duration="permanent",
                          add_abilities=[TICK + ".", LAST], ability_zone="exile", label="Uvilda: refine")
    return not cards or rep.put_counters(plan, [(c, "refine", 3) for c in cards], by=ctx["controller"], then=effects._then(ctx, e), ctx=ctx)


def tick(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Remove a refine counter from this card if it is still the exiled object that triggered (603.4); the removal event is what the last-counter ability reads."""
    card = plan.state.cards.get(ctx.get("source_card") or "")
    if card is not None and card.zone.endswith(":exile") and plan.oid(card) == ctx.get("source_object") and card.counters.get("refine", 0) > 0:
        plan.do({"type": "counter", "card_ids": [card.id], "kind": "refine", "delta": -1}, actor=card.owner)
    return True


def found(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The card whose last counter came off: this very object, if it's still exiled (603.4); else nothing is cast."""
    card = plan.state.cards.get(ctx.get("source_card") or "")
    ctx["found"] = card.id if card is not None and card.zone.endswith(":exile") and plan.oid(card) == ctx.get("source_object") else None
    return True


def less(state: GameState, card: CardInstance) -> int:
    """The {N} less a resolving paid cast takes off the generic part of this card's cost (permissions.spell_mana)."""
    p = state.rules.free_cast_then if state.rules is not None else None
    return int(p["e"].get("less", 0)) if p and p.get("card") == card.id and p.get("e") else 0


PRIMITIVES: dict[str, Any] = {"refine110e": refine, "found110e": found, "tick110e": tick}

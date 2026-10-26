"""-- Koh, the Face Stealer (wave 110C) --

* "Pay 1 life: Choose a creature card exiled with Koh." (607.2a): the choice is made as the ability resolves (608.2d); it is remembered as Koh's choice, the object
  that card is in exile (400.7), replacing the earlier choice ("the last chosen card").
* "Koh has all activated and triggered abilities of the last chosen card." (113.10, 613.1f): abilities_of lends the card's activated and triggered abilities as they
  are now (611.3a); a chosen card that left exile is a new object, so Koh has none of its abilities; Koh leaving forgets the choice (400.7).
"""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import GameState
    from app.rules.plan import Plan

KEY = "Last chosen110c"
_PAY = "Pay 1 life: Choose a creature card exiled with Koh."
_STATIC = "Koh has all activated and triggered abilities of the last chosen card."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    t = ability.text.replace("~", "Koh")
    if t == _PAY:
        native = scripts.define(replace(ability, text="Pay 1 life: You gain 1 life."), ch)
        return None if native is None else {**native, "effects": [{"do": "koh_choose110c"}]}
    if t == _STATIC:
        from app.rules.statics import _definition

        return _definition("self", None, [], abilities_of={"sel": None, "linked": False, "no_mana": False, "chosen110c": True, "triggered": True})  # type: ignore[no-any-return]
    return None


def last_chosen(state: GameState, source: str) -> list[str]:
    koh = state.cards.get(source)
    r = state.rules
    if koh is None or r is None or not (oid := koh.choices.get(KEY)):
        return []
    cid = oid.rsplit(".", 1)[0]
    card = state.cards.get(cid)
    return [cid] if card is not None and card.zone.endswith(":exile") and r.object_id(cid) == oid else []


def _pool(plan: Plan, ctx: dict[str, Any]) -> list[str]:
    from app.rules import exiled_with

    out = []
    for oid in plan.rules.exiled_with.get(exiled_with.link_key(ctx), []):
        card = plan.state.cards.get(oid.rsplit(".", 1)[0])
        if card is not None and card.zone.endswith(":exile") and plan.oid(card) == oid and not card.face_down and "Creature" in plan.ch(card).types:
            out.append(card.id)
    return out


def _set(plan: Plan, ctx: dict[str, Any], cid: str) -> None:
    koh = plan.state.cards.get(ctx.get("source_card") or "")
    if koh is not None and koh.zone.endswith(":battlefield") and plan.oid(koh) == ctx.get("source_object"):
        plan.do({"type": "set_choice", "card_id": koh.id, "key": KEY, "value": plan.oid(plan.state.cards[cid])}, actor=ctx["controller"])
        plan.note(f"{koh.name} now has the abilities of {plan.state.cards[cid].name}", [cid], actor=ctx["controller"])


def koh_choose(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    pool = _pool(plan, ctx)
    if not pool:
        plan.note(f"{ctx.get('name') or 'It'}: no creature card is exiled with it", actor=ctx["controller"])
        return True
    if len(pool) == 1:
        _set(plan, ctx, pool[0])
        return True
    decide(plan, player=ctx["controller"], kind="choose_cards", prompt=f"Choose a creature card exiled with {ctx.get('name') or 'it'}",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in pool], min_choices=1, max_choices=1,
           resume={"step": "koh_choose110c", "ctx": ctx}, source=plan.state.cards.get(ctx.get("source_card") or ""))
    return False


def resume_koh_choose(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume["ctx"]
    if chosen and chosen[0] in _pool(plan, ctx):
        _set(plan, ctx, chosen[0])
    effects.continue_effects(plan, ctx)


PRIMITIVES = {"koh_choose110c": koh_choose}
RESUME = {"koh_choose110c": resume_koh_choose}

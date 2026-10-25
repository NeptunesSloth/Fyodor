"""-- aura return (wave 110D) -- an Aura that comes back when the creature it enchanted goes away (CR 2026-09-25).

* 303.4f / 303.4g: an Aura put onto the battlefield without a stated object is attached to what its new controller chooses, a legal host; with none it stays.
* Reins of the Vinesteed: "you may return this card from your graveyard to the battlefield attached to a creature that shares a creature type with that
  creature" — not a target (no "target"): chosen on resolution among the creatures that share a type with the dead one (205.3m) (linked_attachment_return).
* Traveling Plague: "that creature's controller returns this Aura from its owner's graveyard to the battlefield" — that player (its controller as it last
  existed, 608.2h) puts it onto the battlefield, so 110.2a: under their control, and they choose what it enchants.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

_REINS = ("When enchanted creature dies, you may return this card from your graveyard to the battlefield attached to a creature that shares a creature "
          "type with that creature.")
_PLAGUE = "When enchanted creature leaves the battlefield, that creature's controller returns this Aura from its owner's graveyard to the battlefield."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    def norm(t: str) -> str:
        return t.replace("this card", "~").replace("this Aura", "~")

    text = norm(scripts.self_text(ability.text, ch.name))
    if text == norm(_REINS):
        native, effects = _REINS.replace("a creature that shares a creature type with that creature", "target creature"), [{"do": "aura_sharing110d", "who": "self_aura_gy"}]
    elif text == norm(_PLAGUE):
        native, effects = "When enchanted creature leaves the battlefield, return this card from your graveyard to the battlefield.", [{"do": "aura_back110d", "who": "self_aura_gy"}]
    else:
        return None
    d = scripts.define(replace(ability, text=native), ch)
    return {**d, "effects": effects, "target": None} if d and d.get("kind") == "triggered" else None


def sharing(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, creature_types, effects, linked_attachment_return

    aura, dead = effects._cards(plan, ctx, e["who"]), context.info(plan, ctx, context.EVENT)
    if not aura or dead is None or plan.state.cards[aura[0]].owner != ctx["controller"]:
        return True
    kin = dead[1].subtypes & creature_types.CREATURE_TYPES  # as it last existed (608.2h, 603.10a): layer-added types count
    hosts = [r for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and plan.ch(c).is_creature
             and plan.ch(c).subtypes & kin and (r := context.ref_of(plan, c.id)) is not None]
    ref = context.ref_of(plan, aura[0])
    return True if ref is None else linked_attachment_return.return_attached(
        plan, ctx, {"aura": ref.model_dump(mode="json"), "hosts": [h.model_dump(mode="json") for h in hosts]})


def back(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects

    ref = next(iter(context._object_refs(ctx, context.EVENT)), None)
    snap = None if ref is None else context.snapshot(plan, ref)
    if snap is None or snap.controller not in plan.live():
        return True
    context.bind_players(ctx, "plague110d", [snap.controller])
    return effects.return_card(plan, ctx, {"do": "return_card", "who": e["who"], "to": "battlefield", "under": "ref:plague110d"})


PRIMITIVES = {"aura_sharing110d": sharing, "aura_back110d": back}

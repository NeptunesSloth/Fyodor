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

# Creatures that come back as an Aura enchantment (205.1a: a set type drops the creature types; 303.4f: it enters attached to a host chosen by its
# controller, who must be able to enchant it; the grant is read as "Enchanted land": an Aura that stops enchanting a Forest falls off, 704.5m). self_text'd line -> (intervening "if it was a creature", host selector, the Aura's own abilities).
_LION = "When ~ dies, return it to the battlefield. It's an Aura enchantment with enchant creature you control and \"{G}{W}: Enchanted creature gains indestructible until end of turn,\" and it loses all other abilities."
_HAROLD = ("When ~ dies, if it was a creature, return it to the battlefield. It's an Aura enchantment with enchant Forest you control and \"Enchanted Forest has "
           "'{T}: Add three mana of any one color. You get two rad counters.'\" ~ loses all other abilities.")
_TROLL = ("When ~ dies, if it was a creature, return it to the battlefield. It's an Aura enchantment with enchant Forest you control and \"Enchanted Forest has "
          "'{T}: Add {G}{G}' and '{1}, {T}, Sacrifice ~: Create a tapped 4/4 green Troll Warrior creature token with trample.'\"")
_AURAS: dict[str, tuple[bool, str, list[str]]] = {
    _HAROLD: (True, "Forests you control", ["Enchant Forest you control", "Enchanted land has \"{T}: Add three mana of any one color. You get two rad counters.\""]),
    _TROLL: (True, "Forests you control", ["Enchant Forest you control", "Enchanted land has \"{T}: Add {G}{G}\" and \"{1}, {T}, Sacrifice this land: Create a tapped 4/4 green Troll Warrior creature token with trample.\""]),
    _LION: (False, "creatures you control", ["Enchant creature you control", "{G}{W}: Enchanted creature gains indestructible until end of turn."]),
}


def comes_back(text: str, ability: Any) -> dict[str, Any] | None:
    from app.rules import selectors

    if (hit := _AURAS.get(text)) is None or ability.kind != "triggered":
        return None
    host = selectors.parse(hit[1])
    assert host is not None
    creature = selectors.Selector(types=("Creature",)).key()
    cond = {"object": "self", "is": creature}
    effect = {"do": "return_card", "who": "event.new", "to": "battlefield", "under": "owner", "tapped": False,
              "host_choice": host.key(),
              "entry_characteristics": {"set_types": ["Enchantment"], "set_creature_types": [], "add_subtypes": ["Aura"], "remove_abilities": True,
                                        "add_abilities": hit[2]}}
    return {"kind": "triggered", "trigger": "dies_self", "optional": False, "target": None, **({"if": cond} if hit[0] else {}),
            "effects": [{"do": "only_if", "cond": cond, "skip": 1}, effect] if hit[0] else [effect]}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    def norm(t: str) -> str:
        return t.replace("this card", "~").replace("this Aura", "~")

    text = norm(scripts.self_text(ability.text, ch.name))
    if (back := comes_back(text, ability)) is not None:
        return back
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

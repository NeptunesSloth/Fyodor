"""-- trigger lines (wave 100A) -- triggered abilities read as an equivalent native wording plus, where needed, instructions of their own.

* Calculating Lich: "Whenever a creature attacks one of your opponents, that player loses 1 life." — the attack is declared against that opponent
  directly (508.3a; the "opponent" defender is a player, not a planeswalker), so "that player" is the attacking creature's defending player (508.5).
* Invasion of Ulgrotha: "When this Siege enters, it deals 3 damage to any other target …" — "it" is the Siege the trigger is about (608.2k) and
  "any other target" is any target but the Siege (115.4).
* Primordial Plasm: "… another target creature gets +2/+2 and loses all abilities until end of turn." — one effect: +2/+2 (613.4c) and losing all
  abilities (613.1f) from the same resolution, both until end of turn (514.2).
* Spreading Plague: "Whenever a creature enters, destroy all other creatures that share a color with it. They can't be regenerated." — "it" is the
  entering creature as it is as the ability resolves, or as it last existed (608.2h); a colorless one shares no color (105.2c); "other" is other than
  that object (a new object it became is another one, 400.7); all are destroyed at once (701.8a), without regeneration (701.19c).
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

# text (after scripts.self_text) -> (the native wording it reads as, instructions, whether they replace the native effects or follow them)
_AS: dict[str, tuple[str, list[dict[str, Any]], bool]] = {
    "Whenever a creature attacks one of your opponents, that player loses 1 life.":
        ("Whenever a creature attacks one of your opponents, defending player loses 1 life.", [], False),
    "When ~ enters, it deals 3 damage to any other target and you gain 3 life.":
        ("When ~ enters, ~ deals 3 damage to any other target and you gain 3 life.", [], False),
    # Dinrova Horror: "that player" is the owner whose hand it went to (the one player named before)
    "When ~ enters, return target permanent to its owner's hand, then that player discards a card.":
        ("When ~ enters, return target permanent to its owner's hand. Its owner discards a card.", [], False),
    # Carrion Locust: "that player" is the opponent whose graveyard held it, the card's owner (404.2: a card goes to its owner's graveyard)
    "When ~ enters, exile target card from an opponent's graveyard. If it was a creature card, that player loses 1 life.":
        ("When ~ enters, exile target card from an opponent's graveyard. If it was a creature card, its owner loses 1 life.", [], False),
    "At the beginning of combat on your turn, another target creature gets +2/+2 and loses all abilities until end of turn.":
        ("At the beginning of combat on your turn, another target creature gets +2/+2 until end of turn.",
         [{"do": "become", "who": "target", "types": [], "lose_abilities": True, "duration": "end_of_turn"}], False),
    "Whenever a creature enters, destroy all other creatures that share a color with it. They can't be regenerated.":
        ("Whenever a creature enters, destroy it.", [{"do": "plague100a"}, {"do": "destroy", "who": "ref:plague100a"}, {"do": "no_regen"}], True),
}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != "triggered":
        return None
    text = scripts.self_text(ability.text, ch.name)
    found = _AS.get(text)
    if found is None:
        return None
    native = scripts.define(replace(ability, text=found[0]), ch)
    if native is None:
        return None
    if found[2]:
        return {**native, "effects": list(found[1])}
    return {**native, "effects": [*native["effects"], *found[1]]} if found[1] else native


def plague(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Spreading Plague: bind every other creature on the battlefield sharing a color with the entering creature (as it is, or last existed)."""
    from app.rules import context

    got = context.info(plan, ctx, context.EVENT)
    refs = context._object_refs(ctx, context.EVENT)
    colors = set(got[1].colors) if got is not None else set()
    oid = refs[0].object_id if refs else None
    victims = [c.id for c in plan.state.cards.values() if colors and c.zone.endswith(":battlefield") and plan.in_game(c)
               and plan.oid(c) != oid and (o := plan.ch(c)).is_creature and o.colors & colors]
    context.bind_objects(plan, ctx, "plague100a", victims)
    return True


PRIMITIVES = {"plague100a": plague}

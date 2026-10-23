"""Exact cross-zone control exchanges; source and spell retain their original identities."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

CHIMERA = "Whenever an opponent casts a spell, you may exchange control of ~ and that spell. If you do, you may choose new targets for the spell."
SUDDEN = "Exchange control of target noncreature spell and target creature. Then the spell's controller may choose new targets for it."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    text = scripts.self_text(ability.text, ch.name)
    if text == CHIMERA:
        native = scripts.define(replace(ability, text="Whenever an opponent casts a spell, draw a card."), ch)
        if native:
            return {**native, "effects": [{"do": "exchange_chimera_offer93"}]}
    if text == SUDDEN:
        spell = selectors.parse("noncreature spell")
        creature = selectors.parse("creature")
        assert spell is not None and creature is not None
        return {
            "kind": "spell",
            "target": None,
            "targets": [
                {"what": spell.key(), "min": 1, "max": 1},
                {"what": creature.key(), "min": 1, "max": 1},
            ],
            "effects": [
                {"do": "exchange_spell_permanent93", "permanent": "target:1", "spell": "target:0"},
                {"do": "choose_new_targets", "who": "target:0", "by": "spell_controller"},
            ],
        }
    return None


def pair(plan: Any, ctx: Any, effect: Any) -> Any:
    from app.rules import effects

    permanents = effects._cards(plan, ctx, effect["permanent"])
    spells = effects._stack_targets(plan, ctx, {"who": effect["spell"]})
    if len(permanents) != 1 or len(spells) != 1:
        return None
    permanent, spell = plan.state.cards[permanents[0]], plan.state.cards[spells[0]]
    if (
        not permanent.zone.endswith(":battlefield")
        or not plan.in_game(permanent)
        or spell.zone != "stack"
        or spell.ability is not None
        or not plan.in_game(spell)
        or permanent.controller == spell.controller
    ):
        return None
    return permanent, spell


def offer(plan: Any, ctx: Any, effect: Any) -> bool:
    exchange = {"do": "exchange_spell_permanent93", "permanent": "self", "spell": "event_spell"}
    if pair(plan, ctx, exchange) is None:
        return True
    ctx["effects"][ctx["next"] : ctx["next"]] = [
        {"do": "may_rest", "label": "Exchange control of this permanent and that spell"},
        exchange,
        {"do": "only_if", "cond": {"succeeded": "exchange_spell93"}, "skip": 1},
        {"do": "choose_new_targets", "who": "event_spell"},
    ]
    return True


def exchange(plan: Any, ctx: Any, effect: Any) -> bool:
    from app.rules import context, effects, layers

    context.bind_payment(ctx, "exchange_spell93", False)
    actors = pair(plan, ctx, effect)
    if actors is None:
        return True
    permanent, spell = actors
    permanent_controller, spell_controller = permanent.controller, spell.controller
    effects._control_effect(plan, ctx, [permanent.id], spell_controller, "permanent")
    effects._control_effect(plan, ctx, [spell.id], permanent_controller, "permanent")
    layers.control_sync(plan)
    context.bind_payment(ctx, "exchange_spell93", True)
    return True


PRIMITIVES = {"exchange_chimera_offer93": offer, "exchange_spell_permanent93": exchange}

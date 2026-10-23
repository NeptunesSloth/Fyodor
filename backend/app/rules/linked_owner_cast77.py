"""Exact Spell Queller departure offers the original linked card to its owner now."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics
    from app.rules.plan import Plan

TEXT = "When this creature leaves the battlefield, the exiled card's owner may cast that card without paying its mana cost."


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.text != TEXT:
        return None
    native = scripts.define(replace(ability, text="When this creature leaves the battlefield, return the exiled card to its owner's hand."), ch)
    return {**native, 'effects': [{'do': 'linked_owner_cast77'}]} if native is not None else None


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, exiled_with
    from app.rules import exile_packet_continuations as packets

    offers: list[dict[str, Any]] = []
    for i, cid in enumerate(exiled_with.cards(plan, ctx)):
        binding = f'queller77_{i}'
        context.bind_objects(plan, ctx, binding, [cid])
        offers.extend([{'do': 'as_player', 'player': plan.state.cards[cid].owner},
                       {'do': 'free_cast', 'zone': 'that', 'who': context.PREFIX + binding, 'exact_refs': True},
                       {'do': 'as_player_end'}])
    return packets.insert(ctx, offers)


PRIMITIVES = {'linked_owner_cast77': run}

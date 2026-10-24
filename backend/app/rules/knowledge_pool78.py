"""Knowledge Pool exchanges only the actual hand-cast spell for another linked card."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics
    from app.rules.plan import Plan

TEXT = ('Whenever a player casts a spell from their hand, that player exiles it. If the player does, '
        'they may cast a spell from among other cards exiled with this artifact without paying its mana cost.')


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.text != TEXT:
        return None
    native = scripts.define(replace(ability, text='Whenever a player casts a spell from their hand, you gain 1 life.'), ch)
    return {**native, 'effects': [{'do': 'knowledge_pool78', 'stage': 'exile'}]} if native is not None else None


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects, exiled_with
    from app.rules import exile_packet_continuations as packets

    if e['stage'] == 'exile':
        spell = effects._cards(plan, ctx, 'event_spell')
        players = context.players(plan, ctx, context.EVENT)
        if not spell or len(players) != 1:
            return True
        return packets.insert(ctx, [{'do': 'as_player', 'player': players[0]},
                                    {'do': 'exile', 'who': 'event_spell', 'link': True, 'as': 'pool78_moved'},
                                    {'do': 'knowledge_pool78', 'stage': 'offer'}, {'do': 'as_player_end'}])
    moved = [cid for cid in context.objects(plan, ctx, 'pool78_moved')
             if plan.state.cards[cid].zone.endswith(':exile')]
    if not moved:
        return True
    pool = [cid for cid in exiled_with.cards(plan, ctx) if cid not in moved]
    context.bind_objects(plan, ctx, 'pool78_other', pool)
    return packets.insert(ctx, [{'do': 'free_cast', 'zone': 'that', 'who': context.PREFIX + 'pool78_other',
                                 'exact_refs': True}])


PRIMITIVES = {'knowledge_pool78': run}

"""A dies trigger grants the original graveyard successors an Adventure-only cast."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics
    from app.rules.plan import Plan

TEXT = 'When ~ dies, you may cast it from your graveyard as an Adventure until the end of your next turn.'


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import scripts

    if scripts.self_text(ability.text, ch.name) != TEXT:
        return None
    native = scripts.define(replace(ability, text='When this creature dies, draw a card.'), ch)
    return {**native, 'effects': [{'do': 'grant_adventure74'}]} if native is not None else None


def grant(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.game.state import zone_key
    from app.rules import context, permissions, selectors
    from app.rules.plan import decide

    original = context._object_refs(ctx, context.EVENT_NEW)
    if not original:
        old = context._object_refs(ctx, context.EVENT)
        if old and all(ref.snapshot is not None and ref.snapshot.is_token for ref in old):
            return True
        decide(plan, player=ctx['controller'], kind='manual_resolution',
               prompt='This saved death trigger lacks the original graveyard object. Resolve its Adventure permission with the table tools, then press Done.',
               options=[DecisionOption(id='done', label='Done')],
               resume={'step': 'grant_adventure74', 'ctx': ctx})
        return False
    cards = [cid for cid in context.objects(plan, ctx, context.EVENT_NEW)
             if plan.state.cards[cid].zone == zone_key(ctx['controller'], 'graveyard')]
    context.bind_objects(plan, ctx, 'adventure74', cards)
    return permissions.grant_play(plan, ctx, {'do': 'grant_play', 'who': 'ref:adventure74', 'zone': 'graveyard',
        'play': False, 'cast': True, 'until': 'end_of_next_turn',
        'filter': selectors.Selector(zones=('stack',), subtypes=('Adventure',)).key()})


def manual_done(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    effects.continue_effects(plan, d.resume['ctx'])


PRIMITIVES = {'grant_adventure74': grant}
RESUME = {'grant_adventure74': manual_done}

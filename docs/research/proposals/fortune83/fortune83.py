"""Fortune chooses actual saddle contributors when its delayed trigger resolves."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXT = ("Whenever Fortune attacks while saddled, at end of combat, exile it and up to one creature that saddled it this turn, "
        "then return those cards to the battlefield under their owner's control.")


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import delayed, scripts

    if ability.kind != 'triggered' or ability.text != TEXT:
        return None
    native = scripts.define(replace(ability, text='Whenever Fortune attacks while saddled, draw a card.'), ch)
    return {**native, 'effects': delayed.wrap_when([{'do': 'fortune_choose83'}], delayed.END_OF_COMBAT)} if native else None


def choose(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import crew_saddle, selectors

    keys = [selectors.Selector(types=('Creature',), extras=('oid:' + plan.oid(c),)).key()
            for c in plan.state.cards.values() if c.zone.endswith(':battlefield') and plan.in_game(c)
            and plan.ch(c).is_creature and crew_saddle.tapped_for(plan, 'saddle', plan.oid(c), ctx.get('source_object'))]
    following: list[dict[str, Any]] = [{'do': 'fortune_blink83'}]
    if keys:
        following.insert(0, {'do': 'player_chooses', 'who': 'you', 'sel': selectors.Selector(either=tuple(keys)).key(),
                             'n': 1, 'upto': True, 'any': True, 'as': 'fortune_contributor83'})
    ctx['effects'][ctx['next']:ctx['next']] = following
    return True


def blink(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context

    cards = [c.id for c in plan.state.cards.values() if c.zone.endswith(':battlefield') and plan.oid(c) == ctx.get('source_object')]
    cards += context.objects(plan, ctx, 'fortune_contributor83')
    context.bind_objects(plan, ctx, 'fortune_cohort83', list(dict.fromkeys(cards)))
    ctx['effects'][ctx['next']:ctx['next']] = [
        {'do': 'exile', 'who': 'ref:fortune_cohort83', 'as': 'fortune_exiled83'},
        {'do': 'return_card', 'who': 'ref:fortune_exiled83', 'to': 'battlefield', 'under': 'owner'}]
    return True


PRIMITIVES = {'fortune_choose83': choose, 'fortune_blink83': blink}

"""Exact two-face native attack histories and random destruction."""
from __future__ import annotations

import secrets
from typing import Any

_KEYWORDS = ('first strike', 'double strike', 'vigilance', 'haste')


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    if ability.text == ("When Path of Mettle enters, it deals 1 damage to each creature that doesn't have "
                        "first strike, double strike, vigilance, or haste."):
        return {'kind': 'triggered', 'trigger': 'event', 'cond': {'event': 'enter', 'subject': 'self'},
                'effects': [{'do': 'damage', 'n': 1, 'who': selectors.Selector(
                    types=('Creature',), without_keywords=_KEYWORDS).key()}]}
    if ability.text == ('Whenever you attack with at least two creatures that have first strike, double strike, '
                        'vigilance, and/or haste, transform Path of Mettle.'):
        return {'kind': 'triggered', 'trigger': 'event',
                'cond': {'event': 'you_attack', 'subject': 'player', 'player': 'you', 'min_attackers': 2,
                         'sel': selectors.Selector(types=('Creature',), extras=(
                             'any_kw:' + ','.join(_KEYWORDS),)).key()},
                'effects': [{'do': 'transform', 'who': 'self'}]}
    if ability.text == ('{2}{W}, {T}: Choose a creature at random that attacked this turn. '
                        'Destroy that creature.'):
        from dataclasses import replace

        native = scripts.define(replace(ability, text='{2}{W}, {T}: Draw a card.'), ch)
        if native is not None:
            return {**native, 'effects': [{'do': 'random_transform43'}]}
    return None


def consume(plan: Any, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.rules import coin_recipes, context, selectors

    pool = sorted(selectors.candidates(plan, selectors.Selector(
        types=('Creature',), extras=('attacked_this_turn',)), ctx['controller'], ctx.get('source')))
    if pool:
        from app.rules import randomness  # -- random choices (wave MBC-D) --
        selected = randomness.choice(plan, plan.rng or secrets.SystemRandom(), pool, kind='object', player=ctx['controller'])
        context.bind_objects(plan, ctx, 'r43_metzali_selected', [selected])
        coin_recipes.insert(ctx, [{'do': 'destroy', 'who': 'ref:r43_metzali_selected'}])
    return True

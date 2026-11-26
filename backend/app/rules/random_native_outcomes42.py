"""Wave42 exact random receipts and native entry, return and die consequences."""
from __future__ import annotations

from typing import Any


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    text = ' '.join(body.split())
    text = text[:1].upper() + text[1:]
    if text in ('Return X cards at random from your graveyard to your hand.',
                'Return X cards at random from your graveyard to your hand. Exile ~.'):
        effects = [{'do': 'random_native42', 'kind': 'reap'}]
        if text.endswith('Exile ~.'):
            effects.append({'do': 'exile', 'who': 'self_stack'})
        return effects, None, False
    if text == ('Roll two d10 and choose one result. Return a creature card from your graveyard to the battlefield '
                'with a number of +1/+1 counters on it equal to that result. Then each opponent loses X life '
                'and you gain X life, where X is the other result.'):
        got = scripts.parse_effects('Return a creature card from your graveyard to the battlefield.')
        assert got is not None
        return ([{'do': 'roll', 'sides': 10, 'count': 2, 'choose': True},
                 {**got[0][0], 'counter': '+1/+1', 'counter_n': {'die': 'result'}},
                 {'do': 'lose_life', 'who': 'each_opponent', 'n': {'die': 'other'}},
                 {'do': 'gain_life', 'who': 'you', 'n': {'die': 'other'}}], None, False)
    return None


def merge_lines(ch: Any, out: dict[int, Any]) -> None:
    from app.rules import dice

    header = '{3}{G}: Roll a d20. Activate only if this card is in your graveyard.'
    rows = ['1—9 | Put this card on top of your library.',
            '10—19 | Return this card to your hand.', '20 | Return this card to the battlefield tapped.']
    for at, ab in enumerate(ch.abilities):
        following = ch.abilities[at + 1:at + 4]
        if ab.text != header or [a.text for a in following] != rows:
            continue
        original = out.get(ab.index)
        if original is None or original.get('kind') != 'activated' or original.get('effects') != [{'do': 'roll', 'sides': 20, 'count': 1}]:
            continue
        effects: list[dict[str, Any]] = list(original['effects'])
        for lo, hi, dest in [(1, 9, 'library_top'), (10, 19, 'hand'), (20, 20, 'battlefield')]:
            condition = dice.condition(f'the result is {lo} to {hi}')
            assert condition is not None
            effects += [{'do': 'only_if', 'cond': condition, 'skip': 1},
                        {'do': 'return_card', 'who': 'self_gy', 'to': dest, 'tapped': dest == 'battlefield'}]
        out[ab.index] = {**original, 'effects': effects}
        for row in following:
            out[row.index] = {'kind': 'static', 'static': 'merged', 'merged_into': ab.index}


def consume(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    import secrets

    from app.rules import coin_recipes, context, effects

    if e.get('kind') != 'reap':
        raise ValueError('Unknown native random receipt')
    cards = sorted(plan.state.zones.get(ctx['controller'] + ':graveyard', []))
    count = max(0, effects._amount(plan, ctx, {'x': 1}))
    from app.rules import randomness  # -- random choices (wave MBC-D) --
    picked = cards if count >= len(cards) else randomness.sample(plan, plan.rng or secrets.SystemRandom(), cards, count, kind='card', player=ctx['controller']) if count else []
    context.bind_objects(plan, ctx, 'r42_reap', picked)
    coin_recipes.insert(ctx, [{'do': 'return_card', 'who': 'ref:r42_reap', 'to': 'hand'}])
    return True


PRIMITIVES = {'random_native42': consume}

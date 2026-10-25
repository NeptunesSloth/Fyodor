"""Delayed next-spell/loyalty copy watches using native event and copy jobs."""
from __future__ import annotations

from dataclasses import replace
from typing import Any


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts
    from app.rules.oracle import strip_reminders

    text = strip_reminders(scripts.self_text(ability.text, ch.name)).strip()
    if ' — ' in text:
        text = text.split(' — ', 1)[1]
    shaman = 'Whenever ~ deals combat damage to a player, copy the next instant or sorcery spell you cast this turn when you cast it. You may choose new targets for the copy.'
    sea = 'When ~ enters, copy the next instant or sorcery spell with mana value 2 or less you cast this turn when you cast it. If ~ was kicked, copy that spell twice instead. You may choose new targets for the copies.'
    repeated = 'When you next cast an instant spell, cast a sorcery spell, or activate a loyalty ability this turn, copy that spell or ability twice. You may choose new targets for the copies.'
    if text == repeated:
        d = scripts.define(replace(ability, text='Draw a card.'), ch)
        assert d is not None
        return {**d, 'effects': [{'do': 'next_copy104', 'mode': 'either'}]}
    if text in (shaman, sea):
        proxy = 'Whenever ~ deals combat damage to a player, draw a card.' if text == shaman else 'When ~ enters, draw a card.'
        d = scripts.define(replace(ability, text=proxy), ch)
        assert d is not None
        return {**d, 'effects': [{'do': 'next_copy104', 'mode': 'sea' if text == sea else 'spell'}]}
    return None


def next_copy(plan: Any, ctx: Any, effect: Any) -> bool:
    from app.rules import conditions, delayed, events, selectors

    mode = effect['mode']
    cond = events.parse_condition('you cast an instant or sorcery spell')
    assert cond is not None
    n = 1
    if mode == 'sea':
        # Payment provenance is retained on the permanent object and its LKI.
        n = 2 if conditions.holds(plan, ctx, {'object': 'self', 'cast': {'kicked': True}}) else 1
        what = selectors.parse('instant or sorcery spell with mana value 2 or less')
        assert what is not None
        cond = {**cond, 'spell': what.key()}
    elif mode == 'either':
        loyalty = events.parse_condition('you activate a loyalty ability')
        assert loyalty is not None
        cond = {'event': 'either', 'subject': 'player', 'player': 'you', 'conds': [cond, loyalty]}
        n = 2
    out = delayed.wrap_when([{'do': 'copy_event_stack', 'n': n}, {'do': 'copy_new_targets', 'optional': True}],
                            {'kind': 'watch', 'cond': cond, 'text': 'you next cast a matching spell or activate a matching ability'}, this_turn=True)
    out[0]['once'] = True
    ctx['effects'][ctx['next']:ctx['next']] = out
    return True


PRIMITIVES = {'next_copy104': next_copy}

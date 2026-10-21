"""Printed mana symbols as production instructions (CR106.8–106.11).

This is not a payment solver: generic symbols produce colorless mana and no
Phyrexian choice ever permits paying life to produce mana.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import Characteristics
    from app.rules.oracle import AbilityText
    from app.rules.plan import Plan


def choices(cost: str, *, colored_only: bool = False) -> list[tuple[str, ...]]:
    """One ordered production choice per symbol, without exponential expansion.

Each item contains alternative output strings; e.g. {2/W} is ('CC','W').
Colored-only consumers count a hybrid's colored symbol once, selecting among
its component colors, rather than offering the generic/colorless half.
"""
    result: list[tuple[str, ...]] = []
    for symbol in re.findall(r'\{([^{}]+)\}', cost):
        halves = symbol.split('/')
        if colored_only:
            colors = tuple(dict.fromkeys(x for x in halves if x in 'WUBRG' and len(x) == 1))
            if colors:
                result.append(colors)
            continue
        options = []
        for half in halves:
            if half == 'P':
                continue
            if half.isdecimal():
                options.append('C' * int(half))
            elif half in ('X', 'Y', 'Z'):
                options.append('')
            elif half == 'S':
                options.append('C')
            elif half in 'WUBRGC' and len(half) == 1:
                options.append(half)
            else:
                raise ValueError(f'Unrecognized mana symbol {{{symbol}}}')
        result.append(tuple(dict.fromkeys(options)))
    return result


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from dataclasses import replace

    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if ability.kind == 'activated' and text == "{T}, Mill a card: For each colored mana symbol in the milled card's mana cost, add one mana of that color.":
        base = scripts.define(replace(ability, text='{T}, Mill a card: Draw a card.'), ch)
        if base is not None:
            return {**base, 'effects': [{'do': 'mana_from_printed_cost', 'who': 'milled', 'colored_only': True}]}
    if ability.kind == 'triggered' and text == "At the beginning of your first main phase, add mana equal to enchanted permanent's mana cost.":
        base = scripts.define(replace(ability, text='At the beginning of your first main phase, draw a card.'), ch)
        if base is not None:
            return {**base, 'effects': [{'do': 'mana_from_printed_cost', 'who': 'host'}]}
    return None


def produce(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import values

    if e['who'] == 'milled':
        from app.rules import payment_card_facts

        facts = payment_card_facts.get(plan, ctx, 'milled')
        if facts is None or any(f.mana_cost is None for f in facts):
            from app.game.rules_state import DecisionOption
            from app.rules.plan import decide

            decide(plan, player=ctx['controller'], kind='manual_resolution',
                prompt="This older activation did not record the milled card's mana symbols. Add the appropriate mana by hand, then press Done.",
                options=[DecisionOption(id='done', label='Done')],
                resume={'step': 'mana_symbol_unknown_cost', 'ctx': ctx})
            return False
        pending = [options for f in facts for options in choices(f.mana_cost or '', colored_only=True)]
        return _advance(plan, ctx, pending, [])
    if e['who'] == 'host':
        from app.rules import attached_kindred_look, context

        ref = attached_kindred_look.host_reference(plan, ctx, e)
        view = {**ctx, 'refs': {'symbol_host': {'kind': 'objects', 'objects': [ref.model_dump(mode='json')]}}} if ref is not None else ctx
        got = context.info(plan, view, 'symbol_host') if ref is not None else None
    else:
        got = values._object(plan, ctx, e['who'])
    if got is None:
        return True
    pending = choices(got[1].mana_cost, colored_only=bool(e.get('colored_only')))
    return _advance(plan, ctx, pending, [])


def _advance(plan: Plan, ctx: dict[str, Any], pending: list[tuple[str, ...]], got: list[str]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import effects
    from app.rules.plan import decide

    while pending and len(pending[0]) == 1:
        got.extend(pending.pop(0)[0])
    if not pending:
        return effects._put_mana(plan, ctx, ctx['controller'], got)
    decide(plan, player=ctx['controller'], kind='choose_one', prompt='Choose mana for this mana symbol',
        options=[DecisionOption(id=str(i), label=''.join('{'+c+'}' for c in option) or 'No mana')
                 for i, option in enumerate(pending[0])],
        resume={'step': 'mana_symbol_production', 'ctx': ctx, 'pending': pending, 'got': got})
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    data = d.resume
    pending = [tuple(x) for x in data['pending']]
    got = [*data['got'], *pending.pop(0)[int(chosen[0])]]
    if _advance(plan, data['ctx'], pending, got):
        effects.continue_effects(plan, data['ctx'])


PRIMITIVES = {'mana_from_printed_cost': produce}
RESUME = {'mana_symbol_production': resume}


def unknown_cost_done(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    effects.continue_effects(plan, d.resume['ctx'])


RESUME['mana_symbol_unknown_cost'] = unknown_cost_done

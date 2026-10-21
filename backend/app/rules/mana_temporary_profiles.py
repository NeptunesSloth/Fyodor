"""A resolved upkeep creates fixed creature changes and temporary mana rules."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


BODY = ('At the beginning of each upkeep, count the number of permanents. If the number is odd, until end of turn, '
        'red creatures get +1/+1 and whenever a player taps a Mountain for mana, that player adds an additional {R}. '
        'If the number is even, until end of turn, red creatures get -1/-1 and if a player taps a Mountain for mana, '
        'that Mountain produces colorless mana instead of any other type.')


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind == 'triggered' and scripts.self_text(ability.text, ch.name) == BODY:
        base = scripts.define(replace(ability, text='At the beginning of each upkeep, gain 1 life.'), ch)
        if base is not None:
            return {**base, 'effects': [{'do': 'parity_mana_upkeep'}]}
    return None


def upkeep(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import mana_replace, scripts, tap_mana

    n = sum(c.zone.endswith(':battlefield') for c in plan.state.cards.values())
    odd = bool(n % 2)
    pump = scripts.parse_effects('Red creatures get ' + ('+1/+1' if odd else '-1/-1') + ' until end of turn.')
    if pump is None:
        raise ValueError('Native red-creature modifier unavailable')
    if odd:
        rule = tap_mana.definition('Whenever a player taps a Mountain for mana, that player adds an additional {R}.')
        if rule is None:
            raise ValueError('Native Mountain trigger unavailable')
        rule = {**rule, 'staged': True}
    else:
        parsed = mana_replace.spell_effect('Until end of turn, if a player taps a land for mana, it produces colorless mana instead of any other type.')
        if parsed is None:
            raise ValueError('Native mana replacement unavailable')
        from app.rules import selectors

        rule = {**parsed['def'], 'sel': selectors.Selector(types=('Land',), subtypes=('Mountain',)).key()}
    ctx['effects'][ctx['next']:ctx['next']] = [*pump[0], {'do': 'tap_mana_until_eot', 'def': rule}]
    return True


PRIMITIVES = {'parity_mana_upkeep': upkeep}

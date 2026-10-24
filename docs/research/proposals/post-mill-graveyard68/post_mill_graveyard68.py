"""Whole post-mill graveyard instructions with forced fallback and native placement."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

_ROOTS = "Mill three cards, then return a land card or Elf card from your graveyard to your hand. If you can't, draw a card."
_STILL = 'At the beginning of your upkeep, mill three cards. Then if your library has no cards in it, exile this enchantment and put five cards from your graveyard on top of your library in any order.'


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import conditions, scripts, selectors

    text = ability.text.strip().casefold()
    roots = text == _ROOTS.casefold()
    if not roots and text not in (_STILL.casefold(), _STILL.replace('this enchantment', '~').casefold()):
        return None
    native = scripts.define(replace(ability, text='Draw a card.' if roots else 'At the beginning of your upkeep, draw a card.'), ch)
    if native is None:
        raise ValueError('Native post-mill shell unavailable')
    effects: list[dict[str, Any]] = [{'do': 'mill', 'who': 'you', 'n': 3}]
    if roots:
        effects.append({'do': 'roots_finish68'})
    else:
        sel = selectors.Selector(card=True, zone_owner='you', zones=('graveyard',)).key()
        cond = conditions.parse('your library has no cards in it')
        assert cond is not None
        effects.extend([{'do': 'only_if', 'cond': cond, 'skip': 3},
                        {'do': 'exile', 'who': 'self'},
                        {'do': 'return_choice', 'sel': sel, 'n': 5, 'upto': False, 'to': 'choose', 'as': 'stillness68'},
                        {'do': 'to_library', 'who': 'ref:stillness68', 'place': 'top'}])
    return {**native, 'effects': effects}


def roots_finish(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import scripts, selectors

    native = scripts.parse_effects('Return a land card or Elf card from your graveyard to your hand.')
    assert native is not None
    effect = native[0][0]
    found = selectors.candidates(plan, selectors.from_key(effect['sel']), ctx['controller'], ctx.get('source_card'))
    # Enqueue the native mover, so commander903.9b preflight occurs before it runs.
    ctx['effects'][ctx['next']:ctx['next']] = [effect] if found else [{'do': 'draw', 'who': 'you', 'n': 1}]
    return True


PRIMITIVES = {'roots_finish68': roots_finish}

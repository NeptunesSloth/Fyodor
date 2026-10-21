"""Qualified private library choices using exact native looked-card continuations."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.rules import context, selectors
from app.rules.plan import Plan


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = body.strip().rstrip('.')
    text = text[:1].upper() + text[1:]
    cases = {
        'Look at the top six cards of your library. You may reveal a card that shares a creature type with that creature from among them and put it into your hand. Put the rest on the bottom of your library in a random order': 'mantle',
        'Look at the top five cards of your library. You may reveal a land or double-faced card from among them and put that card into your hand. Put the rest on the bottom of your library in a random order': 'pest',
        'Look at the top four cards of your library. You may reveal a creature or land card from among them and put it into your hand. If you gained life this turn, you may instead reveal two creature and/or land cards from among them and put them into your hand. Put the rest on the bottom of your library in a random order': 'lumarets',
    }
    if text in cases:
        mode = cases[text]
        return [{'do': 'qualified_library_look', 'mode': mode,
                 **({'who': 'ref:event'} if mode == 'mantle' else {})}], None, False
    return None


def insert(ctx: dict[str, Any], steps: list[dict[str, Any]]) -> None:
    ctx['effects'][ctx['next']:ctx['next']] = steps


def qualified_library_look(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import reveal_outcomes
    from app.rules.creature_types import CREATURE_TYPES

    mode = e['mode']
    sel = selectors.Selector(zones=(), card=True)
    n, pick = 5, 1
    if mode == 'mantle':
        n = 6
        info = context.info(plan, ctx, e['who'].removeprefix(context.PREFIX))
        subtypes = info[1].subtypes & CREATURE_TYPES if info is not None else frozenset()
        sel = replace(sel, subtypes=tuple(sorted(subtypes))) if subtypes else replace(sel, types=('Creature',), not_types=('Creature',))
    elif mode == 'pest':
        sel = replace(sel, zones=('library',), either=(selectors.Selector(zones=(), card=True, types=('Land',)).key(),
                                  selectors.Selector(zones=(), card=True, extras=('double_faced_card',)).key()))
    elif mode == 'lumarets':
        n = 4
        pick = 2 if plan.rules.turn_log.turn == plan.state.turn.number and plan.rules.turn_log.gained.get(ctx['controller'], 0) > 0 else 1
        sel = replace(sel, types=('Creature', 'Land'))
    elif mode == 'radagast':
        info = context.info(plan, ctx, e['who'].removeprefix(context.PREFIX))
        n = int(info[1].mana_value) if info is not None else 0
        excluded_subtypes: set[str] = set().union(*(plan.ch(c).subtypes & CREATURE_TYPES for c in plan.state.cards.values()
                                                  if c.zone.endswith(':battlefield') and c.controller == ctx['controller'] and plan.ch(c).is_creature))
        sel = replace(sel, types=('Creature',), not_subtypes=tuple(sorted(excluded_subtypes)))
    if not reveal_outcomes.reveal_outcome_top(plan, ctx, {'do': 'reveal_outcome_top', 'n': n, 'player': 'you', 'exact_look': True}):
        return False
    insert(ctx, [{'do': 'pick_looked', 'n': pick, 'optional': True, 'sel': sel.key(), 'reveal': True, 'to': 'hand'},
                 {'do': 'rest_looked', 'to': 'bottom_random'}])
    return True


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered':
        return None
    text = scripts.self_text(ability.text, ch.name)
    if text != "Whenever ~ or another nontoken creature you control enters, look at the top X cards of your library, where X is that creature's mana value. You may reveal a creature card that doesn't share a creature type with a creature you control from among those cards and put it into your hand. Put the rest on the bottom of your library in a random order.":
        return None
    native = scripts.define(replace(ability, text='Whenever ~ or another nontoken creature you control enters, you gain 1 life.'), ch)
    if native is None:
        return None
    return {**native, 'effects': [{'do': 'qualified_library_look', 'mode': 'radagast', 'who': 'ref:event'}]}


PRIMITIVES = {'qualified_library_look': qualified_library_look}

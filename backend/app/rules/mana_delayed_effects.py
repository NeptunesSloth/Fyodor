"""Mana production can create native delayed effects without using the stack."""
from __future__ import annotations

import copy
import re
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.characteristics import Characteristics
    from app.rules.oracle import AbilityText
    from app.rules.plan import Plan


def _watch(cond: dict[str, Any], effects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from app.rules import delayed

    return delayed.wrap_when(effects, {'kind': 'watch', 'cond': cond, 'text': 'you next cast a matching spell'}, this_turn=True)


def tail(text: str) -> list[dict[str, Any]] | None:
    from app.rules import delayed, events, scripts

    t = text.strip().rstrip('.')
    if t == 'When you next cast an artifact spell this turn, that spell gains sunburst':
        cond = events.parse_condition('you cast an artifact spell')
        return _watch(cond, [{'do': 'spell_rider', 'who': 'event_spell', 'keyword': 'sunburst'}]) if cond is not None else None
    if t == 'When you next cast a spell with {X} in its mana cost this turn, you draw a card and gain half X life, rounded down':
        cond = events.parse_condition('you cast a spell')
        if cond is not None:
            cond['cost_has_x'] = True
            return _watch(cond, [{'do': 'draw', 'who': 'you', 'n': 1},
                                 {'do': 'gain_life', 'who': 'you', 'n': {'half': {'event_x': 1}, 'round': 'down'}}])
    if t == 'An opponent gains control of this land at the beginning of the next end step':
        return delayed.wrap_when([{'do': 'gain_control', 'who': 'self', 'to': 'choose_opponent'}],
                                 {'kind': 'step', 'step': 'end', 'whose': 'next'})
    if re.fullmatch(r'When you next cast (?:a Bird creature|a creature) spell this turn, (?:it|that creature) enters with (?:an|two) additional \+1/\+1 counters? on it', t):
        parsed = scripts.parse_effects(t + '.')
        if parsed is not None and parsed[1] is None and not parsed[2]:
            return parsed[0]
    return None


def extract(text: str) -> tuple[str, tuple[dict[str, Any], ...]] | None:
    first, sep, rest = text.partition('. ')
    if not sep or ': Add ' not in first:
        return None
    effects = tail(rest)
    return (first + '.', tuple(effects)) if effects is not None else None


def start(plan: Plan, card: CardInstance, controller: str, source_object: str,
          effects: tuple[dict[str, Any], ...]) -> None:
    from app.rules import delayed

    if not effects:
        return
    ctx: dict[str, Any] = {'kind': 'mana', 'controller': controller, 'source_card': card.id,
                           'source_object': source_object, 'name': plan.ch(card).name,
                           'effects': copy.deepcopy(list(effects)), 'next': 1}
    delayed.create(plan, ctx, ctx['effects'][0])


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered' or not re.fullmatch(r'Whenever another permanent you control is put into a graveyard from the battlefield, if it had one or more counters on it, you may put that number of \+1/\+1 counters on target creature\.', ability.text):
        return None
    defined = scripts.define(replace(ability, text=ability.text.replace('that number of', 'a')), ch)
    if defined is not None:
        defined = copy.deepcopy(defined)
        for effect in defined['effects']:
            if effect.get('do') == 'add_counters':
                effect['n'] = {'counters': None, 'on': 'event'}
    return defined

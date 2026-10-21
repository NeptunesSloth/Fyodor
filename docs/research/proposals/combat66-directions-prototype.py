"""Exact public direction choices constrain declared attacks, using live seat order."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics
    from app.rules.plan import Plan

CHOICE = 'Chosen direction'
SOURCE = 'attack_direction_source:'
FIXED = 'attack_direction:'
STATIC = {
    'Each player may attack only the nearest opponent in the chosen direction and planeswalkers controlled by that opponent.',
    'Each player may attack only the nearest opponent in the last chosen direction and planeswalkers controlled by that opponent.',
}


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import scripts, selectors, statics

    text = scripts.self_text(ability.text, ch.name)
    choice = {'do': 'choose_value', 'who': 'you', 'what': 'direction', 'remember': True}
    if text == 'As ~ enters, choose left or right.':
        return {'kind': 'replacement', 'replacement': 'enters_choice', 'effects': [choice]}
    if text in STATIC:
        return statics._definition(selectors.Selector(types=('Creature',)).key(), None, [], rules=[SOURCE + '@src'])
    if text == 'When ~ enters and at the beginning of your upkeep, choose left or right.':
        native = scripts.define(replace(ability, text='When ~ enters and at the beginning of your upkeep, draw a card.'), ch)
        return {**native, 'effects': [choice]} if native is not None else None
    if text == ('−2: Choose left or right. Until your next turn, each player may attack only the nearest opponent '
                'in the last chosen direction and planeswalkers controlled by that opponent.'):
        native = scripts.define(replace(ability, text='−2: Draw a card.'), ch)
        if native is not None:
            return {**native, 'effects': [
                {'do': 'choose_value', 'who': 'you', 'what': 'direction', 'as': 'direction66'},
                {'do': 'restrict_direction66'}]}
    return None


def restrict_direction(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.rules import layers, selectors

    value = (ctx.get('refs') or {}).get('direction66', {}).get('value')
    if value not in ('left', 'right'):
        return True
    layers.add_effect(plan, affected=[], layer='6', source=ctx.get('source_object'), controller=ctx['controller'],
                      who=selectors.Selector(types=('Creature',)).key(), source_card=ctx.get('source_card'),
                      imposes=(FIXED + value,), duration='next_turn', until_player=ctx['controller'],
                      turn=plan.state.turn.number, label='Attacks only ' + value + ' until your next turn')
    return True


def forbidden(plan: Plan, rules: set[str], target: str) -> bool:
    """Declaration-only constraints intersect; entering attacking bypasses them (508.4)."""
    live = plan.live()
    attacker = plan.active
    if attacker not in live or len(live) < 2:
        return False
    from app.game import actions as A
    from app.rules import combat

    defender = target if target in plan.state.players else combat.defender_of(
        plan.state, A.AttackTarget(kind='card', id=target))
    if target not in plan.state.players:
        card = plan.state.cards.get(target)
        if card is None or 'Planeswalker' not in plan.ch(card).types:
            defender = None  # Printed permission names players and planeswalkers, never battles.
    for rule in rules:
        if rule.startswith(SOURCE):
            source = plan.state.cards.get(rule[len(SOURCE):])
            direction = source.choices.get(CHOICE) if source is not None else None
        elif rule.startswith(FIXED):
            direction = rule[len(FIXED):]
        else:
            continue
        if direction not in ('left', 'right'):
            continue  # No linked choice means no restriction, including ability-only copies.
        nearest = live[(live.index(attacker) + (1 if direction == 'left' else -1)) % len(live)]
        if defender != nearest:
            return True
    return False


PRIMITIVES = {'restrict_direction66': restrict_direction}

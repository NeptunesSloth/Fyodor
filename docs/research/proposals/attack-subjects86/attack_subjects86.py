"""Compound attack subjects use native declarations, frozen object refs and one resolution choice."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

CANAL = "Whenever ~ and another creature attack different players, ~ can't be blocked this combat."
PUPPET = "Whenever ~ attacks, if you attacked with exactly one other creature this combat, you may have that creature's base power and toughness become 4/3 until end of turn."
BALLROOM = 'Whenever ~ attacks, ~ and up to one other target creature you control both gain your choice of first strike or lifelink until end of turn.'


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered':
        return None
    text = scripts.self_text(ability.text, ch.name)
    if text == CANAL:
        native = scripts.define(replace(ability, text="Whenever ~ attacks alone, ~ can't be blocked this combat."), ch)
        if native is None:
            return None
        cond = {k: v for k, v in native['cond'].items() if k != 'alone'}
        return {**native, 'cond': {**cond, 'while': {'attack_pair_players86': True}}}
    if text == scripts.self_text(PUPPET, ch.name):
        native = scripts.define(replace(ability, text='Whenever ~ attacks, you may draw a card.'), ch)
        return {**native, 'if': {'attack_other_exact86': True}, 'effects': [
            {'do': 'puppet_bind86'}, {'do': 'become', 'who': 'ref:puppet_other86', 'types': [],
                                    'p': 4, 't': 3, 'duration': 'end_of_turn'}]} if native else None
    if text == BALLROOM:
        native = scripts.define(replace(ability, text='Whenever ~ attacks, up to one other target creature you control gains first strike until end of turn.'), ch)
        return {**native, 'effects': [{'do': 'ballroom_prepare86'}]} if native else None
    return None


def others(plan: Any, ctx: dict[str, Any]) -> list[str]:
    log = plan.rules.turn_log
    source = ctx.get('source_object')
    return [oid for oid in log.attackers.get(ctx['controller'], []) if oid != source
            and log.turn == plan.state.turn.number and log.declared.get(oid) == plan.rules.combats]


def holds(plan: Any, ctx: dict[str, Any], cond: dict[str, Any]) -> bool:
    if cond.get('attack_other_exact86'):
        return len(others(plan, ctx)) == 1
    source = plan.state.cards.get(ctx.get('source_card') or '')
    log = plan.rules.turn_log
    if source is None or source.attacking is None or source.attacking.kind != 'player' or log.declared.get(plan.oid(source)) != plan.rules.combats:
        return False
    return any(c.id != source.id and c.zone.endswith(':battlefield') and c.attacking is not None
               and c.attacking.kind == 'player' and c.attacking.id != source.attacking.id
               and log.declared.get(plan.oid(c)) == plan.rules.combats
               and plan.ch(c).is_creature for c in plan.state.cards.values())


def puppet_bind(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context

    original = set(others(plan, ctx))
    cards = [c.id for c in plan.state.cards.values() if c.zone.endswith(':battlefield') and plan.oid(c) in original]
    context.bind_objects(plan, ctx, 'puppet_other86', cards)
    return True


def ballroom_prepare(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects

    cards = list(dict.fromkeys(effects._cards(plan, ctx, 'self') + effects._cards(plan, ctx, 'target:0')))
    context.bind_objects(plan, ctx, 'ballroom_cohort86', cards)
    options = [{'label': word.capitalize(), 'effects': [
        {'do': 'grant', 'who': 'ref:ballroom_cohort86', 'keywords': [word]}]} for word in ['first strike', 'lifelink']]
    ctx['effects'][ctx['next']:ctx['next']] = [{'do': 'choose_effect', 'who': 'ref:ballroom_cohort86', 'options': options}]
    return True


PRIMITIVES = {'puppet_bind86': puppet_bind, 'ballroom_prepare86': ballroom_prepare}

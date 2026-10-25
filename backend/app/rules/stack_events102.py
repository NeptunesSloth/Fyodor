"""Cast target counts, creature-type exclusions, and original spell-copy destinations."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

BIB = 'Whenever you cast a spell with one or more targets, draw that many cards.'
VOLO = "Whenever you cast a creature spell that doesn't share a creature type with a creature you control or a creature card in your graveyard, copy that spell."
HIVE = 'Whenever a player casts an instant or sorcery spell, each other player copies that spell. Each of those players may choose new targets for their copy.'
IVY = 'Whenever a player casts a spell that targets only a single creature other than ~, you may copy that spell. The copy targets ~.'
FRONT = 'Whenever you cast a spell that targets only a single creature you control, create a 1/1 red Soldier creature token with haste, then copy that spell. The copy targets that token.'
PHOENIX = 'Whenever ~ deals combat damage to a player or planeswalker, copy the next loyalty ability you activate this turn when you activate it. You may choose new targets for the copy.'


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, selectors
    from app.rules.oracle import strip_reminders

    text = strip_reminders(scripts.self_text(ability.text, ch.name)).strip()
    proxy = None
    if text in (IVY, FRONT):
        proxy = ('Whenever a player casts a spell that targets only a single creature, draw a card.' if text == IVY else
                 'Whenever you cast a spell that targets only a single creature you control, draw a card.')
    elif text == VOLO:
        proxy = 'Whenever you cast a creature spell, copy it.'
    elif text == HIVE:
        proxy = 'Whenever a player casts an instant or sorcery spell, copy it.'
    elif text == BIB:
        proxy = 'Whenever you cast a spell that targets a creature, draw a card.'
    elif text == PHOENIX:
        proxy = 'Whenever ~ deals combat damage to a player or planeswalker, draw a card.'
    if proxy is None:
        return None
    native = scripts.define(replace(ability, text=proxy), ch)
    assert native is not None
    if text == BIB:
        cond = {**native['cond'], 'cast_targets102': True}
        cond.pop('targets', None)
        return {**native, 'cond': cond, 'effects': [{'do': 'bibliophile_draw102'}]}
    if text == VOLO:
        return {**native, 'cond': {**native['cond'], 'disjoint_creatures102': True}}
    if text == HIVE:
        return {**native, 'effects': [{'do': 'hive_copies102'}]}
    if text == IVY:
        cond = {**native['cond'], 'targets': 'only_one:' + selectors.Selector(types=('Creature',), other=True).key()}
        return {**native, 'cond': cond, 'optional': True, 'effects': [{'do': 'fixed_copy102', 'who': 'self'}]}
    if text == FRONT:
        token = scripts.parse_effects('Create a 1/1 red Soldier creature token with haste.')
        assert token is not None
        return {**native, 'effects': [{**token[0][0], 'as': 'front_created102'},
            {'do': 'return_choice', 'who': 'ref:front_created102', 'to': 'choose', 'n': 1, 'upto': False, 'as': 'front_target102'},
            {'do': 'fixed_copy102', 'who': 'ref:front_target102'}]}
    return {**native, 'effects': [{'do': 'jaya_watch102'}]}


def disjoint(plan: Any, watcher: Any, spell: Any) -> bool:
    from app.rules.creature_types import CREATURE_TYPES

    kinds = plan.ch(spell).subtypes & CREATURE_TYPES
    for c in plan.state.cards.values():
        if (c.zone.endswith(':battlefield') and c.controller == watcher.controller) or c.zone == f'{watcher.controller}:graveyard':
            ch = plan.ch(c)
            if ch.is_creature and kinds.intersection(ch.subtypes):
                return False
    return True


def hive_copies(plan: Any, ctx: Any, effect: Any) -> bool:
    caster = next(iter((ctx.get('event') or {}).get('players') or []), None)
    jobs = [sub for player in plan.apnap() if player != caster for sub in (
        {'do': 'copy_spell', 'who': 'event_spell', 'by': 'player:' + player},
        {'do': 'copy_new_targets', 'optional': True})]
    ctx['effects'][ctx['next']:ctx['next']] = jobs
    return True


def fixed_copy(plan: Any, ctx: Any, effect: Any) -> bool:
    from app.rules import copying, effects, spell_copy_replacements, targets

    victims = effects._cards(plan, ctx, effect['who'])
    found = next(iter(copying._copy_sources(plan, ctx, 'event_spell')), None)
    if len(victims) != 1:
        return True
    if found is None:
        return copying._manual_each(plan, ctx, ctx['controller'], None) if copying._event_object_left(ctx, 'event_spell') else True
    victim = victims[0]
    source, oid = found
    card = plan.state.cards.get(source)
    if card is None:
        return True
    entry = copying.source_entry102(plan, card, oid)
    if entry is None:
        return True
    reason = copying.uncopyable(plan, card, object_id=oid)
    if reason is not None:
        return True if not reason else copying._manual_each(plan, ctx, ctx['controller'], card)
    pos = copying.positions(entry)
    if not pos:
        return True
    source_ch = targets.source_of(plan, entry.source_card, entry.kind == 'spell', object_id=entry.source_object)
    for p in pos:
        spec = copying._spec(entry, p)
        if victim not in targets.legal_targets(plan, spec.get('what', 'any'), ctx['controller'], source_ch,
                                              entry.source_card, source_object=entry.source_object):
            return True
    probe = copying._retargeted(entry, pos, [targets.ref(plan, victim)] * len(pos))
    probe.controller = ctx['controller']
    if copying._problem(plan, probe) is not None:
        return True
    job = {'ctx': ctx, 'spell': source, 'oid': oid, 'controller': ctx['controller'], 'victims': [victim],
           'additional': spell_copy_replacements.additional(plan, ctx['controller'])}
    return copying._each_run(plan, job)


def bibliophile_draw(plan: Any, ctx: Any, effect: Any) -> bool:
    from app.rules import effects

    return effects.draw(plan, ctx, {'do': 'draw', 'who': 'you', 'n': int((ctx.get('event') or {}).get('amount') or 0)})


def jaya_watch(plan: Any, ctx: Any, effect: Any) -> bool:
    from app.rules import delayed, events

    cond = events.parse_condition('you activate a loyalty ability')
    assert cond is not None
    head = {'kind': 'watch', 'cond': cond, 'text': 'you next activate a loyalty ability'}
    out = delayed.wrap_when([{'do': 'copy_ability', 'who': 'event_ability'},
                            {'do': 'copy_new_targets', 'optional': True}], head, this_turn=True)
    out[0]['once'] = True
    ctx['effects'][ctx['next']:ctx['next']] = out
    return True


PRIMITIVES = {'hive_copies102': hive_copies, 'fixed_copy102': fixed_copy,
              'bibliophile_draw102': bibliophile_draw, 'jaya_watch102': jaya_watch}

"""Initial cast conditions and next-spell copy watches."""
from __future__ import annotations

from dataclasses import replace
from typing import Any


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import conditions, scripts
    from app.rules.oracle import strip_reminders

    text = strip_reminders(scripts.self_text(ability.text, ch.name)).strip()
    if text == 'Whenever you cast an instant or sorcery spell that targets only ~ or activate an ability that targets only ~, copy that spell or ability. You may choose new targets for the copy. This ability triggers only once each turn.':
        from app.rules import events

        d = scripts.define(replace(ability, text='Whenever you cast an instant or sorcery spell that targets only ~, copy that spell. You may choose new targets for the copy. This ability triggers only once each turn.'), ch)
        assert d is not None
        activate = events.parse_condition('you activate an ability')
        assert activate is not None
        return {**d, 'cond': {'event': 'either', 'conds': [d['cond'], {**activate, 'only_self103': True}]},
                'effects': [{'do': 'copy_event_stack'}, {'do': 'copy_new_targets', 'optional': True}]}
    precursor = 'Whenever a player casts an instant or sorcery spell that targets only a single Golem, that player copies that spell for each other Golem that spell could target. Each copy targets a different one of those Golems.'
    ink = 'Whenever a player casts an instant or sorcery spell, if that spell targets only ~, copy the spell for each other creature that spell could target. Each copy targets a different one of those creatures.'
    if text in (precursor, ink):
        from app.rules import selectors

        d = scripts.define(replace(ability, text='Whenever a player casts an instant or sorcery spell, copy it.'), ch)
        assert d is not None
        target = 'only_one:' + selectors.Selector(subtypes=('Golem',)).key() if text == precursor else 'self_only'
        return {**d, 'cond': {**d['cond'], 'targets': target},
                'effects': [{'do': 'spread_copy103', 'golem': text == precursor}]}
    initial = {
        'When you cast this spell while you control your commander, copy this spell. You may choose a new target for the copy.': 'you control your commander',
        'When you cast this spell while you control a creature, you may copy this spell.': 'you control a creature',
    }
    if text in initial:
        d = scripts.define(replace(ability, text='When you cast this spell, copy it. You may choose new targets for the copy.'), ch)
        assert d is not None
        cond = conditions.parse(initial[text])
        assert cond is not None
        return {**d, 'cast_initial103': cond, 'optional': 'may copy' in text,
                'effects': d['effects'] if 'new target' in text else [{'do': 'copy_spell', 'who': 'event_spell'}]}
    if text == 'When you cast this spell from your hand, copy it if you control an artifact, then copy it if you control an enchantment. You may choose new targets for the copies.':
        d = scripts.define(replace(ability, text='When you cast this spell, copy it. You may choose new targets for the copy.'), ch)
        assert d is not None
        out = []
        for kind in ('artifact', 'enchantment'):
            cond = conditions.parse('you control an ' + kind)
            assert cond is not None
            out.extend([{'do': 'only_if', 'cond': cond, 'skip': 2}, *d['effects']])
        return {**d, 'cast_hand103': True, 'effects': out}
    if text == 'When ~ enters, copy the next spell you cast this turn when you cast it. You may choose new targets for the copy.':
        d = scripts.define(replace(ability, text='When ~ enters, draw a card.'), ch)
        assert d is not None
        return {**d, 'effects': [{'do': 'next_spell103'}]}
    return None


def next_spell(plan: Any, ctx: Any, effect: Any) -> bool:
    from app.rules import delayed, events

    cond = events.parse_condition('you cast a spell')
    assert cond is not None
    out = delayed.wrap_when([{'do': 'copy_spell', 'who': 'event_spell'},
                             {'do': 'copy_new_targets', 'optional': True}],
                            {'kind': 'watch', 'cond': cond, 'text': 'you next cast a spell'}, this_turn=True)
    out[0]['once'] = True
    ctx['effects'][ctx['next']:ctx['next']] = out
    return True


def spread_copy(plan: Any, ctx: Any, effect: Any) -> bool:
    from app.rules import copying, spell_copy_replacements, targets

    found = next(iter(copying._copy_sources(plan, ctx, 'event_spell')), None)
    if found is None:
        return copying._manual_each(plan, ctx, ctx['controller'], None) if copying._event_object_left(ctx, 'event_spell') else True
    source, oid = found
    card = plan.state.cards.get(source)
    if card is None:
        return True
    entry = copying.source_entry102(plan, card, oid)
    if entry is None:
        return True
    positions = copying.positions(entry)
    old = {(t.id, t.object_id) for t in entry.targets}
    if not effect['golem'] and old != {(ctx['source_card'], ctx['source_object'])}:
        return True  # The Nephilim's intervening condition is checked again (603.4).
    reason = copying.uncopyable(plan, card, object_id=oid)
    if reason is not None:
        return True if not reason else copying._manual_each(plan, ctx, ctx['controller'], card)
    if not positions:
        return True
    # 115.9d: eligibility uses the ORIGINAL spell controller, including Nephilim
    # copies that subsequently have a different controller and illegal targets.
    caster = entry.controller
    controller = ((ctx.get('event') or {}).get('players') or [caster])[0] if effect['golem'] else ctx['controller']
    source_ch = targets.source_of(plan, source, True, object_id=oid)
    victims = []
    for c in plan.state.cards.values():
        if not c.zone.endswith(':battlefield') or (c.id, plan.oid(c)) in old:
            continue
        ch = plan.ch(c)
        if ('Golem' not in ch.subtypes) if effect['golem'] else not ch.is_creature:
            continue
        if any(c.id not in targets.legal_targets(plan, copying._spec(entry, p).get('what', 'any'), caster,
                                                source_ch, source, source_object=oid) for p in positions):
            continue
        probe = copying._retargeted(entry, positions, [targets.ref(plan, c.id)] * len(positions))
        probe.controller = caster
        if copying._problem(plan, probe) is None:
            victims.append(c.id)
    if not victims:
        return True
    return copying._each_run(plan, {'ctx': ctx, 'spell': source, 'oid': oid, 'controller': controller,
                                    'victims': victims, 'additional': spell_copy_replacements.additional(plan, controller)})


PRIMITIVES = {'next_spell103': next_spell, 'spread_copy103': spread_copy}

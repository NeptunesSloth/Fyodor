"""Conditional and next-matching casting timing permissions reuse the native caster."""
from __future__ import annotations

import re
from typing import Any


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import delayed, events, selectors

    text = body.strip()
    text = text[:1].upper() + text[1:]
    text = text.replace('"When ~ enters,', '"When this creature enters,')
    if text == 'Target creature you control and target creature an opponent controls each gain indestructible until end of turn. Then destroy all creatures.':
        groups = [{'what': selectors.Selector(types=('Creature',), controller=who).key(), 'min': 1, 'max': 1}
                  for who in ('you', 'opponent')]
        effects = [{'do': 'grant', 'who': 'target:' + str(i), 'keywords': ['indestructible'], 'duration': 'end_of_turn'} for i in range(2)]
        return [*effects, {'do': 'destroy', 'who': selectors.Selector(types=('Creature',)).key()}], groups, False
    if text == 'Until your next turn, you may cast creature spells as though they had flash, and each creature you control enters with an additional +1/+1 counter on it.':
        key = selectors.Selector(zones=('stack',), types=('Creature',)).key()
        return [{'do': 'flash_permission', 'filter': key, 'until': 'next_turn'}, {'do': 'timing_entry_rule'}], None, False
    if text == 'You may cast Dinosaur spells this turn as though they had flash, and whenever you cast a Dinosaur spell this turn, it gains "When this creature enters, you may have it fight another target creature."':
        key = selectors.Selector(zones=('stack',), subtypes=('Dinosaur',)).key()
        cond = events.parse_condition('you cast a Dinosaur spell')
        assert cond is not None
        watch = delayed.wrap_when([{'do': 'grant_cast_ability', 'who': 'event_spell',
                                    'ability': 'When this creature enters, you may have it fight another target creature.'}],
                                   {'kind': 'watch', 'cond': cond, 'text': 'you cast a Dinosaur spell'}, this_turn=True)
        watch[0]['once'] = False
        return [{'do': 'flash_permission', 'filter': key}, *watch], None, False
    next_flash = re.fullmatch(r'The next (?P<kind>sorcery spell|creature spell|creature card|spell) you (?P<verb>cast|play) this turn can be (?P<done>cast|played) as though it had flash\.(?P<tail>.*)', text)
    if next_flash is None:
        return None
    kind, tail = next_flash['kind'], next_flash['tail'].strip()
    if (kind == 'creature card') != (next_flash['verb'] == 'play' and next_flash['done'] == 'played'):
        return None
    wanted = 'Creature' if kind.startswith('creature') else 'Sorcery' if kind.startswith('sorcery') else None
    key = selectors.Selector(zones=('stack',), types=(wanted,) if wanted else ()).key()
    effect = {'do': 'flash_permission', 'filter': key, 'next_matching': True}
    if not tail:
        return [effect], None, False
    if tail == 'Draw a card.':
        return [effect, {'do': 'draw', 'who': 'you', 'n': 1}], None, False
    if tail == "That spell can't be countered. That creature enters with an additional +1/+1 counter on it.":
        return [effect, {'do': 'uncounterable_next', 'filter': key}, {'do': 'timing_next_entry', 'filter': key}], None, False
    if tail == 'When you next cast a spell this turn, put X +1/+1 counters on up to one target creature, where X is the mana value of that spell.':
        cond = events.parse_condition('you cast a spell')
        assert cond is not None
        es = delayed.mark_target([{'do': 'add_counters', 'who': 'target', 'kind': '+1/+1', 'n': {'mana_value': 'event'}}])
        watch = delayed.wrap_when(es, {'kind': 'watch', 'cond': cond, 'text': 'you next cast a spell'}, this_turn=True)
        watch[0].update(once=True, target={'what': selectors.Selector(types=('Creature',)).key(), 'min': 0, 'max': 1})
        return [effect, *watch], None, False
    return None


def static(text: str) -> dict[str, Any] | None:
    from app.rules import cast_limits, conditions, selectors

    if text == 'You may cast Aura spells with enchant creature as though they had flash.':
        return cast_limits.flash_def(selectors.Selector(zones=('stack',), subtypes=('Aura',), extras=('enchant_creature_exact',)).key())
    optional = {
        'You may cast this spell as though it had flash by tapping three untapped creatures you control with flying in addition to paying its other costs.':
            {'optional': 'flash_tap', 'cost': 'Tap three untapped creatures with flying you control'},
        'You may cast this spell as though it had flash if you behold a Dragon as an additional cost to cast it.':
            {'optional': 'behold', 'cost': 'Behold a Dragon'},
        "You may cast this spell as though it had flash if it's cast using teamwork.": {'optional': 'teamwork'},
    }
    if text in optional:
        return {**cast_limits.flash_def(None), 'self': True, 'flash_if': optional[text]}
    if text == 'You may cast this spell as though it had flash if a creature is attacking and a creature is blocking.':
        tests = [{'value': {'count': sel.key()}, 'op': '>=', 'n': 1}
                 for sel in (selectors.Selector(types=('Creature',), attacking=True), selectors.Selector(types=('Creature',), blocking=True))]
        return {**cast_limits.flash_def(None), 'self': True, 'if': {'all': tests}}
    if text == 'You may cast creature spells with mana value 3 or less by paying {E} rather than paying their mana costs. If you cast a spell this way, you may cast it as though it had flash.':
        from app.rules import alt_costs

        native = alt_costs.define('you may pay one {E} rather than pay the mana cost for creature spells you cast')
        assert native is not None
        return {**native, 'filter': selectors.Selector(zones=('stack',), types=('Creature',), compare=(('mv', '<=', 3),)).key(),
                'flash': True}
    body = re.sub(r'^(?:Ferocious|Spell mastery) — ', '', text)
    m = re.fullmatch(r'If (?P<cond>.+), you may cast this spell as though it had flash\.', body)
    if m is None:
        return None
    cond = conditions.parse(m['cond'][:1].lower() + m['cond'][1:])
    if cond is None:
        return None
    return {**cast_limits.flash_def(None), 'self': True, 'if': cond}


def entry_rule(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    from app.rules import layers, selectors

    layers.add_effect(plan, affected=[], layer='6', source=ctx.get('source_object'), controller=ctx['controller'],
                      who=selectors.Selector(types=('Creature',), controller='you').key(),
                      duration='next_turn', until_player=ctx['controller'], turn=plan.state.turn.number,
                      entry_counters={'+1/+1': 1}, label='Additional entry counter')
    return True


def next_entry(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    plan.rules.results.append({'what': 'next_entry_counters', 'turn': plan.state.turn.number, 'player': ctx['controller'],
                               'source': ctx.get('source_object'), 'filter': e['filter'], 'name': ctx.get('name') or ''})
    return True


def bind_next_entry(plan: Any, card: Any, record: Any) -> None:
    from app.rules import layers, permissions

    for mark in list(plan.rules.results):
        if mark.get('what') != 'next_entry_counters' or mark['turn'] != plan.state.turn.number or mark['player'] != record.controller:
            continue
        if not permissions.spell_matches(plan.state, record.controller, card, plan.ch(card), mark['filter'], plan.info):
            continue
        layers.add_effect(plan, affected=[plan.oid(card)], layer='6', source=mark.get('source'), controller=record.controller,
                          duration='permanent', entry_counters={'+1/+1': 1}, label=mark['name'])
        plan.rules.results.remove(mark)


def entering_counters(plan: Any, card: Any, controller: str, ch: Any) -> dict[str, int]:
    from app.rules import selectors

    result: dict[str, int] = {}
    for effect in plan.rules.effects:
        if not effect.entry_counters:
            continue
        if effect.who:
            probe = card.model_copy(update={'zone': controller + ':battlefield', 'controller': controller})
            if not selectors.matches(plan, selectors.from_key(effect.who), probe, ch, effect.controller, effect.source_card):
                continue
        elif plan.oid(card) not in effect.affected:
            continue
        for kind, n in effect.entry_counters.items():
            result[kind] = result.get(kind, 0) + n
    return result


def grant_cast_ability(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    from app.rules import copying, layers

    for sid in copying._stack_objects(plan, ctx, e['who']):
        layers.add_effect(plan, affected=[plan.oid(sid)], layer='6', source=ctx.get('source_object'), controller=ctx['controller'],
                          duration='permanent', add_abilities=[e['ability']], label=ctx.get('name') or 'Granted cast ability')
    return True


PRIMITIVES = {'timing_entry_rule': entry_rule, 'timing_next_entry': next_entry, 'grant_cast_ability': grant_cast_ability}


def alternative_flash(state: Any, player: str, card: Any, ch: Any, info: Any, *, announced: bool, key: str | None) -> bool:
    from app.rules import alt_costs, casting
    from app.rules.plan import Plan

    view = Plan.view(state, player, info)
    return any(o.flash and (not announced or o.key == key) and casting.additional_problem(view, o.alt.cost, card, player) is None
               for o in alt_costs.offers(state, player, card, ch, info))


def optional_flash(state: Any, player: str, card: Any, ch: Any, info: Any, condition: dict[str, Any], *,
                   announced: bool, selected: tuple[str, ...]) -> bool:
    from app.rules import casting, cost_changes, costs
    from app.rules.plan import Plan

    view = Plan.view(state, player, info)
    for offer in cost_changes.optional_offers(state, player, card, ch, info):
        if offer.kind != condition['optional'] or announced and offer.source not in selected:
            continue
        part = cost_changes.keyword_component(offer)
        if part is not None and casting.additional_problem(view, costs.AbilityCost(components=(part,)), card, player) is None:
            return True
    return False

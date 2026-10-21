"""Bound prevention outcomes; immediate bodies and genuine triggered outcomes stay distinct."""
from __future__ import annotations

import copy
import secrets
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP = 'prevention_outcome'
AMOUNT = {'ref_amount': 'prevented'}


def _effect(mode: str, **kw: Any) -> dict[str, Any]:
    return {'do': STEP, 'mode': mode, **kw}


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = body.strip().replace('this creature', '~')
    cases = {
        'Prevent all damage target spell would deal this turn. You gain life equal to the damage prevented this way.': ('hallow', 'spell'),
        'Prevent all damage that would be dealt to target multicolored creature this turn. For each 1 damage prevented this way, put a +1/+1 counter on that creature.': ('brace', 'multicolored_creature'),
        "Prevent all damage that would be dealt to you and planeswalkers you control this turn by sources you don't control. If damage from a creature source is prevented this way, ~ deals that much damage to that creature. If damage from a noncreature source is prevented this way, ~ deals that much damage to the source's controller.": ('comeuppance', None),
        "Prevent all damage that would be dealt to you and permanents you control this turn by sources you don't control. If damage is prevented this way, you may have ~ deal that much damage to target creature.": ('channel', 'creature'),
        'The next time a source of your choice would deal damage to you and/or creatures you control this turn, prevent that damage. If damage from a black source is prevented this way, you gain that much life.': ('shadowbane', None),
        'Prevent all damage that would be dealt to you this turn by a source of your choice. Whenever damage from a black or red source is prevented this way this turn, you gain that much life.': ('samite', None),
        "The next time a source of your choice would deal damage to you this turn, prevent that damage. When damage is prevented this way, ~ deals that much damage to that source's controller and you draw that many cards.": ('new_way', None),
        'Prevent all damage that would be dealt to you this turn by sources your opponents control. Whenever damage from a creature is prevented this way, each commander creature you control deals damage equal to its power to that creature.': ('judgment', None),
        'Until end of turn, if damage would be dealt to any creature, you may have that damage dealt to you instead.': ('blood', None),
        'Prevent the next X damage that would be dealt to you this turn. If damage is prevented this way, ~ deals that much damage to target player or planeswalker.': ('archon', 'player_or_planeswalker'),
        "Prevent the next X damage that would be dealt to target creature this turn, where X is your devotion to white. If damage is prevented this way, ~ deals that much damage to any target.": ('acolyte', [{'what': 'creature'}, {'what': 'any'}]),
        'Prevent the next 3 damage that would be dealt to target creature this turn. At the beginning of the next end step, put a +0/+1 counter on that creature for each 1 damage prevented this way.': ('sacred', 'creature'),
        "Prevent the next 7 damage that would be dealt to any target this turn. If it's a creature, put a +0/+1 counter on it for each 1 damage prevented this way at the beginning of the next end step.": ('scars', 'any'),
    }
    found = cases.get(text)
    if found is None:
        return None
    mode, target = found
    if target == 'multicolored_creature':
        from app.rules.nontarget_creature_choices import key

        target = key('multicolored creature')
    return [_effect(mode)], target, False


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name).replace('this creature', '~')
    if text == 'If damage would be dealt to ~, prevent that damage. When damage is prevented this way, ~ deals that much damage to any other target.':
        return {'kind': 'static', 'static': 'replace', 'event': 'damage',
                'match': {'to': {'objects': {'self': True}}},
                'op': {'do': 'prevent_all', 'prevention': True, 'rider': {
                    'if': True, 'aggregation': 'batch', 'effects': [_effect('trigger', outcome='vindicator')]}}, 'effects': []}
    if text == 'Whenever damage that would be dealt to you is prevented, put that many +1/+1 counters on ~.':
        return {'kind': 'triggered', 'trigger': 'event', 'cond': {'event': 'damage_prevented', 'subject': 'player', 'player': 'you', 'aggregate': True},
                'effects': [{'do': 'add_counters', 'who': 'self', 'kind': '+1/+1', 'n': {'event_amount': 1}}]}
    return None


def _rider(ctx: dict[str, Any], body: list[dict[str, Any]], aggregation: str = 'batch', **kw: Any) -> dict[str, Any]:
    # Targets are already filtered for legality by the original resolution. The refs
    # remain exact objects; later protection still modifies damage normally.
    saved = {k: copy.deepcopy(v) for k, v in ctx.items() if k not in ('effects', 'next', 'body_done')}
    return {'if': True, 'aggregation': aggregation, 'effects': body, 'context': saved, **kw}


def _record(plan: Plan, ctx: dict[str, Any], to: dict[str, Any], rider: dict[str, Any],
            *, source: dict[str, Any] | None = None, limit: int | None = None) -> dict[str, Any]:
    from app.rules import replace

    return replace.add_record(plan, event='damage', match={'to': to, 'source': source or {}},
                              op={'do': 'prevent_all' if limit is None else 'finite_prevention', 'prevention': True,
                                  'rider': rider, **({'limit': limit, 'allocate': True} if limit is not None else {})},
                              controller=ctx['controller'], source=ctx.get('source_object'), source_card=ctx.get('source_card'),
                              label=ctx.get('name') or 'Prevention')


def _replace_current(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.rules import effects

    # The native descriptor must be the current instruction, so every nested damage
    # replacement pause retains its actual rerun site and original body continuation.
    ctx['effects'][ctx['next'] - 1] = effect
    return effects.PRIMITIVES[effect['do']](plan, ctx, effect)


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, source_shields
    from app.rules.nontarget_creature_choices import key

    mode = e['mode']
    if mode == 'bound_damage':
        return _bound_damage(plan, ctx, e, e['who'])
    if mode == 'commanders':
        from app.rules.sba import power

        targets = [cid for cid in effects._cards(plan, ctx, 'event') if _damageable(plan, cid)]
        commanders = effects._cards(plan, ctx, key('commander creature you control'))
        hits = [(effects._card_source(plan, cid), target, max(0, power(plan.state.cards[cid], plan.ch(plan.state.cards[cid])) or 0))
                for cid in commanders for target in targets]
        return effects._deal(plan, ctx, hits, e) if hits else True
    if mode == 'reflect':
        event = ctx['prevented_event']
        who = 'ref:prevented_source' if 'Creature' in (event.get('src') or {}).get('types', []) else 'ref:from_ctrl'
        return _bound_damage(plan, ctx, e, who)
    if mode == 'trigger':
        return _trigger(plan, ctx, e['outcome'])
    if mode == 'accumulate':
        for trigger in plan.rules.delayed:
            if trigger.id == e['id']:
                trigger.effects[0]['n'] += effects._amount(plan, ctx, AMOUNT)
        return True
    if mode == 'blood':
        from app.rules import replace

        replace.add_record(plan, event='damage', match={'to': {'objects': {'sel': key('creature')}}},
                           op={'do': 'redirect', 'to': 'pid', 'pid': ctx['controller'], 'optional': True, 'external_optional': True},
                           controller=ctx['controller'], source=ctx.get('source_object'), source_card=ctx.get('source_card'), label=ctx['name'])
        return True
    if mode in ('shadowbane', 'samite', 'new_way'):
        outcome = {'shadowbane': [{'do': 'gain_life', 'who': 'you', 'n': AMOUNT}],
                   'samite': [_effect('trigger', outcome='samite')], 'new_way': [_effect('trigger', outcome='new_way')]}[mode]
        rider = _rider(ctx, outcome, colors=['B'] if mode == 'shadowbane' else ['B', 'R'] if mode == 'samite' else [])
        return _replace_current(plan, ctx, {'do': 'source_shield', 'props': {},
                                           'to': 'you_creatures' if mode == 'shadowbane' else 'you',
                                           'once': mode != 'samite', 'rider': rider})
    if mode == 'hallow':
        refs = effects.target_refs(ctx, 'target')
        if refs:
            _record(plan, ctx, {}, _rider(ctx, [{'do': 'gain_life', 'who': 'you', 'n': AMOUNT}]),
                    source={'oids': [refs[0]['object_id'], source_shields.BECOMES + refs[0]['object_id']]})
        return True
    if mode == 'brace':
        to = source_shields._recipient(plan, ctx, {'to': 'target'})
        if to:
            _record(plan, ctx, to, _rider(ctx, [{'do': 'add_counters', 'who': 'ref:to', 'kind': '+1/+1', 'n': AMOUNT}], 'recipient'))
        return True
    if mode in ('comeuppance', 'channel', 'judgment'):
        to = {'players': 'you', 'objects': {'sel': key('planeswalker you control' if mode == 'comeuppance' else 'permanent you control')}}
        if mode == 'judgment':
            to = {'players': 'you'}
        body = ([_effect('reflect')] if mode == 'comeuppance' else
                [{'do': 'may_rest', 'skip': 1}, _effect('bound_damage', who='target')] if mode == 'channel' else
                [_effect('trigger', outcome='judgment')])
        _record(plan, ctx, to, _rider(ctx, body, 'source' if mode in ('comeuppance', 'judgment') else 'batch'),
                source={'controller': 'opponent', **({'types': ['Creature']} if mode == 'judgment' else {})})
        return True
    if mode in ('archon', 'acolyte', 'sacred', 'scars'):
        return _finite(plan, ctx, mode)
    raise ValueError(f'Unknown prevention outcome {mode}')



def _damageable(plan: Plan, card_id: str) -> bool:
    card = plan.state.cards[card_id]
    return card.zone.endswith(':battlefield') and plan.in_game(card) and bool({'Creature', 'Planeswalker', 'Battle'} & plan.ch(card).types)


def _bound_damage(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], who: str) -> bool:
    from app.rules import effects

    n = effects._amount(plan, ctx, AMOUNT)
    recipients = [cid for cid in effects._cards(plan, ctx, who) if _damageable(plan, cid)] + effects._players(plan, ctx, who)
    hits = [(effects._ability_source(plan, ctx), target, n) for target in recipients if n > 0]
    return effects._deal(plan, ctx, hits, e) if hits else True

def _trigger(plan: Plan, ctx: dict[str, Any], outcome: str) -> bool:
    from app.game.rules_state import ObjectRef, TriggerEvent
    from app.rules import context, trigger_multipliers, triggers

    n = context.amount(ctx, 'prevented')
    if n <= 0:
        return True
    event = ctx['prevented_event']
    source = ObjectRef(card=event['source_card'], object_id=event['source_oid']) if event.get('source_card') and event.get('source_oid') else None
    triggered = TriggerEvent(kind='prevention', amount=n, source=source, objects=[source] if source else [],
                             players=context.players(plan, ctx, 'from_ctrl'), combat=bool(event.get('combat')))
    bodies = {
        'vindicator': [{'do': 'damage', 'who': 'target', 'n': {'event_amount': 1}}],
        'new_way': [{'do': 'damage', 'who': 'ref:event', 'n': {'event_amount': 1}},
                    {'do': 'draw', 'who': 'you', 'n': {'event_amount': 1}}],
        'samite': [{'do': 'gain_life', 'who': 'you', 'n': {'event_amount': 1}}],
        'judgment': [_effect('commanders')],
    }
    definition = {'kind': 'triggered', 'effects': bodies[outcome],
                  **({'target': {'what': 'any_other'}} if outcome == 'vindicator' else {})}
    triggers._add(plan, controller=ctx['controller'], source_card=ctx.get('source_card') or '', source_object=ctx.get('source_object') or '',
                  name=ctx.get('name') or '', index=trigger_multipliers.REFLEXIVE if outcome in ('vindicator', 'new_way') else trigger_multipliers.DELAYED,
                  definition=definition, event=triggered)
    return True


def _finite(plan: Plan, ctx: dict[str, Any], mode: str) -> bool:
    from app.game.rules_state import DelayedTrigger
    from app.rules import context, effects, source_shields

    n = effects._amount(plan, ctx, {'devotion': ['W']} if mode == 'acolyte' else {'x': 1}) if mode in ('acolyte', 'archon') else 3 if mode == 'sacred' else 7
    to = {'players': 'you'} if mode == 'archon' else source_shields._recipient(plan, ctx, {'to': 'target:0' if mode == 'acolyte' else 'target'})
    if not to or n <= 0:
        return True
    if mode in ('archon', 'acolyte'):
        body = [_effect('bound_damage', who='target:1' if mode == 'acolyte' else 'target')]
    else:
        cards = effects._cards(plan, ctx, 'target')
        body = []
        if cards and plan.ch(plan.state.cards[cards[0]]).is_creature:
            saved: dict[str, Any] = {}
            context.bind_objects(plan, saved, 'protected', cards)
            tid = secrets.token_hex(4)
            plan.rules.delayed.append(DelayedTrigger(id=tid, controller=ctx['controller'], source_card=ctx.get('source_card'),
                source_object=ctx.get('source_object'), name=ctx.get('name') or '', when={'kind': 'step', 'step': 'end', 'whose': 'next'},
                effects=[{'do': 'add_counters', 'who': 'ref:protected', 'kind': '+0/+1', 'n': 0}], refs=saved['refs'],
                turn=plan.state.turn.number, step=plan.state.turn.phase, created_step=plan.rules.step_serial))
            body = [_effect('accumulate', id=tid)]
    _record(plan, ctx, to, _rider(ctx, body), limit=n)
    return True


PRIMITIVES = {STEP: run}

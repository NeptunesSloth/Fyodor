"""Collect owner placement and private ordering before one simultaneous library move."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption, ObjectRef
from app.rules.plan import decide

if TYPE_CHECKING:
    from app.rules.plan import Plan


def start(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], cards: list[str], before: list[ObjectRef]) -> bool:
    roots = []
    for cid in dict.fromkeys(cards):
        c = plan.state.cards[cid]
        if c.merged:
            pick = next((p for p in c.merged if p.commander_key), c.merged[0])
            parts = [{'id': cid if p is pick else p.id, 'owner': p.owner, 'name': p.name} for p in c.merged if not p.is_token]
        else:
            parts = [] if c.is_token else [{'id': cid, 'owner': c.owner, 'name': c.name}]
        roots.append({'id': cid, 'oid': plan.oid(c), 'zone': c.zone, 'owner': c.owner, 'name': c.name, 'parts': parts})
    request = {'ctx': ctx, 'e': e, 'before': [r.model_dump(mode='json') for r in before], 'roots': roots,
               'owners': [p for p in plan.apnap() if any(r['owner'] == p for r in roots)],
               'places': {}, 'ordered': {}, 'commander_done': []}
    return _next(plan, request)


def _live(plan: Plan, r: dict[str, Any]) -> bool:
    c = plan.state.cards.get(r['id'])
    return c is not None and plan.oid(c) == r['oid'] and c.zone == r['zone']


def _next(plan: Plan, r: dict[str, Any]) -> bool:
    roots = [x for x in r['roots'] if _live(plan, x)]
    for owner in r['owners']:
        mine = [x for x in roots if x['owner'] == owner and x['id'] not in r['places']]
        if not mine:
            continue
        decide(plan, player=owner, kind='choose_cards', prompt='Choose which creatures to put on top of your library; the rest go on the bottom',
               options=[DecisionOption(id=x['id'], label=x['name'] or 'Card', card_id=x['id']) for x in mine],
               min_choices=0, max_choices=len(mine), resume={'step': 'library_placements', 'stage': 'place', 'request': r, 'cards': [x['id'] for x in mine]})
        return False
    # Commander replacement choices happen before cards move or private piles are ordered.
    from app.rules.engine import remembered
    for x in roots:
        c = plan.state.cards[x['id']]
        if not c.commander_key or c.id in r['commander_done']:
            continue
        key = f'{plan.oid(c)}>library'
        answer = plan.rules.answers_903_9b.get(key) or remembered(plan, c.owner, f'commander_zone:{c.commander_key}', 'library')
        if answer is not None:
            r['commander_done'].append(c.id)
            x['command'] = answer == 'yes'
            continue
        decide(plan, player=c.owner, kind='choose_one', prompt=f'Put {c.name} into the command zone instead of your library?',
               options=[DecisionOption(id='yes', label='Command zone'), DecisionOption(id='no', label='Library')],
               resume={'step': 'library_placements', 'stage': 'commander', 'request': r, 'card': c.id, 'key': key}, source=c)
        return False
    parts = [dict(p, place=r['places'][x['id']]) for x in roots for p in x['parts'] if not (x.get('command') and p['id'] == x['id'])]
    for owner in plan.apnap():
        for place in ['top', 'bottom']:
            key = f'{owner}:{place}'
            pile = [p for p in parts if p['owner'] == owner and p['place'] == place]
            if key in r['ordered']:
                continue
            if len(pile) < 2:
                r['ordered'][key] = [p['id'] for p in pile]
                continue
            decide(plan, player=owner, kind='order', prompt=f'Order the cards for the {place} of your library (first chosen ends up ' + ('on top)' if place == 'top' else 'at the very bottom)'),
                   options=[DecisionOption(id=p['id'], label=p['name'] or 'Card', card_id=p['id'] if p['id'] in plan.state.cards else None) for p in pile],
                   min_choices=len(pile), max_choices=len(pile), resume={'step': 'library_placements', 'stage': 'order', 'request': r, 'key': key})
            return False
    positions = {p['id']: p['place'] for p in parts}
    positions.update({x['id']: r['places'][x['id']] for x in roots})
    order = []
    for owner in plan.apnap():
        order += r['ordered'].get(f'{owner}:top', [])
        order += list(reversed(r['ordered'].get(f'{owner}:bottom', [])))
    plan.do({'type': 'move', 'card_ids': [x['id'] for x in roots], 'to': {'zone': 'library'},
             'library_positions': positions, 'library_order': order}, actor=r['ctx']['controller'])
    from app.rules.effects import _moved
    _moved(plan, r['ctx'], r['e'], [ObjectRef.model_validate(x) for x in r['before']])
    return True


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    r = d.resume['request']
    stage = d.resume['stage']
    if stage == 'place':
        for cid in d.resume['cards']:
            r['places'][cid] = 'top' if cid in chosen else 'bottom'
        # Later players know previous public destination choices, never the private pile order.
        for place in ['top', 'bottom']:
            ids = [cid for cid in d.resume['cards'] if r['places'][cid] == place]
            if ids:
                plan.note(f'{plan.name(d.player)} chooses the {place} of their library', actor=d.player, card_ids=ids)
    elif stage == 'commander':
        plan.rules.answers_903_9b[d.resume['key']] = chosen[0]
        r['commander_done'].append(d.resume['card'])
        for x in r['roots']:
            if x['id'] == d.resume['card']:
                x['command'] = chosen[0] == 'yes'
    else:
        r['ordered'][d.resume['key']] = chosen
    if _next(plan, r):
        from app.rules.effects import continue_effects
        continue_effects(plan, r['ctx'])

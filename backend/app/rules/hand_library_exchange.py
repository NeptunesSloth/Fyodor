"""Exchange complete hidden-zone sets simultaneously; this neither draws nor discards."""
from __future__ import annotations

import re
from typing import Any

from app.game.rules_state import DecisionOption
from app.rules.plan import Plan, decide


def exchange(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import replacements

    pid = ctx['controller']
    frame = ctx.get('hand_library_exchange')
    if frame is None:
        frame = {'cards': [{'card': cid, 'oid': plan.oid(plan.state.cards[cid]), 'from': f'{pid}:{zone}',
                            'to': 'library' if zone == 'hand' else 'hand'}
                           for zone in ('hand', 'library') for cid in plan.state.zones.get(f'{pid}:{zone}', [])],
                 'routes': {}, 'next': 0}
        ctx['hand_library_exchange'] = frame
    if any((card := plan.state.cards.get(row['card'])) is None or card.zone != row['from'] or plan.oid(card) != row['oid']
           for row in frame['cards']):
        ctx.pop('hand_library_exchange', None)
        plan.note('The hand and library exchange cannot be completed')
        return True
    while frame['next'] < len(frame['cards']):
        row = frame['cards'][frame['next']]
        card = plan.state.cards[row['card']]
        # 903.9b applies to either direction, including commanders already in a hidden zone.
        command = replacements._commander_instead(plan, card, row['to'])
        if command is None:
            where = 'your hand' if row['to'] == 'hand' else 'your library'
            decide(plan, player=card.owner, kind='confirm', prompt=f'Your commander would enter {where}: put it into the command zone instead? (903.9b)',
                   options=[DecisionOption(id='yes', label='Command zone'), DecisionOption(id='no', label=f'Into {where}')],
                   resume={'step': 'exchange_hand_library', 'ctx': ctx, 'key': f"{row['oid']}>{row['to']}"},
                   memory_key=f'commander_zone:{card.commander_key}', memory_context=row['to'])
            return False
        frame['routes'][card.id] = {'player': card.owner, 'zone': 'command' if command else row['to']}
        frame['next'] += 1
    routes = frame['routes']
    if routes:
        # Every individual commander replacement has been prepared before this one event.
        plan.do({'type': 'move', 'card_ids': list(routes), 'to': {'zone': 'hand', 'player': pid}, 'routes': routes}, actor=pid)
    ctx.pop('hand_library_exchange', None)
    plan.note(f'{plan.name(pid)} exchanges their hand and library', actor=pid)
    return True


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    plan.rules.answers_903_9b[d.resume['key']] = chosen[0]
    if exchange(plan, d.resume['ctx'], {}):
        continue_effects(plan, d.resume['ctx'])


TEMPLATES = [(re.compile(r'^exchange your hand and library$'), lambda m: ([{'do': 'exchange_hand_library'}], None))]
PRIMITIVES = {'exchange_hand_library': exchange}
RESUME = {'exchange_hand_library': resume}

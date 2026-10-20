"""Optional counters chosen by each player, committed together with actual putters."""
from __future__ import annotations

import re
from typing import Any

from app.game.rules_state import DecisionOption
from app.rules.plan import Plan, decide

_PATTERN = re.compile(r'^Each player may put (?P<n>one|two|three|four|five|\d+) (?P<kind>\+1/\+1|-1/-1) counters? on a creature they control\. (?P<rider>Goad each creature that had counters put on it this way\.|For each opponent who does, you gain protection from that player until your next turn\.)$', re.I)


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    m = _PATTERN.fullmatch(body.strip())
    if m is None:
        return None
    words = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5}
    n = words.get(m['n'].lower())
    return ([{'do': 'each_counter_offer', 'kind': m['kind'], 'n': int(m['n']) if n is None else n,
              'goad': m['rider'].lower().startswith('goad'),
              'player_protection': m['rider'].lower().startswith('for each')}], None, False)


def eligible(plan: Plan, player: str, kind: str) -> list[str]:
    from app.rules import prohibitions

    return [c.id for c in plan.state.cards.values() if c.zone.endswith(':battlefield') and c.controller == player
            and plan.in_game(c) and plan.ch(c).is_creature and prohibitions.cant_counters(plan, c.id, None, kind) is None]


def offer(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    frame = {'ctx': ctx, 'e': e, 'players': plan.apnap(), 'index': 0, 'chosen': []}
    _next(plan, frame)
    return False


def _next(plan: Plan, frame: dict[str, Any]) -> None:
    while frame['index'] < len(frame['players']):
        player = frame['players'][frame['index']]
        options = eligible(plan, player, frame['e']['kind']) if player in plan.live() else []
        if not options:
            frame['index'] += 1
            continue
        decide(plan, player=player, kind='choose_cards',
               prompt=f"{frame['ctx'].get('name') or 'The ability'}: choose a creature you control to receive {frame['e']['n']} {frame['e']['kind']} counters, or none",
               options=[DecisionOption(id=c, card_id=c, label=plan.state.cards[c].name) for c in options],
               min_choices=0, max_choices=1, resume={'step': 'counter_offer', 'frame': frame})
        return
    _put(plan, frame)


def resume(plan: Plan, decision: Any, chosen: list[str]) -> None:
    frame = decision.resume['frame']
    player = frame['players'][frame['index']]
    if chosen:
        cid = chosen[0]
        frame['chosen'].append({'card': cid, 'object': plan.oid(cid), 'player': player})
        plan.note(f"{plan.name(player)} chooses {plan.state.cards[cid].name}", [cid], actor=player)
    frame['index'] += 1
    _next(plan, frame)


def _put(plan: Plan, frame: dict[str, Any]) -> None:
    from app.rules import replace

    frame['chosen'] = [pick for pick in frame['chosen'] if pick['card'] in eligible(plan, pick['player'], frame['e']['kind'])
                       and plan.oid(pick['card']) == pick['object']]
    frame['start'] = plan.rules.batch
    then = {'do': 'counter_offer_done', 'frame': frame}
    puts = [(pick['card'], frame['e']['kind'], int(frame['e']['n'])) for pick in frame['chosen']]
    if replace.put_counters(plan, puts, by=frame['ctx']['controller'], effect=True, then=then,
                            putters=[pick['player'] for pick in frame['chosen']]):
        done(plan, then)


def done(plan: Plan, then: dict[str, Any]) -> None:
    from app.rules import context, effects, keyword_actions

    frame = then['frame']
    received = {event.object_id for event in plan.rules.events if event.kind == 'counters' and event.amount > 0
                and event.counter == frame['e']['kind'] and event.batch > frame['start']}
    picked = [p['card'] for p in frame['chosen'] if p['object'] in received
              and p['card'] in plan.state.cards and plan.oid(p['card']) == p['object']]
    if picked and frame['e'].get('goad'):
        context.bind_objects(plan, frame['ctx'], 'counter_offer_received', picked)
        keyword_actions.goad(plan, frame['ctx'], {'do': 'goad', 'who': 'ref:counter_offer_received'})
    if frame['e'].get('player_protection'):
        from app.rules import player_shields

        for player in dict.fromkeys(p['player'] for p in frame['chosen']):
            if player != frame['ctx']['controller']:
                player_shields._add(plan, frame['ctx'], 'protection', f'player:{player}', 'next_turn')
    effects.continue_effects(plan, frame['ctx'])


PRIMITIVES = {'each_counter_offer': offer}
RESUME = {'counter_offer': resume}

from app.rules import replace as _replace  # noqa: E402, I001

_replace.THEN['counter_offer_done'] = done

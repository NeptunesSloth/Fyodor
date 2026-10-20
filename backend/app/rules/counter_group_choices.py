"""Choose counter quantities separately on public permanent objects, then remove or move together."""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypedDict

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.rules.plan import Plan


class Row(TypedDict):
    card: str
    object_id: str
    kind: str
    available: int


class Frame(TypedDict):
    rows: list[Row]
    choices: list[int]
    destination: dict[str, Any] | None


STEP = 'choose_group_counters'
KEY = '_group_counter_choices'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import language, scripts

    body = body[:1].upper() + body[1:]
    move = re.fullmatch(r'Move any number of (?P<kind>\+1/\+1 )?counters from (?P<group>(?:among )?creatures you control|other permanents you control) onto (?P<to>that creature|~)\.', body)
    prefix = re.fullmatch(r'(?P<before>Put a hexproof counter on target creature)\. Then (?P<tail>move .+)\.', body)
    if prefix is not None:
        first = scripts.parse_effects(prefix['before'] + '.')
        rest = parse(prefix['tail'][0].upper() + prefix['tail'][1:] + '.')
        if first is not None and rest is not None:
            return first[0] + rest[0], first[1], first[2]
    if move is not None:
        group = move['group'].removeprefix('among ')
        sel = language.selectors.parse(group)
        if sel is None:
            return None
        return ([{'do':STEP, 'sel':sel.key(), 'kind':(move['kind'] or '').strip() or None,
                  'to':'target' if move['to'] == 'that creature' else 'self'}], None, False)
    patterns = [
        (r'Remove any number of counters from among permanents on the battlefield\. You draw cards and lose life equal to the number of counters removed this way\.',
         'permanents', None, None, None, 'draw_loss'),
        (r'You may remove any number of \+1/\+1 counters from among creatures you control\. If you do, put twice that many \+1/\+1 counters on ~\.',
         'creatures you control', '+1/+1', None, None, 'double'),
        (r'You may remove a lore counter from each of any number of Sagas you control\. Put a \+1/\+1 counter on ~ for each lore counter removed this way\.',
         'Sagas you control', 'lore', None, 1, 'put'),
        (r'Then you may remove up to three stun counters from among all permanents\. Draw cards equal to the number of stun counters removed this way\.',
         'permanents', 'stun', 3, None, 'draw'),
    ]
    # Targeting/tapping remains the native language machinery; only the following counter-choice instruction is new.
    spider = re.fullmatch(r'(?P<before>Tap target creature defending player controls and put a stun counter on it)\. (?P<tail>Then you may remove .+)', body)
    if spider is not None:
        first, rest = scripts.parse_effects(spider['before'] + '.'), parse(spider['tail'])
        if first is not None and rest is not None:
            return first[0] + rest[0], first[1], first[2]
    for pattern, group, kind, cap, each, after in patterns:
        if re.fullmatch(pattern, body):
            sel = language.selectors.parse(group)
            if sel is None:
                return None
            return ([{'do':STEP, 'sel':sel.key(), 'kind':kind, 'cap':cap, 'each':each, 'after':after}], None, False)
    return None


def _live(plan: Plan, row: Mapping[str, Any]) -> bool:
    c = plan.state.cards.get(row['card'])
    return c is not None and c.zone.endswith(':battlefield') and plan.oid(c) == row['object_id']


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import (
        context,
        counter_removal_results,
        effects,
        group_choice,
        prohibitions,
        replace,
        selectors,
    )
    from app.rules.plan import decide

    index = str(int(ctx.get('next') or 0) - 1)
    frames = ctx.setdefault(KEY, {})
    if index not in frames:
        destination = None
        if e.get('to'):
            dest = effects._cards(plan, ctx, e['to'])
            if len(dest) != 1 or (ref := context.ref_of(plan, dest[0])) is None:
                return True
            destination = ref.model_dump(mode='json')
        rows: list[Row] = []
        for cid in selectors.candidates(plan, selectors.from_key(e['sel']), ctx['controller'], ctx.get('source_card')):
            c = plan.state.cards[cid]
            if destination is not None and destination['card'] == cid:
                continue
            for kind, n in sorted(c.counters.items()):
                if n <= 0 or (e.get('kind') and kind != e['kind']) or prohibitions.cant_remove_counters(plan, cid, kind):
                    continue
                if destination is not None and prohibitions.cant_counters(plan, destination['card'], None, kind):
                    continue
                rows.append({'card':cid, 'object_id':plan.oid(c), 'kind':kind, 'available':min(n, e['each']) if e.get('each') else n})
        frame: Frame = {'rows':rows, 'choices':[], 'destination':destination}
        frames[index] = frame
    frame = frames[index]
    while len(frame['choices']) < len(frame['rows']):
        row = frame['rows'][len(frame['choices'])]
        remaining = row['available'] if e.get('cap') is None else min(row['available'], max(0, e['cap'] - sum(frame['choices'])))
        if not _live(plan, row) or not remaining:
            frame['choices'].append(0)
            continue
        decide(plan, player=ctx['controller'], kind='choose_one',
               prompt=f"{ctx.get('name') or 'Counter choice'}: remove 0–{remaining} {row['kind']} counters from {plan.state.cards[row['card']].name}",
               options=[DecisionOption(id=group_choice.NUMBER, label='Type a number ≥ 0', group='number')],
               source=plan.state.cards[row['card']], resume={'step':STEP, 'ctx':ctx, 'e':e, 'maximum':remaining})
        return False
    destination = frame['destination']
    total = 0
    puts: list[tuple[str, str, int]] = []
    for row, selected in zip(frame['rows'], frame['choices'], strict=True):
        if not selected or not _live(plan, row):
            continue
        if destination is not None and (not _live(plan, destination) or prohibitions.cant_counters(plan, destination['card'], None, row['kind'])):
            continue
        c = plan.state.cards[row['card']]
        actual = counter_removal_results.remove(plan, c.id, row['kind'], selected, by=ctx['controller'])
        if actual:
            total += actual
            if destination is not None:
                puts.append((destination['card'], row['kind'], actual))
    frames.pop(index, None)
    if e.get('bind'):
        context.bind_amount(ctx, e['bind'], total)
    if destination is not None:
        return not puts or replace.put_counters(plan, puts, by=ctx['controller'], then=effects._then(ctx, e), ctx=ctx)
    # Expand the actual result into ordinary native effects. A paused draw/life replacement therefore retains the same continuation.
    after = e.get('after')
    tail: list[dict[str, Any]] = []
    if after in ('draw', 'draw_loss'):
        tail.append({'do':'draw', 'who':'you', 'n':total})
    if after == 'draw_loss':
        tail.append({'do':'lose_life', 'who':'you', 'n':total})
    if after in ('put', 'double'):
        tail.append({'do':'add_counters', 'who':'self', 'kind':'+1/+1', 'n':total * (2 if after == 'double' else 1)})
    ctx['effects'][ctx['next']:ctx['next']] = tail
    return True


def resume(plan: Plan, decision: Any, chosen: list[str]) -> None:
    from app.rules import effects

    if len(chosen) != 1 or not chosen[0].isdigit() or not 0 <= int(chosen[0]) <= decision.resume['maximum']:
        raise ActionError('Choose a number in the offered range')
    ctx, e = decision.resume['ctx'], decision.resume['e']
    index = str(int(ctx.get('next') or 0) - 1)
    ctx[KEY][index]['choices'].append(int(chosen[0]))
    if run(plan, ctx, e):
        effects.continue_effects(plan, ctx)


PRIMITIVES = {STEP:run}
RESUME = {STEP:resume}

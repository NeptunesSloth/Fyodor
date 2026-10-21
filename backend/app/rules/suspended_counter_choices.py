"""Counter choices on permanent objects and physical suspended cards (702.62b)."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, TypedDict

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP = 'suspended_counter_choice'
KEY = '_suspended_counter_choices'


class Frame(TypedDict):
    refs: list[dict[str, Any]]
    selected: str | None
    kind: str | None
    mode: str | None


def definition(text: str) -> dict[str, Any] | None:
    from app.rules import events

    match = re.fullmatch(r"Whenever (?P<event>an opponent casts a spell|a card is put into an opponent's graveyard from anywhere), if this card is suspended, (?P<body>.+)\.", text)
    if match is None:
        return None
    body = match['body']
    if body in ('remove a time counter from it', 'you may remove a time counter from this card'):
        action = [{'do':STEP, 'mode':'source_remove', 'kind':'time', 'n':1}]
        optional = body.startswith('you may')
    elif body == 'that player may put a time counter on this card':
        action, optional = [{'do':STEP, 'kind':'time', 'mode':'put_optional', 'chooser':'event_player'}], False
    else:
        return None
    cond = events.parse_condition(match['event'])
    assert cond is not None
    return {'kind':'triggered', 'trigger':'event', 'cond':{**cond, 'exiled':True},
            'if':{'object':'self', 'test':'suspended'}, 'optional':optional, 'target':None, 'effects':action}


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import selectors

    body = body.strip()
    body = body[:1].upper() + body[1:]
    if body == 'Choose a counter on target permanent or suspended card. Remove that counter from that permanent or card or put another of those counters on it.':
        union = selectors.parse('permanent or suspended card')
        assert union is not None
        return ([{'do':STEP, 'who':'target', 'mode':'choose'}], union.key(), False)
    if body == 'Choose target permanent you control or suspended card you own. If that permanent or card has a time counter on it, you may remove a time counter from it or put another time counter on it.':
        own_union = selectors.parse('permanent you control or suspended card you own')
        assert own_union is not None
        return ([{'do':STEP, 'who':'target', 'kind':'time', 'mode':'choose_optional'}], own_union.key(), False)
    if body == 'Choose a suspended card you own and remove that many time counters from it.':
        return ([{'do':STEP, 'mode':'amy', 'n':{'event_amount':1}}], None, False)
    if body == 'Remove a time counter from this card.':
        return ([{'do':'remove_counters', 'who':'self_gy_exile', 'kind':'time', 'n':1}], None, False)
    if body in ('Remove two time counters from each permanent and each suspended card.',
                'Put two time counters on each permanent with a time counter on it and each suspended card.'):
        putting = body.startswith('Put')
        return ([{'do':STEP, 'mode':'bulk_put' if putting else 'bulk_remove', 'kind':'time', 'n':2}], None, False)
    return None


def _live(plan: Plan, ref: dict[str, Any]) -> bool:
    card = plan.state.cards.get(ref['card'])
    return card is not None and plan.oid(card) == ref['object_id'] and card.zone.endswith((':battlefield', ':exile'))


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, counter_removal_results, effects, replace, suspend_grants
    from app.rules.plan import decide

    key = str(int(ctx.get('next') or 0) - 1)
    frames = ctx.setdefault(KEY, {})
    mode = e['mode']
    if key not in frames:
        if mode in ('source_remove', 'put_optional'):
            source = plan.state.cards.get(ctx.get('source_card') or '')
            cards = [source.id] if source is not None and source.zone.endswith(':exile') and plan.oid(source) == ctx.get('source_object') else []
        elif mode == 'amy':
            cards = [c.id for c in plan.state.cards.values() if c.owner == ctx['controller'] and suspend_grants.is_suspended(plan, c)]
        elif mode.startswith('bulk_'):
            cards = [c.id for c in plan.state.cards.values() if plan.in_game(c) and
                     ((c.zone.endswith(':battlefield') and (mode != 'bulk_put' or c.counters.get('time', 0) > 0))
                      or suspend_grants.is_suspended(plan, c))]
        else:
            cards = effects._cards(plan, ctx, e['who'])
        refs = [ref.model_dump(mode='json') for cid in cards if (ref := context.ref_of(plan, cid)) is not None]
        frame: Frame = {'refs':refs, 'selected':None, 'kind':e.get('kind'), 'mode':None}
        frames[key] = frame
    frame = frames[key]
    refs = [ref for ref in frame['refs'] if _live(plan, ref)]
    if not refs:
        frames.pop(key, None)
        return True
    chooser = effects._players(plan, ctx, e.get('chooser', 'you'))
    if len(chooser) != 1:
        frames.pop(key, None)
        return True
    player = chooser[0]
    if mode == 'source_remove':
        counter_removal_results.remove(plan, refs[0]['card'], 'time', int(e['n']), by=player)
        frames.pop(key, None)
        return True
    if mode == 'amy' and frame['selected'] is None:
        options = [DecisionOption(id=ref['card'], label=plan.state.cards[ref['card']].name) for ref in refs]
        decide(plan, player=player, kind='choose_one', prompt=f"{ctx.get('name') or 'The ability'}: choose a suspended card you own",
               options=options, resume={'step':STEP, 'ctx':ctx, 'e':e, 'answer':'selected'})
        return False
    if frame['selected'] is not None:
        refs = [ref for ref in refs if ref['card'] == frame['selected']]
        if not refs:
            frames.pop(key, None)
            return True
    if mode == 'amy':
        card = plan.state.cards[refs[0]['card']]
        counter_removal_results.remove(plan, card.id, 'time', effects._amount(plan, ctx, e['n']), by=ctx['controller'])
        frames.pop(key, None)
        return True
    if mode.startswith('bulk_'):
        cards = [ref['card'] for ref in refs]
        if mode == 'bulk_remove':
            group = plan.rules.batch + 1
            amounts: dict[int, list[str]] = {}
            for cid in cards:
                amount = min(2, max(0, plan.state.cards[cid].counters.get('time', 0)))
                if amount:
                    amounts.setdefault(amount, []).append(cid)
            for amount, ids in amounts.items():
                plan.do({'type':'counter', 'card_ids':ids, 'kind':'time', 'delta':-amount, 'group':group}, actor=ctx['controller'])
            frames.pop(key, None)
            return True
        puts = [(cid, 'time', 2) for cid in cards]
    else:
        card = plan.state.cards[refs[0]['card']]
        kinds = [kind for kind, n in sorted(card.counters.items()) if n > 0 and (e.get('kind') is None or kind == e['kind'])]
        if mode != 'put_optional' and not kinds:
            frames.pop(key, None)
            return True
        if frame['kind'] is None:
            decide(plan, player=player, kind='choose_one', prompt=f"{ctx.get('name') or 'Counter choice'}: choose a counter on {card.name}",
                   options=[DecisionOption(id=kind, label=kind) for kind in kinds], source=card,
                   resume={'step':STEP, 'ctx':ctx, 'e':e, 'answer':'kind'})
            return False
        if frame['mode'] is None and mode == 'choose':
            from app.rules import counter_restrictions43

            assert frame['kind'] is not None
            frame['mode'] = counter_restrictions43.fixed_suspended_mode(plan, card.id, frame['kind'])
        if frame['mode'] is None:
            options = ([DecisionOption(id='add', label='Put another counter on it')] if mode == 'put_optional' else
                       [DecisionOption(id='remove', label='Remove a counter'), DecisionOption(id='add', label='Put another counter on it')])
            if mode in ('put_optional', 'choose_optional'):
                options.append(DecisionOption(id='decline', label="Don't change its counters"))
            decide(plan, player=player, kind='choose_one', prompt=f"{ctx.get('name') or 'Counter choice'}: {card.name}",
                   options=options, source=card, resume={'step':STEP, 'ctx':ctx, 'e':e, 'answer':'mode'})
            return False
        kind = frame['kind']
        assert kind is not None
        if frame['mode'] == 'decline':
            frames.pop(key, None)
            return True
        if frame['mode'] == 'remove':
            counter_removal_results.remove(plan, card.id, kind, 1, by=player)
            frames.pop(key, None)
            return True
        puts = [(card.id, kind, 1)]
    # Keep the original descriptor and chosen frame while replacement order pauses.
    answers = replace._ctx_answers(ctx)
    planned = replace.plan_counters(plan, puts, by=player, effect=True, entering=None, answers=answers, ask=True)
    if isinstance(planned, replace.Ask):
        then = replace.rerun_then(ctx, e)
        assert then is not None
        replace.ask(plan, planned, answers, then)
        return False
    replace.do_counters(plan, planned, by=player)
    frames.pop(key, None)
    return True


def resume(plan: Plan, decision: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx, e = decision.resume['ctx'], decision.resume['e']
    key = str(int(ctx.get('next') or 0) - 1)
    ctx[KEY][key][decision.resume['answer']] = chosen[0]
    if run(plan, ctx, e):
        effects.continue_effects(plan, ctx)


PRIMITIVES = {STEP:run}
RESUME = {STEP:resume}

"""Untargeted counter distributions are chosen during resolution (CR 608.2d)."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, TypedDict

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP = 'distribute_counters_resolving'
KEY = '_resolving_counter_distribution'


class Recipient(TypedDict):
    card: str
    object_id: str


class Frame(TypedDict):
    total: int
    available: list[Recipient]
    selected: list[Recipient]
    shares: list[int]
    allocating: bool


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import language, scripts, selectors, values

    text = body[:1].upper() + body[1:]
    # A resolving return's second target is the player, not any recipient of the subsequent counters.
    invoke = re.fullmatch(r'Return target permanent card from your graveyard to the battlefield, then distribute (?P<n>\w+) (?P<kind>\+1/\+1) counters among any number of (?P<group>creatures and/or Vehicles) target player controls\.', text)
    if invoke is not None:
        first = scripts.parse_effects('Return target permanent card from your graveyard to the battlefield.')
        n = values.parse_amount(invoke['n'])
        sel = selectors.parse(invoke['group'])
        if first is None or n is None or sel is None:
            return None
        targets = [language.target_group('target permanent card from your graveyard'), language.target_group('target player')]
        if any(g is None for g in targets):
            return None
        return ([{**e, 'who':'target:0'} for e in first[0]] +
                [{'do':STEP, 'who':f'controlled:target:1|{sel.key()}', 'n':n, 'kind':invoke['kind']}], targets, False)
    feast = re.fullmatch(r'You gain (?P<amount>that much|X) life and distribute (?:that many|X) \+1/\+1 counters among any number of creatures you control(?:, where X is (?P<value>.+))?\.', text)
    if feast is not None:
        value = values.parse_count(feast['value'] or 'the number of creatures that died this turn')
        sel = selectors.parse('creatures you control')
        if value is None or sel is None:
            return None
        return ([{'do':'life_and_counter_distribution', 'who':sel.key(), 'n':value, 'kind':'+1/+1'}], None, False)
    hydra = re.fullmatch(r'You may distribute a number of \+1/\+1 counters equal to the number of \+1/\+1 counters on ~ among any number of creatures you control\.', text)
    if hydra is not None:
        sel = selectors.parse('creatures you control')
        assert sel is not None
        return ([{'do':STEP, 'who':sel.key(), 'n':{'counters':'+1/+1', 'on':'self'}, 'kind':'+1/+1'}], None, False)
    stumps = re.fullmatch(r'Distribute X \+1/\+1 counters among it and any number of commanders\.', text)
    if stumps is not None:
        sel = selectors.parse('commanders')
        if sel is None:
            return None
        return ([{'do':STEP, 'who':'union:self+' + sel.key(), 'n':{'x':1}, 'kind':'+1/+1'}], None, False)
    snow = re.fullmatch(r'Distribute X \+1/\+1 counters among any number of creatures you control, where X is the amount of \{S\} spent to cast this spell\. Then (?P<tail>draw a card for each creature you control with power 4 or greater)\.', text)
    if snow is not None:
        sel = selectors.parse('creatures you control')
        after = scripts.parse_effects(snow['tail'][:1].upper() + snow['tail'][1:] + '.')
        if sel is None or after is None or after[1] is not None or after[2]:
            return None
        return ([{'do':STEP, 'who':sel.key(), 'n':{'mana_from':'Snow'}, 'kind':'+1/+1'}, *after[0]], None, False)
    return None


def life_and_counters(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    total = max(0, effects._amount(plan, ctx, e['n']))
    ctx['effects'][ctx['next']:ctx['next']] = [
        {'do':'gain_life', 'who':'you', 'n':total}, {**e, 'do':STEP, 'n':total}]
    return True


def _live(plan: Plan, recipient: Recipient) -> bool:
    c = plan.state.cards.get(recipient['card'])
    return c is not None and c.zone.endswith(':battlefield') and plan.oid(c) == recipient['object_id']


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, group_choice, prohibitions, replace
    from app.rules.plan import decide

    key = str(int(ctx.get('next') or 0) - 1)
    frames = ctx.setdefault(KEY, {})
    if key not in frames:
        total = max(0, effects._amount(plan, ctx, e['n']))
        if not total:
            return True
        available: list[Recipient] = [{'card':cid, 'object_id':plan.oid(cid)} for cid in effects._cards(plan, ctx, e['who'])
                                     if plan.state.cards[cid].zone.endswith(':battlefield') and not prohibitions.cant_counters(plan, cid, None, e['kind'])]
        frame: Frame = {'total':total, 'available':available, 'selected':[], 'shares':[], 'allocating':False}
        frames[key] = frame
    frame = frames[key]
    if not frame['allocating']:
        available = [r for r in frame['available'] if _live(plan, r) and r not in frame['selected']
                     and not prohibitions.cant_counters(plan, r['card'], None, e['kind'])]
        if available and len(frame['selected']) < frame['total']:
            decide(plan, player=ctx['controller'], kind='choose_one',
                   prompt=f"{ctx.get('name') or 'Distribute counters'}: choose recipients ({frame['total']} {e['kind']} counters), or finish",
                   options=[DecisionOption(id='done', label='Finish choosing recipients'),
                            *[DecisionOption(id=r['card'], label=plan.state.cards[r['card']].name, card_id=r['card']) for r in available]],
                   resume={'step':STEP, 'ctx':ctx, 'e':e, 'stage':'recipients'})
            return False
        frame['allocating'] = True
    while len(frame['shares']) < len(frame['selected']):
        remaining = frame['total'] - sum(frame['shares'])
        recipients_left = len(frame['selected']) - len(frame['shares'])
        maximum = remaining - recipients_left + 1
        if maximum == 1 or recipients_left == 1:
            frame['shares'].append(remaining if recipients_left == 1 else 1)
            continue
        recipient = frame['selected'][len(frame['shares'])]
        decide(plan, player=ctx['controller'], kind='choose_one',
               prompt=f"{ctx.get('name') or 'Distribute counters'}: assign 1–{maximum} {e['kind']} counters to {plan.state.cards[recipient['card']].name}",
               options=[DecisionOption(id=group_choice.NUMBER, label='Type a number ≥ 1', group='number')],
               resume={'step':STEP, 'ctx':ctx, 'e':e, 'stage':'amount', 'maximum':maximum})
        return False
    puts = [(r['card'], e['kind'], n) for r,n in zip(frame['selected'], frame['shares'], strict=True)
            if _live(plan, r)]
    if puts:
        answers = replace._ctx_answers(ctx)
        result = replace.plan_counters(plan, puts, by=ctx['controller'], effect=True, entering=None, answers=answers, ask=True)
        if isinstance(result, replace.Ask):
            then = replace.rerun_then(ctx, e)
            assert then is not None
            replace.ask(plan, result, answers, then)
            return False
        replace.do_counters(plan, result, by=ctx['controller'])
    frames.pop(key, None)
    return True


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx, e = d.resume['ctx'], d.resume['e']
    frame = ctx[KEY][str(int(ctx.get('next') or 0) - 1)]
    if len(chosen) != 1:
        raise ActionError('Choose one recipient or amount')
    if d.resume['stage'] == 'recipients':
        if chosen[0] == 'done':
            frame['allocating'] = True
        else:
            recipients = [r for r in frame['available'] if r['card'] == chosen[0] and r not in frame['selected'] and _live(plan,r)]
            if len(recipients) != 1:
                raise ActionError('Choose an available recipient')
            frame['selected'].append(recipients[0])
    else:
        if not chosen[0].isdigit() or not 1 <= int(chosen[0]) <= d.resume['maximum']:
            raise ActionError('Choose an amount in the offered range')
        frame['shares'].append(int(chosen[0]))
    if run(plan, ctx, e):
        effects.continue_effects(plan, ctx)


PRIMITIVES = {STEP:run, 'life_and_counter_distribution':life_and_counters}
RESUME = {STEP:resume}

"""CR 122.5: choose how to move counters from one permanent onto several others.

Choices happen during resolution, without targeting or spending the source counters yet.
All chosen moves are then performed together, through the ordinary counter replacements.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption
from app.rules import prohibitions, replace, selectors
from app.rules.plan import decide

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP = 'distribute_moved_counters'


def move(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    sources = effects._cards(plan, ctx, 'self')
    if len(sources) != 1:
        return True
    source = plan.state.cards[sources[0]]
    if not source.zone.endswith(':battlefield'):
        return True
    have = source.counters.get(e['kind'], 0)
    if have <= 0:
        return True
    return _ask(plan, ctx, e, source.id, plan.oid(source), have, {})


def _pool(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], source: str) -> list[str]:
    return [cid for cid in selectors.candidates(plan, selectors.from_key(e['sel']), ctx['controller'], source)
            if cid != source and not prohibitions.cant_counters(plan, cid, None, e['kind'])]


def _ask(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], source: str, oid: str,
         remaining: int, shares: dict[str, int]) -> bool:
    pool = _pool(plan, ctx, e, source)
    if remaining <= 0 or not pool:
        return _finish(plan, ctx, e, source, oid, shares)
    decide(plan, player=ctx['controller'], kind='choose_one',
           prompt=f"Move {e['kind']} counters: choose another creature ({remaining} remaining), or finish",
           options=[DecisionOption(id='done', label='Finish moving counters'),
                    *[DecisionOption(id=cid, label=plan.state.cards[cid].name or 'Creature', card_id=cid) for cid in pool]],
           resume={'step': STEP, 'ctx': ctx, 'e': e, 'source': source, 'oid': oid,
                   'remaining': remaining, 'shares': shares})
    return False


def _finish(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], source: str, oid: str,
            shares: dict[str, int]) -> bool:
    from app.rules import counter_removal_results, effects, prohibitions

    card = plan.state.cards.get(source)
    if card is None or plan.oid(card) != oid or not card.zone.endswith(':battlefield'):
        return True
    valid = set(_pool(plan, ctx, e, source))
    shares = {cid: n for cid, n in shares.items() if cid in valid and n > 0}
    total = sum(shares.values())
    if not total or prohibitions.cant_remove_counters(plan, source, e['kind']):
        return True
    if total > card.counters.get(e['kind'], 0):
        raise ActionError('The source no longer has that many counters')
    counter_removal_results.remove(plan, source, e['kind'], total, by=ctx['controller'])
    return replace.put_counters(plan, [(cid, e['kind'], n) for cid, n in shares.items()],
                                by=ctx['controller'], then=effects._then(ctx, e), ctx=ctx)


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    if len(chosen) != 1 or chosen[0] not in {o.id for o in d.options}:
        raise ActionError('Choose one of the offered options')
    ctx, e = r['ctx'], r['e']
    shares = dict(r['shares'])
    if r.get('recipient'):
        n = int(chosen[0])
        recipient = r['recipient']
        shares[recipient] = shares.get(recipient, 0) + n
        complete = _ask(plan, ctx, e, r['source'], r['oid'], r['remaining'] - n, shares)
    elif chosen[0] == 'done':
        complete = _finish(plan, ctx, e, r['source'], r['oid'], shares)
    else:
        decide(plan, player=d.player, kind='choose_one', prompt=f"How many {e['kind']} counters to move?",
               options=[DecisionOption(id=str(i), label=str(i)) for i in range(1, r['remaining'] + 1)],
               resume={**r, 'recipient': chosen[0]})
        return
    if complete:
        effects.continue_effects(plan, ctx)


PRIMITIVES = {STEP: move}

"""Latest-mill pairs, prepared 616 choices, and bounded mandatory continuations.

A processing checkpoint is not a game choice to stop. A mandatory draw is proved
only when every remaining card necessarily shuffles itself back, every possible
next batch contains a matching pair, and no intervening draw changes the library.
Hidden cards are used only for adjudication; no names or counts are published.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption, emit, track

if TYPE_CHECKING:
    from app.rules.plan import Plan

BUDGET = 32
_PATTERN = re.compile(r'^((?:Target player|Target opponent|You) mills?|Mill) two cards\. If two (?P<nonland>nonland )?cards that share a (?P<property>color|card type) were milled this way, (?P<draw>draw a card and )?repeat this process\.$', re.IGNORECASE)


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import language

    body = body.strip()
    m = _PATTERN.fullmatch(body)
    if m is None:
        return None
    target = 'target opponent' if body.lower().startswith('target opponent') else 'target player' if body.lower().startswith('target player') else None
    draw = bool(m['draw'])
    out: list[dict[str, Any]] = [{'do': 'mill_pair', 'who': 'target' if target else 'you', 'n': 2},
        {'do': 'mill_pair_test', 'property': 'colors' if m['property'].lower() == 'color' else 'types',
         'nonland': bool(m['nonland']), 'skip': 2 if draw else 1, 'draw': draw}]
    if draw:
        out.append({'do': 'draw', 'who': 'you', 'n': 1})
    out.append({'do': 'mill_pair_again', 'rewind': len(out) + 1})
    group = language.target_group(target) if target else None
    if target and group is None:
        return None
    return out, group['what'] if group is not None else None, False


def _prepare(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> dict[str, Any] | None:
    from app.rules import effects, replace, replacements

    counts = replace.mill_counts(plan, [(p, effects._amount(plan, ctx, e['n'])) for p in effects._players(plan, ctx, e['who'])],
                                 then=replace.rerun_then(ctx, e), ctx=ctx)
    if counts is None:
        return None
    request: dict[str, Any] = {'cards': [], 'counts': [], 'choices': {}}
    for pid, count in counts:
        library = plan.state.zones.get(pid + ':library', [])
        top = library[:count]
        request['counts'].append([pid, len(top)])
        for cid in top:
            ch = plan.ch(plan.state.cards[cid])
            cands = {c.sig: c._asdict() for c in replacements.zone_candidates(plan, plan.state.cards[cid])}
            request['cards'].append({'id': cid, 'colors': list(ch.colors), 'types': list(ch.types), 'cands': list(cands.values())})
    return request


def _choose(plan: Plan, ctx: dict[str, Any], request: dict[str, Any]) -> bool:
    from app.rules.plan import decide

    for card in request['cards']:
        cid, cands = card['id'], card['cands']
        if len(cands) > 1 and cid not in request['choices']:
            decide(plan, player=plan.state.cards[cid].owner, kind='choose_one',
                   prompt=f"{plan.state.cards[cid].name}: which graveyard replacement applies first? (616.1)",
                   options=[DecisionOption(id=str(i), label=c['label'] + ': ' + c['outcome']) for i, c in enumerate(cands)],
                   resume={'step': 'mill_pair_replace', 'ctx': ctx, 'request': request, 'card': cid})
            return False
    _commit(plan, ctx, request)
    return True


def _commit(plan: Plan, ctx: dict[str, Any], request: dict[str, Any]) -> None:
    from app.rules import replace, replacements

    start = plan.rules.batch
    # No shuffle occurs until every selected card has its prepared destination.
    # In particular a shuffle cannot invalidate another card's pending 616 choice.
    shuffles: list[str] = []
    if not any(c['cands'] for c in request['cards']):
        for pid, n in request['counts']:
            if n:
                plan.do({'type': 'mill', 'player': pid, 'count': n}, actor=pid)
    else:
        groups: dict[str, dict[str, dict[str, str]]] = {}
        chosen: list[tuple[str, Any]] = []
        revealed = []
        for c in request['cards']:
            cid = c['id']
            card = plan.state.cards[cid]
            cand = replacements.Cand(**c['cands'][int(request['choices'].get(cid, 0))]) if c['cands'] else None
            outcome = cand.outcome if cand else 'graveyard'
            position = 'bottom' if outcome == 'library:bottom' else 'top'
            groups.setdefault(position, {})[cid] = {'player': card.owner, 'zone': outcome.split(':')[0]}
            if cand:
                chosen.append((cid, cand))
                if cand.used:
                    plan.rules.exile_if_graveyard = [o for o in plan.rules.exile_if_graveyard if o != plan.oid(card)]
                if outcome == 'library:shuffle':
                    revealed.append(cid)
                    if card.owner not in shuffles:
                        shuffles.append(card.owner)
        if revealed:
            plan.do({'type': 'reveal', 'card_ids': revealed}, actor=ctx['controller'])
        for position, routes in groups.items():
            plan.do({'type': 'move', 'card_ids': list(routes), 'to': {'zone': 'graveyard'},
                     'routes': routes, 'position': position}, actor=ctx['controller'])
        counters: dict[str, list[str]] = {}
        for cid, cand in chosen:
            replacements._record_link(plan, cid, cand)
            if cand.counter:
                counters.setdefault(cand.counter, []).append(cid)
        for kind, ids in counters.items():
            replacements.mark_exiled_counters(plan, ids, kind, actor=ctx['controller'])
        for _, cand in chosen:
            if cand.rider is not None:
                replacements.run_rider(plan, cand.rider)
        for routes in groups.values():
            for cid, route in routes.items():
                if route['zone'] == 'graveyard':
                    emit(plan.state, 'milled', card=cid, player=route['player'])
        track(plan.state)
        for pid in shuffles:
            plan.do({'type': 'shuffle', 'player': pid, 'zone': 'library'}, actor=pid)
    replace._one_batch(plan, start)
    ctx['mill_pair_batch'] = request


def mill(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    request = _prepare(plan, ctx, e)
    return request is not None and _choose(plan, ctx, request)


def _shared(cards: list[dict[str, Any]], prop: str, nonland: bool) -> bool:
    counts: Counter[str] = Counter()
    for c in cards:
        if not nonland or 'Land' not in c['types']:
            counts.update(set(c[prop]))
    return any(n >= 2 for n in counts.values())


def _mandatory(plan: Plan, request: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import replacements

    # The server can adjudicate using hidden state without publishing that state.
    # Check every possible next batch, not merely one observed shuffle order.
    for pid, count in request['counts']:
        library = plan.state.zones.get(pid + ':library', [])
        take = min(count, len(library))
        if take < 2:
            return False
        masks: set[frozenset[str]] = set()
        empty = 0
        for cid in library:
            card = plan.state.cards[cid]
            cands = {c.sig: c for c in replacements.zone_candidates(plan, card)}
            if len(cands) != 1:
                return False
            cand = next(iter(cands.values()))
            if cand.outcome != 'library:shuffle' or cand.rider or cand.counter or cand.used or cand.link:
                return False
            ch = plan.ch(card)
            props = frozenset() if e['nonland'] and 'Land' in ch.types else frozenset(getattr(ch, e['property']))
            if props:
                masks.add(props)
            else:
                empty += 1
        # Maximum number of cards selectable without any shared property. Empty
        # masks never match; a nonempty mask can appear at most once in such a
        # selection. At most 2**5 color states (card types likewise finite).
        possible: dict[frozenset[str], int] = {frozenset(): empty}
        for mask in masks:
            for used, n in list(possible.items()):
                if not used & mask:
                    union = used | mask
                    possible[union] = max(possible.get(union, 0), n + 1)
        if max(possible.values()) >= take:
            return False
    return bool(request['counts'])


def _draw_inert(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import prohibitions

    if not e['draw']:
        return True
    cap = prohibitions.draw_left(plan, ctx['controller'])
    return cap is not None and cap[0] == 0


def test(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    request = ctx.get('mill_pair_batch', {'cards': []})
    if not _shared(request['cards'], e['property'], e['nonland']):
        ctx['next'] += e['skip']
    elif _draw_inert(plan, ctx, e) and _mandatory(plan, request, e):
        # CR 104.4b / 732.4: every possible next batch is proved to repeat,
        # never inferred from a random repeated order or an iteration limit.
        plan.rules.draw_reason = 'Mandatory loop (104.4b, 732.4)'
        plan.rules.priority = None
        plan.rules.decision = None
        plan.note('The game is a draw: a mandatory mill/shuffle loop cannot end (104.4b, 732.4)')
        return False
    return True


def again(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules.plan import decide

    ctx['next'] -= e['rewind']
    count = int(ctx.get('mill_pair_iterations', 0)) + 1
    ctx['mill_pair_iterations'] = count
    if count % BUDGET == 0 or len(plan.steps) >= plan.max_steps - 24:
        decide(plan, player=ctx['controller'], kind='confirm',
               prompt='Continue resolving the mandatory mill process (no priority is available).',
               options=[DecisionOption(id='continue', label='Continue resolving')],
               resume={'step': 'mill_pair_continue', 'ctx': ctx})
        return False
    return True


def resume_replace(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    request, ctx = d.resume['request'], d.resume['ctx']
    request['choices'][d.resume['card']] = int(chosen[0])
    if _choose(plan, ctx, request):
        continue_effects(plan, ctx)


def resume_continue(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    continue_effects(plan, d.resume['ctx'])


PRIMITIVES = {'mill_pair': mill, 'mill_pair_test': test, 'mill_pair_again': again}
RESUME = {'mill_pair_replace': resume_replace, 'mill_pair_continue': resume_continue}

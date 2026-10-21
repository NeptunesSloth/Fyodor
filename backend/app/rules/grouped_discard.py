"""CR 101.4/118.12: chosen discard payments become one prepared event."""
from __future__ import annotations

from typing import Any

from app.game.rules_state import DecisionOption
from app.rules.plan import Plan, decide


def begin(plan: Plan, ctx: dict[str, Any], queued: list[Any]) -> None:
    from app.rules import context, optional_payment, replacements

    request: dict[str, Any] = {'kind': 'discard_group', 'actor': ctx['controller'], 'cards': [], 'chosen': {}}
    for opt, cost in queued:
        picked = {int(k): list(v) for k, v in opt['chosen'].items()}
        if optional_payment.problem(plan, ctx, cost, opt['payer'], picked) is not None:
            context.bind_payment(ctx, opt['bind'], False)
            continue
        ids = [c for values in picked.values() for c in values]
        refs = [r for r in (context.ref_of(plan, c) for c in ids) if r is not None]
        context.bind_payment(ctx, opt['bind'], True, refs)
        for cid in ids:
            card = plan.state.cards[cid]
            candidates: dict[str, dict[str, Any]] = {c.sig: {'candidate': c._asdict()} for c in replacements.zone_candidates(plan, card)}
            if request['actor'] != card.owner and any(d.get('replacement') == 'discard_battlefield'
                    for d in replacements._definitions(plan, card).values()):
                c = replacements.Cand(card.name, 'battlefield')
                candidates[c.sig] = {'candidate': c._asdict()}
            if (madness := replacements._madness_cost(plan, card)) is not None:
                c = replacements.Cand('Madness', 'exile')
                candidates['madness'] = {'candidate': c._asdict(), 'madness': madness}
            request['cards'].append({'card': cid, 'object': plan.oid(card), 'owner': card.owner,
                                     'candidates': list(candidates.values())})
    if _choose(plan, ctx, request):
        from app.rules.effects import continue_effects

        continue_effects(plan, ctx)


def _choose(plan: Plan, ctx: dict[str, Any], request: dict[str, Any]) -> bool:
    for entry in request['cards']:
        candidates = entry['candidates']
        if len(candidates) > 1 and entry['card'] not in request['chosen']:
            decide(plan, player=entry['owner'], kind='choose_one',
                   prompt=f"{plan.state.cards[entry['card']].name}: choose its discard replacement (616.1)",
                   options=[DecisionOption(id=str(i), label=c['candidate']['label']) for i, c in enumerate(candidates)],
                   resume={'step': 'grouped_discard_replace', 'ctx': ctx, 'request': request, 'card': entry['card']})
            return False
    from app.rules import attachments

    incoming = [e for e in request['cards'] if _selected(request, e).get('candidate', {}).get('outcome') == 'battlefield']
    if incoming:
        ctx['simultaneous_move'] = request
        return attachments.enter(plan, [{'card': e['card'], 'player': e['owner'], 'actor': request['actor'], 'tapped': False}
                                        for e in incoming], ctx)
    commit(plan, [], request)
    return True


def _selected(request: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    candidates = entry['candidates']
    return candidates[int(request['chosen'].get(entry['card'], 0))] if candidates else {}


def resume(plan: Plan, decision: Any, chosen: list[str]) -> None:
    r = decision.resume
    request = r['request']
    request['chosen'][r['card']] = int(chosen[0])
    if _choose(plan, r['ctx'], request):
        from app.rules.effects import continue_effects

        continue_effects(plan, r['ctx'])


def commit(plan: Plan, planned: list[Any], request: dict[str, Any]) -> None:
    from app.rules import history, replacements
    from app.rules.plan import Plan as Scratch

    actor = request['actor']
    incoming = [c.id for _, c, _ in planned]
    prepared = {}
    if planned:
        probe = Scratch(plan.state, actor, plan.info, plan.rng)
        probe.do({'type': 'move', 'card_ids': incoming, 'to': {'zone': 'battlefield'},
                  'controllers': {c.id: e['player'] for e, c, _ in planned}}, actor=actor)
        for entry, card, ep in planned:
            prepared[card.id] = replacements.after_entry(probe, card.id, entry['player'], x=entry.get('x'),
                extra_counters=replacements._extra(entry, probe), choices=ep.get('choices'), newcomers=incoming,
                bare=bool(entry.get('bare')), preview=True)
    routes = {}
    selected = []
    for entry in request['cards']:
        cid = entry['card']
        card = plan.state.cards.get(cid)
        if card is None or plan.oid(card) != entry['object'] or not card.zone.endswith(':hand'):
            continue
        picked = _selected(request, entry)
        candidate = replacements.Cand(**picked['candidate']) if picked else None
        outcome = candidate.outcome if candidate is not None else 'graveyard'
        if outcome == 'battlefield' and cid not in incoming:
            continue
        routes[cid] = {'player': card.owner, 'zone': outcome.split(':')[0]}
        selected.append((cid, candidate, picked.get('madness')))
    if routes:
        # All hand choices remain private until everyone has committed. This
        # reveal also covers replacement destinations that stay hidden.
        plan.do({'type': 'reveal', 'card_ids': list(routes)}, actor=actor)
        history.note_discards(plan, [cid for cid, c, _ in selected if c is not None])
        payload: dict[str, Any] = {'type': 'move', 'card_ids': list(routes), 'to': {'zone': 'graveyard'}, 'routes': routes}
        tapped = [c.id for _, c, ep in planned if ep.get('tapped')]
        if tapped:
            payload['tapped_ids'] = tapped
        plan.do(payload, actor=actor)
    for entry, card, ep in planned:
        replacements._after_move(plan, entry, card.id, ep, incoming, prepared=prepared[card.id])
    for cid, candidate, madness in selected:
        if candidate is not None:
            replacements._record_link(plan, cid, candidate)
            if candidate.counter:
                replacements.mark_exiled_counters(plan, [cid], candidate.counter, actor=actor)
            if candidate.rider is not None:
                replacements.run_rider(plan, candidate.rider)
            if candidate.outcome == 'library:shuffle':
                plan.do({'type': 'shuffle', 'player': plan.state.cards[cid].owner, 'zone': 'library'}, actor=actor)
        if madness:
            replacements._discard_into_exile(plan, cid, madness, actor, already_moved=True)


RESUME = {'grouped_discard_replace': resume}


def begin_cards(plan: Plan, ctx: dict[str, Any], card_ids: list[str]) -> bool:
    """A mandatory effect discards these exact hand objects as one prepared event."""
    from app.rules import prohibitions, replacements

    request: dict[str, Any] = {'kind': 'discard_group', 'actor': ctx['controller'], 'cards': [], 'chosen': {}}
    for cid in dict.fromkeys(card_ids):
        card = plan.state.cards.get(cid)
        if card is None or not card.zone.endswith(':hand') or prohibitions.cant_cause_discard(plan, card.owner, ctx['controller']) is not None:
            continue
        candidates: dict[str, dict[str, Any]] = {c.sig: {'candidate': c._asdict()} for c in replacements.zone_candidates(plan, card)}
        if request['actor'] != card.owner and any(d.get('replacement') == 'discard_battlefield'
                for d in replacements._definitions(plan, card).values()):
            candidate = replacements.Cand(card.name, 'battlefield')
            candidates[candidate.sig] = {'candidate': candidate._asdict()}
        if (madness := replacements._madness_cost(plan, card)) is not None:
            candidate = replacements.Cand('Madness', 'exile')
            candidates['madness'] = {'candidate': candidate._asdict(), 'madness': madness}
        request['cards'].append({'card': cid, 'object': plan.oid(card), 'owner': card.owner, 'candidates': list(candidates.values())})
    return _choose(plan, ctx, request)

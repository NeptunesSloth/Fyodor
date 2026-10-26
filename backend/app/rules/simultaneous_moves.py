"""CR 608.2b, 609.3, 614.12: prepare mixed zone changes, then commit one event.

Entry choices and counter replacement plans use the table before the outgoing
permanent leaves. The recorded Move carries each prepared route, so tracking
captures the outgoing and incoming objects in one zone-change batch.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.rules.plan import Plan


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import selectors

    body = body.strip()
    if body != ("Choose target artifact a player controls and target artifact card in that player's graveyard. "
                "If both targets are still legal as this ability resolves, that player simultaneously sacrifices "
                "the artifact and returns the artifact card to the battlefield."):
        return None
    graveyard = selectors.parse("artifact card in that player's graveyard")
    assert graveyard is not None
    return ([{'do': 'simultaneous_sacrifice_return', 'out': 'target:0', 'in': 'target:1'}],
            [{'what': 'artifact', 'min': 1, 'max': 1}, {'what': graveyard.key(), 'min': 1, 'max': 1, 'of': 0}], False)


def exchange(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, prohibitions, replacements
    from app.rules.plan import decide

    outgoing, incoming = effects._cards(plan, ctx, e['out']), effects._cards(plan, ctx, e['in'])
    # This printed restriction goes beyond ordinary partial target resolution.
    if len(outgoing) != 1 or len(incoming) != 1:
        return True
    card = plan.state.cards[outgoing[0]]
    request: dict[str, Any] = {'card': card.id, 'oid': plan.oid(card), 'player': card.controller,
                               'actor': ctx['controller'], 'incoming': incoming[0]}
    if (prohibitions.sacrifice_forbidden(plan, card) or
            prohibitions.cant_cause_sacrifice(plan, card.controller, ctx['controller'])):
        request['skip'] = True
    else:
        cands = replacements.zone_candidates(plan, card, 'graveyard')
        distinct = {c.sig: c for c in cands}
        if len(distinct) > 1:
            decide(plan, player=card.controller, kind='choose_one',
                   prompt=f'{card.name}: which graveyard replacement applies first? (616.1)',
                   options=[DecisionOption(id=str(i), label=c.label) for i, c in enumerate(distinct.values())],
                   resume={'step': 'simultaneous_replacement', 'ctx': ctx, 'request': request,
                           'cands': [c._asdict() for c in distinct.values()]})
            return False
        if cands:
            request['candidate'] = cands[0]._asdict()
    return _enter(plan, ctx, request)


def _enter(plan: Plan, ctx: dict[str, Any], request: dict[str, Any]) -> bool:
    from app.rules import attachments

    ctx['simultaneous_move'] = request
    return attachments.enter(plan, [{'card': request['incoming'], 'player': request['player'],
                                      'actor': request['actor'], 'tapped': False}], ctx)


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    r = d.resume
    request = {**r['request'], 'candidate': r['cands'][int(chosen[0])]}
    if _enter(plan, r['ctx'], request):
        continue_effects(plan, r['ctx'])


def commit(plan: Plan, planned: list[Any], request: dict[str, Any]) -> None:
    if request.get('kind') == 'discard_group':
        from app.rules import grouped_discard

        grouped_discard.commit(plan, planned, request)
        return
    from app.rules import replacements
    from app.rules.plan import Plan as Scratch
    from app.rules.triggers import sacrificing

    actor = request['actor']
    incoming = [c.id for _, c, _ in planned]
    routes = {c.id: {'player': e['player'], 'zone': 'battlefield'} for e, c, _ in planned}
    outgoing = plan.state.cards.get(request['card'])
    sacrifice = outgoing is not None and outgoing.zone.endswith(':battlefield') and plan.oid(outgoing) == request['oid'] and not request.get('skip')
    cand = replacements.Cand(**request['candidate']) if request.get('candidate') else None
    outcome = cand.outcome if cand is not None else 'graveyard'
    if sacrifice and outgoing is not None:
        routes[outgoing.id] = {'player': outgoing.owner, 'zone': outcome.split(':')[0]}
    if not routes:
        return
    # A scratch entry supplies the exact counter plan with the outgoing static
    # effects and permanents still present. No scratch action reaches the game.
    forms = {c.id: e['entry_characteristics'] for e, c, _ in planned if e.get('entry_characteristics')}
    prepared: dict[str, tuple[Any, Any] | None] = {}
    if planned:
        probe = Scratch(plan.state, actor, plan.info, plan.rng)
        probe.do({'type': 'move', 'card_ids': incoming, 'to': {'player': planned[0][0]['player'], 'zone': 'battlefield'},
                  'controllers': {c.id: e['player'] for e, c, _ in planned},
                  **({'entry_characteristics': forms} if forms else {})}, actor=actor)
        for entry, card, ep in planned:
            prepared[card.id] = replacements.after_entry(probe, card.id, entry['player'], x=entry.get('x'),
                extra_counters=replacements._extra(entry, probe), choices=ep.get('choices'), newcomers=incoming,
                bare=bool(entry.get('bare')), preview=True)
    if sacrifice and outgoing is not None:
        sacrificing(plan, [outgoing.id])
        if cand is not None and cand.used:
            plan.rules.exile_if_graveyard = [o for o in plan.rules.exile_if_graveyard if o != request['oid']]
        plan.rules.exile_if_leaves = [o for o in plan.rules.exile_if_leaves if o != request['oid']]
    payload: dict[str, Any] = {'type': 'move', 'card_ids': list(routes), 'to': {'zone': 'battlefield'}, 'routes': routes}
    if forms:
        payload['entry_characteristics'] = forms
    tapped = [c.id for _, c, ep in planned if ep.get('tapped')]
    if tapped:
        payload['tapped_ids'] = tapped
    back = [c.id for e, c, _ in planned if e.get('transformed') or e.get('modal_back')]
    if back:
        payload['back_ids'] = back
    if flipped := [c.id for e, c, _ in planned if e.get('flipped')]:  # (-- flip (wave 110I) -- 710: enters flipped)
        payload['flipped_ids'] = flipped
    if ':' in outcome:
        payload['position'] = 'bottom' if outcome.endswith(':bottom') else 'top'
    plan.do(payload, actor=actor)
    for entry, card, ep in planned:
        replacements._after_move(plan, entry, card.id, ep, incoming, prepared=prepared[card.id])
    from app.rules import (
        wave110e_once,  # -- one-shot entry counters (wave 110E) -- spent on this entry path too
    )

    wave110e_once.spend(plan, incoming)
    if sacrifice and outgoing is not None and cand is not None:
        replacements._record_link(plan, outgoing.id, cand)
        if cand.counter:
            replacements.mark_exiled_counters(plan, [outgoing.id], cand.counter, actor=actor)
        if cand.rider is not None:
            replacements.run_rider(plan, cand.rider)
        if outcome == 'library:shuffle':
            plan.do({'type': 'shuffle', 'player': outgoing.owner, 'zone': 'library'}, actor=outgoing.owner)


PRIMITIVES = {'simultaneous_sacrifice_return': exchange}
RESUME = {'simultaneous_replacement': resume}

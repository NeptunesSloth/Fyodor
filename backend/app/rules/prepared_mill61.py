"""Prepare all mill replacement routes before committing outcomes and continuing."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan
Context = dict[str, Any]


def run(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.game.rules_state import snapshot
    from app.game.state import zone_key
    from app.rules import context, effects, replace, replacements, sized_damage
    players = effects._players(plan, ctx, e['who'])
    each = {p: effects._amount(plan, {**ctx, 'recipient': p}, e['n']) for p in players} if sized_damage.has_per_player(e['n']) else None
    want = 0 if each is not None else effects._amount(plan, ctx, e['n'])
    wants = []
    for pid in players:
        if each is not None:
            want = each[pid]
        if e.get('half'):
            size = len(plan.state.zones.get(zone_key(pid, 'library'), []))
            want = (size + 1) // 2 if e['half'] == 'up' else size // 2
        wants.append((pid, want))
    counts = replace.mill_counts(plan, wants, then=replace.rerun_then(ctx, e), ctx=ctx)
    if counts is None:
        return False
    request: dict[str, Any] = {'cards': [], 'counts': [], 'choices': {}, 'before61': [], 'effect61': e,
                               'complete61': bool(counts) and all(n > 0 and len(plan.state.zones.get(zone_key(p, 'library'), [])) >= n for p, n in counts)}
    for pid, count in counts:
        selected = plan.state.zones.get(zone_key(pid, 'library'), [])[:count]
        request['counts'].append([pid, len(selected)])
        for cid in selected:
            ref = context.ref_of(plan, cid)
            if ref is not None:
                request['before61'].append(ref.model_copy(update={'snapshot': snapshot(plan.state, cid)}).model_dump(mode='json'))
            cands = {c.sig: c._asdict() for c in replacements.zone_candidates(plan, plan.state.cards[cid])}
            request['cards'].append({'id': cid, 'mill_player61': pid, 'cands': list(cands.values())})
    return _routes(plan, ctx, request)


def _routes(plan: Plan, ctx: Context, request: dict[str, Any]) -> bool:
    from app.game.errors import ActionError
    from app.game.rules_state import DecisionOption, ObjectRef
    from app.game.state import zone_key
    from app.rules import context, effects, mill_pair_repeat, replace
    from app.rules.plan import decide

    # No replacement choice grants priority. If an imported/admin-mutated state
    # nevertheless changed a selected object, never mill its new incarnation.
    for raw in request['before61']:
        ref = ObjectRef.model_validate(raw)
        card = plan.state.cards.get(ref.card)
        if card is None or plan.oid(card) != ref.object_id or card.zone != ref.zone:
            raise ActionError('A selected library object changed before the mill replacements finished')
    for row in request['cards']:
        cid, cands = row['id'], row['cands']
        if len(cands) > 1 and cid not in request['choices']:
            decide(plan, player=plan.state.cards[cid].owner, kind='choose_one',
                   prompt=f"{plan.state.cards[cid].name}: which graveyard replacement applies first? (616.1)",
                   options=[DecisionOption(id=str(i), label=c['label'] + ': ' + c['outcome']) for i, c in enumerate(cands)],
                   resume={'step': 'prepared_mill61', 'ctx': ctx, 'request': request, 'card': cid})
            return False
    start = plan.rules.batch
    # Native prepared-route commit moves selected cards before self-shuffles.
    # Per-player child contexts preserve the old generic mill's actor and keep
    # the loop-only mill_pair_batch receipt out of this resolution context.
    for pid, count in request['counts']:
        child = {'cards': [row for row in request['cards'] if row['mill_player61'] == pid],
                 'counts': [[pid, count]], 'choices': request['choices']}
        mill_pair_repeat._commit(plan, {**ctx, 'controller': pid}, child)
    replace._one_batch(plan, start)
    before = [ObjectRef.model_validate(ref) for ref in request['before61']]
    e = request['effect61']
    effects._moved(plan, ctx, e, before)
    if e.get('did'):
        context.bind_payment(ctx, e['did'], request['complete61'])
    if e.get('look'):
        # Preserve the established generic graveyard-only look default.
        pid = effects._players(plan, ctx, e['who'])[0]
        gone = {ref.card for ref in before}
        grave = plan.state.zones.get(zone_key(pid, 'graveyard'), [])
        ctx['looked'] = [cid for cid in grave if cid in gone]
        ctx['looked_zone'], ctx['looked_owner'], ctx['found'] = 'graveyard', pid, None
    return True


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects
    r = d.resume
    r['request']['choices'][r['card']] = int(chosen[0])
    if _routes(plan, r['ctx'], r['request']):
        effects.continue_effects(plan, r['ctx'])


RESUME = {'prepared_mill61': resume}

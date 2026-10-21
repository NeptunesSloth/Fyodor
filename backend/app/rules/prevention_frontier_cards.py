"""Exact shared-budget prevention and redirection recipes using native costs and targets."""
from __future__ import annotations

from dataclasses import replace as changed
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan
    from app.rules.replace import Candidate

STEP = 'prevention_frontier_card'
SOURCE = 'prevention_frontier_source'
COVER = ('If a creature would deal combat damage to you and/or one or more creatures you control, prevent X of that damage, '
         'where X is the number of age counters on this enchantment.')


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    cases = {
        'The next 2 damage that a source of your choice would deal to you and/or permanents you control this turn is dealt to any target instead.':
            ('source', 2, 'redirect', 'you_perms'),
        'The next X damage that a source of your choice would deal to you and/or creatures you control this turn is dealt to any target instead.':
            ('source', {'x': 1}, 'redirect', 'you_creatures'),
        'Prevent the next X damage that would be dealt to you and/or permanents you control this turn. If damage is prevented this way, ~ deals that much damage to any target.':
            ('all', {'x': 1}, 'prevent', 'you_perms'),
        'Prevent the next 3 damage that a source of your choice would deal to you and/or permanents you control this turn. If damage is prevented this way, ~ deals that much damage to any target.':
            ('source', 3, 'prevent', 'you_perms'),
    }
    found = cases.get(body)
    if found is None:
        return None
    source, limit, mode, to = found
    return [{'do': STEP, 'source': source, 'limit': limit, 'mode': mode, 'to': to}], 'any', False


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    if ability.kind != 'static' or ability.text != COVER:
        return None
    return _cover_definition()


def _cover_definition() -> dict[str, Any]:
    from app.rules import selectors

    return {'kind': 'static', 'static': 'replace', 'event': 'damage',
            'match': {'combat': True, 'source': {'types': ['Creature']},
                      'to': {'players': 'you', 'objects': {'sel': selectors.Selector(types=('Creature',), controller='you').key()}}},
            'op': {'do': 'finite_prevention', 'limit': 0, 'allocate': True, 'prevention': True,
                   'budget_scope': 'source_batch', 'frontier_age': True, 'joint_prevention': True}, 'effects': []}


def supported_static(value: dict[str, Any]) -> bool:
    return value == _cover_definition()


def bind_candidates(plan: Plan, candidates: list[Candidate]) -> list[Candidate]:
    out = []
    for candidate in candidates:
        if candidate.op.get('frontier_age'):
            source = plan.state.cards.get(candidate.source_card or '')
            if source is None or not source.zone.endswith(':battlefield') or plan.oid(source) != candidate.source_oid:
                raise ValueError('The exact static source incarnation is no longer on the battlefield')
            operation = {key: value for key, value in candidate.op.items() if key != 'frontier_age'}
            candidate = changed(candidate, op={**operation, 'limit': source.counters.get('age', 0)})
        out.append(candidate)
    return out


def _record(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], oids: list[str] | None, label: str) -> None:
    from app.rules import effects, prevention_outcomes, replace, source_shields

    n = effects._amount(plan, ctx, e['limit'])
    if n <= 0:
        return
    recipient = source_shields._recipient(plan, ctx, {'to': e['to']})
    if recipient is None:
        return
    if e['mode'] == 'redirect':
        destination = source_shields._destination(plan, ctx, 'target')
        if destination is None:
            return
        operation = {'do': 'redirect', **destination, 'limit': n, 'allocate': True, 'joint_prevention': True}
    else:
        rider = prevention_outcomes._rider(ctx, [{'do': prevention_outcomes.STEP, 'mode': 'bound_damage', 'who': 'target'}])
        operation = {'do': 'finite_prevention', 'prevention': True, 'limit': n, 'allocate': True, 'rider': rider, 'joint_prevention': True}
    replace.add_record(plan, event='damage', match={'to': recipient, **({'source': {'oids': oids}} if oids is not None else {})},
                       op=operation, controller=ctx['controller'], source=ctx.get('source_object'),
                       source_card=ctx.get('source_card'), label=ctx.get('name') or 'a finite damage effect')
    if label:
        plan.note(f"{plan.name(ctx['controller'])} chose {label} for the next {n} damage", actor=ctx['controller'])


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import effects, source_shields
    from app.rules.plan import decide

    if effects._amount(plan, ctx, e['limit']) <= 0:
        return True
    if e['source'] == 'all':
        _record(plan, ctx, e, None, '')
        return True
    options = source_shields.choosable(plan, {})
    if not options:
        return True
    if len(options) == 1:
        _record(plan, ctx, e, options[0][1], options[0][0])
        return True
    decide(plan, player=ctx['controller'], kind='choose_one', prompt=f"{ctx.get('name', 'Damage effect')}: choose a source (609.7a)",
           options=[DecisionOption(id=f's{i}', label=label[:120], card_id=shown) for i, (label, _, shown) in enumerate(options)],
           resume={'step': SOURCE, 'ctx': ctx, 'e': e,
                   'map': {f's{i}': [oids, label] for i, (label, oids, _) in enumerate(options)}})
    return False


def resume(plan: Plan, decision: Any, chosen: list[str]) -> None:
    from app.rules import effects

    oids, label = decision.resume['map'][chosen[0]]
    _record(plan, decision.resume['ctx'], decision.resume['e'], oids, label)
    effects.continue_effects(plan, decision.resume['ctx'])


PRIMITIVES = {STEP: run}
RESUME = {SOURCE: resume}

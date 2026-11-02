"""Prospective Aura-token hosts: choices precede every token's creation (303.4f/g)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

HOST = '__aura_host__'
SKIP = '__aura_skip__'
COPY = '__entry_copy_recipe__'
ENTRY = '__entry_copy_effects__'


def probe(plan: Plan, player: str, spec: dict[str, Any]) -> Any:
    from app.rules import copying, replacements

    if spec.get('_copy') is not None:
        ch = copying.characteristics(copying.CopyRecipe.model_validate(spec['_copy']), plan.info)
        spec = {'name': ch.name, 'power': ch.power, 'toughness': ch.toughness, 'colors': sorted(ch.colors),
                'type_line': copying.type_line(ch), 'text': ch.oracle_text, '_embalmed': bool(spec.get('_embalmed'))}
    return replacements._token_probe(player, spec).model_copy(update={'embalmed': bool(spec.get('_embalmed'))})


def prospect(plan: Plan, incoming: Any) -> Any:
    """-- big boards (perf) -- the token as it would exist on the battlefield (``plan.ch`` of the probe: the whole field is worked out
    with it on it, layer_dependency_graph.solve_field), in a read pass (Plan.reading: the statics table, each permanent's printed
    values and the effects on each object are read once, not once per permanent). Only reads the table."""
    with plan.reading():
        return plan.ch(incoming)


def effective(ev: dict[str, Any], row: dict[str, str]) -> dict[str, Any]:
    import json

    return {**ev['token'], '_embalmed': bool(ev.get('embalmed')),
            **({'_copy': json.loads(row[COPY])} if row.get(COPY) else {})}


def copy_choices(plan: Plan, evs: list[dict[str, Any]], answers: dict[str, str]) -> tuple[list[list[dict[str, str]]], dict[str, Any] | None]:
    import json

    from app.game.errors import ActionError
    from app.rules import copying, scripts

    rows: list[list[dict[str, str]]] = []
    n = 0
    for ev in evs:
        row: list[dict[str, str]] = []
        d: dict[str, Any] | None = None
        for k in range(ev['count']):
            if k and d is None:
                # -- big boards (perf) -- every token of the event is the same prospective object (``effective(ev, {})``) and the token before
                # it had no "enter as a copy" ability and changed nothing: this one has none either. (Each look derives the whole
                # battlefield as it would be with the token on it: 614.12; Adrix and Nev's doubled tokens looked twice.)
                row.append({})
                continue
            incoming = probe(plan, ev['player'], effective(ev, {}))
            d = next((d for d in scripts.definitions(prospect(plan, incoming)).values()
                      if d.get('replacement') == 'enter_as_copy'), None)
            got: dict[str, str] = {}
            if d is not None:
                options = copying.entry_options(plan, ev['player'], d['what'])
                key = f'enter:{n + k}:copy_source'
                answer = answers.get(key)
                if options and answer is None:
                    return rows, {'key': key, 'player': ev['player'], 'prompt': 'Choose a permanent for the token to enter as a copy of',
                                  'options': options, 'source': ev.get('source')}
                if options and answer not in {o.id for o in options}:
                    raise ActionError('That cannot be copied as the token enters')
                if answer not in (None, '', copying.NONE):
                    source = plan.state.cards[answer]
                    excepts = [copying.CopyExcept.model_validate(x) for x in d.get('excepts') or []]
                    excepts = [copying.keep_colors(x, plan.ch(incoming).colors) for x in excepts]
                    if d.get('embalmed_except') and ev.get('embalmed'):
                        excepts.append(copying.CopyExcept.model_validate(d['embalmed_except']))
                    if (grant := d.get('copy_if_lacks')) and not any(grant['keyword'] in a.keywords for a in plan.ch(source).abilities):
                        excepts.append(copying.CopyExcept(add_text=[grant['text']]))
                    recipe = copying.with_excepts(copying.recipe_of(plan, source), excepts)
                    got[COPY] = json.dumps(recipe.model_dump(mode='json'))
                    got[ENTRY] = json.dumps({'counters': d.get('enter_counters') or [], 'controller': source.controller,
                                             'tapped': bool(d.get('tapped')), 'duration': d.get('duration') or 'permanent'})
            row.append(got)
        rows.append(row)
        n += ev['count']
    return rows, None


def hosts(plan: Plan, evs: list[dict[str, Any]], rows: list[list[dict[str, str]]], answers: dict[str, str]) -> tuple[list[list[dict[str, str]]], dict[str, Any] | None]:
    from app.game.errors import ActionError
    from app.game.rules_state import DecisionOption, ObjectRef
    from app.rules import attachments, context, targets

    n = 0
    for index, ev in enumerate(evs):
        while len(rows[index]) < ev['count']:
            rows[index].append({})
        kind = None
        for k in range(ev['count']):
            if k and kind not in ('aura', 'equipment', 'fortification') and rows[index][k].get(COPY) == rows[index][k - 1].get(COPY):
                # -- big boards (perf) -- the same prospective object as the token before it (``effective`` reads only the copy recipe of
                # the row), which attaches to nothing and changed nothing: neither does this one (below, ``continue``)
                continue
            incoming = probe(plan, ev['player'], effective(ev, rows[index][k]))
            kind = attachments.attach_kind(prospect(plan, incoming))
            fixed = ev.get('attachment_ref')
            if fixed is not None and kind in ('aura', 'equipment', 'fortification'):
                ref = ObjectRef.model_validate(fixed)
                host = context._same(plan, ref)
                fixed_legal = host is not None and ref.card in attachments._hosts_on_entering(plan, incoming, ev['player'])
                if fixed_legal:
                    rows[index][k][HOST] = ref.card
                elif kind == 'aura':
                    rows[index][k][SKIP] = '1'
                continue
            if kind != 'aura':
                continue
            key = f'enter:{n + k}:aura_host'
            legal = attachments._hosts_on_entering(plan, incoming, ev['player'])
            if not legal:
                rows[index][k][SKIP] = '1'
            elif key in answers:
                if answers[key] not in legal:
                    raise ActionError('The Aura cannot enchant that object')
                rows[index][k][HOST] = answers[key]
            elif len(legal) == 1:
                rows[index][k][HOST] = legal[0]
            else:
                return rows, {'key': key, 'player': ev['player'], 'prompt': 'Choose what the Aura token enchants',
                              'options': [DecisionOption(id=h, label=targets.label(plan, h), card_id=h if h in plan.state.cards else None) for h in legal],
                              'source': ev.get('source')}
        n += ev['count']
    return rows, None

"""Bind compound and chosen-source protection qualities during resolution."""
from __future__ import annotations

from typing import Any

from app.rules.plan import Plan

OPPONENT_CREATURES = 'Protection from creatures your opponents control'
SOURCE_COLOR = 'Protection from the source chosen color'
LAND_COLORS = (('Plains', 'white'), ('Island', 'blue'), ('Swamp', 'black'), ('Mountain', 'red'), ('Forest', 'green'))


def abilities(plan: Plan, ctx: dict[str, Any], lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        if line == SOURCE_COLOR:
            from app.rules import protection

            source = plan.state.cards.get(ctx.get('source_card') or '')
            snap = plan.rules.lki.get(ctx.get('source_object') or '')
            choices = (source.choices if source is not None and plan.oid(source) == ctx.get('source_object')
                       else snap.choices if snap is not None else {})
            color = choices.get('Chosen color', '').lower()
            if color in protection.COLORS:
                out.append(f'Protection from {color}')
        else:
            out.append(line)
    return out


def bind_definition(d: dict[str, Any], ch: Any) -> dict[str, Any]:
    from app.rules import chosen

    if d.get('kind') not in ('activated', 'triggered') or chosen._enters_choices(ch).count('color') != 1:
        return d
    effects = d.get('effects') or []
    if any(e.get('do') == 'choose_value' and e.get('what') == 'color' for e in effects):
        return d
    return {**d, 'effects': [{**e, 'abilities': [SOURCE_COLOR if a == 'Protection from the chosen color' else a
                                               for a in e['abilities']], 'source_choice_color': True}
                            if e.get('do') == 'grant' and 'Protection from the chosen color' in e.get('abilities', []) else e
                            for e in effects]}


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import selectors

    if body == 'Target creature you control gains protection from creatures your opponents control until end of turn. Untap it.':
        sel = selectors.parse('creature you control')
        assert sel is not None
        return ([{'do': 'grant', 'who': 'target', 'abilities': [OPPONENT_CREATURES]},
                 {'do': 'untap', 'who': 'target'}], sel.key(), False)
    if body == 'Target permanent you control gains protection from instant spells and from sorcery spells until end of turn.':
        sel = selectors.parse('permanent you control')
        assert sel is not None
        return ([{'do': 'grant', 'who': 'target', 'abilities': ['Protection from instant spells and from sorcery spells']}], sel.key(), False)
    if body == 'Target creature gains protection from the chosen color until end of turn.':
        return ([{'do': 'grant', 'who': 'target', 'abilities': [SOURCE_COLOR], 'source_choice_color': True}], 'creature', False)
    expected = ('Until end of turn, creatures you control gain protection from white if you control a Plains, '
                'from blue if you control an Island, from black if you control a Swamp, '
                'from red if you control a Mountain, and from green if you control a Forest.')
    if body == expected:
        return ([{'do': 'land_type_protection'}], None, False)
    return None


def land_types(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, selectors

    subtypes = {t for c in plan.state.cards.values() if c.zone.endswith(':battlefield')
                and c.controller == ctx['controller'] and plan.in_game(c) and 'Land' in plan.ch(c).types
                for t in plan.ch(c).subtypes}
    sel = selectors.parse('creatures you control')
    assert sel is not None
    return effects.grant(plan, ctx, {'do': 'grant', 'who': sel.key(),
                                     'abilities': [f'Protection from {color}' for subtype, color in LAND_COLORS if subtype in subtypes]})


PRIMITIVES = {'land_type_protection': land_types}

"""Cross-target current qualities for native, all-or-nothing permanent exchanges."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any, Literal, TypedDict

from app.rules import selectors
from app.rules.plan import Plan


class RelativeQuality(TypedDict, total=False):
    kind: Literal['mv', 'power', 'types']
    types: list[str]


_SAW = 'shares_bound_card_types:'


def _group(phrase: str) -> dict[str, Any]:
    sel = selectors.parse(phrase)
    assert sel is not None
    return {'what': sel.key(), 'min': 1, 'max': 1}


def parse(phrase: str) -> tuple[list[dict[str, Any]], Any] | None:
    patterns: dict[str, tuple[str, str, RelativeQuality, bool]] = {
        'target nonland permanent you control and target nonland permanent an opponent controls with equal or lesser mana value':
            ('nonland permanent you control', 'nonland permanent an opponent controls', {'kind': 'mv'}, False),
        'target nonland permanent you control and target permanent an opponent controls that shares a card type with it':
            ('nonland permanent you control', 'permanent an opponent controls', {'kind': 'types'}, False),
        'target artifact or creature and another target permanent that shares one of those types with it':
            ('artifact or creature', 'permanent', {'kind': 'types', 'types': ['Artifact', 'Creature']}, True),
        "target creature you control and target creature with power less than or equal to that creature's power an opponent controls":
            ('creature you control', 'creature an opponent controls', {'kind': 'power'}, False),
    }
    if phrase in patterns:
        first, second, quality, distinct = patterns[phrase]
        group = {**_group(second), 'of': 0, 'relative_quality': quality}
        if distinct:
            group['distinct_from'] = [0]
        return [{'do': 'exchange_control', 'who': 'target', 'with': 'target:1'}], [_group(first), group]
    if phrase in ('~ and target permanent you neither own nor control', 'this enchantment and target permanent you neither own nor control'):
        sel = selectors.Selector(owner='opponent', controller='opponent')
        return [{'do': 'exchange_control', 'who': 'self', 'with': 'target'}], {'what': sel.key(), 'min': 1, 'max': 1}
    return None


def _facts(plan: Plan, refs: list[Any]) -> Any:
    from app.rules import targets

    if len(refs) != 1:
        return None
    ref = refs[0] if hasattr(refs[0], 'id') else targets.ref(plan, refs[0])
    fact = targets._facts(plan, ref)
    return None if fact is None else fact[0]


def bind(plan: Plan, spec: dict[str, Any], groups: list[list[Any]]) -> str:
    if spec['relative_quality']['kind'] == 'hostctl110j':  # -- wave 110J -- "another permanent with the same controller" as the permanent the Aura is attached to
        host = _host110j(plan, groups[spec['of']] if spec['of'] < len(groups) else [])
        sel = selectors.from_key(spec['what'])
        return sel.key() if host is None else replace(sel, controller=f'player:{host.controller}', extras=(*sel.extras, f'not_oid:{plan.oid(host)}')).key()
    sel = selectors.from_key(spec['what'])
    at = spec['of']
    fact = _facts(plan, groups[at]) if at < len(groups) else None
    quality = spec['relative_quality']
    if fact is None:
        return replace(sel, extras=(*sel.extras, _SAW)).key()  # A known empty allowed set, never unconstrained.
    if quality['kind'] == 'types':
        common = fact.types & set(quality.get('types') or selectors.CARD_TYPES.values())
        return replace(sel, extras=(*sel.extras, _SAW + ','.join(sorted(common)))).key()
    value = fact.mana_value if quality['kind'] == 'mv' else fact.pt[0] if fact.pt is not None else 0
    return replace(sel, compare=(*sel.compare, (quality['kind'], '<=', value))).key()


def _matches(plan: Plan, spec: dict[str, Any], first: str, second: str, facts: dict[str, Any]) -> bool:
    if spec['relative_quality']['kind'] == 'hostctl110j':
        host = plan.state.cards.get(plan.state.cards[first].attached_to or '')
        return host is not None and host.id != second and plan.state.cards[second].controller == host.controller
    a, b = facts[first], facts[second]
    kind = spec['relative_quality']['kind']
    if kind == 'types':
        return bool(a.types & b.types & set(spec['relative_quality'].get('types') or selectors.CARD_TYPES.values()))
    if kind == 'mv':
        return b.mana_value <= a.mana_value
    return (b.pt[0] if b.pt is not None else 0) <= (a.pt[0] if a.pt is not None else 0)


def _host110j(plan: Plan, refs: list[Any]) -> Any:
    from app.rules import targets

    if len(refs) != 1:
        return None
    card = plan.state.cards.get((refs[0] if hasattr(refs[0], 'id') else targets.ref(plan, refs[0])).id)
    return plan.state.cards.get(card.attached_to or '') if card is not None else None


def _pairs(plan: Plan, spec: dict[str, Any], first: list[str], second: list[str]) -> dict[str, list[str]]:
    facts = {cid: plan.ch(plan.state.cards[cid]) for cid in set(first) | set(second)}
    distinct = spec['of'] in (spec.get('distinct_from') or [])
    return {a: [b for b in second if (not distinct or a != b) and _matches(plan, spec, a, b, facts)] for a in first}


def room(plan: Plan, spec: dict[str, Any], specs: list[dict[str, Any]], legal: Callable[[str], list[str]]) -> int:
    pairs = _pairs(plan, spec, legal(specs[spec['of']]['what']), legal(spec['what']))
    return max((len(xs) for xs in pairs.values()), default=0)


def viable_first(plan: Plan, specs: list[dict[str, Any]], at: int, options: list[str],
                 legal: Callable[[str], list[str]]) -> list[str]:
    """Only the new two-singleton dependency: every first pick has a legal completion."""
    for later in specs[at + 1:]:
        if later.get('relative_quality') and later.get('of') == at and later.get('min') == later.get('max') == 1:
            pairs = _pairs(plan, later, options, legal(later['what']))
            options = [cid for cid in options if pairs[cid]]
    return options

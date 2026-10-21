"""Declaration-wide one-attacker requirements retain independent source multiplicity."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics
    from app.rules.plan import Plan

PREFIX = 'attack_at_least_one68:'


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import scripts, selectors, statics

    text = scripts.self_text(ability.text, ch.name)
    if text == 'Each opponent must attack with at least one creature each combat if able.':
        mode = 'any'
    elif text == 'Each opponent must attack you or a planeswalker you control with at least one creature each combat if able.':
        mode = 'controller'
    else:
        return None
    return statics._definition(selectors.Selector(types=('Creature',), controller='opponent').key(), None, [],
                               rules=[PREFIX + '@src:@you:' + mode])


def groups(plan: Plan, eligible: set[str]) -> list[tuple[int, frozenset[str]]]:
    """Compress identical destination sets; copies still contribute separate weight."""
    from collections import Counter

    from app.rules import attack_requirements

    counts: dict[str, int] = {}
    for cid in eligible:
        for rule, n in attack_requirements.counts(plan.ch(plan.state.cards[cid])).items():
            if rule.startswith(PREFIX):
                counts[rule] = max(n, counts.get(rule, 0))
    grouped: Counter[frozenset[str]] = Counter()
    for rule, n in counts.items():
        _, controller, mode = rule[len(PREFIX):].rsplit(':', 2)
        if mode == 'any':
            destinations = frozenset({'*'})
        else:
            destinations = frozenset({controller} | {c.id for c in plan.state.cards.values()
                if c.zone.endswith(':battlefield') and c.controller == controller and 'Planeswalker' in plan.ch(c).types})
        grouped[destinations] += n
    return [(n, places) for places, n in sorted(grouped.items(), key=lambda item: sorted(item[0]))]


def hit(groups: list[tuple[int, frozenset[str]]], place: str | None) -> int:
    if place is None:
        return 0
    return sum(1 << i for i, (_, places) in enumerate(groups) if '*' in places or place in places)


def value(groups: list[tuple[int, frozenset[str]]], mask: int) -> int:
    return sum(n for i, (n, _) in enumerate(groups) if mask & (1 << i))

"""Flagbearer target requirements apply only during casting and activation."""
from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics
    from app.rules.plan import Plan

TEXT = ('While an opponent is choosing targets as part of casting a spell they control or activating an ability they control, '
        'that player must choose at least one Flagbearer on the battlefield if able.')


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    return {'kind': 'static', 'static': 'flagbearer_requirement86'} if ability.text == TEXT else None


def current(plan: Plan, actor: str | None = None) -> set[str]:
    from app.rules import scripts

    actor = actor or plan.actor
    active = False
    flags: set[str] = set()
    for card in plan.state.cards.values():
        if not card.zone.endswith(':battlefield'):
            continue
        ch = plan.ch(card)
        if 'Flagbearer' in ch.subtypes:
            flags.add(card.id)
        if card.controller != actor and card.controller in plan.live() and any(
                d.get('static') == 'flagbearer_requirement86' for d in scripts.definitions(ch).values()):
            active = True
    return flags if active else set()


def single(plan: Plan, legal: list[str], *, actor: str | None = None) -> list[str]:
    forced = current(plan, actor).intersection(legal)
    return [t for t in legal if t in forced] if forced else legal


def enforce_groups(plan: Plan, action: Any, specs: list[dict[str, Any]], found: Any,
                   source: Characteristics | None, what: str, exclude: tuple[str, ...]) -> None:
    """601.2c: target counts/modes/X are fixed before target identities are chosen."""
    from app.game.errors import ActionError
    from app.rules import targets

    flags = current(plan)
    if not flags or flags.intersection(t for group in found.groups for t in group):
        return
    if len(specs) == 1 and specs[0].get("random"):
        return  # Native random selection already restricted its eligible pool before sampling.
    fixed = [len(group) for group in found.groups]
    dependencies = any(any(k in spec for k in ('of', 'object_of', 'controller_opponents_of', 'relative_quality')) for spec in specs)
    if not dependencies and not any(n and flags.intersection(targets.legal_targets(
            plan, spec['what'], plan.actor, source, action.card_id)) for n, spec in zip(fixed, specs, strict=True)):
        return

    def prefix_ok(spec: dict[str, Any], picked: list[str]) -> bool:
        if not targets.relation_ok(plan, spec, [targets.ref(plan, t) for t in picked]):
            return False
        if spec.get('same_graveyard') and len({plan.state.cards[t].owner for t in picked if t in plan.state.cards}) > 1:
            return False
        if spec.get('different') and not targets._different(plan, picked, spec['different']):
            return False
        if spec.get('total'):
            limit = int(action.x_value or 0) if spec['total'][1] == 'X' else spec['total'][1]
            if targets._total(plan, picked, spec['total'][0]) > limit:
                return False
        return True

    def subsets(options: list[str], n: int, spec: dict[str, Any]) -> Iterator[list[str]]:
        ordered = sorted(options, key=lambda t: (t not in flags, t))

        def extend(start: int, picked: list[str]) -> Iterator[list[str]]:
            left = n - len(picked)
            if not left:
                yield picked
                return
            available = [(i, t) for i, t in enumerate(ordered[start:], start) if prefix_ok(spec, [*picked, t])]
            if len(available) < left:
                return
            for i, t in available:
                yield from extend(i + 1, [*picked, t])
        yield from extend(0, [])

    def possible(flat: list[str], counts: list[int]) -> bool:
        try:
            choice = targets.choose_groups(plan, specs, plan.actor, source, action.card_id, flat, counts,
                                           [], action.x_value, what, exclude)
        except ActionError:
            return False
        if choice.ask is None:
            return bool(flags.intersection(t for group in choice.groups for t in group))
        if choice.ask[0] != 'group':
            # Division follows all target identities, and may choose a new valid positive division.
            return bool(flags.intersection(t for group in choice.groups for t in group)) and all(
                total is None or total >= len(group) for group, spec in zip(choice.groups, specs, strict=True)
                for total in [targets.divide_total(spec, targets.divide_x(plan, spec, plan.actor, action.card_id, None, None, action.x_value))])
        _, g, options, lo, hi = choice.ask
        n = fixed[g]
        if not lo <= n <= hi:
            return False
        for picked in subsets(options, n, specs[g]):
            if possible([t for group in choice.groups for t in group] + picked, [*choice.counts, n]):
                return True
        return False

    if possible([], []):
        raise ActionError('Choose at least one legal Flagbearer as a target')

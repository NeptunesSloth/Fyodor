"""Unimported producer-allocation prototype; no native engine admissions.

Facts are captured by a future reviewed production boundary, never reconstructed
from a source's current characteristics. This bounded solver accepts already
produced units and explicit selected filter options; it is not an AUTO planner.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.game.rules_state import ObjectRef
    from app.rules.plan import Plan

from app.rules.mana_requirement_rows import Requirement


class ProducerRequirement(StrEnum):
    CREATURE_PERMANENT = 'creature_permanent'
    BASIC_LAND = 'basic_land'
    TREASURE = 'treasure'


@dataclass(frozen=True)
class ProducerFact:
    tags: tuple[str, ...]
    zone: str | None


def capture(plan: Plan, source: ObjectRef) -> ProducerFact | None:
    """Inspect exact current/LKI source only; never follow its physical successor."""
    from app.rules import mana_units

    card = plan.state.cards.get(source.card)
    if card is not None and plan.oid(card) == source.object_id and card.zone == source.zone:
        return ProducerFact(tuple(mana_units.tags_of(plan.ch(card))), card.zone)
    snap = source.snapshot or plan.rules.lki.get(source.object_id)
    if (snap is None or snap.object_id != source.object_id or snap.card != source.card
            or snap.zone != source.zone):
        return None
    from app.rules.triggers import _snapshot_card

    return ProducerFact(tuple(mana_units.tags_of(_snapshot_card(plan, snap)[1])), snap.zone)


def eligible(fact: ProducerFact | None, requirement: ProducerRequirement | None) -> bool:
    if requirement is None:
        return True
    if fact is None or fact.zone is None or fact.zone.partition(':')[2] != 'battlefield':
        return False
    tags = set(fact.tags)
    if requirement is ProducerRequirement.CREATURE_PERMANENT:
        return 'Creature' in tags
    if requirement is ProducerRequirement.BASIC_LAND:
        return {'Basic', 'Land'} <= tags
    return 'Treasure' in tags


@dataclass(frozen=True)
class Unit:
    """Exact unit identity and captured producer; helpers are explicitly nonmana."""
    id: str
    sym: str
    producer: ProducerFact | None = None
    generic_allowed: bool = True
    snow: bool = False
    helper: bool = False


@dataclass(frozen=True)
class Row:
    requirement: Requirement
    producer: ProducerRequirement | None = None


def matches(unit: Unit, row: Row) -> bool:
    req = row.requirement
    if req.generic and not unit.generic_allowed:
        return False
    alternatives = req.helpers if unit.helper and req.helpers is not None else req.alternatives
    if unit.helper:
        # Nonmana helpers never establish snow or producer facts. They bypass
        # producer restrictions on MANA while retaining original helper colors.
        return 'S' not in alternatives and unit.sym in alternatives
    return (eligible(unit.producer, row.producer)
            and any(unit.snow if sym == 'S' else unit.sym == sym for sym in alternatives))


def _fixed_allocations(units: tuple[Unit, ...], rows: tuple[Row, ...]) -> tuple[tuple[str, ...], ...]:
    """All exact unit receipts, with memoized bounded-state matching.

    Restricted generic requirements are explicit rows; unrestricted filter rows
    remain distinct, so merging costs cannot erase the producer predicate.
    """
    if len({unit.id for unit in units}) != len(units):
        raise ValueError('Duplicate actual mana unit identity')

    @cache
    def visit(index: int, available: tuple[int, ...]) -> tuple[tuple[int, ...], ...]:
        if index == len(rows):
            return ((),)
        out: list[tuple[int, ...]] = []
        for i in available:
            if matches(units[i], rows[index]):
                rest = tuple(j for j in available if j != i)
                out.extend((i, *tail) for tail in visit(index + 1, rest))
        return tuple(out)

    return tuple(tuple(units[i].id for i in receipt)
                 for receipt in visit(0, tuple(range(len(units)))))


def allocations(units: tuple[Unit, ...], rows: tuple[Row, ...]) -> tuple[tuple[str, ...], ...]:
    """Expand numeric hybrid branches without losing producer or generic origin."""
    plans: list[tuple[Row, ...]] = [()]
    for row in rows:
        numeric = tuple(sym for sym in row.requirement.alternatives if sym.isdigit())
        colors = tuple(sym for sym in row.requirement.alternatives if not sym.isdigit())
        branches: list[tuple[Row, ...]] = []
        if colors:
            branches.append((Row(Requirement(colors, row.requirement.generic,
                                             row.requirement.helpers), row.producer),))
        branches.extend((Row(Requirement(('W', 'U', 'B', 'R', 'G', 'C'), generic=True),
                             row.producer),) * int(amount) for amount in numeric)
        plans = [(*plan, *branch) for plan in plans for branch in branches]
    return tuple(dict.fromkeys(receipt for plan in plans for receipt in _fixed_allocations(units, plan)))


@dataclass(frozen=True)
class FilterReceipt:
    inputs: tuple[str, ...]
    final: tuple[str, ...]


def filtered_allocations(units: tuple[Unit, ...], activation: tuple[Row, ...],
                         output: tuple[Unit, ...], final: tuple[Row, ...]) -> tuple[FilterReceipt, ...]:
    """Pay selected filter before producing output; output cannot fund itself.

    This isolated sequential witness intentionally does not infer independent
    trigger producers or activation availability from a serialized symbol list.
    """
    if {u.id for u in units} & {u.id for u in output}:
        raise ValueError('A new output cannot alias an existing unit')
    out: list[FilterReceipt] = []
    for paid in allocations(units, activation):
        remaining = tuple(u for u in units if u.id not in paid)
        for receipt in allocations((*remaining, *output), final):
            out.append(FilterReceipt(paid, receipt))
    return tuple(out)

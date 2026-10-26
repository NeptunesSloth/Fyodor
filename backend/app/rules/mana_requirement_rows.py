"""Internal allocation identities; actual mana symbols and cost origins stay distinct."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ProducerRequirement(StrEnum):
    CREATURE_PERMANENT = 'creature_permanent'
    BASIC_LAND = 'basic_land'
    TREASURE_PERMANENT = 'treasure_permanent'


@dataclass(frozen=True)
class ProducerFact:
    tags: tuple[str, ...]
    zone: str | None


@dataclass(frozen=True)
class OutputProducer:
    source_object: str
    producer: ProducerFact | None


def producer_allowed(fact: ProducerFact | None, requirement: ProducerRequirement | None) -> bool:
    if requirement is None:
        return True
    if fact is None or fact.zone is None or fact.zone.partition(':')[2] != 'battlefield':
        return False
    if requirement is ProducerRequirement.TREASURE_PERMANENT:
        return 'Treasure' in fact.tags
    return ('Creature' in fact.tags if requirement is ProducerRequirement.CREATURE_PERMANENT
            else {'Basic', 'Land'} <= set(fact.tags))


@dataclass(frozen=True)
class UnitClass:
    sym: str
    generic: bool = True
    snow: bool = False
    producer: ProducerFact | None = None


@dataclass(frozen=True)
class Requirement:
    alternatives: tuple[str, ...]
    generic: bool = False
    helpers: tuple[str, ...] | None = None
    producer: ProducerRequirement | None = None
    distinct: bool = False  # wave 110J: "no more than one mana of each color may be spent this way": the rows flagged so are paid with different colors


@dataclass(frozen=True)
class RequirementPlan:
    generic: int
    symbols: tuple[Requirement, ...]
    phyrexian: tuple[Requirement, ...] = ()


@dataclass(frozen=True)
class SpentClass:
    unit: UnitClass
    amount: int

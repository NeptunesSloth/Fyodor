"""Costs of activated abilities (the text before the colon), as data.

``parse_ability_cost("{2}, {T}, Sacrifice Mind Stone")`` → ``AbilityCost(mana="{2}", tap=True,
sacrifice_self=True)``. Anything the engine can't pay by itself is listed in ``unsupported``; the
ability is then refused with a clear message and can be done by hand.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_MANA_ONLY = re.compile(r"^(\{(?:[0-9WUBRGCX]|[WUBRG2]/[WUBRGP])\})+$")
_SAC_SELF = re.compile(r"^Sacrifice (this \w+|it|~|(?P<name>.+))$")
_LIFE = re.compile(r"^Pay (?P<n>\d+) life$")
_REMOVE = re.compile(
    r"^Remove (?P<n>a|an|one|two|three|\d+) (?P<kind>[\w+/\-]+) counters? from (this \w+|it|~|(?P<name>.+))$"
)
_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3}


@dataclass(frozen=True)
class AbilityCost:
    mana: str = ""  # mana symbols, e.g. "{2}{G}"
    tap: bool = False
    sacrifice_self: bool = False
    life: int = 0
    remove_counters: tuple[tuple[str, int], ...] = ()  # (kind, amount) from the source itself
    loyalty: int | None = None  # +N / −N / 0 for planeswalker abilities
    loyalty_x: bool = False  # −X: remove X loyalty counters, X chosen as it's activated (107.3k)
    unsupported: tuple[str, ...] = field(default_factory=tuple)


def parse_ability_cost(cost: str, *, card_name: str = "", loyalty: bool = False) -> AbilityCost:
    if loyalty:
        raw = cost.strip().replace("−", "-")
        if raw.upper() == "-X":
            return AbilityCost(loyalty_x=True)
        if raw.upper().lstrip("+-") == "X":
            return AbilityCost(unsupported=(cost,))
        return AbilityCost(loyalty=int(raw))
    mana = ""
    tap = sac = False
    life = 0
    counters: list[tuple[str, int]] = []
    unsupported: list[str] = []
    for part in (p.strip() for p in cost.split(",")):
        if not part:
            continue
        if part == "{T}":
            tap = True
        elif _MANA_ONLY.match(part):
            mana += part
        elif (m := _SAC_SELF.match(part)) and (not m.group("name") or m.group("name") == card_name):
            sac = True
        elif m := _LIFE.match(part):
            life += int(m.group("n"))
        elif (m := _REMOVE.match(part)) and (not m.group("name") or m.group("name") == card_name):
            n = m.group("n")
            counters.append((m.group("kind"), _WORDS.get(n, 0) or int(n)))
        else:
            unsupported.append(part)
    return AbilityCost(mana=mana, tap=tap, sacrifice_self=sac, life=life, remove_counters=tuple(counters),
                       unsupported=tuple(unsupported))

"""-- if you do (wave 6F) -- mana abilities that remove "any number" of the source's counters as their cost and add mana
for each counter removed this way: the storage lands ("{T}, Remove any number of storage counters from this land: Add
{C} for each storage counter removed this way." — Mage-Ring Network, Fountain of Cho, Saprazzan Cove, Mercadian Bazaar,
Rushwood Grove, Subterranean Hangar) and the Mana Batteries ("{T}, Remove any number of charge counters from this
artifact: Add {G}, then add an additional {G} for each charge counter removed this way.").

CR 2026-09-25: 107.1c — "any number" is any positive number or zero; the number is chosen as the cost is paid
(601.2h via 602.2b, 605.3a: a mana ability is activated and resolves at once, so the mana it adds is the number just
removed); 118.3 — no more counters than the source has can be removed (122.8: a counter that isn't there can't be
removed). A cost isn't an effect: the removal is the cost (no replacement applies to it).

The engine reads such an ability as a counted mana ability (``ManaAbility.count = "removed:<kind>:<base>"``): each
number the player could choose is one option of the "Which mana should … add?" choice (base + n symbols for n counters,
n from 1 for the storage lands — removing none adds nothing — and from 0 for the Batteries), and ``casting.produce``
removes the n counters before the mana is added. The auto-payer never uses it (the number is the player's choice: it's
activated by hand, like the other mana abilities whose cost is a choice).
"""

from __future__ import annotations

import re

PREFIX = "removed:"
_COST = re.compile(r"^Remove any number of (?P<kind>[a-z]+) counters from (?:this \w+|~|it)$")
_EACH = re.compile(r"^Add \{(?P<sym>[WUBRGC])\} for each (?P<kind>[a-z]+) counter removed this way$")
_BATTERY = re.compile(r"^Add \{(?P<sym>[WUBRGC])\}, then add an additional \{(?P<more>[WUBRGC])\} for each "
                      r"(?P<kind>[a-z]+) counter removed this way$")


def cost_kind(part: str) -> str | None:
    """"Remove any number of storage counters from this land" → "storage" (else None)."""
    m = _COST.fullmatch(part)
    return m["kind"] if m else None


def first_sentence(first: str, kind: str | None) -> tuple[str, tuple[tuple[str, ...], ...]] | None:
    """(count, options) of the "Add … for each … counter removed this way" sentence, when the cost removes that kind."""
    if kind is None:
        return None
    if (m := _EACH.fullmatch(first)) and m["kind"] == kind:
        return f"{PREFIX}{kind}:0", ((m["sym"],),)
    if (m := _BATTERY.fullmatch(first)) and m["kind"] == kind and m["sym"] == m["more"]:
        return f"{PREFIX}{kind}:1", ((m["sym"],),)
    return None


def parts(count: str | None) -> tuple[str, int] | None:
    """The counter kind and the base amount of a removed-counters count, or None for any other count."""
    if not count or not count.startswith(PREFIX):
        return None
    kind, base = count[len(PREFIX):].rsplit(":", 1)
    return kind, int(base)


def options(have: int, count: str, option: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    """One option per number of counters the player may remove (107.1c; 118.3: at most ``have``)."""
    found = parts(count)
    assert found is not None
    _, base = found
    return tuple(option * (base + n) for n in range(0 if base else 1, have + 1))


def removed(count: str, option: tuple[str, ...]) -> tuple[str, int]:
    """The counters an option's mana removes as its cost: (kind, n)."""
    found = parts(count)
    assert found is not None
    kind, base = found
    return kind, len(option) - base

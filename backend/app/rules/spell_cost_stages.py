"""CR 601.2b/f: concrete symbol announcements precede reductions and total-cost floors."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.game.errors import ActionError
from app.rules import mana as M


@dataclass(frozen=True)
class PreparedCost:
    raw: M.ManaCost
    generic_less: int = 0
    colored_less: tuple[str, ...] = ()
    colored_only: tuple[str, ...] = ()
    # Selected raw mana/alternative and additional costs, before X substitution.
    # None means the caller did not preserve that history (including old saves).
    selected_cost_has_x: bool | None = None

    def evaluate(self, choices: list[str] | None = None) -> M.ManaCost:
        from app.rules import cost_changes

        cost = concrete(self.raw, choices) if choices is not None else self.raw
        cost = cost_changes.reduce_colored(cost, self.colored_less)
        cost = cost_changes.reduce_colored(cost, self.colored_only, only=True)
        return cost.plus_generic(-min(cost.generic, self.generic_less))


def symbols(cost: M.ManaCost) -> list[tuple[str, ...]]:
    return [*cost.hybrid, *(tuple(c.split('/')) + ('life',) for c in cost.phyrexian)]


def concrete(cost: M.ManaCost, choices: list[str]) -> M.ManaCost:
    slots = symbols(cost)
    if len(slots) != len(choices) or any(choice not in slot for choice, slot in zip(choices, slots, strict=True)):
        raise ActionError('Choose one legal nonhybrid equivalent for each mana symbol (601.2b)')
    generic = cost.generic + sum(int(c) for c in choices if c.isdigit())
    colored = cost.colored + tuple(c for c in choices if c != 'life' and not c.isdigit())
    return M.ManaCost(generic, colored, (), (), cost.x, cost.unsupported)


def life_symbols(cost: M.ManaCost, choices: list[str]) -> list[str]:
    concrete(cost, choices)  # validate the complete announcement, including hybrid slots
    return [color for color, choice in zip(cost.phyrexian, choices[len(cost.hybrid):], strict=True) if choice == 'life']


def variants(cost: M.ManaCost) -> list[list[str]]:
    """Distinct concrete costs, retaining a representative announcement for identical symbols."""
    ways: dict[tuple[Any, ...], list[str]] = {(cost.generic, tuple(sorted(cost.colored)), ()): []}
    for i, slot in enumerate(symbols(cost)):
        next_ways: dict[tuple[Any, ...], list[str]] = {}
        for (generic, colored, life), prior in ways.items():
            for choice in slot:
                key = (generic + (int(choice) if choice.isdigit() else 0),
                       tuple(sorted((*colored, choice))) if choice != 'life' and not choice.isdigit() else colored,
                       tuple(sorted((*life, cost.phyrexian[i-len(cost.hybrid)]))) if choice == 'life' else life)
                next_ways.setdefault(key, [*prior, choice])
        ways = next_ways
    return list(ways.values())

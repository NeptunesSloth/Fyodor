"""Paying a spell's total cost with things that aren't mana (CR 601.2h).

Convoke (702.51a), improvise (702.126a) and delve (702.66a) each say "rather than pay that mana":
tapping a creature or an artifact, or exiling a card from your graveyard, pays for ONE mana
symbol of the spell's locked-in total cost (601.2f). No mana is produced (106.3): nothing enters
the mana pool, nothing is left over, and "whenever you tap … for mana" / "whenever you add mana"
never sees it (106.12a).

A requirement is one symbol of the total cost: ``"1"`` (one generic mana), ``"G"``, ``"C"``
(specifically colorless), ``"W/U"`` / ``"2/G"`` (hybrid, 107.4e), ``"G/P"`` (Phyrexian).
A contribution pays exactly one requirement:

* convoke — a generic one, or a colored one matching one of the creature's colors
  (a hybrid symbol is each of its colors, 107.4e; a Phyrexian symbol is its color);
* improvise, delve — a generic one only.

Nothing here ever pays ``{C}``. The rest of the cost is paid with mana as usual.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from app.rules import mana as M

KINDS = ("convoke", "improvise", "delve")
GENERIC = "1"


@dataclass(frozen=True)
class Helper:
    """Something offered to pay part of the cost: a creature (convoke), an artifact (improvise)
    or a graveyard card (delve). ``colors`` matters only for convoke."""

    kind: str
    card: str
    colors: frozenset[str] = frozenset()


def requirements(cost: M.ManaCost) -> list[str]:
    """The total cost as one entry per mana symbol (generic mana is one entry per mana)."""
    out = [GENERIC] * cost.generic + list(cost.colored)
    out += ["/".join(h) for h in cost.hybrid]
    out += [f"{c}/P" for c in cost.phyrexian]
    return out


def pays(helper: Helper, symbol: str) -> bool:
    """Can this helper pay this one requirement?"""
    if symbol == GENERIC:
        return True
    if helper.kind != "convoke" or symbol == "C":
        return False
    parts = symbol.split("/")
    if parts[-1] == "P":
        return parts[0] in helper.colors
    return any(p in helper.colors for p in parts)


def remaining(cost: M.ManaCost, paid: Iterable[str]) -> M.ManaCost:
    """The mana still to pay after these requirements were paid by contributions."""
    generic = cost.generic
    colored = list(cost.colored)
    hybrid = ["/".join(h) for h in cost.hybrid]
    phyrexian = [f"{c}/P" for c in cost.phyrexian]
    for sym in paid:
        if sym == GENERIC:
            generic -= 1
        elif sym in colored:
            colored.remove(sym)
        elif sym in hybrid:
            hybrid.remove(sym)
        elif sym in phyrexian:
            phyrexian.remove(sym)
        else:
            raise ValueError(f"{{{sym}}} isn't part of the cost")
    if generic < 0:
        raise ValueError("more generic mana paid than the cost has")
    return M.ManaCost(generic, tuple(colored), tuple(tuple(h.split("/")) for h in hybrid),
                      tuple(p[0] for p in phyrexian), 0, cost.unsupported)


def _order(symbols: Iterable[str]) -> list[str]:
    """Colored requirements before generic ones: a colored creature is most useful where only it
    (or mana of its color) can pay."""
    return sorted(set(symbols), key=lambda s: (s == GENERIC, s))


def pool_pays(pool: dict[str, int], life: int = 0) -> Callable[[M.ManaCost], bool]:
    """``covers`` for :func:`assign`: can this mana pool (plus life for Phyrexian mana) pay it?"""
    def covers(rest: M.ManaCost) -> bool:
        try:
            M.solve(rest, dict(pool), [], life=life)
        except M.ManaError:
            return False
        return True
    return covers


def assign(cost: M.ManaCost, helpers: Sequence[Helper],
           covers: Callable[[M.ManaCost], bool] | None = None) -> list[str] | None:
    """Which requirement each helper pays (parallel to ``helpers``), such that ``covers`` accepts
    the mana still to pay — or, without ``covers``, merely such that every helper pays something.
    None if there's no such assignment (too many helpers, a wrong-color creature, …)."""
    reqs = requirements(cost)
    if len(helpers) > len(reqs):
        return None
    failed: set[tuple[int, tuple[str, ...]]] = set()

    def leaf(left: list[str]) -> bool:
        if covers is None:
            return True
        paid = list(reqs)
        for sym in left:
            paid.remove(sym)
        return covers(remaining(cost, paid))

    def dfs(i: int, left: list[str], chosen: list[str]) -> list[str] | None:
        if i == len(helpers):
            return chosen if leaf(left) else None
        key = (i, tuple(sorted(left)))
        if key in failed:
            return None
        for sym in _order(s for s in left if pays(helpers[i], s)):
            rest = list(left)
            rest.remove(sym)
            found = dfs(i + 1, rest, [*chosen, sym])
            if found is not None:
                return found
        failed.add(key)
        return None

    return dfs(0, reqs, [])


def label(symbol: str) -> str:
    return "{" + symbol + "}"


def after_pool(cost: M.ManaCost, pool: dict[str, int]) -> M.ManaCost:
    """What's still to add once the mana pool pays what it can (for the payment panel: a greedy
    estimate — colored symbols first, then hybrid, Phyrexian, and generic from what's left)."""
    units = {k: v for k, v in pool.items() if v > 0}

    def take(colors: Iterable[str]) -> bool:
        for c in colors:
            if units.get(c, 0) > 0:
                units[c] -= 1
                return True
        return False

    colored = tuple(c for c in cost.colored if not take((c,)))
    hybrid: list[tuple[str, ...]] = []
    for h in cost.hybrid:
        if not take(p for p in h if not p.isdigit()):
            hybrid.append(h)
    phyrexian = tuple(c for c in cost.phyrexian if not take((c,)))
    generic = max(0, cost.generic - sum(units.values()))
    return M.ManaCost(generic, colored, tuple(hybrid), phyrexian, 0, cost.unsupported)

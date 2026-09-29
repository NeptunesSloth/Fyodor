"""Mana: costs, mana abilities, and paying for things.

* ``parse_cost("{2}{G}{G}")`` → a ``ManaCost``.
* ``parse_mana_ability("{T}: Add {R} or {G}.")`` → what a mana ability produces, or ``None`` when
  the wording isn't one the engine understands (the ability then stays a manual one).
* ``solve(cost, pool, sources)`` finds a way to pay: mana already in the pool first, then untapped
  sources, preferring the least flexible ones so dual lands and "any color" sources are kept for
  last (roughly what Arena's auto-payment does).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from itertools import combinations_with_replacement

COLORS = ("W", "U", "B", "R", "G")
ALL_MANA = (*COLORS, "C")
_SYMBOL = re.compile(r"\{([^}]+)\}")
_COST_AND_EFFECT = re.compile(r"^(?P<cost>[^:]+): (?P<effect>Add .+)$")


class ManaError(ValueError):
    pass


@dataclass(frozen=True)
class ManaCost:
    generic: int = 0
    colored: tuple[str, ...] = ()  # one entry per coloured symbol, e.g. ("G", "G"); "C" = specifically colourless
    hybrid: tuple[tuple[str, ...], ...] = ()  # each: acceptable colours; ("2", "B") = two generic or {B}
    phyrexian: tuple[str, ...] = ()  # colours payable with mana or 2 life
    x: int = 0  # number of {X}
    unsupported: tuple[str, ...] = ()  # symbols the engine can't pay (e.g. {S} snow)

    def with_x(self, x: int) -> ManaCost:
        return ManaCost(self.generic + x * self.x, self.colored, self.hybrid, self.phyrexian, 0, self.unsupported)

    def plus_generic(self, n: int) -> ManaCost:
        return ManaCost(self.generic + n, self.colored, self.hybrid, self.phyrexian, self.x, self.unsupported)

    def text(self) -> str:
        parts = [f"{{{self.generic}}}"] if self.generic else []
        parts += ["{X}"] * self.x
        parts += [f"{{{c}}}" for c in self.colored]
        parts += ["{" + "/".join(h) + "}" for h in self.hybrid]
        parts += [f"{{{c}/P}}" for c in self.phyrexian]
        return "".join(parts) or "{0}"

    @property
    def is_free(self) -> bool:
        return not (self.generic or self.colored or self.hybrid or self.phyrexian or self.x)


def parse_cost(text: str | None) -> ManaCost:
    generic = x = 0
    colored: list[str] = []
    hybrid: list[tuple[str, ...]] = []
    phyrexian: list[str] = []
    unsupported: list[str] = []
    for sym in _SYMBOL.findall(text or ""):
        if sym.isdigit():
            generic += int(sym)
        elif sym == "X":
            x += 1
        elif sym in ALL_MANA:
            colored.append(sym)
        elif sym.endswith("/P") and sym[0] in COLORS:
            phyrexian.append(sym[0])
        elif "/" in sym:
            hybrid.append(tuple(sym.split("/")))
        else:
            unsupported.append(sym)
    return ManaCost(generic, tuple(colored), tuple(hybrid), tuple(phyrexian), x, tuple(unsupported))


@dataclass(frozen=True)
class ManaAbility:
    tap: bool
    sacrifice_self: bool
    options: tuple[tuple[str, ...], ...]  # each option: the mana it adds, e.g. ("C", "C") or ("R",)


def _effect_options(effect: str, identity: tuple[str, ...]) -> tuple[tuple[str, ...], ...] | None:
    effect = effect.strip().rstrip(".")
    if effect == "Add one mana of any color":
        return tuple((c,) for c in COLORS)
    if effect == "Add one mana of any color in your commander's color identity":
        return tuple((c,) for c in COLORS if c in identity)
    if effect == "Add two mana of any one color":
        return tuple((c, c) for c in COLORS)
    if effect == "Add two mana in any combination of colors":
        return tuple(combinations_with_replacement(COLORS, 2))
    body = effect[len("Add "):]
    if not body.startswith("{"):
        return None
    # "{R} or {G}" / "{W}, {U}, or {B}" → one symbol each; "{C}{C}" / "{G}{G}" → one option
    if " or " in body or ", " in body:
        pieces = [p.strip() for p in re.split(r",? or |, ", body) if p.strip()]
        if all(re.fullmatch(r"\{[WUBRGC]\}", p) for p in pieces):
            return tuple((p[1],) for p in pieces)
        return None
    if re.fullmatch(r"(\{[WUBRGC]\})+", body):
        return (tuple(_SYMBOL.findall(body)),)
    return None


def parse_mana_ability(text: str, identity: tuple[str, ...] = COLORS) -> ManaAbility | None:
    """Understand a mana ability whose cost is {T} (optionally "Sacrifice this …"). ``identity``
    is the controller's commander color identity (for Command Tower-style wording)."""
    m = _COST_AND_EFFECT.match(text.strip())
    if not m:
        return None
    cost = [c.strip() for c in m.group("cost").split(",")]
    tap = "{T}" in cost
    sacrifice = any(re.fullmatch(r"Sacrifice (this \w+|it)", c) for c in cost)
    if not tap or any(c != "{T}" and not re.fullmatch(r"Sacrifice (this \w+|it)", c) for c in cost):
        return None  # costs beyond {T} / sacrificing itself aren't automated yet
    options = _effect_options(m.group("effect"), identity)
    if options is None:
        return None
    return ManaAbility(tap=tap, sacrifice_self=sacrifice, options=options)


@dataclass(frozen=True)
class Source:
    card_id: str
    options: tuple[tuple[str, ...], ...]
    sacrifice: bool = False
    rank: int = 0  # tie-breaker: lower is tapped first (lands before creatures, …)
    preferred: bool = False  # the player marked it PREFER: used before anything else that fits

    @property
    def flexibility(self) -> int:
        return len({m for opt in self.options for m in opt})


@dataclass
class Payment:
    tapped: list[str] = field(default_factory=list)
    sacrificed: list[str] = field(default_factory=list)
    produced: dict[str, int] = field(default_factory=dict)  # mana added by the tapped sources
    spent: dict[str, int] = field(default_factory=dict)  # mana taken from the pool (after producing)
    life: int = 0  # life paid for Phyrexian symbols

    def delta(self) -> dict[str, int]:
        out = dict(self.produced)
        for k, v in self.spent.items():
            out[k] = out.get(k, 0) - v
        return {k: v for k, v in out.items() if v}


MAX_SEARCH = 20000
Chosen = list[tuple[Source, tuple[str, ...]]]
Found = tuple[dict[str, int], Chosen]


def _solve(reqs: list[tuple[str, ...]], generic: int, pool: dict[str, int], sources: list[Source]
           ) -> tuple[dict[str, int], list[tuple[Source, tuple[str, ...]]]] | None:
    """DFS over coloured/hybrid requirements; generic mana is paid last from whatever is left.
    Returns (units left over after paying, sources tapped with the option used)."""
    budget = [MAX_SEARCH]

    def generic_from(units: dict[str, int], remaining: list[Source], n: int, chosen: Chosen) -> Found | None:
        units = dict(units)
        # tap the sources that give the most mana first (Sol Ring before a Forest)
        for src in sorted(remaining, key=lambda s: (not s.preferred, -max(len(o) for o in s.options), s.flexibility, s.rank)):
            if sum(units.values()) >= n:
                break
            opt = max(src.options, key=len)
            for m in opt:
                units[m] = units.get(m, 0) + 1
            chosen = [*chosen, (src, opt)]
        if sum(units.values()) < n:
            return None
        for _ in range(n):  # spend colourless first, then the most plentiful colour
            k = max(units, key=lambda c: (c == "C", units[c]))
            units[k] -= 1
        return {k: v for k, v in units.items() if v}, chosen

    def dfs(i: int, units: dict[str, int], remaining: list[Source], chosen: Chosen, extra_generic: int) -> Found | None:
        budget[0] -= 1
        if budget[0] < 0:
            return None
        if i == len(reqs):
            return generic_from(units, remaining, generic + extra_generic, chosen)
        req = reqs[i]
        if req[0].isdigit():  # {2/B}: {B}, or two generic
            alt = _pay_one(units, remaining, chosen, (req[1],))
            for u2, rem2, ch2 in alt:
                r = dfs(i + 1, u2, rem2, ch2, extra_generic)
                if r:
                    return r
            return dfs(i + 1, units, remaining, chosen, extra_generic + int(req[0]))
        for u2, rem2, ch2 in _pay_one(units, remaining, chosen, req):
            r = dfs(i + 1, u2, rem2, ch2, extra_generic)
            if r:
                return r
        return None

    return dfs(0, {k: v for k, v in pool.items() if v > 0}, sources, [], 0)


def _pay_one(units: dict[str, int], remaining: list[Source], chosen: Chosen, req: tuple[str, ...]
             ) -> Iterator[tuple[dict[str, int], list[Source], Chosen]]:
    """Ways to pay one symbol that accepts any colour in ``req``: from the pool, else by tapping a source."""
    for color in req:
        if units.get(color, 0) > 0:
            new = dict(units)
            new[color] -= 1
            yield new, remaining, chosen
    for j, src in enumerate(remaining):
        for opt in src.options:
            wanted = next((c for c in req if c in opt), None)
            if wanted is None:
                continue
            new = dict(units)
            for m in opt:
                new[m] = new.get(m, 0) + 1
            new[wanted] -= 1
            yield new, remaining[:j] + remaining[j + 1:], [*chosen, (src, opt)]


def solve(cost: ManaCost, pool: dict[str, int], sources: list[Source], *, life: int = 0) -> Payment:
    """Find a payment for ``cost`` (X already fixed). Raises ManaError if there is none."""
    if cost.unsupported:
        raise ManaError(f"Can't pay {' '.join('{' + s + '}' for s in cost.unsupported)} automatically")
    ordered = sorted(sources, key=lambda s: (not s.preferred, s.flexibility, s.rank, -max(len(o) for o in s.options)))
    base = [(c,) for c in cost.colored] + sorted(cost.hybrid, key=len)
    attempts = [(base + [(c,) for c in cost.phyrexian], 0)]  # Phyrexian with mana first …
    if cost.phyrexian:
        attempts.append((base, 2 * len(cost.phyrexian)))  # … else with 2 life each
    for reqs, life_cost in attempts:
        if life_cost and life_cost >= life:
            continue
        found = _solve(reqs, cost.generic, pool, ordered)
        if found is None:
            continue
        left, chosen = found
        payment = Payment(life=life_cost)
        for src, opt in chosen:
            payment.tapped.append(src.card_id)
            if src.sacrifice:
                payment.sacrificed.append(src.card_id)
            for m in opt:
                payment.produced[m] = payment.produced.get(m, 0) + 1
        total = {k: v for k, v in pool.items() if v > 0}
        for k, v in payment.produced.items():
            total[k] = total.get(k, 0) + v
        payment.spent = {k: v - left.get(k, 0) for k, v in total.items() if v - left.get(k, 0) > 0}
        return payment
    raise ManaError(f"Not enough mana to pay {cost.text()}")


def symbols(mana: dict[str, int]) -> str:
    """{"G": 2, "C": 1} → "{C}{G}{G}"."""
    return "".join(f"{{{c}}}" * mana.get(c, 0) for c in ALL_MANA) or "{0}"

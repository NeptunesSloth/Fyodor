"""Typed allocation for mana units that cannot pay genuine generic requirements."""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from itertools import combinations

from app.rules import mana as M
from app.rules.mana_requirement_rows import (
    ProducerRequirement,
    Requirement,
    RequirementPlan,
    SpentClass,
    UnitClass,
    producer_allowed,
)


def requirements(cost: M.ManaCost, mode: str | None = None) -> RequirementPlan:
    """Stage matching changes without replacing a colored symbol by a generic origin."""
    def matches(symbols: tuple[str, ...]) -> tuple[str, ...]:
        if mode == 'white_red' and 'R' in symbols:
            return tuple(dict.fromkeys((*symbols, 'W')))
        if mode == 'white_any':
            return tuple(dict.fromkeys(x for c in symbols for x in (('C', 'U', 'B', 'R', 'G') if c == 'C' else ('W',) if c in M.COLORS else (c,))))
        if mode == 'white_color' and any(c in M.COLORS for c in symbols):
            return tuple(dict.fromkeys((*symbols, 'W')))
        if mode == 'colorless_color' and any(c in M.COLORS for c in symbols):
            return tuple(dict.fromkeys((*symbols, 'C')))
        if mode in ('type', 'color'):
            numeric = tuple(c for c in symbols if c.isdigit())
            if mode == 'type' and any(c in M.ALL_MANA for c in symbols):
                return M.ALL_MANA
            if mode == 'color' and all(c in M.COLORS for c in symbols):
                return (*numeric, *M.ALL_MANA)
        return symbols

    if cost.allocation is not None:
        def transform(row: Requirement) -> Requirement:
            return Requirement(matches(row.alternatives), row.generic, row.helpers, row.producer)
        return RequirementPlan(cost.allocation.generic, tuple(map(transform, cost.allocation.symbols)),
                               tuple(map(transform, cost.allocation.phyrexian)))
    return RequirementPlan(cost.generic,
        tuple(Requirement(matches((c,)), helpers=(c,)) for c in cost.colored) +
        tuple(Requirement(matches(h), helpers=h) for h in sorted(cost.hybrid, key=len)),
        tuple(Requirement(matches(tuple(c.split('/'))), helpers=tuple(c.split('/'))) for c in cost.phyrexian))


def constrain_producer(cost: M.ManaCost, producer: ProducerRequirement) -> M.ManaCost:
    """Post-announcement lowering; constrained generic retains genuine origin."""
    rows = requirements(cost)
    def restrict(row: Requirement) -> Requirement:
        return Requirement(row.alternatives, row.generic, row.helpers, producer)
    restricted = RequirementPlan(0,
        tuple(map(restrict, rows.symbols)) +
        (Requirement(M.ALL_MANA, generic=True, helpers=(*M.ALL_MANA, '1'), producer=producer),) * rows.generic,
        tuple(map(restrict, rows.phyrexian)))
    return from_plan(restricted, cost.unsupported)


def constrain_generic(plan: RequirementPlan, alternatives: tuple[tuple[str, ...], ...]) -> RequirementPlan:
    if len(alternatives) > plan.generic:
        raise ValueError('A generic allocation constraint cannot invent additional requirements')
    return RequirementPlan(plan.generic - len(alternatives),
        plan.symbols + tuple(Requirement(colors, generic=True) for colors in alternatives), plan.phyrexian)


def assign_generic_encoding(cost: M.ManaCost, colors: tuple[str, ...]) -> RequirementPlan:
    """Fix filter/chosen-color inputs while retaining origins hidden by as-though folding."""
    if len(colors) != cost.generic:
        raise ValueError('Every encoded generic input needs an actual matching type')
    rows = requirements(cost)
    ordinary = min(rows.generic, len(colors))
    constrained = constrain_generic(rows, tuple((c,) for c in colors[:ordinary]))
    hidden = iter(colors[ordinary:])
    symbols = list(constrained.symbols)
    for i, row in enumerate(symbols):
        if row.alternatives == M.ALL_MANA and not row.generic:
            color = next(hidden, None)
            if color is not None:
                symbols[i] = Requirement((color,), False, row.helpers, row.producer)
    if next(hidden, None) is not None:
        raise ValueError('The encoded input has no preserved requirement origin')
    return RequirementPlan(constrained.generic, tuple(symbols), constrained.phyrexian)


def from_plan(rows: RequirementPlan, unsupported: tuple[str, ...] = ()) -> M.ManaCost:
    return M.ManaCost(rows.generic, (), tuple(r.alternatives for r in rows.symbols),
                      tuple('/'.join(r.alternatives) for r in rows.phyrexian), unsupported=unsupported,
                      allocation=rows)


@dataclass(frozen=True)
class MaskedSource:
    source: M.Source
    generic: tuple[bool, ...] = ()

    def allows_generic(self, index: int) -> bool:
        if self.generic and len(self.generic) != len(self.source.options):
            raise ValueError('Every source option needs its own eligibility mask')
        return self.generic[index] if self.generic else True

    def unit_class(self, index: int, position: int) -> UnitClass:
        actual_mana = not self.source.abilities or self.source.abilities[index] >= 0
        profiles = self.source.producer_facts
        if profiles and (len(profiles) != len(self.source.options)
                or any(len(facts) != len(option) for facts, option in zip(profiles, self.source.options, strict=True))):
            raise ValueError('Every output position needs its own producer fact')
        producer = profiles[index][position] if profiles and actual_mana else None
        snow = ('Snow' in producer.tags if producer is not None else self.source.snow if not profiles else False)
        return UnitClass(self.source.options[index][position], self.allows_generic(index), snow and actual_mana, producer)



@dataclass(frozen=True)
class Choice:
    source: MaskedSource
    index: int

    @property
    def output(self) -> tuple[str, ...]:
        return self.source.source.options[self.index]


@dataclass
class MaskedPayment:
    payment: M.Payment
    choices: list[Choice]
    allocation: list[SpentClass]
    remaining: dict[UnitClass, int]


Units = dict[UnitClass, int]
Found = tuple[Units, list[Choice]]
State = tuple[int, Units, list[MaskedSource], list[Choice], int, tuple[Requirement, ...], tuple[str, ...]]  # (the last: colors the distinct rows used)


def _produced(units: Units, source: MaskedSource, index: int) -> Units:
    out = dict(units)
    for position, _ in enumerate(source.source.options[index]):
        key = source.unit_class(index, position)
        out[key] = out.get(key, 0) + 1
    return out


def _pay_one(units: Units, remaining: list[MaskedSource], chosen: list[Choice], req: Requirement, used: tuple[str, ...] = ()
             ) -> Iterator[tuple[Units, list[MaskedSource], list[Choice], str]]:
    for color in req.alternatives:
        for key in sorted(units, key=lambda k: (k.generic, k.snow, k.sym)):
            if req.distinct and key.sym in used:
                continue
            if units[key] > 0 and producer_allowed(key.producer, req.producer) and (not req.generic or key.generic) and (key.snow if color == M.SNOW else key.sym == color):
                out = dict(units)
                out[key] -= 1
                yield out, remaining, chosen, key.sym
    for j, source in enumerate(remaining):
        src = source.source
        for index, option in enumerate(src.options):
            helper = bool(src.abilities and src.abilities[index] < 0)
            if req.alternatives == ('B', '@X') and src.abilities and src.abilities[index] < 0:
                continue
            if req.generic and not source.allows_generic(index):
                continue
            alternatives = req.helpers if helper and req.helpers is not None else req.alternatives
            keys = tuple(dict.fromkeys(source.unit_class(index, position)
                                       for position, _ in enumerate(option)))
            for key in keys:
                if not (key.snow if alternatives == (M.SNOW,) else key.sym in alternatives) or (req.distinct and key.sym in used):
                    continue
                if not helper and not producer_allowed(key.producer, req.producer):
                    continue
                out = _produced(units, source, index)
                out[key] -= 1
                yield out, remaining[:j] + remaining[j + 1:], [*chosen, Choice(source, index)], key.sym



def _generic(units: Units, remaining: list[MaskedSource], n: int, chosen: list[Choice]) -> Found | None:
    units = dict(units)
    for source in sorted(remaining, key=lambda s: (s.source.rank >= 0, not s.source.preferred,
            -max(map(len, s.source.options)), s.source.flexibility, s.source.rank)):
        if sum(amount for key, amount in units.items() if key.generic) >= n:
            break
        options = [i for i in range(len(source.source.options)) if source.allows_generic(i)]
        if not options:
            continue
        index = max(options, key=lambda i: len(source.source.options[i]))
        units = _produced(units, source, index)
        chosen = [*chosen, Choice(source, index)]
    if sum(amount for key, amount in units.items() if key.generic) < n:
        return None
    for _ in range(n):
        key = max((k for k, amount in units.items() if amount > 0 and k.generic),
                  key=lambda k: (k.sym == 'C', units[k], not k.snow))
        units[key] -= 1
    return {key: amount for key, amount in units.items() if amount > 0}, chosen


def _solve(reqs: list[Requirement], generic: int, pool: dict[str, int], sources: list[MaskedSource],
           *, iterative: bool = False) -> Found | None:
    budget = [M.MAX_SEARCH]
    start = {UnitClass(sym): amount for sym, amount in pool.items() if amount > 0}

    def children(state: State) -> Iterator[State]:
        i, units, remaining, chosen, extra, deferred, used = state
        req = reqs[i] if i < len(reqs) else deferred[i - len(reqs)]
        if req.alternatives[0].isdigit():
            for u, r, c, _sym in _pay_one(units, remaining, chosen, Requirement(req.alternatives[1:], req.generic, req.helpers, req.producer), used):
                yield i + 1, u, r, c, extra, deferred, used
            amount = int(req.alternatives[0])
            if req.producer is None:
                yield i + 1, units, remaining, chosen, extra + amount, deferred, used
            else:
                owed = (Requirement(M.ALL_MANA, generic=True, helpers=(*M.ALL_MANA, '1'), producer=req.producer),) * amount
                yield i + 1, units, remaining, chosen, extra, deferred + owed, used
        else:
            for u, r, c, sym in _pay_one(units, remaining, chosen, req, used):
                yield i + 1, u, r, c, extra, deferred, (*used, sym) if req.distinct else used

    def dfs(state: State) -> Found | None:
        budget[0] -= 1
        if budget[0] < 0:
            return None
        i, units, remaining, chosen, extra, deferred, used = state
        if i == len(reqs) + len(deferred):
            return _generic(units, remaining, generic + extra, chosen)
        for child in children(state):
            if (found := dfs(child)) is not None:
                return found
        return None

    initial: State = (0, start, sources, [], 0, (), ())
    potential = len(reqs) + sum(int(req.alternatives[0]) for req in reqs
        if req.producer is not None and req.alternatives[0].isdigit())
    if not iterative and potential < 256:
        return dfs(initial)
    pending: list[Iterator[State]] = [iter([initial])]
    while pending:
        state = next(pending[-1], None)
        if state is None:
            pending.pop()
            continue
        budget[0] -= 1
        if budget[0] < 0:
            return None
        i, units, remaining, chosen, extra, deferred, used = state
        if i == len(reqs) + len(deferred):
            if (found := _generic(units, remaining, generic + extra, chosen)) is not None:
                return found
        else:
            pending.append(children(state))
    return None


def solve(cost: M.ManaCost, pool: dict[str, int], sources: list[MaskedSource], *, life: int = 0,
          iterative: bool = False, plan: RequirementPlan | None = None, mode: str | None = None) -> MaskedPayment:
    if cost.unsupported:
        raise M.ManaError('Unsupported cost symbol')
    ordered = sorted(sources, key=lambda s: (s.source.rank >= 0, not s.source.preferred, s.source.flexibility,
                                            s.source.rank, -max(map(len, s.source.options))))
    plan = plan or cost.allocation or requirements(cost, mode)
    base = list(plan.symbols)
    phy = plan.phyrexian
    by_life = {tuple(sorted((phy[i] for i in ix), key=lambda r: (r.alternatives, r.generic))): ix
               for k in range(len(phy) + 1) for ix in combinations(range(len(phy)), k)}
    for indices in by_life.values():
        due_life = 2 * len(indices)
        if due_life > life:
            continue
        reqs = base + [req for i, req in enumerate(phy) if i not in indices]
        if (found := _solve(reqs, plan.generic, pool, ordered, iterative=iterative)) is None:
            continue
        left, chosen = found
        total = {UnitClass(sym): amount for sym, amount in pool.items() if amount > 0}
        payment = M.Payment(life=due_life)
        for choice in chosen:
            src = choice.source.source
            payment.selected_options.append((src.card_id, choice.index))
            if src.ability_options:
                payment.ability_options.append((src.card_id, src.ability_options[choice.index]))
            payment.slots.append((src.card_id, choice.output))
            payment.tapped.append(src.card_id)
            if src.sacrifice:
                payment.sacrificed.append(src.card_id)
            if src.abilities:
                payment.used.append((src.card_id, src.abilities[choice.index]))
            total = _produced(total, choice.source, choice.index)
            for sym in choice.output:
                payment.produced[sym] = payment.produced.get(sym, 0) + 1
        allocation = [SpentClass(key, amount - left.get(key, 0)) for key, amount in total.items()
                      if amount > left.get(key, 0)]
        for row in allocation:
            payment.spent[row.unit.sym] = payment.spent.get(row.unit.sym, 0) + row.amount
        payment.allocation = allocation
        return MaskedPayment(payment, chosen, allocation, left)
    raise M.ManaError(f'Not enough eligible mana to pay {cost.text()}')


@dataclass(frozen=True)
class Slot:
    unit: UnitClass
    source: str
    unit_id: int | None = None
    tags: tuple[str, ...] = ()
    riders: tuple[str, ...] = ()


@dataclass
class Settlement:
    spent: list[Slot]
    produced_left: list[Slot]
    plain_delta: dict[str, int]


def settle(allocation: list[SpentClass], slots: list[Slot]) -> Settlement:
    """Stage the native exact-class settlement boundary, without mutating any game."""
    spent: list[Slot] = []
    left = list(slots)
    delta: dict[str, int] = {}
    for row in allocation:
        eligible = sorted((s for s in left if s.unit == row.unit), key=lambda s: s.unit_id is None)
        taken = eligible[:row.amount]
        spent.extend(taken)
        for slot in taken:
            left.remove(slot)
        plain = row.amount - len(taken)
        if plain:
            if row.unit != UnitClass(row.unit.sym):
                raise M.ManaError('A typed allocation has no matching actual mana slots')
            delta[row.unit.sym] = delta.get(row.unit.sym, 0) - plain
    return Settlement(spent, [slot for slot in left if slot.unit_id is None], delta)

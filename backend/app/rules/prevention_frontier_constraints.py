"""Unregistered integer feasibility prototype for saved damage frontiers.

The exhaustive proof oracle enumerates every allocation. This model instead
validates a numeric prefix by affine constraints, including cyclic capacities.
No new dependency, production planner path, candidate commutation shortcut or
card hook is introduced here.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.rules import prevention_frontier_prototype as frontier

Variable = tuple[str, str]


@dataclass(frozen=True)
class Affine:
    constant: int = 0
    terms: tuple[tuple[Variable, int], ...] = ()

    def add(self, other: Affine) -> Affine:
        terms = dict(self.terms)
        for key, coefficient in other.terms:
            terms[key] = terms.get(key, 0) + coefficient
        return Affine(self.constant + other.constant, tuple(sorted((k, n) for k, n in terms.items() if n)))

    def scale(self, n: int) -> Affine:
        return Affine(self.constant * n, tuple((k, coefficient * n) for k, coefficient in self.terms if coefficient * n))

    def subtract(self, other: Affine) -> Affine:
        return self.add(other.scale(-1))


def model(frame: frontier.Frontier, zero_terminals: tuple[str, ...] = ()) -> tuple[dict[Variable, tuple[int, int]], tuple[Affine, ...], tuple[tuple[Affine, ...], ...]]:
    """Every returned base expression is <=0; each budget case chooses one ==0."""
    bounds = {(group, row): (0, upper) for group, row, upper in frontier.rows(frame)}
    capacities: dict[Variable, Affine] = {}
    budgets: dict[str, int] = {}
    terminals: dict[str, Affine] = {}

    def visit(packet: frontier.Packet, path: str, recipient: str, n: Affine,
              operations: tuple[frontier.Operation, ...], applied: frozenset[str]) -> None:
        for op in operations:
            if op.id in applied:
                continue
            if op.kind == 'multiply':
                applied |= {op.id}
                n = n.scale(op.factor)
            elif op.kind == 'protection':
                applied |= {op.id}
                if not packet.unpreventable:
                    n = Affine()
            elif op.kind == 'pool':
                pool = frontier._pool(frame, op.pool)
                eligible = ((pool.mode == 'redirect' or not packet.unpreventable)
                            and (not pool.source_oids or packet.source_oid in pool.source_oids)
                            and (not pool.recipients or recipient in pool.recipients))
                group = frontier.group(frame, pool, packet)
                key = group, path
                budgets[group] = pool.remaining
                capacities[key] = n if eligible else Affine()
                amount = Affine(terms=((key, 1),))
                n = n.subtract(amount)
                if not eligible:
                    continue
                applied |= {op.id}
                if pool.mode == 'redirect':
                    import json

                    branch = json.dumps([path, op.id, pool.destination, pool.destination_oid], separators=(',', ':'))
                    visit(packet, branch, pool.destination, amount,
                          frontier._trace(frame, pool.destination, pool.destination_controller, packet.source_oid, branch), applied)

        terminals[path] = n

    for packet in frame.packets:
        visit(packet, packet.lineage, packet.recipient, Affine(packet.amount), packet.operations, frozenset())
    constraints = [Affine(terms=((key, 1),)).subtract(capacity) for key, capacity in capacities.items()]
    if any(path not in terminals for path in zero_terminals):
        raise ValueError('Unknown symbolic zero terminal')
    constraints.extend(terminals[path] for path in zero_terminals)
    cases = []
    for group, budget in sorted(budgets.items()):
        total = Affine()
        capacity = Affine()
        for key, expression in capacities.items():
            if key[0] == group:
                total = total.add(Affine(terms=((key, 1),)))
                capacity = capacity.add(expression)
        exhausted = total.subtract(Affine(budget))
        all_prevented = total.subtract(capacity)
        constraints += [exhausted, all_prevented]
        # sum(vector)=min(budget,sum(capacity)): both upper bounds, one equality.
        cases.append(tuple(dict.fromkeys((exhausted, all_prevented))))
    return bounds, tuple(constraints), tuple(cases)


def _tighten(bounds: dict[Variable, tuple[int, int]], constraints: tuple[Affine, ...]) -> dict[Variable, tuple[int, int]] | None:
    bounds = dict(bounds)
    while True:
        changed = False
        for expression in constraints:
            for key, coefficient in expression.terms:
                others_min = expression.constant + sum(
                    n * bounds[k][0 if n > 0 else 1] for k, n in expression.terms if k != key)
                low, high = bounds[key]
                if coefficient > 0:
                    high = min(high, -others_min // coefficient)
                else:
                    low = max(low, -(others_min // coefficient))
                if low > high:
                    return None
                if bounds[key] != (low, high):
                    bounds[key] = low, high
                    changed = True
            if expression.constant + sum(n * bounds[k][0 if n > 0 else 1] for k, n in expression.terms) > 0:
                return None
        if not changed:
            return bounds


def _integer_witness(bounds: dict[Variable, tuple[int, int]], constraints: tuple[Affine, ...]) -> dict[Variable, int] | None:
    tightened = _tighten(bounds, constraints)
    if tightened is None:
        return None
    free = [key for key, (low, high) in tightened.items() if low != high]
    if not free:
        return {key: low for key, (low, _) in tightened.items()}
    key = max(free, key=lambda k: tightened[k][1] - tightened[k][0])
    low, high = tightened[key]
    middle = (low + high) // 2
    for interval in ((low, middle), (middle + 1, high)):
        proposed = {**tightened, key: interval}
        if (result := _integer_witness(proposed, constraints)) is not None:
            return result
    return None


def witness(frame: frontier.Frontier, prefix: tuple[tuple[str, str, int], ...] = (), *,
            zero_terminals: tuple[str, ...] = ()) -> frontier.Solution | None:
    """Return one jointly feasible completion, without enumerating the vectors."""
    bounds, base, cases = model(frame, zero_terminals)
    fixed: dict[Variable, int] = {}
    for group, row, n in [*( (s.pool_group, row, n) for s in frame.selections for row, n in s.vector), *prefix]:
        key = group, row
        if key not in bounds or (key in fixed and fixed[key] != n):
            return None
        low, high = bounds[key]
        if not low <= n <= high:
            return None
        fixed[key] = n
        bounds[key] = n, n

    def branch(i: int, current: tuple[Affine, ...]) -> dict[Variable, int] | None:
        if i == len(cases):
            return _integer_witness(bounds, current)
        for equality in cases[i]:
            proposed = (*current, equality.scale(-1))  # <=0 already present; add >=0.
            if _tighten(bounds, proposed) is None:
                continue
            if (found := branch(i + 1, proposed)) is not None:
                return found
        return None

    found = branch(0, base)
    if found is None:
        return None
    result = frontier._evaluate(frame, found)
    assert result is not None, 'Integer constraints diverged from the pure event evaluator'
    return result

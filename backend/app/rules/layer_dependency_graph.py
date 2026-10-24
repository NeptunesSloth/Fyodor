"""Transient native layer positions and dependency ordering (613.6, 613.8).

Rule timestamps stay unchanged. Applied operations are retained explicitly, including
fixed resolved effects, so reconstruction does not sort a dependency order away.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.rules_state import ContinuousEffect
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import CardInfo, Characteristics
    from app.rules.layers import Static

Key = tuple[int, int, int]


def next_index(keys: Sequence[Key], depends: Callable[[int, int], bool]) -> int:
    """Only disregard a cycle's internal edges when that component is ready."""
    deps = {i: {j for j in range(len(keys)) if i != j and depends(i, j)} for i in range(len(keys))}
    serial = 0
    indices: dict[int, int] = {}
    lows: dict[int, int] = {}
    stack: list[int] = []
    stacked: set[int] = set()
    components: list[set[int]] = []

    def visit(v: int) -> None:
        nonlocal serial
        indices[v] = lows[v] = serial
        serial += 1
        stack.append(v)
        stacked.add(v)
        for w in deps[v]:
            if w not in indices:
                visit(w)
                lows[v] = min(lows[v], lows[w])
            elif w in stacked:
                lows[v] = min(lows[v], indices[w])
        if lows[v] == indices[v]:
            component: set[int] = set()
            while True:
                w = stack.pop()
                stacked.remove(w)
                component.add(w)
                if w == v:
                    break
            components.append(component)

    for i in range(len(keys)):
        if i not in indices:
            visit(i)
    ready = [c for c in components if all(deps[v] <= c for v in c)]
    return min((i for c in ready for i in c), key=lambda i: (keys[i], i))


@dataclass(frozen=True)
class Node:
    key: Key
    static: Static | None = None
    effect: ContinuousEffect | None = None
    definition: dict[str, Any] | None = None
    fixed: frozenset[str] | None = None
    source: str | None = None


@dataclass(frozen=True)
class Signature:
    active: bool
    members: frozenset[str]
    operation: str


@dataclass(frozen=True)
class Position:
    chars: dict[str, Characteristics]
    dead: dict[str, Key]


def apply_type_node(node: Node, before: Characteristics) -> tuple[Characteristics, bool]:
    """One native type operation, including intrinsic mana that follows land types."""
    from app.rules import layers, type_statics

    if node.effect is not None:
        changed = layers._layer4(before, [node.effect])
        sets = node.effect.set_land_types is not None
    else:
        changed = layers._layer4(before, [], [(node.key[0], node.definition or {})])
        sets = bool(((node.definition or {}).get('layer4') or {}).get('set_land_types'))
    # Reconstructing several separate operations must not keep intrinsic mana
    # from an earlier land type that a subsequent operation has removed.
    kept = tuple(a for a in changed.abilities if not (a.intrinsic and 90 <= a.index < 95)
                 or ('Land' in changed.types and type_statics.BASIC[a.index - 90] in changed.subtypes))
    if kept != changed.abilities:
        changed = replace(changed, abilities=kept)
    return type_statics.with_gained_mana(before, changed, sets), sets and 'Land' in changed.types


class StaticTable(list["Static"]):
    """Effective statics plus transient raw sources and exact layer4 operations."""
    def __init__(self, rows: Sequence[Static], raw: Sequence[Static], orders: dict[str, tuple[Node, ...]],
                 colors: dict[str, tuple[Node, ...]] | None = None) -> None:
        super().__init__(rows)
        self.raw = tuple(raw)
        self.layer4_orders = orders
        self.layer5_orders = colors or {}

    def detached(self) -> StaticTable:
        return StaticTable(self, self.raw, self.layer4_orders, self.layer5_orders)

    def layer4(self, cid: str, ch: Characteristics) -> Characteristics:
        for node in self.layer4_orders.get(cid, ()):
            ch, _ = apply_type_node(node, ch)
        return ch

    def layer5(self, cid: str, ch: Characteristics) -> Characteristics:
        from app.rules import layers

        for node in self.layer5_orders.get(cid, ()):
            ch = layers._layer5(ch, [node.effect] if node.effect is not None else [],
                               [] if node.effect is not None else [(node.key[0], node.definition or {})])
        return ch


def has_layer4(d: dict[str, Any]) -> bool:
    return bool(d.get('layer4') or any(k in d for k in ('remove_types', 'add_types', 'add_subtypes')))


def first_layer(d: dict[str, Any]) -> int:
    from app.rules.group_layers import first_layer as native_first

    return 4 if has_layer4(d) else native_first(d)


class Solver:
    def __init__(self, state: GameState, info: CardInfo, raw: Sequence[Static], incoming: CardInstance | None = None) -> None:
        from app.rules import characteristics as chars
        from app.rules import layers, scripts
        from app.rules.plan import Plan

        self.original, self.info = state, info
        self.raw = list(raw)
        self.incoming = incoming
        self.cards = {cid: c for cid, c in state.cards.items() if c.zone.endswith(':battlefield')}
        if incoming is not None:
            self.cards[incoming.id] = incoming
            self.raw = [st for st in self.raw if st.source != incoming.id]
            real = state.cards.get(incoming.id)
            stamp = (state.rules.next_object + 1 if state.rules is not None and
                     (real is None or not real.zone.endswith(':battlefield')) else layers.timestamp(state, incoming.id))
            for d in scripts.definitions(layers.source_text71(state, incoming, layers.copiable(state, incoming, info), info)).values():
                if d['kind'] == 'static' and d.get('static') in ('grant', 'attached_rule'):
                    self.raw.append(layers.Static(incoming.id, incoming.controller, d, stamp))
                    self.raw.extend(layers.Static(incoming.id, incoming.controller, extra, stamp)
                                    for extra in d.get('also', ()))
            zones = {k: [cid for cid in ids if cid != incoming.id] for k, ids in state.zones.items()}
            zones.setdefault(incoming.zone, []).append(incoming.id)
            state = state.model_copy(update={'cards': {**state.cards, incoming.id: incoming}, 'zones': zones})
            if real is not None and real.zone.endswith(':battlefield'):
                self.raw.extend(layers._resolved_mana_statics(state, [(incoming.id, incoming.controller)]))
        self.state = state
        self.effects = {cid: layers.affecting(self.original, c, info) for cid, c in self.cards.items()}
        if incoming is not None:
            real = self.original.cards.get(incoming.id)
            if (real is None or not real.zone.endswith(':battlefield')) and not layers.spell_entry(self.original, incoming, info):
                self.effects[incoming.id] = [e for e in self.effects[incoming.id] if e.id.startswith('entry:')]
        self.base = {cid: layers.name_changes(layers.subtype_cdas(c, layers.prepared(self.original, c, chars.of(c, info), info)),
                                            self.effects[cid], layers._attached45(state, c, info, self.raw), info, state, c)
                     for cid, c in self.cards.items()}
        self.base = {cid: replace(chars.provenance(self.cards[cid], ch), on_battlefield=True,
                                  object_counters=frozenset(k for k, n in self.cards[cid].counters.items() if n > 0),
                                  object_ring_bearer=bool(state.rules and
                                      state.rules.ring_bearers.get(self.cards[cid].controller) == state.rules.object_id(cid)))
                     for cid, ch in self.base.items()}
        self.begun: dict[int, frozenset[str]] = {}
        self.removed: set[int] = set()
        self.orders: dict[str, list[Node]] = {cid: [] for cid in self.cards}
        self.color_orders: dict[str, list[Node]] = {cid: [] for cid in self.cards}
        self.position = Position(self.base, {})
        owner = self

        class PositionView(Plan):
            def ch(self, card: CardInstance) -> Characteristics:
                if card.id in owner.position.chars and card.zone.endswith(':battlefield'):
                    return owner.position.chars[card.id]
                return layers.prepared(owner.original, card, chars.of(card, owner.info), owner.info)

        self.view = PositionView.__new__(PositionView)
        self.view.state, self.view.info = state, info
        self.nodes4: list[Node] = []
        for st in self.raw:
            if st.gate is None and has_layer4(st.definition):
                self.nodes4.append(Node(st.key, static=st, definition=self.definition(st), source=st.source))
        # Impending and linked traits are native self contributors, represented once.
        from app.rules import linked_aggregates
        for cid, card in self.cards.items():
            for seq, d in layers._impending_layer4(self.original, card, info):
                self.nodes4.append(Node((int(seq), 0, 0), definition=d, fixed=frozenset({cid}), source=cid))
            linked = (linked_aggregates.traits_layer4(state, card, info)
                      if any(st.source == cid and st.definition.get("linked_traits") for st in self.raw) else [])
            for seq, d in linked:
                linked_st = next((st for st in self.raw if st.source == cid and st.definition.get('linked_traits')), None)
                self.nodes4.append(Node((int(seq), 0, 0), static=linked_st, definition=d, fixed=frozenset({cid}), source=cid))
        fixed: dict[tuple[str, int, int], tuple[Any, set[str]]] = {}
        for cid, effects in self.effects.items():
            for e in effects:
                if incoming is not None and cid == incoming.id:
                    real = self.original.cards.get(cid)
                    if real is not None and not real.zone.endswith(':battlefield') and not e.id.startswith('entry:'):
                        continue  # Previous incarnations are not this prospective permanent.
                token = (e.id, e.object_seq, e.timestamp)
                if token not in fixed:
                    fixed[token] = (e, set())
                fixed[token][1].add(cid)
        self.fixed = [Node((e.object_seq, 1, e.timestamp), effect=e, fixed=frozenset(found)) for e, found in fixed.values()]
        self.nodes4 += [n for n in self.fixed if n.effect is not None and n.effect.layer == '4']
        for st in self.raw:
            if first_layer(st.definition) == 3 and self.holds(st, self.position):
                self.begun[id(st)] = self.members(st, self.position)

    def definition(self, st: Static) -> dict[str, Any]:
        from app.rules.group_layers import with_chosen

        d = with_chosen(self.state, st)
        if d.get('chosen_type') and not d.get('layer4'):
            return {**d, 'add_subtypes': [v for v in [self.state.cards[st.source].choices.get('Chosen creature type', '').strip()] if v]}
        return d

    def _with_position(self, pos: Position, fn: Callable[[], Any]) -> Any:
        old = self.position
        self.position = pos
        try:
            return fn()
        finally:
            self.position = old

    def holds(self, st: Static, pos: Position) -> bool:
        from app.rules import statics

        return bool(self._with_position(pos, lambda: statics.conditions_hold(self.view, st.definition,
                                                                             source=self.state.cards[st.source], controller=st.controller)))

    def members(self, st: Static, pos: Position) -> frozenset[str]:
        from app.rules import selectors

        who = st.definition['who']
        if who == 'self':
            return frozenset({st.source}) if st.source in self.cards else frozenset()
        if who == 'attached':
            host = self.state.cards[st.source].attached_to
            return frozenset({host}) if host in self.cards else frozenset()
        selector = selectors.from_key(who)
        return self._with_position(pos, lambda: frozenset(cid for cid, card in self.cards.items()
            if selectors.matches(self.view, selector, card, pos.chars[cid], st.controller, st.source)))

    def alive(self, node: Node, pos: Position) -> bool:
        if node.effect is not None or node.source not in pos.dead:
            return True
        st = node.static
        return bool(st is not None and st.effect_key is not None and st.effect_key > pos.dead[node.source])

    def signature(self, node: Node, pos: Position, *, late: bool = False) -> Signature:
        st = node.static
        if st is not None and id(st) in self.begun:
            sig = Signature(True, self.begun[id(st)], 'lose_all' if late else repr(node.definition))
        else:
            active = self.alive(node, pos) and (st is None or self.holds(st, pos))
            found = (node.fixed if node.fixed is not None else self.members(st, pos) if st is not None else frozenset()) if active else frozenset()
            operation = 'lose_all' if late else repr(node.definition if node.effect is None else node.effect.model_dump(mode='json'))
            sig = Signature(active, found, operation)
        if late or not sig.active:
            return sig
        if node.effect is not None:
            if node.effect.layer != '4':
                return sig
            fields = node.effect.model_dump(mode='json')
        else:
            definition = node.definition or {}
            fields = definition.get('layer4') or definition
        requested: set[str] = set()
        for key in ('add_subtypes', 'set_creature_types', 'set_land_types', 'set_artifact_types'):
            requested.update(fields.get(key) or ())
        if fields.get('all_creature_types'):
            from app.rules.creature_types import CREATURE_TYPES

            requested.update(CREATURE_TYPES)
        if not requested:
            return sig
        from app.rules import layers

        # 205.3d: an added subtype is effective only with its corresponding type.
        # Probe AFTER this node's own type operation: a self-setting creature form
        # must not depend on another animation that supplies the same type.
        applicable = []
        for cid in sorted(sig.members):
            after, _ = apply_type_node(node, pos.chars[cid])
            applicable.append((cid, tuple(sorted(s for s in requested if layers._subtype_fits(s, after.types)))))
        return replace(sig, operation=repr((sig.operation, tuple(applicable))))

    def apply4(self, node: Node, pos: Position, sig: Signature) -> Position:
        if not sig.active:
            return pos
        chs, dead = dict(pos.chars), dict(pos.dead)
        for cid in sig.members:
            chs[cid], sets = apply_type_node(node, chs[cid])
            if sets:
                dead.setdefault(cid, (-1, 0, 0))
        return Position(chs, dead)

    def schedule(self, pending: Sequence[Node], late: bool = False) -> None:
        pending = list(pending)
        while pending:
            pos = self.position
            def signature(node: Node, at: Position) -> Signature:
                return self.signature(node, at, late=late)
            def apply(node: Node, at: Position, sig: Signature) -> Position:
                if not late:
                    return self.apply4(node, at, sig)
                dead = dict(at.dead)
                if sig.active:
                    for cid in sig.members:
                        dead[cid] = max(dead.get(cid, (-1, 0, 0)), node.key)
                return Position(at.chars, dead)
            def depends(i: int, j: int, pos: Position = pos) -> bool:
                x, y = pending[i], pending[j]
                return signature(x, pos) != signature(x, apply(y, pos, signature(y, pos)))
            i = next_index([n.key for n in pending], depends) if len(pending) > 1 else 0
            node = pending.pop(i)
            sig = signature(node, pos)
            self.position = apply(node, pos, sig)
            if node.static is not None:
                if sig.active:
                    self.begun.setdefault(id(node.static), sig.members)
                else:
                    self.removed.add(id(node.static))
            if not late and sig.active:
                for cid in sig.members:
                    self.orders[cid].append(node)

    def run(self) -> tuple[StaticTable, dict[str, Key]]:
        from app.rules import group_layers, layers
        from app.rules.attached_types import wipe_key

        self.schedule(self.nodes4)
        # Layer5 keeps original timestamp ordering; earlier-start effects keep members.
        colors: list[tuple[Key, Node]] = []
        for st in self.raw:
            d = st.definition
            if st.gate is not None or not (d.get('layered') or d.get('who') == 'self' or d.get('who') == 'attached'):
                continue
            entry = group_layers._colors(self.state, st)
            if entry:
                colors.append((st.key, Node(st.key, static=st, definition=entry, source=st.source)))
        colors.extend((n.key, n) for n in self.fixed if n.effect is not None and n.effect.layer == '5')
        for _, node in sorted(colors, key=lambda row: row[0]):
            color_st = node.static
            if color_st is not None and id(color_st) in self.begun:
                sig = Signature(True, self.begun[id(color_st)], '')
            else:
                sig = self.signature(node, self.position)
            if not sig.active:
                if color_st is not None:
                    self.removed.add(id(color_st))
                continue
            if color_st is not None:
                self.begun.setdefault(id(color_st), sig.members)
            chs = dict(self.position.chars)
            for cid in sig.members:
                self.color_orders[cid].append(node)
                chs[cid] = layers._layer5(chs[cid], [node.effect] if node.effect is not None else [],
                                          [] if node.effect is not None else [(node.key[0], node.definition or {})])
            self.position = Position(chs, self.position.dead)
        late = [Node(wipe_key(st), static=st, source=st.source) for st in self.raw if st.gate is None and st.definition.get('lose_all')]
        late += [n for n in self.fixed if n.effect is not None and n.effect.layer == '6' and n.effect.remove_abilities]
        self.schedule(late, late=True)
        out = []
        for st in self.raw:
            if id(st) in self.removed:
                continue
            begun = self.begun.get(id(st))
            if begun is not None:
                out.append(replace(st, members=begun, order=0))
            elif self.alive(Node(st.key, static=st, source=st.source), self.position):
                if st.definition.get('layered') and st.gate is None:
                    found = self.members(st, self.position) if self.holds(st, self.position) else frozenset()
                    out.append(replace(st, members=found, order=0))
                else:
                    out.append(st)
        return StaticTable(out, self.raw, {cid: tuple(nodes) for cid, nodes in self.orders.items()},
                           {cid: tuple(nodes) for cid, nodes in self.color_orders.items()}), self.position.dead


@dataclass(frozen=True)
class SolvedField:
    origin: GameState
    state: GameState
    incoming: CardInstance | None
    table: StaticTable
    wiped: dict[str, Key]



def _unchanged_field(state: GameState, raw: Sequence[Static]) -> bool:
    for st in raw:
        d = st.definition
        if (first_layer(d) < 6 or has_layer4(d) or d.get('layered') or
                d.get('lose_all') or d.get('linked_traits') or
                any(k in d for k in ('set_colors', 'add_colors', 'chosen_color'))):
            return False
    if state.rules is not None:
        if any(e.layer in ('4', '5') or e.remove_abilities for e in state.rules.effects):
            return False
        for cid, card in state.cards.items():
            if not card.zone.endswith(':battlefield'):
                continue
            if card.entry_characteristics is not None:
                return False
            payment = state.rules.payments.get(state.rules.object_id(cid))
            if card.counters.get('time', 0) and payment is not None and payment.alternative == 'impending':
                return False
    return True

def solve_field(state: GameState, info: CardInfo, raw: Sequence[Static],
                incoming: CardInstance | None = None) -> SolvedField:
    """The battlefield and prospective entry use the same core and source table."""
    from app.rules import layers

    # Without an operation in layers 4/5 or an ability-loss frontier, source
    # availability cannot change here. Ordinary layer6/7 predicates still run
    # in their native later stages. Entry probes deliberately keep the complete
    # shared solver, including prospective object identity and source discovery.
    if incoming is None and _unchanged_field(state, raw):
        ids: dict[str, tuple[Node, ...]] = {cid: () for cid, card in state.cards.items() if card.zone.endswith(':battlefield')}
        return SolvedField(state, state, None, StaticTable(raw, raw, ids, ids), {})

    layers._T.solving.append(list(raw))
    layers._T.depth += 1
    try:
        solver = Solver(state, info, raw, incoming)
        table, wiped = solver.run()
        return SolvedField(state, solver.state, incoming, table, wiped)
    finally:
        layers._T.depth -= 1
        layers._T.solving.pop()

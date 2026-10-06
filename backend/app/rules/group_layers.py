"""-- layers (wave 22A) -- group statics that change what objects ARE (layers 4, 5 and 6) and how they interact, researched against
CR 2026-09-25.

"Nonbasic lands are Mountains." (Blood Moon, Magus of the Moon, Harbinger of the Seas; 305.7), "All creatures lose all abilities and
have base power and toughness 1/1." (Humility), "Each other non-Aura enchantment is a creature in addition to its other types and
has base power and base toughness each equal to its mana value." (Opalescence), "All permanents are colorless.", "All cards that
aren't on the battlefield, spells, and permanents are colorless." (Mycosynth Lattice), "All nonland permanents are legendary.":
every one is a static ability that works on a group and in several layers. A definition carries ``layered`` and the parts by layer
(app/rules/type_statics.py ``parse``): ``layer4`` (the format ``layers._layer4`` reads), ``set_colors`` / ``add_colors`` /
``chosen_color`` (layer 5), ``lose_all`` / ``keep_mana`` (layer 6), ``base`` / ``base_mv`` (layer 7b), ``everywhere`` (it also works on
cards that aren't on the battlefield and on spells, 611.3: the cards and spells it names).

* 613.6: "If an effect starts to apply in one layer and/or sublayer, it will continue to be applied to the same set of objects in each
  other applicable layer and/or sublayer, even if the ability generating the effect is removed during this process." ``solve`` finds,
  for each such static, the objects it begins applying to (``Static.members``) and the layers then use that set (March of the
  Machines' "noncreature artifacts" are no longer noncreature in layer 7b; Humility keeps applying to itself when it is a creature).
* 613.8: within a layer, an effect that depends on another waits for it (613.8a-b), and the order is re-evaluated after each effect
  is applied (613.8c); a dependency loop is applied in timestamp order. Read here: an effect depends on another that would change which
  objects it applies to (Dryad of the Ilysian Grove's "lands you control" depends on Ashaya making creatures lands), or that would take
  away the abilities of the object it comes from (Urborg depends on Blood Moon: 305.7). Everything else is in timestamp order (613.7).
* 305.7: a land whose land types are set loses the abilities of its rules text — its static abilities too: they are not in the table
  once solved. 613.1f: a permanent that lost all abilities in layer 6 has none of its static abilities (an effect that began earlier
  keeps applying, 613.6).
Not modelled: dependencies between per-object effects (resolved spells, Auras) and these statics beyond timestamp order (613.7); a
characteristic-defining ability's dependency rule (613.8a (c)); the leaves-the-battlefield duration of Titania's Song.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.rules import selectors

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import CardInfo, Characteristics
    from app.rules.layers import Static

ALL_COLORS = ["W", "U", "B", "R", "G"]
_END = (10**9, 0, 0)


def first_layer(d: dict[str, Any]) -> int:
    """The layer a layered static begins to apply in (613.6): 4 (types), 5 (colors) or 6 (abilities, then 7)."""
    if d.get("layer4"):
        return 4
    if "set_colors" in d or "add_colors" in d or d.get("chosen_color"):
        return 5
    return 6


def with_chosen(state: GameState, st: Static) -> dict[str, Any]:
    """-- chosen type (wave 26D) -- the layer-4 part of a static that adds "the chosen type": the creature type (or basic land type) its
    source chose as it entered (614.12a, 205.1b), read now (the table is cached by what is on the battlefield, not by what was chosen)."""
    d = st.definition
    l4 = d.get("layer4")
    if not l4 or not l4.get("chosen_type"):
        return d
    value = state.cards[st.source].choices.get("Chosen basic land type" if l4["chosen_type"] == "land" else "Chosen creature type", "").strip()
    return {**d, "layer4": {**l4, "add_subtypes": [value] if value else []}}


def _colors(state: GameState, st: Static) -> dict[str, Any] | None:
    """The layer-5 entry of a static (its chosen color read from its source, 614.12a), or None."""
    d = st.definition
    if d.get("chosen_color"):
        value = state.cards[st.source].choices.get("Chosen color", "").strip().lower()
        return {"add_colors": [selectors.COLORS[value]]} if value in selectors.COLORS else None
    return {k: d[k] for k in ("set_colors", "add_colors") if k in d}


def solve(state: GameState, info: CardInfo, table: list[Static], tkey: tuple) -> tuple[list[Static], dict[str, tuple[int, int, int]]]:
    """The table with each layered static's members found and the statics of permanents that lost their abilities left out, and the
    permanents that lost all abilities here (card id → the ordering key of the latest such effect, as ``attached_types.wipes``)."""
    layered = [st for st in table if st.definition.get("layered") and st.gate is None]
    if not layered:
        return table, {}
    from app.rules import layers as L

    L._SOLVING.append(table)
    L._depth += 1
    try:
        return _Solver(state, info, table, tkey, layered).run()
    finally:
        L._depth -= 1
        L._SOLVING.pop()


class _Solver:
    def __init__(self, state: GameState, info: CardInfo, table: list[Static], tkey: tuple, layered: list[Static]) -> None:
        from app.rules import layers as L

        self.state, self.info, self.table, self.tkey, self.layered = state, info, table, tkey, layered
        self.view = L._view(state, info)
        self.cards = {cid: c for cid, c in state.cards.items() if c.zone.endswith(":battlefield")}
        self.base: dict[str, Characteristics] = {}
        self.effects: dict[str, list[Any]] = {}
        self.own4: dict[str, list[tuple[float, dict[str, Any]]]] = {}
        self.own5: dict[str, list[tuple[float, dict[str, Any]]]] = {}
        self.applied4: dict[str, list[tuple[float, dict[str, Any]]]] = {}
        self.applied5: dict[str, list[tuple[float, dict[str, Any]]]] = {}
        self.members: dict[int, frozenset[str]] = {}
        self.removed: set[int] = set()
        # the timestamp an effect is applied at: its own, or just after the effects it waited for (613.8b)
        self.order: dict[int, float] = {}
        self.waited: dict[int, set[int]] = {}
        self.seen: dict[tuple[Any, ...], Characteristics] = {}
        self.dead: dict[str, tuple[int, int, int]] = {}  # permanents that lost all abilities → the ordering key of the latest effect

    # -- per-object state ----------------------------------------------------------------------
    def _prepare(self, cid: str) -> None:
        from app.rules import characteristics as chars
        from app.rules import layers as L

        card = self.cards[cid]
        self.base[cid] = L.prepared(self.state, card, chars.of(card, self.info), self.info)
        self.effects[cid] = L.affecting(self.state, card)
        attached = L._attached45(self.state, card, self.info, self.table)
        self.own4[cid] = L._own_layer4(self.state, card, self.info, self.table) + attached
        self.own5[cid] = attached + L._own_layer5(self.state, card, self.info, self.table)
        self.applied4[cid], self.applied5[cid] = [], []

    def at(self, cid: str, key: tuple[int, int, int]) -> Characteristics:
        """The object's types and colors as the effects applied so far (and the per-object ones with an earlier timestamp) leave them."""
        from app.rules import layers as L

        if cid not in self.base:
            self._prepare(cid)
        memo = (cid, key, len(self.applied4[cid]), len(self.applied5[cid]))  # (review 22A: the applied lists only grow)
        if memo in self.seen:
            return self.seen[memo]
        eff = [e for e in self.effects[cid] if (e.object_seq, 1, e.timestamp) < key]
        ch = L._layer4(self.base[cid], eff, [x for x in self.own4[cid] if (x[0], 0, 0) < key] + self.applied4[cid])
        out = self.seen[memo] = L._layer5(ch, eff, [x for x in self.own5[cid] if (x[0], 0, 0) < key] + self.applied5[cid])
        return out

    def _matches(self, st: Static, cid: str, ch: Characteristics) -> bool:
        return selectors.matches(self.view, selectors.from_key(st.definition["who"]), self.cards[cid], ch, st.controller, st.source)

    def _begin(self, st: Static, layer: int) -> bool:
        """Does the static begin to apply now (its source still has the ability, 613.6; its conditions hold)? Otherwise it is
        left out (lost) or applies to nothing."""

        if st.source in self.dead:
            self.removed.add(id(st))
            return False
        if st.definition.get("conditions") and not self._holds(st):
            self.members[id(st)] = frozenset()
            return False
        return True

    def _holds(self, st: Static) -> bool:
        """The static's conditions, read now (611.3a): a count of objects ("As long as you control five or more enchantments") from the
        objects as the effects applied so far leave them (613.8: not as they were printed), anything else as ``layers._conditions``."""
        from app.rules import statics as grammar

        source = self.cards[st.source]
        for cond in st.definition["conditions"]:
            value = cond.get("value")
            if cond.get("static") is None and isinstance(value, dict) and set(value) == {"count"}:
                sel = selectors.from_key(value["count"])
                key = (st.seq, 0, 0)
                n = sum(1 for cid in self.cards if selectors.matches(self.view, sel, self.cards[cid], self.at(cid, key), st.controller, st.source))
                if not {"==": n == cond["n"], ">=": n >= cond["n"], "<=": n <= cond["n"], "<": n < cond["n"], ">": n > cond["n"]}[cond["op"]]:
                    return False
            elif not grammar.holds(self.view, cond, source=source, controller=st.controller):
                return False
        return True

    def _find(self, st: Static) -> frozenset[str]:
        key = (st.seq, 0, 0) if first_layer(st.definition) < 6 else _END
        found = frozenset(cid for cid in self.cards if self._matches(st, cid, self.at(cid, key)))
        self.members[id(st)] = found
        return found

    # -- dependencies (613.8) --------------------------------------------------------------------
    def _depends(self, x: Static, y: Static) -> bool:
        """Would applying ``y`` change ``x``: the objects it applies to or whether its source has the ability (613.8a)?"""
        from app.rules import layers as L

        yk, xk = (y.seq, 0, 0), (x.seq, 0, 0)
        sets_land = bool(y.definition["layer4"].get("set_land_types"))
        if sets_land and x.source in self.cards and self._matches(y, x.source, self.at(x.source, yk)):
            return True  # 305.7: the source of x loses its abilities
        for cid in self.cards:
            if not self._matches(y, cid, self.at(cid, yk)):
                continue
            before = self.at(cid, xk)
            after = L._layer4(before, [], [(y.seq, with_chosen(self.state, y))])
            if self._matches(x, cid, before) != self._matches(x, cid, after):
                return True
        return False

    def _takes(self, x: Static, y: Static) -> bool:
        """-- review (wave 22A) -- layer 6: would ``y`` take away the ability ``x`` comes from before ``x`` begins to apply (613.8a:
        its existence; Dress Down on a creature whose static takes abilities: Sludge Monster, Poppet Factory)? An effect that began
        in an earlier layer keeps applying (613.6)."""
        if first_layer(x.definition) < 6 or x.source not in self.cards or (first_layer(y.definition) == 6 and y.source in self.dead):
            return False  # (613.8c: an effect whose ability is already gone takes nothing)
        if id(y) in self.members:
            return x.source in self.members[id(y)]
        return self._matches(y, x.source, self.at(x.source, _END))

    def _next(self, pending: list[Static], depends: Any = None) -> Static:
        if len(pending) == 1:
            return pending[0]
        depends = depends or self._depends
        deps = {id(x): [y for y in pending if y is not x and depends(x, y)] for x in pending}
        for x in pending:
            self.waited.setdefault(id(x), set()).update(id(y) for y in deps[id(x)])
        ready = [x for x in pending if not deps[id(x)]]
        if ready:
            return min(ready, key=lambda st: st.seq)
        # every remaining effect depends on another: those in a dependency loop apply in timestamp order (613.8b)
        reach: dict[int, set[int]] = {}
        for x in pending:
            seen: set[int] = set()
            todo = list(deps[id(x)])
            while todo:
                y = todo.pop()
                if id(y) not in seen:
                    seen.add(id(y))
                    todo += deps[id(y)]
            reach[id(x)] = seen
        loop = [x for x in pending if id(x) in reach[id(x)]]
        return min(loop or pending, key=lambda st: st.seq)

    # -- the layers ----------------------------------------------------------------------------
    def run(self) -> tuple[list[Static], dict[str, tuple[int, int, int]]]:
        from dataclasses import replace

        from app.rules.attached_types import wipe_key

        pending = [st for st in self.layered if first_layer(st.definition) == 4]
        while pending:  # layer 4 (613.1d)
            st = self._next(pending)
            pending.remove(st)
            if not self._begin(st, 4):
                continue
            found = self._find(st)
            self.order[id(st)] = max([st.seq, *(self.order[w] + 0.5 for w in self.waited.get(id(st), ()) if w in self.order)])
            for cid in found:
                self.applied4[cid].append((self.order[id(st)], with_chosen(self.state, st)))
            if st.definition["layer4"].get("set_land_types"):  # 305.7: those lands lose the abilities of their rules text
                for cid in found:
                    self.dead.setdefault(cid, (-1, 0, 0))
        for st in sorted(self.layered, key=lambda s: s.seq):  # layer 5 (613.1e)
            if first_layer(st.definition) > 5:
                continue
            if first_layer(st.definition) == 5:
                if not self._begin(st, 5):
                    continue
                self._find(st)
            entry = _colors(self.state, st)
            if entry and id(st) in self.members:
                for cid in self.members[id(st)]:
                    self.applied5[cid].append((self.order.get(id(st), st.seq), entry))
        pending = sorted((st for st in self.layered if st.definition.get("lose_all")), key=lambda s: s.seq)
        while pending:  # layer 6 (613.1f): a permanent that loses all abilities; one waits for an effect that takes its ability (613.8)
            st = self._next(pending, self._takes)
            pending.remove(st)
            if first_layer(st.definition) == 6:
                if not self._begin(st, 6):
                    continue
                self._find(st)
            elif id(st) in self.removed:
                continue  # (it never began to apply)
            for cid in self.members.get(id(st), ()):
                self.dead[cid] = max(self.dead.get(cid, (-1, 0, 0)), wipe_key(st))
        for st in self.layered:  # (a static of layer 6 or 7 that doesn't take abilities away: the objects it applies to now)
            fresh = first_layer(st.definition) == 6 and id(st) not in self.members and id(st) not in self.removed
            if fresh and not st.definition.get("lose_all") and self._begin(st, 6):
                self._find(st)
        out: list[Static] = []
        for st in self.table:
            if id(st) in self.removed:
                continue
            if st.definition.get("layered") and st.gate is None:
                out.append(replace(st, members=self.members.get(id(st), frozenset()), order=self.order.get(id(st), st.seq)))
            elif st.source not in self.dead:  # 613.1f / 305.7: a permanent without abilities has no static abilities
                out.append(st)
        return out, self.dead


# -- applying (app/rules/layers.py ``_derive``) ----------------------------------------------------
def entries(state: GameState, card: CardInstance, ch: Characteristics, info: CardInfo | None
            ) -> tuple[list[tuple[float, dict[str, Any]]], list[tuple[float, dict[str, Any]]]]:
    """The layered group statics that apply to ``card`` in layers 4 and 5, each (timestamp, definition): on the battlefield the
    objects found as the table was solved (613.6); elsewhere the cards and spells a static that works everywhere names (611.3)."""
    if info is None or state.rules is None:
        return [], []
    from app.rules import statics as grammar
    from app.rules.layers import _view, probing, statics

    layer4: list[tuple[float, dict[str, Any]]] = []
    layer5: list[tuple[float, dict[str, Any]]] = []
    on_field = card.zone.endswith(":battlefield")
    probe = on_field and probing(state, card)  # (614.12: as it would exist on the battlefield: the subject read from it as printed)
    for st in statics(state, info):
        d = st.definition
        if not d.get("layered") or st.gate is not None:
            continue
        if probe:
            if not grammar.applies(_view(state, info), d, source=state.cards[st.source], controller=st.controller, card=card, ch=ch,
                                   conditions=True):
                continue
        elif on_field:
            if st.members is None or card.id not in st.members:
                continue
        elif not _elsewhere(st, card, ch):
            continue
        if d.get("layer4"):
            layer4.append((st.order or st.seq, with_chosen(state, st)))
        colors = _colors(state, st) if first_layer(d) <= 5 else None
        if colors is not None and ("set_colors" in colors or "add_colors" in colors):
            layer5.append((st.order or st.seq, colors))
    return layer4, layer5


def _elsewhere(st: Static, card: CardInstance, ch: Characteristics) -> bool:
    """Maskwood Nexus: "creature spells you control" (on the stack) and "creature cards you own that aren't on the battlefield"
    (every other zone, the command zone too); Mycosynth Lattice: all of them."""
    where = st.definition.get("everywhere")
    if not where or card.ability is not None or card.zone.endswith(":battlefield"):
        return False
    if where["own"] and (card.controller if card.zone == "stack" else card.owner) != st.controller:
        return False
    if where["types"] and not set(where["types"]) & ch.types:
        return False
    if set(where["not_types"]) & ch.types:
        return False
    return not where["permanent"] or ch.is_permanent_card

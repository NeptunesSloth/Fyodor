"""-- hints speed (wave 29A) -- A read-only pass over a table that cannot change while it runs.

A player's hints ask the same questions of the same table for every card in their hand, graveyard and exile: who has which static
ability, what each permanent is after the layers, what each printing looks like. Worked out afresh each time that was ~2.5 s with
80 permanents on the table (every question derived every permanent again). ``scope`` opens a pass for exactly one table; the answers
shared by the whole pass are kept in it and nowhere else:

* the pass belongs to one thread (``threading.local``): a table another thread is changing is never read from it;
* it belongs to one table *object* and one card-info object (``is``, not ``==``): a scratch copy a probe changes, another game or
  a Plan that carries out actions is never served from it (it does not even see it);
* it ends with the ``with`` block, whether the block returns or raises: nothing is kept for the next call, so nothing a later action
  changes can be read out of it. Callers open it only around code that reads (view.hints, view.rules_view).
"""

from __future__ import annotations

import functools
import threading
import weakref
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from app.game.state import GameState
    from app.rules.characteristics import CardInfo


class ReadPass:
    """The answers one pass shares. ``derived`` / ``printed``: card object id → (the card object, what it was asked with, answer);
    only cards that are in the table itself are kept, and the entry holds the card so its id cannot be reused within the pass."""

    __slots__ = ("state", "info", "table", "derived", "printed", "once", "facts", "effects", "seen")

    def __init__(self, state: GameState, info: CardInfo) -> None:
        self.state, self.info = state, info
        self.table: Any = None  # layers.statics: the statics table
        self.derived: dict[int, tuple[Any, Any, Any]] = {}  # layers.derive: (card, printed characteristics, derived)
        self.printed: dict[int, tuple[Any, Any]] = {}  # characteristics.of: (card, printed characteristics)
        self.once: dict[Any, Any] = {}  # ``once``: the other answers that depend on the table alone
        self.facts: dict[str, tuple[int, Any]] = {}  # ``card_fact``: (the owning plan's writes then, answer)
        self.effects: tuple[tuple[int, Any, int], dict[str, list[Any]]] | None = None  # ``effects_by_object``: (guard, index)
        # -- big boards round 3 -- a pass kept between checks (``Plan.reading``): each WATCHED rules field read while it was open → that
        # field as it was then (``field_json``). None: a pass nothing compares later (not kept), which notes nothing.
        self.seen: dict[str, str | None] | None = None


T = TypeVar("T")
_PASS = threading.local()
_WATCHING = threading.local()  # -- big boards round 3 -- ``passes``: the kept passes open on this thread (``enter``), innermost last
_OWNERS = threading.local()  # -- read passes (repeat speed) -- id(table) -> the Plan carrying out actions on that table (weakly held)


def own(state: GameState, plan: Any) -> None:
    """``plan`` carries out actions on ``state``: readers handed only the table may use its kept passes (``adopted``)."""
    owners = getattr(_OWNERS, "map", None)
    if owners is None:
        owners = _OWNERS.map = weakref.WeakValueDictionary()
    owners[id(state)] = plan


@contextmanager
def adopted(state: GameState, info: CardInfo) -> Iterator[ReadPass]:
    """``scope`` for a reader handed only the table: the pass already open, else the owning plan's (``Plan.reading``)."""
    if (sc := current(state, info)) is not None:
        yield sc
        return
    owners = getattr(_OWNERS, "map", None)
    plan = owners.get(id(state)) if owners is not None else None
    if plan is None or plan.state is not state or plan.info is not info:
        with scope(state, info) as sc:
            yield sc
        return
    with plan.reading() as sc:
        yield sc


def adopting(info_at: int) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """A function of (table, …, info at position ``info_at`` or keyword ``info``) that only reads the table: run it in ``adopted``."""
    def wrap(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def run(state: GameState, *args: Any, **kw: Any) -> T:
            info = kw["info"] if "info" in kw else args[info_at - 1]
            if info is None:
                return fn(state, *args, **kw)
            with adopted(state, info):
                return fn(state, *args, **kw)
        return run
    return wrap


def current(state: GameState, info: CardInfo | None) -> ReadPass | None:
    """The pass this thread is making over exactly this table with exactly this card info, if any."""
    sc: ReadPass | None = getattr(_PASS, "cur", None)
    return sc if sc is not None and sc.state is state and sc.info is info else None


def for_info(info: CardInfo) -> ReadPass | None:
    """The pass this thread is making with this card info (for readers that are not handed the table)."""
    sc: ReadPass | None = getattr(_PASS, "cur", None)
    return sc if sc is not None and sc.info is info else None


def once(state: GameState, info: CardInfo | None, key: Any, compute: Callable[[], T]) -> T:
    """``compute()`` — an answer that depends on this table and the arguments in ``key`` alone — read once per pass (outside a pass, and
    while a derivation is part-way, every time). ``compute`` must not change the table and must not be handed the answer back changed:
    it is shared."""
    from app.rules.layers import settled  # (layers imports this module)

    sc = current(state, info)
    if sc is None or not settled():
        return compute()
    if key not in sc.once:
        sc.once[key] = compute()
    return sc.once[key]


def card_fact(state: GameState, key: str, compute: Callable[[], T]) -> T | None:
    """-- big boards (perf) -- ``compute()``: an answer read from the fields of the table's cards alone (no characteristics, nothing
    derived: e.g. which cards something is attached to), read once per pass and kept while the table is exactly as it was. None
    when there is no such pass: the caller reads the cards itself. A derivation reads such a fact for every permanent it derives, and
    reading it from every card in the game each time made a scan of the battlefield cost the square of the table.

    Only for a pass over the scratch table of a Plan (``own``): that table's cards change only through ``Plan.do`` (the table actions,
    which count themselves in ``Plan.writes``), so an answer kept with the count it was read at is the table's answer while the
    count is the same, even if a block that only reads were to carry out an action part-way. Any other table: None."""
    got = _owned(state)
    if got is None:
        return None
    sc, plan = got
    writes = getattr(plan, "writes", 0)
    hit = sc.facts.get(key)
    if hit is not None and hit[0] == writes:
        return hit[1]
    value = compute()
    sc.facts[key] = (writes, value)
    return value


def _owned(state: GameState) -> tuple[ReadPass, Any] | None:
    """The pass this thread is making over ``state``, the scratch table of a Plan (``own``), and that plan; else None."""
    sc: ReadPass | None = getattr(_PASS, "cur", None)
    if sc is None or sc.state is not state:
        return None
    owners = getattr(_OWNERS, "map", None)
    plan = owners.get(id(state)) if owners is not None else None
    return (sc, plan) if plan is not None and plan.state is state else None


def effects_by_object(state: GameState) -> dict[str, list[Any]] | None:
    """-- big boards (perf) -- rules object id → the continuous effects of ``state.rules.effects`` whose ``affected`` names it, in their
    order (each effect once), read once per read pass over a Plan's scratch table (else None: the caller reads the effects itself). A
    derivation looks for the effects on one object (layers.affecting, the copy effect of layer 1: copying._layer1) in every effect of the
    game, so with a copy effect per token a scan of the battlefield cost the square of the board.

    Kept in the pass like the statics table it keeps (built from the same effects), so it is good while the pass is (``Plan.reading``
    compares the whole rules state before a kept pass is used again); and read again whenever the plan carried out a table action
    (``Plan.writes``: a step's bookkeeping moves effects to an object's new id, ``track``) or the effects list itself was replaced or
    grew (``layers.add_effect``) since it was read."""
    got = _owned(state)
    r = state.rules
    if got is None or r is None:
        return None
    sc, plan = got
    effects = r.effects
    if sc.effects is not None:
        (writes, seen, n), index = sc.effects
        if writes == getattr(plan, "writes", 0) and seen is effects and n == len(effects):
            return index
    index = {}
    for e in effects:
        for oid in dict.fromkeys(e.affected):
            index.setdefault(oid, []).append(e)
    sc.effects = ((getattr(plan, "writes", 0), effects, len(effects)), index)
    return index


@contextmanager
def enter(sc: ReadPass) -> Iterator[ReadPass]:
    """``scope`` with a pass kept from before (``Plan.reading``: the table is exactly as it was when the pass began)."""
    prev: ReadPass | None = getattr(_PASS, "cur", None)
    if prev is not None and prev.state is sc.state and prev.info is sc.info:
        sc = prev
    _PASS.cur = sc
    watching = sc.seen is not None  # -- big boards round 3 -- while it is open, the first read of each WATCHED rules field is noted in it
    if watching:
        open_ = getattr(_WATCHING, "passes", None)
        if open_ is None:
            open_ = _WATCHING.passes = []
        open_.append(sc)
    try:
        yield sc
    finally:
        _PASS.cur = prev
        if watching:
            _WATCHING.passes.pop()


# -- big boards round 3 -- a cheaper comparison for a kept pass. ``Plan.reading`` uses a kept read pass again only while the table is exactly
# as it was; it told that by serialising the whole rules state for every check (about 35 times per trigger on a big board), and most of it
# is the event list, the last known information, the stack and this turn's history, which grow with every step and which almost no kept
# answer reads. Now a WATCHED field is compared only if the kept pass read it:
#
# * a WATCHED field is read through ``_Watched`` (a data descriptor on its model class, which Python consults before the instance's own
#   attributes); while kept passes are open on this thread (``enter``, nested ones too), the first read of the field notes it in each of
#   them as it is then (``seen``: the kept table's field, serialised like ``Plan._mark``, whichever object was read);
# * ``Plan.reading`` uses a kept pass again only if the rest of the rules state is exactly as it was (``Plan._mark``, as before, without
#   the WATCHED fields) and each field the pass noted is exactly as it was when noted (``unchanged``).
#
# Exact: every kept answer (characteristics, the statics table, ``once``, the card facts, the effects index) is worked out while its pass
# is open, from the table it is handed, reading the rules state through attributes; an answer that read a WATCHED field has it compared,
# and one that did not cannot depend on it. (Serialising, copying or comparing a model reads its ``__dict__`` without the descriptor; no
# kept answer is worked out that way: the scratch tables derivations build are ``model_copy`` of the state, sharing its rules object.)
# The descriptor reads and writes the instance's own ``__dict__``, as an attribute without it would: values, saves and copies are unchanged.
WATCHED = frozenset({"events", "lki", "stack", "stack_lki", "controlled_since",  # fields of RulesState: the big ones, and
                     # the bookkeeping each step or trigger moves on (a kept pass that never read it outlives it: a batch of 80
                     # landfall triggers derived the board once more per trigger only because the trigger collector had looked)
                     "batch", "trigger_batch", "once_per_turn", "lands_played", "draws_turn", "recent", "recent_labels", "recent_turn",
                     "actions", "last_actor"})
WATCHED_LOG = frozenset({"facts", "entered"})  # fields of TurnLog (both RulesState.turn_log and .last_turn_log: one key for the two)
_INCLUDE: dict[str, Any] = {**{name: {name} for name in WATCHED},
                            **{f"log.{name}": {"turn_log": {name}, "last_turn_log": {name}} for name in WATCHED_LOG}}
# what ``Plan._mark`` leaves out of the rules state for them (``exclude`` of pydantic's serialiser)
MARK_EXCLUDE: dict[str, Any] = {**dict.fromkeys(WATCHED, True), **{log: dict.fromkeys(WATCHED_LOG, True) for log in ("turn_log", "last_turn_log")}}


def field_json(state: GameState, key: str) -> str | None:
    """A WATCHED field of ``state`` (``key``: a RulesState field, or ``log.<TurnLog field>`` for both turn logs), serialised; None: no
    rules state."""
    r = state.rules
    return None if r is None else type(r).__pydantic_serializer__.to_json(r, include=_INCLUDE[key], warnings=False).decode()


def unchanged(sc: ReadPass) -> bool:
    """Is every WATCHED field the kept pass ``sc`` read exactly as it was when the pass read it?"""
    return not sc.seen or all(field_json(sc.state, key) == was for key, was in sc.seen.items())


class _Watched:
    """A WATCHED field: the instance's own value; its first read is noted in each kept pass open on this thread."""

    __slots__ = ("name", "key")

    def __init__(self, name: str, key: str) -> None:
        self.name, self.key = name, key

    def __get__(self, obj: Any, owner: Any = None) -> Any:
        if obj is None:
            return self
        open_ = getattr(_WATCHING, "passes", None)
        if open_:
            key = self.key
            for sc in open_:
                if key not in sc.seen:
                    sc.seen[key] = field_json(sc.state, key)
        return obj.__dict__[self.name]

    def __set__(self, obj: Any, value: Any) -> None:
        obj.__dict__[self.name] = value


def watch(rules_cls: Any, log_cls: Any) -> None:
    """Read the WATCHED fields of the rules state class and of the turn log class through ``_Watched`` (once)."""
    for cls, names, prefix in ((rules_cls, WATCHED, ""), (log_cls, WATCHED_LOG, "log.")):
        for name in names:
            if not isinstance(cls.__dict__.get(name), _Watched):
                assert name in cls.model_fields, name
                setattr(cls, name, _Watched(name, prefix + name))


@contextmanager
def scope(state: GameState, info: CardInfo) -> Iterator[ReadPass]:
    """Run code that only reads ``state``. Re-entered with the same table and info, it shares the pass already open."""
    prev: ReadPass | None = getattr(_PASS, "cur", None)
    sc = prev if prev is not None and prev.state is state and prev.info is info else ReadPass(state, info)
    _PASS.cur = sc
    try:
        yield sc
    finally:
        _PASS.cur = prev

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

    __slots__ = ("state", "info", "table", "derived", "printed", "once")

    def __init__(self, state: GameState, info: CardInfo) -> None:
        self.state, self.info = state, info
        self.table: Any = None  # layers.statics: the statics table
        self.derived: dict[int, tuple[Any, Any, Any]] = {}  # layers.derive: (card, printed characteristics, derived)
        self.printed: dict[int, tuple[Any, Any]] = {}  # characteristics.of: (card, printed characteristics)
        self.once: dict[Any, Any] = {}  # ``once``: the other answers that depend on the table alone


T = TypeVar("T")
_PASS = threading.local()
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


@contextmanager
def enter(sc: ReadPass) -> Iterator[ReadPass]:
    """``scope`` with a pass kept from before (``Plan.reading``: the table is exactly as it was when the pass began)."""
    prev: ReadPass | None = getattr(_PASS, "cur", None)
    if prev is not None and prev.state is sc.state and prev.info is sc.info:
        sc = prev
    _PASS.cur = sc
    try:
        yield sc
    finally:
        _PASS.cur = prev


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

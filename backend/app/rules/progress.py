"""-- resolving progress -- a read-only look at an action while the engine is still carrying it out.

One player action can run a long automatic chain (200 Kiki-Jiki copies sacrificed at the end step, each sacrifice resolving in turn):
the server works it out inside that one action, and the tables would show nothing until it is done. A session that wants to show the
chain as it goes (``GameSession.prepare``) opens ``watching`` around the compile, on the thread doing it; the engine calls ``resolved``
after each object it resolves on automatic passes (engine.advance), and the watcher may look at the action's scratch table then.

What the watcher may do is read: never change the plan's table, its steps or its random numbers. The engine's output (``plan.steps``)
is the same with or without a watcher, so history, undo and replay never depend on it. Only the action's own plan is reported (the
outermost compile on this thread: ``compiling``), never a probe's scratch copy.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

Watcher = Callable[[Any, int], None]  # (the plan, objects resolved so far in this action)

log = logging.getLogger(__name__)
_LOCAL = threading.local()


@contextmanager
def watching(watcher: Watcher | None) -> Iterator[None]:
    """Report the resolutions of the action compiled inside this block (on this thread) to ``watcher``."""
    prev = getattr(_LOCAL, "watcher", None), getattr(_LOCAL, "plan", None), getattr(_LOCAL, "n", 0), getattr(_LOCAL, "depth", 0)
    _LOCAL.watcher, _LOCAL.plan, _LOCAL.n, _LOCAL.depth = watcher, None, 0, 0
    try:
        yield
    finally:
        _LOCAL.watcher, _LOCAL.plan, _LOCAL.n, _LOCAL.depth = prev


@contextmanager
def compiling() -> Iterator[None]:
    """Around ``compile_intent``: only the outermost compile's plan is the action's own."""
    _LOCAL.depth = getattr(_LOCAL, "depth", 0) + 1
    try:
        yield
    finally:
        _LOCAL.depth -= 1


def adopt(plan: Any) -> None:
    """``plan`` carries out the action being watched (a compile run again with token stacks spread makes a new one: it takes over)."""
    if getattr(_LOCAL, "watcher", None) is not None and getattr(_LOCAL, "depth", 0) == 1:
        _LOCAL.plan = plan


def resolved(plan: Any) -> None:
    """The engine resolved one more object for the action (engine.advance)."""
    watcher = getattr(_LOCAL, "watcher", None)
    if watcher is None or plan is not getattr(_LOCAL, "plan", None):
        return
    _LOCAL.n += 1
    try:
        watcher(plan, _LOCAL.n)
    except Exception:  # noqa: BLE001 - showing progress must never break the action: stop showing it
        log.exception("Resolving progress failed; the rest of this action is shown when it is done")
        _LOCAL.watcher = None

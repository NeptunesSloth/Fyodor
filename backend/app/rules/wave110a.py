"""-- wave 110A -- dispatcher: exact Oracle wordings of PARTIAL cards, read onto existing machinery by the ``wave110a_*`` modules.

Each module exports ``BUILDERS`` (a whole spell/ability body, ``~`` for the card's name, -> parsed effects) and/or ``DEFINITIONS`` (a whole ability
text -> builder of its definition) and ``PRIMITIVES``. A wording not listed stays unsupported."""
from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

MODULES = ("wave110a_spells",)
Parsed = tuple[list[dict[str, Any]], Any, bool]


def _mods() -> list[Any]:
    return [importlib.import_module(f"app.rules.{m}") for m in MODULES]


def parse(body: str) -> Parsed | None:
    for mod in _mods():
        build: Callable[[], Parsed] | None = getattr(mod, "BUILDERS", {}).get(body.strip())
        if build is not None:
            return build()
    return None


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    for mod in _mods():
        build = getattr(mod, "DEFINITIONS", {}).get(scripts.self_text(ability.text, ch.name))
        if build is not None:
            return build(ability, ch)
        if (fn := getattr(mod, "definition", None)) is not None and (got := fn(ability, ch)) is not None:
            return got
    return None


def primitives() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for mod in _mods():
        out.update(getattr(mod, "PRIMITIVES", {}))
    return out

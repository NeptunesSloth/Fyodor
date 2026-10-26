"""-- wave 110A -- dispatcher: exact Oracle wordings of PARTIAL cards, read onto existing machinery by the ``wave110a_*`` modules.

Each module exports ``BUILDERS`` (a whole spell/ability body, ``~`` for the card's name, -> parsed effects) and/or ``DEFINITIONS`` (a whole ability
text -> builder of its definition) and ``PRIMITIVES``. A wording not listed stays unsupported."""
from __future__ import annotations

import importlib
import re
from collections.abc import Callable
from typing import Any

MODULES = ("wave110a_spells", "wave110a_choosers", "wave110a_parade", "wave110a_teferi", "wave110a_averna", "wave110a_enter", "wave110a_aminatou", "wave110a_bolas")
Parsed = tuple[list[dict[str, Any]], Any, bool]


def _mods() -> list[Any]:
    return [importlib.import_module(f"app.rules.{m}") for m in MODULES]


_LABEL = re.compile(r"^(?P<w>(?:[A-Z0-9][\w'’!?,.\-]*|a|an|the|of|and|or|in|on|to|for|with|at|from|by|as)(?: (?:[A-Z0-9][\w'’!?,.\-]*|a|an|the|of|and|or|in|on|to|for|with|at|from|by|as))*) — "
                    r"(?P<rest>[A-Z].*)$")


def strip_mode_label(text: str) -> str:
    """207.2d: the name before the dash of a bulleted mode ("• Take the Elevator — Create three …") is a flavor word with no rules meaning."""
    m = _LABEL.match(text)
    return m["rest"] if m is not None and len(m["w"]) <= 48 and m["w"].lower() != "choose one" else text


def parse(body: str) -> Parsed | None:
    from app.rules import scripts

    for mod in _mods():
        build: Callable[[], Parsed] | None = getattr(mod, "BUILDERS", {}).get(body.strip())
        if build is not None:
            return build()
        if (same := getattr(mod, "REWRITES", {}).get(body.strip())) is not None:  # the same sentences in words the grammar reads (608.2c)
            return scripts.parse_effects(same)
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


def holds(plan: Any, ctx: dict[str, Any], cond: dict[str, Any]) -> bool:
    """A condition of ``{"w110a": kind, …}``: the kind's function in the first module that has it (``CONDITIONS``)."""
    for mod in _mods():
        if (fn := getattr(mod, "CONDITIONS", {}).get(cond["w110a"])) is not None:
            return bool(fn(plan, ctx, cond))
    raise ValueError(f"unknown wave 110A condition {cond!r}")


def primitives() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for mod in _mods():
        out.update(getattr(mod, "PRIMITIVES", {}))
    return out


def resume() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for mod in _mods():
        out.update(getattr(mod, "RESUME", {}))
    return out

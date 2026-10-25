"""-- wave 110I -- exact Oracle wordings of single cards, read as a wording the grammar already reads (``_AS``) or built from parts of it.

Each entry matches one whole ability's Oracle text exactly and nothing else; any other wording stays unsupported.
Researched against the Comprehensive Rules of 2026-09-25.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

Def = dict[str, Any]


def _won_last(d: Def) -> Def:
    """701.30d: the last instruction (the token's haste) happens only if you won the clash the trigger is about."""
    *head, last = d["effects"]
    return {**d, "effects": [*head, {"do": "only_if", "cond": {"clash_won100a": True}, "skip": 1}, last]}


# whole ability text -> (the wording the grammar reads, what to change in its definition)
_BUILD: dict[str, tuple[str, Callable[[Def], Def]]] = {
    "Whenever you clash, you may pay {1}. If you do, create a 3/1 red Elemental Shaman creature token. If you won, that token gains haste until end of turn.":
        ("Whenever you clash, you may pay {1}. If you do, create a 3/1 red Elemental Shaman creature token. That token gains haste until end of turn.", _won_last),
}


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    built = _BUILD.get(ability.text.strip())
    if built is None:
        return None
    native = scripts.define(replace(ability, text=built[0]), ch)
    return None if native is None else built[1](native)

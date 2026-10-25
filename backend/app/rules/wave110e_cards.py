"""-- wave 110E -- exact Oracle wordings of single cards, built from a wording the grammar reads plus native effects.

Each entry matches one whole ability's Oracle text exactly and nothing else; any other wording stays unsupported.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

Def = dict[str, Any]

# 701.29a: fateseal N = look at the top N cards of an opponent's library (chosen, not targeted), any number to the bottom, the rest back on top
# in any order. Only the looking player sees them (look_top reveal false).
_FATESEAL2 = [{"do": "choose_value", "who": "you", "what": "opponent", "as": "fs110e"},
              {"do": "look_top", "n": 2, "player": "ref:fs110e", "reveal": False},
              {"do": "pick_looked", "n": 2, "optional": True, "to": "bottom_any", "reveal": False},
              {"do": "rest_looked", "to": "top_any"}]

# whole ability text -> (the wording the grammar reads for the first part, the effects appended)
_APPEND: dict[str, tuple[str, list[Def]]] = {
    "Put target creature on top of its owner's library, then fateseal 2.":
        ("Put target creature on top of its owner's library.", _FATESEAL2),
}


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    got = _APPEND.get(ability.text.strip())
    if got is None:
        return None
    native = scripts.define(replace(ability, text=got[0]), ch)
    return None if native is None else {**native, "effects": [*native["effects"], *got[1]]}

"""Exact canonical mana-X grant over native cost provenance and static grants."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

NEXOS = ('Strategic Coordinator — Basic lands you control have "{T}: Add {C}{C}. '
         'Spend this mana only on costs that contain {X}."')


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    if ability.kind != 'static' or ability.text != NEXOS:
        return None
    from app.rules import scripts

    return scripts.define(replace(ability, text=ability.text.split(' — ', 1)[1]), ch)

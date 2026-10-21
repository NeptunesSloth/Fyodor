"""Staged resolved Saga grants and linked mana/casting chapters."""
from __future__ import annotations

from dataclasses import replace
from typing import Any


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if ability.kind == 'static' and text == ('II — This Saga gains "Creatures you control have '
            '\'{T}: Add {R}, {G}, or {W}.\'"'):
        from app.rules import sagas

        base = sagas.chapter_definition(replace(ability, text='II — Gain 1 life.'), ch)
        if base is not None:
            return {**base, 'effects': [{'do': 'become', 'who': 'self', 'types': [],
                'abilities': ['Creatures you control have "{T}: Add {R}, {G}, or {W}."'], 'duration': 'permanent'}]}
    return None

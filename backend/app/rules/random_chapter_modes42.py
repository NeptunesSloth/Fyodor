"""Staged random chapter modes reuse native chapter and modal announcement paths."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

_HEADER = 'I, II, III — Choose one at random —'
_ROWS = ['• Combine Powers! — Put three +1/+1 counters on target creature.',
         '• Defense! — Put a shield counter on target creature. You gain 3 life.',
         '• Fight! — This creature fights up to one target creature an opponent controls.']
_NATIVE = ['• Put three +1/+1 counters on target creature.',
           '• Put a shield counter on target creature. You gain 3 life.',
           '• This creature fights up to one target creature an opponent controls.']


def merge_lines(ch: Any, out: dict[int, Any]) -> None:
    from app.rules import modal_abilities

    if 'Saga' not in ch.subtypes:
        return
    for position, ability in enumerate(ch.abilities):
        rows = ch.abilities[position + 1:position + 4]
        if ability.text != _HEADER or [r.text for r in rows] != _ROWS:
            continue
        header = replace(ability, kind='triggered', text='When this creature enters, choose one —')
        rewritten_rows = [replace(row, text=text) for row, text in zip(rows, _NATIVE, strict=True)]
        replacements = {a.index: a for a in [header, *rewritten_rows]}
        rewritten = replace(ch, abilities=tuple(replacements.get(a.index, a) for a in ch.abilities))
        found = modal_abilities.definitions(header, rewritten)
        if found and found[ability.index].get('modal'):
            found[ability.index] = {**found[ability.index], 'trigger': 'chapter', 'chapters': [1, 2, 3],
                                    'modal': {**found[ability.index]['modal'], 'random': True}}
            out.update(found)

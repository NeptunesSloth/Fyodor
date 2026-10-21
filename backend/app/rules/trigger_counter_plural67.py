"""Plural Human counter packets retain the native once-each-turn trigger limit."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXT = ('Whenever one or more +1/+1 counters are put on one or more Humans you control, '
        'draw a card. This ability triggers only once each turn.')


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered' or ability.text != TEXT:
        return None
    native = scripts.define(replace(ability, text=TEXT.replace('one or more Humans', 'a Human')), ch)
    if native is None or native.get('cond', {}).get('event') != 'counters_put' or native.get('limit') != 'once_each_turn':
        return None
    return {**native, 'cond': {**native['cond'], 'aggregate': True}}

"""One attack event, filtered by the original attacking creature's suspected designation."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXT = 'Whenever one or more suspected creatures you control attack, surveil 1.'
BASE = 'Whenever one or more creatures you control attack, surveil 1.'


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    if ability.kind != 'triggered' or ability.text != TEXT:
        return None
    native = scripts.define(replace(ability, text=BASE), ch)
    if native is None or native.get('cond', {}).get('event') != 'attack':
        return None
    sel = selectors.Selector(types=('Creature',), controller='you', extras=('suspected',)).key()
    return {**native, 'cond': {**native['cond'], 'sel': sel}}

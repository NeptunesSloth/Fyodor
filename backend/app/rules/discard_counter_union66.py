"""A discard's one card may satisfy either printed characteristic branch once."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXT = 'Whenever you discard a Spirit card or a card with disturb, put a +1/+1 counter on ~.'


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.game.state import PLAYER_ZONES
    from app.rules import scripts, selectors

    if ability.kind != 'triggered' or scripts.self_text(ability.text, ch.name) != TEXT:
        return None
    native = scripts.define(replace(ability, text='Whenever you discard a card, put a +1/+1 counter on ~.'), ch)
    if native is None or native.get('cond') is None:
        return None
    either = selectors.Selector(zones=PLAYER_ZONES, either=(
        selectors.Selector(card=True, zones=(), subtypes=('Spirit',)).key(),
        selectors.Selector(card=True, zones=(), with_keywords=('disturb',)).key(),
    ))
    return {**native, 'cond': {**native['cond'], 'obj': either.key()}}

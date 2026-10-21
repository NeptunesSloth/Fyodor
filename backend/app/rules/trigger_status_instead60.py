"""Three exact upkeep alternatives freeze the native status once during resolution."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

CUNNING = ("At the beginning of your upkeep, any number of target players each mill two cards. "
           "If you're the monarch, each of those players mills ten cards instead.")
BOUNTY = ("At the beginning of your upkeep, you may put a land card from your hand onto the battlefield. "
          "If you're the monarch, instead you may put a creature or land card from your hand onto the battlefield.")
KUMENA = ("At the beginning of your upkeep, each player draws a card. "
          "If you have the city's blessing, instead only you draw a card.")


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered' or ability.text not in (CUNNING, BOUNTY, KUMENA):
        return None
    base = ability.text.split('. If ', 1)[0] + '.'
    native = scripts.define(replace(ability, text=base), ch)
    if native is None or len(native.get('effects') or []) != 1:
        return None
    status = 'city_blessing' if ability.text == KUMENA else 'monarch'
    original = native['effects'][0]
    if ability.text == CUNNING:
        alternate = {**original, 'n': 10}
    elif ability.text == KUMENA:
        alternate = {**original, 'who': 'you'}
    else:
        parsed = scripts.parse_effects('You may put a creature or land card from your hand onto the battlefield.')
        if parsed is None or len(parsed[0]) != 1:
            return None
        alternate = {**original, **parsed[0][0]}
    flag = 'trigger_status_instead60'
    return {**native, 'effects': [
        {'do': 'only_if', 'cond': {'status': status}, 'bind': flag, 'skip': 1}, alternate,
        {'do': 'only_if', 'cond': {'flag': flag, 'negate': True}, 'skip': 1}, original]}

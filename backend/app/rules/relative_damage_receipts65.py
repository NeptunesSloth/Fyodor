"""Source damage triggers bind their target to the actual damaged player."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXTS = frozenset({
    "Whenever a source you control deals noncombat damage to an opponent, ~ deals that much damage to target creature or planeswalker that player controls.",
    "Whenever a source you control deals noncombat damage to an opponent, if there are four or more card types among cards in your graveyard, ~ deals that "
    "amount of damage to target creature that player controls.",  # -- turn state (wave 100H) -- Fear of Burning Alive (delirium: 603.4)
})


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    if scripts.self_text(ability.text, ch.name) not in TEXTS:
        return None
    body = ability.text.replace('that player controls', 'an opponent controls')
    body = body.replace('that amount of damage', 'that much damage')
    native = scripts.define(replace(ability, text=body), ch)
    if native is None or native.get('target') is None:
        return None
    original = selectors.from_key(native['target']['what'])
    # Existing trigger announcement binds this selector to TriggerEvent.players;
    # source controller, damage amount, and intervening-if checks stay native.
    return {**native, 'event_players_from_damage_recipient': True, 'target': {**native['target'], 'what': selectors.replace(original, controller='that_player').key()}}

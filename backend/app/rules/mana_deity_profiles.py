"""Native transformations and mana riders of the blue Ojer."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.mana import ManaAbility


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    text = scripts.self_text(ability.text, ch.name)
    if ability.kind == 'triggered' and text == 'Whenever you cast an instant spell from your hand, it gains rebound.':
        base = scripts.define(replace(ability, text='Whenever you cast an instant spell, draw a card.'), ch)
        if base is not None:
            return {**base, 'trigger': 'event', 'cond': {'event': 'cast', 'subject': 'player', 'player': 'you',
                'spell': selectors.Selector(zones=('stack',), types=('Instant',)).key(), 'from': 'hand', 'from_owner': 'you'},
                'effects': [{'do': 'spell_rider', 'who': 'event_spell', 'keyword': 'rebound'}]}
    if ability.kind == 'triggered' and text == ("When ~ dies, return it to the battlefield tapped and transformed "
            "under its owner's control with three time counters on it."):
        base = scripts.define(replace(ability, text="When ~ dies, return this card to the battlefield tapped under its owner's control."), ch)
        if base is not None:
            return {**base, 'effects': [{**e, 'transformed': True, 'counter': 'time', 'counter_n': 3}
                if e.get('do') == 'return_card' else e for e in base['effects']]}
    if ability.kind == 'activated' and text == ('{2}{U}, {T}: Transform ~. Activate only if it has no time '
            'counters on it and only as a sorcery.'):
        return scripts.define(replace(ability, text='{2}{U}, {T}: Transform ~. Activate only if there are no time counters on ~ and only as a sorcery.'), ch)
    return None


def parse_mana(text: str, identity: tuple[str, ...], name: str) -> ManaAbility | None:
    from app.rules import mana as M

    if text == '{T}: Add {U}. Remove a time counter from this land.':
        base = M.parse_mana_ability('{T}: Add {U}.', identity, card_name=name)
        if base is not None:
            return replace(base, immediate_effects=({'do': 'remove_counters', 'who': 'self', 'kind': 'time', 'n': 1},))
    return None

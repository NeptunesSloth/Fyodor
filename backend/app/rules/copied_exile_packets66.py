"""Exact current-resolution exile packets feed native card copying and free casts."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

PLUS = ("+1: ~ deals 1 damage to target player or planeswalker and 1 damage to up to one target creature "
        "that player or that planeswalker's controller controls. That creature can't block this turn.")
ULTIMATE = ('−7: Exile the top ten cards of your library. Choose an instant or sorcery card exiled this way '
            'and copy it three times. You may cast the copies without paying their mana costs.')
STRANGER = ('When ~ enters, for each graveyard with an instant or sorcery card in it, exile target instant or sorcery '
            'card from that graveyard. If two or more cards are exiled this way, choose one of them at random and copy it. '
            'You may cast the copy without paying its mana cost.')
PACKET = 'copied_exile_packet66'


def _target(value: Any, group: int) -> Any:
    if isinstance(value, dict):
        return {key: _target(item, group) for key, item in value.items()}
    if isinstance(value, list):
        return [_target(item, group) for item in value]
    return f'target:{group}' if value in ('target', 'target:0') else value


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import card_copy_sources, scripts, selectors

    text = scripts.self_text(ability.text, ch.name)
    if text == PLUS:
        first = scripts.define(replace(ability, text='+1: This planeswalker deals 1 damage to target player or planeswalker.'), ch)
        second = scripts.define(replace(ability, text=("+1: This planeswalker deals 1 damage to up to one target creature "
            "an opponent controls. That creature can't block this turn.")), ch)
        if first is None or second is None or first.get('target') is None or len(second.get('targets', ())) != 1:
            return None
        group = second['targets'][0]
        relative = selectors.replace(selectors.from_key(group['what']), controller='that_player').key()
        return {**first, 'target': None,
                'targets': [{**first['target'], 'min': 1, 'max': 1}, {**group, 'what': relative, 'of': 0}],
                'effects': [*_target(first['effects'], 0), *_target(second['effects'], 1)]}
    if text == ULTIMATE:
        native = scripts.define(replace(ability, text='−7: Exile the top ten cards of your library.'), ch)
        if native is None:
            return None
        copy, cast = card_copy_sources.copy_cast()
        return {**native, 'effects': [{**native['effects'][0], 'as': PACKET},
            card_copy_sources.select(who='ref:' + PACKET, filter=card_copy_sources.key('instant or sorcery card')),
            {**copy, 'n': 3}, cast]}
    if text == STRANGER:
        native = scripts.define(replace(ability, text=("When this creature enters, for each player, exile up to one target "
            "instant or sorcery card from that player's graveyard.")), ch)
        if native is None or len(native.get('targets', ())) != 1:
            return None
        steps = [card_copy_sources.select(who='ref:' + PACKET, random=True), *card_copy_sources.copy_cast()]
        effects: list[dict[str, Any]] = [{'do': 'exile', 'who': 'all_targets', 'as': PACKET},
                   {'do': 'only_if', 'cond': {'value': {'ref_count': PACKET, 'this_way': 'exiled', 'of': None}, 'op': '>=', 'n': 2}, 'skip': len(steps)}, *steps]
        return {**native, 'targets': [{**native['targets'][0], 'min': 1, 'required_present': True}],
                'effects': [{**effect, 'opponent_aggregate': True} for effect in effects]}
    return None

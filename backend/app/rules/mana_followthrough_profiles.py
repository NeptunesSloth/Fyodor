"""Precise target unions and native counter, land-form, and mana followthrough."""
from __future__ import annotations

from dataclasses import replace
from typing import Any


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    text = scripts.self_text(ability.text, ch.name)
    if ability.kind == 'triggered' and text == ('When ~ dies, if it was a nonland creature, return this card to the '
            'battlefield tapped under your control. She\'s a land named Moon. ~ gains "{T}: Add {C}."'):
        base = scripts.define(replace(ability, text='When ~ dies, if it was a nonland creature, '
            'return this card to the battlefield tapped under your control.'), ch)
        if base is not None:
            return {**base, 'effects': [{**e, 'entry_characteristics': {'set_name': 'Moon', 'set_types': ['Land'],
                'add_abilities': ['{T}: Add {C}.']}} if e.get('do') == 'return_card' else e for e in base['effects']]}
    if ability.kind == 'triggered' and text == ('At the beginning of your end step, untap ~. Until your next turn, '
            '~ becomes a land and gains "{T}: Add {U}."'):
        base = scripts.define(replace(ability, text='At the beginning of your end step, untap ~.'), ch)
        if base is not None:
            return {**base, 'effects': [*base['effects'], {'do': 'become', 'who': 'self', 'types': ['Land'],
                'abilities': ['{T}: Add {U}.'], 'duration': 'next_turn'}]}
    if ability.kind == 'triggered' and text == ("At the beginning of each player's first main phase, that player may put "
            'a +1/+1 counter on ~. If they do, they add {C} for each counter on it.'):
        return scripts.define(replace(ability, text=text.replace('counter on it.', 'counter on ~.')), ch)
    if ability.kind == 'spell' and text == ('Return target instant or sorcery card from your graveyard or exiled card '
            'with flashback you own to your hand. Add {R}.'):
        base = scripts.define(replace(ability, text='Return target card from your graveyard to your hand. Add {R}.'), ch)
        if base is not None:
            gy = selectors.Selector(zones=('graveyard',), zone_owner='you', card=True, types=('Instant', 'Sorcery'))
            exiled = selectors.Selector(zones=('exile',), owner='you', card=True, with_keywords=('flashback',))
            union = selectors.Selector(zones=('graveyard', 'exile'), either=(gy.key(), exiled.key()))
            return {**base, 'target': {'what': union.key()}}
    return None

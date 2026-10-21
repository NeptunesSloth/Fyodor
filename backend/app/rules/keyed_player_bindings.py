"""A source's stable entering or latest combat choice, never a guessed display name."""
from __future__ import annotations

import re
from typing import Any

from app.rules.plan import Plan

LAST = 'creatures attacking the last chosen player'


def remembers_combat(ch: Any) -> bool:
    from app.rules import oracle

    headers = []
    for ab in ch.abilities:
        text = ab.text
        if prefix := oracle.word_prefix(text):
            text = prefix[1]
        if text == 'At the beginning of combat on your turn, choose an opponent.':
            headers.append(ab)
    return len(headers) == 1 and any(LAST in ab.text.lower() for ab in ch.abilities)


def bind(d: dict[str, Any], ch: Any) -> dict[str, Any]:
    if remembers_combat(ch) and d.get('kind') == 'triggered' and d.get('trigger') == 'step:begin_combat:you':
        es = d.get('effects') or []
        if len(es) == 1 and es[0].get('do') == 'choose_value' and es[0].get('what') == 'opponent':
            return {**d, 'effects': [{**es[0], 'remember': True}]}
    return d


def definition(text: str, ch: Any) -> dict[str, Any] | None:
    if text == 'Whenever the chosen player casts a spell, that player mills a card.':
        from app.rules import chosen, selectors

        if not chosen.chooses_player(ch):
            return None
        spell = selectors.parse('spell')
        assert spell is not None
        return {'kind': 'triggered', 'trigger': 'event', 'cond': {'event': 'cast', 'subject': 'player', 'player': 'chosen', 'spell': spell.key()},
                'effects': [{'do': 'mill', 'who': 'event_player', 'n': 1}], 'optional': False, 'target': None}
    return None


def static(text: str) -> dict[str, Any] | None:
    from app.rules import selectors, statics

    m = re.fullmatch(r'Creatures attacking the last chosen player (?P<r>have menace|get \+1/\+0)\.', text)
    if m is None:
        return None
    sel = selectors.Selector(types=('Creature',), attacking=True, extras=('attacking_chosen_player',))
    return statics._definition(sel.key(), None, [], p=1 if m['r'].startswith('get') else 0,
                               keywords=['menace'] if m['r'].startswith('have') else [])


def recipient(plan: Plan, source_card: str | None, source_oid: str | None, target: str) -> bool:
    from app.rules import chosen

    if source_card is None:
        return False
    player = chosen.player_of(plan, source_card, source_oid)
    if player is None:
        return False
    if target in plan.state.players:
        return target == player
    card = plan.state.cards.get(target)
    return card is not None and card.zone.endswith(':battlefield') and card.controller == player

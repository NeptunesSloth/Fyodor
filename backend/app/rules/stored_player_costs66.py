"""Exact stored taxes reuse native duration, optional resolution and caster records."""
from __future__ import annotations

from typing import Any


def parse(body: str, event_player: bool) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    text = body.casefold()
    if text == 'until your next turn, spells your opponents cast cost {1} more to cast.':
        return [{'do': 'cost_modifier', 'delta': 1, 'filter': None, 'caster': 'opponent', 'until': 'next_turn'}], None, False
    if text == 'arrest — detain target creature an opponent controls.':
        return scripts.parse_effects('Detain target creature an opponent controls.')
    if text == 'that player may draw an additional card. if they do, spells they cast this turn cost {2} more to cast.':
        native = scripts.parse_effects('That player may draw a card.', event_player=True)
        if native is None:
            return None
        effects, target, optional = native
        effects = [{**e, 'skip': 2} if e.get('do') == 'only_if' else dict(e) for e in effects]
        return effects + [{'do': 'cost_modifier', 'delta': 2, 'filter': None, 'until': 'end_of_turn', 'recipient66': 'event_player'}], target, optional
    return None

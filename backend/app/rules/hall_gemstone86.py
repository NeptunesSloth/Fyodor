"""One upkeep color choice creates a source-independent temporary land mana rule."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXT = ("At the beginning of each player's upkeep, that player chooses a color. Until end of turn, "
        "lands tapped for mana produce mana of the chosen color instead of any other color.")
BIND = 'hall86_color'
COLORS = {'White': 'W', 'Blue': 'U', 'Black': 'B', 'Red': 'R', 'Green': 'G'}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered' or ability.text != TEXT:
        return None
    base = scripts.define(replace(ability, text="At the beginning of each player's upkeep, that player draws a card."), ch)
    return {**base, 'effects': [{'do': 'choose_value', 'who': 'event_player', 'what': 'color', 'as': BIND},
                              {'do': 'hall86_rule'}]} if base is not None else None


def record(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.errors import ActionError
    from app.rules import context, effects, selectors, tap_mana

    choice = context.refs(ctx).get(BIND, {}).get('value')
    if choice not in COLORS:
        if not effects._players(plan, ctx, 'event_player'):
            return True
        raise ActionError('The saved Hall of Gemstone color is missing; resolve this ability manually')
    rule = {'kind': 'static', 'static': 'mana_replace', 'who': 'any',
            'sel': selectors.Selector(types=('Land',)).key(),
            'op': {'do': 'colored_recolor86', 'to': COLORS[choice]}, 'effects': []}
    return tap_mana.until_eot(plan, ctx, {'def': rule})


PRIMITIVES = {'hall86_rule': record}

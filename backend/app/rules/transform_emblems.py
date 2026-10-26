"""An emblem granted as a permanent transforms into its resulting face (not a trigger)."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

LINE = re.compile(r'As ~ transforms into ~, you get an emblem with "(?P<text>[^"]+)"\.?')


def definition(text: str, kind: str) -> dict[str, Any] | None:
    from app.rules.designations import emblem_text_ok

    m = LINE.fullmatch(text) if kind == 'static' else None
    return {'kind': 'static', 'static': 'as_transform_emblem', 'text': m['text'], 'effects': []} \
        if m is not None and emblem_text_ok(m['text']) else None


def apply(plan: Plan, card: CardInstance) -> None:
    """During an actual turnover, after its face changes and before any transform event/SBA.

    Read the resulting face with continuous effects applied. A copy effect or ability loss
    can suppress the printed ability. Entering or being cast with that face up never calls here.
    The resulting permanent's controller receives the emblem, regardless of who caused the turn.
    """
    from app.rules import designations, scripts, wave110i_cards

    wave110i_cards.transform_attach(plan, card)  # -- cards (wave 110I) -- Curse of Leeches
    if plan.manual(card):
        return
    effects = [d['text'] for d in scripts.definitions(plan.ch(card)).values() if d.get('static') == 'as_transform_emblem']
    for text in effects:
        designations.emblem(plan, {'controller': card.controller, 'source_card': card.id},
                            {'do': 'emblem', 'who': 'you', 'text': text})

"""CR 702.64: each absorb instance prevents N damage per source/event."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.rules import oracle

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan
    from app.rules.replace import Candidate


def candidates(plan: Plan, card: CardInstance, ch: Characteristics) -> list[Candidate]:
    from app.rules.layers import timestamp
    from app.rules.replace import Candidate, conditional_lines

    if not ch.is_creature or 'absorb' not in ch.keywords:
        return []
    out = []
    skip = conditional_lines(ch)
    oid = plan.oid(card)
    for ability in ch.abilities:
        if ability.kind != 'keywords' or 'absorb' not in ability.keywords or ability.index in skip:
            continue
        for index, piece in enumerate(oracle.keyword_pieces(oracle.strip_reminders(ability.text))):
            if m := re.fullmatch(r'absorb (\d+)\.?', piece.strip(), re.I):
                out.append(Candidate(id=f'absorb:{oid}:{ability.index}:{index}', event='damage',
                                     match={'to': {'objects': {'self': True}}},
                                     op={'do': 'prevent', 'n': int(m[1]), 'prevention': True},
                                     controller=card.controller, source_card=card.id, source_oid=oid,
                                     seq=(timestamp(plan.state, card.id), 0, ability.index, index),
                                     label=f'{ch.name}: absorb {m[1]}'))
    return out

"""CR 601.2f: effects that directly adjust a spell's final total mana cost."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.rules import mana as M

if TYPE_CHECKING:
    from app.game.state import GameState
    from app.rules.characteristics import CardInfo

TEXT = 'as long as this artifact is untapped, each spell that would cost less than three mana to cast costs three mana to cast'


def definition(text: str) -> dict[str, Any] | None:
    return {'kind': 'static', 'static': 'spell_mana_floor', 'minimum': 3, 'untapped': True, 'effects': []} if text in (TEXT, TEXT.replace('this artifact', '~')) else None


def minimum(state: GameState, info: CardInfo | None) -> int:
    from app.rules.permissions import _table_statics

    return max((int(d['minimum']) for source, _, d in _table_statics(state, info, {'spell_mana_floor'})
                if not d.get('untapped') or not source.tapped), default=0) if info is not None else 0


def apply(state: GameState, info: CardInfo | None, cost: M.ManaCost) -> M.ManaCost:
    if cost.hybrid or cost.phyrexian:
        # Only concrete announcements can be floored: life is not mana, and {2/B} can be one or two.
        raise ValueError('A spell mana floor requires concrete mana-symbol announcements')
    return cost.plus_generic(max(0, minimum(state, info) - cost.generic - len(cost.colored)))

"""A live, global white-as-red spending permission; actual mana is unchanged."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import GameState
    from app.rules import mana as M
    from app.rules.characteristics import AbilityText, CardInfo, Characteristics

TEXT = 'You may spend white mana as though it were red mana.'


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    if ability.kind == 'static' and ability.text == TEXT:
        return {'kind': 'static', 'static': 'spend_white_red', 'effects': []}
    return None


def present(state: GameState, player: str, info: CardInfo | None) -> bool:
    if info is None or state.rules is None:
        return False
    from app.rules import wave110i_cards

    if wave110i_cards.spending_active(state, player):  # -- cards (wave 110I) -- False Dawn
        return True
    from app.rules import read_pass
    from app.rules.plan import Plan

    def scan() -> bool:
        view = Plan.view(state, player, info)
        for card in state.cards.values():
            if card.controller != player or not card.zone.endswith(':battlefield') or card.face_down:
                continue
            if state.rules is not None and state.rules.card_mode(card.id) == 'manual':
                continue
            if any(ability.kind == 'static' and ability.text == TEXT for ability in view.ch(card).abilities):
                return True
        return False
    return read_pass.once(state, info, f'sunglasses49.spend:{player}', scan)


def spending_cost(state: GameState, player: str, info: CardInfo | None, cost: M.ManaCost) -> M.ManaCost:
    from app.rules import mana as M
    from app.rules import wave110i_cards

    if wave110i_cards.spending_active(state, player):  # -- cards (wave 110I) -- False Dawn: white mana pays any color
        return M.spend_as(cost, 'white_color')
    return M.spend_as(cost, 'white_red') if present(state, player, info) else cost

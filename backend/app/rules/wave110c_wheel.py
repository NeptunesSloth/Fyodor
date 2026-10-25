"""-- Wheel of Sun and Moon (wave 110C) -- 614.1a, 303.4: "If a card would be put into enchanted player's graveyard from anywhere, instead that
card is revealed and put on the bottom of that player's library." A card, not a token (108.2a): owner-based, any zone it comes from."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.rules_state import CardInstance
    from app.rules.plan import Plan
    from app.rules.replacements import Cand

STATIC = "bottom_enchanted110c"
_TEXT = "If a card would be put into enchanted player's graveyard from anywhere, instead that card is revealed and put on the bottom of that player's library."


def definition(text: str) -> dict[str, Any] | None:
    return {"kind": "static", "static": STATIC, "effects": []} if text == _TEXT else None


def candidates(plan: Plan, card: CardInstance) -> list[Cand]:
    from app.rules import scripts
    from app.rules.replacements import Cand

    if card.is_token:
        return []
    return [Cand(f"{s.name} (the card is revealed)", "library:bottom") for s in plan.state.cards.values()
            if s.attached_player == card.owner and s.zone.endswith(":battlefield") and not s.face_down and plan.in_game(s) and not plan.manual(s)
            and any(d.get("static") == STATIC for d in scripts.definitions(plan.ch(s)).values())]

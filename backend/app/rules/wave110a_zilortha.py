"""-- wave 110A -- Zilortha, Strength Incarnate: "Lethal damage dealt to creatures you control is determined by their power rather than their toughness."

120.6 / 704.5g: damage is lethal when it is at least the creature's toughness; with this static, the creature's power stands in (Scryfall ruling 2020-04-17): every check
of lethal damage uses it - the state-based action, a trampler's assignment (702.19b) and excess damage (120.10) - and a creature with 0 power is destroyed only when
it has at least 1 damage marked on it (so the basis is never below 1). The 0-toughness state-based action (704.5f) is no consequence of damage, so it is unchanged.
Nonlethal damage may become lethal when Zilortha enters or leaves (the check reads the table now). Only creatures of Zilortha's controller."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

TEXT = "Lethal damage dealt to creatures you control is determined by their power rather than their toughness."
STATIC = "power_lethal110a"


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    return {"kind": "static", "static": STATIC, "effects": []} if ability.text.strip() == TEXT else None


def basis(plan: Plan, card: CardInstance, ch: Characteristics, toughness: int | None) -> int | None:
    """The damage that is lethal to ``card`` (instead of its toughness while a Zilortha of its controller's applies)."""
    from app.rules import prohibitions, sba

    if toughness is None or not ch.is_creature or not any(src.controller == card.controller for src, _ in prohibitions._statics(plan, STATIC)):
        return toughness
    power = sba.power(card, ch)
    return max(1, power if power is not None else 1)

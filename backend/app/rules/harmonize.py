"""-- casting extras (wave 18E) -- harmonize (CR 702.180), researched against the stored Comprehensive Rules (2026-09-25).

* 702.180a — "Harmonize [cost]": "You may cast this card from your graveyard by paying [cost] and tapping up to one untapped creature you
  control rather than paying this spell's mana cost" (an alternative cost, 118.9, offered as escape's and disturb's are: ``Offer.escape``,
  tag "harmonize"), "its total cost is reduced by an amount of generic mana equal to the tapped creature's power" (``casting.cast_spell``
  reads the power of what the cost tapped), and "if the harmonize cost was paid, exile this card instead of putting it anywhere else any
  time it would leave the stack" (the flashback bookkeeping: ``RulesState.flashback``).
* 702.180b — the creature is chosen as the cost is chosen (601.2b) and tapped as it is paid (601.2h): it may be none (``up_to``). Tapping a
  creature for a cost isn't a {T} cost: one that came under your control this turn can be tapped.
-- cast keywords (wave 43D) -- a harmonize cost with {X} (Nature's Rhythm, Zenith Festival) is read: 107.3a, the X announced for the spell is the cost's too
(``casting.cast_spell``: X comes with the cast, the total cost is worked out with it, then the tapped creature's power reduces the generic part).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.game.state import zone_key
from app.rules import alt_costs
from app.rules import costs as C

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import CardInfo, Characteristics

_LINE = re.compile(r"^harmonize (?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)


def parse(line: str) -> str | None:
    m = _LINE.fullmatch(re.sub(r"\s*\(.*?\)", "", line).strip().rstrip("."))
    return m["cost"] if m else None


def offers(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo) -> list[alt_costs.Offer]:
    """The harmonize cost ``player`` could cast this card (in their own graveyard) for."""
    if card.owner != player or card.zone != zone_key(player, "graveyard") or card.token \
            or (state.rules is not None and state.rules.card_mode(card.id) == "manual"):
        return []
    key = C._selector("untapped creature you control", zone="battlefield")
    out: list[alt_costs.Offer] = []
    for ab in ch.abilities:
        cost = parse(ab.text) if ab.kind == "keywords" and ab.keywords == ("harmonize",) else None
        alt = alt_costs.parse_cost(f"pay {cost}", x_ok=True) if cost else None
        if alt is not None and key is not None:
            tap = C.CostComponent(C.TAP_OTHER, amount=1, selector=key, up_to=True, text="Tap up to one untapped creature you control")
            alt = alt_costs.AltCost(alt.mana, C.AbilityCost(components=(tap,)))
            out.append(alt_costs.Offer(f"{card.id}:{ab.index}", f"{ch.name}: harmonize {cost}", alt, escape=True, tag="harmonize"))
    # -- one-card wordings (wave 110B) -- "gains harmonize until end of turn. Its harmonize cost is equal to its mana cost." (graveyard_grants, 611.2a)
    granted = state.rules is not None and any(g.get("oid") == state.rules.object_id(card.id) and g.get("turn") == state.turn.number
                                              and g.get("harmonize") for g in state.rules.graveyard_grants)
    if granted and key is not None and ch.mana_cost and "//" not in ch.mana_cost and not card.face and "//" not in (card.name or ""):
        alt = alt_costs.parse_cost(f"pay {ch.mana_cost}", x_ok=True)
        if alt is not None:
            tap = C.CostComponent(C.TAP_OTHER, amount=1, selector=key, up_to=True, text="Tap up to one untapped creature you control")
            out.append(alt_costs.Offer(f"{card.id}:granted", f"{ch.name}: harmonize {ch.mana_cost}", alt_costs.AltCost(alt.mana, C.AbilityCost(components=(tap,))),
                                       escape=True, tag="harmonize"))
    return out

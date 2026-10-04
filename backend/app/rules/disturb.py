"""-- casting extras (wave 18E) -- disturb (CR 702.146), researched against the stored Comprehensive Rules (2026-09-25).

* 702.146a — "Disturb [cost]" on the front face of a double-faced card: "You may cast this card transformed from your graveyard by
  paying [cost] rather than its mana cost" — an alternative cost (118.9) and a permission (601.3), offered as escape's are
  (app/rules/escape.py; ``Offer.escape`` marks a cast from the graveyard that is its own alternative cost).
* 702.146b / 712.8c — the spell is the back face: :func:`cast_face` turns the intent to face 1 before anything is read, so the spell
  on the stack has the back face's characteristics (cost for timing, type, enchant) and the resolving permanent enters with its back
  face up. Off the stack and battlefield a card shows its front face again (712.8a).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.game.state import zone_key
from app.rules import alt_costs

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import CardInfo

_LINE = re.compile(r"^disturb (?P<cost>(?:\{[^}X]+\})+)$", re.IGNORECASE)


def parse(line: str) -> str | None:
    """The mana cost of a "Disturb {cost}" line, or None."""
    m = _LINE.fullmatch(re.sub(r"\s*\(.*?\)", "", line).strip().rstrip("."))
    return m["cost"] if m else None


def offers(state: GameState, player: str, card: CardInstance, info: CardInfo) -> list[alt_costs.Offer]:
    """The disturb cost ``player`` could cast this card (in their own graveyard) transformed for."""
    from app.rules import characteristics as chars

    data = info.get(card.card_id) if card.card_id else None
    if data is None or data.get("layout") != "transform" or card.owner != player or card.zone != zone_key(player, "graveyard") \
            or card.token or (state.rules is not None and state.rules.card_mode(card.id) == "manual"):
        return []
    front = chars.printed_from_data(data, 0)
    out: list[alt_costs.Offer] = []
    for ab in front.abilities:
        cost = parse(ab.text) if ab.kind == "keywords" and ab.keywords == ("disturb",) else None
        alt = alt_costs.parse_cost(f"pay {cost}") if cost else None
        if alt is not None:
            out.append(alt_costs.Offer(f"{card.id}:{ab.index}", f"{front.name}: disturb {cost}", alt, escape=True, tag="disturb"))
    return out


def cast_face(state: GameState, player: str, card: CardInstance, info: CardInfo, alt_cost: str | None) -> bool:
    """Whether this cast of a card from the graveyard is a disturb cast (the alternative cost named, or the only way)."""
    found = offers(state, player, card, info)
    if not found or alt_cost is not None:
        return any(o.key == alt_cost for o in found)
    # (-- review (wave 18E) -- unnamed: disturb only when nothing else lets them cast the front face from there, as escape: casting.cast_grant)
    from app.rules import characteristics as chars
    from app.rules import permissions

    front = chars.as_cast(card, info, None)
    return not any(g.zone_ok and not g.free for g in permissions.grants(state, player, card, front, info, verb="cast"))

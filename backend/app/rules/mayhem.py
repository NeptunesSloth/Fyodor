"""-- Marvel keywords (wave 25A) -- mayhem (CR 702.187), researched against the stored Comprehensive Rules (2026-09-25).

* 702.187a — mayhem is a static ability that functions while the card is in a player's graveyard.
* 702.187b — "Mayhem [cost]": "As long as you discarded this card this turn, you may cast it from your graveyard by paying [cost] rather than
  paying its mana cost. Timing rules still apply." An alternative cost (118.9) and a permission (601.3), offered as escape's, disturb's and
  harmonize's are (``Offer.escape``, tag "mayhem"); what was cast that way is not exiled afterwards (it isn't flashback), and "if this spell's
  mayhem cost was paid" reads the payment record (``PaymentRecord.alternative`` "mayhem").
* 702.187c — "Mayhem" without a cost: "You may play this card from your graveyard if you discarded it this turn" (a land is played, a
  spell is cast for its mana cost: ``permissions.grants``).
* "Each nonland card in your graveyard has mayhem. The mayhem cost is equal to its mana cost." (Norman Osborn's back face): a static that
  gives the cards the keyword (``mayhem_grant``); a card with no mana cost, or a split card (two mana costs), isn't offered.

"You discarded this card this turn" (701.9a): the card went from its owner's hand to the graveyard as a discard this turn
(``TurnLog.facts``, kept per rules object: a card that left the graveyard and came back is a new object, 400.7). A mayhem cost with {X}
isn't read.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.game.state import zone_key
from app.rules import alt_costs

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import CardInfo, Characteristics

_LINE = re.compile(r"^mayhem(?: (?P<cost>(?:\{[^}X]+\})+))?$", re.IGNORECASE)
GRANT = re.compile(r"^each (?P<sel>[A-Za-z][A-Za-z -]*?) cards? in your graveyard has mayhem\. the mayhem cost is equal to "
                   r"(?:its|that card's|the card's) mana cost$", re.IGNORECASE)


def parse(line: str) -> str | None:
    """The cost of a "Mayhem {cost}" line ("" for a bare "Mayhem"), or None when the line isn't one."""
    m = _LINE.fullmatch(re.sub(r"\s*\(.*?\)", "", line).strip().rstrip("."))
    return None if m is None else (m["cost"] or "")


def discarded_this_turn(state: GameState, card: CardInstance) -> bool:
    """701.9a, 702.187b: this card (this object, 400.7) was discarded this turn."""
    r = state.rules
    log = r.turn_log if r is not None else None
    if r is None or log is None or log.turn != state.turn.number:
        return False
    oid = r.object_id(card.id)
    return any(f.kind == "discard" and f.object_id == oid for f in log.facts)


def _may(state: GameState, player: str, card: CardInstance) -> bool:
    return card.owner == player and card.zone == zone_key(player, "graveyard") and not card.token \
        and state.rules is not None and state.rules.card_mode(card.id) != "manual" and discarded_this_turn(state, card)


def offers(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo) -> list[alt_costs.Offer]:
    """The mayhem costs ``player`` could cast this card (in their own graveyard) for: its own line and the ones permanents give it."""
    if not _may(state, player, card):
        return []
    out: list[alt_costs.Offer] = []
    for ab in ch.abilities:
        cost = parse(ab.text) if ab.kind == "keywords" and ab.keywords == ("mayhem",) else None
        alt = alt_costs.parse_cost(f"pay {cost}") if cost else None
        if alt is not None:
            out.append(alt_costs.Offer(f"{card.id}:{ab.index}", f"{ch.name}: mayhem {cost}", alt, escape=True, tag="mayhem"))
    out += granted_offers(state, player, card, ch, info)
    return out


def granted_offers(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo) -> list[alt_costs.Offer]:
    from app.rules import mana as M
    from app.rules import permissions, selectors
    from app.rules.graveyard_grants import _two_ways

    out: list[alt_costs.Offer] = []
    granted = permissions._table_statics(state, info, {"mayhem_grant"})
    if not granted or not ch.mana_cost or "//" in ch.mana_cost or _two_ways(card):
        return out
    cost = M.parse_cost(ch.mana_cost)
    if cost.x or cost.unsupported or (alt := alt_costs.parse_cost(f"pay {ch.mana_cost}")) is None:
        return out
    view = permissions._view(state, player, info)
    for src, index, d in granted:
        if src.controller == player and selectors.matches(view, selectors.from_key(d["filter"]), card, ch, player, src.id):
            out.append(alt_costs.Offer(f"{src.id}:{index}", f"{src.name}: mayhem {ch.mana_cost}", alt, escape=True, tag="mayhem"))
    return out


def plays_land(state: GameState, player: str, card: CardInstance, ch: Characteristics) -> bool:
    """702.187c: a bare "Mayhem" lets its owner play the card from the graveyard (a land) when they discarded it this turn."""
    return _may(state, player, card) and any(ab.kind == "keywords" and ab.keywords == ("mayhem",) and parse(ab.text) == ""
                                             for ab in ch.abilities)


def define_grant(t: str) -> dict | None:
    """The static "Each nonland card in your graveyard has mayhem. The mayhem cost is equal to its mana cost." (``t``: the line,
    first letter lowercased, no period)."""
    from app.rules import selectors

    m = GRANT.fullmatch(t)
    if m is None:
        return None
    sel = selectors.parse(f"{m['sel']} card in your graveyard")
    if sel is None or sel.player is not None or sel.zones != ("graveyard",) or not sel.card or sel.zone_owner not in (None, "you"):
        return None
    return {"kind": "static", "static": "mayhem_grant", "filter": sel.key(), "effects": []}

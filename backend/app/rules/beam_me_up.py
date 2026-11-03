"""-- Star Trek mechanics (wave 112T) -- beam me up, from the Star Trek release notes
(https://magic.wizards.com/en/news/feature/star-trek-release-notes). The Comprehensive Rules (2026-09-25) don't define it yet.
# Star Trek release notes (2026-11): re-check against the CR when it defines beam me up

* "Beam me up [cost]" means "You may cast this card from your graveyard by paying [cost] and returning a creature you control to its
  owner's hand rather than paying its mana cost" and "If the beam me up cost was paid, exile this card instead of putting it anywhere
  else any time it would leave the stack." (release notes). It is read as harmonize (702.180a) and flashback (702.34a) are: a permission
  to cast from the graveyard plus an alternative cost (118.9), offered as escape's is (``Offer.escape``, tag "beam_me_up"); the creature
  is a part of that cost (a RETURN_PERMANENT component, chosen as the cost is chosen, 601.2b, and returned as it is paid, 601.2h); the
  exile is the flashback bookkeeping (``RulesState.flashback``).
* "You must still follow any timing restrictions and permissions" (``casting.timing_problem``, as for escape); "start with the mana cost or
  alternative cost (such as a beam me up cost) you're paying, add any cost increases, then apply any cost reductions" (601.2f, 118.9d);
  "You can cast a spell using beam me up even if it was somehow put into your graveyard without having been cast" (only where the card is).
* "A permanent that 'can't be beamed up' can't be returned to a player's hand to pay a beam me up cost." (Marooned: the selector extra
  ``beamable112t``.)
* Scotty, Miracle Worker: "During your main phase, each card in your graveyard has beam me up. The beam me up cost is equal to that spell's
  mana cost. Scotty can't be beamed up to cast a spell this way." Its reminder text: "Only instant and sorcery spells can be cast this
  way"; its ruling: "Scotty can't be returned to your hand to pay the beam me up cost of spells cast with the beam me up ability granted by
  his ability. He can be returned … to pay the beam me up cost of spells that are cast using their own beam me up abilities." A card with
  two mana costs (split, adventure, double-faced) isn't offered a granted cost (which one is unsettled), as granted mayhem and harmonize.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from app.game.state import zone_key
from app.rules import alt_costs, selectors
from app.rules import costs as C

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import CardInfo, Characteristics
    from app.rules.plan import Plan

TAG = "beam_me_up"
EXTRA = "beamable112t"  # selectors: a creature that can be beamed up
_LINE = re.compile(r"^beam me up (?P<cost>(?:\{[^}X]+\})+)$", re.IGNORECASE)
_RETURN_TEXT = "Return a creature you control to its owner's hand"
GRANT = ("During your main phase, each card in your graveyard has beam me up. The beam me up cost is equal to that spell's mana cost. "
         "~ can't be beamed up to cast a spell this way.")
_CANT = re.compile(r"^(?P<who>Enchanted (?:permanent|creature|artifact)) (?P<rest>.+?) and can't be beamed up\.$")


def parse(line: str) -> str | None:
    """The mana cost of a "Beam me up {cost}" line, or None."""
    m = _LINE.fullmatch(re.sub(r"\s*\(.*?\)", "", line).strip().rstrip("."))
    return m["cost"] if m else None


def _returned(not_oid: str | None) -> C.CostComponent | None:
    key = C._selector("creature you control", zone="battlefield")
    if key is None:
        return None
    sel = selectors.from_key(key)
    extras = (*sel.extras, EXTRA, *((f"not_oid:{not_oid}",) if not_oid else ()))
    return C.CostComponent(C.RETURN_PERMANENT, amount=1, selector=replace(sel, extras=extras).key(), text=_RETURN_TEXT)


def _offer(key: str, label: str, mana: str, not_oid: str | None = None) -> alt_costs.Offer | None:
    alt = alt_costs.parse_cost(f"pay {mana}", x_ok=True)
    comp = _returned(not_oid)
    if alt is None or comp is None:
        return None
    return alt_costs.Offer(key, label, alt_costs.AltCost(alt.mana, C.AbilityCost(components=(comp,))), escape=True, tag=TAG)


def offers(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo) -> list[alt_costs.Offer]:
    """The beam me up costs ``player`` could cast this card (in their own graveyard) for: its own lines, then Scotty's grants."""
    r = state.rules
    if card.owner != player or card.zone != zone_key(player, "graveyard") or card.token or r is None or r.card_mode(card.id) == "manual" \
            or not ch.is_instant_or_sorcery:  # (Scotty's reminder text: "Only instant and sorcery spells can be cast this way")
        return []
    out: list[alt_costs.Offer] = []
    for ab in ch.abilities:
        cost = parse(ab.text) if ab.kind == "keywords" and ab.keywords == ("beam me up",) else None
        if cost and (o := _offer(f"{card.id}:{ab.index}", f"{ch.name}: beam me up {cost}", cost)) is not None:
            out.append(o)
    return out + _granted(state, player, card, ch, info)


def _granted(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo) -> list[alt_costs.Offer]:
    """Scotty: during the player's main phase (505.1), for the card's own mana cost; Scotty himself can't be returned for it."""
    from app.rules import permissions
    from app.rules.graveyard_grants import _two_ways

    if state.turn.active_player != player or state.turn.phase not in ("main1", "main2"):
        return []
    if not ch.mana_cost or "//" in ch.mana_cost or _two_ways(card) or card.face:
        return []
    out: list[alt_costs.Offer] = []
    r = state.rules
    assert r is not None
    for src, index, _d in permissions._table_statics(state, info, {"beam_grant112t"}):
        if src.controller == player and (o := _offer(f"{src.id}:{index}", f"{src.name}: beam me up {ch.mana_cost}", ch.mana_cost,
                                                     not_oid=r.object_id(src.id))) is not None:
            out.append(o)
    return out


def beamable(plan: Plan, card: CardInstance) -> bool:
    """False for a permanent something says "can't be beamed up" (Marooned's enchanted permanent)."""
    from app.rules import scripts

    for other in plan.state.cards.values():
        if other.attached_to != card.id or not other.zone.endswith(":battlefield") or other.face_down or plan.rules.card_mode(other.id) == "manual":
            continue
        if any(d.get("cant_beam112t") == "host" for d in scripts.definitions(plan.ch(other)).values()):
            return False
    return True


def definition(ability: Any, ch: Characteristics) -> dict[str, Any] | None:
    """Scotty's grant, and "Enchanted permanent <restriction> and can't be beamed up." (the restriction's own reading, marked)."""
    from app.rules import scripts

    if ability.kind != "static" or ability.index >= 100:
        return None
    text = scripts.self_text(ability.text, ch.name)
    if text == GRANT:
        return {"kind": "static", "static": "beam_grant112t", "effects": []}
    m = _CANT.fullmatch(text)
    if m is None:
        return None
    d = scripts.define(replace(ability, text=f"{m['who']} {m['rest']}."), ch)
    return None if d is None else {**d, "cant_beam112t": "host"}

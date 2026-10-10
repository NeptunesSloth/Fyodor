"""-- zone keyword grants (wave 25A) -- "Each creature card in your hand has cycling {1}{U}." (Rhet-Tomb Mystic), "Each creature card in
your graveyard has unearth {2}{B}." (Sedris), "Each instant
and sorcery card in your hand has miracle {2}." (Lorehold, the Historian), "Each enchantment card in your hand has miracle. Its miracle
cost is equal to its mana cost reduced by {4}." (Aminatou, Veil Piercer), "Each artifact creature card in your graveyard has encore. Its
encore cost is equal to its mana cost." (Wire Surgeons).

* 113.6, 113.6m: an ability granted to a card in a hand or a graveyard works from there — cycling and miracle are the card's
  abilities in a hand (702.29a, 702.94), unearth and encore in a graveyard (702.84, 702.141); the card keeps what its printed text
  and effects give it (613.1f: layer 6, the abilities are added after the printed ones, numbered from 100 as every granted ability is).
* 400.7: the grant is read afresh each time the card is looked at (it is a static ability of the permanent, 604.1): the card has it
  only while the static applies, and a card that leaves the hand or graveyard has it no more.
* "Equal to its mana cost [reduced by {N}]": the cost is worked out from the card's mana cost as it is (generic mana only is reduced,
  118.7a); a card with no mana cost, a split card, a double-faced card, or an X in its cost isn't given the keyword (which mana cost
  is "its" isn't settled, as graveyard_grants._two_ways).
* "Your hand" / "your graveyard" are those of the static's controller (108.4: a card in a graveyard is in its owner's).

The keywords granted are those the engine carries out from the zone: ``KEYWORDS``. Each is read by its own module from the card's
characteristics (casting.cycle, casting.unearth, miracle, graveyard_keywords).
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import CardInfo, Characteristics

KEYWORDS = ("cycling", "unearth", "miracle", "encore")
_LINE = re.compile(r"^(?:each )?(?P<sel>[A-Za-z][A-Za-z ,'/-]*?) in your (?P<zone>hand|graveyard)(?P<tail> that's [A-Za-z ,/-]+?)? (?:has|have) (?P<kw>" + "|".join(KEYWORDS) + r")"
                   r"(?: (?P<cost>(?:\{[^}X]+\})+)| ?\. (?:its|the) [a-z]+ cost is equal to its mana cost(?: reduced by (?P<red>\{\d+\}))?)$",
                   re.IGNORECASE)


def define(t: str) -> dict[str, Any] | None:
    """The static for a granted keyword ``t`` (the line, first letter lowercased, no period), or None."""
    from app.rules import selectors

    m = _LINE.fullmatch(t)
    if m is None:
        return None
    phrase = re.sub(r"\bcards\b", "card", m["sel"])
    sel = selectors.parse(f"{phrase} in your {m['zone']}{m['tail'] or ''}")
    if sel is None or sel.player is not None or sel.zones != (m["zone"],) or not sel.card or sel.zone_owner not in (None, "you"):
        return None
    if m["kw"].lower() not in {"hand": ("cycling", "miracle"), "graveyard": ("unearth", "encore")}[m["zone"]]:
        return None  # (the zone the keyword works from: 702.29a, 702.49a, 702.94a — the hand; 702.84a, 702.141a — the graveyard)
    if m["cost"] is None and m["kw"].lower() not in ("miracle", "encore"):
        return None
    return {"kind": "static", "static": "zone_grant", "filter": sel.key(), "keyword": m["kw"].lower(), "cost": m["cost"],
            "reduce": int(m["red"][1:-1]) if m["red"] else 0, "effects": []}


def _line(d: dict[str, Any], ch: Characteristics, card: CardInstance) -> str | None:
    from app.rules import mana as M
    from app.rules.graveyard_grants import _two_ways

    if d["cost"]:
        return f"{d['keyword'].capitalize()} {d['cost']}"
    if not ch.mana_cost or "//" in ch.mana_cost or _two_ways(card):
        return None
    cost = M.parse_cost(ch.mana_cost)
    if cost.x or cost.unsupported:
        return None
    if d["reduce"]:
        cost = cost.plus_generic(-min(d["reduce"], cost.generic))
    return f"{d['keyword'].capitalize()} {cost.text()}"


def apply(state: GameState, card: CardInstance, ch: Characteristics, info: CardInfo) -> Characteristics:
    """The characteristics of a card in a hand or graveyard with the keywords the statics on the table give it."""
    from app.rules import selectors
    from app.rules.cast_limits import _statics
    from app.rules.plan import Plan
    from app.rules.scripts import parse_abilities

    found = _statics(state, info, "zone_grant")
    if not found:
        return ch
    zone = "hand" if card.zone.endswith(":hand") else "graveyard"
    extra: list[Any] = []
    view = None
    for src, d in found:
        if card.zone != f"{src.controller}:{zone}" or card.owner != src.controller or f"{d['keyword']}" not in KEYWORDS:
            continue
        view = view or Plan.view(state, src.controller, info)
        if not selectors.matches(view, selectors.from_key(d["filter"]), card, ch, src.controller, src.id) or (line := _line(d, ch, card)) is None:
            continue
        parsed = parse_abilities(line)
        if len(parsed) == 1 and parsed[0].kind == "keywords":
            extra.append(replace(parsed[0], index=100 + len(extra)))
    return replace(ch, abilities=ch.abilities + tuple(extra)) if extra else ch

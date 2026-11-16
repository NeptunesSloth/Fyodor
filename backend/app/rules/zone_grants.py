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

KEYWORDS = ("ninjutsu", "cycling", "unearth", "miracle", "encore", "dredge", "scavenge", "jump-start")  # (wave 42A: dredge; 44C: scavenge, jump-start)
_LINE = re.compile(r"^(?:each )?(?P<sel>[A-Za-z][A-Za-z ,'/-]*?) in (?P<owner>your|each player's) (?P<zone>hand|graveyard)(?P<tail> that's [A-Za-z ,/-]+?)? (?:has|have) (?P<kw>" + "|".join((*KEYWORDS, "warp", r"(?:(?:basic|artifact) )?[a-z]+cycling")) + r")"
                   r"(?: (?P<cost>(?:\{[^}X]+\})+)| (?P<num>\d+)|(?P<eq> ?\. (?:its|the) [a-z]+ cost is equal to its mana cost(?: reduced by (?P<red>\{\d+\}))?)"
                   r"| (?P<mv>\{X\}, where X is its mana value))?$",  # (wave 49B: "encore {X}, where X is its mana value", Sliver Gravemother)
                   re.IGNORECASE)  # (wave 44C: the tail is optional: jump-start has none, 702.133a)


def define(t: str) -> dict[str, Any] | None:
    """The static for a granted keyword ``t`` (the line, first letter lowercased, no period), or None."""
    from app.rules import selectors

    m = _LINE.fullmatch(t)
    if m is None:
        return None
    keyword = m["kw"].lower()
    all_players = m["owner"].lower() == "each player's"
    if all_players and not keyword.endswith("cycling"):
        return None
    if keyword == "warp":
        return _warp(m)
    phrase = re.sub(r"^(instant|sorcery) and (instant|sorcery) cards?\b", r"\1 or \2 card", re.sub(r"\bcards\b", "card", m["sel"]))  # (wave 44C: "instant and sorcery")
    sel = selectors.parse(f"{phrase} in your {m['zone']}{m['tail'] or ''}")
    if sel is None or sel.player is not None or sel.zones != (m["zone"],) or not sel.card or sel.zone_owner not in (None, "you"):
        return None
    if keyword not in {"hand": ("cycling", "miracle", "ninjutsu"), "graveyard": ("unearth", "encore", "dredge", "scavenge", "jump-start")}[m["zone"]] and not (
            m["zone"] == "hand" and keyword.endswith("cycling")):
        return None  # (the zone the keyword works from: 702.29a, 702.49a, 702.94a — the hand; 702.84a, 702.141a, 702.52a, 702.97a, 702.133a — the graveyard)
    if m["kw"].lower() == "jump-start":  # -- static_other (wave 44C) -- 702.133a: no cost of its own, the card's cost is paid and a card is discarded
        return {"kind": "static", "static": "zone_grant", "filter": sel.key(), "keyword": "jump-start", "cost": None, "reduce": 0, "effects": []} \
            if not (m["cost"] or m["num"] or m["eq"]) else None
    if m["cost"] is None and not m["num"] and not m["eq"] and not m["mv"]:
        return None
    if m["cost"] is None and m["kw"].lower() not in ("miracle", "encore", "dredge", "scavenge"):
        return None
    if (m["num"] is not None) != (m["kw"].lower() == "dredge"):  # (702.52a: "Dredge N", a number and no cost)
        return None
    if keyword.endswith("cycling"):
        from app.rules import cycling_costs

        if not m["cost"] or not cycling_costs.parts(f"{keyword} {m['cost']}"):
            return None
    if all_players:
        sel = replace(sel, zone_owner=None)
    return {"kind": "static", "static": "zone_grant", **({"all_players": True} if all_players else {}), "filter": sel.key(), "keyword": keyword, "cost": m["cost"],
            "reduce": int(m["red"][1:-1]) if m["red"] else 0, "effects": [], **({"num": int(m["num"])} if m["num"] else {}), **({"mv": True} if m["mv"] else {})}


def _warp(m: re.Match[str]) -> dict[str, Any] | None:
    """-- static_other (wave 42A) -- 702.185a: "Artifact cards and red creature cards in your hand have warp {2}{R}." (Tannuk). The alternative cost is chosen as the spell
    is cast, from the card's printed characteristics (casting.cast_spell), so the grant is read the way a table alternative cost is (alt_costs.offers): for a spell
    of those kinds cast from its caster's hand, "{2}{R}" instead of its mana cost, and the exile at the next end step and the later cast follow from the tag."""
    from app.rules.permissions import spell_filter

    if m["zone"] != "hand" or m["tail"] or not m["cost"]:
        return None
    keys = [spell_filter(re.sub(r"\bcards?\b", "", part).strip()) for part in re.split(r" and ", m["sel"])]
    if not keys or None in keys:
        return None
    return {"kind": "static", "static": "alt_cost", "cost": f"pay {m['cost']}", "table": True, "filter": None, "filters": keys, "once": False,
            "zone": "hand", "mv": None, "cond": None, "tag": "warp", "effects": []}


def _line(d: dict[str, Any], ch: Characteristics, card: CardInstance) -> str | None:
    from app.rules import mana as M
    from app.rules.graveyard_grants import _two_ways

    if d["keyword"] == "jump-start":
        return "Jump-start"
    if d["keyword"] == "brink110b":  # -- Back from the Brink (wave 110B) -- the exile is part of the cost (602.2b), the token is a copy of that card (707.2); paying a mana cost is not casting
        cost = M.parse_cost(ch.mana_cost.replace("{X}", "") or "{0}") if ch.mana_cost and "//" not in ch.mana_cost + ch.name else None  # (712.8a, 715.4: a card in a graveyard has only its front face's characteristics; a split card has both, which cost is "its" is unsettled)
        return None if cost is None or cost.unsupported else (
            f"{cost.text()}, Exile this card from your graveyard: Create a token that's a copy of the card exiled to activate this ability. Activate only as a sorcery.")
    if d.get("num"):
        return f"{d['keyword'].capitalize()} {d['num']}"
    if d.get("mv"):  # (wave 49B) "{X}, where X is its mana value": that much generic mana (an {X} in the card's own cost is 0 there, 107.3g); a card with two ways to read it isn't given it
        return None if "//" in ch.mana_cost or _two_ways(card) else f"{d['keyword'].capitalize()} {{{int(ch.mana_value)}}}"
    if d["cost"]:
        return f"{d['keyword'].capitalize()} {d['cost']}"
    if not ch.mana_cost or "//" in ch.mana_cost or _two_ways(card):
        return None
    cost = M.parse_cost(ch.mana_cost.replace("{X}", "") or "{0}")  # (an {X} in that mana cost is 0: Varolz ruling)
    if cost.unsupported:
        return None
    if d["reduce"]:
        cost = cost.plus_generic(-min(d["reduce"], cost.generic))
    return f"{d['keyword'].capitalize()} {cost.text()}"


def jump_start(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo) -> bool:
    """-- static_other (wave 44C) -- 702.133a: does a static of ``player``'s give this card in their graveyard jump-start? (A cast reads the card as it is cast, so the
    granted ability that ``apply`` adds to a card in a graveyard is not there: the permission is asked here.)"""
    from app.rules import selectors
    from app.rules.cast_limits import _statics
    from app.rules.plan import Plan

    view = None
    r = state.rules  # -- (wave 110O) -- granted until end of turn by a resolved effect (Filigree Racer): graveyard_grants.grant_flashback
    if r is not None and card.zone == f"{player}:graveyard" and card.owner == player and any(
            g.get("jump_start") and g.get("oid") == r.object_id(card.id) and g.get("turn") == state.turn.number for g in r.graveyard_grants):
        return True
    for src, d in _statics(state, info, "zone_grant"):
        if d["keyword"] != "jump-start" or src.controller != player or card.zone != f"{player}:graveyard" or card.owner != player:
            continue
        view = view or Plan.view(state, player, info)
        if selectors.matches(view, selectors.from_key(d["filter"]), card, ch, player, src.id):
            return True
    return False


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
        if (not d.get("all_players") and (card.zone != f"{src.controller}:{zone}" or card.owner != src.controller)
                or d['keyword'] not in KEYWORDS and d['keyword'] not in ("brink110b", "embalm") and not d['keyword'].endswith('cycling')):  # (wave E1: Naktamun's embalm)
            continue
        view = view or Plan.view(state, src.controller, info)
        if not selectors.matches(view, selectors.from_key(d["filter"]), card, ch, src.controller, src.id) or (line := _line(d, ch, card)) is None:
            continue
        parsed = parse_abilities(line)
        if len(parsed) == 1 and (parsed[0].kind == "keywords" or d["keyword"] in ("scavenge", "jump-start", "brink110b")):  # (wave 44C: read as the ability they mean, 702.97a, 702.133a)
            extra.append(replace(parsed[0], index=100 + len(extra)))
    return replace(ch, abilities=ch.abilities + tuple(extra)) if extra else ch

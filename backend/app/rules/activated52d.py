"""-- activated other (wave 52D) -- instructions that activated abilities of older cards use and the grammar did not read.

* **The edge of a graveyard or library.** 404.2: the cards of a graveyard are kept in an order (the last one in the zone list is the top, as
  ``effects.return_choice`` reads it). "Exile the bottom card of target player's graveyard." (Phyrexian Furnace) takes the first. "Put the bottom card of
  your library into your graveyard." (Grenzo, Dungeon Warden; Cellar Door: "Target player puts the bottom card of their library into their graveyard.")
  is no mill (701.17a mills the top), so no "whenever you mill" ability sees it; the card is "it" of the sentence after.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.effects import Context
    from app.rules.plan import Plan

_EDGE = re.compile(r"^(?i:exile the (?P<edge>top|bottom) card of (?:(?P<t>target player)'s|(?P<y>your)) graveyard)$")
_BOTTOM = re.compile(r"^(?i:(?:(?P<t>target player) puts|put) the bottom card of (?:their|your) library into (?:their|your) graveyard)$")


def _edge(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "exile_edge", "who": "target" if m["t"] else "you", "edge": m["edge"].lower()}], "player" if m["t"] else None


def _bottom(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "bottom_to_graveyard", "who": "target" if m["t"] else "you"}], "player" if m["t"] else None


# -- mana (wave 52D) -- 106.4: "Double the amount of each type of unspent mana you have." (Doubling Cube) adds, for each type in the pool, as much again. The mana it adds is
# plain: the cube's ability puts no restriction on it, and what was restricted stays so (106.6).
_DOUBLE = re.compile(r"^(?i:double the amount of each type of unspent mana you have)$")


def _double(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "double_mana"}], None


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_EDGE, _edge), (_BOTTOM, _bottom), (_DOUBLE, _double)]
RECORDING: dict[str, str | None] = {"exile_edge": "exiled", "bottom_to_graveyard": None}  # (scripts._RECORDING and _MOVERS: what a later "it" names)

CHOSEN = {"bottom_to_graveyard": "n"}  # (scripts._CHOSEN: one card, whoever puts it, so a player target still names the card as "it")


def exile_edge(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.game.state import zone_key
    from app.rules.effects import _players, _remember, exile_cards

    for pid in _players(plan, ctx, e["who"]):
        yard = plan.state.zones.get(zone_key(pid, "graveyard"), [])
        if yard:
            card = yard[0] if e["edge"] == "bottom" else yard[-1]
            _remember(plan, ctx, e, [card])
            exile_cards(plan, ctx, e, [card])
    return True


def bottom_to_graveyard(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.game.state import zone_key
    from app.rules.effects import _moved, _players, _remember

    for pid in _players(plan, ctx, e["who"]):
        library = plan.state.zones.get(zone_key(pid, "library"), [])
        if library:
            before = _remember(plan, ctx, e, [library[-1]])  # (the library's last card is its bottom: a mill takes from the front)
            plan.do({"type": "move", "card_ids": [library[-1]], "to": {"zone": "graveyard"}}, actor=pid)
            _moved(plan, ctx, e, before)
    return True


def double_mana(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from collections import Counter

    from app.rules.effects import _put_mana

    me = ctx["controller"]
    pool = plan.state.players[me]
    have = Counter(pool.mana) + Counter(u.sym for u in pool.mana_units)
    return _put_mana(plan, ctx, me, [sym for sym, n in have.items() for _ in range(n)])


PRIMITIVES = {"exile_edge": exile_edge, "bottom_to_graveyard": bottom_to_graveyard, "double_mana": double_mana}
